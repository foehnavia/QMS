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
        )
        other = create_item(
            session,
            item_number="C1-08420B",
            item_type=ref(session, RefItemType, "implant"),
            connection_type=ref(session, RefConnectionType, "C1"),
            size=ref(session, RefSize, "SP"),
        )
        bind(session, item, group.positions[0], "12")
        bind(session, item, group.positions[1], "19")
        bind(session, other, group.positions[0], "77")

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
        characteristic, _ = get_or_create_characteristic(session, other, "77")
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
            characteristic, _ = get_or_create_characteristic(session, item, number)
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
            decision_insp="approved",
            protocol=r"\\srv\qa\SW-2026-14.docx",
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
            text = cell.text() if cell else ""
            if metrics.horizontalAdvance(text) > widest:
                longest, widest = text, metrics.horizontalAdvance(text)
        verdict = "режет" if widest > room else "ok"
        print(
            f"    {label:20} {table.columnWidth(column):4} px  "
            f"место {room:4}  рекорд {widest:4} ({longest[:28]!r})  {verdict}"
        )


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
    widget.grab().save(str(OUT / f"{name}.png"))
    print(f"  {name}.png")


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

    # Лента при минимальной ширине: уходят подписи и правая строка состояния,
    # высота остаётся 44 (решение В-5).
    window.resize(kit.tokens.WINDOW_MIN_WIDTH, kit.tokens.WINDOW_MIN_HEIGHT)
    window.select_section(3)
    shoot(window, "01-section-4b-deviations-1280")
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
    shoot(DecisionDialog(engine, ids["current_id"]), "10-dialog-decision")
    shoot(CardDialog(engine, ids["current_id"]), "11-dialog-card")
    tall_card = CardDialog(engine, ids["current_id"])
    tall_card.resize(kit.tokens.DIALOG_FULL, CARD_TALL)
    shoot(tall_card, "11b-dialog-card-tall")
    shoot(ItemPositionsDialog(engine, ids["item_id"]), "12-dialog-item-positions")

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
