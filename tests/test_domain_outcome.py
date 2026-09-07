"""Исход находки и связывающий инвариант (QMS-025, наряд 0030).

Все проверки инварианта заходят **мимо формы, прямо в домен** — так требует §2
наряда, и не ради удобства: инвариант межтабличный, `CHECK` его не выражает, а
триггер в SQLite молча теряется при пересборке таблицы миграцией. Схема его не
держит, значит держат домен и эти тесты, и тест через диалог проверял бы, что
форма зовёт домен, а не что домен инвариант держит.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import make_item, rev
from db.models import Direction, Finding
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.errors import InvariantViolation, ValidationError
from domain.findings import check_outcome, make_finding, update_finding

TODAY = date.today()


def _deviation(session: Session, item, *, numbers=("12",), wo: str = "W1"):
    deviation = register(session, item=item, wo=wo, quantity=5, date=TODAY)
    findings = []
    for number in numbers:
        characteristic, _ = get_or_create_characteristic(session, rev(item), number)
        findings.append(
            make_finding(
                session, deviation, characteristic, direction=Direction.PLUS, value=0.08
            )
        )
    return deviation, findings


def _set_outcome(session: Session, finding: Finding, outcome: str | None) -> Finding:
    """Правка находки **доменом**, со всеми полями: `update_*` заменяет целиком."""
    return update_finding(
        session,
        finding,
        direction=finding.direction,
        value=finding.value,
        dimension_point=finding.dimension_point,
        comment=finding.comment,
        zone=finding.zone,
        deviation_type=finding.deviation_type,
        outcome=outcome,
    )


# --- Критерий 3: инвариант, точка 1 — сохранение решения ---------------------------


def test_approved_is_refused_while_a_finding_is_not_permitted(
    seeded_session: Session,
) -> None:
    """**Главный тест наряда `0030`, точка 1.** Правило `docs/model/Deviation.md`
    rev 1.03: «a deviation may carry `approved — use as is` **only** when every one
    of its findings is `permitted`».

    Заходит **прямо в домен**: `set_decision` — та функция, которую зовут и форма,
    и импорт, и следующий наряд, и инвариант обязан держаться на ней, а не на
    диалоге.
    """
    item = make_item(seeded_session, "IT-001")
    deviation, findings = _deviation(seeded_session, item, numbers=("12", "19"))
    _set_outcome(seeded_session, findings[0], "permitted")
    _set_outcome(seeded_session, findings[1], "not_permitted")

    with pytest.raises(InvariantViolation) as refused:
        set_decision(
            seeded_session, deviation, decision="approved", explanation="fits anyway"
        )

    # Текст называет **размеры поимённо**: «какая-то находка не прошла» — это
    # ровно та работа по открыванию записей, ради устранения которой исход и
    # переехал на находку.
    assert "no. 19" in str(refused.value)
    assert "no. 12" not in str(refused.value)
    assert deviation.decision_dev is None


def test_approved_is_refused_while_a_finding_is_undecided(seeded_session: Session) -> None:
    """Та же точка, **пустой исход**. Правило `Deviation.md` rev 1.03: «any finding
    state other than `permitted` — *including empty* — closes that outcome».

    Отдельным тестом от предыдущего, потому что это отдельное состояние и самая
    вероятная ошибка реализации: проверка `outcome == "not_permitted"` вместо
    `outcome != "permitted"` прошла бы первый тест и провалила этот.
    """
    item = make_item(seeded_session, "IT-002")
    deviation, findings = _deviation(seeded_session, item, numbers=("12", "19"))
    _set_outcome(seeded_session, findings[0], "permitted")
    # Вторая остаётся пустой — «ещё не решали».

    with pytest.raises(InvariantViolation) as refused:
        set_decision(seeded_session, deviation, decision="approved", explanation="ok")

    assert "no. 19 (not decided)" in str(refused.value)
    assert deviation.decision_dev is None


def test_approved_passes_when_every_finding_is_permitted(seeded_session: Session) -> None:
    """**Критерий 4, обратная сторона.** Без неё предыдущие два были бы зелёными и
    на коде, который не одобряет **никогда**, — то есть не отличали бы верное от
    неверного (`CLAUDE.md` §9а.4).
    """
    item = make_item(seeded_session, "IT-003")
    deviation, findings = _deviation(seeded_session, item, numbers=("12", "19", "77"))
    for finding in findings:
        _set_outcome(seeded_session, finding, "permitted")

    set_decision(seeded_session, deviation, decision="approved", explanation="all pass")
    seeded_session.commit()

    assert deviation.decision_dev == "approved"


@pytest.mark.parametrize("decision", ["rejected", "sorting", "repair"])
def test_the_other_three_decisions_require_nothing(
    seeded_session: Session, decision: str
) -> None:
    """**Критерий 4.** Правило `Deviation.md` rev 1.03: «The other three
    (`rejected`, `sorting`, `repair`) require nothing: they are what the engineer
    picks precisely **while sorting the matter out**».

    Проверяется на самом тяжёлом наборе — одна находка не прошла, вторая не
    решена: если бы инвариант применялся ко всем исходам, здесь он и сработал бы.
    """
    item = make_item(seeded_session, f"IT-{decision[:3]}")
    deviation, findings = _deviation(seeded_session, item, numbers=("12", "19"))
    _set_outcome(seeded_session, findings[0], "not_permitted")

    set_decision(
        seeded_session, deviation, decision=decision, explanation="sorting it out"
    )
    seeded_session.commit()

    assert deviation.decision_dev == decision


# --- Критерий 3: инвариант, точка 2 — правка находки -------------------------------


def test_a_finding_cannot_be_refused_under_an_approved_deviation(
    seeded_session: Session,
) -> None:
    """**Главный тест наряда `0030`, точка 2.** Правило `Deviation.md` rev 1.03:
    «a finding cannot be changed to `not permitted` while its deviation stands
    `approved` — the edit is refused with an explanation, because **silently
    voiding a decision that has gone into a document** is worse than making the
    engineer withdraw it on purpose».

    Тоже мимо формы: `update_finding` зовут и диалог, и импорт S6.
    """
    item = make_item(seeded_session, "IT-004")
    deviation, findings = _deviation(seeded_session, item, numbers=("12",))
    _set_outcome(seeded_session, findings[0], "permitted")
    set_decision(seeded_session, deviation, decision="approved", explanation="ok")

    with pytest.raises(InvariantViolation) as refused:
        _set_outcome(seeded_session, findings[0], "not_permitted")

    # Текст называет **следующее действие**, а не нарушенное правило.
    assert "Withdraw the decision" in str(refused.value)
    assert findings[0].outcome == "permitted"


def test_the_same_edit_passes_once_the_decision_is_withdrawn(
    seeded_session: Session,
) -> None:
    """Обратная сторона точки 2: путь наружу существует и работает.

    Отказ, из которого нет выхода, — это не инвариант, а тупик. Проверяется
    именно **последовательность**: сняли решение, и та же правка прошла.
    """
    item = make_item(seeded_session, "IT-005")
    deviation, findings = _deviation(seeded_session, item, numbers=("12",))
    _set_outcome(seeded_session, findings[0], "permitted")
    set_decision(seeded_session, deviation, decision="approved", explanation="ok")

    set_decision(seeded_session, deviation, decision="sorting", explanation="withdrawn")
    _set_outcome(seeded_session, findings[0], "not_permitted")
    seeded_session.commit()

    assert findings[0].outcome == "not_permitted"


def test_other_edits_of_a_finding_are_not_blocked_by_the_decision(
    seeded_session: Session,
) -> None:
    """Запирается **переход в `not_permitted`**, а не правка находки вообще.

    Иначе одобренное отклонение нельзя было бы поправить ни в чём — ни в
    комментарии, ни в величине, — и инвариант превратился бы в замок на записи.
    """
    item = make_item(seeded_session, "IT-006")
    deviation, findings = _deviation(seeded_session, item, numbers=("12",))
    _set_outcome(seeded_session, findings[0], "permitted")
    set_decision(seeded_session, deviation, decision="approved", explanation="ok")

    update_finding(
        seeded_session,
        findings[0],
        direction=Direction.MINUS,
        value=0.11,
        dimension_point=2,
        comment="re-measured",
        zone=None,
        deviation_type=None,
        outcome="permitted",
    )
    seeded_session.commit()

    assert (findings[0].value, findings[0].comment) == (0.11, "re-measured")


# --- Значение исхода: словарь и его границы ----------------------------------------


@pytest.mark.parametrize("outcome", ["permitted", "not_permitted"])
def test_both_values_of_the_canon_are_accepted(seeded_session: Session, outcome: str) -> None:
    """Правило `docs/model/Finding.md` rev 1.01: «**`outcome`** — `permitted` ·
    `not permitted` · **empty = not decided yet**».
    """
    item = make_item(seeded_session, f"IT-{outcome[:4]}")
    _, findings = _deviation(seeded_session, item)

    _set_outcome(seeded_session, findings[0], outcome)
    seeded_session.commit()

    assert findings[0].outcome == outcome


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_outcome_is_stored_as_none(seeded_session: Session, empty) -> None:
    """Пусто нормализуется к `None`: «не решено» и «пустая строка из формы» — одно
    состояние, и хранить его двумя способами значило бы сравнивать исходы двумя
    способами (тот же довод, что у позиции исследования в QMS-018).
    """
    assert check_outcome(empty) is None


def test_an_unknown_outcome_is_refused(seeded_session: Session) -> None:
    """Словарь остаётся словарём: «approved» на находке — чужое слово."""
    with pytest.raises(ValidationError) as refused:
        check_outcome("approved")

    assert "permitted" in str(refused.value)


def test_the_schema_refuses_an_outcome_outside_the_canon(seeded_session: Session) -> None:
    """`CHECK` на самом значении — **это** схема выражает, в отличие от связи.

    Инвариант «approved требует всех permitted» межтабличный и живёт в домене; а
    вот словарь одного поля схема держит, и вставка мимо домена его не обходит.
    """
    from sqlalchemy import text

    item = make_item(seeded_session, "IT-007")
    _, findings = _deviation(seeded_session, item)
    seeded_session.flush()

    with pytest.raises(IntegrityError):
        seeded_session.execute(
            text("UPDATE finding SET outcome = 'maybe' WHERE finding_id = :id"),
            {"id": findings[0].finding_id},
        )
    seeded_session.rollback()


def test_a_fresh_finding_is_undecided(seeded_session: Session) -> None:
    """Правило `Finding.md` rev 1.01: «Empty is the **normal state** of a freshly
    registered deviation: findings are entered at registration, and the judgement
    comes later».
    """
    item = make_item(seeded_session, "IT-008")
    _, findings = _deviation(seeded_session, item, numbers=("12", "19"))
    seeded_session.commit()

    assert [finding.outcome for finding in findings] == [None, None]


def test_update_finding_demands_the_outcome_explicitly(seeded_session: Session) -> None:
    """`CLAUDE.md` §9: у доменных `update_*` значений по умолчанию не появляется.

    Пропущенный аргумент стирал бы исход, выглядя как «это поле не трогаем», — а
    стёртый исход закрывает одобрение, то есть молча меняет то, что можно решить.
    """
    item = make_item(seeded_session, "IT-009")
    _, findings = _deviation(seeded_session, item)

    with pytest.raises(TypeError):
        update_finding(
            seeded_session,
            findings[0],
            direction=Direction.PLUS,
            value=0.08,
            dimension_point=None,
            comment=None,
            zone=None,
            deviation_type=None,
        )
