"""rev 0.2 - CG drawing, balloon coordinates, code-99 table (QMS-013 / worklog 0003).

Canon layer gets a visual editor, so it needs the drawing and the balloon
positions; code 99 moves from a flag on `mapping` into its own
`item_position_absent` table, because the flag could not record *which* position
is missing (see `db/models.py`). SQLite cannot ALTER in place - every change to
an existing table goes through `batch_alter_table`.

Revision ID: rev02
Revises: baseline
Create Date: 2026-08-11 16:15:53.834223

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev02"
down_revision: Union[str, Sequence[str], None] = "baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "item_position_absent",
        sa.Column("absent_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("g_position_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["g_position_id"],
            ["g_position.g_position_id"],
            name=op.f("fk_item_position_absent_g_position_id"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["item.item_id"],
            name=op.f("fk_item_position_absent_item_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("absent_id", name=op.f("pk_item_position_absent")),
        sa.UniqueConstraint("item_id", "g_position_id", name="uq_item_position_absent_pair"),
    )

    with op.batch_alter_table("characteristic_group", schema=None) as batch_op:
        batch_op.add_column(sa.Column("drawing", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("drawing_name", sa.String(length=255), nullable=True))

    with op.batch_alter_table("g_position", schema=None) as batch_op:
        batch_op.add_column(sa.Column("x", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("y", sa.Float(), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_g_position_x_normalized"), "x IS NULL OR (x BETWEEN 0 AND 1)"
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_g_position_y_normalized"), "y IS NULL OR (y BETWEEN 0 AND 1)"
        )

    # Old code-99 rows (is_absent = 1, hence g_position_id IS NULL) cannot be
    # carried over: the flag never recorded which position was missing, so there
    # is nothing to fill the now-mandatory g_position_id with. They are dropped,
    # loudly. Everything else keeps its binding untouched.
    connection = op.get_bind()
    stranded = connection.execute(
        sa.text("SELECT COUNT(*) FROM mapping WHERE g_position_id IS NULL")
    ).scalar_one()
    if stranded:
        print(
            f"rev02: dropping {stranded} old code-99 mapping row(s) - the flag did not "
            "record which g-position was absent, so they cannot be converted; "
            "re-enter them via the mapping dialog."
        )
        connection.execute(sa.text("DELETE FROM mapping WHERE g_position_id IS NULL"))

    with op.batch_alter_table("mapping", schema=None) as batch_op:
        batch_op.alter_column("g_position_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_constraint(batch_op.f("ck_mapping_target_xor_absent"), type_="check")
        batch_op.drop_column("is_absent")


def downgrade() -> None:
    """Downgrade schema."""
    # Отметки «позиции нет» на rev 0.1 не представимы (флаг не хранил позицию) —
    # они просто исчезают вместе с таблицей.
    with op.batch_alter_table("mapping", schema=None) as batch_op:
        # server_default обязателен: batch-режим пересоздаёт таблицу и переносит
        # строки, а NOT NULL-колонке нужно чем-то заполниться.
        batch_op.add_column(
            sa.Column("is_absent", sa.BOOLEAN(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_mapping_target_xor_absent"),
            "(g_position_id IS NOT NULL AND is_absent = 0)"
            " OR (g_position_id IS NULL AND is_absent = 1)",
        )
        batch_op.alter_column("g_position_id", existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table("g_position", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_g_position_y_normalized"), type_="check")
        batch_op.drop_constraint(batch_op.f("ck_g_position_x_normalized"), type_="check")
        batch_op.drop_column("y")
        batch_op.drop_column("x")

    with op.batch_alter_table("characteristic_group", schema=None) as batch_op:
        batch_op.drop_column("drawing_name")
        batch_op.drop_column("drawing")

    op.drop_table("item_position_absent")
