"""`combo` — поле выбора одного значения из **длинного** списка, с отбором.

Находка №17 прогона QMS-016. Обычный `QComboBox` на трёхстах деталях ведёт себя
так, как ему и положено, и это не годится: первая набранная буква перемещает
отметку, но список не сужает; вторая начинает поиск заново, а не уточняет
первую; буква, которой нет ни в одной записи, не делает ничего молча; строки
ввода, которую можно стереть, у элемента нет вовсе.

Решение пользователя (2026-09-03): отбор **прямо в поле**, а не отдельным окном.
Отклонений за смену много, и лишнее окно на каждом — плата, которую платить не
за что. Модальный `PickerDialog` остаётся там, где выбор идёт не внутри формы, а
вопросом перед действием (`pickers.choose_cg_for_item`).

Границы — те же, что у `PickerDialog`, и по той же причине (запрет §3а наряда
0010 про **аппарат экрана**: поиск по выдаче, срезы, чипы, экспорт; отбор внутри
поля сужает выбор одного значения, а не меняет, чем список является):

* одна строка отбора, по вхождению подстроки, регистронезависимо;
* отбор **не переживает закрытие списка** — открыл заново, список полон;
* значение поля — всегда ключ из списка, набранный текст значением не станет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QWidget

from .direction import bind_direction, directional, iso


class FilterCombo(QComboBox):
    """Выпадающий список, который сужается по набранному.

    Наружу отдаёт **ключ** (`currentData()`), как и обычный список до него, —
    вызывающий код смысла не меняет.
    """

    #: Выбор сменился. Своим сигналом, а не `currentIndexChanged`: тот срабатывает
    #: и на перестройку списка отбором, когда оператор ничего не выбирал.
    keyChanged = Signal(object)

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Родной автодополнитель здесь мешает: он дописывает текст за оператора
        # и спорит с нашей перестройкой списка. Отбор делаем сами.
        self.setCompleter(None)

        #: Полный набор `(ключ, подпись)` — источник правды, из него строится
        #: любой показ. Отбор его не трогает.
        self._rows: list[tuple[object, str]] = []
        #: Выбранное значение. Живёт **отдельно** от текущей строки списка:
        #: список во время отбора сужен, а выбор от этого меняться не должен.
        self._key: object | None = None
        self._explaining = False

        edit = self.lineEdit()
        edit.setPlaceholderText(placeholder)
        # Каталожные номера латинские, значения справочников бывают ивритскими —
        # направление поля следует за набранным, а не за окном (канон §6).
        bind_direction(edit)
        # Строка списка разворачивается по своему содержимому — тем же делегатом,
        # что и всякий список в наборе.
        directional(self.view())

        # `textEdited`, а не `textChanged`: перестраивает список только правка
        # оператора, а не наши же `setText` при восстановлении.
        edit.textEdited.connect(self._on_typed)
        edit.editingFinished.connect(self.settle)
        self.activated.connect(self._remember)

    # --- содержимое ------------------------------------------------------------

    def set_rows(self, rows: list[tuple[object, str]], *, key: object | None = None) -> None:
        """Задать полный набор значений и, если надо, выбрать одно из них.

        Ключ, которого в новом наборе нет, снимается: показывать выбранным то,
        чего в списке больше не существует, — обещать несуществующее.
        """
        self._rows = list(rows)
        known = {row[0] for row in self._rows}
        if key is not None:
            self._key = key if key in known else None
        elif self._key not in known:
            self._key = None
        self.settle()

    def rows(self) -> list[tuple[object, str]]:
        return list(self._rows)

    def current_key(self) -> object | None:
        """Выбранное значение — то же, что вернёт `currentData()`."""
        return self._key

    def currentData(self, role: int = Qt.ItemDataRole.UserRole):  # noqa: N802 - Qt API
        """Ключ выбранного значения, **независимо от состояния отбора**.

        Обычный `currentData()` вернул бы данные текущей строки суженного
        списка — то есть значение, которого оператор не выбирал. Здесь ответ
        один и тот же в любой момент: последний осознанный выбор.
        """
        if role == Qt.ItemDataRole.UserRole:
            return self._key
        return super().currentData(role)

    def select_key(self, key: object | None) -> None:
        """Выбрать значение по ключу — программный путь вместо клика."""
        known = {row[0] for row in self._rows}
        chosen = key if key in known else None
        changed = chosen != self._key
        self._key = chosen
        self.settle()
        if changed:
            self.keyChanged.emit(self._key)

    def setCurrentText(self, text: str) -> None:  # noqa: N802 - Qt API
        """Выбрать по подписи; неизвестный текст выбором не становится.

        Оставлено рабочим потому, что так поле выбирают из кода и из тестов.
        Текст, которого нет в списке, поле покажет, но значением не сделает —
        его откатит `settle()` (страховка от свободного текста, §3.1.3).
        """
        for key, label in self._rows:
            if label == text:
                self.select_key(key)
                return
        super().setCurrentText(text)

    def label_of(self, key: object | None) -> str:
        for row_key, label in self._rows:
            if row_key == key:
                return label
        return ""

    # --- отбор -----------------------------------------------------------------

    def filter_to(self, text: str) -> list[tuple[object, str]]:
        """Сузить список по вхождению подстроки. Возвращает отобранное.

        По вхождению, а не по началу строки: каталожный номер `MF5-10375A-N`
        оператор помнит серединой чаще, чем префиксом.
        """
        needle = (text or "").strip().casefold()
        matched = [row for row in self._rows if not needle or needle in row[1].casefold()]
        self._show(matched, needle)
        return matched

    def visible_labels(self) -> list[str]:
        """Что сейчас в списке — то, что видит оператор."""
        return [self.itemText(index) for index in range(self.count())]

    def is_explaining(self) -> bool:
        """Показывает ли список объяснение вместо значений."""
        return self._explaining

    def settle(self) -> None:
        """Вернуть поле в устойчивое состояние: полный список, прежний выбор.

        Зовётся при уходе фокуса, при закрытии списка и при подтверждении формы.
        Набранное, не ставшее выбором, здесь и откатывается: свободный текст
        значением поля не бывает.

        Сам по себе выбор здесь не меняется: `settle` только восстанавливает
        показ. Снятие выбора — жест оператора (стереть строку), и живёт оно в
        `_on_typed`; смешивать их нельзя, иначе программный выбор по ключу
        снимался бы сам собой — строка в этот момент ещё пуста.
        """
        self._show(self._rows, "")
        index = self.findData(self._key) if self._key is not None else -1
        self.blockSignals(True)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setCurrentIndex(-1)
            self.lineEdit().setText("")
        self.blockSignals(False)

    def hidePopup(self) -> None:  # noqa: N802 - Qt API
        """Список закрылся — отбор снят. Открыл заново, список полон (§3.1.4)."""
        super().hidePopup()
        self.settle()

    # --- внутреннее ------------------------------------------------------------

    def _on_typed(self, text: str) -> None:
        typed = text
        if not typed.strip() and self._key is not None:
            # Стёртая строка — законное «не выбрано»: у обоих мест применения
            # это состояние допустимо (деталь ещё не названа, деталь без группы).
            self._key = None
            self.keyChanged.emit(None)
        self.filter_to(typed)
        # `clear()` в `_show` стирает набранное — возвращаем его на место.
        # `setText` шлёт `textChanged`, но не `textEdited`, поэтому не зацикливается.
        self.lineEdit().setText(typed)
        if not self.view().isVisible():
            self.showPopup()

    def _show(self, rows: list[tuple[object, str]], needle: str = "") -> None:
        self.blockSignals(True)
        self.clear()
        for key, label in rows:
            self.addItem(label, key)
        self._explaining = not rows and bool(needle)
        if self._explaining:
            # Пустой список без объяснения читается как «таких значений нет»,
            # хотя их не пропустил отбор. Строка выключена: объяснение не
            # выбирается и значением стать не может.
            self.addItem(_nothing_matches(needle, len(self._rows)), None)
            item = self.model().item(0)
            if item is not None:
                item.setEnabled(False)
        self.blockSignals(False)

    def _remember(self, index: int) -> None:
        """Оператор выбрал строку — она и становится значением поля."""
        key = self.itemData(index, Qt.ItemDataRole.UserRole)
        if key is None and self._explaining:
            return
        changed = key != self._key
        self._key = key
        if changed:
            self.keyChanged.emit(self._key)


def _nothing_matches(needle: str, total: int) -> str:
    """Объяснение пустого результата — тем же словами, что в `PickerDialog`."""
    return (
        f"Nothing matches {iso(needle)} — "
        f"all {total} values are still there, the filter hides them"
    )
