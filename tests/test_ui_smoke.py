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
    assert dialog.group.currentText() == NO_GROUP
    assert dialog.positions.rowCount() == 0


def test_item_dialog_shows_group_positions_without_prefilled_numbers(seeded_engine) -> None:
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

    assert dialog.positions.rowCount() == 2
    # номер размера не подставляется — он с чертежа детали (решение Cowork, заметка Б)
    assert dialog.local_numbers() == {1: "", 2: ""}
    assert dialog.positions.item(0, 2).text() == "3.75"  # номинал показан, не скопирован
    assert dialog.positions.item(0, 0).text() == "g1"


def test_item_dialog_saves_item_and_seeds_the_group(seeded_engine) -> None:
    from domain.groups import GPositionSpec, create_group
    from domain.items import groups_of, list_items
    from db.session import session_scope

    with session_scope(seeded_engine) as session:
        create_group(session, "CG-A", (GPositionSpec(1, 3.75), GPositionSpec(2, 2.0)))

    dialog = ItemDialog(seeded_engine)
    dialog.number_edit.setText("C1-08375A")
    dialog.group.setCurrentText("CG-A")
    dialog.positions.item(0, 1).setText("12")
    dialog.positions.item(1, 1).setText("19")
    dialog.save()

    assert dialog.created_number == "C1-08375A"
    with session_scope(create_db_engine(str(seeded_engine.url))) as session:
        item = list_items(session)[0]
        assert sorted(c.local_number for c in item.characteristics) == ["12", "19"]
        assert [g.name for g in groups_of(item)] == ["CG-A"]


def test_item_dialog_refuses_to_save_without_local_numbers(seeded_engine, monkeypatch) -> None:
    """Незаполненный номер размера — отказ с сообщением, деталь не создаётся."""
    import ui.item_dialog as item_dialog
    from domain.groups import GPositionSpec, create_group
    from domain.items import list_items
    from db.session import session_scope

    with session_scope(seeded_engine) as session:
        create_group(session, "CG-A", (GPositionSpec(1, 3.75), GPositionSpec(2, 2.0)))

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = item_dialog.ItemDialog(seeded_engine)
    dialog.number_edit.setText("C1-08375A")
    dialog.group.setCurrentText("CG-A")
    dialog.positions.item(0, 1).setText("12")  # вторую позицию оставляем пустой
    dialog.save()

    assert dialog.created_number is None
    assert shown and "g2" in str(shown[0])
    with session_scope(seeded_engine) as session:
        assert list_items(session) == []


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

    Минус канона стоит в заголовке `Tolerance −`, в ячейке допуска `+0.05 / −0.05`
    и на переключателе направления. Оператор копирует значение из показанной
    ячейки в редактируемую; без нормализации он получал «`−0.05` is not a number»
    — сообщение про текст, который выглядит совершенно нормальным числом. Это
    ошибка, которая не подсказывает, а сбивает.
    """
    assert parse_optional_number(text, "tolerance") == -0.05


def test_bad_number_is_a_domain_error() -> None:
    from domain.errors import ValidationError

    with pytest.raises(ValidationError):
        parse_optional_number("три", "номинал")


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
