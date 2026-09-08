"""Карточка отклонения — рабочий экран и главный deliverable Этапа 1 (наряд 0005).

Смысл экрана один: инженер, глядя на отклонение, сразу видит, случалось ли такое
раньше, что тогда решили и как обосновали (`DeviationCard.md`, шаг 6 процесса).
Ради этого карточка открывается **сама** после регистрации нового отклонения.

Прецеденты показываются **по выбранной находке**, а не по отклонению целиком
(решение Cowork 2): отклонение с пятью размерами иначе свалило бы в одну кучу
разное, а инженер работает с конкретным размером.

Вкладки — уровни поиска (`Search.md`): «Точные (L1)» по паре «деталь + размер» и
по канонической позиции. Вкладка описательного уровня **списка не показывает**
(наряд 0022, ревизия ратификации S5): описательный прецедент — результат поиска,
который инженер собирает под конкретный случай из нескольких параметров, а не
строка, которую система выводит сама по одному признаку. Вкладка остаётся с
объяснением — пустая вкладка без слов читалась бы как «прецедентов нет».

Своего диалога решения здесь нет: `DecisionDialog` переехал из списка **как
есть** — S4 сделал его самостоятельным ровно для этого.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from db.models import (
    Characteristic,
    Deviation,
    Finding,
    Inspection,
    Item,
    RefDeviationType,
    RefZone,
)
from db.session import session_scope
from domain.findings import (
    findings_for_deviations,
    inspection_counts,
    inspections_of_deviation,
    update_finding,
)
from domain.precedents import (
    CANON_NEW,
    CANON_UNBOUND,
    PrecedentRow,
    canon_labels,
    precedents_same_dimension,
    precedents_same_position,
)

from . import kit
from .common import (
    UNBOUND_MARK,
    FindingsPanel,
    panel_height,
    decision_dev_label,
    dimension_sort_key,
    iso,
    joined,
    mark_other_revision,
    mark_unbound,
    outcome_label,
    signed_label,
    unbound_size_text,
)
from .kit import tokens
from .kit.chips import EXPANDED_ROLE, ExpanderDelegate
from .kit.pills import DECISION_ROLE, DecisionPillDelegate
from .decision_dialog import DecisionDialog
from .deviation_dialog import (
    FINDING_COLUMNS,
    FINDING_MAGNITUDE_COLUMNS,
    FINDING_NUMERIC_COLUMNS,
    FINDING_WIDTHS,
    DeviationDialog,
    hide_finding_columns,
)
from .finding_dialog import FindingDialog, FindingRow
from .inspection_dialog import InspectionDialog
from .item_dialog import open_mapping
from .pickers import choose_cg_for_item

#: Исследования выбранной находки — тип · позиция · короткий вывод (наряд 0027 §3).
#:
#: Колонки «находка» здесь нет намеренно: таблица показывает исследования **одной**
#: находки — той, что выбрана выше, — и повторять её номер в каждой строке значило
#: бы объяснять то, что уже сказано выбором.
INSPECTION_COLUMNS = ("Type", "Conclusion")

#: Ширины по правилу §8.3 наряда 0020: `Type` — рекорд справочника
#: (`Implantation torque test`), `Conclusion` — предел с обрезкой, остальное в
#: подсказке. Колонка `Result` снята вместе с позицией (QMS-025); её знакоместа
#: **не отдаются** выводу — вывод и так на своём пределе с обрезкой, а лишняя
#: ширина у него отняла бы её у таблицы находок, где появилась колонка исхода.
INSPECTION_WIDTHS = (30, 46)

#: Индекс колонки вывода — адресуем по имени, а не по числу в теле цикла (§9а.9).
INSPECTION_CONCLUSION_COLUMN = INSPECTION_COLUMNS.index("Conclusion")

#: Колонка-раскрывателя у прецедента — своя, 30 px, всегда первая: шасси LTR.
#: Подписи нет по той же причине, что и в списке отклонений: заголовок над
#: стрелкой называл бы механику, а не данные.
PRECEDENT_EXPANDER = ""

#: Ширина раскрывателя — 30 px по §3 наряда `0031`. Отдельным именем, потому что
#: её же приходится ставить минимумом секции: без этого Qt поднимает её до своих
#: 34 и сумма расходится при сошедшемся объявлении.
PRECEDENT_EXPANDER_WIDTH = 30

PRECEDENT_COLUMNS = (
    PRECEDENT_EXPANDER,
    "Deviation",
    "Date",
    "Item",
    "Revision",
    "WO",
    "Characteristic",
    "Sign · value",
    "Decision",
    "Explanation",
    "Insp.",
)

#: Числовые колонки прецедента: дата, знак с величиной, счётчик исследований.
#: Ширины поимённо (§7.3 наряда 0020): max(заголовок, самое длинное реальное
#: значение) × 1.25; знакоместо — по самому широкому знаку шрифта канона.
#: `Characteristic` — составная ячейка `19 · C1 SP375 Int. Con. Zone`:
#: у неё предел с обрезкой, а не расчёт по рекорду.
#: `kit.FIT_LABEL` — счётчик (§8.3, класс 2): ширина равна заголовку,
#: запаса нет — не растёт ни содержимое, ни подпись.
#: `Revision` — обозначение как выпущено, обычно один-два знака; класс 2
#: (§8.3 наряда 0020): ширина по заголовку, запаса нет.
#:
#: **Все ширины назначены замером заново — §2 наряда `0032`.** Таблица объявляла
#: 1448 px при полотне в 1136 и потому прокручивалась вбок; наряд велел снять
#: разницу с колонок, у которых полный текст уже лежит в подсказке.
#:
#: Двух колонок не хватило, и вот почему — это замер, а не оценка. Потребность
#: колонки считается как `max(заголовок, самое длинное реальное значение) + 27`
#: непечатаемого; сумма потребностей вышла **1373**, то есть уже больше полотна.
#: Значит вопрос стоял не «где взять 312», а «как разложить 1136»:
#:
#:   колонка          было  нужно  стало   отчего так
#:   (раскрыватель)     30      —     30   §3 наряда 0031, не трогается
#:   Deviation         153    131    132   потребность плюс округление
#:   Date              132     89     92   то же
#:   Item              125     89     92   то же (наряд назвал её третьей)
#:   Revision           68     75     68   `FIT_LABEL`; недобор в 7 px — QMS-022
#:   WO                125     95     96   потребность плюс округление
#:   Characteristic    230    195    120   обрезается, полный текст в подсказке
#:   Sign · value      118     93     96   потребность плюс округление
#:   Decision          150     85    150   рисует пилюля, ей нужна оправа
#:   Explanation       270    440    176   обрезается, полный текст в подсказке
#:   Insp.              47     54     47   `FIT_LABEL`; тот же недобор, QMS-022
#:   сумма            1448   1373   1119   полотно 1120
#:
#: **Полотно считается по тесноте, а не по удобному случаю.** Раскрытие строк
#: поднимает вертикальную полосу, та забирает шестнадцать пикселей, и сетка,
#: сошедшаяся на свёрнутой таблице, давала колонку за краем на раскрытой.
#: Держится это не запасом, а тем, что центрирование **пересчитывается** после
#: раскрытия (`kit.recentre_columns`): отступ 8 на свёрнутой, 3 на раскрытой,
#: полотно в обоих случаях 1120. Сумма при этом не меняется ни на пиксель.
#:
#: `Revision` и `Insp.` оставлены `FIT_LABEL` намеренно, хотя замер показывает у
#: обеих недобор в 7 px: это известный дефект формулы `kit.FIT_LABEL`, общий для
#: всех экранов, и он чинится задачей **QMS-022**, а не здесь.
PRECEDENT_WIDTHS = (
    kit.px(PRECEDENT_EXPANDER_WIDTH),
    kit.px(132),
    kit.px(92),
    kit.px(92),
    kit.FIT_LABEL,
    kit.px(96),
    kit.px(120),
    kit.px(96),
    kit.pill(14),
    kit.px(196),
    kit.FIT_LABEL,
)

#: Дата, «знак · величина», счётчик. Ревизия сюда **не входит**: обозначение —
#: идентификатор, а не величина, сравнивать по нему нечего, и левый край держит
#: его у подписи колонки (`CLAUDE.md` §9).
#:
#: Номера сдвинуты на единицу колонкой-раскрывателем и потому берутся у
#: `PRECEDENT_COLUMNS.index(...)`, а не выписываются числами: индекс, выписанный
#: руками, — величина, общая у кода и теста (`CLAUDE.md` §9а.9).
PRECEDENT_NUMERIC_COLUMNS = tuple(
    PRECEDENT_COLUMNS.index(name) for name in ("Date", "Sign · value", "Insp.")
)

#: Вправо — только «знак · величина»: её и сравнивают вниз по столбцу.
PRECEDENT_MAGNITUDE_COLUMNS = (PRECEDENT_COLUMNS.index("Sign · value"),)

#: Колонка исхода — рисуется пилюлей (канон §1).
PRECEDENT_DECISION_COLUMN = PRECEDENT_COLUMNS.index("Decision")

#: Колонка ревизии и колонка размера — на них садятся обе пометки `Search.md`.
PRECEDENT_REVISION_COLUMN = PRECEDENT_COLUMNS.index("Revision")
PRECEDENT_SIZE_COLUMN = PRECEDENT_COLUMNS.index("Characteristic")

#: Колонка-раскрыватель и колонка, несущая идентификатор отклонения.
PRECEDENT_EXPANDER_COLUMN = PRECEDENT_COLUMNS.index(PRECEDENT_EXPANDER)
PRECEDENT_ID_COLUMN = PRECEDENT_COLUMNS.index("Deviation")
PRECEDENT_EXPLANATION_COLUMN = PRECEDENT_COLUMNS.index("Explanation")

#: Знак у не-канонного размера. Определение и смысл — в `ui.common`: одно значение
#: на всех экранах требует одного определения, иначе второй экран заведёт второй
#: смысл (`Search.md` v1.04). Здесь имя оставлено ради прежних точек ввоза.

UNBOUND_TITLE = "Search by canonical position is unavailable"
UNBOUND_HINT = (
    "This characteristic is not bound to the canon. Binding is exactly what "
    "finds the same design node on other items."
)

#: Заглушка вкладки описательного уровня — по образцу ленты, где поиск объявлен
#: словами «Search — not built yet». Место под будущую группу фильтров остаётся
#: видимым, а обещание несуществующего исчезает.
NOT_BUILT_TITLE = "Descriptive search — not built yet"
NOT_BUILT_HINT = (
    "Descriptive precedents are found by a search the engineer sets up: several "
    "parameters at once, for one case, not saved. A single parameter would return "
    "half the database."
)

NO_SELECTION_TITLE = "No finding selected"
NO_SELECTION_HINT = (
    "Pick a finding in the table above — precedents are searched by its characteristic."
)

#: Та же причина одной фразой — для компактных секций вкладки «точные».
NO_SELECTION_SHORT = "pick a finding above; precedents are searched by its characteristic"

#: Подписи вкладок. Счётчик на вкладке отвечает «сколько там есть» до того,
#: как оператор туда заглянул (макет S14), — иначе пустую вкладку он открывает,
#: чтобы это выяснить.
EXACT_TAB = "Exact precedents (L1)"
#: Счётчика у второй вкладки нет: считать нечего, пока запрос не собран человеком.
DESCRIPTIVE_TAB = "Descriptive precedents (L2)"

#: Пустая секция исследований. Две причины пустоты — «находка не выбрана» и
#: «исследований нет» — здесь **не** разводятся: обе секции стоят под таблицей
#: находок, и вторая фраза объясняет ровно то, что оператор и так видит.
#: Роль, под которой строка исследования несёт признак «файла нет».
#: Кнопку красит **код**, а не разбор текста ячейки (тот же приём, что у пилюли).
NO_PROTOCOL_ROLE = Qt.ItemDataRole.UserRole + 4

#: Почему у этой записи нечего открывать. Стоит и на строке, и на самой кнопке:
#: неактивная кнопка без объяснения читается как поломка (§4 наряда 0029).
NO_PROTOCOL_HINT = (
    "No protocol file — the drawing settles this one; the conclusion is the record."
)

NO_INSPECTIONS_TITLE = "No inspections"
NO_INSPECTIONS_HINT = (
    "an inspection is recorded only when a written, reusable analysis exists"
)

#: Роль, под которой групповая строка несёт своё имя. Групповая строка —
#: **третий** вид служебной строки этой таблицы (после строки панели), и отличать
#: её надо признаком, а не догадкой по содержимому ячейки.
GROUP_ROLE = Qt.ItemDataRole.UserRole + 5

#: Сколько строк таблицы находок видно, пока она не начнёт прокручиваться сама.
#: Шесть — потому что дальше карточка перестаёт быть обзором (§1 наряда `0032`).
FINDINGS_SHOWN = 6

#: То же для исследований выбранной находки. Четыре: их у одного размера единицы,
#: и высота секции не должна отбирать вертикаль у сравнения.
INSPECTIONS_SHOWN_IN_CARD = 4

#: Сколько строк прецедента область обязана показать в любом случае.
PRECEDENTS_FLOOR_ROWS = 2


def precedent_floor() -> int:
    """Нижний предел области прецедентов — **видимым**, а не числом пикселей.

    Требование §1 наряда `0032`: две строки прецедента плюс одна раскрытая панель
    целиком. Пиксельная константа на этом месте была бы тем же, что и снятый
    отсюда `INLINE_TABLE_HEIGHT`, — числом, которое перестаёт значить обещанное
    при первой же правке высоты строки.

    Панель считается **на максимум**: раскрытая запись с находкой, несущей больше
    двух исследований, — самый высокий случай, и обещать «панель целиком» надо на
    нём, а не на удобном. Групповая строка входит: без неё первая же группа
    съедала бы одну из двух обещанных строк.

    Чистая функция от токенов: проверяется арифметикой на любой платформе
    (`CLAUDE.md` §9а.14).
    """
    rows = kit.table_height(PRECEDENTS_FLOOR_ROWS)
    panel = panel_height([FINDING_WITH_MANY_INSPECTIONS])
    return rows + tokens.PRECEDENT_GROUP_HEIGHT + panel + tokens.TAB_STRIP_HEIGHT


#: Столько исследований у находки хватает, чтобы подстрока панели встала в самую
#: высокую из трёх своих высот (28 / 43 / 58).
FINDING_WITH_MANY_INSPECTIONS = 3

NO_PRECEDENTS_TITLE = "No precedents yet"
#: Компактная секция говорит одной фразой: читатель просматривает вкладку, а не
#: секцию, и абзац на каждую из двух пустых секций он всё равно не читает.
NO_PRECEDENTS_HINT = "only deviations that already carry a decision are listed"


@dataclass(frozen=True)
class PrecedentGroup:
    """Одна выборка прецедентов внутри общей таблицы (§3 наряда `0032`).

    До наряда каждая выборка была **своей таблицей** со своей шапкой. Колонки у
    них одинаковые, значит по норме `design-system.md` §7 rev 1.13 («One level,
    one header») это одна таблица с групповыми строками. Групповая строка вдобавок
    умеет то, чего шапка не умела, — **называть группу и считать её**.

    `key` отделяет одинаковые отклонения в разных группах: запись, попавшая в обе
    выборки, показывается в обеих, и раскрытие в одной не обязано раскрывать её
    в другой. Это не дубль, а два разных ответа на два разных вопроса.
    """

    key: str
    title: str
    rows: tuple[PrecedentRow, ...] = ()
    #: Чем объяснить пустую группу, если причина не «совпадений нет».
    note: str = ""


class PrecedentTable(kit.DataTable):
    """Таблица прецедентов. Единица строки — **отклонение целиком** (`Search.md`).

    Строка **раскрывается** теми же тремя уровнями, что и строка списка
    отклонений: отклонение → его находки → исследования при каждой находке
    (наряд `0031` §1). Панель под ней — не вторая такая же, а **та же самая**:
    `ui.common.FindingsPanel`, одна на оба экрана (`design-system.md` §3
    revision 1.12, «Expansion follows the object, not the screen»).

    Единица действия при этом не меняется: `Open precedent…` продолжает работать
    по выбранной строке прецедента, а у находки внутри панели своих действий нет
    (инварианты 1 и 2 наряда `0028` действуют здесь дословно).
    """

    def __init__(self, engine: Engine | None = None, *, parent: QWidget | None = None) -> None:
        columns = PRECEDENT_COLUMNS
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)
        # Минимум секции — **до** раздачи ширин, а не после: `dress_table` уже
        # выставляет колонки, и поднятый после неё порог их не пересчитывает.
        # Собственный минимум Qt — 34 px, и он молча раздул бы объявленные 30 до
        # 34: **объявленная ширина колонки — не нарисованная** (`design-system.md`
        # §3, `CLAUDE.md` §9а.12). Замер это и показал — сумма разошлась на 4 px
        # при идеально сходившемся объявлении.
        self.horizontalHeader().setMinimumSectionSize(PRECEDENT_EXPANDER_WIDTH)
        # Одевается тем же кодом, что и всякая таблица данных: разошедшиеся
        # настройки двух таблиц — та самая болезнь, ради которой заведён `kit`.
        kit.dress_table(
            self,
            numeric_columns=PRECEDENT_NUMERIC_COLUMNS,
            magnitude_columns=PRECEDENT_MAGNITUDE_COLUMNS,
            widths=PRECEDENT_WIDTHS,
        )
        self.setItemDelegateForColumn(
            PRECEDENT_DECISION_COLUMN, DecisionPillDelegate(self)
        )
        self.setItemDelegateForColumn(
            PRECEDENT_EXPANDER_COLUMN, ExpanderDelegate(self)
        )

        #: Движок нужен **только** раскрытию: находки и исследования прецедента
        #: читаются лениво, на клик по стрелке (§5 наряда `0031`). Заранее для
        #: всех строк их не тянут — выдача возвращает десятки отклонений, и тащить
        #: содержимое каждого ради двух, которые раскроют, значит работать
        #: впустую при каждом клике по находке.
        self._engine = engine
        self._groups: list[PrecedentGroup] = []
        self._reference: str | None = None
        #: Раскрытые — парой «группа · отклонение», а не одним идентификатором:
        #: одна и та же запись законно стоит в обеих группах, и раскрытие её в
        #: одной не обязано раскрывать её в другой (§3 наряда `0032`).
        self._expanded: set[tuple[str, int]] = set()
        #: Кому принадлежит строка, включая служебную.
        self._row_owner: dict[int, tuple[str, int]] = {}

        self.cellClicked.connect(self._on_cell_clicked)

    # --- раскрытие ----------------------------------------------------------------

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == PRECEDENT_EXPANDER_COLUMN:
            self.toggle_expansion(row)

    def toggle_expansion(self, row: int) -> None:
        """Раскрыть или свернуть строку. Раскрытых может быть сколько угодно.

        Решение 6 реестра, дословно то же, что в списке: гармошка убивает ровно
        то, ради чего раскрытие заведено, — сравнение двух записей между собой.
        А здесь это ещё существеннее: карточка и есть экран сравнения.

        Групповая строка не раскрывается: раскрывать в ней нечего, и `_row_owner`
        её не держит.
        """
        owner = self._row_owner.get(row)
        if owner is None:
            return
        selected = self.selected_deviation()
        if owner in self._expanded:
            self._expanded.discard(owner)
        else:
            self._expanded.add(owner)
        self._render(keep=selected)

    def expanded(self) -> set[int]:
        """Какие прецеденты раскрыты — идентификаторами, как и до наряда `0032`.

        Внутри состояние держится парой «группа · отклонение», но наружу отдаётся
        то, о чём спрашивают, — какие **записи** раскрыты.
        """
        return {deviation_id for _key, deviation_id in self._expanded}

    def is_panel_row(self, row: int) -> bool:
        """Служебная ли это строка панели. Признак — виджет, а не догадка."""
        return self.cellWidget(row, 0) is not None

    def is_group_row(self, row: int) -> bool:
        """Групповая ли это строка. Признак — роль, а не разбор текста ячейки."""
        cell = self.item(row, 0)
        return bool(cell is not None and cell.data(GROUP_ROLE))

    def is_service_row(self, row: int) -> bool:
        """Любая служебная строка: групповая или строка панели.

        Одним вопросом, потому что всем потребителям таблицы важно одно и то же —
        «это не прецедент». Разводить два вида по местам вызова значило бы
        заводить второй шанс забыть про один из них, а именно на таком пропуске
        в наряде `0029` вырос `TypeError` доводки 3.
        """
        return self.is_panel_row(row) or self.is_group_row(row)

    def panel_at(self, row: int) -> FindingsPanel | None:
        widget = self.cellWidget(row, 0)
        return widget if isinstance(widget, FindingsPanel) else None

    def _insert_group(self, group: PrecedentGroup) -> None:
        """Строка-заголовок группы во всю ширину.

        Не выбирается и не ловится стрелками — флаги сняты, Qt такие пропускает.
        Считает свою группу сама: «(0)» это **ответ**, а исчезнувшая группа
        читается оператором как «поиск не работал» (§3 наряда).
        """
        index = self.rowCount()
        self.insertRow(index)
        cell = QTableWidgetItem(iso(group.title))
        cell.setFlags(Qt.ItemFlag.NoItemFlags)
        cell.setData(GROUP_ROLE, True)
        if group.note:
            cell.setToolTip(group.note)
        self.setItem(index, 0, cell)
        self.setSpan(index, 0, 1, len(PRECEDENT_COLUMNS))
        self.setRowHeight(index, tokens.PRECEDENT_GROUP_HEIGHT)

    def _insert_panel(self, key: str, deviation_id: int) -> None:
        """Служебная строка на всю ширину с панелью находок прецедента.

        Строка **не выбирается и не ловится стрелками**: у её ячейки сняты все
        флаги, а Qt пропускает такие при навигации клавиатурой. Панель фокуса
        тоже не берёт, поэтому клик по ней не уводит выбор с прецедента.

        Шапка панели — **подчинённая** (§4 наряда `0032`): в диалоге она читается
        как подпись колонок, а не как заголовок новой таблицы. Это параметр
        панели, а не смена вида для всех: список отклонений строит ту же панель
        без него и остаётся с прежней шапкой.
        """
        findings, inspections = self._content(deviation_id)
        index = self.rowCount()
        self.insertRow(index)
        holder = QTableWidgetItem()
        holder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.setItem(index, 0, holder)
        self.setSpan(index, 0, 1, len(PRECEDENT_COLUMNS))
        panel = FindingsPanel(findings, inspections, self, subordinate=True)
        self.setCellWidget(index, 0, panel)
        self.setRowHeight(index, panel.height())
        self._row_owner[index] = (key, deviation_id)

    def _content(self, deviation_id: int):
        """Находки и исследования прецедента — **доменом**, при раскрытии (§5).

        Вторая дорога к тем же данным мимо домена была бы вторым источником
        правды: экран уже берёт сами прецеденты через `precedents_same_*`.
        """
        if self._engine is None:
            return [], {}
        with session_scope(self._engine) as session:
            findings = findings_for_deviations(session, [deviation_id]).get(
                deviation_id, []
            )
            inspections = inspections_of_deviation(session, deviation_id)
        return findings, inspections

    def fill(
        self, groups: list[PrecedentGroup], *, reference: str | None = None
    ) -> None:
        """Разложить **группы** выдачи. `reference` — ревизия, из которой смотрят.

        Она попадает в подсказку пометки выпуска; пометку ставит
        `mark_other_revision` — та же функция, что и в списке отклонений детали,
        чтобы один факт не выглядел на двух экранах по-разному.

        **Раскрытия здесь сбрасываются** (§4 наряда `0031`) — по той же причине,
        по какой сбрасывается выбор: пришёл другой набор отклонений, то есть
        другой вопрос, и уцелевшее состояние делало бы вид, что оператор что-то
        раскрывал в наборе, которого он ещё не видел. Внутри одного набора
        раскрытия живут: переключение вкладок сюда не заходит.
        """
        self._groups = list(groups)
        self._reference = reference
        self._expanded.clear()
        self._render()

    def groups(self) -> tuple[PrecedentGroup, ...]:
        """Выдача, как её разложили, — для тех, кто спрашивает про данные.

        Экран берёт отсюда полный текст обоснования (§5 наряда `0032`): в ячейке
        он урезан до одной строки, и копировать надо не то, что нарисовано.
        """
        return tuple(self._groups)

    def rows_of(self, key: str) -> tuple[PrecedentRow, ...]:
        """Строки одной группы — для тех, кто спрашивает про выдачу, не про экран."""
        for group in self._groups:
            if group.key == key:
                return group.rows
        return ()

    def _render(self, *, keep: int | None = None) -> None:
        """Разложить строки заново вместе со служебными. `keep` — что выбрать."""
        # Выбор сбрасываем: строки другие, а уцелевшее выделение делало бы вид,
        # что оператор что-то выбрал в таблице, которую он ещё не смотрел.
        self.clearSelection()
        self.setCurrentCell(-1, -1)
        self.setRowCount(0)
        self.clearSpans()
        self._row_owner = {}
        for group in self._groups:
            self._insert_group(group)
            for row in group.rows:
                index = self.rowCount()
                self.insertRow(index)
                self._fill_precedent(index, row, expanded=(group.key, row.deviation_id))
                self._row_owner[index] = (group.key, row.deviation_id)
                if (group.key, row.deviation_id) in self._expanded:
                    self._insert_panel(group.key, row.deviation_id)
        self._stretch_panels()
        if keep is not None:
            self._select_deviation(keep)

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя от Qt
        """Переложить панели по новой ширине.

        Ширина панели считается от полотна, а полотно к моменту вставки строки
        ещё не знает своего размера: раскрытие в `_render` укладывало панель по
        **устаревшему** числу, и на снимке она выходила короче таблицы на треть,
        теряя две последние колонки. При этом замер после доводки раскладки
        показывал верные числа — то есть дефект был виден только картинкой
        (`CLAUDE.md` §9а: сверяй то, чем рисуют).

        Флаг — не перестраховка: `_stretch_panels` двигает отступы полотна через
        `recentre_columns`, а это снова `resizeEvent`. Рекурсия здесь кончалась бы
        не миганием, а смертью процесса (§9а.15).
        """
        super().resizeEvent(event)
        if getattr(self, "_laying_out", False):
            return
        self._laying_out = True
        try:
            self._stretch_panels()
        finally:
            self._laying_out = False

    def _stretch_panels(self) -> None:
        """Растянуть панели на ширину служебной строки.

        `setCellWidget` кладёт виджет в прямоугольник ячейки и объединение
        (`setSpan`) к моменту вставки ещё не учитывает — панель осталась бы
        шириной первой колонки. Тот же приём и по той же причине, что в списке
        отклонений (`DeviationView._stretch_panels`).
        """
        content = sum(self.columnWidth(column) for column in range(self.columnCount()))
        # Панель **не шире полотна**: иначе раскрытая строка сама заводит
        # горизонтальную полосу, которую §2 наряда `0032` как раз и убирает.
        # Замерено: панель выходила ровно на пиксель шире, и этого пикселя
        # хватало, чтобы полоса появилась.
        available = self.viewport().width()
        width = min(content, available) if available > 0 else content
        for row in range(self.rowCount()):
            panel = self.panel_at(row)
            if panel is not None:
                panel.setFixedWidth(width)
                panel.fit_to(width)
                self.setRowHeight(row, panel.height())
        # Раскрытие меняет **высоту** содержимого, а с ней появляется
        # вертикальная полоса — и забирает у полотна свои пиксели. Отступ
        # центрирования, посчитанный до неё, остаётся прежним, и колонка уезжает
        # за правый край при сумме, которая не менялась ни на пиксель (§2 наряда
        # `0032`, замерено: полотно 1064 → 1054 при сумме 1063).
        kit.recentre_columns(self)

    def _select_deviation(self, deviation_id: int) -> None:
        """Вернуть выбор на ту же запись: раскрытие сдвигает номера строк."""
        for row, (_key, owner) in self._row_owner.items():
            if owner == deviation_id and not self.is_service_row(row):
                self.selectRow(row)
                return

    def _fill_precedent(self, index: int, row: PrecedentRow, *, expanded) -> None:
        """Разложить одну строку прецедента. Служебные строки сюда не заходят."""
        # Составная ячейка: номер размера и g-подпись — самостоятельные
        # токены, каждый в своём изоляте (наряд 0007, §4а).
        size = unbound_size_text(
            row.local_number, row.g_label, canon_bound=row.is_canon_bound
        )
        values = [
            # Пусто: стрелку рисует делегат по роли, а подпись, которой никто
            # не рисует, врала бы и тесту, и замеру ширин.
            "",
            iso(row.dev_number),
            iso(f"{row.date:%d.%m.%Y}"),
            iso(row.item_number),
            iso(row.revision),
            iso(row.wo),
            size,
            signed_label(row.direction, row.value),
            decision_dev_label(row.decision, short=True),
            _one_line(row.explanation),
            str(row.inspection_count),
        ]

        for column, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if column == PRECEDENT_EXPANDER_COLUMN:
                # Состояние стрелки — в роли, откуда его и берёт делегат: сверяй
                # то, чем рисуют (`CLAUDE.md` §9а).
                cell.setData(EXPANDED_ROLE, expanded in self._expanded)
            if column == PRECEDENT_ID_COLUMN:
                cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
            if column == PRECEDENT_SIZE_COLUMN and row.g_label:
                # Узкая колонка съедает имя группы — оно нужно, чтобы понять,
                # по какому канону совпало; держим в подсказке.
                cell.setToolTip(f"{row.local_number} · {row.g_label}")
            if column == PRECEDENT_SIZE_COLUMN and not row.is_canon_bound:
                mark_unbound(cell)
            if column == PRECEDENT_REVISION_COLUMN and row.other_revision:
                # Пометка выпуска — всегда при расхождении: совпадение через
                # ревизию не отсеивается никогда, только помечается. Цвет здесь
                # не ставится — он занят смыслом «нет канона» (`Search.md` v1.05).
                mark_other_revision(cell, row.revision, self._reference)
            if column == PRECEDENT_DECISION_COLUMN:
                # Код исхода рядом с подписью: пилюлю красит он. Домен
                # отдаёт в `row.decision` именно **код** — подпись из него
                # строит `decision_dev_label` строкой выше, и обратное
                # преобразование здесь красило все пилюли как «нет решения».
                cell.setData(DECISION_ROLE, row.decision)
            if column == PRECEDENT_EXPLANATION_COLUMN:
                # Обоснование в строке урезано, целиком — в подсказке: это
                # главный текст прецедента, терять его нельзя.
                cell.setToolTip(row.explanation)
            self.setItem(index, column, cell)

    def selected_deviation(self) -> int | None:
        """Выбранный прецедент; `None` — ничего или **служебная строка**.

        Служебная строка ломает допущение «строка таблицы = прецедент», на
        котором эта функция стояла: она читала `self.item(row, 0)`, а у служебной
        строки в нулевой колонке пустой держатель без роли — раньше это дало бы
        `None` случайно, а после `setSpan` могло дать и `AttributeError`. §6
        наряда `0031` требует определённого поведения, а не «как получится»:
        служебная строка прецедентом не является, и ответ на неё — `None`.

        Идентификатор берётся из колонки `Deviation` **по имени**, а не из
        нулевой: нулевая теперь раскрыватель (`CLAUDE.md` §9а.9).
        """
        row = self.currentRow()
        if row < 0 or self.is_service_row(row):
            return None
        cell = self.item(row, PRECEDENT_ID_COLUMN)
        return None if cell is None else cell.data(Qt.ItemDataRole.UserRole)


class CardDialog(QDialog):
    """Карточка одного отклонения с автообзором прецедентов."""

    def __init__(
        self, engine: Engine, deviation_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = deviation_id
        self._finding_ids: list[int] = []
        # Карточка — **окно**, а не диалог фиксированного размера: она держит
        # шапку, находки и две секции прецедентов сразу, и вертикали ей может не
        # хватить на любом наперёд заданном размере. Минимум — чтобы окно не
        # сжали в нечитаемое; область прецедентов ниже прокручивается.
        self.setMinimumSize(tokens.DIALOG_WIDE, tokens.WINDOW_MIN_HEIGHT)
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_CARD)

        # --- шапка ---
        self.number = QLabel()
        self.item_label = QLabel()
        # Ревизия рядом с деталью, только чтение: менять её — через `Edit`,
        # где выбор уже есть и работает (наряд 0024). Номер детали без
        # ревизии — дефект: он не говорит, по какому чертежу читать номера.
        self.revision_label = QLabel()
        self.wo = QLabel()
        self.machine = QLabel()
        self.quantity = QLabel()
        self.date = QLabel()
        self.ncr = QLabel()
        self.attachment = QLabel()
        self.attachment.setWordWrap(True)
        self.decision = kit.decision_badge("", None)
        self.explanation = QLabel()
        # Обоснование **копируется, не редактируясь** (§5 наряда `0032`): его
        # переносят в своё отклонение, а правка по-прежнему идёт формой. Ярлык
        # выделяется мышью и клавиатурой — это и есть «копируется»; поля ввода
        # здесь не появляется, иначе таблица стала бы редактируемой по месту,
        # что канон запрещает (§7).
        self.explanation.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.explanation.setWordWrap(True)

        # Поля не растягиваются на всю ширину: иначе значение уезжает от своей
        # подписи через полэкрана и липнет к подписи соседней колонки.
        head_left = kit.form()
        head_left.addRow("Deviation:", self.number)
        head_left.addRow("Item:", self.item_label)
        head_left.addRow("Revision:", self.revision_label)
        head_left.addRow("WO:", self.wo)
        head_left.addRow("Machine:", self.machine)
        head_right = kit.form()
        head_right.addRow("Quantity:", self.quantity)
        head_right.addRow("Date:", self.date)
        head_right.addRow("NCR:", self.ncr)
        head_right.addRow("Attachments:", self.attachment)

        # Каждая колонка — в своём виджете: соседние QFormLayout иначе делят
        # ширину так, что значение левой оказывается вплотную к подписи правой.
        head_columns = QHBoxLayout()
        head_columns.addWidget(kit.boxed(head_left), 1)
        head_columns.addWidget(kit.boxed(head_right), 1)

        decision_form = kit.form()
        # Пилюля не растягивается на ширину формы: её край и есть её форма.
        decision_row = QHBoxLayout()
        decision_row.addWidget(self.decision)
        decision_row.addStretch(1)
        decision_form.addRow("Decision:", kit.boxed(decision_row))
        decision_form.addRow("Explanation:", self.explanation)

        self.edit_button = kit.secondary("Edit…")
        self.decision_button = kit.primary("Decision…")
        self.close_button = kit.secondary("Close")
        self.edit_button.clicked.connect(self.edit_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.close_button.clicked.connect(self.reject)

        head_buttons = kit.button_row(self.edit_button, self.decision_button)

        header_box = QGroupBox("Deviation")
        header_layout = QVBoxLayout(header_box)
        header_layout.addLayout(head_columns)
        header_layout.addLayout(decision_form)
        header_layout.addLayout(head_buttons)

        # --- находки ---
        self.findings = kit.data_table(
            FINDING_COLUMNS,
            numeric_columns=FINDING_NUMERIC_COLUMNS,
            magnitude_columns=FINDING_MAGNITUDE_COLUMNS,
            widths=FINDING_WIDTHS,
        )
        hide_finding_columns(self.findings)
        self.findings.currentCellChanged.connect(lambda *_: self.refresh_precedents())

        # Три кнопки названы по объекту, который открывают, и стоят в порядке
        # рассуждения: сама находка → её исследование → её привязка к канону.
        # `Edit…` для находки не годится — он уже занят наверху отклонением, и
        # два `Edit…` на одном экране значили бы разное (доводка `0030`, Д-1).
        self.finding_button = kit.secondary("Finding…")
        self.inspect_button = kit.secondary("Inspection…")
        self.map_button = kit.secondary("Mapping…")
        self.finding_button.clicked.connect(self.open_finding)
        self.inspect_button.clicked.connect(self.open_inspection)
        self.map_button.clicked.connect(self.bind_canon)

        finding_buttons = kit.button_row(
            self.finding_button, self.inspect_button, self.map_button
        )

        self.findings_box = findings_box = QGroupBox(
            "Findings — pick a characteristic; precedents are searched by it"
        )
        findings_layout = QVBoxLayout(findings_box)
        findings_layout.addWidget(self.findings)
        findings_layout.addLayout(finding_buttons)
        # Высоту раздаёт **содержимое** (`design-system.md` §7 rev 1.13, «Only one
        # region of a dialog stretches»). Прежний жёсткий низ в 150 px давал
        # таблице с одной находкой вдвое больше нужного, и эти пикселы отнимались
        # у единственного места, ради которого карточку и открывают.
        kit.fit_table_height(self.findings, rows=FINDINGS_SHOWN)

        # --- исследования выбранной находки ---
        self.inspections = kit.data_table(INSPECTION_COLUMNS, widths=INSPECTION_WIDTHS)
        self.inspections.currentCellChanged.connect(lambda *_: self._refresh_protocol_button())
        # Двойной клик открывает **объект строки** — исследование, — как и везде
        # в этом интерфейсе: по отклонению в списке он открывает карточку, по
        # прецеденту ниже — прецедент. Вешать сюда открытие файла было ошибкой
        # (доводка 3, Д-3.1): жест «открыть запись» превращался в жест «открыть
        # чужое приложение», а у записи без протокола открывать было и нечего.
        # Файл остаётся за своей кнопкой `Open protocol…`, которая умеет быть
        # неактивной там, где файла нет.
        self.inspections.doubleClicked.connect(lambda *_: self.edit_inspection())
        self.protocol_button = kit.secondary("Open protocol…")
        self.protocol_button.clicked.connect(self.open_protocol)

        self.inspections_empty = kit.empty_state(
            NO_INSPECTIONS_TITLE, NO_INSPECTIONS_HINT, compact=True
        )
        inspections_box = QGroupBox("Inspections of the selected characteristic")
        inspections_layout = QVBoxLayout(inspections_box)
        inspections_layout.addWidget(self.inspections)
        # Кнопка и объяснение пустоты — **в одной строке** (§1 наряда `0032`):
        # пустая секция обязана быть строкой, а не коробкой с фразой посередине.
        # Кнопка стоит первой и потому не переезжает, когда исследования есть и
        # объяснение уходит: место действия не должно зависеть от наличия данных.
        empty_row = kit.button_row(self.protocol_button, stretch_at_end=False)
        empty_row.addWidget(self.inspections_empty)
        empty_row.addStretch(1)
        inspections_layout.addLayout(empty_row)
        kit.fit_table_height(self.inspections, rows=INSPECTIONS_SHOWN_IN_CARD)

        # --- прецеденты ---
        # **Одна** таблица, а не две (§3 наряда `0032`). У `same_dimension` и
        # `same_position` были одинаковые колонки — значит по норме §7 канона
        # («One level, one header») это одна таблица с групповыми строками, а
        # групповая строка вдобавок называет группу и считает её, чего шапка не
        # умела. Движок нужен ей для ленивого запроса находок при раскрытии
        # (§5 наряда `0031`).
        self.precedents = PrecedentTable(engine)
        self.precedents.doubleClicked.connect(lambda *_: self.open_precedent())
        self.precedents.itemSelectionChanged.connect(self._refresh_open_button)
        self.precedents.currentCellChanged.connect(lambda *_: self._refresh_open_button())
        # `Ctrl+C` кладёт в буфер **полное** обоснование выбранной строки
        # (§5 наряда): копируют не своё, а чужое — обоснование прецедента
        # переносят в своё отклонение, и обрезанный по ячейке текст для этого
        # бесполезен.
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.precedents)
        self.copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.copy_shortcut.activated.connect(self.copy_explanation)

        # Привязки нет — поиск по канону невозможен, и это **действие**, а не
        # пустое состояние: оператору предлагают привязать. Групповая строка
        # рядом скажет, что совпадений ноль (канон §8, наряд 0010 §4).
        self.position_hint_button = kit.secondary("Mapping…")
        self.position_hint_button.clicked.connect(self.bind_canon)
        self.position_hint_box = kit.empty_state(
            UNBOUND_TITLE, UNBOUND_HINT, self.position_hint_button
        )
        # Одно пустое состояние вместо двух: причины «прецедентов нет» больше не
        # существует — её отвечает групповая строка с нулём. Осталась причина
        # «находка не выбрана», и она про таблицу целиком.
        self.precedents_empty = kit.empty_state(
            NO_SELECTION_TITLE, NO_SELECTION_SHORT, compact=True
        )

        exact = QWidget()
        exact_layout = QVBoxLayout(exact)
        exact_layout.setContentsMargins(0, 0, 0, 0)
        exact_layout.addWidget(self.position_hint_box)
        exact_layout.addWidget(self.precedents, 1)
        exact_layout.addWidget(self.precedents_empty)

        # Вкладка описательного уровня: списка нет, есть объяснение почему.
        # Вкладка целиком — одна поверхность, значит полное пустое состояние.
        self.descriptive_hint = kit.empty_state(NOT_BUILT_TITLE, NOT_BUILT_HINT)
        similar = QWidget()
        similar_layout = QVBoxLayout(similar)
        similar_layout.setContentsMargins(0, 0, 0, 0)
        similar_layout.addWidget(self.descriptive_hint)
        similar_layout.addStretch(1)

        self.tabs = kit.slice_tabs()
        self.tabs.addTab(_scrolling(exact), EXACT_TAB)
        self.tabs.addTab(_scrolling(similar), DESCRIPTIVE_TAB)

        self.open_button = kit.secondary("Open precedent…")
        self.open_button.clicked.connect(lambda: self.open_precedent())
        self.open_button.setEnabled(False)
        # Рядом с открытием, а не в контекстном меню: перенос чужого обоснования
        # в своё отклонение — штатный ход работы, а не редкость (§5 наряда).
        self.copy_button = kit.secondary("Copy explanation")
        self.copy_button.clicked.connect(self.copy_explanation)
        self.copy_button.setEnabled(False)
        self.status = kit.status_label()

        footer = QHBoxLayout()
        footer.setSpacing(tokens.GAP_CONTROL)
        footer.addWidget(self.open_button)
        footer.addWidget(self.copy_button)
        footer.addStretch(1)
        footer.addWidget(self.close_button)

        layout = kit.dialog_layout(self)
        layout.addWidget(header_box)
        # Вкладки прецедентов — **единственная растягивающаяся область** диалога
        # (`design-system.md` §7 rev 1.13). Остальные секции занимают ровно свою
        # высоту, и всё остальное достаётся сюда.
        #
        # Нижний предел задан **видимым**, а не числом пикселей (§1 наряда
        # `0032`): две строки прецедента плюс одна раскрытая панель целиком.
        # Не помещается — растёт диалог, а не сжимается сравнение, ради которого
        # карточку открывают.
        self.tabs.setMinimumHeight(precedent_floor())
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        # На второй вкладке выдачи нет вовсе, и `_current_table` там отдаёт
        # `None` — значит и кнопка обязана гаснуть при переходе, а не оставаться
        # активной от прежней вкладки.
        self.tabs.currentChanged.connect(lambda *_: self._refresh_open_button())

        layout.addWidget(findings_box)
        layout.addWidget(inspections_box)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> None:
        """Открыть карточку. Возврата не имеет: карточка ничего не решает сама."""
        cls(engine, deviation_id, parent=parent).exec()

    # --- загрузка ---------------------------------------------------------------

    def reload(self) -> None:
        """Перечитать шапку и находки; выбор строки сохраняем, если можем."""
        previous = self._selected_finding_id()

        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            self.setWindowTitle(
                f"Deviation card — {deviation.dev_number} · {deviation.item.item_number}"
            )
            self.number.setText(iso(deviation.dev_number))
            self.item_label.setText(iso(deviation.item.item_number))
            self.revision_label.setText(iso(deviation.revision.designation))
            self.wo.setText(iso(deviation.wo))
            self.machine.setText(iso(deviation.machine or "—"))
            self.quantity.setText(iso(str(deviation.quantity)))
            self.date.setText(iso(f"{deviation.date:%d.%m.%Y}"))
            self.ncr.setText(iso(deviation.ncr or "—"))
            self.attachment.setText(iso(deviation.attachment or "—"))
            code = deviation.decision_dev
            # Пилюля — тот же компонент, что и в колонке списка: одно значение
            # не имеет права выглядеть на двух экранах по-разному.
            kit.paint_badge(self.decision, decision_dev_label(code), code)
            self.explanation.setText(deviation.explanation or "—")

            findings = _load_findings(session, deviation)
            counts = inspection_counts(session, findings)
            canon = canon_labels(session, [f.characteristic for f in findings])
            rows = [
                (
                    finding.finding_id,
                    finding.characteristic.local_number,
                    canon.get(finding.characteristic_id, CANON_NEW),
                    finding.direction,
                    finding.value,
                    finding.dimension_point,
                    finding.zone.name if finding.zone else "",
                    finding.deviation_type.name if finding.deviation_type else "",
                    counts.get(finding.finding_id, 0),
                    finding.outcome,
                )
                for finding in findings
            ]

        self._finding_ids = [row[0] for row in rows]
        self.findings.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                iso(row[1]),
                iso(row[2]),
                signed_label(row[3], row[4]),
                row[6],
                row[7],
                "" if row[5] is None else iso(str(row[5])),
                # Исход — перед счётчиком исследований, тем же порядком, что и в
                # форме отклонения: суждение, а исследования лишь сведения к нему.
                outcome_label(row[9]),
                str(row[8]),
            )
            for column, value in enumerate(values):
                self.findings.setItem(index, column, QTableWidgetItem(value))

        if rows:
            restored = self._finding_ids.index(previous) if previous in self._finding_ids else 0
            # Сигнал глушим: иначе выбор строки и явный вызов ниже дают две
            # перерисовки прецедентов, то есть два лишних похода в базу.
            self.findings.blockSignals(True)
            self.findings.setCurrentCell(restored, 0)
            self.findings.blockSignals(False)
        # Высота **после** наполнения, а не при сборке: в конструкторе строк ещё
        # нет, и посчитанная там высота была бы высотой пустой таблицы. Ровно
        # на этом первая попытка и дала ноль — поймал замер, не тест.
        kit.fit_table_height(self.findings, rows=FINDINGS_SHOWN)
        self.refresh_precedents()

    def refresh_precedents(self) -> None:
        """Перерисовать обе вкладки и таблицу исследований под выбранную находку."""
        finding_id = self._selected_finding_id()
        self._refresh_buttons(finding_id)
        self._refresh_inspections(finding_id)

        if finding_id is None:
            self.precedents.fill([])
            self.precedents.setVisible(False)
            self.position_hint_box.setVisible(False)
            # Причина пустоты здесь другая — «находка не выбрана», а не
            # «совпадений нет»: второе отвечает групповая строка, и подменять
            # одно другим значит объяснять оператору не то, что он видит.
            kit.set_empty_reason(
                self.precedents_empty, NO_SELECTION_TITLE, NO_SELECTION_SHORT
            )
            self.precedents_empty.setVisible(True)
            # Заглушка описательной вкладки от выбора находки не зависит вовсе:
            # там нечего искать ни при какой выбранной строке.
            self.status.setText(NO_SELECTION_HINT)
            self._refresh_open_button()
            return

        with session_scope(self._engine) as session:
            finding = session.get(Finding, finding_id)
            characteristic = finding.characteristic
            deviation = finding.deviation
            bound = characteristic.mapping is not None
            position = (
                f"g{characteristic.mapping.g_position.g_index}" if bound else None
            )

            same_dimension = precedents_same_dimension(
                session, characteristic, exclude_deviation=deviation
            )
            same_position = precedents_same_position(
                session, characteristic, exclude_deviation=deviation
            )
            local_number = characteristic.local_number
            reference_revision = characteristic.revision.designation

        # Групповые строки несут ровно те формулировки, что стояли подписями
        # секций: они называют **как совпало**, а не чья деталь (`Search.md`
        # v1.04). Разница в том, что теперь они ещё и считают свою группу.
        #
        # Группа с нулём строк **показывается** (§3 наряда `0032`): «совпадений
        # нет» — это ответ, а его отсутствие оператор прочтёт как «поиск не
        # работал».
        groups = [
            PrecedentGroup(
                key="dimension",
                title=(
                    f"By number: no. {local_number}, all revisions of this item "
                    f"({len(same_dimension)})"
                ),
                rows=tuple(same_dimension),
            ),
            PrecedentGroup(
                key="position",
                title=(
                    f"By canon: position {position} — other items and other "
                    f"revisions ({len(same_position)})"
                    if bound
                    else "By canon: this characteristic is not bound (0)"
                ),
                rows=tuple(same_position) if bound else (),
                note="" if bound else UNBOUND_HINT,
            ),
        ]
        self.precedents.fill(groups, reference=reference_revision)
        self.precedents.setVisible(True)
        self.precedents_empty.setVisible(False)
        # Привязки нет — предлагаем её сделать. Это действие, а не объяснение
        # пустоты: пустоту уже объяснила групповая строка с нулём.
        self.position_hint_box.setVisible(not bound)

        exact_total = len(same_dimension) + len(same_position)
        self.tabs.setTabText(0, f"{EXACT_TAB}  {exact_total}")

        # Автоперехода на вторую вкладку больше нет: там нет выдачи, и уводить
        # туда оператора при пустом L1 значит показывать ему объяснение вместо
        # ответа на вопрос «случалось ли такое».
        self._refresh_open_button()

        self.status.setText(
            f"Exact matches: {exact_total}. "
            "Only deviations that already carry a decision are listed."
        )

    def _refresh_inspections(self, finding_id: int | None) -> None:
        """Исследования выбранной находки: **тип и короткий вывод**.

        Позиции здесь больше нет (`Inspection.md` rev 1.03): суждение по размеру
        переехало на находку и живёт колонкой в таблице находок выше.

        Читаются на выбор строки, а не на открытие карточки: свёрнутому экрану
        от исследования нужен один признак — счётчик в колонке находок, он уже
        посчитан пакетом (решение 7 QMS-018).
        """
        rows: list[tuple[int, str, str, str]] = []
        if finding_id is not None:
            with session_scope(self._engine) as session:
                finding = session.get(Finding, finding_id)
                rows = [
                    (
                        inspection.inspection_id,
                        inspection.type.name,
                        inspection.conclusion or "",
                        bool(inspection.no_protocol),
                    )
                    for inspection in sorted(
                        finding.inspections, key=lambda i: i.insp_number
                    )
                ]

        self.inspections.setRowCount(len(rows))
        for index, (inspection_id, kind, conclusion, no_protocol) in enumerate(rows):
            values = (kind, _one_line(conclusion))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, inspection_id)
                if column == INSPECTION_CONCLUSION_COLUMN and conclusion:
                    # Вывод в строке урезан, целиком — в подсказке: тот же приём,
                    # что у обоснования решения, отдельного механизма нет.
                    cell.setToolTip(conclusion)
                if column == 0:
                    cell.setData(NO_PROTOCOL_ROLE, no_protocol)
                self.inspections.setItem(index, column, cell)
            if no_protocol:
                # Запись без протокола читается **полноценно** (§4 наряда 0029):
                # тип, позиция, вывод. Пометка ставится приглушённой подсказкой у
                # типа, а не отдельной колонкой: колонка ради признака у одной
                # записи из десяти — это счётчик там, где показано содержимое.
                self.inspections.item(index, 0).setToolTip(NO_PROTOCOL_HINT)

        self.inspections.setVisible(bool(rows))
        self.inspections_empty.setVisible(not rows)
        # Пустая секция — **одна строка** пустого состояния, а не коробка с
        # фразой посередине (§1 наряда `0032`): у скрытой таблицы высота ноль,
        # и вертикаль достаётся сравнению.
        kit.fit_table_height(self.inspections, rows=INSPECTIONS_SHOWN_IN_CARD)
        self._refresh_protocol_button()

    def _refresh_protocol_button(self) -> None:
        """Кнопка неактивна там, где **файла нет**, а не там, где выбор пуст.

        §4 наряда 0029: у записи без протокола открывать нечего, и это не отказ, а
        отсутствие. Причину неактивности объясняет подсказка самой кнопки —
        неактивная кнопка без слов читается как поломка.
        """
        row = self.inspections.currentRow()
        cell = self.inspections.item(row, 0) if row >= 0 else None
        without = bool(cell.data(NO_PROTOCOL_ROLE)) if cell is not None else False
        self.protocol_button.setEnabled(
            self._selected_inspection_id() is not None and not without
        )
        self.protocol_button.setToolTip(NO_PROTOCOL_HINT if without else "")

    def _selected_inspection_id(self) -> int | None:
        # На видимость таблицы не смотрим: у ребёнка непоказанного окна
        # `isVisible()` ложно всегда, и кнопка «открыть протокол» оказалась бы
        # мёртвой в любом тесте (`CLAUDE.md` §9а.5). Пустая таблица и так даёт
        # `currentRow() == -1`.
        row = self.inspections.currentRow()
        if row < 0:
            return None
        cell = self.inspections.item(row, 0)
        return None if cell is None else cell.data(Qt.ItemDataRole.UserRole)

    def open_protocol(self) -> None:
        """Открыть файл протокола системным приложением.

        Существование проверяется **здесь**, а не при вводе: канон запрещает
        проверку на входе (протокол может лежать на недоступном в тот момент
        ресурсе, `Inspection.md` rev 1.01), но ссылка, которую нельзя открыть и
        которая об этом молчит, — просто текст.
        """
        inspection_id = self._selected_inspection_id()
        if inspection_id is None:
            return
        with session_scope(self._engine) as session:
            protocol = session.get(Inspection, inspection_id).protocol

        # Вторая сторона Д-3.2. Первая — что для такой записи действие вообще
        # недоступно: кнопка выключена, а двойной клик сюда больше не ведёт. Но
        # «недоступно» держится на состоянии экрана, и одного этого мало: с
        # наряда `0029` пустой протокол — **законное** состояние записи, и
        # функция обязана отвечать на него словами сама, откуда бы её ни позвали.
        # До `0029` `None` не возникал, поэтому `Path(protocol)` и падал
        # `TypeError` — регрессия ровно того рода, которую ловит листинг
        # потребителей поля, а не память.
        if not (protocol or "").strip():
            kit.show_error(self, _protocol_absent(), title="No protocol to open")
            return

        path = Path(protocol)
        if not path.exists():
            kit.show_error(self, _protocol_missing(protocol), title="Protocol not opened")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            kit.show_error(self, _protocol_not_opened(protocol), title="Protocol not opened")

    def _refresh_buttons(self, finding_id: int | None) -> None:
        """Действия по находке — только при выбранной строке (закрытие Δ S4-в)."""
        self.finding_button.setEnabled(finding_id is not None)
        self.inspect_button.setEnabled(finding_id is not None)
        self.map_button.setEnabled(finding_id is not None)

    def _selected_finding_id(self) -> int | None:
        row = self.findings.currentRow()
        if 0 <= row < len(self._finding_ids):
            return self._finding_ids[row]
        return None

    # --- действия ---------------------------------------------------------------

    def edit_deviation(self) -> None:
        """Правка — существующая форма S4; карточка перечитывается по возврату."""
        DeviationDialog.run(self._engine, self._deviation_id, self)
        self.reload()

    def set_decision(self) -> None:
        """Тот же `DecisionDialog`, что и в списке, — без единой правки."""
        if DecisionDialog.run(self._engine, self._deviation_id, self):
            self.reload()

    def open_finding(self) -> None:
        """Правка находки прямо отсюда — **та же** форма, что и в форме отклонения.

        Повод (доводка `0030`, Д-1): колонка `Outcome` показывала `Not decided`, а
        проставить исход из карточки было нечем — путь шёл через закрытие карточки,
        `Open…`, поиск находки и вход в неё. Четыре действия и уход с экрана, на
        котором инженер как раз изучает прецеденты; смысл карточки в том, чтобы
        ввод стоял там же, где происходит рассуждение.

        Второй формы не заводится — `FindingDialog` уже умеет сохранённую находку:
        номер размера она запирает, потому что другой размер это другая находка.
        Отличие от формы отклонения одно и существенное: там правки копятся в
        таблице и уходят в базу разом при сохранении отклонения, а здесь запись
        **немедленная**, и идёт она через `update_finding` — единственный путь в
        базу проходит доменом (`CLAUDE.md` §9а.18), иначе инвариант, который
        держит домен, обходится молча.

        Он же здесь и срабатывает: перевод находки в `not_permitted` под
        `approved` отбивается доменом, и отказ обязан дойти до оператора окном, а
        не пропасть — правка при этом не применяется.
        """
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return

        with session_scope(self._engine) as session:
            finding = session.get(Finding, finding_id)
            item_id = finding.deviation.item_id
            row = FindingRow(
                local_number=finding.characteristic.local_number,
                direction=finding.direction,
                value=finding.value,
                dimension_point=finding.dimension_point,
                comment=finding.comment,
                zone_id=finding.zone_id,
                deviation_type_id=finding.deviation_type_id,
                finding_id=finding.finding_id,
                inspections=len(finding.inspections),
                outcome=finding.outcome,
            )

        dialog = FindingDialog(self._engine, item_id, row, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.row is None:
            return

        edited = dialog.row
        try:
            with session_scope(self._engine) as session:
                update_finding(
                    session,
                    session.get(Finding, finding_id),
                    direction=edited.direction,
                    value=edited.value,
                    dimension_point=edited.dimension_point,
                    comment=edited.comment,
                    zone=(
                        session.get(RefZone, edited.zone_id) if edited.zone_id else None
                    ),
                    deviation_type=(
                        session.get(RefDeviationType, edited.deviation_type_id)
                        if edited.deviation_type_id
                        else None
                    ),
                    outcome=edited.outcome,
                )
        except Exception as error:
            kit.show_error(self, error, title="Finding not saved")
            return
        self.reload()

    def open_inspection(self) -> None:
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return
        if InspectionDialog.run(self._engine, finding_id, None, self):
            self.reload()

    def edit_inspection(self) -> None:
        """Открыть **выбранное** исследование — та же форма, что заводит новое.

        Кнопка `Inspection…` заводит новую запись по выбранной находке; двойной
        клик по строке правит ту запись, по которой кликнули (доводка 3, Д-3.1).
        Разные действия, одна форма — различает их `inspection_id`.
        """
        inspection_id = self._selected_inspection_id()
        if inspection_id is None:
            return
        with session_scope(self._engine) as session:
            finding_id = session.get(Inspection, inspection_id).finding_id
        if InspectionDialog.run(self._engine, finding_id, inspection_id, self):
            self.reload()

    def bind_canon(self) -> None:
        """Ранняя привязка R2 — тот же диалог, что везде.

        После возврата карточка перечитывается целиком: привязка меняет и колонку
        «канон», и секцию L1b — ради неё привязку и делают.
        """
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return
        with session_scope(self._engine) as session:
            item_id = session.get(Finding, finding_id).deviation.item_id

        cg_id = choose_cg_for_item(self, self._engine, item_id)
        if cg_id is None:
            return
        open_mapping(self._engine, self, item_id, cg_id)
        self.reload()

    def open_precedent(self, table: PrecedentTable | None = None) -> None:
        """Открыть карточку прецедента поверх текущей — глубина не ограничена.

        Аргумент остался ради прежних точек вызова: таблица теперь **одна**
        (§3 наряда `0032`), и выбирать между двумя больше не надо. Сведение
        `_active_table` / `_on_table_selected` ушло вместе со второй таблицей —
        оно и существовало только затем, чтобы кнопка не открывала «первую
        непустую» из двух.
        """
        deviation_id = self.precedents.selected_deviation()
        if deviation_id is None:
            self.status.setText("Select a precedent row in the table first.")
            return
        try:
            CardDialog.run(self._engine, deviation_id, self)
        except Exception as error:  # pragma: no cover - защита от битой ссылки
            kit.show_error(self, error, title="Precedent not opened")

    def copy_explanation(self) -> None:
        """Положить в буфер **полное** обоснование выбранного прецедента (§5).

        Копируют не своё, а **чужое**: обоснование прецедента переносят в своё
        отклонение. Поэтому берётся текст из выдачи, а не из ячейки — ячейка
        урезана до одной строки и обрезана по ширине колонки, и скопированный из
        неё текст пришлось бы дописывать руками, то есть копирование не
        сэкономило бы ничего.

        Правка по месту от этого не появляется (§7 канона): копирование ею не
        является — из таблицы только читают.
        """
        text = self._selected_explanation()
        if not text:
            return
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        QApplication.clipboard().setText(text)
        self.status.setText("Explanation copied to the clipboard.")

    def _selected_explanation(self) -> str:
        """Обоснование выбранной строки — из **выдачи**, а не из ячейки."""
        deviation_id = self.precedents.selected_deviation()
        if deviation_id is None:
            return ""
        for group in self.precedents.groups():
            for row in group.rows:
                if row.deviation_id == deviation_id:
                    return row.explanation or ""
        return ""

    def _refresh_open_button(self) -> None:
        """Действия по прецеденту активны ровно тогда, когда есть что открывать.

        §6 наряда `0031` и §3 наряда `0032`: на служебной строке — и на строке
        панели, и на **групповой** — действие обязано быть недоступно, а не
        отвечать отказом после нажатия. Признак берётся у той же функции,
        которая потом и открывает, — иначе кнопка и действие разошлись бы на
        первой же правке одного из них.

        Обе кнопки гаснут вместе: обе действуют на выбранный прецедент, и
        состояние, в котором одна доступна, а другая нет, значило бы, что
        «выбранная строка» у них разная.
        """
        # На второй вкладке выдачи нет вовсе — открывать нечего, и брать строку
        # с невидимой вкладки кнопка не должна.
        on_results = self.tabs.currentIndex() == 0
        ready = on_results and self.precedents.selected_deviation() is not None
        self.open_button.setEnabled(ready)
        self.copy_button.setEnabled(ready and bool(self._selected_explanation()))


def _load_findings(session, deviation: Deviation) -> list[Finding]:
    """Находки со всем, что рисует строка, — фиксированным числом запросов.

    Размер, его привязка к канону, зона и тип тянутся `selectinload`: обращение
    к связи в цикле и есть `N+1`, снятие которого — отдельный критерий наряда.
    """
    findings = session.scalars(
        select(Finding)
        .where(Finding.deviation_id == deviation.deviation_id)
        .options(
            selectinload(Finding.characteristic).selectinload(Characteristic.mapping),
            selectinload(Finding.zone),
            selectinload(Finding.deviation_type),
        )
    ).all()
    return sorted(findings, key=lambda f: dimension_sort_key(f.characteristic.local_number))


def _scrolling(content: QWidget) -> QScrollArea:
    """Обернуть вкладку в прокрутку: секции сохраняют свою высоту, а не делят её.

    Без этого две секции прецедентов делили остаток вертикали, и второй
    доставалась строка с половиной (ревью 0011, О-6). Полоса появляется только
    когда содержимое действительно не помещается.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(content)
    return area


def _one_line(text: str | None) -> str:
    """Обоснование в одну строку — в таблице многострочный текст рвёт вёрстку."""
    return " ".join((text or "").split())


def _protocol_absent() -> Exception:
    """Протокола у записи нет вовсе — это **не** ошибка, а объявленное состояние.

    Отдельно от `_protocol_missing`: там путь записан, а файла по нему нет — сбой,
    который надо чинить правкой ссылки. Здесь файла нет **по решению инженера**
    (галочка `No protocol`, наряд `0029`), и вся запись — её вывод. Свалить два
    случая в одно сообщение значило бы объяснять оператору не то, что он видит.
    """
    from domain.errors import ValidationError

    return ValidationError(
        "This inspection has no protocol file — “No protocol” is set on it, and "
        "its conclusion is the record. Open the inspection to read it."
    )


def _protocol_missing(protocol: str) -> Exception:
    """Файла нет по записанному пути — говорим это словами, а не молчим."""
    from domain.errors import ValidationError

    return ValidationError(
        f"The protocol file is not there:\n{protocol}\n\n"
        "The path is stored as it was typed and is never checked on entry — the "
        "file may have moved, or the share may be unreachable from this machine. "
        "Open the inspection and correct the link."
    )


def _protocol_not_opened(protocol: str) -> Exception:
    """Файл на месте, но система его не открыла — обычно нечем."""
    from domain.errors import ValidationError

    return ValidationError(
        f"The system could not open this file:\n{protocol}\n\n"
        "There is probably no application associated with this file type."
    )


__all__ = ["CANON_NEW", "CANON_UNBOUND", "CardDialog", "PrecedentTable"]
