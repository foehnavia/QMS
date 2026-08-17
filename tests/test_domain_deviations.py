"""Отклонение: регистрация, решение, список, удаление (критерии 1, 5, 8 наряда 0004)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Deviation, Direction, Finding, Inspection, Item, RefInspectionType
from domain.characteristics import get_or_create_characteristic
from domain.deviations import (
    delete_deviation,
    list_deviations,
    register,
    set_decision,
    update_registration,
)
from domain.errors import ValidationError
from domain.findings import make_finding
from domain.inspections import create_inspection
from domain.reference import list_values

TODAY = date(2026, 8, 11)


def _item(session: Session, number: str = "C1-08375A") -> Item:
    return make_item(session, number)


def _register(session: Session, item: Item, **overrides) -> Deviation:
    kwargs = dict(wo="W26007336", quantity=5, date=TODAY)
    kwargs.update(overrides)
    return register(session, item=item, **kwargs)


# --- Критерий 1: регистрация -----------------------------------------------------


def test_registration_creates_a_numbered_deviation_without_a_decision(
    seeded_session: Session,
) -> None:
    """Регистрация — шаг 3, решение — шаг 8: запись рождается без исхода."""
    item = _item(seeded_session)

    deviation = _register(seeded_session, item, machine="CNC-7", ncr="NCR-118")
    seeded_session.commit()

    assert deviation.dev_number.startswith("DEV-")
    assert deviation.decision_dev is None
    assert deviation.explanation == ""
    assert (deviation.wo, deviation.quantity, deviation.machine) == ("W26007336", 5, "CNC-7")


def test_registration_refuses_empty_wo(seeded_session: Session) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _register(seeded_session, _item(seeded_session), wo="   ")
    assert "WO" in str(excinfo.value)


@pytest.mark.parametrize("quantity", [0, -3])
def test_registration_refuses_a_non_positive_quantity(
    seeded_session: Session, quantity: int
) -> None:
    with pytest.raises(ValidationError):
        _register(seeded_session, _item(seeded_session), quantity=quantity)


def test_registration_refuses_a_fractional_quantity(seeded_session: Session) -> None:
    """Количество деталей — штуки; `2.5` отбивается до базы, а не округляется."""
    with pytest.raises(ValidationError):
        _register(seeded_session, _item(seeded_session), quantity=2.5)


def test_registration_refuses_a_future_date(seeded_session: Session) -> None:
    tomorrow = datetime.now().date() + timedelta(days=1)
    with pytest.raises(ValidationError) as excinfo:
        _register(seeded_session, _item(seeded_session), date=tomorrow)
    assert "будущем" in str(excinfo.value)


def test_registration_refuses_a_deviation_without_an_item(seeded_session: Session) -> None:
    with pytest.raises(ValidationError):
        register(seeded_session, item=None, wo="W1", quantity=1, date=TODAY)


def test_sampling_quantity_9999_is_an_ordinary_number_here(seeded_session: Session) -> None:
    """Заметка А: сентинел выборки приходит из импорта S6, ручной ввод его не знает."""
    deviation = _register(seeded_session, _item(seeded_session), quantity=9999)
    assert deviation.quantity == 9999


def test_blank_optional_fields_are_stored_as_absent(seeded_session: Session) -> None:
    """Пробелы в необязательном поле — это отсутствие значения, а не значение."""
    deviation = _register(seeded_session, _item(seeded_session), machine="  ", ncr="")
    assert deviation.machine is None and deviation.ncr is None


# --- Правка шапки ----------------------------------------------------------------


def test_registration_can_be_edited(seeded_session: Session) -> None:
    deviation = _register(seeded_session, _item(seeded_session), machine="CNC-7", ncr="NCR-1")

    update_registration(
        seeded_session,
        deviation,
        wo="W26009000",
        quantity=12,
        date=TODAY,
        machine=None,
        ncr="NCR-2",
        attachment=r"\\srv\qa\photo.jpg",
    )
    seeded_session.commit()

    assert (deviation.wo, deviation.quantity, deviation.ncr) == ("W26009000", 12, "NCR-2")
    assert deviation.machine is None
    assert deviation.attachment.endswith("photo.jpg")


# --- Критерий 5: решение ---------------------------------------------------------


def test_decision_is_a_separate_action(seeded_session: Session) -> None:
    deviation = _register(seeded_session, _item(seeded_session))

    set_decision(
        seeded_session, deviation, decision="approved", explanation="Влияния на сборку нет."
    )
    seeded_session.commit()

    assert deviation.decision_dev == "approved"
    assert deviation.explanation == "Влияния на сборку нет."


@pytest.mark.parametrize("decision", ["approved", "rejected", "sorting", "repair"])
def test_all_four_outcomes_are_accepted(seeded_session: Session, decision: str) -> None:
    deviation = _register(seeded_session, _item(seeded_session))
    set_decision(seeded_session, deviation, decision=decision, explanation="обоснование")
    assert deviation.decision_dev == decision


def test_unknown_outcome_is_rejected(seeded_session: Session) -> None:
    deviation = _register(seeded_session, _item(seeded_session))
    with pytest.raises(ValidationError):
        set_decision(seeded_session, deviation, decision="maybe", explanation="x")


def test_approval_without_an_explanation_is_refused(seeded_session: Session) -> None:
    """Ратификация S1 №3: обоснование одобрения уходит в אישור חריגה."""
    deviation = _register(seeded_session, _item(seeded_session))

    with pytest.raises(ValidationError) as excinfo:
        set_decision(seeded_session, deviation, decision="approved", explanation="   ")

    assert "חריגה" in str(excinfo.value)
    assert deviation.decision_dev is None


def test_rejection_without_an_explanation_is_allowed(seeded_session: Session) -> None:
    """Пустое обоснование запрещено только на одобрении — документ выдаётся только там."""
    deviation = _register(seeded_session, _item(seeded_session))
    set_decision(seeded_session, deviation, decision="rejected", explanation="")
    assert deviation.decision_dev == "rejected"


def test_changing_the_decision_rewrites_the_decision_date(seeded_session: Session) -> None:
    deviation = _register(seeded_session, _item(seeded_session))
    old = datetime(2026, 1, 1, 12, 0)

    set_decision(
        seeded_session, deviation, decision="sorting", explanation="100 %", decision_date=old
    )
    assert deviation.decision_date == old

    set_decision(seeded_session, deviation, decision="rejected", explanation="брак")
    assert deviation.decision_date > old


def test_decision_keeps_the_ncr_entered_at_registration(seeded_session: Session) -> None:
    """`ncr=None` — «не трогать»: номер QA вводится и на регистрации, и в решении."""
    deviation = _register(seeded_session, _item(seeded_session), ncr="NCR-118")

    set_decision(seeded_session, deviation, decision="rejected", explanation="брак")

    assert deviation.ncr == "NCR-118"


def test_decision_can_set_and_clear_the_ncr_explicitly(seeded_session: Session) -> None:
    deviation = _register(seeded_session, _item(seeded_session))

    set_decision(seeded_session, deviation, decision="repair", explanation="x", ncr="NCR-9")
    assert deviation.ncr == "NCR-9"

    set_decision(seeded_session, deviation, decision="repair", explanation="x", ncr="")
    assert deviation.ncr is None


# --- Список ----------------------------------------------------------------------


def test_list_counts_findings_and_inspections(seeded_session: Session) -> None:
    item = _item(seeded_session)
    deviation = _register(seeded_session, item)
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    other, _ = get_or_create_characteristic(seeded_session, item, "19")
    finding = make_finding(seeded_session, deviation, char, direction=Direction.PLUS)
    make_finding(seeded_session, deviation, other, direction=Direction.MINUS)
    create_inspection(
        seeded_session,
        finding,
        inspection_type=list_values(seeded_session, RefInspectionType)[0],
        decision_insp="approved",
        protocol=r"\\srv\qa\p.docx",
    )
    seeded_session.commit()

    rows = list_deviations(seeded_session)

    assert len(rows) == 1
    assert (rows[0].findings, rows[0].inspections) == (2, 1)
    assert rows[0].item_number == item.item_number
    assert rows[0].decision_dev is None


def test_list_shows_a_deviation_without_findings_as_zero(seeded_session: Session) -> None:
    """Отклонение без находок в домене возможно — инвариант 1..N держит форма."""
    _register(seeded_session, _item(seeded_session))
    seeded_session.commit()

    rows = list_deviations(seeded_session)
    assert (rows[0].findings, rows[0].inspections) == (0, 0)


def test_list_can_be_narrowed_to_one_item(seeded_session: Session) -> None:
    first = _item(seeded_session, "IT-001")
    second = _item(seeded_session, "IT-002")
    _register(seeded_session, first)
    _register(seeded_session, second)
    seeded_session.commit()

    rows = list_deviations(seeded_session, item=second)

    assert [row.item_number for row in rows] == ["IT-002"]


# --- Критерий 8: целостность -----------------------------------------------------


def test_deleting_a_deviation_takes_findings_and_inspections(seeded_session: Session) -> None:
    item = _item(seeded_session)
    deviation = _register(seeded_session, item)
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    finding = make_finding(seeded_session, deviation, char, direction=Direction.PLUS)
    create_inspection(
        seeded_session,
        finding,
        inspection_type=list_values(seeded_session, RefInspectionType)[0],
        decision_insp="not_approved",
        protocol="protocol.docx",
    )
    seeded_session.commit()

    delete_deviation(seeded_session, deviation)
    seeded_session.commit()

    assert seeded_session.query(Deviation).count() == 0
    assert seeded_session.query(Finding).count() == 0
    assert seeded_session.query(Inspection).count() == 0
    # Размер детали переживает удаление: он существует независимо от отклонения.
    assert seeded_session.query(Item).one().characteristics[0].local_number == "12"
