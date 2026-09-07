"""Исследование: заведение, независимость вердикта, зеркальный поиск (критерии 6, 7)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, rev
from db.models import Deviation, Direction, Inspection, Item, RefInspectionType
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.errors import ValidationError
from domain.findings import make_finding
from domain.inspections import (
    CONCLUSION_LIMIT,
    create_inspection,
    inspections_for,
    remove_inspection,
    update_inspection,
)
from domain.reference import list_values

TODAY = date(2026, 8, 11)


def _type(session: Session, name: str | None = None) -> RefInspectionType:
    values = list_values(session, RefInspectionType)
    if name is None:
        return values[0]
    from domain.reference import ensure_value

    return ensure_value(session, RefInspectionType, name)


def _finding(session: Session, item: Item, local_number: str = "12", wo: str = "W1"):
    deviation = register(session, item=item, wo=wo, quantity=3, date=TODAY)
    characteristic, _ = get_or_create_characteristic(session, rev(item), local_number)
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
        decision_insp="approval_possible",
        conclusion=None,
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
            decision_insp="approval_possible",
            conclusion=None,
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
            conclusion=None,
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
            decision_insp="approval_possible",
            conclusion=None,
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
            decision_insp="approval_possible",
            conclusion=None,
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
        decision_insp="approval_possible",
        conclusion=None,
        protocol="p.docx",
    )
    set_decision(
        seeded_session, finding.deviation, decision="rejected", explanation="в брак"
    )
    seeded_session.commit()

    deviation = seeded_session.query(Deviation).one()
    assert deviation.decision_dev == "rejected"
    assert [i.decision_insp for i in deviation.inspections] == ["approval_possible"]


# --- Правка и удаление -----------------------------------------------------------


def test_inspection_is_updated_wholesale(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion=None,
        protocol="old.docx",
    )

    update_inspection(
        seeded_session,
        inspection,
        inspection_type=_type(seeded_session, "Implantation torque test"),
        decision_insp="approval_not_possible",
        conclusion=None,
        protocol="new.docx",
    )
    seeded_session.commit()

    assert inspection.type.name == "Implantation torque test"
    assert (inspection.decision_insp, inspection.protocol) == ("approval_not_possible", "new.docx")


def test_update_demands_every_field(seeded_session: Session) -> None:
    """Правило S3: пропущенный аргумент не должен выглядеть как «не трогаем»."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion=None,
        protocol="p.docx",
    )

    with pytest.raises(TypeError):
        update_inspection(seeded_session, inspection, decision_insp="approval_not_possible")


def test_inspection_is_removed_without_touching_the_finding(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion=None,
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
        decision_insp="approval_possible",
        conclusion=None,
        protocol="first.docx",
    )
    create_inspection(
        seeded_session,
        second_finding,
        inspection_type=kind,
        decision_insp="approval_not_possible",
        conclusion=None,
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
    characteristic, _ = get_or_create_characteristic(seeded_session, rev(item), "12")

    for index, wo in enumerate(("W1", "W2")):
        deviation = register(seeded_session, item=item, wo=wo, quantity=1, date=TODAY)
        finding = make_finding(
            seeded_session, deviation, characteristic, direction=Direction.MINUS
        )
        create_inspection(
            seeded_session,
            finding,
            inspection_type=kind,
            decision_insp="approval_possible",
            conclusion=None,
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
        decision_insp="approval_possible",
        conclusion=None,
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


# --- QMS-018: позиция трёхзначна и необязательна, рядом — короткий вывод ----------


@pytest.mark.parametrize(
    "position", ["approval_possible", "approval_not_possible", "inconclusive"]
)
def test_the_three_positions_of_the_canon_are_accepted(
    seeded_session: Session, position: str
) -> None:
    """Критерий 5 наряда `0027`; правило `docs/model/Inspection.md` rev 1.01:
    «`decisionInsp` is three-valued and optional. Values: `approval possible` ·
    `approval not possible` · `inconclusive`».
    """
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-{position[:4]}"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp=position,
        conclusion=None,
        protocol="p.docx",
    )
    seeded_session.commit()

    assert inspection.decision_insp == position


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_position_is_accepted_and_stored_as_none(
    seeded_session: Session, empty
) -> None:
    """Правило `Inspection.md` rev 1.01: «**Empty means "not assessed yet"** and is
    a legitimate state: the protocol is attached first, the reading of it comes
    later».

    Пустая строка из формы и `None` — **одно** состояние, и хранится оно одним
    способом: иначе позиции пришлось бы сравнивать двумя.
    """
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-e{len(str(empty))}"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp=empty,
        conclusion=None,
        protocol="p.docx",
    )
    seeded_session.commit()

    assert inspection.decision_insp is None


@pytest.mark.parametrize("stale", ["approved", "not_approved"])
def test_the_old_binary_values_are_refused(seeded_session: Session, stale: str) -> None:
    """Критерий 5 наряда: старые значения отвергаются доменной валидацией.

    Не косметика: `approved` дословно совпадало с исходом отклонения, и приняв
    его здесь, база снова хранила бы две разные сущности одним словом.
    """
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-{stale[:3]}"))

    with pytest.raises(ValidationError) as excinfo:
        create_inspection(
            seeded_session,
            finding,
            inspection_type=_type(seeded_session),
            decision_insp=stale,
            conclusion=None,
            protocol="p.docx",
        )

    assert "approval_possible" in str(excinfo.value)


def test_a_conclusion_is_kept_and_trimmed(seeded_session: Session) -> None:
    """Правило `Inspection.md` rev 1.01: «`Conclusion` — short free text saying what
    the study found, optional, up to 500 characters».
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-C01"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion="  clearance in the assembled state −20 %  ",
        protocol="p.docx",
    )
    seeded_session.commit()

    assert inspection.conclusion == "clearance in the assembled state −20 %"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_conclusion_is_accepted(seeded_session: Session, empty) -> None:
    """Критерий 7 наряда: пустой вывод принимается — поле необязательное."""
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-c{len(str(empty))}"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion=empty,
        protocol="p.docx",
    )
    seeded_session.commit()

    assert inspection.conclusion is None


def test_a_conclusion_longer_than_the_limit_is_refused(seeded_session: Session) -> None:
    """Критерий 7 наряда; предел канона — 500 знаков, «three or four sentences».

    Граница проверяется с обеих сторон: ровно предел принимается, предел плюс
    один — нет. Проверка одного лишь длинного значения не отличила бы `>` от `>=`.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-C02"))

    at_the_limit = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion="x" * CONCLUSION_LIMIT,
        protocol="p.docx",
    )
    assert len(at_the_limit.conclusion) == CONCLUSION_LIMIT

    with pytest.raises(ValidationError) as excinfo:
        update_inspection(
            seeded_session,
            at_the_limit,
            inspection_type=_type(seeded_session),
            decision_insp="approval_possible",
            conclusion="x" * (CONCLUSION_LIMIT + 1),
            protocol="p.docx",
        )

    assert str(CONCLUSION_LIMIT) in str(excinfo.value)


def test_the_protocol_link_is_not_checked_for_existence(seeded_session: Session) -> None:
    """Правило `Inspection.md` rev 1.01: «its existence is **not** verified on entry
    — a protocol may sit on a share unreachable at the moment of typing, and a false
    refusal there costs more than a stale link» (решение 4 QMS-018).

    Отрицательное требование, и проверяется оно тем, что **не** происходит:
    заведомо несуществующий путь принимается.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-P01"))
    nowhere = r"\\nowhere\qa\never-existed.docx"

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp=None,
        conclusion=None,
        protocol=nowhere,
    )
    seeded_session.commit()

    assert inspection.protocol == nowhere


def test_an_empty_protocol_is_still_refused_when_the_position_is_empty(
    seeded_session: Session,
) -> None:
    """Критерий 8 наряда: обязательность протокола не ослаблена.

    Существенно именно в паре с пустой позицией: необязательными стали вывод и
    позиция, а критерий, по которому строка заводится вообще, — наличие
    письменного переиспользуемого анализа — остался (`Inspection.md`).
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-P02"))

    with pytest.raises(ValidationError) as excinfo:
        create_inspection(
            seeded_session,
            finding,
            inspection_type=_type(seeded_session),
            decision_insp=None,
            conclusion=None,
            protocol="   ",
        )

    assert "Protocol" in str(excinfo.value)


def test_update_replaces_the_conclusion_wholesale(seeded_session: Session) -> None:
    """`CLAUDE.md` §9: доменные `update_*` заменяют поля целиком, умолчаний нет.

    Пустой вывод, переданный явно, **стирает** прежний — это и значит «заменяет
    целиком». Умолчание сделало бы то же самое молча, выглядя как «не трогаем».
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-U01"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        decision_insp="approval_possible",
        conclusion="first reading",
        protocol="p.docx",
    )

    update_inspection(
        seeded_session,
        inspection,
        inspection_type=_type(seeded_session),
        decision_insp=None,
        conclusion=None,
        protocol="p.docx",
    )
    seeded_session.commit()

    assert (inspection.decision_insp, inspection.conclusion) == (None, None)
