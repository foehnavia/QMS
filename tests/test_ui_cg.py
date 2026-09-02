"""UI канон-слоя: чертёж, редактор CG, диалог привязки (наряд 0014).

Прежний файл назывался `test_ui_canvas.py` и проверял холст с баллонами. Холста
больше нет (находки №7 и №8 прогона QMS-016): чертёж приходит размеченным, а
позиции ведутся таблицей. Проверки переписаны под это, а не сняты.

Правило проверки то же, что и во всём проекте (`CLAUDE.md` §9): **сверяй то,
чем рисуют**. Про чертёж это значит размер отрисованного pixmap, а не
запрошенный масштаб; про кнопку зума — состояние вида после нажатия, а не
наличие обработчика.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ui.kit
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QDialogButtonBox

from conftest import make_item, make_png
from db.models import CharacteristicGroup, GPosition, Item
from db.session import session_scope
from domain.groups import GPositionSpec, create_group, set_drawing
from domain.mappings import bind, binding_state, mark_absent
from ui.cg_dialog import CgDialog
from ui.cg_editor import CgEditor
from ui.cg_view import CgView
from ui.drawing_view import DrawingPane, DrawingView
from ui.kit import tokens
from ui.mapping_dialog import LOCAL_NUMBER, STATE_LABELS, MappingDialog

pytestmark = pytest.mark.usefixtures("qt_app")

POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0), GPositionSpec(3, 0.5))

#: Область показа для тестов чертежа: размер окна берётся токенами, но здесь
#: важна только пропорция «ширина картинки к ширине области».
VIEW_WIDTH = tokens.DIALOG_FULL
VIEW_HEIGHT = tokens.DIALOG_HEIGHT_MEDIUM


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


@pytest.fixture
def quiet(monkeypatch):
    """Перехват модального сообщения об ошибке.

    Тест, утверждающий, что операция **проходит**, обязан это делать: под
    offscreen непойманный `show_error` не роняет прогон, а вешает его
    (`CLAUDE.md` §9). Возвращает список показанных ошибок — пустой значит
    «диалогов не было».
    """
    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))
    return shown


def _cg_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(CharacteristicGroup).one().cg_id


def _item_id(engine) -> int:
    with session_scope(engine) as session:
        return session.query(Item).one().item_id


def _laid_out(view: DrawingView, width: int = VIEW_WIDTH, height: int = VIEW_HEIGHT) -> DrawingView:
    """Довести раскладку без `show()`: иначе viewport нулевой ширины."""
    view.resize(width, height)
    view.setMinimumSize(width, height)
    return view


def _wheel(view: DrawingView, up: bool, ctrl: bool) -> None:
    point = QPointF(view.viewport().rect().center())
    view.wheelEvent(
        QWheelEvent(
            point,
            view.mapToGlobal(point),
            QPoint(),
            QPoint(0, 120 if up else -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
    )


def _double_click(view: DrawingView) -> None:
    point = QPointF(view.viewport().rect().center())
    view.mouseDoubleClickEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


# --- Чертёж: показ, масштаб, панорамирование ---------------------------------------


def test_drawing_fills_the_width_of_the_area(qt_app) -> None:
    """Критерий 2: чертёж — ширина области минус ~15 %, пропорции целы.

    Считаем **нарисованное**: ширину отрисованного pixmap, а не масштаб, о
    котором виджет отчитался (`CLAUDE.md` §9, обобщение пяти случаев).
    """
    view = _laid_out(DrawingView())
    assert view.set_drawing(make_png(400, 100)) is True

    shown = view.shown_size()
    ratio = shown.width() / view.viewport().width()
    assert 0.80 <= ratio <= 0.90, ratio
    # Пропорции: исходный 400×100 — четыре к одному.
    assert abs(shown.width() / shown.height() - 4) < 0.05


def test_a_taller_drawing_still_fits_by_width(qt_app) -> None:
    """«Вписать по ширине», а не «по области»: высокий чертёж прокручивается."""
    view = _laid_out(DrawingView())
    view.set_drawing(make_png(200, 600))

    shown = view.shown_size()
    assert shown.width() / view.viewport().width() >= 0.80
    # Раз вписывали по ширине, картинка вышла выше области — и это нормально.
    assert shown.height() > view.viewport().height()


def test_ctrl_wheel_zooms_and_a_plain_wheel_does_not(qt_app) -> None:
    """Критерий 2: зум — только с `Ctrl`; колесо само по себе прокручивает."""
    view = _laid_out(DrawingView())
    view.set_drawing(make_png(400, 300))
    fitted = view.shown_size().width()

    _wheel(view, up=True, ctrl=True)
    assert view.shown_size().width() > fitted
    assert view.fitting is False

    zoomed = view.shown_size().width()
    _wheel(view, up=False, ctrl=True)
    assert view.shown_size().width() < zoomed

    unchanged = view.shown_size().width()
    _wheel(view, up=True, ctrl=False)
    assert view.shown_size().width() == unchanged


def test_buttons_zoom_and_double_click_returns_to_fit(qt_app) -> None:
    """Кнопки `+` / `−` / «вписать» и двойной клик — тот же вид, что и колесо."""
    pane = DrawingPane()
    _laid_out(pane.view)
    pane.set_drawing(make_png(400, 300))
    fitted = pane.view.shown_size().width()

    pane.zoom_in_button.click()
    assert pane.view.shown_size().width() > fitted
    assert pane.view.fitting is False

    pane.fit_button.click()
    assert pane.view.fitting is True
    assert pane.view.shown_size().width() == fitted

    pane.zoom_out_button.click()
    assert pane.view.shown_size().width() < fitted

    _double_click(pane.view)
    assert pane.view.fitting is True
    assert pane.view.shown_size().width() == fitted


def test_zoom_stays_between_the_limits(qt_app) -> None:
    view = _laid_out(DrawingView())
    view.set_drawing(make_png(400, 300))

    for _ in range(40):
        view.zoom_in()
    assert view.scale == pytest.approx(tokens.DRAWING_ZOOM_MAX)

    for _ in range(80):
        view.zoom_out()
    assert view.scale == pytest.approx(tokens.DRAWING_ZOOM_MIN)


def test_panning_moves_the_view_when_the_drawing_is_bigger(qt_app) -> None:
    """Критерий 2: увеличенный чертёж таскают мышью, а не полосой прокрутки."""
    view = _laid_out(DrawingView())
    view.set_drawing(make_png(400, 300))
    view.set_scale(view.scale * 4)

    bar = view.horizontalScrollBar()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()

    view.pan_begin(QPoint(200, 200))
    view.pan_to(QPoint(140, 200))  # курсор влево — содержимое уезжает влево
    view.pan_end()

    assert bar.value() > before


def test_a_group_without_a_drawing_shows_a_placeholder_with_a_load_button(qt_app) -> None:
    """Критерий 2: группа без чертежа остаётся рабочей."""
    pane = DrawingPane(editable=True)

    assert pane.stack.currentWidget() is pane.empty
    assert pane.zoom_in_button.isEnabled() is False
    # Выход из пустоты — прямо на месте пустоты (канон §8).
    assert pane.empty.findChildren(type(pane.load_button))

    pane.set_drawing(make_png())
    assert pane.stack.currentWidget() is pane.view
    assert pane.zoom_in_button.isEnabled() is True


def test_a_read_only_pane_offers_no_loading(qt_app) -> None:
    """В привязке чертёж только показывают: группу правит редактор группы."""
    pane = DrawingPane()

    assert pane.load_button is None and pane.remove_button is None


def test_the_pane_reports_a_broken_image(qt_app) -> None:
    pane = DrawingPane()

    assert pane.set_drawing(b"not an image") is False
    assert pane.stack.currentWidget() is pane.empty
    assert pane.set_drawing(make_png()) is True


# --- Баллоны убраны --------------------------------------------------------------


def test_the_balloon_machinery_is_gone_from_the_sources() -> None:
    """Критерий 1: холста нет ни файлом, ни импортом — проверка поиском по `src/`."""
    src = Path(__file__).resolve().parents[1] / "src"

    assert not (src / "ui" / "balloon_canvas.py").exists()
    leaked = {
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "BalloonCanvas" in path.read_text(encoding="utf-8")
        or "balloon_canvas" in path.read_text(encoding="utf-8")
    }
    assert leaked == set()


# --- Редактор CG -----------------------------------------------------------------


def test_editor_loads_group(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))

    assert editor.name_edit.text() == "CG-A"
    assert editor.table.rowCount() == 3
    assert editor.status.text() == "Positions: 3"


def test_editor_saves_geometry_and_name(group_engine) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.name_edit.setText("CG-переименована")
    editor.table.item(0, 1).setText("4,25")  # запятая как разделитель
    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert group.name == "CG-переименована"
        assert next(p for p in group.positions if p.g_index == 1).nominal == 4.25


def test_editor_saves_a_position_without_a_nominal(group_engine, quiet) -> None:
    """Критерий 4: позиция бывает допуском формы — номинала у неё нет.

    Ошибку ввода перехватываем нарочно: без этого «номинал пуст» упало бы не
    провалом, а зависшим модальным окном.
    """
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.add_position()
    editor.table.item(3, 1).setText("")
    editor.table.item(3, 2).setText("0.02")
    editor.table.item(3, 3).setText("−0.02")  # минус канона, U+2212
    editor.save()

    assert quiet == []
    with session_scope(group_engine) as session:
        added = next(
            p for p in session.query(CharacteristicGroup).one().positions if p.g_index == 4
        )
        assert (added.nominal, added.tol_plus, added.tol_minus) == (None, 0.02, -0.02)


def test_editor_writes_no_coordinates(group_engine, quiet) -> None:
    """Критерий 6: ни у новой позиции, ни у отредактированной `x`/`y` не берутся."""
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.add_position()
    editor.table.item(0, 1).setText("4.0")
    editor.save()

    assert quiet == []
    with session_scope(group_engine) as session:
        positions = session.query(GPosition).all()
        assert len(positions) == 4
        assert all((p.x, p.y) == (None, None) for p in positions)


def test_editor_locks_the_index_of_every_position(group_engine) -> None:
    """Ревью S3 п. 1 + ратификация В-8: индекс не вводится руками вообще."""
    editor = CgEditor(group_engine, _cg_id(group_engine))
    assert not editor.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable

    editor.add_position()

    assert not editor.table.item(3, 0).flags() & Qt.ItemFlag.ItemIsEditable
    # Выдан следующий за максимальным, а не занявший дыру.
    assert editor.table.item(3, 0).text() == "4"


def test_editor_ignores_a_forced_index_swap(group_engine) -> None:
    """Тот же пункт со стороны сохранения: перестановка g1↔g2 не доезжает до базы."""
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


def test_editor_refuses_to_remove_a_used_position(group_engine, quiet) -> None:
    """Занятая позиция не удаляется, сообщение с числом ссылок."""
    with session_scope(group_engine) as session:
        item = session.query(Item).one()
        group = session.query(CharacteristicGroup).one()
        bind(session, item, group.positions[0], "12")

    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.table.setCurrentCell(0, 0)
    editor.remove_position()

    assert editor.table.rowCount() == 3
    assert quiet and "g1" in str(quiet[0])


def test_editor_loads_and_drops_a_drawing(group_engine) -> None:
    """Чертёж кладётся в базу и снимается; таблица позиций от этого не зависит."""
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor._drawing, editor._drawing_name, editor._drawing_changed = make_png(30, 20), "cg.png", True
    editor._refresh()
    assert editor.drawing.stack.currentWidget() is editor.drawing.view
    editor.save()

    with session_scope(group_engine) as session:
        group = session.query(CharacteristicGroup).one()
        assert group.drawing is not None and group.drawing_name == "cg.png"

    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.drop_drawing()
    assert editor.drawing.stack.currentWidget() is editor.drawing.empty
    assert editor.table.rowCount() == 3
    editor.save()

    with session_scope(group_engine) as session:
        assert session.query(CharacteristicGroup).one().drawing is None


def test_editor_rejects_a_bad_number(group_engine, quiet) -> None:
    editor = CgEditor(group_engine, _cg_id(group_engine))
    editor.table.item(0, 1).setText("три")
    editor.save()

    assert quiet and "три" in str(quiet[0])


# --- Новая группа: число позиций с чертежа -----------------------------------------


def test_new_group_lays_the_table_out_by_the_number_of_positions(seeded_engine) -> None:
    """Критерий 3: назвали `N` — получили `g1…gN`, индексы подряд."""
    dialog = CgDialog(seeded_engine)
    assert dialog.table.rowCount() == 1

    dialog.count.setValue(5)

    assert dialog.table.rowCount() == 5
    assert [dialog.table.item(row, 0).text() for row in range(5)] == ["1", "2", "3", "4", "5"]


def test_shrinking_the_count_drops_rows_from_the_tail(seeded_engine) -> None:
    dialog = CgDialog(seeded_engine)
    dialog.count.setValue(4)
    dialog.table.item(0, 1).setText("3.75")

    dialog.count.setValue(2)

    assert dialog.table.rowCount() == 2
    # Введённое в оставшихся строках пересборкой не стирается.
    assert dialog.table.item(0, 1).text() == "3.75"


def test_adding_a_row_by_hand_keeps_the_counter_honest(seeded_engine) -> None:
    """Счётчик и таблица отвечают на один вопрос — и обязаны отвечать одинаково."""
    dialog = CgDialog(seeded_engine)
    dialog.count.setValue(3)

    dialog.add_row()
    assert (dialog.table.rowCount(), dialog.count.value()) == (4, 4)

    dialog.table.setCurrentCell(3, 0)
    dialog.drop_row()
    assert (dialog.table.rowCount(), dialog.count.value()) == (3, 3)


def test_new_group_saves_positions_without_geometry(seeded_engine, quiet) -> None:
    """Критерий 4 на входе: `N` позиций заводятся пустыми и это законно."""
    dialog = CgDialog(seeded_engine)
    dialog.name_edit.setText("CG-N")
    dialog.count.setValue(3)
    dialog.save()

    assert quiet == []
    with session_scope(seeded_engine) as session:
        group = session.query(CharacteristicGroup).filter_by(name="CG-N").one()
        assert sorted(p.g_index for p in group.positions) == [1, 2, 3]
        assert all(p.nominal is None and (p.x, p.y) == (None, None) for p in group.positions)


# --- Диалог привязки -------------------------------------------------------------


def test_mapping_dialog_shows_states_and_blocks_save(group_engine) -> None:
    """«Готово» неактивна, пока хоть одна позиция без состояния."""
    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))
    save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)

    assert dialog.table.rowCount() == 3
    assert save.isEnabled() is False
    assert "g1" in dialog.status.text()
    assert dialog.table.item(0, 1).text() == STATE_LABELS["none"] == "undecided"

    # Ревью S3: диалог пишет сразу, откатывать нечего — подписи это признают.
    assert save.text() == "Done"
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == "Close"


def test_mapping_dialog_enables_save_when_every_position_is_decided(group_engine) -> None:
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)
    with session_scope(group_engine) as session:
        item, group = session.get(Item, item_id), session.get(CharacteristicGroup, cg_id)
        bind(session, item, group.positions[0], "12")
        bind(session, item, group.positions[1], "19")
        mark_absent(session, item, group.positions[2])

    dialog = MappingDialog(group_engine, item_id, cg_id)

    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled() is True
    assert [dialog.table.item(row, 1).text() for row in range(3)] == [
        "linked",
        "linked",
        "absent (99)",
    ]
    assert dialog.table.item(0, LOCAL_NUMBER).text() == "12"


def test_mapping_dialog_binds_from_the_row(group_engine, quiet) -> None:
    """Критерий 5: номер вписывается прямо в строку — иного входа больше нет."""
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)
    dialog = MappingDialog(group_engine, item_id, cg_id)

    dialog.table.item(0, LOCAL_NUMBER).setText("12")

    assert quiet == []
    assert dialog.table.item(0, 1).text() == "linked"
    with session_scope(group_engine) as session:
        states = binding_state(
            session, session.get(Item, item_id), session.get(CharacteristicGroup, cg_id)
        )
        assert states[0].state == "linked" and states[0].local_number == "12"


def test_only_the_local_number_is_editable(group_engine) -> None:
    """Индекс, состояние и геометрия канона — не то, что правят в этом окне."""
    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))

    editable = [
        column
        for column in range(dialog.table.columnCount())
        if dialog.table.item(0, column).flags() & Qt.ItemFlag.ItemIsEditable
    ]
    assert editable == [LOCAL_NUMBER]


def test_clearing_the_cell_does_not_clear_the_binding(group_engine, quiet) -> None:
    """Снятие привязки — отдельная кнопка: `Backspace` не должен терять данные."""
    item_id, cg_id = _item_id(group_engine), _cg_id(group_engine)
    dialog = MappingDialog(group_engine, item_id, cg_id)
    dialog.table.item(0, LOCAL_NUMBER).setText("12")

    dialog.table.item(0, LOCAL_NUMBER).setText("")

    assert quiet == []
    assert dialog.table.item(0, LOCAL_NUMBER).text() == "12"
    assert dialog.table.item(0, 1).text() == "linked"


def test_mapping_dialog_marks_absent_and_clears(group_engine, quiet) -> None:
    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))

    dialog.table.setCurrentCell(2, 0)
    dialog.mark_absent()
    assert dialog.table.item(2, 1).text() == "absent (99)"

    dialog.table.setCurrentCell(2, 0)
    dialog.clear_position()
    assert dialog.table.item(2, 1).text() == "undecided"
    assert quiet == []


def test_mapping_dialog_reports_a_refused_rebinding(group_engine, quiet) -> None:
    """«Один индекс = один размер детали» — в обе стороны, и оператор это видит."""
    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))

    dialog.table.item(0, LOCAL_NUMBER).setText("12")
    dialog.table.item(1, LOCAL_NUMBER).setText("12")  # тот же номер на другую позицию

    assert quiet and "g1" in str(quiet[0])
    assert dialog.table.item(1, 1).text() == "undecided"
    assert dialog.table.item(1, LOCAL_NUMBER).text() == ""


def test_mapping_dialog_has_a_public_entry_point(group_engine, monkeypatch) -> None:
    """Критерий 5: на `run()` завязана форма ввода отклонения — сигнатура та же."""
    import inspect

    monkeypatch.setattr(MappingDialog, "exec", lambda self: 1)

    assert MappingDialog.run(group_engine, _item_id(group_engine), _cg_id(group_engine)) is True
    assert list(inspect.signature(MappingDialog.run).parameters) == [
        "engine",
        "item_id",
        "cg_id",
        "parent",
    ]
    # точка вызова задокументирована — S4 должен её найти, а не гадать
    assert "S4" in (MappingDialog.run.__doc__ or "") + (MappingDialog.__doc__ or "")


def test_mapping_shows_the_drawing_of_the_group(group_engine) -> None:
    """Критерий 5: оператор сверяет индекс с выноской, значит чертёж здесь есть."""
    with session_scope(group_engine) as session:
        set_drawing(session, session.query(CharacteristicGroup).one(), make_png(400, 200), "cg.png")

    dialog = MappingDialog(group_engine, _item_id(group_engine), _cg_id(group_engine))
    _laid_out(dialog.drawing.view)

    assert dialog.drawing.stack.currentWidget() is dialog.drawing.view
    assert dialog.drawing.view.shown_size().width() > 0


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


# --- В-6: геометрия канона в диалоге привязки ---------------------------------------


def test_mapping_shows_the_canon_geometry_of_each_position(group_engine) -> None:
    """Привязка — момент, когда оператор решает **по номиналу и допуску** канона."""
    from ui.common import NO_GEOMETRY, strip_iso
    from ui.mapping_dialog import COLUMNS

    item_id = _item_id(group_engine)
    dialog = MappingDialog(group_engine, item_id, _cg_id(group_engine))
    geometry = COLUMNS.index("Canon geometry")

    assert COLUMNS == ("Position", "State", "Local number", "Canon geometry")
    assert strip_iso(dialog.table.item(0, geometry).text()) == "3.75 +0.05 / −0.05"
    # У позиции без допусков остаётся один токен — номинал; пустой части в
    # ячейке нет, а не «+0 / −0», которого в каноне не записано.
    assert strip_iso(dialog.table.item(1, geometry).text()) == "2"

    # Позиция без геометрии вовсе — прочерк: деталь по ней не засеется, и это
    # видно в момент привязки, а не при регистрации отклонения.
    with session_scope(group_engine) as session:
        bare = create_group(session, "CG-BARE", (GPositionSpec(1),))
        bare_id = bare.cg_id
    bare_dialog = MappingDialog(group_engine, item_id, bare_id)
    assert bare_dialog.table.item(0, geometry).text() == NO_GEOMETRY


def test_mapping_reads_the_group_once(group_engine) -> None:
    """Геометрия берётся из той же выборки, что и состояния."""
    from conftest import count_queries

    item_id = _item_id(group_engine)
    with count_queries(group_engine) as statements:
        MappingDialog(group_engine, item_id, _cg_id(group_engine))

    selects = [text for text in statements if text.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 6, selects
