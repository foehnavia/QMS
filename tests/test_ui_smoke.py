"""Критерии приёмки 1 и 8 — окно и формы строятся без дисплея; домен без UI.

Прогон offscreen (`QT_QPA_PLATFORM=offscreen`, выставляется в `conftest`).
«Живой» иврит/RTL подтверждается ручным запуском (заметка Е).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from db.session import create_db_engine
from ui.cg_dialog import CgDialog, parse_optional_number
from ui.item_dialog import NO_GROUP, NO_TYPE, ItemDialog
from ui.item_view import ItemView
from ui.main_window import MainWindow
from ui.reference_view import ReferenceView

pytestmark = pytest.mark.usefixtures("qt_app")

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def seeded_engine(seeded_session):
    """Движок на мигрированной БД с засеянными справочниками."""
    seeded_session.commit()
    return seeded_session.get_bind()


def test_main_window_builds(seeded_engine, qt_app: QApplication) -> None:
    window = MainWindow(seeded_engine)
    window.show()
    qt_app.processEvents()

    assert window.sections.count() >= 3
    assert window.pages.count() == 3
    window.sections.setCurrentRow(1)
    assert window.pages.currentWidget() is window.cg_view
    window.sections.setCurrentRow(2)
    assert window.pages.currentWidget() is window.item_view
    window.close()


def test_application_is_right_to_left(qt_app: QApplication) -> None:
    """RTL из коробки — иврит основной язык данных."""
    assert qt_app.layoutDirection() == Qt.LayoutDirection.RightToLeft


def test_reference_view_lists_all_six_dictionaries(seeded_engine) -> None:
    view = ReferenceView(seeded_engine)
    assert view.picker.count() == 6

    names = []
    for index in range(view.picker.count()):
        view.picker.setCurrentIndex(index)
        names.append([view.values.item(row).text() for row in range(view.values.count())])

    flat = [label for group in names for label in group]
    assert any("General" in label and "дефолт" in label for label in flat)


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
    monkeypatch.setattr(item_dialog, "show_error", lambda parent, error, **kw: shown.append(error))

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
