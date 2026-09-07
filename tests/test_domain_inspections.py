"""Исследование: заведение, независимость вердикта, зеркальный поиск (критерии 6, 7)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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
        conclusion=None,
        protocol=r"\\srv\qa\SW-2026-14.docx",
        no_protocol=False,
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
            conclusion=None,
            protocol=f"p{index}.docx",
            no_protocol=False,
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


def test_empty_protocol_is_refused(seeded_session: Session) -> None:
    """Критерий заведения строки — существование письменного анализа."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))

    with pytest.raises(ValidationError) as excinfo:
        create_inspection(
            seeded_session,
            finding,
            inspection_type=_type(seeded_session),
            conclusion=None,
            protocol="   ",
            no_protocol=False,
        )

    assert "Protocol" in str(excinfo.value)


def test_missing_type_is_refused(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    with pytest.raises(ValidationError):
        create_inspection(
            seeded_session,
            finding,
            inspection_type=None,
            conclusion=None,
            protocol="p.docx",
            no_protocol=False,
        )


def test_an_inspection_under_a_rejected_deviation_is_valid(
    seeded_session: Session,
) -> None:
    """Независимость исследования от решения стала **структурной** (rev 1.03).

    До QMS-025 её сторожило правило «`decision_insp` независим от `decision_dev`»,
    и сторожить приходилось потому, что поле было. Теперь поля нет, и нарушить
    независимость нечем; проверяется то, что осталось проверяемым: исследование
    заводится и живёт при любом исходе отклонения.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))

    create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
    )
    set_decision(
        seeded_session, finding.deviation, decision="rejected", explanation="в брак"
    )
    seeded_session.commit()

    deviation = seeded_session.query(Deviation).one()
    assert deviation.decision_dev == "rejected"
    assert len(deviation.inspections) == 1
    assert not hasattr(deviation.inspections[0], "decision_insp")


# --- Правка и удаление -----------------------------------------------------------


def test_inspection_is_updated_wholesale(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        conclusion=None,
        protocol="old.docx",
        no_protocol=False,
    )

    update_inspection(
        seeded_session,
        inspection,
        inspection_type=_type(seeded_session, "Implantation torque test"),
        conclusion=None,
        protocol="new.docx",
        no_protocol=False,
    )
    seeded_session.commit()

    assert inspection.type.name == "Implantation torque test"
    assert inspection.protocol == "new.docx"


def test_update_demands_every_field(seeded_session: Session) -> None:
    """Правило S3: пропущенный аргумент не должен выглядеть как «не трогаем»."""
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
    )

    with pytest.raises(TypeError):
        update_inspection(seeded_session, inspection, conclusion="only one argument")


def test_inspection_is_removed_without_touching_the_finding(seeded_session: Session) -> None:
    finding = _finding(seeded_session, make_item(seeded_session, "IT-001"))
    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
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
        conclusion=None,
        protocol="first.docx",
        no_protocol=False,
    )
    create_inspection(
        seeded_session,
        second_finding,
        inspection_type=kind,
        conclusion=None,
        protocol="second.docx",
        no_protocol=False,
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
            conclusion=None,
            protocol=f"p{index}.docx",
            no_protocol=False,
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
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
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

def test_a_conclusion_is_kept_and_trimmed(seeded_session: Session) -> None:
    """Правило `Inspection.md` rev 1.01: «`Conclusion` — short free text saying what
    the study found, optional, up to 500 characters».
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-C01"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session),
        conclusion="  clearance in the assembled state −20 %  ",
        protocol="p.docx",
        no_protocol=False,
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
        conclusion=empty,
        protocol="p.docx",
        no_protocol=False,
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
        conclusion="x" * CONCLUSION_LIMIT,
        protocol="p.docx",
        no_protocol=False,
    )
    assert len(at_the_limit.conclusion) == CONCLUSION_LIMIT

    with pytest.raises(ValidationError) as excinfo:
        update_inspection(
            seeded_session,
            at_the_limit,
            inspection_type=_type(seeded_session),
            conclusion="x" * (CONCLUSION_LIMIT + 1),
            protocol="p.docx",
            no_protocol=False,
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
        conclusion=None,
        protocol=nowhere,
        no_protocol=False,
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
            conclusion=None,
            protocol="   ",
            no_protocol=False,
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
        conclusion="first reading",
        protocol="p.docx",
        no_protocol=False,
    )

    update_inspection(
        seeded_session,
        inspection,
        inspection_type=_type(seeded_session),
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
    )
    seeded_session.commit()

    assert inspection.conclusion is None


# --- QMS-024: исследование без протокола, инвариант «файл ИЛИ вывод» --------------


def _raw_inspection(session, finding, **columns) -> None:
    """Вставка **в обход домена** — прямым SQL, минуя всякую валидацию.

    Ради этого тесты ограничения и существуют: доменную проверку обходят
    импортом, скриптом или следующим нарядом, а `CHECK` обойти нечем.
    """
    kind = list_values(session, RefInspectionType)[0]
    values = {
        "insp_number": f"INSP-260907-{columns.pop('n', 1):03d}",
        "deviation_id": finding.deviation_id,
        "finding_id": finding.finding_id,
        "type_id": kind.inspection_type_id,
        "conclusion": None,
        "protocol": None,
        "no_protocol": 0,
    }
    values.update(columns)
    session.execute(
        text(
            "INSERT INTO inspection (insp_number, deviation_id, finding_id, type_id,"
            " conclusion, protocol, no_protocol)"
            " VALUES (:insp_number, :deviation_id, :finding_id, :type_id,"
            " :conclusion, :protocol, :no_protocol)"
        ),
        values,
    )


def test_a_record_with_neither_a_file_nor_a_conclusion_is_refused_by_the_schema(
    seeded_session: Session,
) -> None:
    """**Главный тест наряда `0029`.** Правило `docs/model/Inspection.md` rev 1.02:
    «A row with neither says nothing to the precedent search and must not exist —
    that is the invariant this section is about, and it is **enforced by the
    schema, not by discipline**».

    Вставка идёт **прямым SQL, мимо домена**: доменную проверку обходят импортом,
    скриптом или следующим нарядом, и тест, идущий через `create_inspection`,
    проверял бы форму записи, а не инвариант.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-N01"))
    seeded_session.flush()

    with pytest.raises(IntegrityError):
        _raw_inspection(seeded_session, finding, no_protocol=1)
    seeded_session.rollback()


@pytest.mark.parametrize(
    ("columns", "why"),
    [
        ({"no_protocol": 0, "protocol": None}, "признак снят, файла нет"),
        ({"no_protocol": 0, "protocol": "   "}, "признак снят, путь из пробелов"),
        ({"no_protocol": 1, "conclusion": None}, "признак поднят, вывода нет"),
        ({"no_protocol": 1, "conclusion": "  "}, "признак поднят, вывод из пробелов"),
        (
            {"no_protocol": 1, "conclusion": "settled by the drawing", "protocol": "p.docx"},
            "признак поднят и путь введён — «файл есть, но не нужен»",
        ),
    ],
)
def test_the_schema_refuses_every_shape_the_invariant_forbids(
    seeded_session: Session, columns: dict, why: str
) -> None:
    """Каждый из пяти запрещённых видов записи — отдельным случаем.

    Пятый существен особо: `no_protocol = 1` вместе с путём это «файл есть, но он
    не нужен» — состояние без смысла, и допустить его значит завести третий
    случай, который придётся объяснять на каждом экране (§1 наряда).
    """
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-{abs(hash(why)) % 900:03d}"))
    seeded_session.flush()

    with pytest.raises(IntegrityError):
        _raw_inspection(seeded_session, finding, **columns)
    seeded_session.rollback()


@pytest.mark.parametrize(
    ("columns", "why"),
    [
        ({"no_protocol": 0, "protocol": "p.docx"}, "файл есть — обычная запись"),
        (
            {"no_protocol": 1, "conclusion": "OD 10.0 vs ID 9.9 — geometry excludes assembly"},
            "файла нет, вывод есть — случай, ради которого заведён признак",
        ),
    ],
)
def test_the_schema_admits_both_legitimate_shapes(
    seeded_session: Session, columns: dict, why: str
) -> None:
    """Обратная сторона: ограничение пропускает **оба** законных вида.

    Без неё предыдущий тест был бы зелёным и на схеме, которая не пропускает
    ничего, — то есть не отличал бы верное от неверного (`CLAUDE.md` §9а.4).
    """
    finding = _finding(seeded_session, make_item(seeded_session, f"IT-{abs(hash(why)) % 900:03d}"))
    seeded_session.flush()

    _raw_inspection(seeded_session, finding, **columns)
    seeded_session.flush()

    assert seeded_session.query(Inspection).count() == 1


def test_a_verdict_without_a_document_is_recorded_with_its_conclusion(
    seeded_session: Session,
) -> None:
    """Правило `Inspection.md` rev 1.02 и повод наряда: «an outer diameter of 10.0
    against an inner one of 9.9 does not fit, and no study will change that — and
    that verdict is a reusable precedent worth recording, while no document exists
    to attach».
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-N02"))

    inspection = create_inspection(
        seeded_session,
        finding,
        inspection_type=_type(seeded_session, "Tolerances review"),
        conclusion="OD 10.0 vs ID 9.9 — no mating clearance, geometry excludes assembly",
        protocol=None,
        no_protocol=True,
    )
    seeded_session.commit()

    assert inspection.no_protocol is True
    assert inspection.protocol is None
    assert inspection.conclusion.startswith("OD 10.0")


def test_the_domain_explains_what_is_missing_instead_of_an_integrity_error(
    seeded_session: Session,
) -> None:
    """§2 наряда: доменная валидация **человеческим текстом поверх** ограничения.

    Ограничение ловит любой путь записи и отвечает `IntegrityError`; оператору
    надо сказать, чего именно не хватает. Три нехватки — три разных текста, и
    каждый называет **следующее действие**, а не нарушенное правило.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-N03"))

    with pytest.raises(ValidationError) as no_file:
        create_inspection(
            seeded_session, finding, inspection_type=_type(seeded_session),
            conclusion=None, protocol="", no_protocol=False,
        )
    assert "No protocol" in str(no_file.value)

    with pytest.raises(ValidationError) as no_conclusion:
        create_inspection(
            seeded_session, finding, inspection_type=_type(seeded_session),
            conclusion=None, protocol=None, no_protocol=True,
        )
    assert "conclusion" in str(no_conclusion.value)

    with pytest.raises(ValidationError) as both:
        create_inspection(
            seeded_session, finding, inspection_type=_type(seeded_session),
            conclusion="settled", protocol="p.docx", no_protocol=True,
        )
    assert "must be empty" in str(both.value)

    # Ни одна из трёх попыток записи не оставила строки.
    assert seeded_session.query(Inspection).count() == 0


def test_the_flag_survives_an_update_in_both_directions(seeded_session: Session) -> None:
    """`update_inspection` заменяет поля целиком, и признак — тоже поле.

    Проверяются **оба** перехода: обычная запись становится записью без файла и
    обратно. Один переход был бы зелёным и на коде, который признак только
    поднимает.
    """
    finding = _finding(seeded_session, make_item(seeded_session, "IT-N04"))
    inspection = create_inspection(
        seeded_session, finding, inspection_type=_type(seeded_session),
        conclusion=None, protocol="p.docx", no_protocol=False,
    )

    update_inspection(
        seeded_session, inspection, inspection_type=_type(seeded_session),
        conclusion="the drawing settles it", protocol=None, no_protocol=True,
    )
    seeded_session.commit()
    assert (inspection.no_protocol, inspection.protocol) == (True, None)

    update_inspection(
        seeded_session, inspection, inspection_type=_type(seeded_session),
        conclusion="the drawing settles it", protocol="back.docx", no_protocol=False,
    )
    seeded_session.commit()
    assert (inspection.no_protocol, inspection.protocol) == (False, "back.docx")
