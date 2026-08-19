"""Исследование: заведение, независимость вердикта, зеркальный поиск (критерии 6, 7)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Deviation, Direction, Inspection, Item, RefInspectionType
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.errors import ValidationError
from domain.findings import make_finding
from domain.inspections import (
    create_inspection,
    inspections_for,
    remove_inspection,
    update_inspection,
)
from domain.reference import add_value, list_values

TODAY = date(2026, 8, 11)


def _type(session: Session, name: str | None = None) -> RefInspectionType:
    values = list_values(session, RefInspectionType)
    if name is None:
        return values[0]
    return next((v for v in values if v.name == name), None) or add_value(
        session, RefInspectionType, name
    )


def _finding(session: Session, item: Item, local_number: str = "12", wo: str = "W1"):
    deviation = register(session, item=item, wo=wo, quantity=3, date=TODAY)
    characteristic, _ = get_or_create_characteristic(session, item, local_number)
    return make_finding(session, deviation, characteristic, direction=Direction.PLUS)


# --- Критерий 6: заведение -------------------------------------------------------


def test_inspection_is_created_on_a_finding_with_a_business_number(
    seeded_session: Session,
) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session, "Solidworks assembly"),
        decision_insp="approved",
        protocol=r"\\srv\qa\SW-2026-14.docx",
    )
    seeded_session.commit()

    assert inspection.insp_number.startswith("INSP-")
    assert inspection.finding is finding
    # Отклонение выводится из находки, отдельно не передаётся (`Inspection.md`).
    assert inspection.deviation is finding.deviation


def test_business_numbers_are_unique_within_a_day(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    finding = _finding(seeded_session, item)
    kind = _type(seeded_session)

    numbers = {
        create_inspection(
            seeded_session,
            finding,
            inspection_type=kind,
            decision_insp="approved",
            protocol=f"p{index}.docx",
        ).insp_number
        for index in range(5)
    }
    seeded_session.commit()

    assert len(numbers) == 5


def test_a_deviation_may_carry_no_inspections(seeded_session: Session) -> None:
    """`0..N`: рутинная сверка с чертежом строки не создаёт (`Inspection.md`)."""
    _finding(seeded_session, make_item(seeded_session, "IT-001"))
    seeded_session.commit()

    assert seeded_session.query(Inspection).count() == 0


def test_unknown_verdict_is_rejected(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    with pytest.raises(ValidationError):
        create_inspection(
            seeded_session,
            finding,
            inspection_type=_type(seeded_session),
            decision_insp="maybe",
            protocol="p.docx",
        )


def test_empty_protocol_is_refused(seeded_session: Session) -> None:
    """Критерий заведения строки — существование письменного анализа."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))

    with pytest.raises(ValidationError) as excinfo:
        create_inspection(
            seeded_session,
            finding,
            inspection_type=_type(seeded_session),
            decision_insp="approved",
            protocol="   ",
        )

    assert "Protocol" in str(excinfo.value)


def test_missing_type_is_refused(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    with pytest.raises(ValidationError):
        create_inspection(
            seeded_session,
            finding,
            inspection_type=None,
            decision_insp="approved",
            protocol="p.docx",
        )


def test_approved_inspection_under_a_rejected_deviation_is_valid(
    seeded_session: Session,
) -> None:
    """Критерий 6: `decision_insp` независим от `decision_dev` (`Inspection.md`)."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))

    create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approved",
        protocol="p.docx",
    )
    set_decision(
        seeded_session, finding.deviation, decision="rejected", explanation="в брак"
    )
    seeded_session.commit()

    deviation = seeded_session.query(Deviation).one()
    assert deviation.decision_dev == "rejected"
    assert [i.decision_insp for i in deviation.inspections] == ["approved"]


# --- Правка и удаление -----------------------------------------------------------


def test_inspection_is_updated_wholesale(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approved",
        protocol="old.docx",
    )

    update_inspection(
        seeded_session,
        inspection,
        inspection_type=_type(seeded_session, "Implantation torque test"),
        decision_insp="not_approved",
        protocol="new.docx",
    )
    seeded_session.commit()

    assert inspection.type.name == "Implantation torque test"
    assert (inspection.decision_insp, inspection.protocol) == ("not_approved", "new.docx")


def test_update_demands_every_field(seeded_session: Session) -> None:
    """Правило S3: пропущенный аргумент не должен выглядеть как «не трогаем»."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approved",
        protocol="p.docx",
    )

    with pytest.raises(TypeError):
        update_inspection(seeded_session, inspection, decision_insp="not_approved")


def test_inspection_is_removed_without_touching_the_finding(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approved",
        protocol="p.docx",
    )

    remove_inspection(seeded_session, inspection)
    seeded_session.commit()

    assert seeded_session.query(Inspection).count() == 0
    assert finding.deviation.findings == [finding]
    # Граф в памяти согласован с базой — не «призрак» удалённой строки.
    assert finding.inspections == []


# --- Критерий 7: зеркальный поиск по паре (Item, размер) -------------------------


def test_mirror_search_does_not_mix_two_items_with_the_same_dimension_number(
    seeded_session: Session,
) -> None:
    """Номер размера уникален только внутри детали — «дим 12» двух деталей разные."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    first_finding = _finding(seeded_session, first, "12", wo="W1")
    second_finding = _finding(seeded_session, second, "12", wo="W2")
    kind = _type(seeded_session)

    create_inspection(
        seeded_session,
        first_finding,
        inspection_type=kind,
        decision_insp="approved",
        protocol="first.docx",
    )
    create_inspection(
        seeded_session,
        second_finding,
        inspection_type=kind,
        decision_insp="not_approved",
        protocol="second.docx",
    )
    seeded_session.commit()

    first_hits = inspections_for(seeded_session, first, first_finding.characteristic)
    second_hits = inspections_for(seeded_session, second, second_finding.characteristic)

    assert [i.protocol for i in first_hits] == ["first.docx"]
    assert [i.protocol for i in second_hits] == ["second.docx"]


def test_mirror_search_gathers_inspections_across_deviations(seeded_session: Session) -> None:
    """Пара (Item, размер) — сквозная: выдача не ограничена одним отклонением."""
    item = make_item(seeded_session, "IT-001")
    kind = _type(seeded_session)
    characteristic, _ = get_or_create_characteristic(seeded_session, item, "12")

    for index, wo in enumerate(("W1", "W2")):
        deviation = register(seeded_session, item=item, wo=wo, quantity=1, date=TODAY)
        finding = make_finding(
            seeded_session, deviation, characteristic, direction=Direction.MINUS
        )
        create_inspection(
            seeded_session,
            finding,
            inspection_type=kind,
            decision_insp="approved",
            protocol=f"p{index}.docx",
        )
    seeded_session.commit()

    hits = inspections_for(seeded_session, item, characteristic)

    assert len(hits) == 2
    assert {i.deviation.wo for i in hits} == {"W1", "W2"}


def test_mirror_search_returns_nothing_for_a_mismatched_pair(seeded_session: Session) -> None:
    """Половинки пары от разных деталей — пустая выдача, а не чужие исследования."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    finding = _finding(seeded_session, first, "12")
    create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approved",
        protocol="p.docx",
    )
    seeded_session.commit()

    assert inspections_for(seeded_session, second, finding.characteristic) == []


def test_mirror_search_is_empty_for_a_dimension_without_inspections(
    seeded_session: Session,
) -> None:
    item = make_item(seeded_session, "IT-001")
    finding = _finding(seeded_session, item)
    seeded_session.commit()

    assert inspections_for(seeded_session, item, finding.characteristic) == []
