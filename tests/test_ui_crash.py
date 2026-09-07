"""Перехватчик необработанных исключений (доводка 3 наряда `0030`, Д-3.3).

**Проверяется боевой режим, не тестовый** — так требует критерий 3 доводки, и по
делу: в тестовом режиме `show_error` бросает вместо показа, то есть ровно та ветка,
ради которой модуль написан, осталась бы непройденной. Поэтому каждый тест здесь
гасит тестовый режим и подменяет **только** `QMessageBox.exec` — модальный цикл под
offscreen ждёт ответа вечно и повесил бы прогон (`CLAUDE.md` §9). Всё остальное
настоящее: настоящий `sys.excepthook`, настоящее исключение из слота Qt, настоящее
окно `kit.error_box`.
"""

from __future__ import annotations

import sys
import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

import ui.kit as kit
from ui import crash

pytestmark = pytest.mark.usefixtures("qt_app")


@pytest.fixture
def live_mode(monkeypatch):
    """Боевой режим `show_error` + перехват показа окна.

    Гасится тестовый режим (`monkeypatch` вернёт его после теста — иначе
    следующий тест прогона остался бы без механизма QMS-021), ставится
    перехватчик, и подменяется единственное, что подменить обязаны, — `exec()`
    модального окна. Возвращается список показанных окон: проверять надо **что
    показали**, а не что позвали.
    """
    shown: list[QMessageBox] = []

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(kit.widgets, "_TEST_MODE", False)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self) or 0)

    crash.install()
    return shown


def _exploding_button(text: str = "boom") -> QPushButton:
    """Кнопка, чей слот падает. Показана — иначе клик не доставляется (§9а.5)."""
    button = QPushButton(text)

    def slot() -> None:
        raise TypeError("argument should be a str or an os.PathLike object, not 'NoneType'")

    button.clicked.connect(slot)
    button.show()
    QApplication.processEvents()
    return button


def _press(button: QPushButton) -> None:
    QTest.mouseClick(
        button,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button.rect().center(),
    )
    QApplication.processEvents()


def test_an_exception_from_a_slot_reaches_the_operator_as_a_window(live_mode) -> None:
    """**Критерий 3 доводки 3 — главный.** Исключение из слота даёт **окно**, а не
    тихое продолжение.

    Правило доводки (Д-3.3): «сейчас консоль есть, потому что приложение запускают
    из терминала; после упаковки в `.exe` консоли не будет вовсе, и любая такая
    ошибка станет полностью невидимой». Для базы качества это худший из возможных
    отказов — система молчит и продолжает работать, а оператор считает, что
    действие выполнено.

    Настоящим кликом по настоящей кнопке: PySide6 не пробрасывает исключение слота
    вызывающему (§9а.2), и проверять надо именно тот путь, которым оно уходит.
    """
    button = _exploding_button()

    _press(button)

    assert len(live_mode) == 1, "отказ остался невидимым — окна нет"


def test_the_window_carries_the_technical_truth(live_mode) -> None:
    """Текст окна — **тип, сообщение и место**, без выдумывания.

    Правило доводки: «оператор не обязан понимать traceback, но обязан знать, что
    произошёл сбой, и иметь что показать». Пустое «что-то пошло не так» этого не
    даёт: с ним чинящему нечего искать.

    Проверяется и вторая половина — что окно **не выдаёт сбой за отказ ввода**.
    Оператор, прочитавший «проверьте поле», пойдёт править данные, которые в
    порядке.
    """
    button = _exploding_button()

    _press(button)

    box = live_mode[0]
    text = f"{box.text()} {box.informativeText()} {box.detailedText()}"
    assert "TypeError" in text
    assert "not 'NoneType'" in text
    # Место: файл и строка того кадра, где рвануло.
    assert "test_ui_crash.py" in text
    assert "this is a defect" in text


def test_the_previous_hook_is_kept_so_the_terminal_still_gets_the_stack(
    live_mode, monkeypatch
) -> None:
    """Окно **добавляется** к печати, а не заменяет её.

    Разработчику нужен стек, оператору — знание, что произошёл сбой; отняв первое
    ради второго, мы вылечили бы отказ, оставив его недиагностируемым. Проверяется
    тем, что прежний хук всё ещё зовётся: он и печатает traceback.
    """
    printed: list = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: printed.append(args))
    crash.install()  # поверх подменённого — он и есть «прежний»

    button = _exploding_button()
    _press(button)

    assert len(printed) == 1
    assert len(live_mode) == 1


def test_a_deliberate_exit_is_not_reported_as_a_failure(live_mode) -> None:
    """`Ctrl+C` и штатный выход — не сбои.

    Окно на них было бы шумом, а на `KeyboardInterrupt` ещё и неотменяемым: оно
    появлялось бы ровно в тот момент, когда оператор просит приложение
    остановиться.
    """
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    sys.excepthook(SystemExit, SystemExit(0), None)

    assert live_mode == []


def test_a_failure_inside_the_error_window_does_not_loop(live_mode, monkeypatch) -> None:
    """Сбой **внутри** показа окна не зовёт хук по кругу.

    Рекурсия здесь кончалась бы исчерпанием стека, то есть тихой смертью процесса —
    ровно тем исходом, который модуль и предотвращает. Тот же класс, что
    самореференсный расчёт раскладки (`CLAUDE.md` §9а.15): величина, которую
    функция задаёт, не может входить в её же вход без поправки.
    """
    calls: list[int] = []

    def exploding_box(parent, error, title="Not saved"):
        calls.append(1)
        raise RuntimeError("the error window itself is broken")

    monkeypatch.setattr(crash.kit, "show_error", exploding_box)

    sys.excepthook(TypeError, TypeError("boom"), None)

    assert calls == [1], "повторный заход в хук — рекурсия не перекрыта"
