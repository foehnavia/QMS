"""Форма «Добавить деталь»: классификаторы и группа, к которой деталь относится.

`connection_type` и `size` предвыбраны как `General` — деталь заводится и когда
специфика ещё не важна (`Item.md`).

**Номера размеров эта форма не спрашивает** (наряд 0018, находка №13 прогона).
Она разворачивала таблицу g-позиций и ждала локальный номер на каждую, но
чертежа группы не показывала: у оператора оставались индекс `gN`, который без
чертежа ни на что не отображается, и номинал, который размер **не
идентифицирует** — на чертеже он повторяется. Привязка по номиналу закрепляла
неверную пару «локальный номер ↔ g-позиция», а на ней держится весь
перекрёстный поиск.

Поэтому привязка делается там, где для неё есть чертёж, — в `MappingDialog`, и
делается **сразу**: `complete_new_item` открывает её следом за формой. Деталь с
назначенной группой не существует в базе с неполной привязкой (§1a наряда):
отказ от привязки отменяет заведение.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QWidget,
)
from sqlalchemy import Engine, select

from db.models import (
    GENERAL,
    CharacteristicGroup,
    Item,
    RefConnectionType,
    RefItemType,
    RefSize,
)
from db.session import session_scope
from domain.groups import list_groups
from domain.items import create_item, discard_item, update_item
from domain.mappings import binding_state, is_complete
from domain.reference import list_values

from . import kit
from .cg_dialog import CgDialog
from .common import bind_direction, iso, joined, optional_id
from .kit import tokens
from .mapping_dialog import MappingDialog

NO_GROUP = "— no group —"
NO_TYPE = "— not set —"

GROUP_HINT = (
    "The group answers which canon the item belongs to. Its positions are "
    "mapped right after this form, against the group drawing — the local "
    "numbers are not asked for here."
)

#: Вопрос при отказе от привязки на заведении (§3.3 наряда 0018).
DISCARD_TITLE = "Mapping is not complete"
DISCARD_QUESTION = (
    "Mapping is not complete — the item will not be created. Close anyway?"
)

#: Предупреждение у **ранее заведённой** детали (§3.3a): откат здесь невозможен,
#: и запрет производил бы ложные данные — оператор выходил бы из окна, вписав
#: номер наугад. Конечное решение — Q-15.
INCOMPLETE_TITLE = "Mapping stays incomplete"
BACK_TO_MAPPING = "Back to mapping"
CLOSE_ANYWAY = "Close anyway"


class ItemDialog(QDialog):
    """Форма детали: заведение и правка. После accept() номер — в `created_number`.

    **Правка появилась потому, что номер был неисправим** (ревью наряда 0012,
    В-2): форма умела только создавать, и опечатка в реальном каталожном номере
    лечилась перезаливкой базы — то есть останавливала прогон на шаге 5.

    В правке строка группы не показывается: группа детали выводится из привязок
    её размеров, а перепривязка существующей детали — своя работа со своими
    гарантиями (снимок состояния, реестр конфликтов), и она вынесена в Q-15.

    После accept() наружу отдаются `created_item_id` и `created_group_id` — то,
    что нужно следующему шагу: открыть привязку именно этой детали к именно
    этой группе. `created_number` остаётся: на него завязан второй вход
    (`deviation_dialog.create_item`).
    """

    def __init__(
        self,
        engine: Engine,
        item_id: int | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = optional_id(item_id, "item_id")
        self.created_number: str | None = None
        #: Заведённая деталь и выбранная группа — вход в обязательную привязку.
        self.created_item_id: int | None = None
        self.created_group_id: int | None = None
        self.setWindowTitle("New item" if self._item_id is None else "Edit item")
        # Форма стала короткой: пять полей и подсказка. Прежняя высота держала
        # таблицу позиций, которой больше нет.
        self.resize(tokens.DIALOG_MEDIUM, tokens.DIALOG_HEIGHT_SHORT)

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText('e.g. C1-08375A (מק"ט)')
        bind_direction(self.number_edit)

        self.item_type = _combo()
        self.connection_type = _combo()
        self.size = _combo()
        self.group = _combo()

        new_group = kit.secondary("Create group…")
        new_group.clicked.connect(self.create_group)

        group_row = QHBoxLayout()
        group_row.setSpacing(tokens.GAP_CONTROL)
        group_row.addWidget(self.group, 1)
        group_row.addWidget(new_group)

        self.buttons = kit.dialog_buttons(
            accept="Create item" if item_id is None else "Save item"
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        self.group_hint = kit.hint(GROUP_HINT)
        self.group_row = kit.boxed(group_row)

        form = kit.stretching_form()
        form.addRow("Item number:", self.number_edit)
        form.addRow("Item type:", self.item_type)
        form.addRow("Connection type:", self.connection_type)
        form.addRow("Size class:", self.size)
        self.group_label = "Characteristic group:"
        form.addRow(self.group_label, self.group_row)

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        layout.addWidget(self.group_hint)
        layout.addStretch(1)
        layout.addWidget(self.buttons)

        self.reload_reference()
        if self._item_id is not None:
            self._load(self._item_id)

    @classmethod
    def run(
        cls, engine: Engine, item_id: int | None = None, parent: QWidget | None = None
    ) -> bool:
        """Открыть форму; `True` — деталь заведена или правка сохранена.

        **Привязку эта точка не доводит.** Её зовёт правка детали
        (`item_view.edit_item`), где привязывать нечего. Заведение идёт двумя
        входами, и оба продолжают форму `complete_new_item`: деталь с
        назначенной группой не существует с неполной привязкой (наряд 0018 §1a).
        Заводить деталь отсюда — значит обойти это правило молча.
        """
        return cls(engine, item_id, parent=parent).exec() == QDialog.DialogCode.Accepted

    # --- наполнение ------------------------------------------------------------

    def _load(self, item_id: int) -> None:
        """Прочитать деталь в форму и убрать засев: он относится к заведению."""
        with session_scope(self._engine) as session:
            item = session.get(Item, item_id)
            self.number_edit.setText(item.item_number)
            _select_text(self.item_type, item.item_type.name if item.item_type else NO_TYPE)
            _select_text(self.connection_type, item.connection_type.name)
            _select_text(self.size, item.size.name)

        self.group_row.setVisible(False)
        self.group_hint.setVisible(False)
        form = self.layout().itemAt(0).layout()
        for row in range(form.rowCount()):
            label = form.itemAt(row, form.ItemRole.LabelRole)
            if label is not None and label.widget() is not None:
                if label.widget().text().startswith("Characteristic group"):
                    label.widget().setVisible(False)

    def reload_reference(self, keep_group: str | None = None) -> None:
        """Перечитать справочники и список групп."""
        with session_scope(self._engine) as session:
            item_types = [value.name for value in list_values(session, RefItemType)]
            connections = [value.name for value in list_values(session, RefConnectionType)]
            sizes = [value.name for value in list_values(session, RefSize)]
            groups = [group.name for group in list_groups(session)]

        _fill(self.item_type, [NO_TYPE, *item_types], NO_TYPE)
        _fill(self.connection_type, connections, GENERAL)
        _fill(self.size, sizes, GENERAL)
        _fill(self.group, [NO_GROUP, *groups], keep_group or NO_GROUP)

    # --- действия --------------------------------------------------------------

    def create_group(self) -> None:
        """R3 — недостающую группу можно завести прямо отсюда."""
        dialog = CgDialog(self._engine, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_name:
            self.reload_reference(keep_group=dialog.created_name)

    def save(self) -> None:
        item_type_name = self.item_type.currentText()
        group_name = self.group.currentText()
        try:
            with session_scope(self._engine) as session:
                fields = dict(
                    item_number=self.number_edit.text(),
                    item_type=(
                        None
                        if item_type_name == NO_TYPE
                        else _by_name(session, RefItemType, item_type_name)
                    ),
                    connection_type=_by_name(
                        session, RefConnectionType, self.connection_type.currentText()
                    ),
                    size=_by_name(session, RefSize, self.size.currentText()),
                )
                if self._item_id is None:
                    item = create_item(session, **fields)
                    # Размеры здесь не заводятся: их создаст привязка
                    # (`mappings.bind`), и она же скажет, какой номер чей.
                    self.created_item_id = item.item_id
                    if group_name != NO_GROUP:
                        group = session.scalar(
                            select(CharacteristicGroup).where(
                                CharacteristicGroup.name == group_name
                            )
                        )
                        self.created_group_id = group.cg_id
                else:
                    item = update_item(session, session.get(Item, self._item_id), **fields)
                self.created_number = item.item_number
        except Exception as error:
            kit.show_error(self, error)
            return
        self.accept()


# --- привязка как часть заведения (наряд 0018 §3.2, §3.3) --------------------------


def mapping_gap(engine: Engine, item_id: int, cg_id: int) -> list[str]:
    """Позиции группы, оставшиеся без состояния у этой детали.

    Пустой список — привязка полна. Спрашиваем **домен**, а не диалог: диалог
    мог быть закрыт любой кнопкой, а вопрос стоит один — есть ли у каждой
    g-позиции либо номер размера, либо код 99 (`mappings.is_complete`).
    """
    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        group = session.get(CharacteristicGroup, cg_id)
        states = binding_state(session, item, group)
        if is_complete(states):
            return []
        return [f"g{state.g_index}" for state in states if not state.is_decided]


def complete_new_item(
    engine: Engine, parent: QWidget | None, item_id: int | None, cg_id: int | None
) -> bool:
    """Довести заведение детали привязкой к канону. `False` — деталь откачена.

    Правило §1a наряда 0018: **деталь с назначенной группой не существует в базе
    с неполной привязкой**. Привязка — часть заведения, а не следующий за ним
    шаг: в форме находки известен только локальный номер размера, и если
    привязка неполна, размер молча заведётся как не-CG, отклонение ляжет мимо
    канона, а обнаружится это позже — когда секция L1b не найдёт того, что
    обязана была найти.

    Записать всё одной транзакцией нельзя: диалог привязки пишет по действию
    (ратификация S3, наряд её менять не разрешает). Поэтому правило держится с
    другой стороны — **отказ от привязки отменяет заведение** (`discard_item`).

    Живёт одной функцией на оба входа — «New item» на экране деталей и
    «Create item…» в форме отклонения: два места с одинаковым поведением
    разошлись бы на первой же правке.
    """
    if item_id is None or cg_id is None:
        # Группа не выбрана — привязывать нечего, деталь заведена как обычно.
        return True

    while True:
        MappingDialog.run(engine, item_id, cg_id, parent=parent)
        if not mapping_gap(engine, item_id, cg_id):
            return True

        # Спрашиваем **до** отката: закрытое окно бывает и промахом мыши.
        answer = QMessageBox.question(
            parent,
            DISCARD_TITLE,
            DISCARD_QUESTION,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            continue  # «нет» возвращает в привязку

        try:
            with session_scope(engine) as session:
                discard_item(session, session.get(Item, item_id))
        except Exception as error:
            kit.show_error(parent, error, title="Item not discarded")
        return False


def incomplete_mapping_text(gap: list[str], item_number: str) -> str:
    """Текст предупреждения §3.3a — отдельной функцией, чтобы его можно было сверить.

    Перечень позиций собирается `joined`: каждый ярлык в своём изоляте, порядок
    достаётся базовому направлению строки (`CLAUDE.md` §9). Номер детали —
    отдельный токен и тоже в изоляте: он бывает любым.
    """
    verb = "have" if len(gap) > 1 else "has"
    return (
        f"{joined(*gap, sep=', ')} {verb} no state. "
        f"The mapping of item {iso(item_number)} stays incomplete."
    )


def warn_incomplete_mapping(
    engine: Engine, parent: QWidget | None, item_id: int, cg_id: int
) -> bool:
    """Предупредить о неполной привязке **ранее заведённой** детали (§3.3a).

    Здесь откат невозможен: записи уже лежат, прежнее состояние нигде не
    сохранено, а сеанс привязки по построению не транзакционен. Запрет был бы
    вреден — оператор, открывший привязку посмотреть, выходил бы из окна, вписав
    номер наугад или поставив 99 там, где позиция у детали есть, то есть гейт
    производил бы ложные данные.

    Поэтому предупреждение без запрета, с перечнем нерешённых позиций.
    Возвращает `True`, если оператор захотел вернуться в привязку.

    **Это временная мера.** Снимок состояния до правки, предупреждение о
    ссылках на размер и реестр конфликтов — требование пользователя от
    2026-09-03, разбирается в Q-15; данный наряд этой машинерии не строит.
    """
    gap = mapping_gap(engine, item_id, cg_id)
    if not gap:
        return False

    with session_scope(engine) as session:
        number = session.get(Item, item_id).item_number

    box = QMessageBox(parent)
    box.setWindowTitle(INCOMPLETE_TITLE)
    box.setText(incomplete_mapping_text(gap, number))
    back = box.addButton(BACK_TO_MAPPING, QMessageBox.ButtonRole.RejectRole)
    box.addButton(CLOSE_ANYWAY, QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    return box.clickedButton() is back


# --- мелкие помощники ------------------------------------------------------------


def _combo():
    from PySide6.QtWidgets import QComboBox

    return QComboBox()


def _fill(combo, names: list[str], preselect: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(names)
    index = combo.findText(preselect)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def _select_text(combo, text: str) -> None:
    """Отметить значение по подписи; нет такого — оставить как есть."""
    index = combo.findText(text)
    if index >= 0:
        combo.setCurrentIndex(index)


def _readonly(text: str, payload=None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if payload is not None:
        item.setData(Qt.ItemDataRole.UserRole, payload)
    return item


def _format_number(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _by_name(session, model: type, name: str):
    return session.scalar(select(model).where(model.name == name))
