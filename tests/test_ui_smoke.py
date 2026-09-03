"""Критерии приёмки 1 и 8 — окно и формы строятся без дисплея; домен без UI.

Прогон offscreen (`QT_QPA_PLATFORM=offscreen`, выставляется в `conftest`).
«Живой» иврит/RTL подтверждается ручным запуском (заметка Е).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import ui.kit
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from db.session import create_db_engine
from ui.cg_dialog import CgDialog, parse_optional_number
from ui.item_dialog import NO_GROUP, NO_TYPE, ItemDialog
from ui.item_view import ItemView
from ui.main_window import MainWindow
from ui.common import strip_iso
from ui.reference_view import ReferenceView

pytestmark = pytest.mark.usefixtures("qt_app")

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def seeded_engine(seeded_session):
    """Движок на мигрированной БД с засеянными справочниками."""
    seeded_session.commit()
    return seeded_session.get_bind()


def test_main_window_builds(seeded_engine, qt_app: QApplication) -> None:
    """Шасси наряда 0011: лента сверху, разделы под ней, путь базы в подвале."""
    from ui.kit import tokens

    window = MainWindow(seeded_engine)
    window.show()
    qt_app.processEvents()

    assert window.ribbon.height() == tokens.RIBBON_HEIGHT
    assert window.pages.count() == 4
    window.select_section(1)
    assert window.pages.currentWidget() is window.cg_view
    window.select_section(2)
    assert window.pages.currentWidget() is window.item_view
    window.select_section(3)
    assert window.pages.currentWidget() is window.deviation_view
    # Подвал отвечает на «с какой базой я работаю» — критерий 5 наряда.
    assert str(seeded_engine.url) in window.database.text()
    window.close()


def test_application_shell_is_left_to_right(qt_app: QApplication) -> None:
    """Шасси окна — LTR (наряд 0007): направление данных живёт в ячейке."""
    assert qt_app.layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_reference_view_lists_all_six_dictionaries(seeded_engine) -> None:
    """Список списков — панелью (макет S2): видно, какие словари есть вообще."""
    from ui.reference_view import STATE_DEFAULT

    view = ReferenceView(seeded_engine)
    assert view.lists.count() == 6

    seen = []
    for index in range(view.lists.count()):
        view.lists.setCurrentRow(index)
        for row in range(view.values.rowCount()):
            seen.append(
                (
                    strip_iso(view.values.item(row, 0).text()),
                    view.values.item(row, 2).text(),
                )
            )

    # Структурный дефолт назван строкой таблицы, а не догадкой по кнопке.
    assert ("General", STATE_DEFAULT) in seen


def test_item_dialog_preselects_general(seeded_engine) -> None:
    dialog = ItemDialog(seeded_engine)

    assert dialog.connection_type.currentText() == "General"
    assert dialog.size.currentText() == "General"
    assert dialog.item_type.currentText() == NO_TYPE
    # Пустое поле группы — «группа не выбрана». Прежде это была строка списка,
    # теперь подсказка строки ввода: у поля с отбором пустое состояние своё
    # (наряд 0019 §3.1).
    assert dialog.group.currentData() is None
    assert dialog.group.lineEdit().placeholderText() == NO_GROUP


def test_the_item_form_does_not_ask_for_local_numbers(seeded_engine) -> None:
    """Критерий §3.1 наряда 0018: таблицы позиций в форме больше нет.

    Она спрашивала локальный номер на каждую g-позицию, не показывая чертежа:
    у оператора оставались индекс `gN`, который без чертежа ни на что не
    отображается, и номинал, который размер **не идентифицирует** — на чертеже
    он повторяется (находка №13). Ввод переехал в привязку, где чертёж есть.
    """
    from domain.groups import GPositionSpec, create_group
    from db.session import session_scope

    with session_scope(seeded_engine) as session:
        create_group(
            session,
            "CG-A",
            (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0, 0.0, -0.05)),
        )

    dialog = ItemDialog(seeded_engine)
    dialog.group.setCurrentText("CG-A")

    assert not hasattr(dialog, "positions")
    assert not hasattr(dialog, "local_numbers")


def test_the_item_form_saves_without_any_numbers_and_names_the_group(
    seeded_engine,
) -> None:
    """Критерий §3.5.2: с выбранной группой форма проходит дальше без номеров.

    Она же отдаёт наружу то, что нужно следующему шагу: какую деталь к какой
    группе привязывать.
    """
    from domain.groups import GPositionSpec, create_group
    from domain.items import list_items
    from db.session import session_scope

    with session_scope(seeded_engine) as session:
        group = create_group(session, "CG-A", (GPositionSpec(1, 3.75), GPositionSpec(2, 2.0)))
        cg_id = group.cg_id

    dialog = ItemDialog(seeded_engine)
    dialog.number_edit.setText("C1-08375A")
    dialog.group.setCurrentText("CG-A")
    dialog.save()

    assert dialog.created_number == "C1-08375A"
    assert dialog.created_group_id == cg_id
    with session_scope(create_db_engine(str(seeded_engine.url))) as session:
        item = list_items(session)[0]
        assert dialog.created_item_id == item.item_id
        # Размеров ещё нет: их заведёт привязка, а не форма.
        assert item.characteristics == []


def test_without_a_group_the_form_creates_the_item_alone(seeded_engine) -> None:
    """Критерий §3.5.6: привязывать нечего — деталь заводится как раньше."""
    from domain.items import list_items
    from db.session import session_scope

    dialog = ItemDialog(seeded_engine)
    dialog.number_edit.setText("NO-CG-ITEM")
    dialog.save()

    assert dialog.created_group_id is None
    with session_scope(create_db_engine(str(seeded_engine.url))) as session:
        assert [item.item_number for item in list_items(session)] == ["NO-CG-ITEM"]


def test_item_view_reloads(seeded_engine) -> None:
    view = ItemView(seeded_engine)
    assert view.table.rowCount() == 0

    from db.session import session_scope
    from domain.items import create_item
    from domain.reference import list_values
    from db.models import RefConnectionType, RefSize

    with session_scope(seeded_engine) as session:
        create_item(
            session,
            item_number="MT-SRH19A",
            connection_type=[v for v in list_values(session, RefConnectionType) if v.name == "General"][0],
            size=[v for v in list_values(session, RefSize) if v.name == "General"][0],
        )

    view.reload()
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "MT-SRH19A"


def test_cg_dialog_builds_and_saves(seeded_engine) -> None:
    from domain.groups import list_groups
    from db.session import session_scope

    dialog = CgDialog(seeded_engine)
    dialog.name_edit.setText("CG-новая")
    dialog.add_row()
    dialog.table.item(1, 1).setText("2,5")  # запятая как десятичный разделитель
    dialog.save()

    assert dialog.created_name == "CG-новая"
    with session_scope(seeded_engine) as session:
        group = list_groups(session)[0]
        assert [p.g_index for p in group.positions] == [1, 2]
        assert group.positions[1].nominal == 2.5


@pytest.mark.parametrize(
    "text, expected", [("", None), (" 3.75 ", 3.75), ("2,5", 2.5), ("-0,05", -0.05)]
)
def test_number_parsing(text: str, expected) -> None:
    assert parse_optional_number(text, "поле") == expected


@pytest.mark.parametrize("text", ["−0.05", "–0.05", "−0,05", " −0.05 "])
def test_the_parser_accepts_the_minus_the_screen_shows(text: str) -> None:
    """Ревью 0011, Р-1: приложение показывает `−` (U+2212) и обязано принять его.

    Минус канона стоит в ячейке предельных отклонений (`+0.05 / −0.05`) и на
    переключателе направления. Оператор копирует значение из показанной
    ячейки в редактируемую; без нормализации он получал «`−0.05` is not a number»
    — сообщение про текст, который выглядит совершенно нормальным числом. Это
    ошибка, которая не подсказывает, а сбивает.
    """
    assert parse_optional_number(text, "tolerance") == -0.05


def test_bad_number_is_a_domain_error() -> None:
    from domain.errors import ValidationError

    with pytest.raises(ValidationError):
        parse_optional_number("три", "номинал")


# --- §3.3 наряда 0017: дымовой тест уровня экрана ---------------------------------
#
# Тесты проверяли формы, но не то, **чем их открывают**. Дефект №12 («New item» не
# открывается: экран передавал себя в слот `item_id`) жил ровно в этом промежутке —
# все тесты формы конструировали её напрямую, а `add_item`, точку входа оператора,
# не звал никто.
#
# Поэтому кнопки здесь **нажимаются**, а список действий берётся с самого экрана:
# кнопка, добавленная завтра, попадёт под проверку без правки теста.


@pytest.fixture
def filled_engine(seeded_engine):
    """Засеянная база: справочники, деталь, группа и отклонение.

    Нужна именно наполненная: половина действий раздела работает над выбранной
    строкой, и на пустой выдаче эти пути не исполняются вовсе.
    """
    from datetime import date

    from conftest import make_item
    from db.session import session_scope
    from domain.deviations import register
    from domain.groups import GPositionSpec, create_group

    with session_scope(seeded_engine) as session:
        create_group(session, "CG-A", (GPositionSpec(1, 3.75, 0.05, -0.05),))
        item = make_item(session, "C1-08375A")
        register(session, item=item, wo="W26007336", quantity=3, date=date.today())
    return seeded_engine


@pytest.fixture
def deaf(monkeypatch):
    """Заглушить все модальные пути: под offscreen они вешают прогон.

    Модальное окно ждёт ответа вечно (`CLAUDE.md` §9), поэтому тест уровня экрана
    обязан перехватить **каждый** способ его показать — иначе первое же нажатие
    останавливает прогон вместо того, чтобы что-то проверить.
    """
    from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected.value)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        )
    # Ответ на подтверждение — «нет»: дымовой тест ничего не удаляет.
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))
    return shown


def _sections(engine) -> list:
    """Четыре раздела ленты — те же классы, что поднимает `MainWindow`."""
    from ui.cg_view import CgView
    from ui.deviation_view import DeviationView
    from ui.reference_view import ReferenceView

    return [ItemView(engine), CgView(engine), DeviationView(engine), ReferenceView(engine)]


@pytest.fixture
def slot_errors(monkeypatch):
    """Ловушка исключений, вылетевших **из слота**.

    Без неё этот тест зелёный на сломанной кнопке: PySide6 не пробрасывает
    исключение слота через `click()` наружу — оно уходит в `sys.excepthook`, а
    прогон идёт дальше. Проверено на сломанной сборке: с дефектом №12 на месте
    тест проходил, пока сюда не заглянули. Тот же класс, что «сверяй то, чем
    рисуют»: наблюдали не то, чем отказывает.
    """
    import sys

    caught: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, trace: caught.append(value))
    return caught


def _actions(view) -> list:
    """Кнопки панели действий — снимком **до** первого нажатия.

    Снимок обязателен: диалог открывается с `parent=view` и тем самым становится
    его ребёнком, а `findChildren` после первого нажатия вернула бы ещё и кнопки
    открытой формы. Нажимать «Create item» в пустой форме этот тест не нанимался
    — он проверяет вход в неё.

    Заодно отбрасываем всё, что живёт в другом окне: у кнопки диалога
    `window()` — сам диалог.
    """
    from PySide6.QtWidgets import QPushButton

    return [
        button
        for button in view.findChildren(QPushButton)
        if button.window() is view.window()
    ]


def _press(buttons) -> list[str]:
    """Нажать каждую доступную кнопку — как это делает оператор."""
    pressed = []
    for button in buttons:
        if not button.isEnabled():
            continue
        pressed.append(strip_iso(button.text()))
        button.click()
    return pressed


def _select_first_row(view) -> bool:
    """Выбрать первую строку выдачи, если она есть."""
    table = getattr(view, "table", None) or getattr(view, "values", None)
    if table is None or table.rowCount() == 0:
        return False
    table.setCurrentCell(0, 0)
    return True


@pytest.mark.parametrize("fixture", ["engine", "filled_engine"], ids=["empty-db", "seeded-db"])
def test_every_section_action_survives_being_pressed(
    qt_app, deaf, slot_errors, fixture, request
) -> None:
    """Критерий 3 наряда 0017: все действия панелей четырёх разделов зовутся живыми.

    Дважды: на пустой базе и на заполненной, и в заполненной — второй раз с
    выбранной строкой, потому что действие над записью до выбора и после ведёт
    себя по-разному (без выбора обязано вежливо сказать «сначала выберите»).
    """
    engine = request.getfixturevalue(fixture)

    for view in _sections(engine):
        actions = _actions(view)
        assert _press(actions), f"у раздела {type(view).__name__} не нашлось действий"
        if _select_first_row(view):
            _press(actions)

    # Доменных отказов на пустом ходу быть не должно: кнопка либо открывает
    # форму, либо вежливо просит выбрать строку.
    # Ни одного исключения из слота — иначе кнопка отказывает молча.
    assert slot_errors == [], [repr(error) for error in slot_errors]
    # И ни одного доменного отказа на пустом ходу.
    assert deaf == []


def test_a_dialog_refuses_a_positional_parent(seeded_engine) -> None:
    """Критерий 2: лишний позиционный аргумент — `TypeError`, а не подмена смысла.

    `parent` у конструкторов диалогов стоит **только по имени** (§3.2). Пока он
    был позиционным, параметр, вставленный перед ним, молча менял смысл уже
    написанного вызова: ревью 0012 добавило `item_id` вторым — и
    `ItemDialog(engine, self)` из экрана деталей стал значить «правь деталь с
    идентификатором-виджетом».
    """
    view = ItemView(seeded_engine)

    with pytest.raises(TypeError):
        ItemDialog(seeded_engine, None, view)  # родитель третьим позиционным

    # Тот же промах в форме прежней подписи — родитель вторым — теперь тоже
    # называется на месте, а не уходит трассой в глубину SQLAlchemy.
    with pytest.raises(TypeError):
        ItemDialog(seeded_engine, view)


# --- Критерий 8: домен не зависит от UI ------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """Имена модулей из import-инструкций файла (упоминания в тексте не в счёт)."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _pyside_importers(package: str) -> list[str]:
    return [
        path.relative_to(SRC).as_posix()
        for path in (SRC / package).rglob("*.py")
        if any(module.split(".")[0] == "PySide6" for module in _imported_modules(path))
    ]


def test_domain_does_not_import_pyside() -> None:
    """Ядро UI-независимо — UI единственный сменный слой (`architecture.md` §4)."""
    offenders = _pyside_importers("domain")
    assert offenders == [], f"PySide6 просочился в домен: {offenders}"


def test_db_layer_does_not_import_pyside() -> None:
    offenders = _pyside_importers("db")
    assert offenders == [], f"PySide6 просочился в слой хранения: {offenders}"


def test_the_layering_check_actually_detects_an_import(tmp_path: Path) -> None:
    """Страховка от «зелёного» теста, который ничего не проверяет."""
    probe = tmp_path / "probe.py"
    probe.write_text("from PySide6.QtWidgets import QWidget\n", encoding="utf-8")
    assert "PySide6.QtWidgets" in _imported_modules(probe)


# --- Критерий 3 наряда 0004: находки создаются только через make_finding ----------


def _finding_constructions(path: Path) -> list[int]:
    """Строки, где файл конструирует `Finding(...)` напрямую.

    Ловим и голое имя (`Finding(...)`), и обращение через модуль
    (`models.Finding(...)`) — оба обходят доменный гард принадлежности.
    """
    lines: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name == "Finding":
            lines.append(node.lineno)
    return lines


def _finding_constructors(package: str) -> list[str]:
    offenders: list[str] = []
    for path in (SRC / package).rglob("*.py"):
        for line in _finding_constructions(path):
            offenders.append(f"{path.relative_to(SRC).as_posix()}:{line}")
    return offenders


def test_ui_never_constructs_a_finding_directly() -> None:
    """Единственная точка создания находки — `domain.findings.make_finding`.

    Прямой `Finding(...)` в форме обошёл бы гард «находка ∈ деталь отклонения»,
    который схемой SQLite не выражается (перенос гейта из S2).
    """
    offenders = _finding_constructors("ui")
    assert offenders == [], f"Находка создаётся мимо make_finding: {offenders}"


def test_the_finding_guard_actually_detects_a_violation(tmp_path: Path) -> None:
    """Страховка от «зелёного» гарда, который ничего не проверяет."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from db.models import Finding\n"
        "def bad(deviation, characteristic):\n"
        "    return Finding(deviation=deviation, characteristic=characteristic)\n",
        encoding="utf-8",
    )
    assert _finding_constructions(probe) == [3]

    through_module = tmp_path / "probe_module.py"
    through_module.write_text(
        "from db import models\n"
        "def bad(deviation):\n"
        "    return models.Finding(deviation=deviation)\n",
        encoding="utf-8",
    )
    assert _finding_constructions(through_module) == [3]


def test_the_finding_guard_ignores_mere_mentions(tmp_path: Path) -> None:
    """Импорт и аннотация — не создание: гард не должен ловить их."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from db.models import Finding\n"
        "def show(finding: Finding) -> str:\n"
        "    return str(finding.finding_id)\n",
        encoding="utf-8",
    )
    assert _finding_constructions(probe) == []


# --- Критерий 1 наряда 0007: в `src/` нет кириллических строковых литералов -------


CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _docstring_constants(tree: ast.AST) -> set[int]:
    """`id()` узлов-докстрок: их гард пропускает намеренно."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        first = body[0] if body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _cyrillic_literals(path: Path) -> list[int]:
    """Строки, где файл несёт строковый литерал с кириллицей (кроме докстрок).

    Комментарии и docstring исключены **намеренно**: они внутренние, не
    интерфейс, и остаются русскими (наряд 0007, п. 7). Разбираем AST, а не
    текст: иначе гард ловил бы кириллицу в комментарии рядом с кодом.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_constants(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and CYRILLIC.search(node.value)
    ]


def test_src_carries_no_cyrillic_string_literals() -> None:
    """Язык интерфейса — English, и он не уедет обратно на первом же спринте.

    Первый раз русские подписи затекли из нарядов S2-S5 и прожили пять
    спринтов: ревью язык не проверяло. Проверяет гард.
    """
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        for line in _cyrillic_literals(path)
    ]
    assert offenders == [], f"кириллица в строковых литералах src/: {offenders}"


def test_the_cyrillic_guard_actually_detects_a_literal(tmp_path: Path) -> None:
    """Страховка от «зелёного» гарда: докстроку пропускаем, подпись — ловим."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""Русская докстрока — внутренний слой, гард её не трогает."""\n'
        "# русский комментарий тоже\n"
        'LABEL = "Сохранить"\n',
        encoding="utf-8",
    )
    assert _cyrillic_literals(probe) == [3]


def test_the_group_field_narrows_the_same_way(seeded_engine) -> None:
    """Критерий 5 наряда 0019: поле группы ведёт себя так же, как поле детали.

    Тот же класс отказа, тот же компонент: групп на производственном наборе
    десятки, и прокручивать их незачем.
    """
    from db.session import session_scope
    from domain.groups import GPositionSpec, create_group

    with session_scope(seeded_engine) as session:
        for name in ("Implant_Con_375_C1", "Implant_Con_420_SP", "Abutment_C1"):
            create_group(session, name, (GPositionSpec(1, 3.75),))

    from conftest import focus_field, type_keys

    dialog = ItemDialog(seeded_engine)
    dialog.show()
    focus_field(dialog.group)

    trace = type_keys(dialog.group, "con_")
    assert [typed for typed, _shown in trace][-1] == "con_"
    assert trace[-1][1] == ["Implant_Con_375_C1", "Implant_Con_420_SP"]

    type_keys(dialog.group, "нет такой")
    assert dialog.group.is_explaining() is True

    # Наружу форма отдаёт ключ группы, а не её имя.
    dialog.group.settle()
    dialog.group.setCurrentText("Abutment_C1")
    dialog.number_edit.setText("C1-08375A")
    dialog.save()

    with session_scope(seeded_engine) as session:
        from db.models import CharacteristicGroup

        expected = session.query(CharacteristicGroup).filter_by(name="Abutment_C1").one()
        assert dialog.created_group_id == expected.cg_id
