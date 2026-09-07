"""Модели MIS-QMS — 16 таблиц физической схемы (`docs/architecture.md` §5, rev 0.3).

Core (10): item · item_revision · characteristic · characteristic_group ·
g_position · mapping · item_position_absent · deviation · finding · inspection.
Reference (6): ref_item_type · ref_connection_type · ref_size · ref_zone ·
ref_deviation_type · ref_inspection_type.

Везде суррогатный целочисленный PK; у `deviation` и `inspection` дополнительно —
человекочитаемый бизнес-номер (`db.ids`).

Наряд 0001 / QMS-011 (rev 0.1) · наряд 0003 / QMS-013 (rev 0.2: чертёж и
координаты баллонов в канон-слое, код 99 отдельной таблицей) · наряд 0024 /
QMS-017 (rev 0.3: ревизия чертежа владеет размерами и кодом 99).
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
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# --- Контролируемые словари (значения, а не таблицы) ---------------------------

#: `decision_dev` — исход отклонения (`docs/model/Deviation.md`, Outcomes).
DECISION_DEV = ("approved", "rejected", "sorting", "repair")

#: `outcome` — исход **находки** (`docs/model/Finding.md` rev 1.01, QMS-025).
#:
#: Отвечает на вопрос «прошёл ли этот размер», тогда как `decision_dev` отвечает
#: «что делать с партией». Это **вход** для второго, а не замена: отклонение с
#: двумя находками, одна разрешена, другая нет, идёт в сортировку — по критерию
#: второй. Пусто = «ещё не решено», нормальное состояние свежей регистрации:
#: находки заводятся при регистрации, суждение приходит позже.
OUTCOME = ("permitted", "not_permitted")

#: Позиции у исследования больше нет (`Inspection.md` rev 1.03, QMS-025).
#:
#: Правило «исследование не диктует решение» перестало быть предупреждением и
#: стало **структурой**: поля, которым его нарушают, попросту нет. Суждение, за
#: которое позиция стояла, переехало на находку — `OUTCOME` выше.


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
    """Группа характеристик (CG) — канон-слой сравнения деталей между собой.

    Чертёж хранится **в базе** (`drawing`), а не ссылкой на файл: это справочные
    данные канона (~20–30 групп), без них визуальный редактор нерабочий, и
    правило «бэкап = копия одного файла БД» должно оставаться верным. Осознанное
    исключение из конвенции «вложения — ссылки, не блобы» (`architecture.md` §4);
    для `deviation.attachment` конвенция не меняется. Решение Cowork, наряд 0003.
    """

    __tablename__ = "characteristic_group"

    cg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    drawing: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    drawing_name: Mapped[Optional[str]] = mapped_column(String(255))

    positions: Mapped[list["GPosition"]] = relationship(
        back_populates="cg", cascade="all, delete-orphan"
    )


class GPosition(Base):
    """Каноническая позиция `g1…gN` внутри CG; номинал и допуск зашиты из чертежа.

    Номинал и допуски необязательны: позиция бывает допуском формы, и номинала
    у неё нет.

    `x`/`y` — нормализованные 0..1 координаты той механики расстановки, которую
    QMS-016 убрал: чертёж приходит из конструкторского отдела уже размеченным.
    Колонки **остаются в схеме незаполняемыми** — сносить их ценой миграции не
    оправдано, а заведённые до решения значения не трогаются. Проверку 0..1
    держит сама схема (`CheckConstraint` ниже); кода, который бы их писал, нет.
    """

    __tablename__ = "g_position"
    __table_args__ = (
        UniqueConstraint("cg_id", "g_index", name="uq_g_position_cg_index"),
        CheckConstraint("x IS NULL OR (x BETWEEN 0 AND 1)", name="x_normalized"),
        CheckConstraint("y IS NULL OR (y BETWEEN 0 AND 1)", name="y_normalized"),
    )

    g_position_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cg_id: Mapped[int] = mapped_column(
        ForeignKey("characteristic_group.cg_id", ondelete="CASCADE"), nullable=False
    )
    g_index: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal: Mapped[Optional[float]] = mapped_column(Float)
    tol_plus: Mapped[Optional[float]] = mapped_column(Float)
    tol_minus: Mapped[Optional[float]] = mapped_column(Float)
    x: Mapped[Optional[float]] = mapped_column(Float)
    y: Mapped[Optional[float]] = mapped_column(Float)

    cg: Mapped[CharacteristicGroup] = relationship(back_populates="positions")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="g_position")
    absences: Mapped[list["ItemPositionAbsent"]] = relationship(back_populates="g_position")


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
    deviations: Mapped[list["Deviation"]] = relationship(back_populates="item")
    revisions: Mapped[list["ItemRevision"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemRevision.seq"
    )

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Item {self.item_number!r}>"


class ItemRevision(Base):
    """Ревизия чертежа детали — владелец размеров и кода 99 (QMS-017).

    Ревизия принадлежит **чертежу**, а не нашим данным: конструкторский отдел
    перевыпускает чертёж на любое изменение, и новый выпуск несёт следующее
    обозначение. Номер детали при этом остаётся одной записью — ревизия дочерняя,
    поэтому перевыпуск не плодит двойников (`Item.md`).

    У группы характеристик своей ревизии нет: группа — наша конструкция, вне этой
    базы не существует (`CharacteristicGroup.md`).
    """

    __tablename__ = "item_revision"
    __table_args__ = (
        UniqueConstraint("item_id", "designation", name="uq_item_revision_designation"),
        UniqueConstraint("item_id", "seq", name="uq_item_revision_seq"),
        # Ровно одна действующая ревизия на деталь. Частичный уникальный индекс, а не
        # циклический FK `item.current_revision_id`: тот ломает вставку первой ревизии —
        # деталь ссылалась бы на ревизию, которой ещё нет.
        Index(
            "uq_item_revision_current",
            "item_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
    )

    revision_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.item_id", ondelete="CASCADE"), nullable=False
    )
    # Обозначение **как выпущено** (`A`, `B`, `A1`): строка, не номер, не парсится.
    designation: Mapped[str] = mapped_column(String(32), nullable=False)
    # Порядок хранится явно: система обязана уметь назвать «предыдущую», а
    # алфавитный порядок на обозначении не гарантирован.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    item: Mapped[Item] = relationship(back_populates="revisions")
    characteristics: Mapped[list["Characteristic"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    absent_positions: Mapped[list["ItemPositionAbsent"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    deviations: Mapped[list["Deviation"]] = relationship(back_populates="revision")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<ItemRevision item={self.item_id} {self.designation!r}>"


class Characteristic(Base):
    """Размер детали в одной ревизии чертежа. Ключ — `(item, revision, local#)`.

    `local_number` — строка: канон допускает буквенные номера (`AA`/`AB` для
    состояний до/после электрополировки, `Characteristic.md`).

    Владелец — **ревизия**, а не деталь (QMS-017). Ревизия входит в схему ровно в
    этой одной точке: `mapping` и `finding` висят на размере и наследуют её через
    него, поэтому своей колонки ревизии у них нет и не должно быть.
    """

    __tablename__ = "characteristic"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "local_number", name="uq_characteristic_revision_local"
        ),
    )

    characteristic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("item_revision.revision_id", ondelete="CASCADE"), nullable=False
    )
    local_number: Mapped[str] = mapped_column(String(32), nullable=False)
    # Спящее поле R1 (`decisions.md`): связь размеров-состояний. В S1 всегда NULL.
    state_depending_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("characteristic.characteristic_id")
    )

    revision: Mapped["ItemRevision"] = relationship(back_populates="characteristics")
    state_depending: Mapped[Optional["Characteristic"]] = relationship(
        remote_side="Characteristic.characteristic_id"
    )
    mapping: Mapped[Optional["Mapping"]] = relationship(
        back_populates="characteristic", cascade="all, delete-orphan", uselist=False
    )
    findings: Mapped[list["Finding"]] = relationship(back_populates="characteristic")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Characteristic rev={self.revision_id} #{self.local_number}>"


class Mapping(Base):
    """Привязка размера детали к канонической g-позиции — 0..1 на характеристику.

    Строка означает ровно одно: «размер привязан к g-позиции». Факт «позиция
    рассмотрена, у детали её нет» (**код 99**) переехал в отдельную таблицу
    `item_position_absent`: во флаге на `mapping` нельзя было записать, *какой
    именно* позиции нет (`g_position_id` при флаге обязан быть NULL), а канон
    требует именно пару `g:99`. Пересмотр ратификации S1 №6 — решение Cowork,
    наряд 0003.
    """

    __tablename__ = "mapping"

    mapping_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristic.characteristic_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    g_position_id: Mapped[int] = mapped_column(
        ForeignKey("g_position.g_position_id"), nullable=False
    )

    characteristic: Mapped[Characteristic] = relationship(back_populates="mapping")
    g_position: Mapped[GPosition] = relationship(back_populates="mappings")


class ItemPositionAbsent(Base):
    """Код 99 — «позицию рассмотрели, у детали её нет».

    Пара (**ревизия**, g-позиция) — QMS-017. Не ключ поиска: выдача «детали по `(cg, g_index)`»
    строится по `mapping` и такие детали не возвращает — пара лишь фиксирует,
    что вопрос закрыт, и отличает это от «ещё не рассматривали»
    (`CharacteristicGroup.md`, Session-03 §4).
    """

    __tablename__ = "item_position_absent"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "g_position_id", name="uq_item_position_absent_pair"
        ),
    )

    absent_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("item_revision.revision_id", ondelete="CASCADE"), nullable=False
    )
    g_position_id: Mapped[int] = mapped_column(
        ForeignKey("g_position.g_position_id"), nullable=False
    )

    revision: Mapped["ItemRevision"] = relationship(back_populates="absent_positions")
    g_position: Mapped[GPosition] = relationship(back_populates="absences")


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
    # `item_id` сохранён намеренно: выдача «по детали целиком», поверх всех ревизий
    # (`Search.md`), иначе каждый такой запрос шёл бы через join. Инвариант
    # `revision.item_id == item_id` держит домен — схема его выразить не может.
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("item_revision.revision_id"), nullable=False
    )
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
    revision: Mapped["ItemRevision"] = relationship(back_populates="deviations")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="deviation", cascade="all, delete-orphan"
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="deviation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Deviation {self.dev_number}>"


class Finding(Base):
    """Отклонение по одному размеру внутри Deviation.

    rev 0.6 (QMS-025): **несёт собственный исход**. До неё решений не несла вовсе, и
    отклонение с двумя находками не говорило, **какой размер его отклонил** — инженер
    шёл открывать записи, то есть делал ровно ту работу, ради устранения которой база
    и заведена (`Finding.md` rev 1.01). Количеств по-прежнему не несёт.
    """

    __tablename__ = "finding"
    __table_args__ = (
        CheckConstraint("direction IN ('+', '-')", name="direction"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('permitted', 'not_permitted')",
            name="outcome",
        ),
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
    #: Пусто = «ещё не решено». Форма находки ничего не блокирует: любое из трёх
    #: состояний законно в любой момент. Связь с исходом отклонения держит **домен**
    #: в двух точках — инвариант межтабличный, `CHECK` его не выражает.
    outcome: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

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

    rev 0.4 (QMS-018): позиция стала трёхзначной и необязательной, добавлен
    короткий вывод `conclusion`, `protocol` по смыслу — ссылка на файл.
    rev 0.5 (QMS-024): запись бывает **без файла протокола** — по признаку
    `no_protocol`, и тогда вывод обязателен.
    rev 0.6 (QMS-025): позиции нет вовсе. Исследование поставляет сведения — вид,
    вывод, протокол — и ничего больше.
    """

    __tablename__ = "inspection"
    __table_args__ = (
        #: **Файл ИЛИ вывод — инвариант держит схема, а не форма** (`Inspection.md`
        #: rev 1.02). Запись, не несущая ни того ни другого, невидима для поиска
        #: прецедентов, то есть бесполезна ровно в том, ради чего таблица заведена.
        #: Форму обходят импортом, скриптом или следующим нарядом; ограничение
        #: схемы обойти нечем.
        #:
        #: Отмеченный признак требует **пустого** протокола намеренно: «файл есть,
        #: но он не нужен» — состояние без смысла, и допустить его значит завести
        #: третий случай, который придётся объяснять на каждом экране.
        CheckConstraint(
            "(no_protocol = 0 AND protocol IS NOT NULL AND trim(protocol) <> '')"
            " OR "
            "(no_protocol = 1 AND (protocol IS NULL OR trim(protocol) = '')"
            " AND conclusion IS NOT NULL AND trim(conclusion) <> '')",
            name="protocol_or_conclusion",
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
    #: Короткий вывод словами — чтобы находку читали списком, не открывая файл.
    #: Не заменяет протокол и структуры не имеет: «−20 % полезного зазора» в
    #: рамку «величина + единица» не лезет (`Inspection.md` rev 1.01).
    conclusion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    #: Ссылка на файл протокола. **Существование не проверяется** (решение 4
    #: QMS-018): протокол может лежать на недоступном в момент ввода ресурсе, и
    #: ложный отказ дороже устаревшей ссылки. Пусто — только вместе с поднятым
    #: `no_protocol`; это держит `CHECK`, а не форма.
    protocol: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: **Решение инженера, а не вывод из пустого поля** (`Inspection.md` rev 1.02).
    #: Часть отклонений решается одним чертежом — наружный 10.0 против внутреннего
    #: 9.9 не сопрягается, — и такой вердикт стоит записать прецедентом, хотя
    #: документа к нему не существует. Пустое поле протокола — незаконченная
    #: запись; поднятый признак — сознательный отказ от документа.
    no_protocol: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    deviation: Mapped[Deviation] = relationship(back_populates="inspections")
    finding: Mapped[Finding] = relationship(back_populates="inspections")
    type: Mapped[RefInspectionType] = relationship(back_populates="inspections")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Inspection {self.insp_number}>"


#: Полный перечень таблиц схемы rev 0.2 — сверяется тестом критерия приёмки.
ALL_TABLES = (
    "item",
    "item_revision",
    "characteristic",
    "characteristic_group",
    "g_position",
    "mapping",
    "item_position_absent",
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
