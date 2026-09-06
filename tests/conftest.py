"""Общие фикстуры: чистая БД под каждый тест.

Схема поднимается **той же baseline-миграцией Alembic**, что и в production —
так тесты проверяют миграцию, а не параллельный `create_all`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Qt должен узнать про offscreen до создания QApplication (заметка Е наряда 0002).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from db.models import GENERAL, Item, ItemRevision, RefConnectionType, RefSize
from db.session import create_db_engine, make_session_factory
from seed.reference import ref, seed_reference

REPO_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(db_url: str) -> Config:
    """Конфиг Alembic, нацеленный на конкретную БД."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """URL временной SQLite-БД; `QMS_DB_URL` подменён, чтобы env.py смотрел сюда."""
    url = f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}"
    monkeypatch.setenv("QMS_DB_URL", url)
    return url


@pytest.fixture
def migrated_url(db_url: str) -> str:
    """Пустая БД со схемой, накатанной `alembic upgrade head`."""
    command.upgrade(alembic_config(db_url), "head")
    return db_url


@pytest.fixture
def engine(migrated_url: str) -> Iterator[Engine]:
    engine = create_db_engine(migrated_url)
    yield engine
    engine.dispose()


@contextmanager
def reopen(db_url: str) -> Iterator[Session]:
    """Сессия на новом соединении — чтение идёт из файла, не из identity map."""
    engine = create_db_engine(db_url)
    try:
        with make_session_factory(engine)() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = make_session_factory(engine)
    with factory() as session:
        yield session


@pytest.fixture
def seeded_session(session: Session) -> Session:
    """Сессия на БД с засеянными справочниками."""
    seed_reference(session)
    session.commit()
    return session


@pytest.fixture(scope="session")
def qt_app():
    """Единственный `QApplication` на прогон — LTR-шасси, как в боевом запуске.

    Направление данных живёт на уровне ячейки и поля (`ui.common`), поэтому
    приложению остаётся только шасси (наряд 0007, §4).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    yield app
    app.processEvents()


def make_png(width: int = 16, height: int = 12, color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """Настоящий PNG без Qt — для проверок чертежа в домене и в UI."""
    import struct
    import zlib

    signature = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
    raw = b"".join(bytes([0]) + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_item(session: Session, item_number: str, *, revision: str = "A") -> Item:
    """Деталь на `General`-дефолтах вместе с первой ревизией чертежа.

    Ревизия заводится здесь, а не в каждом тесте, по той же причине, по которой
    её заводит `items.create_item`: размеры принадлежат ревизии, и деталь без
    неё — не место, куда их можно записать (QMS-017).

    Обозначение по умолчанию есть **только у фикстуры**. В домене молчаливого
    дефолта нет и быть не должно (ратификация 4): там обозначение приходит с
    чертежа. Здесь оно не означает ничего, кроме «тесту всё равно», а тест,
    которому не всё равно, передаёт своё.
    """
    item = Item(
        item_number=item_number,
        connection_type=ref(session, RefConnectionType, GENERAL),
        size=ref(session, RefSize, GENERAL),
    )
    session.add(item)
    session.flush()
    session.add(ItemRevision(item=item, designation=revision, seq=1, is_current=True))
    session.flush()
    return item


def rev(item: Item) -> ItemRevision:
    """Действующая ревизия детали — то, чем теперь адресуются размеры.

    Короткое имя намеренно: в тестах связей эта величина встречается в каждой
    второй строке, и `current_revision(item)` читался бы там громче, чем предмет
    проверки.
    """
    return next(revision for revision in item.revisions if revision.is_current)


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[str]]:
    """Считать SQL-запросы, ушедшие в базу внутри блока (наряд 0005, критерий 8).

    Возвращает список текстов запросов — по нему видно не только «сколько», но и
    «какие», что превращает провал теста на `N+1` в готовый диагноз. Слушатель
    снимается в `finally`: висящий подписчик исказил бы соседние тесты.
    """
    from sqlalchemy import event

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


# --- поток «заведение детали → привязка» (наряд 0018) ------------------------------
#
# Живут здесь, а не в одном из файлов тестов: этот поток проверяется с двух
# входов — экран деталей и форма отклонения, — и две копии подмены разъехались
# бы на первой же правке.


def fill_item_form_and_accept(number: str = "C1-08375A", group: str | None = "CG-A"):
    """Подмена `exec` формы детали: оператор заполнил поля и нажал «Create item».

    Форма сама сохраняет деталь и отдаёт наружу `created_item_id` /
    `created_group_id` — то, с чем дальше открывается привязка.
    """
    from PySide6.QtWidgets import QDialog

    def fake_exec(self):
        self.number_edit.setText(number)
        if group is not None:
            self.group.setCurrentText(group)
        self.save()
        return QDialog.DialogCode.Accepted.value

    return fake_exec


def stub_mapping_dialog(monkeypatch, action=None) -> list[tuple[int, int]]:
    """Подмена диалога привязки: записывает, с чем открыли, и делает `action`.

    `action(engine, item_id, cg_id, attempt)` — то, что оператор успел сделать в
    окне: диалог пишет по действию (ратификация S3), поэтому и заглушка пишет.
    Возвращаемое значение считается так же, как настоящий «Done»: по полноте.
    """
    import ui.item_dialog as module

    calls: list[tuple[int, int]] = []

    def fake_run(engine, item_id, cg_id, parent=None):
        calls.append((item_id, cg_id))
        if action is not None:
            action(engine, item_id, cg_id, len(calls))
        return not module.mapping_gap(engine, item_id, cg_id)

    monkeypatch.setattr(module.MappingDialog, "run", staticmethod(fake_run))
    return calls


# --- настоящие нажатия клавиш (доводка наряда 0019) --------------------------------
#
# Прошлая редакция поля с отбором была закрыта зелёными тестами и не работала у
# оператора с первого нажатия: тесты звали внутренние методы компонента, а не
# слали события клавиш. Разница принципиальная — путь `keyPressEvent` →
# `textEdited` → перерисовка проходил мимо проверки.


@pytest.fixture(autouse=True)
def _close_windows_after_each_test():
    """Закрыть всё показанное — окна не должны переживать свой тест.

    Понадобилось, когда проверки поля с отбором стали **показывать** виджеты:
    всплывающий список — отдельное окно с захватом ввода, и оставшееся от
    соседнего теста всплытие ломало доставку фокуса следующему. Поймано на
    падении, которое вне pytest не воспроизводилось.
    """
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        if widget.isVisible():
            widget.close()
    app.processEvents()


def press_key(text: str = "", key=None) -> None:
    """Одно нажатие — **через приложение**, а не прямой посылкой в виджет.

    Правило §8.3 наряда 0019, оплаченное дважды. Прямая посылка в строку ввода
    обходит диспетчеризацию Qt, а именно она перенаправляет нажатия в окно,
    захватившее ввод. Из-за этого тест проверял обработчик, а не поведение: у
    оператора со второго символа поле не отвечало вовсе, а тесты были зелёными.

    Адресата выбираем так же, как выбирает Qt: сперва активное всплытие (окно
    типа `Popup` держит захват), затем виджет с фокусом. Событие уходит
    `postEvent`-ом и разбирается циклом событий.
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    target = QApplication.activePopupWidget() or QApplication.focusWidget()
    assert target is not None, "некому доставить нажатие: нет ни всплытия, ни фокуса"

    code = key if key is not None else Qt.Key.Key_unknown
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.postEvent(
            target, QKeyEvent(kind, code, Qt.KeyboardModifier.NoModifier, text)
        )
    QApplication.processEvents()


def type_keys(field, text: str) -> list[tuple[str, list[str]]]:
    """Набрать строку по букве. Возвращает `(что в строке, что в списке)` на каждом шаге.

    Возвращается именно то, что видит оператор: содержимое строки ввода и
    подписи списка — а не внутренние величины компонента.
    """
    trace = []
    for letter in text:
        press_key(letter)
        trace.append((field.lineEdit().text(), field.visible_labels()))
    return trace


def backspace(field) -> tuple[str, list[str]]:
    """Стереть символ — тем же путём, что и оператор."""
    from PySide6.QtCore import Qt

    press_key("", Qt.Key.Key_Backspace)
    return field.lineEdit().text(), field.visible_labels()


def press_arrow(down: bool = True) -> None:
    """Стрелка по списку — через приложение."""
    from PySide6.QtCore import Qt

    press_key("", Qt.Key.Key_Down if down else Qt.Key.Key_Up)


def press_enter() -> None:
    from PySide6.QtCore import Qt

    press_key("", Qt.Key.Key_Return)


def press_escape() -> None:
    from PySide6.QtCore import Qt

    press_key("", Qt.Key.Key_Escape)


def click_away(field) -> None:
    """Щелчок мимо — всплытие закрывается захватом, как в жизни."""
    from PySide6.QtWidgets import QApplication

    popup = QApplication.activePopupWidget()
    if popup is not None:
        popup.close()
    QApplication.processEvents()


def leave_field(field, target=None) -> None:
    """Оператор ушёл из поля — настоящим событием потери фокуса.

    Под offscreen окно теста не становится активным, и `setFocus()` соседнего
    виджета фокусных событий не порождает вовсе (замерено: `hasFocus()` у строки
    всё время `False`). Поэтому шлём то самое событие, которое пришло бы от
    системы, — с причиной «ушёл», а не «открылось всплытие»: различать их
    компонент обязан, и здесь это и проверяется.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFocusEvent
    from PySide6.QtWidgets import QApplication

    if target is not None:
        target.setFocus()
    QApplication.sendEvent(
        field.lineEdit(),
        QFocusEvent(QFocusEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason),
    )
    QApplication.processEvents()


def clear_line(field) -> tuple[str, list[str]]:
    """Стереть строку целиком — выделить всё и нажать Backspace, как оператор."""
    from PySide6.QtCore import Qt

    field.lineEdit().selectAll()
    press_key("", Qt.Key.Key_Backspace)
    return field.lineEdit().text(), field.visible_labels()


def shown_field(field, width: int = 320):
    """Показать поле и дать ему фокус — как оно живёт у оператора.

    Показ нужен потому, что у скрытого виджета всплывающий список не
    открывается вовсе (первая доводка). Фокус — потому, что события теперь
    доставляются через приложение, а адресата приложение ищет по фокусу и по
    активному всплытию (§8.3).
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.addWidget(field)
    host.resize(width, width // 4)
    host.show()
    focus_field(field)
    return host


def focus_field(field) -> None:
    """Поставить фокус в строку поля и убедиться, что приложение его видит."""
    from PySide6.QtWidgets import QApplication

    window = field.window()
    window.raise_()
    window.activateWindow()
    field.lineEdit().setFocus()
    QApplication.processEvents()
    assert QApplication.focusWidget() is field.lineEdit(), (
        "приложение не видит фокуса в поле — доставлять нажатия будет некому"
    )
