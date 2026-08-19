"""Снимки всех экранов на нативной платформе — критерий 3 наряда 0007 (QMS-016).

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
import struct
import sys
import zlib
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
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
from domain.reference import add_value, list_values  # noqa: E402
from seed.reference import ref, seed_reference  # noqa: E402
from ui.common import LTR  # noqa: E402

OUT = REPO_ROOT / "build" / "screens"
DB = REPO_ROOT / "build" / "screens-demo.sqlite"

TODAY = date.today()
POSITIONS = (
    GPositionSpec(1, 3.75, 0.05, -0.05, 0.30, 0.35),
    GPositionSpec(2, 2.0, 0.02, -0.02, 0.55, 0.45),
    GPositionSpec(3, 11.5, 0.10, -0.10, 0.72, 0.62),
)


def _png(width: int = 480, height: int = 320) -> bytes:
    """Заглушка чертежа: настоящий PNG без внешних файлов."""
    rows = b"".join(
        bytes([0]) + bytes([40, 44, 52] * width) for _ in range(height)
    )

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    return (
        bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


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
            add_value(session, RefZone, name)
        add_value(session, RefDeviationType, "thread depth")

        group = create_group(session, "Implant_Con_375_C1", POSITIONS)
        set_drawing(session, group, _png(), "implant.png")

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

        zone = [v for v in list_values(session, RefZone) if v.name == "thread root"][0]
        kind = [
            v for v in list_values(session, RefDeviationType) if v.name == "thread burr"
        ][0]

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
            current_id=current.deviation_id,
            past_id=past.deviation_id,
            finding_id=finding.finding_id,
        )
    return engine, url, ids


def shoot(widget: QWidget, name: str) -> None:
    """Снять виджет без `show()`: раскладку доводит `activate()`."""
    OUT.mkdir(parents=True, exist_ok=True)
    layout = widget.layout()
    if layout is not None:
        layout.activate()
    widget.grab().save(str(OUT / f"{name}.png"))
    print(f"  {name}.png")


def main() -> int:
    engine, url, ids = build_database()
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(LTR)  # шасси LTR, как в боевом запуске

    from ui.card_dialog import CardDialog
    from ui.cg_dialog import CgDialog
    from ui.cg_editor import CgEditor
    from ui.decision_dialog import DecisionDialog
    from ui.deviation_dialog import DeviationDialog
    from ui.finding_dialog import FindingDialog
    from ui.inspection_dialog import InspectionDialog
    from ui.item_dialog import ItemDialog
    from ui.main_window import MainWindow
    from ui.mapping_dialog import MappingDialog

    print(f"Database: {url}")
    print("Screens:")

    window = MainWindow(engine)
    window.resize(1200, 700)
    for row, name in enumerate(
        ("reference-data", "characteristic-groups", "items", "deviations")
    ):
        window.sections.setCurrentRow(row)
        shoot(window, f"01-section-{row + 1}-{name}")

    # Отдельно — ивритский справочник: делегат разворачивает строку списка по
    # её содержимому, шасси остаётся LTR (наряд 0007, §4а).
    window.sections.setCurrentRow(0)
    zone_index = next(
        index
        for index in range(window.reference_view.picker.count())
        if window.reference_view.picker.itemText(index) == "Zone"
    )
    window.reference_view.picker.setCurrentIndex(zone_index)
    shoot(window, "01-section-1b-reference-zone")

    shoot(ItemDialog(engine), "02-dialog-item")
    shoot(CgDialog(engine), "03-dialog-cg-new")

    editor = CgEditor(engine, ids["cg_id"])
    editor.resize(980, 620)
    shoot(editor, "04-dialog-cg-editor")

    mapping = MappingDialog(engine, ids["other_id"], ids["cg_id"])
    mapping.resize(940, 600)
    shoot(mapping, "05-dialog-mapping")

    form = DeviationDialog(engine, ids["current_id"])
    form.resize(1040, 760)
    shoot(form, "06-dialog-deviation-edit")
    shoot(DeviationDialog(engine), "07-dialog-deviation-new")

    shoot(FindingDialog(engine, ids["item_id"]), "08-dialog-finding")
    shoot(InspectionDialog(engine, ids["finding_id"]), "09-dialog-inspection")
    shoot(DecisionDialog(engine, ids["current_id"]), "10-dialog-decision")

    card = CardDialog(engine, ids["current_id"])
    card.resize(1180, 860)
    shoot(card, "11-dialog-card")

    engine.dispose()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
