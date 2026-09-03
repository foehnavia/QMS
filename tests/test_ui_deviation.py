"""UI S4: форма отклонения, находки, решение, исследование (критерии 1-6 наряда 0004).

Прогон offscreen. Диалоги строятся и сохраняются вызовом методов, а не кликами:
проверяем поведение формы, а не то, как Qt доставляет событие мыши.
"""

from __future__ import annotations

from datetime import date

import pytest

import ui.kit
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialogButtonBox

from conftest import make_item
from db.models import (
    CharacteristicGroup,
    Deviation,
    Direction,
    Finding,
    Inspection,
    Item,
    RefInspectionType,
    RefZone,
)
from db.session import session_scope
from domain.deviations import register
from domain.findings import make_finding
from domain.groups import GPositionSpec, create_group
from domain.inspections import create_inspection
from domain.mappings import bind
from domain.reference import list_values
from ui.decision_dialog import NOT_DECIDED, DecisionDialog
from ui.deviation_dialog import FINDING_COLUMNS, DeviationDialog
from ui.deviation_view import DeviationView
from ui.finding_dialog import CANON_NEW, CANON_UNBOUND, FindingDialog, FindingRow
from ui.inspection_dialog import InspectionDialog

pytestmark = pytest.mark.usefixtures("qt_app")

POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0))
TODAY = date.today()


@pytest.fixture
def engine_with_item(seeded_session):
    """Движок с деталью и группой из двух позиций."""
    seeded_session.commit()
    engine = seeded_session.get_bind()
    with session_scope(engine) as session:
        create_group(session, "CG-A", POSITIONS)
        make_item(session, "C1-08375A")
    return engine


def _item_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(Item).one().item_id


def _row(local_number: str = "12", direction: str = Direction.PLUS, **kwargs) -> FindingRow:
    return FindingRow(local_number=local_number, direction=direction, **kwargs)


def _fill_header(dialog: DeviationDialog, wo: str = "W26007336", quantity: int = 5) -> None:
    dialog.item.setCurrentText("C1-08375A")
    dialog.wo.setText(wo)
    dialog.quantity.setValue(quantity)
    dialog.date.setDate(QDate(TODAY.year, TODAY.month, TODAY.day))


# --- Критерий 1: регистрация -----------------------------------------------------


def test_form_blocks_saving_until_an_item_and_a_finding_exist(engine_with_item) -> None:
    """Решение 3: отклонение без находок не сохраняется, причина видна текстом."""
    dialog = DeviationDialog(engine_with_item)
    save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)

    assert save.isEnabled() is False
    assert "item" in dialog.status.text().lower()

    _fill_header(dialog)
    dialog._refresh()
    assert save.isEnabled() is False
    assert "finding" in dialog.status.text()

    dialog._rows.append(_row())
    dialog._refresh()
    assert save.isEnabled() is True


def test_form_registers_a_deviation_with_findings_in_one_go(engine_with_item) -> None:
    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog, quantity=7)
    dialog.machine.setText("CNC-7")
    dialog.ncr.setText("NCR-118")
    dialog.attachment.setPlainText(r"\\srv\qa\photo.jpg")
    dialog._rows.append(_row("12", Direction.PLUS, value=0.08))
    dialog._rows.append(_row("19", Direction.MINUS, value=0.05, dimension_point=3))
    dialog._refresh()

    dialog.save()

    with session_scope(engine_with_item) as session:
        deviation = session.query(Deviation).one()
        assert deviation.dev_number.startswith("DEV-")
        assert (deviation.wo, deviation.quantity, deviation.machine) == ("W26007336", 7, "CNC-7")
        # Регистрация — без решения: исход вносится отдельным действием.
        assert deviation.decision_dev is None
        assert sorted(f.characteristic.local_number for f in deviation.findings) == ["12", "19"]


def test_form_reports_a_domain_error_instead_of_an_integrity_error(
    engine_with_item, monkeypatch
) -> None:
    """Критерий 1: обязательные поля отбиваются доменным сообщением."""
    import ui.deviation_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog, wo="   ")
    dialog._rows.append(_row())
    dialog._refresh()

    dialog.save()

    assert shown and "Work order" in str(shown[0])
    with session_scope(engine_with_item) as session:
        assert session.query(Deviation).count() == 0


def test_the_date_field_cannot_reach_into_the_future(engine_with_item) -> None:
    dialog = DeviationDialog(engine_with_item)
    assert dialog.date.maximumDate() <= QDate.currentDate()


# --- Критерий 2: находки ---------------------------------------------------------


def test_a_dimension_the_item_lacks_is_created_on_save(engine_with_item) -> None:
    """Массовый случай `_overview.md` §6: размера нет — создаётся без формы."""
    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("77"))
    dialog._refresh()

    dialog.save()

    with session_scope(engine_with_item) as session:
        item = session.query(Item).one()
        assert [c.local_number for c in item.characteristics] == ["77"]


def test_the_ui_path_keeps_the_finding_on_the_deviation_item(engine_with_item) -> None:
    """Инвариант «находка ∈ деталь отклонения» — через путь формы, не только домена."""
    with session_scope(engine_with_item) as session:
        make_item(session, "IT-FOREIGN")
        foreign = session.query(Item).filter_by(item_number="IT-FOREIGN").one()
        from domain.characteristics import get_or_create_characteristic

        get_or_create_characteristic(session, foreign, "12")

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()
    dialog.save()

    with session_scope(engine_with_item) as session:
        finding = session.query(Finding).one()
        # Размер №12 есть у обеих деталей — находка обязана взять свой.
        assert finding.characteristic.item.item_number == "C1-08375A"
        assert finding.characteristic.item_id == finding.deviation.item_id


def test_findings_are_edited_and_removed_through_the_form(engine_with_item) -> None:
    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12", Direction.PLUS, value=0.08))
    dialog._rows.append(_row("19", Direction.MINUS))
    dialog._refresh()
    dialog.save()

    reopened = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))
    assert reopened.findings.rowCount() == 2

    reopened._rows[0].value = 0.15
    reopened.findings.setCurrentCell(1, 0)
    reopened.on_drop_finding()
    reopened.save()

    with session_scope(engine_with_item) as session:
        deviation = session.query(Deviation).one()
        assert [f.characteristic.local_number for f in deviation.findings] == ["12"]
        assert deviation.findings[0].value == 0.15


def test_the_form_refuses_to_remove_the_last_finding(engine_with_item, monkeypatch) -> None:
    """Инвариант `1..N` виден сразу при нажатии, а не при сохранении."""
    import ui.deviation_dialog as module

    warned: list[str] = []
    monkeypatch.setattr(
        module.QMessageBox, "warning", lambda *args, **kw: warned.append(args[2])
    )

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()
    dialog.findings.setCurrentCell(0, 0)

    dialog.on_drop_finding()

    assert dialog._rows and "at least one finding" in warned[0]


def test_the_form_refuses_a_duplicate_dimension(engine_with_item, monkeypatch) -> None:
    """Две находки по одному размеру внутри отклонения — это одна находка."""
    import ui.deviation_dialog as module

    warned: list[str] = []
    monkeypatch.setattr(
        module.QMessageBox, "warning", lambda *args, **kw: warned.append(args[2])
    )
    monkeypatch.setattr(
        module.FindingDialog,
        "exec",
        lambda self: setattr(self, "row", _row("12")) or module.QDialog.DialogCode.Accepted,
    )

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()

    dialog.on_add_finding()

    assert len(dialog._rows) == 1
    assert warned and "12" in warned[0]


# --- Критерий 4: ранняя привязка к канону (R2) ------------------------------------


def test_canon_column_follows_the_mapping_without_reopening_the_form(
    engine_with_item, monkeypatch
) -> None:
    """После привязки колонка «канон» показывает g-позицию тут же."""
    import ui.deviation_dialog as module

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()

    assert dialog.findings.item(0, 1).text().strip("\u2068\u2069") == CANON_NEW

    # Привязку делает тот же MappingDialog — подменяем только его открытие.
    def fake_run(engine, item_id, cg_id, parent=None):
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            group = session.query(CharacteristicGroup).one()
            bind(session, item, group.positions[0], "12")
        return True

    monkeypatch.setattr(module.MappingDialog, "run", staticmethod(fake_run))
    monkeypatch.setattr(module, "choose_cg_for_item", lambda *args: _cg_id(engine_with_item))

    dialog.on_map_canon()

    assert dialog.findings.item(0, 1).text().strip("\u2068\u2069") == "g1"


def test_canon_state_reads_the_s3_layer(engine_with_item) -> None:
    from ui.finding_dialog import canon_state

    item_id = _item_id(engine_with_item)
    assert canon_state(engine_with_item, item_id, "12") == CANON_NEW
    assert canon_state(engine_with_item, None, "12") == CANON_NEW

    with session_scope(engine_with_item) as session:
        from domain.characteristics import get_or_create_characteristic

        get_or_create_characteristic(session, session.get(Item, item_id), "12")
    assert canon_state(engine_with_item, item_id, "12") == CANON_UNBOUND

    with session_scope(engine_with_item) as session:
        group = session.query(CharacteristicGroup).one()
        bind(session, session.get(Item, item_id), group.positions[1], "12")
    assert canon_state(engine_with_item, item_id, "12") == "g2"


def test_early_binding_button_needs_an_item(engine_with_item) -> None:
    dialog = DeviationDialog(engine_with_item)
    assert dialog.map_canon.isEnabled() is False

    _fill_header(dialog)
    dialog._refresh()
    assert dialog.map_canon.isEnabled() is True


# --- Диалог находки --------------------------------------------------------------


def test_finding_dialog_demands_a_direction(engine_with_item, monkeypatch) -> None:
    """Заметка Б: направление обязательно, умолчания у переключателя нет."""
    import ui.finding_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = FindingDialog(engine_with_item, _item_id(engine_with_item))
    dialog.number_edit.setText("12")
    assert not (dialog.plus.isChecked() or dialog.minus.isChecked())

    dialog.save()

    assert dialog.row is None
    assert shown and "Direction" in str(shown[0])


def test_finding_dialog_collects_every_field(engine_with_item) -> None:
    with session_scope(engine_with_item) as session:
        zone_name = list_values(session, RefZone)[0].name if list_values(session, RefZone) else None

    dialog = FindingDialog(engine_with_item, _item_id(engine_with_item))
    dialog.number_edit.setText("12")
    dialog.minus.setChecked(True)
    dialog.value_edit.setText("0,08")  # запятая как разделитель
    dialog.point_edit.setText("3")
    dialog.comment_edit.setPlainText("GO не проходит")
    if zone_name:
        dialog.zone.setCurrentText(zone_name)

    dialog.save()

    row = dialog.row
    assert (row.local_number, row.direction, row.value) == ("12", Direction.MINUS, 0.08)
    assert (row.dimension_point, row.comment) == (3, "GO не проходит")


def test_finding_dialog_locks_the_dimension_of_a_saved_finding(engine_with_item) -> None:
    """Другой размер — другая находка; домен номер тоже не меняет."""
    saved = _row("12", finding_id=42)
    dialog = FindingDialog(engine_with_item, _item_id(engine_with_item), saved)

    assert dialog.number_edit.isReadOnly() is True


def test_finding_dialog_keeps_the_identity_of_an_edited_row(engine_with_item) -> None:
    """Правка возвращает ту же находку — иначе форма удалила бы её и создала заново."""
    saved = _row("12", finding_id=42, inspections=2)
    dialog = FindingDialog(engine_with_item, _item_id(engine_with_item), saved)
    dialog.value_edit.setText("0,2")

    dialog.save()

    assert dialog.row.finding_id == 42
    assert dialog.row.inspections == 2


def test_finding_dialog_rejects_a_non_numeric_point(engine_with_item, monkeypatch) -> None:
    import ui.finding_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = FindingDialog(engine_with_item, _item_id(engine_with_item))
    dialog.number_edit.setText("12")
    dialog.plus.setChecked(True)
    dialog.point_edit.setText("три")

    dialog.save()

    assert dialog.row is None and shown


# --- Критерий 5: решение ---------------------------------------------------------


def test_decision_dialog_starts_undecided_and_writes_the_outcome(engine_with_item) -> None:
    deviation_id = _register(engine_with_item)

    dialog = DecisionDialog(engine_with_item, deviation_id)
    # Ничего не предвыбрано: исход — решение инженера, а не умолчание формы
    # (канон §4, ревью 0012 В-9).
    assert dialog.decision.value() is None

    dialog.decision.set_value("sorting")
    dialog.explanation.setPlainText("100 % контроль по диаметру")
    dialog.save()

    with session_scope(engine_with_item) as session:
        deviation = session.get(Deviation, deviation_id)
        assert deviation.decision_dev == "sorting"
        assert deviation.explanation.startswith("100 %")


def test_decision_dialog_refuses_approval_without_an_explanation(
    engine_with_item, monkeypatch
) -> None:
    import ui.decision_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))
    deviation_id = _register(engine_with_item)

    dialog = DecisionDialog(engine_with_item, deviation_id)
    dialog.decision.set_value("approved")
    dialog.explanation.setPlainText("   ")

    dialog.save()

    assert shown and "חריגה" in str(shown[0])
    with session_scope(engine_with_item) as session:
        assert session.get(Deviation, deviation_id).decision_dev is None


def test_decision_dialog_refuses_an_unset_outcome(engine_with_item, monkeypatch) -> None:
    import ui.decision_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = DecisionDialog(engine_with_item, _register(engine_with_item))
    dialog.save()

    assert shown and "outcome" in str(shown[0]).lower()


def test_decision_dialog_lists_all_four_outcomes(engine_with_item) -> None:
    """Четыре исхода стоят на экране разом — их выбирают, читая (канон §4).

    Пятого варианта «решения нет» среди них нет: отсутствие решения это не
    исход, а незаполненная форма.
    """
    from db.models import DECISION_DEV
    from ui.common import DECISION_DEV_LABELS, strip_iso

    dialog = DecisionDialog(engine_with_item, _register(engine_with_item))

    labels = [strip_iso(button.text()) for button in dialog.decision.buttons()]
    assert labels == [DECISION_DEV_LABELS[code] for code in DECISION_DEV]
    assert dialog.decision.value() is None


def test_decision_dialog_keeps_the_ncr_from_registration(engine_with_item) -> None:
    deviation_id = _register(engine_with_item, ncr="NCR-118")

    dialog = DecisionDialog(engine_with_item, deviation_id)
    assert dialog.ncr.text() == "NCR-118"

    dialog.decision.set_value("rejected")
    dialog.save()

    with session_scope(engine_with_item) as session:
        assert session.get(Deviation, deviation_id).ncr == "NCR-118"


# --- Критерий 6: исследование ----------------------------------------------------


def test_inspection_button_needs_a_saved_finding(engine_with_item) -> None:
    """Исследование ссылается на строку находки — на несохранённой его нечем завести."""
    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()
    dialog.findings.setCurrentCell(0, 0)

    assert dialog.inspect.isEnabled() is False
    assert "save the deviation first" in dialog.status.text()

    dialog.save()
    reopened = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))
    reopened.findings.setCurrentCell(0, 0)
    assert reopened.inspect.isEnabled() is True


def test_inspection_dialog_writes_and_shows_the_finding(engine_with_item) -> None:
    finding_id = _finding_id(engine_with_item)

    dialog = InspectionDialog(engine_with_item, finding_id)
    assert "12" in dialog.finding_label.text()

    dialog.protocol.setText(r"\\srv\qa\SW-2026-14.docx")
    dialog.verdict.set_value("not_approved")
    dialog.save()

    with session_scope(engine_with_item) as session:
        inspection = session.query(Inspection).one()
        assert inspection.insp_number.startswith("INSP-")
        assert inspection.decision_insp == "not_approved"
        assert inspection.finding_id == finding_id


def test_inspection_dialog_refuses_an_empty_protocol(engine_with_item, monkeypatch) -> None:
    import ui.inspection_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = InspectionDialog(engine_with_item, _finding_id(engine_with_item))
    # Вывод выбираем: без него форма отбивается раньше, на самом выводе.
    dialog.verdict.set_value("approved")
    dialog.protocol.setText("   ")
    dialog.save()

    assert shown and "Protocol" in str(shown[0])
    with session_scope(engine_with_item) as session:
        assert session.query(Inspection).count() == 0


def test_deviation_form_lists_inspections_and_counts_them(engine_with_item) -> None:
    finding_id = _finding_id(engine_with_item)
    with session_scope(engine_with_item) as session:
        create_inspection(
            session,
            session.get(Finding, finding_id),
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approved",
            protocol="p.docx",
        )

    dialog = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))

    assert dialog.inspections.rowCount() == 1
    # Колонка «Inspections» — последняя; после слияния знака и величины это 6.
    assert dialog.findings.item(0, len(FINDING_COLUMNS) - 1).text() == "1"


def test_the_form_refuses_to_remove_a_studied_finding(engine_with_item, monkeypatch) -> None:
    """Критерий 8 через UI: блокировка видна сразу при нажатии."""
    import ui.deviation_dialog as module

    warned: list[str] = []
    monkeypatch.setattr(
        module.QMessageBox, "warning", lambda *args, **kw: warned.append(args[2])
    )

    finding_id = _finding_id(engine_with_item, extra="19")
    with session_scope(engine_with_item) as session:
        create_inspection(
            session,
            session.get(Finding, finding_id),
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approved",
            protocol="p.docx",
        )

    dialog = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))
    studied = next(i for i, row in enumerate(dialog._rows) if row.finding_id == finding_id)
    dialog.findings.setCurrentCell(studied, 0)

    dialog.on_drop_finding()

    assert warned and "inspections: 1" in warned[0]
    assert len(dialog._rows) == 2


# --- Раздел «Отклонения» ---------------------------------------------------------


def test_view_lists_deviations_with_counts_and_decision(engine_with_item) -> None:
    _finding_id(engine_with_item)

    from ui.deviation_view import COLUMNS

    view = DeviationView(engine_with_item)

    assert view.table.rowCount() == 1
    # Колонки адресуем по имени: наряд 0011 переставил `Findings` перед
    # `Decision` и добавил `Explanation`, и номер здесь ничего не проверяет.
    # Короткая метка колонки списка (макет S13, дизайн-система rev. 1.4).
    assert view.table.item(0, COLUMNS.index("Decision")).text() == "Not decided"
    assert view.table.item(0, COLUMNS.index("Findings")).text() == "1"
    # Счётчик выдачи — в подзаголовке экрана (макет S9); подвал показывает
    # выбранную запись, а не то же число второй раз (наряд 0012).
    assert "1 undecided" in view.summary_text()


def test_view_deletes_a_deviation_with_its_children(engine_with_item, monkeypatch) -> None:
    import ui.deviation_view as module

    finding_id = _finding_id(engine_with_item)
    with session_scope(engine_with_item) as session:
        create_inspection(
            session,
            session.get(Finding, finding_id),
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approved",
            protocol="p.docx",
        )

    asked: list[str] = []

    def confirm(*args, **kwargs):
        asked.append(args[2])
        return module.QMessageBox.StandardButton.Yes

    monkeypatch.setattr(module.QMessageBox, "question", confirm)

    view = DeviationView(engine_with_item)
    view.table.setCurrentCell(0, 0)
    view.delete_deviation()

    # Цену удаления показываем до, а не после.
    assert "findings: 1" in asked[0] and "inspections: 1" in asked[0]
    assert view.table.rowCount() == 0
    with session_scope(engine_with_item) as session:
        assert session.query(Finding).count() == 0
        assert session.query(Inspection).count() == 0


# --- вспомогательное -------------------------------------------------------------


def _cg_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(CharacteristicGroup).one().cg_id


def _register(engine, **overrides) -> int:
    with session_scope(engine) as session:
        item = session.query(Item).filter_by(item_number="C1-08375A").one()
        kwargs = dict(wo="W26007336", quantity=5, date=TODAY)
        kwargs.update(overrides)
        return register(session, item=item, **kwargs).deviation_id


def _deviation_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(Deviation).order_by(Deviation.deviation_id).first().deviation_id


def _finding_id(engine, local_number: str = "12", extra: str | None = None) -> int:
    """Отклонение с находкой (и, если нужно, второй) — возвращает id первой."""
    from domain.characteristics import get_or_create_characteristic

    with session_scope(engine) as session:
        item = session.query(Item).filter_by(item_number="C1-08375A").one()
        deviation = register(session, item=item, wo="W26007336", quantity=5, date=TODAY)
        characteristic, _ = get_or_create_characteristic(session, item, local_number)
        finding = make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        if extra:
            second, _ = get_or_create_characteristic(session, item, extra)
            make_finding(session, deviation, second, direction=Direction.MINUS)
        return finding.finding_id


# --- Bidi: числовые редакторы (найдено рендером, критерий 12) ---------------------


def test_date_and_quantity_editors_are_left_to_right(engine_with_item) -> None:
    """Внутри QDateEdit текст рисует Qt — изолятом его не обернуть.

    Рядом с ивритской строкой `19.08.2026` показывалось как `2026.08.19`:
    числовые группы, разделённые точками, переставляются алгоритмом bidi, и
    оператор читает другую дату. Разворачиваем сами виджеты
    (`ui.common.numeric_field`).
    """
    from PySide6.QtCore import Qt

    dialog = DeviationDialog(engine_with_item)
    assert dialog.date.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert dialog.quantity.layoutDirection() == Qt.LayoutDirection.LeftToRight

    decision = DecisionDialog(engine_with_item, _register(engine_with_item))
    assert decision.decision_date.layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_the_list_isolates_dates_and_business_numbers(engine_with_item) -> None:
    """В таблицах текст формируем сами — там достаточно изолята."""
    _finding_id(engine_with_item)
    view = DeviationView(engine_with_item)

    for column in (0, 1, 2, 3, 4):
        assert view.table.item(0, column).text().startswith("⁨")


# --- Ревью S4: замена всех находок за одну правку --------------------------------


def test_all_findings_can_be_replaced_in_one_edit(engine_with_item, monkeypatch) -> None:
    """Штатный путь исправления опечатки в номере размера.

    Номер размера у сохранённой находки не правится (другой размер — другая
    находка), поэтому «добавить правильную, убрать неправильную» — единственный
    способ. Раньше сохранение падало: удаление шло до записи, и на последней
    удаляемой срабатывал гард «должна остаться хотя бы одна», хотя замена в
    форме была.

    `show_error` перехватываем не ради удобства: при провале сохранения форма
    показывает **модальный** QMessageBox, и под offscreen он ждёт ответа
    вечно — регрессия вешала бы прогон вместо того, чтобы уронить тест.
    """
    import ui.deviation_dialog as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12", Direction.PLUS, value=0.08))
    dialog._refresh()
    dialog.save()

    deviation_id = _deviation_id(engine_with_item)
    reopened = DeviationDialog(engine_with_item, deviation_id)
    reopened._rows.append(_row("15", Direction.MINUS, value=0.04))
    reopened._refresh()
    wrong = next(i for i, row in enumerate(reopened._rows) if row.local_number == "12")
    reopened.findings.setCurrentCell(wrong, 0)
    reopened.on_drop_finding()

    reopened.save()

    assert shown == [], f"сохранение отбито: {shown and shown[0]}"
    with session_scope(engine_with_item) as session:
        deviation = session.get(Deviation, deviation_id)
        assert [f.characteristic.local_number for f in deviation.findings] == ["15"]
        assert deviation.findings[0].value == 0.04
        # Размер существует независимо от канона и от находок — опечаточный
        # №12 остаётся у детали, его чистит администратор, а не форма.
        item = session.query(Item).filter_by(item_number="C1-08375A").one()
        assert sorted(c.local_number for c in item.characteristics) == ["12", "15"]


def test_replacing_findings_keeps_the_inspection_guard(engine_with_item, monkeypatch) -> None:
    """Перестановка порядка не отменила гард по исследованиям."""
    import ui.deviation_dialog as module

    warned: list[str] = []
    monkeypatch.setattr(
        module.QMessageBox, "warning", lambda *args, **kw: warned.append(args[2])
    )

    finding_id = _finding_id(engine_with_item, extra="19")
    with session_scope(engine_with_item) as session:
        create_inspection(
            session,
            session.get(Finding, finding_id),
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approved",
            protocol="p.docx",
        )

    dialog = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))
    studied = next(i for i, row in enumerate(dialog._rows) if row.finding_id == finding_id)
    dialog.findings.setCurrentCell(studied, 0)
    dialog.on_drop_finding()

    assert warned and "inspections: 1" in warned[0]
    assert len(dialog._rows) == 2


def test_saving_stays_blocked_when_the_last_finding_is_removed(engine_with_item) -> None:
    """Регресс на гард `1..N`: пустой список по-прежнему не сохраняется.

    Форма не даёт убрать последнюю строку, а если бы дала — «Сохранить» остаётся
    недоступной. Перестановка «сначала запись, потом удаление» эту защиту не
    отменяет: удалять станет нечего только тогда, когда что-то записано.
    """
    dialog = DeviationDialog(engine_with_item)
    _fill_header(dialog)
    dialog._rows.append(_row("12"))
    dialog._refresh()
    dialog.save()

    reopened = DeviationDialog(engine_with_item, _deviation_id(engine_with_item))
    save = reopened.buttons.button(QDialogButtonBox.StandardButton.Save)
    assert save.isEnabled() is True

    reopened._rows.clear()
    reopened._refresh()

    assert save.isEnabled() is False
    assert "finding" in reopened.status.text()
    with session_scope(engine_with_item) as session:
        assert session.query(Finding).count() == 1


# --- наряд 0017: «Create item…» из формы отклонения ----------------------------------


def test_create_item_from_the_deviation_form_opens_a_create_form(
    engine_with_item, monkeypatch
) -> None:
    """Тот же промах жил и здесь: `ItemDialog(engine, self)` — родитель в слот `item_id`.

    Второй вход в форму детали (R3: деталь заводится по ходу регистрации) звал её
    ровно так же, как экран деталей, и падал бы ровно так же — просто до него на
    прогоне не дошли. Правка одна, поэтому и проверок две.
    """
    import ui.deviation_dialog as module

    opened: list = []
    monkeypatch.setattr(module.ItemDialog, "exec", lambda self: opened.append(self) or 0)

    dialog = DeviationDialog(engine_with_item)
    dialog.create_item()

    assert opened, "форма детали не открылась"
    assert opened[0]._item_id is None
    assert opened[0].windowTitle() == "New item"
    assert opened[0].parent() is dialog


def test_create_item_from_the_deviation_form_maps_it_too(
    engine_with_item, monkeypatch
) -> None:
    """Критерий §3.5.5: второй вход ведёт себя так же — привязка обязательна.

    Здесь она особенно к месту: R2 требует привязать канон **до** регистрации
    отклонения, а мы как раз внутри неё. Заведённая деталь подставляется в
    список — но только если привязка доведена.
    """
    from conftest import fill_item_form_and_accept, stub_mapping_dialog
    from db.models import CharacteristicGroup, Item
    from domain.mappings import bind, mark_absent

    def operator_maps(engine, item_id, cg_id, attempt):
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            positions = sorted(
                session.get(CharacteristicGroup, cg_id).positions, key=lambda p: p.g_index
            )
            bind(session, item, positions[0], "31")
            mark_absent(session, item, positions[1])

    import ui.deviation_dialog as module

    monkeypatch.setattr(
        module.ItemDialog, "exec", fill_item_form_and_accept("C1-08420B", "CG-A")
    )
    calls = stub_mapping_dialog(monkeypatch, operator_maps)

    dialog = DeviationDialog(engine_with_item)
    dialog.create_item()

    assert len(calls) == 1
    with session_scope(engine_with_item) as session:
        created = session.query(Item).filter_by(item_number="C1-08420B").one()
        assert [c.local_number for c in created.characteristics] == ["31"]
    # Заведённая деталь выбрана в форме: регистрировать отклонение можно сразу.
    assert dialog.item.currentText() == "C1-08420B"


def test_refusing_the_mapping_from_the_deviation_form_creates_nothing(
    engine_with_item, monkeypatch
) -> None:
    """Тот же отказ и здесь: детали нет, и подставлять в список нечего."""
    from PySide6.QtWidgets import QMessageBox

    from conftest import fill_item_form_and_accept, stub_mapping_dialog
    from db.models import Item

    import ui.deviation_dialog as module
    import ui.item_dialog as dialog_module

    monkeypatch.setattr(
        module.ItemDialog, "exec", fill_item_form_and_accept("C1-08420B", "CG-A")
    )
    stub_mapping_dialog(monkeypatch)  # оператор ничего не решил и закрыл окно
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )

    dialog = DeviationDialog(engine_with_item)
    dialog.create_item()

    with session_scope(engine_with_item) as session:
        assert session.query(Item).filter_by(item_number="C1-08420B").count() == 0
    assert dialog.item.currentText() != "C1-08420B"


# --- наряд 0019: выбор детали отбором ------------------------------------------------


def _two_items(engine) -> tuple[int, int]:
    """Вторая деталь с похожим номером: отбор обязан их различать."""
    from conftest import make_item

    with session_scope(engine) as session:
        first = session.query(Item).one().item_id
        second = make_item(session, "MF5-10375A-N").item_id
    return first, second


def test_the_item_field_narrows_as_you_type(engine_with_item) -> None:
    """Критерий 1: набор сужает список по вхождению, стирание расширяет.

    Прежде это был обычный `QComboBox`: первая буква переставляла отметку, но
    список оставался полным (находка №17, прогон встал на шаге 8).
    """
    _two_items(engine_with_item)
    dialog = DeviationDialog(engine_with_item)
    dialog.reload_items()

    assert dialog.item.visible_labels() == ["C1-08375A", "MF5-10375A-N"]

    dialog.item.filter_to("10375")
    assert dialog.item.visible_labels() == ["MF5-10375A-N"]

    dialog.item.filter_to("")
    assert dialog.item.visible_labels() == ["C1-08375A", "MF5-10375A-N"]

    dialog.item.filter_to("нет такой")
    assert dialog.item.visible_labels() != []
    assert dialog.item.is_explaining() is True


def test_the_item_field_forgets_the_filter_when_it_closes(engine_with_item) -> None:
    """Критерий 2: открыл заново — список полон, отбор пуст."""
    _two_items(engine_with_item)
    dialog = DeviationDialog(engine_with_item)
    dialog.reload_items()
    dialog.item.setCurrentText("MF5-10375A-N")

    dialog.item.filter_to("C1")
    dialog.item.hidePopup()

    assert dialog.item.visible_labels() == ["C1-08375A", "MF5-10375A-N"]
    assert dialog.item.currentText() == "MF5-10375A-N"


def test_typed_nonsense_cannot_reach_the_database(engine_with_item) -> None:
    """Критерий 3: несовпавший текст откатывается и в базу не попадает."""
    first, _second = _two_items(engine_with_item)
    dialog = DeviationDialog(engine_with_item)
    dialog.reload_items()
    dialog.item.select_key(first)

    dialog.item.lineEdit().setText("C1-99999X")  # такой детали нет
    dialog.item.settle()

    assert dialog.item.currentData() == first
    assert dialog.item.currentText() == "C1-08375A"


def test_the_deviation_lands_on_the_item_chosen_through_the_filter(
    engine_with_item, monkeypatch
) -> None:
    """Критерий 4: отклонение ложится на **выбранную** деталь — сверка по `item_id`.

    Проверяется ключом, а не подписью: подпись у двух деталей похожа настолько,
    что именно на ней и ошибся бы отбор.
    """
    from db.models import Deviation

    # Тест утверждает, что сохранение **проходит**, поэтому модальное окно
    # обязано быть поймано: под offscreen оно вешает прогон (`CLAUDE.md` §9).
    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    _first, second = _two_items(engine_with_item)
    dialog = DeviationDialog(engine_with_item)
    dialog.reload_items()

    # Оператор набирает середину номера и берёт единственное совпадение.
    matched = dialog.item.filter_to("10375")
    assert len(matched) == 1
    dialog.item.select_key(matched[0][0])

    dialog.wo.setText("W26007336")
    dialog.quantity.setValue(3)
    dialog.save()

    assert shown == []
    with session_scope(engine_with_item) as session:
        deviation = session.query(Deviation).one()
        assert deviation.item_id == second
