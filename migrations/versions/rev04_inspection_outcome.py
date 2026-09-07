"""rev 0.4 - inspection outcome is three-valued and optional (QMS-018 / worklog 0027).

Until rev 0.3 `decision_insp` was **binary and mandatory**, which forced a polar
answer out of every study. Most studies do not have one: "the useful clearance in
the assembled state drops by 20 %" is a measurement, not a verdict. The field made
`docs/model/Inspection.md` contradict itself - the file says an inspection
*accumulates information and does not dictate the decision*, while the column
demanded a decision-shaped answer.

Three changes, all on `inspection`:

* `decision_insp` becomes **optional** and three-valued - `approval_possible` /
  `approval_not_possible` / `inconclusive`. Empty means "not assessed yet" and is a
  legitimate state: the protocol is attached first, the reading of it comes later.
  Empty and `inconclusive` are different states, and until now nothing could tell
  them apart.
* `conclusion` - new, optional, up to 500 characters: what the study found, in words,
  so a finding can be read in a list without opening the protocol file.
* `protocol` keeps its type and its NOT NULL. Only its **meaning** changes - it is a
  link to a file now. Existing rows are **not** converted: they may hold prose, and
  prose cannot be turned into a path automatically. Declared in the naryad as an
  announced omission; the operator fixes those by hand.

Existing values are carried over: `approved` -> `approval_possible`,
`not_approved` -> `approval_not_possible`.

The upgrade runs in three passes because SQLite cannot ALTER in place and a batch
recreate copies rows through the **new** CHECK: the old constraint is dropped first,
then the data is rewritten, and only then is the new constraint created. Doing it in
one pass would fail on the copy - every existing row still carries an old value at
that moment.

Revision ID: rev04
Revises: rev03
Create Date: 2026-09-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev04"
down_revision: Union[str, Sequence[str], None] = "rev03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Перенос старых значений в новые (upgrade) — и обратно (downgrade).
_TO_NEW = {"approved": "approval_possible", "not_approved": "approval_not_possible"}
_TO_OLD = {new: old for old, new in _TO_NEW.items()}


def upgrade() -> None:
    """Upgrade schema."""
    # Проход 1: снять старый CHECK и расширить колонку. Пока констрейнта нет,
    # значения свободны — иначе UPDATE ниже отбился бы о старый список.
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_inspection_decision_insp"), type_="check")
        batch_op.alter_column(
            "decision_insp",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            nullable=True,
        )
        batch_op.add_column(sa.Column("conclusion", sa.String(length=500), nullable=True))

    # Проход 2: перенос значений.
    connection = op.get_bind()
    for old, new in _TO_NEW.items():
        connection.execute(
            sa.text("UPDATE inspection SET decision_insp = :new WHERE decision_insp = :old"),
            {"new": new, "old": old},
        )

    # Проход 3: новый CHECK — уже по перенесённым значениям.
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            batch_op.f("ck_inspection_decision_insp"),
            "decision_insp IS NULL OR decision_insp IN "
            "('approval_possible', 'approval_not_possible', 'inconclusive')",
        )


def downgrade() -> None:
    """Downgrade schema.

    Two of the four states have no representation in the old schema: `inconclusive`
    says the study was read and settles nothing, and empty says nobody has read it
    yet. The old column is NOT NULL and holds a polar verdict only, so carrying those
    rows back would mean **inventing a verdict** - and a verdict goes into the output
    document. Such rows are dropped, loudly, the same way rev02 dropped old code-99
    mappings it could not convert (`docs/worklog/0003`, review S3 item 4). Rows that
    do carry a polar position are converted and kept.
    """
    connection = op.get_bind()
    stranded = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM inspection "
            "WHERE decision_insp IS NULL OR decision_insp = 'inconclusive'"
        )
    ).scalar_one()
    if stranded:
        print(
            f"rev04: dropping {stranded} inspection row(s) - 'inconclusive' and "
            "'not assessed yet' have no polar equivalent, and inventing one would put "
            "a verdict nobody gave into the output document; re-enter them if needed."
        )
        connection.execute(
            sa.text(
                "DELETE FROM inspection "
                "WHERE decision_insp IS NULL OR decision_insp = 'inconclusive'"
            )
        )
    # Три прохода, зеркально накату: сначала снять действующий CHECK, потом
    # переписать значения, и только потом ставить старый. Перенос под живым
    # констрейнтом отбивается им же — новый список не знает слова `approved`.
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_inspection_decision_insp"), type_="check")

    for new, old in _TO_OLD.items():
        connection.execute(
            sa.text("UPDATE inspection SET decision_insp = :old WHERE decision_insp = :new"),
            {"old": old, "new": new},
        )

    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_column("conclusion")
        batch_op.alter_column(
            "decision_insp",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            nullable=False,
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_inspection_decision_insp"),
            "decision_insp IN ('approved', 'not_approved')",
        )
