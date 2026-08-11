"""Критерий приёмки 4 — round-trip всего графа через закрытие соединения."""

from __future__ import annotations

import re

from sqlalchemy import select

from conftest import reopen
from db.models import (
    Characteristic,
    Deviation,
    Direction,
    Inspection,
    Item,
    RefConnectionType,
    RefItemType,
    RefSize,
)
from seed.synthetic import build_synthetic

DEV_RE = re.compile(r"^DEV-\d{6}-\d{4}$")
INSP_RE = re.compile(r"^INSP-\d{6}-\d{3}$")


def _fill(db_url: str) -> None:
    with reopen(db_url) as session:
        build_synthetic(session)
        session.commit()


def test_full_graph_survives_a_reopen(migrated_url: str) -> None:
    _fill(migrated_url)

    with reopen(migrated_url) as session:
        item = session.scalar(select(Item).where(Item.item_number == "C1-08375A"))

        # item -> справочники
        assert (item.item_type.name, item.connection_type.name, item.size.name) == (
            "implant",
            "C1",
            "NP",
        )

        # item -> characteristic -> mapping -> g_position -> cg
        by_number = {c.local_number: c for c in item.characteristics}
        assert set(by_number) == {"12", "19", "32"}
        mapped = by_number["12"].mapping
        assert mapped.g_position.g_index == 1
        assert (mapped.g_position.nominal, mapped.g_position.tol_plus) == (3.75, 0.05)
        assert mapped.g_position.cg.name == "Implant_Con_375_C1"
        assert len(mapped.g_position.cg.positions) == 3
        # код 99 — строка есть, канонической позиции нет
        assert by_number["32"].mapping.is_absent is True
        assert by_number["32"].mapping.g_position is None

        # deviation -> finding -> characteristic / zone / deviation_type
        dev = session.scalar(
            select(Deviation)
            .where(Deviation.item_id == item.item_id)
            .where(Deviation.decision_dev == "approved")
        )
        assert dev.wo == "W26007336"
        assert dev.ncr == "NCR-26-0431"
        assert dev.quantity == 120
        assert dev.explanation == "החריגה נבדקה מול השרטוט ואושרה לשימוש כמות שהיא"
        assert dev.attachment.endswith("measure.pdf")
        assert dev.decision_date is not None

        directions = {f.characteristic.local_number: f.direction for f in dev.findings}
        assert directions == {"12": Direction.PLUS, "19": Direction.MINUS}
        f12 = next(f for f in dev.findings if f.characteristic.local_number == "12")
        assert f12.value == 0.08
        assert f12.zone.name == "thread"
        assert f12.deviation_type.name == "thread burr"

        # deviation -> inspection -> finding / type
        insp = dev.inspections[0]
        assert insp.type.name == "Implantation torque test"
        assert insp.decision_insp == "approved"
        assert insp.finding.characteristic.local_number == "19"
        # Item исследования выводится из отклонения, отдельно не хранится
        assert insp.deviation.item.item_number == "C1-08375A"

        # обратная навигация: finding -> deviation -> item
        assert f12.deviation.item is item


def test_synthetic_covers_the_required_invariants(migrated_url: str) -> None:
    _fill(migrated_url)

    with reopen(migrated_url) as session:
        assert session.query(Item).count() >= 2

        decisions = {d.decision_dev for d in session.query(Deviation)}
        assert {"approved", "rejected"} <= decisions
        assert len(decisions) >= 3

        # деталь вне CG — размеры без маппинга (массовый случай)
        item_b = session.scalar(select(Item).where(Item.item_number == "MT-SRH19A"))
        assert item_b.characteristics
        assert all(c.mapping is None for c in item_b.characteristics)

        # у одного отклонения несколько findings с разными направлениями
        multi = [d for d in session.query(Deviation) if len(d.findings) > 1]
        assert multi
        assert {f.direction for f in multi[0].findings} == {Direction.PLUS, Direction.MINUS}

        # качественный признак: направление есть, величины нет
        assert session.query(Characteristic).count() == 5
        qualitative = [f for d in session.query(Deviation) for f in d.findings if f.value is None]
        assert qualitative and qualitative[0].comment

        # бизнес-номера присвоены и уникальны
        dev_numbers = [d.dev_number for d in session.query(Deviation)]
        insp_numbers = [i.insp_number for i in session.query(Inspection)]
        assert insp_numbers
        assert len(set(dev_numbers)) == len(dev_numbers)
        assert all(DEV_RE.match(n) for n in dev_numbers)
        assert all(INSP_RE.match(n) for n in insp_numbers)


def test_reference_values_are_shared_not_copied(migrated_url: str) -> None:
    """Справочники — контролируемые словари: одно значение на всех потребителей."""
    _fill(migrated_url)

    with reopen(migrated_url) as session:
        for model in (RefItemType, RefConnectionType, RefSize):
            names = [row.name for row in session.query(model)]
            assert len(names) == len(set(names))
        general = session.scalar(select(RefSize).where(RefSize.name == "General"))
        assert [item.item_number for item in general.items] == ["MT-SRH19A"]
