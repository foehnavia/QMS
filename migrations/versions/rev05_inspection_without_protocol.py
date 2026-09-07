"""rev 0.5 - an inspection may carry no protocol file (QMS-024 / worklog 0029).

Until rev 0.4 the criterion for creating an inspection row was the existence of an
attached **file**, and the schema enforced it with `protocol NOT NULL`. The hand run
of QMS-018 showed the rule too wide: some deviations are settled by the drawing alone
- an outer diameter of 10.0 against an inner one of 9.9 does not mate, and no study
will change that - and that verdict is a reusable precedent worth recording, while no
document exists to attach. The form refused such a row, so a correct working case had
no way into the database.

Three changes on `inspection`:

* `no_protocol` - new, `Boolean` NOT NULL, default 0. A **decision of the engineer**,
  never inferred from an empty field: an empty protocol is an unfinished record, a set
  flag is a deliberate waiver of the document.
* `protocol` becomes nullable.
* a CHECK carries the invariant **a file or a conclusion**:

      (no_protocol = 0 AND protocol IS NOT NULL AND trim(protocol) <> '')
      OR
      (no_protocol = 1 AND (protocol IS NULL OR trim(protocol) = '')
                       AND conclusion IS NOT NULL AND trim(conclusion) <> '')

  It lives in the schema and not in the form on purpose: a row carrying neither is
  invisible to the precedent search, which is the whole reason the table exists, and a
  form is bypassed by an import, a script or the next naryad.

Existing rows all carry a protocol, so they get `no_protocol = 0` and pass the
constraint untouched - asserted by a test, not assumed.

The upgrade runs in two passes for the same reason rev04 did: on SQLite a batch
recreate copies rows through the **new** constraint, so the column must exist and be
filled before the constraint is created.

Revision ID: rev05
Revises: rev04
Create Date: 2026-09-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev05"
down_revision: Union[str, Sequence[str], None] = "rev04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK = (
    "(no_protocol = 0 AND protocol IS NOT NULL AND trim(protocol) <> '')"
    " OR "
    "(no_protocol = 1 AND (protocol IS NULL OR trim(protocol) = '')"
    " AND conclusion IS NOT NULL AND trim(conclusion) <> '')"
)


def upgrade() -> None:
    """Upgrade schema."""
    # Проход 1: колонка появляется заполненной нулём, а `protocol` теряет NOT NULL.
    # Констрейнт ставится отдельно: пересборка таблицы копирует строки **через
    # него**, а до заполнения `no_protocol` они бы его не прошли.
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "no_protocol",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.alter_column("protocol", existing_type=sa.Text(), nullable=True)

    # Проход 2: инвариант. К этому моменту у всех строк `no_protocol = 0` и
    # непустой протокол — они проходят его без правки данных.
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            batch_op.f("ck_inspection_protocol_or_conclusion"), _CHECK
        )


def downgrade() -> None:
    """Downgrade schema.

    Строки с `no_protocol = 1` в старой схеме **непредставимы**: там `protocol`
    объявлен NOT NULL, а у них его нет по существу, а не по недосмотру. Подставить
    выдуманный путь означало бы вписать в базу документ, которого не существует, —
    та же подмена, против которой заведён сам признак. Поэтому такие строки
    удаляются, и удаление громкое: прецеденты `rev02` (неконвертируемые отметки
    кода 99) и `rev04` (`inconclusive` без полярного эквивалента).

    Констрейнт снимается **до** правки значений: под ним удаление и обратный
    перенос отбились бы о него самого (урок `rev04`).
    """
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_inspection_protocol_or_conclusion"), type_="check"
        )

    connection = op.get_bind()
    stranded = connection.execute(
        sa.text("SELECT COUNT(*) FROM inspection WHERE no_protocol = 1")
    ).scalar_one()
    if stranded:
        print(
            f"rev05: dropping {stranded} inspection row(s) recorded without a protocol - "
            "the old schema demands a file, and inventing a path would put a document "
            "that does not exist into the database; re-enter them if needed."
        )
        connection.execute(sa.text("DELETE FROM inspection WHERE no_protocol = 1"))

    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_column("no_protocol")
        batch_op.alter_column("protocol", existing_type=sa.Text(), nullable=False)
