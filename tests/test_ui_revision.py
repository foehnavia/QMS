"""Ревизия на экране: выбор в форме отклонения и две пометки в прецедентах.

Проверяется **отрисованное**, а не запрошенное (`CLAUDE.md` §9, обобщение
QMS-016): пометка ревизии берётся из той же ячейки, которую рисует таблица, а не
из поля строки выдачи, по которому её ставят. Иначе тест был бы зелёным при
неверном экране — ровно тот класс, на котором QMS-016 споткнулся пять раз.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, rev
from db.models import CharacteristicGroup, GPosition
from db.session import session_scope
from domain.deviations import register
from domain.findings import make_finding
from domain.mappings import bind
from domain.revisions import characteristic_by_number, clone_revision
from ui.card_dialog import (
    PRECEDENT_REVISION_COLUMN,
    PRECEDENT_SIZE_COLUMN,
    UNBOUND_MARK,
    CardDialog,
)
from ui.deviation_dialog import DeviationDialog

pytestmark = pytest.mark.usefixtures("qt_app")


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


def _stock(session: Session):
    """Деталь с канонным размером 12, не-канонным 32 и решённым отклонением по обоим."""
    item = make_item(session, "C1-08375A")
    group = CharacteristicGroup(name="CG-A")
    group.positions = [GPosition(g_index=1, nominal=3.75), GPosition(g_index=2, nominal=2.0)]
    session.add(group)
    session.flush()

    source = rev(item)
    bind(session, source, group.positions[0], "12")
    from domain.characteristics import get_or_create_characteristic

    get_or_create_characteristic(session, source, "32")
    session.flush()

    for number, wo in (("12", "W-CANON"), ("32", "W-NONCANON")):
        deviation = register(
            session, item=item, revision=source, wo=wo, quantity=1, date=date(2026, 8, 1)
        )
        make_finding(
            session,
            deviation,
            characteristic_by_number(source, number),
            direction="+",
            value=0.02,
        )
        deviation.decision_dev = "approved"
        deviation.explanation = "ok"
    session.flush()
    return item, source


def _text(cell) -> str:
    """Текст ячейки без изолятов: сравнивается содержимое, а не разметка направления."""
    return cell.text().replace("⁨", "").replace("⁩", "")


def _texts(table, column: int) -> list[str]:
    return [_text(table.item(row, column)) for row in range(table.rowCount())]


def test_the_precedent_table_shows_the_revision_of_every_match(engine) -> None:
    """Колонка ревизии заполнена всегда — и когда ревизия та же, и когда другая."""
    with session_scope(engine) as session:
        item, source = _stock(session)
        clone = clone_revision(session, item, source, designation="B")
        current = register(
            session, item=item, revision=clone, wo="W-NEW", quantity=1, date=date(2026, 8, 2)
        )
        make_finding(
            session,
            current,
            characteristic_by_number(clone, "12"),
            direction="-",
            value=0.01,
        )
        deviation_id = current.deviation_id

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)

    assert _texts(card.same_dimension, PRECEDENT_REVISION_COLUMN) == ["A"]


def test_a_match_from_another_revision_is_marked_never_dropped(engine) -> None:
    """Совпадение через ревизию **не отсеивается** — только помечается."""
    with session_scope(engine) as session:
        item, source = _stock(session)
        clone = clone_revision(session, item, source, designation="B")
        current = register(
            session, item=item, revision=clone, wo="W-NEW", quantity=1, date=date(2026, 8, 2)
        )
        make_finding(
            session, current, characteristic_by_number(clone, "12"), direction="-", value=0.01
        )
        deviation_id = current.deviation_id

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)

    assert card.same_dimension.rowCount() == 1, "прецедент прошлой ревизии обязан остаться"
    cell = card.same_dimension.item(0, PRECEDENT_REVISION_COLUMN)
    # Пометка берётся с самой ячейки: подсказка и начертание — то, что видит глаз.
    assert "another revision" in cell.toolTip()
    assert cell.font().bold() is True


def test_a_non_canon_size_carries_the_warning_sign(engine) -> None:
    """Знак `!` — на размере, за которым не стоит g-позиция."""
    with session_scope(engine) as session:
        item, source = _stock(session)
        current = register(
            session, item=item, revision=source, wo="W-NEW", quantity=1, date=date(2026, 8, 2)
        )
        make_finding(
            session, current, characteristic_by_number(source, "32"), direction="-", value=0.01
        )
        deviation_id = current.deviation_id

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)

    cell = card.same_dimension.item(0, PRECEDENT_SIZE_COLUMN)
    assert UNBOUND_MARK in _text(cell)
    assert "rests on the local number alone" in cell.toolTip()


def test_a_canon_size_in_the_same_revision_carries_no_marks(engine) -> None:
    """Обратная сторона: ни знака, ни пометки ревизии — иначе они ничего не значат."""
    with session_scope(engine) as session:
        item, source = _stock(session)
        current = register(
            session, item=item, revision=source, wo="W-NEW", quantity=1, date=date(2026, 8, 2)
        )
        make_finding(
            session, current, characteristic_by_number(source, "12"), direction="-", value=0.01
        )
        deviation_id = current.deviation_id

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)

    size = card.same_dimension.item(0, PRECEDENT_SIZE_COLUMN)
    revision_cell = card.same_dimension.item(0, PRECEDENT_REVISION_COLUMN)
    assert UNBOUND_MARK not in _text(size)
    assert revision_cell.font().bold() is False
    assert "another revision" not in revision_cell.toolTip()


# --- Форма отклонения ---------------------------------------------------------------


def test_the_form_offers_the_revisions_and_defaults_to_the_current(engine) -> None:
    with session_scope(engine) as session:
        item, source = _stock(session)
        clone_revision(session, item, source, designation="B")

    dialog = DeviationDialog(engine)
    dialog.item.setCurrentText("C1-08375A")

    assert [dialog.revision.itemText(i) for i in range(dialog.revision.count())] == [
        "A",
        "B (current)",
    ]
    assert dialog.revision.currentText() == "B (current)"


def test_changing_the_revision_keeps_the_numbers_the_operator_typed(engine) -> None:
    """Смена ревизии ничего не пересчитывает (ратификация 11).

    Оператор набрал номера с бланка. Подставить вместо них чужие значит потерять
    его работу — меняется только то, против чего номера читаются.
    """
    from ui.finding_dialog import FindingRow

    with session_scope(engine) as session:
        item, source = _stock(session)
        clone_revision(session, item, source, designation="B")

    dialog = DeviationDialog(engine)
    dialog.item.setCurrentText("C1-08375A")
    dialog._rows = [FindingRow(local_number="12", direction="+", value=0.02)]
    dialog._refresh_findings()
    before = [row.local_number for row in dialog._rows]

    dialog.revision.setCurrentIndex(0)  # перевод на прежнюю ревизию «A»

    assert [row.local_number for row in dialog._rows] == before
    assert _text(dialog.findings.item(0, 0)) == "12"
