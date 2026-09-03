"""`combo` — поле выбора одного значения из **длинного** списка, с отбором.

Находка №17 прогона QMS-016. Обычный `QComboBox` на трёхстах деталях ведёт себя
так, как ему и положено, и это не годится: первая набранная буква перемещает
отметку, но список не сужает; вторая начинает поиск заново, а не уточняет
первую; буква, которой нет ни в одной записи, не делает ничего молча; строки
ввода, которую можно стереть, у элемента нет вовсе.

Решение пользователя (2026-09-03): отбор **прямо в поле**, а не отдельным окном.
Отклонений за смену много, и лишнее окно на каждом — плата, которую платить не
за что. Модальный `PickerDialog` остаётся там, где выбор идёт не внутри формы, а
вопросом перед действием (`pickers.choose_cg_for_item`).

**Почему здесь свой виджет, а не редактируемый `QComboBox`** (доводка §7 наряда
0019: первая редакция приёмку не прошла). У редактируемого списка модель и текст
строки — **один источник**: `clear()` стирает набранное, а заполнение ставит в
строку подпись текущего элемента. Компонент, который на каждое нажатие
пересобирает модель, дерётся сам с собой, и на живой сборке это дало четыре
отказа разом. Замерено на копии базы прогона, настоящими событиями клавиш:
нажали `м` — строка пуста, список полон; нажали `а` — в строке `а`, а в списке
`маккад`; в модели три строки, а по высоте помещается 1.2.

Поэтому строка ввода и список здесь — **разные виджеты**:

* текст в строке принадлежит **только** оператору; код пишет в неё лишь тогда,
  когда жест окончен — выбор сделан или ушёл фокус;
* список — отдельное всплытие над **полным** набором; отбор меняет его
  содержимое и высоту вместе, потому что перестраивается он один;
* значение — по-прежнему ключ (`current_key`), контракт наружу не менялся.

Границы те же, что у `PickerDialog`, и по той же причине (запрет §3а наряда 0010
про **аппарат экрана**: поиск по выдаче, срезы, чипы, экспорт; отбор внутри поля
сужает выбор одного значения, а не меняет, чем список является):

* одна строка отбора, по вхождению подстроки, регистронезависимо;
* отбор не переживает уход фокуса — вернулся, список полон;
* значение поля — всегда ключ из списка, набранный текст значением не станет.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import tokens as t
from .direction import bind_direction, directional, iso


class FilterCombo(QWidget):
    """Поле выбора, сужаемое набранным: строка ввода и всплывающий список.

    Наружу отдаёт **ключ** (`current_key()` / `currentData()`), как и обычный
    список до него, — вызывающий код смысла не меняет.
    """

    #: Выбор сменился. Своим сигналом: перестройка списка отбором выбором не
    #: является, и путать их нельзя.
    keyChanged = Signal(object)

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        #: Полный набор `(ключ, подпись)` — источник правды. Отбор его не трогает.
        self._rows: list[tuple[object, str]] = []
        #: Выбранное значение. Живёт отдельно от того, что показывает список.
        self._key: object | None = None
        self._explaining = False

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        # Каталожные номера латинские, значения справочников бывают ивритскими —
        # направление поля следует за набранным, а не за окном (канон §6).
        bind_direction(self._edit)
        self._edit.textEdited.connect(self._on_typed)
        self._edit.installEventFilter(self)

        # Всплытие, а не выпадающий список элемента: отдельный виджет со своей
        # моделью, и правит её только отбор.
        self._list = QListWidget(self)
        self._list.setWindowFlags(Qt.WindowType.Popup)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._pick)
        directional(self._list)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)
        # Фокус поля — это фокус его строки: снаружи оно одно целое.
        self.setFocusProxy(self._edit)

    # --- содержимое ------------------------------------------------------------

    def set_rows(self, rows: list[tuple[object, str]], *, key: object | None = None) -> None:
        """Задать полный набор значений и, если надо, выбрать одно из них.

        Ключ, которого в новом наборе нет, снимается: показывать выбранным то,
        чего в списке больше не существует, — обещать несуществующее.
        """
        self._rows = list(rows)
        known = {row[0] for row in self._rows}
        if key is not None:
            self._key = key if key in known else None
        elif self._key not in known:
            self._key = None
        self.settle()

    def rows(self) -> list[tuple[object, str]]:
        return list(self._rows)

    def lineEdit(self) -> QLineEdit:  # noqa: N802 - имя как у `QComboBox`
        """Строка ввода. Имя оставлено прежним: на него завязан вызывающий код."""
        return self._edit

    def popup(self) -> QListWidget:
        """Всплывающий список — то, что видит оператор при наборе."""
        return self._list

    # --- значение --------------------------------------------------------------

    def current_key(self) -> object | None:
        """Выбранное значение — то же, что вернёт `currentData()`."""
        return self._key

    def currentData(self, role: int = Qt.ItemDataRole.UserRole):  # noqa: N802 - Qt API
        """Ключ выбранного значения, **независимо от состояния отбора**."""
        return self._key

    def currentText(self) -> str:  # noqa: N802 - Qt API
        """Подпись выбранного значения, а не то, что сейчас набрано.

        Набранное живёт в `lineEdit().text()` и значением поля не является.
        """
        return self.label_of(self._key)

    def label_of(self, key: object | None) -> str:
        for row_key, label in self._rows:
            if row_key == key:
                return label
        return ""

    def select_key(self, key: object | None) -> None:
        """Выбрать значение по ключу — программный путь вместо клика."""
        known = {row[0] for row in self._rows}
        chosen = key if key in known else None
        changed = chosen != self._key
        self._key = chosen
        self.settle()
        if changed:
            self.keyChanged.emit(self._key)

    def setCurrentText(self, text: str) -> None:  # noqa: N802 - Qt API
        """Выбрать по подписи; неизвестная подпись выбором не становится."""
        for key, label in self._rows:
            if label == text:
                self.select_key(key)
                return
        self.select_key(None)

    # --- отбор -----------------------------------------------------------------

    def filter_to(self, text: str) -> list[tuple[object, str]]:
        """Сузить **список** по вхождению подстроки. Строку ввода не трогает.

        По вхождению, а не по началу строки: каталожный номер `MF5-10375A-N`
        оператор помнит серединой чаще, чем префиксом.
        """
        needle = (text or "").strip().casefold()
        matched = [row for row in self._rows if not needle or needle in row[1].casefold()]
        self._fill(matched, needle)
        return matched

    def visible_labels(self) -> list[str]:
        """Что сейчас в списке — то, что видит оператор."""
        return [self._list.item(row).text() for row in range(self._list.count())]

    def is_explaining(self) -> bool:
        """Показывает ли список объяснение вместо значений."""
        return self._explaining

    def settle(self) -> None:
        """Закрыть список и вернуть в строку подпись выбранного.

        Зовётся, когда жест окончен: ушёл фокус, выбрано значение, форма
        спросила состояние. **Во время набора не зовётся никогда** — иначе
        строка перестаёт принадлежать оператору (§7.3 наряда 0019).
        """
        self._list.hide()
        self._explaining = False
        self._edit.setText(self.label_of(self._key))

    # --- события ---------------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is not self._edit:
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.FocusOut:
            # Смотрим на **причину** ухода, а не на то, открыт ли список.
            # Всплытие — отдельное окно, и его появление само по себе забирает
            # фокус (`PopupFocusReason`); откатывать на этом набранное значило
            # бы вернуть тот самый дефект, из-за которого пропадала первая
            # буква. Любая другая причина — оператор ушёл, жест окончен.
            #
            # Проверять видимость списка тут нельзя: тогда уход по Tab с
            # открытым списком оставлял бы в строке несовпавший текст —
            # поймано тестом формы отклонения.
            if event.reason() != Qt.FocusReason.PopupFocusReason:
                self.settle()
        elif event.type() == QEvent.Type.KeyPress and self._on_key(event.key()):
            return True
        return super().eventFilter(watched, event)

    def _on_key(self, key: int) -> bool:
        """Клавиши работы со списком. `True` — событие обработано нами."""
        if not self._list.isVisible():
            return False
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            step = 1 if key == Qt.Key.Key_Down else -1
            self._list.setCurrentRow(
                max(0, min(self._list.currentRow() + step, self._list.count() - 1))
            )
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._list.currentItem()
            if item is not None:
                self._pick(item)
            return True
        if key == Qt.Key.Key_Escape:
            self.settle()
            return True
        return False

    def _on_typed(self, text: str) -> None:
        """Оператор набирает. Трогаем **только список**.

        Строка ввода здесь не переписывается ни при каких обстоятельствах: это и
        есть требование §7.3, и ровно его нарушение съедало первую букву.
        """
        if not text.strip() and self._key is not None:
            # Стёртая строка — законное «не выбрано»: у обоих мест применения
            # это состояние допустимо (деталь ещё не названа, деталь без группы).
            self._key = None
            self.keyChanged.emit(None)
        self.filter_to(text)
        self._open()

    # --- список ----------------------------------------------------------------

    def _fill(self, matched: list[tuple[object, str]], needle: str = "") -> None:
        self._list.clear()
        for key, label in matched:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)

        self._explaining = not matched and bool(needle)
        if self._explaining:
            # Пустой список без объяснения читается как «таких значений нет»,
            # хотя их не пропустил отбор. Строка выключена: объяснение не
            # выбирается и значением стать не может.
            item = QListWidgetItem(_nothing_matches(needle, len(self._rows)))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        elif matched:
            self._list.setCurrentRow(0)

    def _open(self) -> None:
        """Показать список под полем — ростом по тому, что в нём сейчас лежит.

        Высота считается **после** заполнения, поэтому содержимое и рост
        относятся к одному состоянию. В первой редакции они расходились: список
        успевал закрыться и наполниться заново между двумя событиями, и на
        экране выходила одна строка высотой, внутри которой прокручивались все.
        """
        row_height = self._list.sizeHintForRow(0) or t.TABLE_ROW_HEIGHT
        visible = min(max(self._list.count(), 1), t.POPUP_ROWS)

        self._list.setFixedWidth(self.width())
        self._list.setFixedHeight(visible * row_height + self._list.frameWidth() * 2)
        self._list.move(self.mapToGlobal(QPoint(0, self.height())))
        self._list.show()

    def _pick(self, item: QListWidgetItem) -> None:
        """Оператор выбрал строку — она и становится значением поля."""
        key = item.data(Qt.ItemDataRole.UserRole)
        if key is None:
            return
        changed = key != self._key
        self._key = key
        self.settle()
        if changed:
            self.keyChanged.emit(self._key)


def _nothing_matches(needle: str, total: int) -> str:
    """Объяснение пустого результата — теми же словами, что в `PickerDialog`."""
    return (
        f"Nothing matches {iso(needle)} — "
        f"all {total} values are still there, the filter hides them"
    )
