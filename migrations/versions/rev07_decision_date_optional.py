"""rev 0.7 - the decision date is empty until there is a decision (QMS-030 / worklog 0040).

`deviation.decision_date` was `NOT NULL DEFAULT now`. A deviation is registered at step 3 and
decided at step 8, so between them every freshly registered record carried a decision date for
a decision nobody had taken. It changed no behaviour - nothing reads the field before a
decision - but it misleads the **output document**: `אישור חריגה` would print a decision date
on a record that has none. Delta carried since S4 (2026-08-17).

Two changes, and the second is the point of the first:

* the column becomes nullable and **loses its default**. A default would put the value back
  the moment a row is inserted, which is exactly the defect;
* rows already carrying a stamped-but-meaningless date are backfilled to `NULL` **where
  `decision_dev IS NULL`** - that is, precisely where the date describes a decision that was
  never taken. Rows with a decision keep their date untouched.

The date is now written by the domain, in `set_decision`, next to the decision itself and
nowhere else. Making the schema silent about it is what keeps the two from drifting apart.

Revision ID: rev07
Revises: rev06
Create Date: 2026-09-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rev07"
down_revision: Union[str, Sequence[str], None] = "rev06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Порядок обратен привычному: сперва снимаем `NOT NULL`, потом засыпаем.
    # Обратный порядок невозможен по построению — `UPDATE ... = NULL` на
    # `NOT NULL` колонке отбивается самой базой.
    with op.batch_alter_table("deviation", schema=None) as batch_op:
        batch_op.alter_column(
            "decision_date",
            existing_type=sa.DateTime(),
            nullable=True,
            existing_server_default=None,
        )

    # Засыпается **только** то, где решения нет: дата при принятом решении
    # осмысленна и остаётся. Условие по `decision_dev`, а не по значению даты, —
    # спрашиваем о том, что определяет смысл поля, а не о его удобном признаке.
    op.execute(
        sa.text(
            "UPDATE deviation SET decision_date = NULL WHERE decision_dev IS NULL"
        )
    )


def downgrade() -> None:
    """Downgrade schema.

    Возврат `NOT NULL` требует, чтобы пустых значений не осталось, поэтому перед
    сменой типа пустые даты заполняются **датой регистрации** (`date`), а не
    системным временем отката: время отката не имеет отношения к записи и
    выглядело бы как решение, принятое в момент миграции. Дефолт при этом
    **не возвращается** — его снятие и есть содержание правки, а прежнее
    поведение восстанавливается моделью, если её откатят вместе со схемой.
    """
    op.execute(
        sa.text("UPDATE deviation SET decision_date = date WHERE decision_date IS NULL")
    )

    with op.batch_alter_table("deviation", schema=None) as batch_op:
        batch_op.alter_column(
            "decision_date",
            existing_type=sa.DateTime(),
            nullable=False,
            existing_server_default=None,
        )
