"""Критерий приёмки 5 — сид идемпотентен, `General`-дефолты на месте."""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import GENERAL, REFERENCE_MODELS, RefConnectionType, RefSize
from seed.reference import REFERENCE_SEED, ref, seed_reference


def _counts(session: Session) -> dict[str, int]:
    return {model.__tablename__: session.query(model).count() for model in REFERENCE_MODELS}


def test_seed_fills_the_starting_sets(session: Session) -> None:
    inserted = seed_reference(session)
    session.commit()

    for model, names in REFERENCE_SEED.items():
        assert inserted[model.__tablename__] == len(names)
        assert {row.name for row in session.query(model)} == set(names)


def test_seed_is_idempotent(session: Session) -> None:
    seed_reference(session)
    session.commit()
    before = _counts(session)

    inserted = seed_reference(session)
    session.commit()

    assert _counts(session) == before
    assert set(inserted.values()) == {0}


def test_seed_tops_up_a_partially_filled_reference(session: Session) -> None:
    """Оператор мог завести значение сам — сид досеивает недостающее, не дублируя."""
    session.add(RefSize(name="NP"))
    session.commit()

    inserted = seed_reference(session)
    session.commit()

    assert inserted["ref_size"] == len(REFERENCE_SEED[RefSize]) - 1
    names = [row.name for row in session.query(RefSize)]
    assert len(names) == len(set(names)) == len(REFERENCE_SEED[RefSize])


def test_general_defaults_exist(session: Session) -> None:
    seed_reference(session)
    session.commit()

    assert ref(session, RefConnectionType, GENERAL).name == GENERAL
    assert ref(session, RefSize, GENERAL).name == GENERAL
