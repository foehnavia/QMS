"""Модели MIS-QMS — 14 таблиц физической схемы (`docs/architecture.md` §5, rev 0.1).

Core (8): item · characteristic · characteristic_group · g_position · mapping ·
deviation · finding · inspection.
Reference (6): ref_item_type · ref_connection_type · ref_size · ref_zone ·
ref_deviation_type · ref_inspection_type.

Везде суррогатный целочисленный PK; у `deviation` и `inspection` дополнительно —
человекочитаемый бизнес-номер (`db.ids`). Наряд 0001 / QMS-011.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# --- Контролируемые словари (значения, а не таблицы) ---------------------------

#: `decision_dev` — исход отклонения (`docs/model/Deviation.md`, Outcomes).
DECISION_DEV = ("approved", "rejected", "sorting", "repair")

#: `decision_insp` — бинарный вердикт исследования, независим от `decision_dev`.
DECISION_INSP = ("approved", "not_approved")


class Direction:
    """Знаковая конвенция ETL: `-` ниже минимума, `+` выше максимума.

    В БД хранится ASCII-дефис (канон в прозе пишет типографский `−`, U+2212) —
    единая точка для парсера S6 и для UI.
    """

    PLUS = "+"
    MINUS = "-"
    ALL = (PLUS, MINUS)


#: Имя дефолтного значения справочников connection_type / size (`Item.md`).
GENERAL = "General"


# --- Справочники (6) -----------------------------------------------------------


class RefItemType(Base):
    """Тип детали (implant / abutment / drill …). Может быть не задан."""

    __tablename__ = "ref_item_type"

    item_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    items: Mapped[list["Item"]] = relationship(back_populates="item_type")


class RefConnectionType(Base):
    """Тип соединения (C1 / V3 / IntHex / LYNX / General)."""

    __tablename__ = "ref_connection_type"

    connection_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    items: Mapped[list["Item"]] = relationship(back_populates="connection_type")


class RefSize(Base):
    """Размерный класс детали (NP / SP / WP / General)."""

    __tablename__ = "ref_size"

    size_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    items: Mapped[list["Item"]] = relationship(back_populates="size")


class RefZone(Base):
    """Зона детали — мягкий поисковый ярлык на finding (уровень L2)."""

    __tablename__ = "ref_zone"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    findings: Mapped[list["Finding"]] = relationship(back_populates="zone")


class RefDeviationType(Base):
    """Характер отклонения (thread burr, angle …) — второй уровень поиска."""

    __tablename__ = "ref_deviation_type"

    deviation_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    findings: Mapped[list["Finding"]] = relationship(back_populates="deviation_type")


class RefInspectionType(Base):
    """Вид исследования (Solidworks assembly, Implantation torque test …)."""

    __tablename__ = "ref_inspection_type"

    inspection_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="type")


#: Справочники в порядке сида — используется в `seed.reference`.
REFERENCE_MODELS = (
    RefItemType,
    RefConnectionType,
    RefSize,
    RefZone,
    RefDeviationType,
    RefInspectionType,
)


# --- Канон-слой ----------------------------------------------------------------


class CharacteristicGroup(Base):
    """Группа характеристик (CG) — канон-слой сравнения деталей между собой."""

    __tablename__ = "characteristic_group"

    cg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    positions: Mapped[list["GPosition"]] = relationship(
        back_populates="cg", cascade="all, delete-orphan"
    )


class GPosition(Base):
    """Каноническая позиция `g1…gN` внутри CG; номинал и допуск зашиты из чертежа."""

    __tablename__ = "g_position"
    __table_args__ = (UniqueConstraint("cg_id", "g_index", name="uq_g_position_cg_index"),)

    g_position_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cg_id: Mapped[int] = mapped_column(
        ForeignKey("characteristic_group.cg_id", ondelete="CASCADE"), nullable=False
    )
    g_index: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal: Mapped[Optional[float]] = mapped_column(Float)
    tol_plus: Mapped[Optional[float]] = mapped_column(Float)
    tol_minus: Mapped[Optional[float]] = mapped_column(Float)

    cg: Mapped[CharacteristicGroup] = relationship(back_populates="positions")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="g_position")


# --- Ядро ----------------------------------------------------------------------


class Item(Base):
    """Деталь — центр модели. `item_number` — каталожный номер (`מק"ט`)."""

    __tablename__ = "item"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    item_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ref_item_type.item_type_id")
    )
    # connection_type и size обязательны — у обоих есть дефолт `General`,
    # поэтому деталь заводится и когда специфика ещё не важна (`Item.md`).
    connection_type_id: Mapped[int] = mapped_column(
        ForeignKey("ref_connection_type.connection_type_id"), nullable=False
    )
    size_id: Mapped[int] = mapped_column(ForeignKey("ref_size.size_id"), nullable=False)

    item_type: Mapped[Optional[RefItemType]] = relationship(back_populates="items")
    connection_type: Mapped[RefConnectionType] = relationship(back_populates="items")
    size: Mapped[RefSize] = relationship(back_populates="items")
    characteristics: Mapped[list["Characteristic"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    deviations: Mapped[list["Deviation"]] = relationship(back_populates="item")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Item {self.item_number!r}>"


class Characteristic(Base):
    """Размер конкретной детали. Ключ — `(item, local_number)`.

    `local_number` — строка: канон допускает буквенные номера (`AA`/`AB` для
    состояний до/после электрополировки, `Characteristic.md`).
    """

    __tablename__ = "characteristic"
    __table_args__ = (
        UniqueConstraint("item_id", "local_number", name="uq_characteristic_item_local"),
    )

    characteristic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.item_id", ondelete="CASCADE"), nullable=False
    )
    local_number: Mapped[str] = mapped_column(String(32), nullable=False)
    # Спящее поле R1 (`decisions.md`): связь размеров-состояний. В S1 всегда NULL.
    state_depending_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("characteristic.characteristic_id")
    )

    item: Mapped[Item] = relationship(back_populates="characteristics")
    state_depending: Mapped[Optional["Characteristic"]] = relationship(
        remote_side="Characteristic.characteristic_id"
    )
    mapping: Mapped[Optional["Mapping"]] = relationship(
        back_populates="characteristic", cascade="all, delete-orphan", uselist=False
    )
    findings: Mapped[list["Finding"]] = relationship(back_populates="characteristic")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Characteristic item={self.item_id} #{self.local_number}>"


class Mapping(Base):
    """Привязка размера детали к канонической g-позиции — 0..1 на характеристику.

    Три различимых состояния (заметка А наряда 0001):

    * строки нет — маппинга ещё нет (в т.ч. исключение R2 «срочный WO»);
    * `g_position_id` заполнен — размер привязан к канону;
    * `g_position_id IS NULL AND is_absent` — **код 99**: «позиция рассмотрена,
      отсутствует у детали». Не ключ поиска: джойнить нечего, поэтому в выдачу
      по `(cg, g_index)` такие строки не попадают.
    """

    __tablename__ = "mapping"
    __table_args__ = (
        CheckConstraint(
            "(g_position_id IS NOT NULL AND is_absent = 0)"
            " OR (g_position_id IS NULL AND is_absent = 1)",
            name="target_xor_absent",
        ),
    )

    mapping_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristic.characteristic_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    g_position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("g_position.g_position_id")
    )
    is_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    characteristic: Mapped[Characteristic] = relationship(back_populates="mapping")
    g_position: Mapped[Optional[GPosition]] = relationship(back_populates="mappings")


class Deviation(Base):
    """Отклонение — самостоятельная запись с решением, количеством и датой.

    Целостность — на этом уровне: отклонение не дробится по размерам.
    """

    __tablename__ = "deviation"
    __table_args__ = (
        CheckConstraint(
            "decision_dev IS NULL OR decision_dev IN "
            "('approved', 'rejected', 'sorting', 'repair')",
            name="decision_dev",
        ),
    )

    deviation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dev_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.item_id"), nullable=False)
    wo: Mapped[str] = mapped_column(String(64), nullable=False)  # `פק"ע`
    machine: Mapped[Optional[str]] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    ncr: Mapped[Optional[str]] = mapped_column(String(64))  # может прийти позже решения
    decision_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    # NULL = решение ещё не принято (регистрация — шаг 3, решение — шаг 8).
    decision_dev: Mapped[Optional[str]] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Вложения — ссылки на файлы в сетевой папке, не блобы (`architecture.md` §4).
    attachment: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped[Item] = relationship(back_populates="deviations")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="deviation", cascade="all, delete-orphan"
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="deviation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Deviation {self.dev_number}>"


class Finding(Base):
    """Отклонение по одному размеру внутри Deviation. Решений и количеств не несёт."""

    __tablename__ = "finding"
    __table_args__ = (
        CheckConstraint("direction IN ('+', '-')", name="direction"),
    )

    finding_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deviation_id: Mapped[int] = mapped_column(
        ForeignKey("deviation.deviation_id", ondelete="CASCADE"), nullable=False
    )
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristic.characteristic_id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(1), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    dimension_point: Mapped[Optional[int]] = mapped_column(Integer)  # в поиске не участвует
    comment: Mapped[Optional[str]] = mapped_column(Text)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ref_zone.zone_id"))
    deviation_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ref_deviation_type.deviation_type_id")
    )

    deviation: Mapped[Deviation] = relationship(back_populates="findings")
    characteristic: Mapped[Characteristic] = relationship(back_populates="findings")
    zone: Mapped[Optional[RefZone]] = relationship(back_populates="findings")
    deviation_type: Mapped[Optional[RefDeviationType]] = relationship(
        back_populates="findings"
    )
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="finding")


class Inspection(Base):
    """Исследование — задокументированное переиспользуемое изучение влияния отклонения.

    Item выводится из deviation/finding и отдельно не хранится.
    """

    __tablename__ = "inspection"
    __table_args__ = (
        CheckConstraint(
            "decision_insp IN ('approved', 'not_approved')", name="decision_insp"
        ),
    )

    inspection_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insp_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    deviation_id: Mapped[int] = mapped_column(
        ForeignKey("deviation.deviation_id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.finding_id"), nullable=False)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("ref_inspection_type.inspection_type_id"), nullable=False
    )
    decision_insp: Mapped[str] = mapped_column(String(16), nullable=False)
    protocol: Mapped[str] = mapped_column(Text, nullable=False)  # ссылка на документ

    deviation: Mapped[Deviation] = relationship(back_populates="inspections")
    finding: Mapped[Finding] = relationship(back_populates="inspections")
    type: Mapped[RefInspectionType] = relationship(back_populates="inspections")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Inspection {self.insp_number}>"


#: Полный перечень таблиц схемы rev 0.1 — сверяется тестом критерия приёмки 1.
ALL_TABLES = (
    "item",
    "characteristic",
    "characteristic_group",
    "g_position",
    "mapping",
    "deviation",
    "finding",
    "inspection",
    "ref_item_type",
    "ref_connection_type",
    "ref_size",
    "ref_zone",
    "ref_deviation_type",
    "ref_inspection_type",
)
