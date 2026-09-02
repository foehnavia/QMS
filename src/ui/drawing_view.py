"""Чертёж группы: показ во всю ширину, зум и панорамирование.

Заменяет прежний холст с ручной расстановкой меток (наряд 0014, находки №7
и №8 прогона QMS-016).
Чертёж приходит из конструкторского отдела **уже размеченным** — на выносках
стоят метки `G1…GN`, — поэтому приложение своих баллонов не рисует и координат
не хранит. Его работа здесь одна: показать картинку так, чтобы выноска читалась.

Отсюда правила показа:

* по умолчанию — **вписать по ширине**, и вписанная картинка занимает ширину
  области минус ~15 % (`tokens.DRAWING_FIT_RATIO`): чертёж это главный элемент
  экрана, а не иллюстрация сбоку;
* `Ctrl` + колесо — плавный зум, кнопки `+` / `−` / «вписать» — тот же зум
  дискретно, двойной клик возвращает «вписать»;
* когда картинка крупнее области — перетаскивание мышью.

Группа **без чертежа** остаётся рабочей: на месте картинки — пустое состояние
канона §8 с кнопкой загрузки, а таблица позиций рядом полностью функциональна.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QWidget,
)

from . import kit
from .kit import tokens

EMPTY_TITLE = "No drawing loaded"
EMPTY_BODY = (
    "The drawing comes from the engineering department already ballooned — "
    "the callouts carry G1…GN. Load it as issued; the positions below stay "
    "usable without it."
)

ZOOM_IN = "+"
ZOOM_OUT = "−"
FIT_WIDTH = "Fit width"
LOAD = "Load drawing…"
REMOVE = "Remove drawing"

BROKEN_IMAGE = "The drawing could not be displayed — is the file damaged?"


class DrawingView(QScrollArea):
    """Область показа чертежа: масштаб, вписывание, панорамирование.

    Полоса прокрутки, а не своя арифметика смещения: панорамирование сводится к
    сдвигу двух полос, а вписанная по ширине картинка выше области прокручивается
    так же, как любой длинный документ.
    """

    #: Масштаб изменился — панель обновляет свою подпись.
    scaleChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        #: Пока True — масштаб пересчитывается при каждом изменении размера.
        #: Первое, что видит оператор, — вписанный чертёж, и он остаётся
        #: вписанным, пока оператор сам не взялся за зум.
        self._fitting = True
        self._pan_from: QPoint | None = None
        #: Размер, под который область уже разложила свои части (см. `_lay_out`).
        self._laid_out_for = None
        self._laying_out = False

        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Мышь принадлежит области прокрутки: иначе события панорамирования
        # съедала бы картинка, лежащая поверх всей области.
        self._canvas.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.setWidget(self._canvas)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(tokens.DRAWING_MIN_HEIGHT)

    # --- содержимое ------------------------------------------------------------

    def set_drawing(self, data: bytes | None) -> bool:
        """Показать чертёж. `False` — картинка не читается Qt (битый файл)."""
        self._fitting = True
        if not data:
            self._pixmap = None
            self._redraw()
            return True

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._pixmap = None
            self._redraw()
            return False

        self._pixmap = pixmap
        self._redraw()
        return True

    @property
    def pixmap(self) -> QPixmap | None:
        return self._pixmap

    @property
    def scale(self) -> float:
        return self._scale

    @property
    def fitting(self) -> bool:
        """Держится ли вид в режиме «вписано» — по нему тест и отличает режим."""
        return self._fitting

    def shown_size(self):
        """Размер картинки **как она нарисована** — то, что проверяет тест.

        Не `self._scale`, а размер отрисованного pixmap: пиксели и есть ответ
        на вопрос «во всю ли ширину чертёж» (`CLAUDE.md` §9).
        """
        shown = self._canvas.pixmap()
        return None if shown is None or shown.isNull() else shown.size()

    # --- раскладка -------------------------------------------------------------

    def _lay_out(self, force: bool = False) -> None:
        """Досылать себе `resizeEvent`, пока окно не показано.

        Свои части (viewport и полосы) `QScrollArea` раскладывает в
        `resizeEvent`, а скрытому виджету Qt его не шлёт: `resize()` до `show()`
        только запоминает размер. Снимки экрана снимаются как раз **без**
        `show()` (`CLAUDE.md` §9), и без этого досыла чертёж вписывался бы в
        стандартные 640 px, а не в ширину окна.

        `force` — после смены масштаба: полосы прокрутки считают свой ход по
        размеру картинки, а он только что изменился. Повторного входа нет ни в
        том, ни в другом случае — на время досыла стоит флаг.
        """
        if self._laying_out or (not force and self._laid_out_for == self.size()):
            return
        self._laying_out = True
        try:
            self._laid_out_for = self.size()
            QApplication.sendEvent(self, QResizeEvent(self.size(), self.size()))
        finally:
            self._laying_out = False

    # --- масштаб ---------------------------------------------------------------

    def fit_scale(self) -> float:
        """Масштаб «вписать по ширине»: ширина области минус ~15 %."""
        if self._pixmap is None or self._pixmap.isNull() or not self._pixmap.width():
            return 1.0
        self._lay_out()
        available = self.viewport().width() * tokens.DRAWING_FIT_RATIO
        return max(available / self._pixmap.width(), tokens.DRAWING_ZOOM_MIN)

    def fit(self) -> None:
        """Вернуть «вписать по ширине» — двойной клик и кнопка «Fit width»."""
        self._fitting = True
        self._redraw()

    def set_scale(self, scale: float) -> None:
        """Задать масштаб вручную: вписывание с этого момента не навязывается."""
        self._fitting = False
        self._scale = min(max(scale, tokens.DRAWING_ZOOM_MIN), tokens.DRAWING_ZOOM_MAX)
        self._redraw()

    def zoom_in(self) -> None:
        self.set_scale(self._scale * tokens.DRAWING_ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_scale(self._scale / tokens.DRAWING_ZOOM_STEP)

    def _resize_canvas(self, size) -> None:
        """Сменить размер картинки и сказать об этом области прокрутки.

        Ход полос она считает по размеру вложенного виджета и узнаёт о смене
        из его `resizeEvent`. Скрытому виджету Qt событие не шлёт (см.
        `_lay_out`), поэтому досылаем сами — иначе увеличенный чертёж некуда
        двигать: полосы остаются с нулевым ходом, а панорамирование мёртвым.
        """
        previous = self._canvas.size()
        self._canvas.resize(size)
        if not self._canvas.isVisible():
            QApplication.sendEvent(self._canvas, QResizeEvent(size, previous))

    def _redraw(self) -> None:
        self._lay_out()
        if self._pixmap is None or self._pixmap.isNull():
            self._canvas.clear()
            self._resize_canvas(self.viewport().size())
            self.scaleChanged.emit(self._scale)
            return

        if self._fitting:
            self._scale = self.fit_scale()

        size = self._pixmap.size() * self._scale
        self._canvas.setPixmap(
            self._pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._resize_canvas(size)
        self.scaleChanged.emit(self._scale)

    # --- события ---------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        # Пересобираем только вписанный вид: заданный руками масштаб — ответ
        # оператора, и менять его на изменение размера окна значит его стирать.
        if self._fitting:
            self._redraw()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        """`Ctrl` + колесо — зум; колесо само по себе остаётся прокруткой."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.fit()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.pan_begin(event.position().toPoint())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._pan_from is not None:
            self.pan_to(event.position().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.pan_end()
        event.accept()

    # --- панорамирование -------------------------------------------------------
    #
    # Отдельными методами, а не только внутри обработчиков: перетаскивание — это
    # поведение, и тест обязан звать его так же, как зовёт мышь.

    def pan_begin(self, point: QPoint) -> None:
        self._pan_from = point
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def pan_to(self, point: QPoint) -> None:
        if self._pan_from is None:
            return
        delta = point - self._pan_from
        self._pan_from = point
        # Тянут картинку, а не полосу: курсор идёт вправо — содержимое едет
        # вправо, значит смещение уменьшается.
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - delta.x()
        )
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())

    def pan_end(self) -> None:
        self._pan_from = None
        self.viewport().unsetCursor()


class DrawingPane(QWidget):
    """Чертёж с панелью над ним: зум, вписывание и (в редакторе) загрузка.

    Один компонент на два экрана — редактор группы и привязку детали: оператор
    сверяет индекс `g5` с выноской чертежа в обоих, и расходиться поведением им
    незачем.
    """

    loadRequested = Signal()
    removeRequested = Signal()

    def __init__(self, *, editable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = DrawingView()
        self.view.scaleChanged.connect(self._show_scale)

        self.zoom_out_button = kit.secondary(ZOOM_OUT)
        self.zoom_in_button = kit.secondary(ZOOM_IN)
        self.fit_button = kit.secondary(FIT_WIDTH)
        self.zoom_out_button.clicked.connect(self.view.zoom_out)
        self.zoom_in_button.clicked.connect(self.view.zoom_in)
        self.fit_button.clicked.connect(self.view.fit)

        controls = [self.zoom_out_button, self.zoom_in_button, self.fit_button]
        self.load_button = self.remove_button = None
        if editable:
            self.load_button = kit.secondary(LOAD)
            self.remove_button = kit.secondary(REMOVE)
            self.load_button.clicked.connect(self.loadRequested)
            self.remove_button.clicked.connect(self.removeRequested)
            controls += [self.load_button, self.remove_button]

        self.scale_label = kit.status_label()

        # Кнопка загрузки в пустом состоянии — своя: один виджет в двух
        # раскладках жить не может, а выход из пустоты канон §8 требует прямо
        # на месте пустоты.
        empty_action = kit.secondary(LOAD) if editable else None
        if empty_action is not None:
            empty_action.clicked.connect(self.loadRequested)
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY, empty_action)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.empty)

        toolbar = kit.button_row(*controls)
        # Подпись масштаба — после растяжки, у правого края: это состояние вида,
        # а не действие, и в ряду кнопок ему места нет.
        toolbar.addWidget(self.scale_label)

        self.setLayout(kit.column(toolbar, self.stack))
        self.setMinimumHeight(tokens.DRAWING_MIN_HEIGHT)
        self._show_drawing(False)

    def set_drawing(self, data: bytes | None) -> bool:
        """Положить чертёж в панель; `False` — Qt не смог его прочитать."""
        readable = self.view.set_drawing(data)
        self._show_drawing(bool(data) and readable)
        return readable

    def _show_drawing(self, has_drawing: bool) -> None:
        self.stack.setCurrentWidget(self.view if has_drawing else self.empty)
        for button in (self.zoom_out_button, self.zoom_in_button, self.fit_button):
            button.setEnabled(has_drawing)
        if self.remove_button is not None:
            self.remove_button.setEnabled(has_drawing)
        if not has_drawing:
            self.scale_label.setText("")

    def _show_scale(self, scale: float) -> None:
        if self.stack.currentWidget() is self.view:
            self.scale_label.setText(kit.iso(f"{round(scale * 100)} %"))
