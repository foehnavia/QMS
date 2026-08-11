"""Синтетический датасет — правдоподобное наполнение, покрывающее инварианты модели.

Значения смешанные: неsensitive реальные (номер детали, номер WO, ивритское
заключение) и вымышленные. Отдельные значения не sensitive сами по себе —
`docs/decisions.md` (2026-08-10), `CLAUDE.md` §6; целиком собранного документа
здесь нет.

Покрывает: две детали с классификаторами · CG с несколькими g-позициями
(номинал + допуск) · маппинг размеров на канон · **код 99** («позиция
рассмотрена, отсутствует») · не-CG размеры (массовый случай) · четыре
отклонения со всеми значениями `decision_dev` · множественные findings с
разными направлениями `±`, частью с zone/deviation_type · исследование,
привязанное к deviation + finding.

Ожидает чистую БД (детали заводятся по фиксированным `item_number`).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from db.ids import next_dev_number, next_insp_number
from db.models import (
    GENERAL,
    Characteristic,
    CharacteristicGroup,
    Deviation,
    Direction,
    Finding,
    GPosition,
    Inspection,
    Item,
    ItemPositionAbsent,
    Mapping,
    RefConnectionType,
    RefDeviationType,
    RefInspectionType,
    RefItemType,
    RefSize,
    RefZone,
)

from .reference import ref, seed_reference


def build_synthetic(session: Session) -> dict[str, object]:
    """Наполнить БД синтетикой. Возвращает справочник созданных объектов."""
    seed_reference(session)

    # --- Канон-слой: CG с тремя g-позициями (номинал + допуск из чертежа) ---
    cg = CharacteristicGroup(name="Implant_Con_375_C1")
    cg.positions = [
        GPosition(g_index=1, nominal=3.75, tol_plus=0.05, tol_minus=-0.05),
        GPosition(g_index=2, nominal=2.00, tol_plus=0.00, tol_minus=-0.05),
        GPosition(g_index=3, nominal=0.50, tol_plus=0.02, tol_minus=-0.02),
    ]
    session.add(cg)
    session.flush()
    g1, g2, g3 = cg.positions

    # --- Деталь A: в CG, размеры засеяны при заведении детали ---
    item_a = Item(
        item_number="C1-08375A",
        item_type=ref(session, RefItemType, "implant"),
        connection_type=ref(session, RefConnectionType, "C1"),
        size=ref(session, RefSize, "NP"),
    )
    ch_a12 = Characteristic(item=item_a, local_number="12")
    ch_a19 = Characteristic(item=item_a, local_number="19")
    ch_a32 = Characteristic(item=item_a, local_number="32")
    session.add(item_a)
    session.flush()

    # Маппинг создаётся до регистрации отклонения (R2).
    session.add_all(
        [
            Mapping(characteristic=ch_a12, g_position=g1),
            Mapping(characteristic=ch_a19, g_position=g2),
            # Код 99: позицию g3 рассмотрели — у этой детали её нет.
            ItemPositionAbsent(item=item_a, g_position=g3),
        ]
    )
    # Размер 32 — не-CG: у детали он есть, канонической позиции ему не нашлось.

    # --- Деталь B: вне CG (массовый случай), дефолты `General` ---
    item_b = Item(
        item_number="MT-SRH19A",
        item_type=ref(session, RefItemType, "drill"),
        connection_type=ref(session, RefConnectionType, GENERAL),
        size=ref(session, RefSize, GENERAL),
    )
    ch_b07 = Characteristic(item=item_b, local_number="7")
    ch_b21 = Characteristic(item=item_b, local_number="21")
    session.add(item_b)
    session.flush()

    zone_thread = ref(session, RefZone, "thread")
    zone_edge = ref(session, RefZone, "cutting edge")
    dt_burr = ref(session, RefDeviationType, "thread burr")
    dt_inner = ref(session, RefDeviationType, "inner diameter")
    dt_width = ref(session, RefDeviationType, "cutting-edge width")

    # --- Отклонение 1: approved, два findings с разными направлениями ---
    dev1 = Deviation(
        dev_number=next_dev_number(session),
        item=item_a,
        wo="W26007336",
        machine="CNC-07",
        quantity=120,
        date=date(2026, 7, 28),
        ncr="NCR-26-0431",
        decision_dev="approved",
        explanation="החריגה נבדקה מול השרטוט ואושרה לשימוש כמות שהיא",
        attachment=r"\\fileserver\QC\deviations\W26007336\measure.pdf",
    )
    f1_12 = Finding(
        deviation=dev1,
        characteristic=ch_a12,
        direction=Direction.PLUS,
        value=0.08,
        zone=zone_thread,
        deviation_type=dt_burr,
    )
    f1_19 = Finding(
        deviation=dev1,
        characteristic=ch_a19,
        direction=Direction.MINUS,
        value=0.03,
        dimension_point=1,
        deviation_type=dt_inner,
    )
    session.add(dev1)
    session.flush()

    # --- Отклонение 2: rejected (сопутствующий фактор — сломанный инструмент) ---
    dev2 = Deviation(
        dev_number=next_dev_number(session),
        item=item_a,
        wo="W26007336",
        machine="CNC-07",
        quantity=18,
        date=date(2026, 7, 29),
        decision_dev="rejected",
        explanation="שבר בכלי — גדשים בהברגה, לא לשימוש",
    )
    session.add(
        Finding(
            deviation=dev2,
            characteristic=ch_a32,
            direction=Direction.PLUS,
            value=0.12,
            zone=zone_thread,
            deviation_type=dt_burr,
            comment="נמצא בבדיקה שלאחר הפק\"ע",
        )
    )
    session.add(dev2)
    session.flush()

    # --- Отклонение 3: sorting, качественный признак без величины ---
    dev3 = Deviation(
        dev_number=next_dev_number(session),
        item=item_b,
        wo="W26007412",
        quantity=9999,  # выборка `X מתוך Y` — уровень WO
        date=date(2026, 8, 3),
        decision_dev="sorting",
        explanation="מיון 100% לפי קריטריון שנקבע",
    )
    session.add(
        Finding(
            deviation=dev3,
            characteristic=ch_b07,
            direction=Direction.MINUS,
            comment="פין לא נכנס — GO",  # качественный признак: величины нет
            zone=zone_edge,
            deviation_type=dt_width,
        )
    )
    session.add(dev3)
    session.flush()

    # --- Отклонение 4: repair ---
    dev4 = Deviation(
        dev_number=next_dev_number(session),
        item=item_b,
        wo="W26007412",
        machine="CNC-02",
        quantity=45,
        date=date(2026, 8, 4),
        decision_dev="repair",
        explanation="תיקון — החריגה נותרת אך מאושרת",
    )
    session.add(
        Finding(
            deviation=dev4,
            characteristic=ch_b21,
            direction=Direction.PLUS,
            value=0.04,
        )
    )
    session.add(dev4)
    session.flush()

    # --- Исследование: привязано к deviation + finding, вердикт независим ---
    insp = Inspection(
        insp_number=next_insp_number(session),
        deviation=dev1,
        finding=f1_19,
        type=ref(session, RefInspectionType, "Implantation torque test"),
        decision_insp="approved",
        protocol=r"\\fileserver\QC\protocols\2026\torque-C1-08375A-19.docx",
    )
    session.add(insp)
    session.flush()

    return {
        "cg": cg,
        "items": [item_a, item_b],
        "characteristics": [ch_a12, ch_a19, ch_a32, ch_b07, ch_b21],
        "deviations": [dev1, dev2, dev3, dev4],
        "findings": [f1_12, f1_19],
        "inspections": [insp],
    }
