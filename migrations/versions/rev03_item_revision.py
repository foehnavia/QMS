"""rev 0.3 - item revision owns dimensions and code 99 (QMS-017 / worklog 0024).

The revision belongs to the part's **drawing**: engineering re-issues it on any
change, and the new issue carries the next designation. The part number stays one
record, so the revision is a child of `item` - a re-issued drawing never creates a
twin part (`docs/model/Item.md`).

The point of the migration is a change of **owner**: dimensions and code-99 rows move
from the part to the pair (part, revision), and a deviation records the revision it
was raised against. `mapping` and `finding` are deliberately left alone - both hang
off a dimension and inherit the revision through it, so the revision enters the schema
at exactly one point.

`deviation.item_id` is kept alongside the new `revision_id`: the "everything on this
part" query runs across all revisions (`docs/model/Search.md`), and without the column
every such query would go through a join. The invariant that the two agree is a domain
check - SQLite cannot express it.

Existing data: every part gets revision `A` (seq 1, current), and everything that used
to hang off the part is re-pointed at it. SQLite cannot ALTER in place, so each change
to an existing table goes through `batch_alter_table`.

Revision ID: rev03
Revises: rev02
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev03"
down_revision: Union[str, Sequence[str], None] = "rev02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "item_revision",
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["item.item_id"],
            name=op.f("fk_item_revision_item_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_item_revision")),
        sa.UniqueConstraint("item_id", "designation", name="uq_item_revision_designation"),
        sa.UniqueConstraint("item_id", "seq", name="uq_item_revision_seq"),
    )
    # Ровно одна действующая ревизия на деталь. Частичный уникальный индекс, а не
    # циклический FK `item.current_revision_id`: тот ломает вставку первой ревизии.
    op.create_index(
        "uq_item_revision_current",
        "item_revision",
        ["item_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
    )

    # --- Данные: каждой существующей детали - ревизия A ------------------------------
    op.execute(
        "INSERT INTO item_revision (item_id, designation, seq, is_current) "
        "SELECT item_id, 'A', 1, 1 FROM item"
    )

    # --- characteristic: владелец меняется с детали на ревизию -----------------------
    with op.batch_alter_table("characteristic") as batch:
        batch.add_column(sa.Column("revision_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE characteristic SET revision_id = ("
        "  SELECT r.revision_id FROM item_revision r WHERE r.item_id = characteristic.item_id"
        ")"
    )
    with op.batch_alter_table("characteristic") as batch:
        batch.alter_column("revision_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_characteristic_item_local", type_="unique")
        batch.create_unique_constraint(
            "uq_characteristic_revision_local", ["revision_id", "local_number"]
        )
        batch.create_foreign_key(
            op.f("fk_characteristic_revision_id"),
            "item_revision",
            ["revision_id"],
            ["revision_id"],
            ondelete="CASCADE",
        )
        batch.drop_column("item_id")

    # --- item_position_absent: пара (ревизия, g-позиция) -----------------------------
    with op.batch_alter_table("item_position_absent") as batch:
        batch.add_column(sa.Column("revision_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE item_position_absent SET revision_id = ("
        "  SELECT r.revision_id FROM item_revision r "
        "  WHERE r.item_id = item_position_absent.item_id"
        ")"
    )
    with op.batch_alter_table("item_position_absent") as batch:
        batch.alter_column("revision_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_item_position_absent_pair", type_="unique")
        batch.create_unique_constraint(
            "uq_item_position_absent_pair", ["revision_id", "g_position_id"]
        )
        batch.create_foreign_key(
            op.f("fk_item_position_absent_revision_id"),
            "item_revision",
            ["revision_id"],
            ["revision_id"],
            ondelete="CASCADE",
        )
        batch.drop_column("item_id")

    # --- deviation: revision_id рядом с item_id, не вместо ---------------------------
    with op.batch_alter_table("deviation") as batch:
        batch.add_column(sa.Column("revision_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE deviation SET revision_id = ("
        "  SELECT r.revision_id FROM item_revision r WHERE r.item_id = deviation.item_id"
        ")"
    )
    with op.batch_alter_table("deviation") as batch:
        batch.alter_column("revision_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            op.f("fk_deviation_revision_id"),
            "item_revision",
            ["revision_id"],
            ["revision_id"],
        )


def downgrade() -> None:
    """Downgrade schema.

    Наряд 0024 отката не требует; реализован, потому что необратимая миграция в
    цепочке мешает пересобрать базу с любой точки при разборе.
    """
    with op.batch_alter_table("deviation") as batch:
        batch.drop_constraint(op.f("fk_deviation_revision_id"), type_="foreignkey")
        batch.drop_column("revision_id")

    with op.batch_alter_table("item_position_absent") as batch:
        batch.add_column(sa.Column("item_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE item_position_absent SET item_id = ("
        "  SELECT r.item_id FROM item_revision r "
        "  WHERE r.revision_id = item_position_absent.revision_id"
        ")"
    )
    with op.batch_alter_table("item_position_absent") as batch:
        batch.alter_column("item_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_item_position_absent_pair", type_="unique")
        batch.create_unique_constraint("uq_item_position_absent_pair", ["item_id", "g_position_id"])
        batch.create_foreign_key(
            op.f("fk_item_position_absent_item_id"),
            "item",
            ["item_id"],
            ["item_id"],
            ondelete="CASCADE",
        )
        batch.drop_column("revision_id")

    with op.batch_alter_table("characteristic") as batch:
        batch.add_column(sa.Column("item_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE characteristic SET item_id = ("
        "  SELECT r.item_id FROM item_revision r WHERE r.revision_id = characteristic.revision_id"
        ")"
    )
    with op.batch_alter_table("characteristic") as batch:
        batch.alter_column("item_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_characteristic_revision_local", type_="unique")
        batch.create_unique_constraint("uq_characteristic_item_local", ["item_id", "local_number"])
        batch.create_foreign_key(
            op.f("fk_characteristic_item_id"),
            "item",
            ["item_id"],
            ["item_id"],
            ondelete="CASCADE",
        )
        batch.drop_column("revision_id")

    op.drop_index("uq_item_revision_current", table_name="item_revision")
    op.drop_table("item_revision")
