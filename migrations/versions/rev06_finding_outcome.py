"""rev 0.6 - the outcome moves to the finding (QMS-025 / worklog 0030).

Found by use, not by argument. A deviation with one finding reads unambiguously off the
list; a deviation with two or more does not - the screen says the batch was rejected and
cannot say **which dimension rejected it**. The engineer then opens records to find out,
which is the work the base exists to remove.

Two changes:

* `finding.outcome` - new, nullable, `permitted` / `not_permitted`. Empty is the normal
  state of a freshly registered deviation: findings are entered at registration, the
  judgement comes later. It answers "did this dimension pass", while `deviation.decisionDev`
  answers "what happens to the batch" - the first is the **input** to the second, not a
  replacement.
* `inspection.decision_insp` - **dropped**, together with its CHECK. The rule "an inspection
  does not dictate the decision" stops being a warning to observe and becomes structure:
  there is no field left to break it with (`Inspection.md` rev 1.03).

**Values are not carried over** - an announced omission (naryad `0030` §1). Deriving an
engineer's judgement from an inspection's position is exactly what this change exists to
stop, and there is no live data: the run database and the demo one are both disposable.

**The binding invariant is not in the schema, and that is a decision, not an oversight.**
"a deviation may be `approved` only when every finding is `permitted`" depends on the set of
child rows, and a CHECK cannot express that. A trigger can, but on SQLite it is lost silently
whenever `batch_alter_table` rebuilds the table - a burn this project already took. So the
invariant lives in the domain, in two entry points, and its reliability comes from tests that
enter the domain directly, bypassing the form.

Revision ID: rev06
Revises: rev05
Create Date: 2026-09-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev06"
down_revision: Union[str, Sequence[str], None] = "rev05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OUTCOME_CHECK = "outcome IS NULL OR outcome IN ('permitted', 'not_permitted')"
_POSITION_CHECK = (
    "decision_insp IS NULL OR decision_insp IN "
    "('approval_possible', 'approval_not_possible', 'inconclusive')"
)


def upgrade() -> None:
    """Upgrade schema."""
    # Колонка появляется пустой у всех строк, поэтому CHECK можно ставить сразу:
    # пересборка таблицы копирует их через него, и `NULL` он пропускает. Двух
    # проходов, как в `rev04` и `rev05`, здесь не нужно — переносить нечего.
    with op.batch_alter_table("finding", schema=None) as batch_op:
        batch_op.add_column(sa.Column("outcome", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(batch_op.f("ck_finding_outcome"), _OUTCOME_CHECK)

    # Констрейнт снимается **до** колонки: иначе пересборка унесла бы его вместе
    # с ней, а имя осталось бы в истории миграций без владельца (урок `rev04`).
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_inspection_decision_insp"), type_="check")
        batch_op.drop_column("decision_insp")


def downgrade() -> None:
    """Downgrade schema.

    Позиция возвращается **пустой у всех строк**, и это не потеря: значения не
    переносились и при накате. Восстановить их неоткуда — суждение, за которое
    позиция стояла, живёт теперь на находке и в старую колонку не отображается.
    Строки при этом целы: обратный перенос ничего не удаляет.
    """
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decision_insp", sa.String(length=32), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_inspection_decision_insp"), _POSITION_CHECK
        )

    with op.batch_alter_table("finding", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_finding_outcome"), type_="check")
        batch_op.drop_column("outcome")
