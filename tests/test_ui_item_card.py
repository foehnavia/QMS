"""Карточка детали, список её отклонений и запрет правки в строке (наряд 0025).

Колонки адресуются **по имени заголовка** (`CLAUDE.md` §9а): номер сдвигается
вместе с тестом и потому не сторожит ничего — на этом наряд `0024` уже споткнулся.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QAbstractItemView, QMessageBox
from sqlalchemy.orm import Session

from conftest import make_item, rev
from db.models import CharacteristicGroup, GPosition
from db.session import session_scope
from domain.deviations import register
from domain.findings import make_finding
from domain.mappings import bind
from domain.revisions import characteristic_by_number, clone_revision, current_revision
from ui.item_card_dialog import ItemCardDialog
from ui.item_deviations_dialog import ItemDeviationsDialog
from ui.kit import tokens

pytestmark = pytest.mark.usefixtures("qt_app")


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


def _two_revisions(session: Session):
    """Деталь `C1-10375A` с ревизиями `A` и `B`; отклонение записано по `A`."""
    item = make_item(session, "C1-10375A")
    group = CharacteristicGroup(name="CG-A")
    group.positions = [GPosition(g_index=13, nominal=3.75)]
    session.add(group)
    session.flush()

    source = rev(item)
    bind(session, source, group.positions[0], "19")
    deviation = register(
        session, item=item, revision=source, wo="W-REV-A", quantity=3, date=date(2026, 8, 1)
    )
    make_finding(
        session,
        deviation,
        characteristic_by_number(source, "19"),
        direction="+",
        value=0.02,
    )
    clone = clone_revision(session, item, source, designation="B")
    moved = characteristic_by_number(clone, "19")
    moved.local_number = "66"
    session.flush()
    return item.item_id


def _text(cell) -> str:
    return cell.text().replace("⁨", "").replace("⁩", "")


def _column(table, name: str) -> int:
    return next(
        index
        for index in range(table.columnCount())
        if table.horizontalHeaderItem(index).text() == name
    )


# --- §3 карточка -------------------------------------------------------------------


def test_the_card_shows_the_item_and_defaults_to_the_current_revision(engine) -> None:
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)

    assert _text(card.number_label) == "C1-10375A"
    assert card.revision.currentText() == "B (current)"
    # Показаны размеры действующей ревизии: номер переехал на 66.
    assert [
        _text(card.table.item(row, _column(card.table, "Local number")))
        for row in range(card.table.rowCount())
    ] == ["66"]


def test_the_card_table_does_not_edit_on_double_click(engine) -> None:
    """§7: карточка показывает записи, ввод в строке заперт."""
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)

    assert card.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


# --- §4 просмотр и назначение — разные органы --------------------------------------


def test_switching_the_shown_revision_writes_nothing(engine) -> None:
    """Критерий 4: список смотрит. Действующая ревизия от переключения не меняется."""
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)
    card.revision.setCurrentIndex(0)  # показать прежнюю ревизию «A»

    assert card.revision.currentText() == "A"
    assert [
        _text(card.table.item(row, _column(card.table, "Local number")))
        for row in range(card.table.rowCount())
    ] == ["19"], "показ переключился"

    with session_scope(engine) as session:
        from db.models import Item

        assert current_revision(session.get(Item, item_id)).designation == "B"


def test_setting_a_revision_current_needs_confirmation(engine, monkeypatch) -> None:
    """Критерий 5: отказ в диалоге — и в базе ничего не изменилось."""
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)
    card.revision.setCurrentIndex(0)  # «A», не действующая

    asked: list[str] = []

    def refuse(self):
        asked.append(self.informativeText())
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", refuse)
    card.set_as_current()

    assert asked, "смена действующей обязана спрашивать"
    assert "registered against revision A" in asked[0], "последствие названо в окне"
    with session_scope(engine) as session:
        from db.models import Item

        assert current_revision(session.get(Item, item_id)).designation == "B"


def test_confirming_makes_the_revision_current(engine, monkeypatch) -> None:
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)
    card.revision.setCurrentIndex(0)
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes
    )

    card.set_as_current()

    with session_scope(engine) as session:
        from db.models import Item

        assert current_revision(session.get(Item, item_id)).designation == "A"
    # Показ остался на той же ревизии — оператор смотрел именно её.
    assert card.revision.currentText().startswith("A")


def test_the_button_is_dead_on_the_current_revision(engine) -> None:
    """Назначать действующую действующей незачем — кнопка молчит о том, что видно."""
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card = ItemCardDialog(engine, item_id)

    assert card.set_current_button.isEnabled() is False
    card.revision.setCurrentIndex(0)
    assert card.set_current_button.isEnabled() is True


# --- §5 список отклонений детали ----------------------------------------------------


def test_the_item_deviations_list_covers_every_revision(engine) -> None:
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    dialog = ItemDeviationsDialog(engine, item_id)
    revision_column = _column(dialog.table, "Revision")

    assert dialog.table.rowCount() == 1
    assert _text(dialog.table.item(0, revision_column)) == "A"


def test_a_row_from_an_earlier_issue_is_marked(engine) -> None:
    """Пометка выпуска — **только начертание**, и та же, что в прецедентах.

    Прежняя редакция этого теста требовала красного и тем самым закрепляла дефект:
    цвет означает «за номером нет канона», и на колонке ревизии ему делать нечего
    (`Search.md` v1.05).
    """
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    dialog = ItemDeviationsDialog(engine, item_id)
    cell = dialog.table.item(0, _column(dialog.table, "Revision"))

    assert cell.font().bold() is True
    assert cell.foreground().color().name().upper() != tokens.DANGER_TEXT.upper()
    assert "another issue of the drawing" in cell.toolTip()


def test_the_item_deviations_list_has_no_filters(engine) -> None:
    """Фильтров нет намеренно: они часть общей машинерии (часть 2 Q-14, после S6)."""
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    dialog = ItemDeviationsDialog(engine, item_id)

    assert not hasattr(dialog, "filter")
    assert dialog.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


# --- §7 общие таблицы: правка только через форму ------------------------------------


def test_no_list_table_edits_in_place(engine) -> None:
    """Критерий 7: ни одна таблица-список не входит в режим правки.

    Строка там — **чужая запись**, и один промах заменял бы содержимое ячейки
    символом. Правка — явным открытием формы.
    """
    from ui.deviation_view import DeviationView
    from ui.item_positions_dialog import ItemPositionsDialog
    from ui.item_view import ItemView
    from ui.reference_view import ReferenceView

    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    # Владельцы держатся в переменных: возьми только `.table`, и виджет соберёт
    # сборщик мусора, а Qt отдаст «Internal C++ object already deleted».
    screens = {
        "Items": ItemView(engine),
        "Deviations": DeviationView(engine),
        "Item card": ItemCardDialog(engine, item_id),
        "Item deviations": ItemDeviationsDialog(engine, item_id),
        "Item positions": ItemPositionsDialog(engine, item_id),
        "Reference data": ReferenceView(engine),
    }
    tables = {
        name: (screen.values if name == "Reference data" else screen.table)
        for name, screen in screens.items()
    }

    editable = [
        name
        for name, table in tables.items()
        if table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers
    ]
    assert editable == []


def test_the_mapping_dialog_keeps_typing_in_the_row(engine) -> None:
    """Обратная сторона §7: диалог привязки не тронут.

    Набор локального номера прямо в строке там — ратификация S3 (запись по
    действию), и запрет правки в строке на него **не распространяется**: там
    строка это поле ввода, а не чужая запись. Тест сторожит именно это — чтобы
    следующая уборка «редактируемых таблиц» не задела привязку заодно.
    """
    from ui.mapping_dialog import MappingDialog

    with session_scope(engine) as session:
        item_id = _two_revisions(session)
        from db.models import CharacteristicGroup as CG

        cg_id = session.query(CG).one().cg_id

    dialog = MappingDialog(engine, item_id, cg_id)

    assert dialog.table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers


# --- Доводка 0025: пометки различаются свойством, а не функцией ----------------------


def _revision_cell_of_precedent_card(engine, item_id):
    """Ячейка ревизии прецедента в карточке отклонения по новой ревизии."""
    from ui.card_dialog import CardDialog, PRECEDENT_REVISION_COLUMN

    with session_scope(engine) as session:
        from db.models import Item

        item = session.get(Item, item_id)
        clone = current_revision(item)
        fresh = register(
            session, item=item, revision=clone, wo="W-NEW", quantity=1, date=date(2026, 9, 1)
        )
        make_finding(
            session,
            fresh,
            characteristic_by_number(clone, "66"),
            direction="-",
            value=0.01,
        )
        # Прецедент показывается только решённый.
        past = next(d for d in item.deviations if d.wo == "W-REV-A")
        past.decision_dev = "approved"
        past.explanation = "ok"
        session.flush()
        deviation_id = fresh.deviation_id

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    assert card.same_position.rowCount() == 1, "прецедент через ревизию обязан быть"
    return card, card.same_position.item(0, PRECEDENT_REVISION_COLUMN)


def test_the_revision_mark_looks_the_same_on_both_screens(engine) -> None:
    """Один факт — одно оформление. Сравниваются **свойства ячейки**, не снимок.

    Дефект, который этот тест ловит: пометку ставили две разные функции — в
    прецедентах вручную полужирным, в списке отклонений детали через
    `mark_unbound`, то есть красным. Один и тот же факт «строка из прежнего
    выпуска» выглядел на двух экранах по-разному.
    """
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    _card, precedent_cell = _revision_cell_of_precedent_card(engine, item_id)
    listing = ItemDeviationsDialog(engine, item_id)
    listing_cell = listing.table.item(
        next(
            row
            for row in range(listing.table.rowCount())
            if _text(listing.table.item(row, _column(listing.table, "Revision"))) == "A"
        ),
        _column(listing.table, "Revision"),
    )

    assert precedent_cell.font().bold() == listing_cell.font().bold() is True
    assert (
        precedent_cell.foreground().color().name()
        == listing_cell.foreground().color().name()
    )
    assert "another issue of the drawing" in precedent_cell.toolTip()
    assert "another issue of the drawing" in listing_cell.toolTip()


def test_the_revision_column_is_never_red(engine) -> None:
    """Цвет занят смыслом «нет канона» и на колонку ревизии не попадает.

    Проверяется на обоих экранах: разъехаться они могут только порознь.
    """
    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    _card, precedent_cell = _revision_cell_of_precedent_card(engine, item_id)
    listing = ItemDeviationsDialog(engine, item_id)
    listing_cells = [
        listing.table.item(row, _column(listing.table, "Revision"))
        for row in range(listing.table.rowCount())
    ]

    danger = tokens.DANGER_TEXT.upper()
    assert precedent_cell.foreground().color().name().upper() != danger
    assert all(cell.foreground().color().name().upper() != danger for cell in listing_cells)


def test_a_canon_dimension_of_a_past_revision_stays_uncoloured(engine) -> None:
    """Проверка, что прежнее правило не сломалось: канонный размер красным не красится."""
    from ui.card_dialog import PRECEDENT_SIZE_COLUMN

    with session_scope(engine) as session:
        item_id = _two_revisions(session)

    card, _cell = _revision_cell_of_precedent_card(engine, item_id)
    size_cell = card.same_position.item(0, PRECEDENT_SIZE_COLUMN)

    assert size_cell.foreground().color().name().upper() != tokens.DANGER_TEXT.upper()
    assert "!" not in _text(size_cell)
