"""Снимки всех экранов на нативной платформе — критерий 6 наряда 0011 (QMS-016).

Offscreen для снимков непригоден: база шрифтов пуста, иврит и латиница выходят
«тофу» (`CLAUDE.md` §9). Поэтому платформа нативная, но `show()` не зовём —
раскладку доводит `layout().activate()`, и окна на экран не всплывают.

База — **своя демонстрационная**, в `build/`: ни `app.sqlite` (синтетика S2), ни
`data/qms016.sqlite` (база прогона) не трогаются. Данные — реальные по форме
(ивритские зоны и заключения, номера деталей, WO); собранного документа тут нет
(`CLAUDE.md` §6).

    python tools/screenshots.py

Кладёт PNG в `build/screens/`. Артефакт локальный: `build/` в `.gitignore`,
в волт снимки переносит Cowork (та же схема, что у зеркала концепта, Q-09).
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from db.models import (  # noqa: E402
    Direction,
    RefConnectionType,
    RefDeviationType,
    RefInspectionType,
    RefItemType,
    RefSize,
    RefZone,
)
from db.session import create_db_engine, session_scope  # noqa: E402
from domain.revisions import clone_revision, current_revision
from domain.characteristics import get_or_create_characteristic  # noqa: E402
from domain.deviations import register, set_decision  # noqa: E402
from domain.findings import make_finding  # noqa: E402
from domain.groups import GPositionSpec, create_group, set_drawing  # noqa: E402
from domain.inspections import create_inspection  # noqa: E402
from domain.items import create_item  # noqa: E402
from domain.mappings import bind  # noqa: E402
from domain.reference import ensure_value, list_values  # noqa: E402
from domain.errors import ValidationError  # noqa: E402
from seed.reference import ref, seed_reference  # noqa: E402
from ui import kit  # noqa: E402
from ui.deviation_view import COLUMNS as COLUMNS_FOR_MEASURE  # noqa: E402

OUT = REPO_ROOT / "build" / "screens"
DB = REPO_ROOT / "build" / "screens-demo.sqlite"

#: Снимки **на базе прогона** (наряд 0020 §8.5, критерий 4): демонстрационная
#: короче реальной, и ширины колонок на ней не проверяются. Снимаем не с самого
#: файла оператора, а с его копии: рабочая БД автономна (`CLAUDE.md` §6), и
#: экран, открытый на чтение, всё же держит её движком — копия снимает вопрос
#: целиком. Содержимое побайтно то же, значит и длины значений те же.
RUN_DB = REPO_ROOT / "data" / "qms016.sqlite"
RUN_COPY = REPO_ROOT / "build" / "screens-run.sqlite"

#: Ширина показа списков — вторая, 1280, снимается отдельно (наряд 0010 §8.5).
WIDE = 1920
TALL = 1080

#: Карточка изменяема по высоте (ревью 0011, О-6) — снимаем в двух: в своей
#: и в растянутой, чтобы было видно, что вертикаль достаётся секциям, а не
#: тратится на прокрутку.
CARD_TALL = 1000

TODAY = date.today()
POSITIONS = (
    GPositionSpec(1, 3.75, 0.05, -0.05),
    # **Посадка с натягом: оба предельных отклонения в плюс** (наряд 0015,
    # критерий 6). До правки такая пара выводилась как `+0.05 / −0.02` — поле
    # допуска зеркально; снимок без неё не показывает того, ради чего наряд
    # сделан, потому что на симметричной паре дефект не виден вовсе.
    GPositionSpec(2, 2.0, 0.05, 0.02),
    # Допуск формы: номинала у позиции нет вовсе — на экране это пустая ячейка,
    # и снимок обязан её показывать (наряд 0014, критерий 4).
    GPositionSpec(3, None, 0.10, -0.10),
)


def _drawing_png(width: int = 1400, height: int = 620) -> bytes:
    """Чертёж группы **как он приходит из конструкторского отдела**.

    Не сплошной прямоугольник, как было до наряда 0014: смысл экрана теперь в
    том, что метки `G1…GN` уже стоят на выносках и оператор переносит числа с
    них в таблицу. Снимок, на котором выносок нет, этого не показывает.

    Рисуем `QPainter`, поэтому зовётся **после** создания `QApplication`.
    """
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(kit.tokens.WHITE))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    body = QRectF(width * 0.18, height * 0.30, width * 0.52, height * 0.34)
    painter.setPen(QPen(QColor(kit.tokens.N_700), kit.tokens.SELECTION_BAR_WIDTH))
    painter.setBrush(QColor(kit.tokens.N_50))
    painter.drawRect(body)
    painter.drawEllipse(
        QPointF(body.right(), body.center().y()), height * 0.17, height * 0.17
    )

    # Ось и штриховка резьбы — чтобы картинка читалась как чертёж, а не как
    # прямоугольник: снимок показывают людям, знающим, как выглядит бланк.
    pen = QPen(QColor(kit.tokens.N_400), kit.tokens.BORDER_WIDTH)
    pen.setStyle(Qt.PenStyle.DashDotLine)
    painter.setPen(pen)
    painter.drawLine(
        QPointF(width * 0.10, body.center().y()),
        QPointF(width * 0.86, body.center().y()),
    )

    font = QFont(kit.font_family())
    font.setPixelSize(int(kit.tokens.SIZE_TITLE))
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)

    # Выноска = линия от места на детали к кружку с меткой. Метка — `G1…GN`,
    # ровно те индексы, что стоят в таблице позиций.
    callouts = (
        (QPointF(body.left() + body.width() * 0.18, body.top()), QPointF(width * 0.22, height * 0.12), "G1"),
        (QPointF(body.center().x(), body.bottom()), QPointF(width * 0.46, height * 0.86), "G2"),
        (QPointF(body.right(), body.center().y() - height * 0.14), QPointF(width * 0.84, height * 0.14), "G3"),
    )
    radius = height * 0.05
    for anchor, label_at, label in callouts:
        painter.setPen(QPen(QColor(kit.tokens.N_600), kit.tokens.BORDER_WIDTH))
        painter.drawLine(anchor, label_at)
        painter.setBrush(QColor(kit.tokens.WHITE))
        painter.drawEllipse(label_at, radius, radius)
        painter.setPen(QColor(kit.tokens.N_900))
        painter.drawText(
            QRectF(label_at.x() - radius, label_at.y() - radius, radius * 2, radius * 2),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def build_database():
    """Пересобрать демонстрационную базу с нуля и наполнить её."""
    if DB.exists():
        DB.unlink()
    DB.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{DB.as_posix()}"
    # `migrations/env.py` берёт URL из `default_db_url()`, а не из конфига:
    # без этой строки миграции ушли бы в `app.sqlite`.
    os.environ["QMS_DB_URL"] = url

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_db_engine(url)
    with session_scope(engine) as session:
        seed_reference(session)
        # Справочники — English (решение того же дня). Одно ивритское значение
        # заведено намеренно: оператор может ввести любое, и экран обязан это
        # пережить — на нём и виден RTL-путь делегата.
        for name in ("inner diameter", "thread root", "אזור הברגה"):
            ensure_value(session, RefZone, name)
        ensure_value(session, RefDeviationType, "thread depth")
        # Тип, к которому документа не прилагается вовсе, — повод наряда 0029:
        # часть отклонений решается одним чертежом, и такой вердикт стоит
        # записать прецедентом, хотя протокола к нему нет.
        ensure_value(session, RefInspectionType, "Tolerances review")

        group = create_group(session, "Implant_Con_375_C1", POSITIONS)
        set_drawing(session, group, _drawing_png(), "implant.png")

        # Вторая группа — **без чертежа**: она обязана оставаться рабочей, и
        # снимок пустого состояния показывает, что на месте картинки (наряд
        # 0014, п. 3.1).
        bare = create_group(
            session,
            "Implant_Con_420_SP",
            (GPositionSpec(1, 5.0, 0.05, -0.05), GPositionSpec(2)),
        )

        item = create_item(
            session,
            item_number="C1-08375A",
            item_type=ref(session, RefItemType, "implant"),
            connection_type=ref(session, RefConnectionType, "C1"),
            size=ref(session, RefSize, "NP"),
            revision="A",
        )
        other = create_item(
            session,
            item_number="C1-08420B",
            item_type=ref(session, RefItemType, "implant"),
            connection_type=ref(session, RefConnectionType, "C1"),
            size=ref(session, RefSize, "SP"),
            revision="A",
        )
        # Привязка и размеры принадлежат ревизии (QMS-017).
        item_rev = current_revision(item)
        other_rev = current_revision(other)
        bind(session, item_rev, group.positions[0], "12")
        bind(session, item_rev, group.positions[1], "19")
        bind(session, other_rev, group.positions[0], "77")

        # Регистр значений приводится при сохранении (находка №6), поэтому
        # ищем без учёта регистра — как это делает и `ref`.
        zone = ensure_value(session, RefZone, "thread root")
        kind = ensure_value(session, RefDeviationType, "thread burr")

        # Прецедент — с решением: без решения он в выдачу не попадает.
        past = register(
            session,
            item=other,
            wo="W26007201",
            quantity=40,
            date=TODAY - timedelta(days=21),
            machine="CNC-7",
        )
        characteristic, _ = get_or_create_characteristic(session, other_rev, "77")
        make_finding(
            session,
            past,
            characteristic,
            direction=Direction.MINUS,
            value=0.05,
            dimension_point=3,
            comment='GO לא עובר, פין 3.75 מ"מ',
            zone=zone,
            deviation_type=kind,
        )
        set_decision(
            session,
            past,
            decision="approved",
            explanation='אין השפעה על ההרכבה — נבדק ב-Solidworks assembly, סטייה 0.05 מ"מ',
        )

        current = register(
            session,
            item=item,
            wo="W26007336",
            quantity=12,
            date=TODAY,
            machine="CNC-3",
            ncr="NCR-118",
        )
        for number, value in (("12", 0.08), ("19", 0.03)):
            characteristic, _ = get_or_create_characteristic(session, item_rev, number)
            finding = make_finding(
                session,
                current,
                characteristic,
                direction=Direction.PLUS,
                value=value,
                zone=zone,
                deviation_type=kind,
            )
        create_inspection(
            session,
            finding,
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approval_possible",
            conclusion="Clearance in the assembled state drops by 20 %.",
            protocol=r"\\srv\qa\SW-2026-14.docx",
            no_protocol=False,
        )
        # Второе — без позиции и без вывода: «ещё не разбирали» тоже состояние
        # экрана (`Inspection.md` rev 1.01), и снимок обязан показывать оба.
        create_inspection(
            session,
            finding,
            inspection_type=list_values(session, RefInspectionType)[-1],
            decision_insp=None,
            conclusion=None,
            protocol=r"\\srv\qa\torque-2026-03.docx",
            no_protocol=False,
        )

        ids = dict(
            item_id=item.item_id,
            other_id=other.item_id,
            cg_id=group.cg_id,
            bare_cg_id=bare.cg_id,
            current_id=current.deviation_id,
            past_id=past.deviation_id,
            finding_id=finding.finding_id,
        )
    return engine, url, ids


def measure_columns(table, caption: str) -> None:
    """Напечатать фактическую ширину каждой колонки — замер, а не впечатление.

    Критерий 1 §8.5 требует число по каждой размеченной колонке. Берём его из
    того же места, откуда его берёт отрисовка (`columnWidth`), а не глазами по
    снимку: глаз читает те же пиксели, но с ошибкой в пару штук.
    """
    print(f"  {caption}:")
    metrics = table.fontMetrics()
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        label = item.text() if item else f"#{column}"
        room = table.columnWidth(column) - kit.tokens.PAD_CELL * 2
        longest, widest = "", 0
        for row in range(table.rowCount()):
            cell = table.item(row, column)
            # По **строкам**, а не по всему значению: ячейка списка отклонений
            # многострочна (пилюли находок, список исследований), и замер целой
            # строки объявлял бы обрезку там, где рисуются три строки подряд.
            for text in (cell.text() if cell else "").splitlines() or [""]:
                if metrics.horizontalAdvance(text) > widest:
                    longest, widest = text, metrics.horizontalAdvance(text)
        verdict = "режет" if widest > room else "ok"
        print(
            f"    {label:20} {table.columnWidth(column):4} px  "
            f"место {room:4}  рекорд {widest:4} ({longest[:28]!r})  {verdict}"
        )


def measure_pill_room(table, column: int, caption: str) -> None:
    """Хватает ли колонке места на пилюлю — замер **на нативной платформе**.

    Переехал сюда из `tests/test_ui_kit.py` вместе с наряду `0028` (`CLAUDE.md`
    §9а.8): под offscreen шрифт моноширинный, и та же проверка объявляла
    дефицит там, где на пропорциональном шрифте запас двукратный. Свойство,
    которого нет на платформе прогона, замеряется на той, где оно есть.
    """
    from PySide6.QtGui import QFont, QFontMetrics

    from ui.kit.pills import PILL_CHROME

    font = QFont(table.font())
    font.setPointSizeF(kit.tokens.SIZE_PILL)
    font.setWeight(QFont.Weight(kit.tokens.WEIGHT_PILL))
    metrics = QFontMetrics(font)
    room = table.columnWidth(column) - kit.tokens.PAD_CELL * 2
    print(f"  {caption}: место под пилюлю {room} px")
    for text in ("Approved", "Rejected", "Sorting", "Repair", "Not decided"):
        need = metrics.horizontalAdvance(text) + PILL_CHROME
        verdict = "режет" if need > room else "ok"
        print(f"    {text:14} нужно {need:4} px  {verdict}")


def cell_chrome(table) -> int:
    """Сколько пикселей ячейки **не достаётся тексту** — замером, не константой.

    `CLAUDE.md` §9а.12: объявленная ширина колонки — не нарисованная. Между
    числом, выставленным в `setColumnWidth`, и текстом стоят три слагаемых:
    линия сетки, отступы листа стиля (`QTableView::item { padding: 0 10px }`) и
    собственные поля Qt (`PM_FocusFrameHMargin + 1` с каждой стороны). На этой
    платформе выходит 27; зашивать это число нельзя — на другой оно другое, и
    зашитое врало бы молча.
    """
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    margin = table.style().pixelMetric(
        QStyle.PixelMetric.PM_FocusFrameHMargin, QStyleOptionViewItem(), table
    )
    return 1 + kit.tokens.PAD_CELL * 2 + 2 * (margin + 1)


def measure_grid(view, caption: str) -> int:
    """Сетка уровня отклонения: объявлено · нарисовано · рекорд · вердикт.

    Критерий 1 доводки `0028`. Печатается **здесь, а не в тесте**, по
    `CLAUDE.md` §9а.13: под offscreen шрифт моноширинный, и та же проверка
    краснела бы на верной сетке. Возвращает число обрезанных колонок — ноль и
    есть приёмка.

    Колонки, которые рисует делегат, считаются **по тому, чем рисуют**: пилюля
    исхода — своим шрифтом с оправой, пилюли находок — своим и с мензуркой.
    Замер по тексту ячейки у них молчал бы (§8 наряда 0020).
    """
    from PySide6.QtGui import QFont, QFontMetrics

    from ui.deviation_view import COLUMNS
    from ui.kit.chips import CHIPS_ROLE, CHIPS_SHOWN
    from ui.kit.pills import PILL_CHROME

    table = view.table
    chrome = cell_chrome(table)
    metrics = table.fontMetrics()

    pill_font = QFont(table.font())
    pill_font.setPointSizeF(kit.tokens.SIZE_PILL)
    pill_font.setWeight(QFont.Weight(kit.tokens.WEIGHT_PILL))
    pill_metrics = QFontMetrics(pill_font)

    chip_font = QFont(table.font())
    chip_font.setPointSizeF(kit.tokens.SIZE_PILL)
    chip_metrics = QFontMetrics(chip_font)

    print(f"  {caption} (непечатаемое в ячейке: {chrome} px):")
    print(
        f"    {'колонка':14} {'объявл':>7} {'рисует':>7} {'рекорд':>7}  вердикт   значение"
    )
    print("    (у `Explanation` «рисует» — площадь двух строк: ячейка двухстрочная)")
    clipped = 0
    for column, name in enumerate(COLUMNS):
        if table.isColumnHidden(column):
            print(f"    {name or '(раскрытие)':14} {'—':>7} {'—':>7} {'—':>7}  снята")
            continue
        declared = table.columnWidth(column)
        room, widest, longest = declared - chrome, 0, ""

        if name == "Findings":
            # Делегат отступает `PAD_CELL` от обоих краёв ячейки; сама пилюля
            # несёт свои отступы и место под мензурку.
            room = declared - 1 - kit.tokens.PAD_CELL * 2
            for row in range(table.rowCount()):
                cell = table.item(row, column)
                for chip in (cell.data(CHIPS_ROLE) or [])[:CHIPS_SHOWN] if cell else []:
                    need = chip_metrics.horizontalAdvance(chip.text()) + kit.tokens.PAD_CELL * 2
                    if chip.researched:
                        need += kit.tokens.CHIP_GLYPH_SIZE + kit.tokens.GAP_PILL_ICON
                    if need > widest:
                        widest, longest = need, chip.text()
        elif name == "Decision":
            room = declared - 1 - kit.tokens.PAD_CELL * 2
            for row in range(table.rowCount()):
                cell = table.item(row, column)
                text = cell.text() if cell else ""
                need = pill_metrics.horizontalAdvance(text) + PILL_CHROME
                if need > widest:
                    widest, longest = need, text
        elif name == "":
            print(f"    {'(раскрытие)':14} {declared:7} {'—':>7} {'—':>7}  рисует делегат")
            continue
        else:
            for row in range(table.rowCount()):
                cell = table.item(row, column)
                for line in (cell.text() if cell else "").splitlines() or [""]:
                    need = metrics.horizontalAdvance(line)
                    if need > widest:
                        widest, longest = need, line
            header = metrics.horizontalAdvance(name)
            if header > widest:
                widest, longest = header, f"заголовок {name}"

        # Обоснование — единственная двухстрочная ячейка экрана (канва §1), и
        # места у неё вдвое. Считать её по одной строке значило бы объявлять
        # обрезку там, где текст читается целиком, — тот же класс ошибки, что
        # замер целой многострочной ячейки вместо её строк.
        lines = 2 if name == "Explanation" else 1
        room *= lines
        verdict = "РЕЖЕТ" if widest > room else "ok"
        clipped += 1 if widest > room else 0
        print(
            f"    {name:14} {declared:7} {room:7} {widest:7}  {verdict:8}  {longest[:34]!r}"
        )
    total = sum(
        table.columnWidth(column)
        for column in range(table.columnCount())
        if not table.isColumnHidden(column)
    )
    print(f"    {'ИТОГО':14} {total:7}  предел {kit.table_limit(view.window().width())}")
    return clipped


def shoot_on_run_database() -> int:
    """Снять четыре раздела на копии базы прогона и замерить ширины (§8.5).

    Диалоги сюда не берём: они открываются по идентификаторам, а идентичность
    записей у оператора своя. Размеченные оператором колонки все живут на этих
    четырёх экранах.
    """
    import shutil  # noqa: PLC0415

    if not RUN_DB.exists():
        print(f"База прогона не найдена: {RUN_DB}")
        return 1
    RUN_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUN_DB, RUN_COPY)

    app = QApplication.instance() or QApplication([])
    kit.apply_theme(app)
    engine = create_db_engine(f"sqlite:///{RUN_COPY.as_posix()}")

    from ui.main_window import MainWindow  # noqa: PLC0415

    window = MainWindow(engine)
    window.resize(WIDE, TALL)
    print(f"Database: {RUN_COPY} (копия {RUN_DB.name})")
    print("Screens:")
    sections = ("reference-data", "characteristic-groups", "items", "deviations")
    for row, name in enumerate(sections):
        window.select_section(row)
        shoot(window, f"run-{row + 1}-{name}")
    # Карточки отклонений базы прогона — на них и проверяются уровни поиска
    # (наряд 0022 §5): что даёт точный уровень и что стоит на месте снятого
    # описательного. Идентичность записей у оператора своя, поэтому берём все,
    # какие есть, а не заранее известные номера.
    from db.models import Deviation  # noqa: PLC0415
    from db.session import session_scope  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    from ui.card_dialog import CardDialog  # noqa: PLC0415

    with session_scope(engine) as session:
        cards = [
            (row.deviation_id, row.dev_number)
            for row in session.execute(
                select(Deviation.deviation_id, Deviation.dev_number).order_by(
                    Deviation.dev_number
                )
            )
        ]
    print("Cards:")
    for deviation_id, number in cards:
        card = CardDialog(engine, deviation_id)
        card.resize(kit.tokens.DIALOG_FULL, CARD_TALL)
        shoot(card, f"run-card-{number}")
        # Вторая вкладка — то место, где раньше стояла автоматическая выдача.
        # Снимаем её отдельно: на снимке первой вкладки видно только подпись.
        card.tabs.setCurrentIndex(1)
        shoot(card, f"run-card-{number}-descriptive")
        card.tabs.setCurrentIndex(0)
        measure_columns(card.findings, f"card {number} · findings")
        print(
            f"    {number}: exact rows "
            f"{card.same_dimension.rowCount()} + {card.same_position.rowCount()}"
            f" · {card.status.text()}"
        )

    print("Column widths:")
    for row, name in enumerate(sections):
        window.select_section(row)
        section = window.pages.currentWidget()
        # Экран справочников зовёт свою таблицу `values` — она там не одна из
        # многих, а сам список значений; остальные три зовут `table`.
        table = getattr(section, "table", None) or getattr(section, "values", None)
        if table is not None:
            measure_columns(table, name)
    engine.dispose()
    print(f"-> {OUT}")
    return 0


def shoot(widget: QWidget, name: str) -> None:
    """Снять виджет без `show()`: раскладку доводит `activate()` и досыл размера.

    Одного `activate()` мало: разделитель (`QSplitter`) раскладывает своих детей
    в `resizeEvent`, а скрытому виджету Qt его не шлёт. Из-за этого таблица
    внутри разделителя оставалась при своей стартовой ширине, и центрирование
    считалось не от той (наряд 0020 §3.1). Досылаем событие сами — тот же приём,
    что в `drawing_view`.

    Досыла тоже мало для **вложенной** таблицы: шапку `QHeaderView` раскладывает
    отложенно, и панель находок раскрытой строки (наряд 0028) выходила на снимке
    с шапкой в две подписи из восьми — при том что на живом экране она верна.
    Поэтому очередь событий прокручивается перед захватом: снимок обязан
    показывать то, что увидит оператор, а не промежуточное состояние раскладки.
    """
    from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

    OUT.mkdir(parents=True, exist_ok=True)
    layout = widget.layout()
    if layout is not None:
        layout.activate()
    size = QWidget.size(widget)
    QApplication.sendEvent(widget, QResizeEvent(size, size))
    if layout is not None:
        layout.activate()
    QApplication.processEvents()
    widget.grab().save(str(OUT / f"{name}.png"))
    print(f"  {name}.png")


def build_cross_revision_scenario(engine) -> dict:
    """Сценарий наряда 0025: номер размера переехал между ревизиями.

    Деталь `C1-10375A`, канон-позиция `g13`. Ревизия `A` зовёт этот размер
    `19` и несёт по нему решённое отклонение; ревизия `B` зовёт его `66`.
    Прецедент обязан быть виден из карточки нового отклонения — секцией по
    канону, потому что секция по номеру его не найдёт.
    """
    from datetime import timedelta  # noqa: PLC0415

    from domain.deviations import register, set_decision  # noqa: PLC0415
    from domain.findings import make_finding  # noqa: PLC0415
    from domain.groups import GPositionSpec, create_group  # noqa: PLC0415
    from domain.items import create_item  # noqa: PLC0415
    from domain.mappings import bind  # noqa: PLC0415
    from domain.revisions import characteristic_by_number  # noqa: PLC0415

    with session_scope(engine) as session:
        group = create_group(
            session,
            "Implant_Con_375_C1_g13",
            (GPositionSpec(13, 3.75, 0.05, -0.05),),
        )
        item = create_item(
            session,
            item_number="C1-10375A",
            item_type=ref(session, RefItemType, "implant"),
            connection_type=ref(session, RefConnectionType, "C1"),
            size=ref(session, RefSize, "NP"),
            revision="A",
        )
        source = current_revision(item)
        bind(session, source, group.positions[0], "19")

        past = register(
            session,
            item=item,
            revision=source,
            wo="W26007301",
            quantity=25,
            date=TODAY - timedelta(days=30),
            machine="CNC-3",
        )
        make_finding(
            session,
            past,
            characteristic_by_number(source, "19"),
            direction=Direction.MINUS,
            value=0.03,
        )
        set_decision(
            session,
            past,
            decision="approved",
            explanation=(
                "Within functional limits; the thread engages to full depth."
            ),
        )

        # Перевыпуск: номер того же конструктивного места переехал 19 -> 66.
        clone = clone_revision(session, item, source, designation="B")
        moved = characteristic_by_number(clone, "19")
        moved.local_number = "66"
        session.flush()

        fresh = register(
            session,
            item=item,
            revision=clone,
            wo="W26007455",
            quantity=14,
            date=TODAY - timedelta(days=1),
            machine="CNC-3",
        )
        make_finding(
            session,
            fresh,
            characteristic_by_number(clone, "66"),
            direction=Direction.MINUS,
            value=0.04,
        )
        return {"item_id": item.item_id, "deviation_id": fresh.deviation_id}


def build_revision_scenario(engine, ids) -> dict:
    """Довести демо-базу до состояния «вторая ревизия и прецедент через неё».

    Клонируем ревизию детали `C1-08375A`, двигаем один номер (12 → 13) — это
    массовый случай перевыпуска, — и регистрируем по новой ревизии отклонение
    на том же канонном месте. В карточке этого отклонения обязаны быть обе
    пометки: строка прошлой ревизии и знак `!` на не-канонном размере.
    """
    from datetime import timedelta  # noqa: PLC0415

    from db.models import Item  # noqa: PLC0415
    from domain.characteristics import get_or_create_characteristic  # noqa: PLC0415
    from domain.deviations import register, set_decision  # noqa: PLC0415
    from domain.findings import make_finding  # noqa: PLC0415
    from domain.revisions import characteristic_by_number  # noqa: PLC0415

    with session_scope(engine) as session:
        item = session.get(Item, ids["item_id"])
        source = current_revision(item)

        # Решённое отклонение на **не-канонном** размере прежней ревизии: без него
        # знак `!` показать не на чем — у не-канонного размера прецедент берётся
        # прямым путём, а прямой путь показывает только решённое.
        legacy = register(
            session,
            item=item,
            revision=source,
            wo="W26007188",
            quantity=8,
            date=TODAY - timedelta(days=40),
            machine="CNC-2",
        )
        old_noncanon, _ = get_or_create_characteristic(session, source, "41")
        make_finding(
            session,
            legacy,
            old_noncanon,
            direction=Direction.PLUS,
            value=0.06,
        )
        set_decision(
            session,
            legacy,
            decision="repair",
            explanation="Reworked in place; the shoulder was filed back to print.",
        )

        clone = clone_revision(session, item, source, designation="B")

        moved = characteristic_by_number(clone, "12")
        moved.local_number = "13"
        # Размер 41 приехал клоном: за ним нет g-позиции, и в выдаче он обязан
        # получить знак `!` — совпадение держится на одном номере.
        session.flush()

        fresh = register(
            session,
            item=item,
            revision=clone,
            wo="W26007412",
            quantity=12,
            date=TODAY - timedelta(days=2),
            machine="CNC-4",
        )
        make_finding(
            session,
            fresh,
            characteristic_by_number(clone, "13"),
            direction=Direction.MINUS,
            value=0.04,
        )
        make_finding(
            session,
            fresh,
            characteristic_by_number(clone, "41"),
            direction=Direction.PLUS,
            value=0.03,
        )
        return {"new_deviation_id": fresh.deviation_id, "clone_id": clone.revision_id}


def main() -> int:
    # Приложение поднимаем **до** базы: демонстрационный чертёж рисует
    # `QPainter`, а он без `QApplication` не живёт.
    app = QApplication.instance() or QApplication([])
    # Одевание — то же, что в боевом запуске: снимок без темы показывал бы не
    # приложение, а виджеты Windows (наряд 0011).
    kit.apply_theme(app)
    engine, url, ids = build_database()

    from ui.card_dialog import CardDialog
    from ui.cg_dialog import CgDialog
    from ui.cg_editor import CgEditor
    from ui.decision_dialog import DecisionDialog
    from ui.deviation_dialog import DeviationDialog
    from ui.finding_dialog import FindingDialog
    from ui.inspection_dialog import InspectionDialog
    from ui.item_dialog import ItemDialog
    from ui.item_positions_dialog import ItemPositionsDialog
    from ui.main_window import MainWindow
    from ui.mapping_dialog import MappingDialog

    print(f"Database: {url}")
    print("Screens:")

    # --- 1. шасси: лента навигации и четыре раздела ---
    window = MainWindow(engine)
    window.resize(WIDE, TALL)
    for row, name in enumerate(
        ("reference-data", "characteristic-groups", "items", "deviations")
    ):
        window.select_section(row)
        shoot(window, f"01-section-{row + 1}-{name}")

    # Раскрытие строки (наряд 0028): панель находок со своей шапкой, колонка
    # `Research` и список исследований. Снимается **раскрытым**: свёрнутый экран
    # показывает только пилюли, а панель — половина того, что делает наряд.
    window.select_section(3)
    deviations = window.deviation_view
    for row in range(deviations.table.rowCount()):
        if not deviations.is_panel_row(row):
            deviations.toggle_expansion(row)
            break
    window.layout().activate()
    shoot(window, "21-deviations-expanded")
    for row in range(deviations.table.rowCount()):
        panel = deviations.panel_at(row)
        if panel is not None:
            measure_columns(panel, "Deviations, уровень находки")
            break

    # Замер сетки — критерий 1 доводки: на **обеих** ширинах, и ни одно значение
    # не обрезано. Печатается здесь, а не в тесте (`CLAUDE.md` §9а.13).
    print("Deviations grid:")
    clipped = measure_grid(deviations, f"уровень отклонения при {WIDE}")

    # Лента при минимальной ширине: уходят подписи и правая строка состояния,
    # высота остаётся 44 (решение В-5).
    window.resize(kit.tokens.WINDOW_MIN_WIDTH, kit.tokens.WINDOW_MIN_HEIGHT)
    window.select_section(3)
    window.layout().activate()
    QApplication.processEvents()
    shoot(window, "01-section-4b-deviations-1280")
    clipped += measure_grid(
        deviations, f"уровень отклонения при {kit.tokens.WINDOW_MIN_WIDTH}"
    )
    measure_pill_room(deviations.table, COLUMNS_FOR_MEASURE.index("Decision"), "Decision")
    print(f"  обрезанных колонок: {clipped}" + ("" if clipped == 0 else "  <-- РАСХОЖДЕНИЕ"))
    window.resize(WIDE, TALL)

    # Отдельно — ивритский справочник: делегат разворачивает строку списка по
    # её содержимому, шасси остаётся LTR (наряд 0007, §4а).
    window.select_section(0)
    lists = window.reference_view.lists
    zone_index = next(
        index for index in range(lists.count()) if lists.item(index).text() == "Zone"
    )
    lists.setCurrentRow(zone_index)
    shoot(window, "01-section-1b-reference-zone")

    # --- 2…14. диалоги ---
    shoot(ItemDialog(engine), "02-dialog-item")
    shoot(CgDialog(engine), "03-dialog-cg-new")
    shoot(CgEditor(engine, ids["cg_id"]), "04-dialog-cg-editor")
    shoot(CgEditor(engine, ids["bare_cg_id"]), "04b-dialog-cg-editor-no-drawing")
    shoot(MappingDialog(engine, ids["other_id"], ids["cg_id"]), "05-dialog-mapping")
    shoot(DeviationDialog(engine, ids["current_id"]), "06-dialog-deviation-edit")
    shoot(DeviationDialog(engine), "07-dialog-deviation-new")
    shoot(FindingDialog(engine, ids["item_id"]), "08-dialog-finding")
    shoot(InspectionDialog(engine, ids["finding_id"]), "09-dialog-inspection")
    # Форма исследования **без протокола** (наряд 0029, критерий 7): галочка
    # отмечена, поле пути погашено и пусто, подпись вывода несёт признак
    # обязательности. Свёрнутый снимок 09 показывает обычный случай, этот —
    # тот, ради которого наряд и сделан.
    without = InspectionDialog(engine, ids["finding_id"])
    without.kind.setCurrentText("Tolerances review")
    without.verdict.set_value("approval_not_possible")
    without.conclusion.setPlainText(
        "OD 10.0 vs ID 9.9 — no mating clearance, geometry excludes assembly"
    )
    without.no_protocol.setChecked(True)
    shoot(without, "22-dialog-inspection-no-protocol")

    shoot(DecisionDialog(engine, ids["current_id"]), "10-dialog-decision")
    shoot(CardDialog(engine, ids["current_id"]), "11-dialog-card")
    # Карточка с выбранной находкой, у которой исследования есть: при пустом
    # выборе секция показывает одно объяснение, и на нём не видно ни подписей
    # позиции, ни обрезки вывода (наряд 0027 §3).
    card_with_inspections = CardDialog(engine, ids["current_id"])
    card_with_inspections.findings.setCurrentCell(1, 0)
    shoot(card_with_inspections, "11c-card-inspections")

    tall_card = CardDialog(engine, ids["current_id"])
    tall_card.resize(kit.tokens.DIALOG_FULL, CARD_TALL)
    shoot(tall_card, "11b-dialog-card-tall")
    shoot(ItemPositionsDialog(engine, ids["item_id"]), "12-dialog-item-positions")

    # --- 19. Ревизия чертежа: сценарий приёмки наряда 0024 (QMS-017) ---
    #
    # Снимается ровно тот путь, который просит критерий 4: деталь с ревизией →
    # отклонение по ней → клон ревизии с правкой одного номера → отклонение по
    # новой → карточка, где видны обе пометки. Состояние строится здесь, а не в
    # `build_database`: остальные снимки не обязаны нести вторую ревизию.
    revision_ids = build_revision_scenario(engine, ids)

    item_form = ItemDialog(engine)
    item_form.number_edit.setText("C1-08512C")
    item_form.revision_edit.setText("C")
    shoot(item_form, "19-dialog-item-revision")

    window.select_section(2)
    shoot(window, "19b-items-with-revision-column")

    form = DeviationDialog(engine)
    form.item.setCurrentText("C1-08375A")
    shoot(form, "19c-dialog-deviation-revision-picker")

    # --- 20. Сценарий наряда 0025: канон через ревизии своей детали ---
    #
    # Тот самый случай, на котором дефект найден прогоном: у `C1-10375A` позиция
    # `g13` в ревизии `A` привязана к номеру `19`, в `B` — к `66`. До правки §1
    # прецедент не показывался нигде.
    cross_ids = build_cross_revision_scenario(engine)

    from ui.item_card_dialog import ItemCardDialog  # noqa: PLC0415
    from ui.item_deviations_dialog import ItemDeviationsDialog  # noqa: PLC0415

    item_card = ItemCardDialog(engine, cross_ids["item_id"])
    shoot(item_card, "20-dialog-item-card")

    shoot(
        ItemDeviationsDialog(engine, cross_ids["item_id"]),
        "20b-dialog-item-deviations",
    )

    cross_card = CardDialog(engine, cross_ids["deviation_id"])
    cross_card.findings.setCurrentCell(0, 0)
    cross_card.resize(kit.tokens.DIALOG_FULL, CARD_TALL)
    shoot(cross_card, "20c-card-canon-across-revisions")

    window.select_section(3)
    shoot(window, "20d-deviations-with-revision-column")

    card = CardDialog(engine, revision_ids["new_deviation_id"])
    # Вторая находка — не-канонный размер 41: на ней видны **обе** пометки разом,
    # строка прошлой ревизии и знак `!`.
    card.findings.setCurrentCell(1, 0)
    card.resize(kit.tokens.DIALOG_FULL, CARD_TALL)
    shoot(card, "19d-card-revision-marks")

    # --- 15. модальное сообщение об ошибке ---
    # Собираем, но не показываем: показанный модальный диалог ждёт ответа и
    # снимку не даётся (`kit.error_box` для того и отделён от `show_error`).
    shoot(
        kit.error_box(
            None,
            ValidationError(
                "Approval requires an explanation: the text goes into אישור חריגה."
            ),
            title="Decision not saved",
        ),
        "15-dialog-error",
    )

    # --- 18. поле с отбором: набранная подстрока и суженный список ---
    # Всплывающий список — отдельное окно, и в снимок формы он не попадает.
    # Собираем кадр сами: строка и список снимаются порознь и склеиваются, —
    # показывать окно на экране ради снимка нельзя (`CLAUDE.md` §9).
    from PySide6.QtGui import QPainter, QPixmap  # noqa: PLC0415

    field = kit.FilterCombo("— pick an item —")
    field.set_rows(
        [
            (1, "C1-08375A"),
            (2, "MF5-10375A-N"),
            (3, "C1-08420B"),
            (4, "MT-SD1037A"),
        ]
    )
    field.resize(kit.tokens.DIALOG_NARROW, kit.tokens.INPUT_HEIGHT)
    field.layout().activate()
    # Кадр снимается **после второго символа** (§8.5.2): именно до этого
    # состояния дефект второй доводки не доживал — со второй буквы поле
    # переставало отвечать вовсе.
    field.lineEdit().setText("10")
    field.filter_to("10")

    popup = field.popup()
    popup.resize(
        field.width(),
        popup.count() * (popup.sizeHintForRow(0) or kit.tokens.TABLE_ROW_HEIGHT)
        + popup.frameWidth() * 2,
    )

    line_shot = field.grab()
    list_shot = popup.grab()
    frame = QPixmap(field.width(), line_shot.height() + list_shot.height())
    frame.fill(kit.tokens.WHITE)
    painter = QPainter(frame)
    painter.drawPixmap(0, 0, line_shot)
    painter.drawPixmap(0, line_shot.height(), list_shot)
    painter.end()
    OUT.mkdir(parents=True, exist_ok=True)
    frame.save(str(OUT / "18-filter-field.png"))
    print("  18-filter-field.png")

    # --- 17. стенд индикатора: два состояния одного элемента рядом ---
    # Своим снимком, потому что на экранах умолчаний нет: по канону В-9
    # радиокнопка стартует невыбранной, и отмеченного состояния снимок экрана
    # не показывает вовсе. А проверять §3.6 нужно именно его.
    from PySide6.QtWidgets import QRadioButton, QVBoxLayout  # noqa: PLC0415

    stand = QWidget()
    stand_layout = QVBoxLayout(stand)
    checked = QRadioButton("checked — filled circle")
    unchecked = QRadioButton("unchecked — empty circle")
    stand_layout.addWidget(checked)
    stand_layout.addWidget(unchecked)
    stand.resize(kit.tokens.DIALOG_NARROW, kit.tokens.RIBBON_HEIGHT * 2)
    checked.setChecked(True)
    shoot(stand, "17-radio-indicator")

    # --- 16. пикер: тот же диалог в обоих состояниях строки отбора ---
    short = [(index, f"C1-0837{index}A") for index in range(4)]
    long = [(index, f"MF5-1037{index:02d}A-N") for index in range(30)]
    shoot(kit.PickerDialog("Pick an item", "Item:", short), "16-picker-short")
    picker = kit.PickerDialog("Pick an item", "Item:", long)
    picker.filter.setText("103710")
    shoot(picker, "16-picker-filtered")

    engine.dispose()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    if "--run-db" in sys.argv:
        raise SystemExit(shoot_on_run_database())
    raise SystemExit(main())
