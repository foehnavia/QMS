"""UI канон-слоя: холст, редактор CG, диалог привязки (критерии 1, 3, 4, 6, 8)."""

from __future__ import annotations

import pytest

import ui.kit
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialogButtonBox

from conftest import make_item, make_png
from db.models import CharacteristicGroup, Item
from db.session import session_scope
from domain.groups import GPositionSpec, create_group, set_drawing
from domain.mappings import bind, binding_state, mark_absent
from ui.balloon_canvas import MODE_EDIT, MODE_SELECT, Balloon, BalloonCanvas
from ui.cg_editor import CgEditor
from ui.cg_view import CgView
from ui.mapping_dialog import MappingDialog

pytestmark = pytest.mark.usefixtures("qt_app")

POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0), GPositionSpec(3, 0.5))


@pytest.fixture
def seeded_engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


@pytest.fixture
def group_engine(seeded_engine):
    """Движок с одной группой из трёх позиций и деталью."""
    with session_scope(seeded_engine) as session:
        create_group(session, "CG-A", POSITIONS)
        make_item(session, "C1-08375A")
    return seeded_engine


def _cg_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(CharacteristicGroup).one().cg_id


def _item_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(Item).one().item_id


def _mouse_event(kind, point: QPointF) -> QMouseEvent:
    return QMouseEvent(
        kind,
        point,
        point,  # globalPos: без него Qt зовёт устаревший конструктор
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _click(canvas: BalloonCanvas, point: QPointF) -> None:
    canvas.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, point))


# --- Холст -----------------------------------------------------------------------


def test_canvas_lays_balloons_in_a_grid_without_a_drawing(qt_app) -> None:
    """Группа без чертежа обязана работать (наряд 0003, п. 3 UI)."""
    canvas = BalloonCanvas(MODE_EDIT)
    canvas.resize(400, 300)
    canvas.set_balloons([Balloon(g_index=i) for i in (1, 2, 3)])

    points = [canvas._point_of(i, b) for i, b in enumerate(canvas.balloons)]
    assert len({(p.x(), p.y()) for p in points}) == 3  # не свалены в одну точку
    rect = canvas.image_rect()
    assert all(rect.contains(p) for p in points)


def test_canvas_normalizes_dragged_coordinates(qt_app) -> None:
    canvas = BalloonCanvas(MODE_EDIT)
    canvas.resize(400, 300)
    canvas.set_balloons([Balloon(g_index=1, x=0.5, y=0.5)])

    moved: list[tuple[int, float, float]] = []
    canvas.balloonMoved.connect(lambda g, x, y: moved.append((g, x, y)))

    centre = canvas._point_of(0, canvas.balloons[0])
    _click(canvas, centre)
    canvas.mouseMoveEvent(
        _mouse_event(QMouseEvent.Type.MouseMove, QPointF(centre.x() + 40, centre.y()))
    )

    assert moved and moved[0][0] == 1
    assert 0.0 <= moved[0][1] <= 1.0 and moved[0][1] > 0.5


def test_coordinates_are_resolution_independent(qt_app) -> None:
    """Критерий 3: при другом размере окна баллон на том же месте чертежа."""
    canvas = BalloonCanvas(MODE_SELECT)
    canvas.set_drawing(make_png(40, 20))
    canvas.set_balloons([Balloon(g_index=1, x=0.25, y=0.75)])

    canvas.resize(400, 300)
    small = canvas._point_of(0, canvas.balloons[0])
    small_rect = canvas.image_rect()
    canvas.resize(900, 700)
    big = canvas._point_of(0, canvas.balloons[0])
    big_rect = canvas.image_rect()

    def relative(point, rect):
        return round((point.x() - rect.left()) / rect.width(), 6), round(
            (point.y() - rect.top()) / rect.height(), 6
        )

    assert relative(small, small_rect) == relative(big, big_rect) == (0.25, 0.75)


def test_canvas_reports_a_broken_image(qt_app) -> None:
    canvas = BalloonCanvas()
    assert canvas.set_drawing(b"not an image") is False
    assert canvas.set_drawing(make_png()) is True


def test_canvas_click_selects_and_signals(qt_app) -> None:
    canvas = BalloonCanvas(MODE_SELECT)
    canvas.resize(400, 300)
    canvas.set_balloons([Balloon(g_index=1, x=0.3, y=0.3), Balloon(g_index=2, x=0.7, y=0.7)])

    clicked: list[int] = []
    canvas.balloonClicked.connect(clicked.append)
    _click(canvas, canvas._point_of(1, canvas.balloons[1]))

    assert clicked == [2]
    assert canvas.selected == 2


# --- Редактор CG -----------------------------------------------------------------


def test_editor_loads_group(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))

    assert editor.name_edit.text() == "CG-A"
    assert editor.table.rowCount() == 3
    assert len(editor.canvas.balloons) == 3


def test_editor_saves_dragged_coordinates(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor._on_moved(2, 0.4, 0.6)
    editor.save()

    with session_scope(group_engine) as session:
        position = next(
            p for p in session.query(CharacteristicGroup).one().positions if p.g_index == 2
        )
        assert (position.x, position.y) == (0.4, 0.6)


def test_editor_saves_geometry_and_name(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.name_edit.setText("CG-переименована")
    editor.table.item(0, 1).setText("4,25")  # запятая как разделитель
    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert group.name == "CG-переименована"
        assert next(p for p in group.positions if p.g_index == 1).nominal == 4.25


def test_editor_locks_the_index_of_every_position(group_engine) -> None:
    """Ревью S3 п. 1 + ратификация В-8: индекс не вводится руками вообще.

    У существующей позиции на него ссылаются привязки всех деталей —
    перенумерация переклеила бы ярлыки под готовыми привязками. У новой
    позиции индекс тоже закрыт: он выдаётся как `max + 1` и не
    переиспользуется, потому что `g5` живёт не только в таблице, но и на
    чертеже и в протоколе контроля (наряд 0010 §10).
    """
    editor = CgEditor(group_engine, _cg_id(group_engine))
    assert not editor.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable

    editor.add_position()

    assert not editor.table.item(3, 0).flags() & Qt.ItemFlag.ItemIsEditable
    # Выдан следующий за максимальным, а не занявший дыру.
    assert editor.table.item(3, 0).text() == "4"


def test_editor_ignores_a_forced_index_swap(group_engine) -> None:
    """Тот же пункт со стороны сохранения: перестановка g1↔g2 не доезжает до базы.

    Раньше форма писала новый индекс прямо в модель и сбрасывала на диск после
    каждой позиции — на промежуточном шаге индекс двоился, и оператор получал
    сырое `UNIQUE constraint failed` вместо человеческого текста.
    """
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.table.item(0, 0).setText("2")  # мимо запрета — прямо в ячейку
    editor.table.item(1, 0).setText("1")

    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert sorted(p.g_index for p in group.positions) == [1, 2, 3]
        assert next(p for p in group.positions if p.g_index == 1).nominal == 3.75


def test_editor_adds_and_removes_positions(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.add_position()
    assert editor.table.rowCount() == 4

    editor.table.setCurrentCell(3, 0)
    editor.remove_position()
    assert editor.table.rowCount() == 3

    editor.add_position()
    editor.save()
    with session_scope(group_engine) as session:
        assert len(session.query(CharacteristicGroup).one().positions) == 4


def test_editor_refuses_to_remove_a_used_position(group_engine, monkeypatch) -> None:
    """Критерий 7: занятая позиция не удаляется, сообщение с числом ссылок."""
    import ui.cg_editor as module

    with session_scope(group_engine) as session:
        item = session.query(Item).one()
        group = session.query(CharacteristicGroup).one()
        bind(session, item, group.positions[0], "12")

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.table.setCurrentCell(0, 0)
    editor.remove_position()

    assert editor.table.rowCount() == 3
    assert shown and "g1" in str(shown[0])


def test_editor_loads_and_drops_a_drawing(group_engine) -> None:
    """Критерий 2: чертёж кладётся в базу и снимается, координаты живут дальше."""
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor._drawing, editor._drawing_name, editor._drawing_changed = make_png(30, 20), "cg.png", True
    editor._on_moved(1, 0.2, 0.3)
    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert group.drawing is not None and group.drawing_name == "cg.png"

    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.drop_drawing()
    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert group.drawing is None
        assert next(p for p in group.positions if p.g_index == 1).x == 0.2


def test_editor_rejects_a_bad_number(group_engine, monkeypatch) -> None:
    import ui.cg_editor as module

    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.table.item(0, 1).setText("три")
    editor.save()

    assert shown and "три" in str(shown[0])


# --- Диалог привязки -------------------------------------------------------------


def test_mapping_dialog_shows_states_and_blocks_save(group_engine) -> None:
    """Критерий 6: «Готово» неактивна, пока хоть один баллон без состояния."""
    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))
    save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)

    assert dialog.table.rowCount() == 3
    assert save.isEnabled() is False
    assert "g1" in dialog.status.text()

    # Ревью S3: диалог пишет сразу, откатывать нечего — подписи это признают.
    assert save.text() == "Done"
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == "Close"


def test_mapping_dialog_enables_save_when_every_balloon_is_decided(group_engine) -> None:
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)
    with session_scope(group_engine) as session:
        item, group = session.get(Item, item_id), session.get(CharacteristicGroup, cg_id)
        bind(session, item, group.positions[0], "12")
        bind(session, item, group.positions[1], "19")
        mark_absent(session, item, group.positions[2])

    dialog = MappingDialog(group_engine, item_id, cg_id)

    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled() is True
    assert [b.state for b in dialog.canvas.balloons] == ["linked", "linked", "absent"]
    assert dialog.canvas.balloons[0].label == "12"


def test_mapping_dialog_binds_through_the_balloon(group_engine, monkeypatch) -> None:
    """Клик по баллону → ввод номера → зелёный (Session-03 §4)."""
    import ui.mapping_dialog as module

    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("12", True)))
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)

    dialog = MappingDialog(group_engine, item_id, cg_id)
    dialog._on_balloon(1)

    assert dialog.canvas.balloons[0].state == "linked"
    assert dialog.canvas.balloons[0].label == "12"
    with session_scope(group_engine) as session:
        states = binding_state(
            session, session.get(Item, item_id), session.get(CharacteristicGroup, cg_id)
        )
        assert states[0].state == "linked"


def test_mapping_dialog_marks_absent_and_clears(group_engine) -> None:
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)
    dialog = MappingDialog(group_engine, item_id, cg_id)

    dialog.table.setCurrentCell(2, 0)
    dialog.mark_absent()
    assert dialog.canvas.balloons[2].state == "absent"

    dialog.clear_position()
    assert dialog.canvas.balloons[2].state == "none"


def test_mapping_dialog_reports_a_refused_rebinding(group_engine, monkeypatch) -> None:
    import ui.mapping_dialog as module

    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("12", True)))
    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))

    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))
    dialog._on_balloon(1)
    dialog._on_balloon(2)  # тот же номер на другую позицию

    assert shown and "g1" in str(shown[0])
    assert dialog.canvas.balloons[1].state == "none"


def test_mapping_dialog_has_a_public_entry_point(group_engine, monkeypatch) -> None:
    """Критерий 8: на `run()` S4 вешает «ранние кнопки» формы отклонения."""
    monkeypatch.setattr(MappingDialog, "exec", lambda self: 1)

    assert MappingDialog.run(group_engine, _item_id(group_engine), _cg_id(group_engine)) is True
    # точка вызова задокументирована — S4 должен её найти, а не гадать
    assert "S4" in (MappingDialog.run.__doc__ or "") + (MappingDialog.__doc__ or "")


# --- Раздел «Группы характеристик» ------------------------------------------------


def test_cg_view_lists_groups(group_engine) -> None:
    view = CgView(group_engine)

    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "CG-A"
    assert view.table.item(0, 1).text() == "3"
    assert view.table.item(0, 2).text() == "—"

    with session_scope(group_engine) as session:
        set_drawing(session, session.query(CharacteristicGroup).one(), make_png(), "cg.png")
    view.reload()
    assert view.table.item(0, 2).text() == "yes"
