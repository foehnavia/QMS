"""Разведка по архивному журналу отклонений: структура, профили колонок,
покрытие каноничных шаблонов разбора.

**Зачем инструмент, а не разовый скрипт.** Наряд `0033` снимает `Q-17`
(«какие формы свободного текста встречаются в журнале и как их разбирать»)
**измерением, а не представлением**. Мерить придётся не один раз: шапка
действующего журнала в наряд не вошла (объявленный пробел), и когда она
приедет, тот же замер надо будет повторить и сравнить. Поэтому — инструмент,
детерминированный и параметризованный путём к книге.

**Что инструмент не делает.** Он не пишет правила разбора и не правит канон.
Он берёт шаблоны, которые в каноне **уже есть** (`docs/model/Import-Workflow.md`
§ETL: backbone, pin, приоритет словесного направления над знаком числа), и
считает, какую долю массива они накрывают. Расхождение факта с каноном —
находка в отчёт, а не правка канона.

**Почему лестница, а не один шаблон.** Ответ «backbone накрывает N%» без
разбивки бесполезен: он не говорит, чего именно шаблону не хватает. Поэтому
классификация — **упорядоченный каскад**: сперва канон дословно, затем
поимённые послабления (знак приклеен к числу, опущено `חורגת`, переставлен
порядок слов…), каждое со своим приростом. Cowork видит не «сколько не
накрыто», а «какое послабление сколько добавляет» — и решает, что вносить в
правила разбора.

**Счёт обязан сходиться.** Сумма строк по всем категориям каждого разреза
равна числу строк листа (критерий приёмки 3). Это та же структурная гарантия
непропуска, что и на экране импорта: категория «прочее» существует всегда и
считается наравне с остальными.

    python tools/import_journal_probe.py PRIMARY.xlsx [DRIFT.xlsx] \
        --json docs/analysis/0033-import-journal-stats.json \
        --md   docs/analysis/0033-import-journal-stats.md

Ни `--json`, ни `--md` не обязательны: без них печатается сводка в консоль.
Вывод не содержит отметок времени — иначе повторный прогон давал бы другой
файл и критерий детерминизма был бы непроверяем.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import openpyxl
from openpyxl.utils import get_column_letter

# --- имена колонок журнала, по которым он опознаётся -------------------------
# Адресуемся по заголовку, а не по букве колонки: буква у 2025 и 2024 разная
# (`תיאור חריגה` — K и H соответственно), и позиционное обращение здесь
# сломалось бы молча (CLAUDE.md §9а.9).
DESCRIPTION_HEADER = "תיאור חריגה"
WO_HEADER = "פקייע"
ITEM_HEADER = "מקייט"
DATE_HEADERS = ("תאריך סגירה", "תאריך שליחת חריגה", "תאריך פתיחה")

FULL_FREQUENCY_LIMIT = 50  # ≤ стольких различных значений — печатаем распределение целиком
EDGE_TARGET_MAX = 120  # целевой потолок выборки «краёв» из наряда

# --- каноничные шаблоны разбора ----------------------------------------------
# Слова взяты из `docs/model/Import-Workflow.md` §ETL дословно; послабления
# ниже — то, чем реальный массив от них отличается. Инструмент их **измеряет**,
# а не узаконивает: узаконивает Cowork, правя канон.

CANON_ABOVE = "מעל המקסימום"
CANON_BELOW = "מתחת למינימום"

ABOVE_RE = r"(?:מעל|מל)\s+(?:ה|ל)?(?:מקסימום|מקסינום|מקסימוס|מקס)"
BELOW_RE = r"(?:מתחת|מיתחת|מתחתת|מתח)\s+(?:ל)?(?:מינימום|מינמום|נינימום|מנימום|מנמום|מינימוס)"
SIGNWORD_RE = r"ב?(?:פלוס|מינוס)"
DIRECTION_RE = rf"(?:{ABOVE_RE}|{BELOW_RE}|{SIGNWORD_RE})"

VERB_RE = r"(?:חורגת|חורגות|חורגים|חורג|החורגת|החורג|חוגרת|חריגה)"
LEAD_RE = r"(?:חריגה\s+במידה|במידה|המידה|מידות|מידה)"
DIM_RE = (
    r"(?:\[\s*\d+\s*\]|\d+\s*ו\s*\d+|\d+(?:[-.]\d+)*\s*mm"
    r"|\d+(?:[-.]\d+)*(?:\s+\d+)?|[A-Za-z][A-Za-z0-9\-]*)"
)
VALUE_RE = (
    r"[+\-]?\s*\d+(?:[.,]\d+)?\s*[+\-]?"
    r"(?:\s*עד\s*[+\-]?\s*\d+(?:[.,]\d+)?\s*[+\-]?)?"
)
PREP_RE = r"(?:של\s*)?(?:עד|ב|מ)?"

# Порядок этого списка — порядок «лестницы»: она отвечает не «сколько не
# накрыто», а «какое послабление сколько добавляет».
RELAXATION_ORDER = (
    "spacing-and-sign",
    "verb-spelling",
    "verb-omitted",
    "prep-omitted",
    "prep-alt",
    "direction-spelling",
    "direction-as-sign-word",
    "word-order",
    "alt-opening",
    "dimension-token",
    "value-range",
    "context-prefix",
    "context-suffix",
)

RELAXATION_NOTE = {
    "spacing-and-sign": "знак приклеен к числу справа, предлог слит с числом, "
    "запятая как десятичный разделитель, сдвоенные пробелы",
    "verb-spelling": "глагол не `חורגת` (род/число/`חריגה`)",
    "verb-omitted": "глагола нет вовсе: `מידה 15 מעל המקסימום ב 0.05`",
    "prep-omitted": "нет `עד`/`ב` перед величиной",
    "prep-alt": "предлог `של` вместо `עד`/`ב`",
    "direction-spelling": "направление написано иначе: `מעל למקסימום`, "
    "`מעל מקסימום`, опечатки `מינמום`/`נינימום`/`מיתחת`/`מתח`",
    "direction-as-sign-word": "направление словом-знаком `בפלוס`/`במינוס` "
    "вместо `מעל המקסימום`/`מתחת למינימום`",
    "word-order": "направление стоит **после** величины",
    "alt-opening": "фрагмент начинается не с `מידה`: `חריגה במידה`, `המידה`, "
    "`מידות`, ведущее `ו`",
    "dimension-token": "номер размера не голое целое: подындекс точки замера "
    "`12 1`, скобки `[12]`, единица `25mm`, имя (`Circle`), пара `3 ו4`",
    "value-range": "величина задана вилкой `מ0.002+ עד 0.005+`, а не одним числом",
    "context-prefix": "перед шаблоном стоит клауза контекста обнаружения "
    "(`במהלך מדגם סופי…`)",
    "context-suffix": "после величины стоит хвост (`מתקבלת 3.32`, `פיות`)",
}

_SHAPE_A = re.compile(  # направление до величины — порядок канона
    rf"^(?P<open>ו\s*)?(?P<lead>{LEAD_RE})\s*(?P<dim>{DIM_RE})?\s*"
    rf"(?P<verb>{VERB_RE})?\s*(?P<dir>{DIRECTION_RE})\s*"
    rf"(?P<prep>{PREP_RE})\s*(?P<val>{VALUE_RE})$"
)
_SHAPE_B = re.compile(  # величина до направления
    rf"^(?P<open>ו\s*)?(?P<lead>{LEAD_RE})\s*(?P<dim>{DIM_RE})?\s*"
    rf"(?P<verb>{VERB_RE})?\s*(?P<prep>{PREP_RE})\s*"
    rf"(?P<val>{VALUE_RE})\s*(?P<dir>{DIRECTION_RE})$"
)
_SHAPE_A_CTX = re.compile(
    rf"^(?P<prefix>.*?)(?P<lead>{LEAD_RE})\s*(?P<dim>{DIM_RE})?\s*"
    rf"(?P<verb>{VERB_RE})?\s*(?P<dir>{DIRECTION_RE})\s*"
    rf"(?P<prep>{PREP_RE})\s*(?P<val>{VALUE_RE})(?P<suffix>.*)$"
)
_SHAPE_B_CTX = re.compile(
    rf"^(?P<prefix>.*?)(?P<lead>{LEAD_RE})\s*(?P<dim>{DIM_RE})?\s*"
    rf"(?P<verb>{VERB_RE})?\s*(?P<prep>{PREP_RE})\s*"
    rf"(?P<val>{VALUE_RE})\s*(?P<dir>{DIRECTION_RE})(?P<suffix>.*)$"
)

_PIN_CANON = re.compile(r"^מידה\s+(?P<dim>\d+)\s+פין\s+(?P<pin>\d+(?:\.\d+)?)\s+(?P<verdict>לא\s+נכנס|נכנס)$")
_HAS_PIN = re.compile(r"פין")
_HAS_GAUGE = re.compile(r"מדיד|\bNOT\s*GO\b|\bNO\s*GO\b|\bGO\b", re.IGNORECASE)

_ABOVE_ONLY = re.compile(ABOVE_RE)
_BELOW_ONLY = re.compile(BELOW_RE)
_PLUS_WORD = re.compile(r"ב?פלוס")
_MINUS_WORD = re.compile(r"ב?מינוס")


# --- нормализация и разбиение -------------------------------------------------
BIDI_MARKS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"


def cell_text(value: object) -> str:
    """Привести значение ячейки к строке, не потеряв нестроковые значения.

    Число в текстовой колонке — не пустота: ячейка `0` в описании отклонения
    существует и обязана попасть в счёт, иначе сумма категорий не сойдётся
    с числом строк листа (критерий приёмки 3).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def normalise(text: str) -> str:
    """Свернуть пробелы и снять bidi-метки — единственная правка перед разбором.

    Нормализация объявлена, а не спрятана: она перечислена в отчёте, потому
    что от неё зависит, что считать «дословным совпадением с каноном».
    """
    for mark in BIDI_MARKS:
        text = text.replace(mark, "")
    text = text.replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


_SEPARATORS = (
    ("newline", re.compile(r"[\n\r]+")),
    ("comma", re.compile(r",")),
    ("vav", re.compile(r"(?<=\S)\s+(?=ו(?:מידה|פין|חריגה))")),
    ("semicolon", re.compile(r";")),
)


def split_fragments(text: str) -> tuple[list[str], list[str]]:
    """Разбить описание на находки и назвать, чем они разделены.

    Разделители применяются по очереди к уже полученным кускам, поэтому
    строка с переводом строки **и** запятой числится по обоим — вопрос наряда
    звучит «чем разделены», а не «каким одним разделителем».
    """
    parts = [text]
    used: list[str] = []
    for name, pattern in _SEPARATORS:
        split_here = [pattern.split(part) for part in parts]
        if any(len(chunk) > 1 for chunk in split_here):
            used.append(name)
        parts = [piece for chunk in split_here for piece in chunk]
    fragments = [normalise(part) for part in parts]
    return [frag for frag in fragments if frag], used


# --- классификация фрагмента --------------------------------------------------
def _relaxations(match: re.Match[str], fragment: str, shape: str) -> set[str]:
    """Назвать, чем разобранный фрагмент отличается от дословного канона."""
    flags: set[str] = set()
    groups = match.groupdict()

    if shape == "B":
        flags.add("word-order")

    if (groups.get("prefix") or "").strip():
        flags.add("context-prefix")
    if (groups.get("suffix") or "").strip():
        flags.add("context-suffix")

    if (groups.get("open") or "").strip() or groups.get("lead") != "מידה":
        flags.add("alt-opening")

    dim = (groups.get("dim") or "").strip()
    if not re.fullmatch(r"\d+", dim):
        flags.add("dimension-token")

    verb = (groups.get("verb") or "").strip()
    if not verb:
        flags.add("verb-omitted")
    elif verb != "חורגת":
        flags.add("verb-spelling")

    prep = (groups.get("prep") or "").strip()
    if prep.startswith("של"):
        flags.add("prep-alt")
    elif not prep:
        flags.add("prep-omitted")

    direction = (groups.get("dir") or "").strip()
    if _PLUS_WORD.fullmatch(direction) or _MINUS_WORD.fullmatch(direction):
        flags.add("direction-as-sign-word")
    elif direction not in (CANON_ABOVE, CANON_BELOW):
        flags.add("direction-spelling")

    value = (groups.get("val") or "").strip()
    if "עד" in value:
        flags.add("value-range")
    canonical_tail = f"{direction} {prep} {value}".strip() if prep else f"{direction} {value}"
    if (
        not re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", value)
        or f" {canonical_tail}" not in f" {fragment}"
    ):
        flags.add("spacing-and-sign")
    return flags


def _direction_of(match: re.Match[str]) -> str | None:
    direction = (match.groupdict().get("dir") or "").strip()
    if _ABOVE_ONLY.fullmatch(direction) or _PLUS_WORD.fullmatch(direction):
        return "above"
    if _BELOW_ONLY.fullmatch(direction) or _MINUS_WORD.fullmatch(direction):
        return "below"
    return None


def _sign_of(match: re.Match[str]) -> str | None:
    value = (match.groupdict().get("val") or "").replace(" ", "")
    if value.startswith("+") or value.endswith("+"):
        return "above"
    if value.startswith("-") or value.endswith("-"):
        return "below"
    return None


def classify_fragment(fragment: str) -> dict:
    """Отнести фрагмент к одной категории — ровно к одной.

    Порядок проб задан и объявлен: `פין` перебивает backbone, потому что
    фрагмент с пином описывает **измерение пином**, а величины в нём нет
    (канон: «пин измерим, но на этапе 1 уходит в `comment`»). Фрагменты, где
    есть и то и другое, считаются отдельно — счётчик пересечения в отчёте.
    """
    result: dict = {
        "text": fragment,
        "kind": "unrecognised",
        "relaxations": [],
        "direction": None,
        "sign": None,
        "reason": None,
    }
    if not fragment:
        return result

    if _HAS_PIN.search(fragment):
        result["kind"] = "pin_canon" if _PIN_CANON.fullmatch(fragment) else "pin_variant"
        result["also_backbone"] = bool(_SHAPE_A_CTX.match(fragment) or _SHAPE_B_CTX.match(fragment))
        return result

    if _HAS_GAUGE.search(fragment):
        result["kind"] = "gauge"
        return result

    for shape, pattern in (("A", _SHAPE_A), ("B", _SHAPE_B), ("A", _SHAPE_A_CTX), ("B", _SHAPE_B_CTX)):
        match = pattern.match(fragment)
        if not match:
            continue
        flags = _relaxations(match, fragment, shape)
        result["kind"] = "backbone"
        result["relaxations"] = sorted(flags, key=RELAXATION_ORDER.index)
        result["direction"] = _direction_of(match)
        result["sign"] = _sign_of(match)
        result["prefix"] = (match.groupdict().get("prefix") or "").strip()
        result["suffix"] = (match.groupdict().get("suffix") or "").strip()
        return result

    has_dimension_word = "מידה" in fragment or "מידות" in fragment
    has_direction = bool(_ABOVE_ONLY.search(fragment) or _BELOW_ONLY.search(fragment))
    has_verb = bool(re.search(VERB_RE, fragment))
    has_value = bool(re.search(r"\d", fragment))
    if has_dimension_word and (has_direction or has_verb):
        missing = []
        if not has_direction:
            missing.append("direction")
        if not re.search(r"מידה\s*\d", fragment) and not re.search(r"מידות\s*\d", fragment):
            missing.append("dimension")
        if not has_value:
            missing.append("value")
        result["kind"] = "partial"
        result["reason"] = "+".join(missing) if missing else "shape"
    return result


# --- известный шум ------------------------------------------------------------
NOISE_PATTERNS = {
    "typo-minimum": re.compile(r"מינמום|נינימום|מנימום|מנמום|מיתחת|(?<!מ)מתח\s+ל?מינ"),
    "typo-maximum": re.compile(r"מקסינום|מקסימוס|(?<![א-ת])מל\s+ה?מקסימום"),
    "typo-verb": re.compile(r"חוגרת|חורגט"),
    "sample-x-of-y": re.compile(r"מתוך"),
    "gauge-or-go": _HAS_GAUGE,
    "pin": _HAS_PIN,
    "accepted-tail": re.compile(r"מתקבלת"),
    "context-clause": re.compile(r"במהלך|במדגם|מדגם|בתהליך"),
    "doubled-word": re.compile(r"\b(\S+)\s+\1\b"),
    "inner-newline": re.compile(r"[\n\r]"),
    "double-space": re.compile(r"  "),
    "bidi-mark": re.compile("[" + BIDI_MARKS + "]"),
    "nbsp": re.compile("\u00a0"),
}

SUBINDEX_RE = re.compile(r"מידה\s+\d+(?:[-.]\d+|\s+\d+)(?![\d.])")
# Канон называет подындекс точки замера «голым числом» (`12 1`); чем он
# записан на самом деле — вопрос замера, а не представления.
_SUBINDEX_FORM = re.compile(r"מידה\s+\d+([-.\s])(\d+)(?![\d.])")
SIGN_TRAILING_RE = re.compile(r"\d\s*[+\-](?:\s|$)")


def describe_noise(raw: str) -> list[str]:
    """Отметить в описании все известные виды шума — независимыми флагами.

    Флаги независимы намеренно: одно описание бывает разом и выборкой, и с
    приклеенным знаком, и с опечаткой. Взаимоисключающая классификация здесь
    соврала бы, а вопрос наряда — «сколько чего встречается», не «к какому
    одному ведру отнести».
    """
    hits = [name for name, pattern in NOISE_PATTERNS.items() if pattern.search(raw)]
    if SUBINDEX_RE.search(raw):
        hits.append("point-subindex")
    if SIGN_TRAILING_RE.search(raw):
        hits.append("sign-after-number")
    if raw != raw.strip():
        hits.append("outer-space")
    return sorted(hits)


# --- структура книги ----------------------------------------------------------
def survey_workbook(path: Path) -> dict:
    """Снять структуру книги: листы, размеры, шапка, скрытое, блоки колонок.

    **Блоки колонок считаются отдельно от листа.** Лист — не таблица: в файле
    2025 рядом с журналом на том же листе лежат два списка, не имеющие к нему
    отношения (источники выпадающих списков и справочник `Production ID`).
    Взять `max_row` за число строк журнала значило бы промахнуться в три с
    половиной раза, поэтому границы блока определяются заполненностью колонок,
    а не рамкой листа.
    """
    formulas = openpyxl.load_workbook(path, read_only=True, data_only=False)
    values = openpyxl.load_workbook(path, read_only=False, data_only=True)
    report: dict = {"file": path.name, "sheets": []}
    try:
        for sheet in values.worksheets:
            grid = [list(row) for row in sheet.iter_rows(values_only=True)]
            width = max((len(row) for row in grid), default=0)
            filled: dict[int, list[int]] = defaultdict(list)
            for index, row in enumerate(grid, 1):
                for column, value in enumerate(row, 1):
                    if cell_text(value).strip():
                        filled[column].append(index)
            header_row = min((rows[0] for rows in filled.values()), default=0)
            headers = {}
            if header_row:
                for column, rows in sorted(filled.items()):
                    if rows[0] == header_row:
                        headers[column] = cell_text(grid[header_row - 1][column - 1]).strip()
            merged = [str(rng) for rng in sheet.merged_cells.ranges]
            report["sheets"].append(
                {
                    "title": sheet.title,
                    "state": sheet.sheet_state,
                    "dimensions": sheet.dimensions,
                    "max_row_reported": sheet.max_row,
                    "max_column_reported": sheet.max_column,
                    "last_row_with_data": max((rows[-1] for rows in filled.values()), default=0),
                    "header_row": header_row,
                    "merged_ranges": sorted(merged),
                    "merged_in_header": sorted(r for r in merged if f"{header_row}:" in r or re.search(rf"[A-Z]{header_row}\b", r)),
                    "auto_filter": sheet.auto_filter.ref,
                    "freeze_panes": sheet.freeze_panes,
                    "hidden_columns": sorted(
                        letter for letter, dim in sheet.column_dimensions.items() if dim.hidden
                    ),
                    "columns": [
                        {
                            "letter": get_column_letter(column),
                            "header": headers.get(column) or None,
                            "first_row": rows[0],
                            "last_row": rows[-1],
                            "filled_rows": len(rows),
                        }
                        for column, rows in sorted(filled.items())
                    ],
                    "width_scanned": width,
                }
            )
        report["hidden_sheets"] = [s.title for s in values.worksheets if s.sheet_state != "visible"]
        report["sheet_names"] = values.sheetnames
        report["formula_cells"] = _count_formulas(formulas)
    finally:
        values.close()
        formulas.close()
    return report


def _count_formulas(book: openpyxl.Workbook) -> dict[str, dict]:
    """Посчитать формулы **по колонкам**, а не одним числом на лист.

    Одно число на лист здесь врёт: в файле 2025 формула колонки `מכונה`
    протянута до конца листа (миллион с лишним ячеек), и суммарный счёт
    сказал бы «лист состоит из формул», не назвав главного — что одна из
    колонок журнала не заполняется человеком, а **вычисляется**.
    """
    counts: dict[str, dict] = {}
    for sheet in book.worksheets:
        per_column: Counter = Counter()
        samples: dict[str, dict] = {}
        for index, row in enumerate(sheet.iter_rows(values_only=True), 1):
            for column, value in enumerate(row, 1):
                if isinstance(value, str) and value.startswith("="):
                    letter = get_column_letter(column)
                    per_column[letter] += 1
                    samples.setdefault(letter, {"row": index, "formula": value})
        counts[sheet.title] = {
            "total": sum(per_column.values()),
            "by_column": [
                {"letter": letter, "count": per_column[letter], **samples[letter]}
                for letter in sorted(per_column, key=openpyxl.utils.column_index_from_string)
            ],
        }
    return counts


def locate_journal(structure: dict) -> dict:
    """Назвать лист и блок колонок, которые и есть журнал, — и по какому признаку.

    Признак объявлен и один: блок содержит колонку `תיאור חריגה`. Блок берётся
    как **непрерывный ряд озаглавленных колонок**, а не как весь лист: соседние
    озаглавленные колонки за разрывом (`Production ID` / `CNC` в файле 2025) —
    отдельный список, к журналу отношения не имеющий.
    """
    for sheet in structure["sheets"]:
        headed = [c for c in sheet["columns"] if c["header"] and c["first_row"] == sheet["header_row"]]
        if not any(c["header"] == DESCRIPTION_HEADER for c in headed):
            continue
        indexes = sorted(
            openpyxl.utils.column_index_from_string(c["letter"]) for c in headed
        )
        anchor = openpyxl.utils.column_index_from_string(
            next(c["letter"] for c in headed if c["header"] == DESCRIPTION_HEADER)
        )
        block = [anchor]
        for index in indexes:
            if index < anchor and all(step in indexes for step in range(index, anchor)):
                block.append(index)
            if index > anchor and all(step in indexes for step in range(anchor + 1, index + 1)):
                block.append(index)
        block = sorted(set(block))
        columns = [c for c in sheet["columns"] if openpyxl.utils.column_index_from_string(c["letter"]) in block]
        return {
            "sheet": sheet["title"],
            "identified_by": f"блок озаглавленных колонок, содержащий {DESCRIPTION_HEADER!r}",
            "header_row": sheet["header_row"],
            "first_data_row": sheet["header_row"] + 1,
            "last_data_row": max(c["last_row"] for c in columns),
            "columns": columns,
            "outside_block": [
                c for c in sheet["columns"]
                if openpyxl.utils.column_index_from_string(c["letter"]) not in block
            ],
        }
    raise SystemExit(f"{structure['file']}: лист с колонкой {DESCRIPTION_HEADER!r} не найден")


def read_journal(path: Path, journal: dict) -> list[dict]:
    """Прочитать строки журнала как словари «заголовок → значение»."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book[journal["sheet"]]
    order = [(c["letter"], c["header"]) for c in journal["columns"]]
    rows: list[dict] = []
    try:
        for number, values in enumerate(
            sheet.iter_rows(
                min_row=journal["first_data_row"], max_row=journal["last_data_row"], values_only=True
            ),
            journal["first_data_row"],
        ):
            record = {"__row__": number}
            for letter, header in order:
                index = openpyxl.utils.column_index_from_string(letter) - 1
                record[header] = values[index] if index < len(values) else None
            rows.append(record)
    finally:
        book.close()
    return rows


# --- профиль колонки ----------------------------------------------------------
_DATE_TEXT_RE = re.compile(r"^\s*\d{1,4}[./\-]\d{1,2}([./\-]\d{1,4})?\s*$")
_NUMERIC_TEXT_RE = re.compile(r"^\s*[+\-]?\d+([.,]\d+)?\s*[+\-]?\s*$")


def profile_column(header: str, values: list[object], brief: bool = False) -> dict:
    """Профиль одной колонки: заполненность, типы, распределение, аномалии."""
    total = len(values)
    texts = [cell_text(value) for value in values]
    non_empty = [(value, text) for value, text in zip(values, texts) if text.strip()]
    kinds = Counter()
    for value, _ in non_empty:
        if isinstance(value, bool):
            kinds["bool"] += 1
        elif isinstance(value, (datetime, date, time)):
            kinds["date"] += 1
        elif isinstance(value, int):
            kinds["int"] += 1
        elif isinstance(value, float):
            kinds["float"] += 1
        elif isinstance(value, str) and value.startswith("="):
            kinds["formula"] += 1
        elif isinstance(value, str) and value.startswith("#") and value.endswith(("!", "?", "A", "0")):
            kinds["error"] += 1
        else:
            kinds["text"] += 1

    lengths = sorted(len(text) for _, text in non_empty)
    distinct = Counter(text.strip() for _, text in non_empty)
    string_cells = [text for value, text in non_empty if isinstance(value, str)]

    profile: dict = {
        "header": header,
        "rows": total,
        "non_empty": len(non_empty),
        "empty": total - len(non_empty),
        "fill_share": round(len(non_empty) / total, 4) if total else 0.0,
        "distinct": len(distinct),
        "types": dict(sorted(kinds.items())),
        "text_length": {
            "min": lengths[0] if lengths else None,
            "median": int(statistics.median(lengths)) if lengths else None,
            "p95": lengths[min(len(lengths) - 1, int(round(0.95 * (len(lengths) - 1))))] if lengths else None,
            "max": lengths[-1] if lengths else None,
        },
        "anomalies": {
            "outer_space": sum(1 for t in string_cells if t != t.strip()),
            "double_space": sum(1 for t in string_cells if "  " in t),
            "inner_newline": sum(1 for t in string_cells if "\n" in t or "\r" in t),
            "bidi_marks": sum(1 for t in string_cells if any(m in t for m in BIDI_MARKS)),
            "nbsp": sum(1 for t in string_cells if "\u00a0" in t),
            "numeric_as_text": sum(1 for t in string_cells if _NUMERIC_TEXT_RE.fullmatch(t)),
            "date_as_text": sum(1 for t in string_cells if _DATE_TEXT_RE.fullmatch(t)),
        },
        "numeric_as_text_examples": sorted({t for t in string_cells if _NUMERIC_TEXT_RE.fullmatch(t)})[:10],
        "date_as_text_examples": sorted({t for t in string_cells if _DATE_TEXT_RE.fullmatch(t)})[:10],
    }
    if kinds.get("date"):
        stamps = [v for v, _ in non_empty if isinstance(v, (datetime, date))]
        with_time = sum(
            1 for v in stamps if isinstance(v, datetime) and (v.hour or v.minute or v.second)
        )
        profile["date_forms"] = {
            "as_datetime": len(stamps),
            "with_nonzero_time": with_time,
            "min": min(stamps).isoformat(),
            "max": max(stamps).isoformat(),
        }
    if len(distinct) <= FULL_FREQUENCY_LIMIT and not brief:
        profile["frequencies"] = [
            {"value": value, "count": count}
            for value, count in sorted(distinct.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
    else:
        profile["top_values"] = [
            {"value": value, "count": count} for value, count in distinct.most_common(10)
        ]
    return profile


# --- покрытие шаблонов --------------------------------------------------------
def analyse_descriptions(rows: list[dict]) -> dict:
    """Померить, какую долю массива накрывают шаблоны канона.

    Три разреза, и **каждый сходится с числом строк листа**: строки по
    покрытию, фрагменты по категориям, строки по числу находок. Категория
    «прочее» в каждом разрезе существует всегда — иначе сумма сошлась бы за
    счёт молча выброшенного остатка, а это ровно тот непропуск, который наряд
    и проверяет.
    """
    per_row: list[dict] = []
    row_coverage = Counter()
    fragment_kinds = Counter()
    relaxation_hits = Counter()
    relaxation_sets = Counter()
    unparsed_forms: Counter = Counter()
    pin_forms: Counter = Counter()
    gauge_forms: Counter = Counter()
    unparsed_example: dict[str, dict] = {}
    separators = Counter()
    noise = Counter()
    conflicts: list[dict] = []
    suffixes = Counter()
    prefixes = Counter()
    fragment_counts = Counter()
    subindex_forms = Counter()
    conflict_shapes = Counter()

    for record in rows:
        raw = cell_text(record.get(DESCRIPTION_HEADER))
        number = record["__row__"]
        if not raw.strip():
            row_coverage["empty"] += 1
            fragment_counts[0] += 1
            per_row.append({"row": number, "coverage": "empty", "fragments": []})
            continue

        for flag in describe_noise(raw):
            noise[flag] += 1
        for match in _SUBINDEX_FORM.finditer(raw):
            subindex_forms[{"-": "N-M", ".": "N.M"}.get(match.group(1), "N M")] += 1

        fragments, used = split_fragments(raw)
        for name in used:
            separators[name] += 1
        if not used:
            separators["<none>"] += 1
        fragment_counts[len(fragments)] += 1

        parsed = [classify_fragment(fragment) for fragment in fragments]
        for item in parsed:
            fragment_kinds[item["kind"]] += 1
            if item["kind"] == "backbone":
                relaxation_sets[tuple(item["relaxations"])] += 1
                for flag in item["relaxations"]:
                    relaxation_hits[flag] += 1
                if item.get("suffix"):
                    suffixes[item["suffix"]] += 1
                if item.get("prefix"):
                    prefixes[item["prefix"]] += 1
                if item["direction"] and item["sign"] and item["direction"] != item["sign"]:
                    conflicts.append({"row": number, "text": item["text"], "word": item["direction"], "sign": item["sign"]})
                    conflict_shapes[re.sub(r"[-+]?\d+(?:[.,]\d+)?", "#", item["text"])] += 1
            else:
                form = re.sub(r"[-+]?\d+(?:[.,]\d+)?", "#", item["text"])
                key = f"{item['kind']}|{form}"
                bucket = pin_forms if item["kind"].startswith("pin") else (
                    gauge_forms if item["kind"] == "gauge" else unparsed_forms
                )
                bucket[key] += 1
                unparsed_example.setdefault(key, {"row": number, "text": item["text"], "reason": item.get("reason")})

        recognised = {"backbone", "pin_canon", "pin_variant", "gauge"}
        kinds = {item["kind"] for item in parsed}
        if kinds <= recognised:
            coverage = "full"
        elif kinds & recognised:
            coverage = "partial"
        elif "partial" in kinds:
            coverage = "partial"
        else:
            coverage = "unrecognised"
        row_coverage[coverage] += 1
        per_row.append({"row": number, "coverage": coverage, "fragments": parsed, "raw": raw})

    backbone_total = fragment_kinds["backbone"]
    ladder = []
    allowed: set[str] = set()
    covered = sum(count for flags, count in relaxation_sets.items() if not flags)
    ladder.append(
        {
            "step": "canon",
            "note": "дословно `מידה {N} חורגת {מעל המקסימום|מתחת למינימום} {עד|ב} {value}`",
            "cumulative": covered,
            "added": covered,
        }
    )
    for flag in RELAXATION_ORDER:
        allowed.add(flag)
        total = sum(count for flags, count in relaxation_sets.items() if set(flags) <= allowed)
        ladder.append(
            {
                "step": flag,
                "note": RELAXATION_NOTE[flag],
                "cumulative": total,
                "added": total - covered,
            }
        )
        covered = total

    return {
        "rows_total": len(rows),
        "row_coverage": dict(sorted(row_coverage.items())),
        "fragment_kinds": dict(sorted(fragment_kinds.items())),
        "fragments_total": sum(fragment_kinds.values()),
        "backbone_total": backbone_total,
        "backbone_canon_exact": relaxation_sets.get((), 0),
        "relaxation_hits": dict(sorted(relaxation_hits.items(), key=lambda kv: (-kv[1], kv[0]))),
        "relaxation_ladder": ladder,
        "relaxation_sets": [
            {"relaxations": list(flags), "count": count}
            for flags, count in sorted(relaxation_sets.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "separators": dict(sorted(separators.items(), key=lambda kv: (-kv[1], kv[0]))),
        "fragments_per_row": dict(sorted(fragment_counts.items())),
        "noise": dict(sorted(noise.items(), key=lambda kv: (-kv[1], kv[0]))),
        "conflicts_word_vs_sign": conflicts,
        "conflict_shapes": [
            {"form": form, "count": count}
            for form, count in sorted(conflict_shapes.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "subindex_notation": dict(sorted(subindex_forms.items(), key=lambda kv: (-kv[1], kv[0]))),
        "context_suffixes": [{"text": t, "count": n} for t, n in suffixes.most_common()],
        "context_prefixes": [{"text": t, "count": n} for t, n in prefixes.most_common()],
        "pin_forms": [
            {
                "kind": key.split("|", 1)[0],
                "form": key.split("|", 1)[1],
                "count": count,
                "row": unparsed_example[key]["row"],
                "example": unparsed_example[key]["text"],
            }
            for key, count in sorted(pin_forms.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "gauge_forms": [
            {
                "form": key.split("|", 1)[1],
                "count": count,
                "row": unparsed_example[key]["row"],
                "example": unparsed_example[key]["text"],
            }
            for key, count in sorted(gauge_forms.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "unparsed_forms": [
            {
                "kind": key.split("|", 1)[0],
                "form": key.split("|", 1)[1],
                "count": count,
                "row": unparsed_example[key]["row"],
                "example": unparsed_example[key]["text"],
                "reason": unparsed_example[key]["reason"],
            }
            for key, count in sorted(unparsed_forms.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "per_row": per_row,
    }


# --- ключ строки --------------------------------------------------------------
def analyse_key(rows: list[dict], date_headers: list[str]) -> dict:
    """Проверить постановочный ключ «дата + `פק\"ע` + текст описания» на массиве.

    Дат в журнале больше одной, и наряд не говорит какую — поэтому считаются
    **все** кандидаты, а выбор остаётся Cowork. Отдельной строкой — строки без
    даты или без `פק\"ע`: они ключа не образуют вовсе, и это важнее дубля,
    потому что непропуск строки важнее дедупликации.
    """
    result: dict = {"candidates": [], "wo_header": WO_HEADER}
    for header in date_headers:
        pairs = Counter()
        triples = Counter()
        no_date = 0
        no_wo = 0
        no_either = 0
        for record in rows:
            day = cell_text(record.get(header)).strip()
            work_order = cell_text(record.get(WO_HEADER)).strip()
            text = normalise(cell_text(record.get(DESCRIPTION_HEADER)))
            if not day and not work_order:
                no_either += 1
            if not day:
                no_date += 1
            if not work_order:
                no_wo += 1
            if day and work_order:
                pairs[(day, work_order)] += 1
                triples[(day, work_order, text)] += 1
        duplicate_pairs = {key: count for key, count in pairs.items() if count > 1}
        duplicate_triples = {key: count for key, count in triples.items() if count > 1}
        result["candidates"].append(
            {
                "date_header": header,
                "rows_with_full_key": sum(pairs.values()),
                "rows_without_date": no_date,
                "rows_without_wo": no_wo,
                "rows_without_either": no_either,
                "distinct_pairs": len(pairs),
                "pairs_seen_more_than_once": len(duplicate_pairs),
                "rows_in_repeated_pairs": sum(duplicate_pairs.values()),
                "max_rows_per_pair": max(pairs.values(), default=0),
                "distinct_triples": len(triples),
                "triples_seen_more_than_once": len(duplicate_triples),
                "rows_in_repeated_triples": sum(duplicate_triples.values()),
                "max_rows_per_triple": max(triples.values(), default=0),
                "examples_repeated_triples": [
                    {"date": key[0], "wo": key[1], "text": key[2], "count": count}
                    for key, count in sorted(duplicate_triples.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
                ],
            }
        )
    return result


# --- кандидаты «краёв» --------------------------------------------------------
def collect_edges(rows: list[dict], coverage: dict, limit: int = EDGE_TARGET_MAX) -> list[dict]:
    """Собрать строки, покрывающие края массива, а не его середину.

    Выбор **детерминированный**: категории перечислены в фиксированном
    порядке, внутри категории берётся первое вхождение по номеру строки.
    Наряд отдаёт выбор Cowork — инструмент обязан лишь не дать двум прогонам
    разойтись.
    """
    by_row = {record["__row__"]: record for record in rows}
    picks: dict[int, dict] = {}

    def add(number: int, reason: str) -> None:
        entry = picks.setdefault(
            number,
            {
                "row": number,
                "reasons": [],
                "description": cell_text(by_row[number].get(DESCRIPTION_HEADER)),
                "wo": cell_text(by_row[number].get(WO_HEADER)).strip() or None,
                "item": cell_text(by_row[number].get(ITEM_HEADER)).strip() or None,
            },
        )
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)

    texts = [
        (record["__row__"], cell_text(record.get(DESCRIPTION_HEADER)))
        for record in rows
        if cell_text(record.get(DESCRIPTION_HEADER)).strip()
    ]
    longest = max(texts, key=lambda item: (len(item[1]), -item[0]))
    shortest = min(texts, key=lambda item: (len(item[1]), item[0]))
    add(longest[0], "longest-description")
    add(shortest[0], "shortest-description")

    for form in coverage["unparsed_forms"]:
        add(form["row"], f"unparsed:{form['kind']}")

    for conflict in coverage["conflicts_word_vs_sign"]:
        add(conflict["row"], "conflict-word-vs-sign")

    seen_noise: set[str] = set()
    seen_relaxation: set[str] = set()
    for record in rows:
        raw = cell_text(record.get(DESCRIPTION_HEADER))
        if not raw.strip():
            continue
        for flag in describe_noise(raw):
            if flag not in seen_noise:
                seen_noise.add(flag)
                add(record["__row__"], f"noise:{flag}")

    for entry in coverage["per_row"]:
        for item in entry.get("fragments", []):
            for flag in item.get("relaxations", []):
                if flag not in seen_relaxation:
                    seen_relaxation.add(flag)
                    add(entry["row"], f"relaxation:{flag}")

    most_fragments = max(
        (entry for entry in coverage["per_row"] if entry["coverage"] != "empty"),
        key=lambda entry: (len(entry["fragments"]), -entry["row"]),
    )
    add(most_fragments["row"], "most-findings-in-one-cell")

    # Повторяющиеся поводы берутся с потолком: «текст в числовой колонке» встречается
    # 34 раза одинаково, и тридцать четыре строки одного вида — это не край, а середина.
    repeated: Counter = Counter()
    repeated_cap = 3

    def add_capped(number: int, reason: str) -> None:
        if repeated[reason] >= repeated_cap:
            return
        repeated[reason] += 1
        add(number, reason)

    for record in rows:
        number = record["__row__"]
        if not cell_text(record.get(WO_HEADER)).strip():
            add(number, "empty-wo")
        if not cell_text(record.get(DESCRIPTION_HEADER)).strip():
            add(number, "empty-description")
        for header in DATE_HEADERS:
            if header in record and isinstance(record[header], str) and record[header].strip():
                add(number, f"date-as-text:{header}")
        value = record.get(DESCRIPTION_HEADER)
        if value is not None and not isinstance(value, str):
            add(number, "description-not-text")
        for header in ("כמות", "עדיפות"):
            cell = record.get(header)
            if isinstance(cell, str) and cell.strip():
                add_capped(number, f"text-in-numeric-column:{header}")
        for header, cell in record.items():
            if isinstance(cell, str) and cell.startswith("#") and cell.endswith(("!", "?", "A", "0", "E")):
                add_capped(number, f"error-value:{header}")

    ordered = sorted(picks.values(), key=lambda entry: entry["row"])
    if len(ordered) <= limit:
        return ordered
    # Тесним середину, а не края: строки с наибольшим числом поводов остаются.
    def weight(entry: dict) -> tuple:
        # Форма, встреченная один раз, — это и есть край; она не может уступить
        # место строке, интересной сразу по двум обыденным поводам.
        unique = any(r.startswith(("unparsed:", "noise:", "relaxation:")) for r in entry["reasons"])
        return (0 if unique else 1, -len(entry["reasons"]), entry["row"])

    ranked = sorted(ordered, key=weight)
    return sorted(ranked[:limit], key=lambda entry: entry["row"])


# --- сверка шапок -------------------------------------------------------------
def compare_headers(primary: dict, drift: dict) -> dict:
    """Сверить перечни колонок двух журналов — дословно и по порядку.

    Это прямой ответ на предупреждение пользователя, что часть второстепенных
    колонок архива может отличаться от действующей версии: сверка выписана
    так, чтобы её можно было повторить механически, когда приедет шапка
    действующего журнала.
    """
    left = [c["header"] for c in primary["columns"]]
    right = [c["header"] for c in drift["columns"]]
    return {
        "primary_order": left,
        "drift_order": right,
        "in_both": [h for h in left if h in right],
        "only_primary": [h for h in left if h not in right],
        "only_drift": [h for h in right if h not in left],
        "same_order": [h for h in left if h in right] == [h for h in right if h in left],
    }


def file_fingerprint(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"name": path.name, "size_bytes": path.stat().st_size, "sha256": digest}


def probe(path: Path, brief: bool = False) -> dict:
    structure = survey_workbook(path)
    journal = locate_journal(structure)
    rows = read_journal(path, journal)
    headers = [c["header"] for c in journal["columns"]]
    profiles = [
        profile_column(header, [record.get(header) for record in rows], brief=brief)
        for header in headers
    ]
    formulas = structure["formula_cells"].get(journal["sheet"], {"by_column": []})
    block_letters = {c["letter"] for c in journal["columns"]}
    computed = [item for item in formulas["by_column"] if item["letter"] in block_letters]
    broken = [
        {
            "row": record["__row__"],
            "value": cell_text(record.get(DESCRIPTION_HEADER)),
            "wo": cell_text(record.get(WO_HEADER)).strip() or None,
            "item": cell_text(record.get(ITEM_HEADER)).strip() or None,
        }
        for record in rows
        if record.get(DESCRIPTION_HEADER) is not None
        and not isinstance(record.get(DESCRIPTION_HEADER), str)
    ]
    coverage = analyse_descriptions(rows)
    dates = [h for h in headers if h in DATE_HEADERS]
    keys = analyse_key(rows, dates)
    edges = [] if brief else collect_edges(rows, coverage, EDGE_TARGET_MAX)
    return {
        "source": file_fingerprint(path),
        "structure": structure,
        "journal": journal,
        "profiles": profiles,
        "coverage": coverage,
        "computed_columns": computed,
        "broken_descriptions": broken,
        "key": keys,
        "edges": edges,
        "rows": rows,
    }



# --- находки и слепые пятна ---------------------------------------------------
BLIND_SPOTS = [
    "1. **Шапка действующего журнала не проверялась.** Её нет во входе наряда — это",
    "   объявленный пробел, а не упущение. Оба замеренных файла — архивы (2025 и 2024);",
    "   что ведётся в Teams сегодня, разведка не знает. Сверка §2 написана так, чтобы",
    "   стать механической, как только шапка приедет.",
    "2. **Что колонка значит — не измеряется.** Замер отвечает, чем колонка заполнена,",
    "   а не что она означает. `הערה` и `הערה יצור` различены здесь только заголовком.",
    "3. **Правильность разбора не проверена ни на одной строке.** Проверено только, что",
    "   шаблон **сработал**. Совпадение шаблона и верный смысл — разные утверждения;",
    "   различить их может лишь человек, читающий иврит, на выборке из §7.",
    "4. **Единицы величин неизвестны.** В журнале лежит голое число; миллиметры это или",
    "   что-то ещё, из текста не следует (в двух фрагментах стоит `mm` — и это всё).",
    "5. **Номинал и допуски в источнике отсутствуют.** Backbone даёт величину и",
    "   направление, но не то, от чего отклонились: колонка `מידה` в источнике",
    "   vestigial, а номинал живёт в чертеже, которого здесь нет.",
    "6. **Контекст обнаружения не разбирался** (`במהלך המדגם` / `מיון 100%`): он отложен",
    "   в `staging.md` на этап 2. Здесь он только посчитан как клауза контекста.",
    "7. **Связь строки с деталью не проверялась.** Совпадает ли номер детали журнала с",
    "   номенклатурой приложения — вопрос к справочнику деталей, а не к журналу.",
    "8. **Второй файл — не второй источник правил.** 2024 взят как вторая точка на шкале",
    "   времени; его профили сокращены намеренно, покрытие шаблонов по нему не считалось.",
    "9. **Порядок предъявления строк оператору не выводится из замера.** Строки на листе",
    "   идут не по возрастанию даты; в каком порядке их показывать — решение экрана.",
    "10. **Разбор не запускался на данных приложения.** Инструмент разведки и будущий ETL",
    "    — разные куски кода; совпадение их поведения этим нарядом не проверялось и",
    "    проверяться не могло: правила разбора ещё не написаны.",
]


def findings(primary: dict, drift: dict) -> list[tuple[str, list[str]]]:
    """Расхождения факта с каноном — числами из разделов выше.

    Текст находок живёт **в инструменте**, а не дописывается в отчёт руками:
    дописанный руками раздел исчез бы при следующем прогоне, и файл перестал бы
    быть воспроизводимым — то есть критерий детерминизма стал бы непроверяемым
    ровно там, где отчёт интереснее всего.
    """
    cov = primary["coverage"]
    canon = cov["backbone_canon_exact"]
    total = cov["backbone_total"]
    ladder = {step["step"]: step for step in cov["relaxation_ladder"]}
    hits = cov["relaxation_hits"]
    sheet = next(s for s in primary["structure"]["sheets"] if s["title"] == primary["journal"]["sheet"])
    machine = next((c for c in primary["computed_columns"] if c["letter"] == "N"), None)
    drift_dates = [c for c in drift["computed_columns"] if c["letter"] in ("D", "N")]
    pins = cov["fragment_kinds"].get("pin_canon", 0) + cov["fragment_kinds"].get("pin_variant", 0)
    key = primary["key"]["candidates"][0]
    journal_rows = primary["journal"]["last_data_row"] - primary["journal"]["first_data_row"] + 1

    items: list[tuple[str, list[str]]] = []

    items.append((
        "Дословный шаблон канона накрывает шестую часть массива, а не основную его долю",
        [
            f"Backbone-фрагментов — {total}. Из них шаблону канона",
            "`מידה {N} חורגת {מעל המקסימום|מתחת למינימום} {עד|ב} {value}` отвечают **дословно**",
            f"**{canon}** — {canon / total:.1%}. Остальное разбирается тем же шаблоном, но только",
            "после поимённых послаблений (§5.1).",
            "",
            "Это не значит, что канон неверен: backbone действительно **тот самый** костяк —",
            f"со всеми послаблениями он один берёт {total} фрагментов из {cov['fragments_total']}",
            f"({total / cov['fragments_total']:.1%}), а вместе с pin- и качественными —",
            f"{total + pins + cov['fragment_kinds'].get('gauge', 0)}. Это значит другое: правила",
            "разбора нельзя писать с шаблона как с литерала. Между каноном и массивом лежат",
            f"{len(RELAXATION_ORDER)} названных послаблений, и каждое придётся внести явно.",
        ],
    ))

    items.append((
        "Знак почти всегда стоит **после** числа, а предлог слит с числом",
        [
            f"`spacing-and-sign` требуется {hits.get('spacing-and-sign', 0)} фрагментам из {total}",
            f"({hits.get('spacing-and-sign', 0) / total:.1%}); одно это послабление даёт",
            f"+{ladder['spacing-and-sign']['added']} к покрытию — больше любого другого.",
            "Живая форма — `ב0.001-`: предлог приклеен к числу слева, знак стоит справа от",
            "числа. Канон пишет `{עד|ב} {value}`, то есть предполагает пробел и знак при числе.",
            "",
            f"Отдельно: `sign-after-number` встречается в {cov['noise'].get('sign-after-number', 0)}",
            "описаниях из 1113 непустых — это не редкость и не опечатка, а **основной способ",
            "записи знака** в этом журнале.",
        ],
    ))

    items.append((
        "Глагол `חורגת` опускается в каждом седьмом фрагменте",
        [
            f"`verb-omitted` — {hits.get('verb-omitted', 0)} фрагментов, +{ladder['verb-omitted']['added']}",
            "к покрытию. Живая форма — `מידה 15 מעל המקסימום ב 0.05`: размер, направление,",
            "величина — и ни одного глагола. Канон делает `חורגת` частью костяка; массив — нет.",
        ],
    ))

    items.append((
        "Подындекс точки замера пишется не так, как говорит канон",
        [
            "Канон: «a point sub-index is a bare number (`12 1`)». Фактическая запись:",
            "",
            _table(
                [[form, str(count)] for form, count in cov["subindex_notation"].items()],
                ["запись", "вхождений"],
            ),
            "",
            "Форма из канона (`N M`, через пробел) существует, но она **не преобладающая**.",
            f"Шире: `dimension-token` нужен {hits.get('dimension-token', 0)} фрагментам",
            f"(+{ladder['dimension-token']['added']} к покрытию) — туда же идут `[12]`, `19-1mm`,",
            "`Circle`, `3 ו4`. Номер размера не всегда целое число и не всегда число вообще.",
        ],
    ))

    items.append((
        "Все конфликты знака и слова оказались ложными: дефис — не минус",
        [
            f"Конфликтов «слово против знака числа»: **{len(cov['conflicts_word_vs_sign'])}**,",
            "и все они одной формы:",
            "",
            _table(
                [[str(item["count"]), _fence(item["form"])] for item in cov["conflict_shapes"]],
                ["вхождений", "форма"],
            ),
            "",
            "Здесь `ב - 0.004` — предлог `ב` с приставочным дефисом, а не «минус 0.004»;",
            "направление задано словом `בפלוס`, и оно верное. Настоящих конфликтов в массиве",
            "2025 нет **ни одного**, а эти тринадцать перевернул бы разбор, читающий дефис",
            "как знак.",
            "",
            "Правило канона «направление берётся из слова, знак числа — вторичная сверка»",
            "спасает ровно эти строки. Находка не против канона, а **за** него — но она",
            "добавляет требование: дефис, приставленный к предлогу `ב`, знаком не является",
            "и снимается до чтения знака, иначе флаг конфликта срабатывает вхолостую.",
        ],
    ))

    items.append((
        "Pin-шаблон канона накрывает три фрагмента из полутора сотен",
        [
            f"Фрагментов с `פין` — {pins}; шаблону `מידה {{N}} פין {{v}} נכנס/לא נכנס` дословно",
            f"отвечают **{cov['fragment_kinds'].get('pin_canon', 0)}**. Остальные — вариации:",
            "`נכנס` и `פין` меняются местами, добавляется `מינימום`/`מקסימום`, появляется",
            "второй, проверочный пин (`נבדק פין 2.05 נכנס`), заключение уточняется",
            f"(`נכנס חצי דרך`, `נכנס חופשי`). Форм — {len(cov['pin_forms'])}, все в §5.5.",
            "",
            "Пин — не край и не редкость: это второй по массовости способ описать отклонение",
            "в этом журнале.",
        ],
    ))

    items.append((
        "В журнале есть отклонения, которые не являются отклонением размера",
        [
            f"Фрагментов `unrecognised` — {cov['fragment_kinds'].get('unrecognised', 0)},",
            f"`partial` — {cov['fragment_kinds'].get('partial', 0)}; строк, где не разобрано",
            f"**ничего**, — {cov['row_coverage'].get('unrecognised', 0)} из {journal_rows}.",
            "Заметная часть остатка — не шум и не опечатка, а описания дефектов поверхности:",
            "ступенька в канавке, забоины, скол кромки, следы захвата, «маленькая ступенька",
            "в плане». У них нет ни номера размера, ни величины, ни направления — разбирать",
            "в находку нечего.",
            "",
            "Канон описывает только отклонение размера. Осознанное это сужение или пробел —",
            "решать Cowork; замер лишь показывает, что такой класс в журнале существует.",
        ],
    ))

    items.append((
        "Лист — не таблица: журнал занимает малую часть листа",
        [
            f"`max_row` листа 2025 — {sheet['max_row_reported']}; строк с данными на листе —",
            f"{sheet['last_row_with_data']}; строк **журнала** — {journal_rows}. Три разных",
            "числа, и все три встречаются в наивных подсчётах.",
            "",
            "На том же листе рядом с журналом лежат справочник `Production ID` / `CNC`",
            "(колонки `X`/`Y`, 3891 строка) и два обрывка источников выпадающих списков",
            "(`U` и `V`, четыре и девять значений). К журналу они отношения не имеют.",
            "**Импорт обязан брать блок колонок, а не лист.**",
        ],
    ))

    if machine:
        items.append((
            "Колонка `מכונה` не заполняется человеком — она вычисляется",
            [
                f"В колонке `N` — {machine['count']} формул вида `{machine['formula']}`,",
                "протянутых до конца листа; они и составляют десять мегабайт файла.",
                "Станок **выводится** из номера наряда по справочнику `X:Y`, то есть это не",
                "данные журнала, а их производная.",
                "",
                "Канон колонку `מכונה` не упоминает вовсе. Для импорта отсюда два следствия:",
                "значение не надо принимать как введённое оператором, и связь",
                "«наряд → станок» существует отдельным справочником — её можно взять готовой.",
            ],
        ))

    if drift_dates:
        items.append((
            "В журнале 2024 дата закрытия — волатильная формула, а не дата",
            [
                _table(
                    [[item["letter"], str(item["count"]), _fence(item["formula"][:110])] for item in drift_dates],
                    ["колонка", "формул", "формула"],
                ),
                "",
                "`TODAY()` и `NOW()` пересчитываются при каждом открытии книги: в ячейке лежит",
                "не дата закрытия, а день, когда файл в последний раз открыли. В журнале 2025",
                "колонка `תאריך סגירה` формул не содержит и держит значения.",
                "",
                "Ключ строки, построенный на дате, устойчив поэтому **только для 2025**. Если",
                "в действующем журнале формула вернулась — ключ на дате брать нельзя, и это",
                "первое, что надо проверить в его шапке.",
            ],
        ))

    items.append((
        "Постановочный ключ не уникален — и это не главная его проблема",
        [
            f"По дате закрытия и номеру наряда: повторяющихся пар — {key['pairs_seen_more_than_once']},",
            f"строк в них — {key['rows_in_repeated_pairs']} из {journal_rows}, максимум строк",
            f"на пару — {key['max_rows_per_pair']}. Один наряд за один день даёт несколько",
            "отклонений — это норма процесса, а не грязь данных.",
            "",
            "Добавление текста описания снимает почти всё: троек, встреченных больше раза, —",
            f"{key['triples_seen_more_than_once']}, строк в них — {key['rows_in_repeated_triples']}.",
            "Но не всё: полные совпадения по всем трём полям остаются, и различить их",
            "нечем — в источнике нет ни одной колонки, которая бы их развела.",
            "",
            f"**Важнее другое: {key['rows_without_date']} строк без даты закрытия и",
            f"{key['rows_without_wo']} без номера наряда ключа не образуют вовсе.** Их нельзя",
            "ни склеить, ни отбросить: непропуск строки важнее дедупликации, значит на экране",
            "импорта они обязаны быть видимой категорией, а не тихим остатком.",
            "",
            f"Вторая дата (`תאריך שליחת חריגה`) заполнена {primary['key']['candidates'][1]['rows_with_full_key']}",
            f"раз из {journal_rows} и ключом служить не может.",
        ],
    ))

    if primary["broken_descriptions"]:
        items.append((
            "Две строки журнала — настоящие отклонения с потерянным описанием",
            [
                _table(
                    [
                        [str(row["row"]), _fence(row["value"]), _fence(row["wo"] or "—"), _fence(row["item"] or "—")]
                        for row in primary["broken_descriptions"]
                    ],
                    ["строка", "значение в описании", "наряд", "деталь"],
                ),
                "",
                "У обеих заполнены наряд, деталь, количество и решение — это не пустые строки",
                "и не разделители. В строке 281 в ячейку описания попала чужая формула",
                "`=SUBTOTAL(109,K2:K280)`, давшая `0`; в строке 25 лежит просто `0`.",
                "",
                "Для импорта это отдельный случай: **строка есть, описания нет**. Пропустить",
                "её нельзя, разбирать нечего — значит нужна категория «без описания», и она",
                "не совпадает ни с «не распознано», ни с «пустая строка».",
            ],
        ))

    items.append((
        "Шапки 2025 и 2024 расходятся на четыре колонки",
        [
            "Общих колонок десять, и порядок их совпадает. Расходятся четыре: `מכונה` и",
            "`תאריך שליחת חריגה` есть только в 2025, `NCR` и `תאריך פתיחה` — только в 2024",
            "(§2).",
            "",
            "Предупреждение пользователя подтвердилось: второстепенные колонки между годами",
            "плывут. Ядро — описание, наряд, деталь, количество, решение техотдела,",
            "ответственный, дата закрытия — устойчиво в обоих файлах. Правила разбора",
            "безопасно опирать на ядро; всё остальное — только после сверки с действующей",
            "шапкой.",
        ],
    ))

    items.append((
        "Разделитель находок внутри ячейки — не один",
        [
            _table(
                [[f"`{k}`", str(v)] for k, v in cov["separators"].items()],
                ["разделитель", "описаний"],
            ),
            "",
            "Канон говорит «одна строка Excel → одно отклонение с массивом находок», но чем",
            "находки разделены — не называет. Их разделяют переводом строки, запятой и союзом",
            f"`ו`; максимум находок в одной ячейке — {max(int(k) for k in cov['fragments_per_row'])}.",
            "Запятая при этом встречается и **внутри** находки, поэтому порядок разбиения",
            "(сперва перевод строки, затем запятая, затем союз) — часть правил, а не деталь",
            "реализации.",
        ],
    ))

    return items

# --- рендер -------------------------------------------------------------------
def _escape_pipes(cell: str) -> str:
    """Экранировать вертикальную черту, ещё не экранированную.

    Иначе `{מעל המקסימום|מתחת למינימום}` — кусок шаблона канона — разваливает
    строку таблицы на две колонки, и таблица в отчёте едет.
    """
    return re.sub(r"(?<!\\)\|", r"\\|", cell)


def _table(rows: list[list[str]], head: list[str]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(_escape_pipes(cell) for cell in row) + " |" for row in rows]
    return out


def _fence(text: str) -> str:
    """Обернуть ивритское значение в кодовый span — иначе оно склеится с рамкой."""
    return "`" + text.replace("|", "\\|").replace("\n", "⏎").replace("`", "'") + "`"


def render_markdown(primary: dict, drift: dict, comparison: dict, originals: dict) -> str:
    cov = primary["coverage"]
    out: list[str] = []
    add = out.append

    add("# 0033 — разведка по архивному журналу отклонений")
    add("")
    add("> Отчёт наряда `docs/worklog/0033-import-journal-recon.md`. Снят инструментом")
    add("> `tools/import_journal_probe.py`; отметок времени в файле нет намеренно —")
    add("> иначе повторный прогон давал бы другой файл и критерий детерминизма был бы")
    add("> непроверяем. Машиночитаемая версия — `0033-import-journal-stats.json`.")
    add("")
    add("**Чего этот отчёт не делает.** Он не пишет правила разбора и не правит канон.")
    add("Он измеряет, какую долю массива накрывают шаблоны, которые в")
    add("`docs/model/Import-Workflow.md` §ETL **уже есть**. Расхождения факта с каноном")
    add("собраны в §9 как находки.")
    add("")

    add("## 0. Источники и неприкосновенность оригиналов")
    add("")
    add(
        r"Работа шла с копией; в `C:\Workbook` не записано ничего. Размер и время правки"
    )
    add("оригиналов до и после работы:")
    add("")
    add("\n".join(_table(
        [
            [
                _fence(name),
                str(state["before"]["size"]),
                state["before"]["mtime"],
                str(state["after"]["size"]),
                state["after"]["mtime"],
                "совпало" if state["same"] else "**РАСХОЖДЕНИЕ**",
            ]
            for name, state in originals.items()
        ],
        ["файл", "размер до", "mtime до", "размер после", "mtime после", "итог"],
    )))
    add("")
    add("\n".join(_table(
        [
            [_fence(book["source"]["name"]), str(book["source"]["size_bytes"]), book["source"]["sha256"][:16] + "…"]
            for book in (primary, drift)
        ],
        ["копия", "размер", "sha256"],
    )))
    add("")

    for title, book in (("основной массив (2025)", primary), ("контроль дрейфа (2024)", drift)):
        sheet = next(s for s in book["structure"]["sheets"] if s["title"] == book["journal"]["sheet"])
        add(f"## 1{'' if book is primary else chr(1072)}. Структура книги — {title}")
        add("")
        add(f"- листы: {', '.join(_fence(n) for n in book['structure']['sheet_names'])}; "
            f"скрытых листов: {len(book['structure']['hidden_sheets'])}")
        add(f"- лист журнала: {_fence(sheet['title'])} — опознан по признаку: {book['journal']['identified_by']}")
        add(f"- рамка листа: `{sheet['dimensions']}`, `max_row` = {sheet['max_row_reported']}, "
            f"`max_column` = {sheet['max_column_reported']}")
        add(f"- **последняя строка с данными на листе: {sheet['last_row_with_data']}** — "
            "`max_row` листа к числу строк журнала отношения не имеет")
        add(f"- строка шапки: {sheet['header_row']}; объединённых ячеек на листе: "
            f"{len(sheet['merged_ranges'])} ({', '.join(sheet['merged_ranges']) or 'нет'}); "
            f"в шапке: {', '.join(sheet['merged_in_header']) or 'нет'}")
        add(f"- автофильтр: {sheet['auto_filter'] or 'нет'}; заморозка панелей: {sheet['freeze_panes'] or 'нет'}")
        add(f"- скрытые колонки: {', '.join(sheet['hidden_columns']) or 'нет'}")
        formulas = book["structure"]["formula_cells"].get(sheet["title"], {"total": 0, "by_column": []})
        add(f"- формул на листе: {formulas['total']}, по колонкам:")
        for item in formulas["by_column"]:
            add(f"  - `{item['letter']}` — {item['count']}, первая в строке {item['row']}: "
                f"`{item['formula'][:90]}`")
        add(f"- **блок журнала**: колонки "
            f"{book['journal']['columns'][0]['letter']}–{book['journal']['columns'][-1]['letter']}, "
            f"строки данных {book['journal']['first_data_row']}–{book['journal']['last_data_row']} "
            f"(**{book['journal']['last_data_row'] - book['journal']['first_data_row'] + 1}** строк)")
        outside = book["journal"]["outside_block"]
        if outside:
            add("- **вне блока журнала на том же листе** (к журналу отношения не имеет):")
            for column in outside:
                add(f"  - `{column['letter']}` — заголовок "
                    f"{_fence(column['header']) if column['header'] else '**нет**'}, "
                    f"строки {column['first_row']}–{column['last_row']}, "
                    f"заполнено {column['filled_rows']}")
        add("")
    add("## 2. Шапки обоих файлов дословно и их сверка")
    add("")
    for title, book in (("2025 — основной массив", primary), ("2024 — контроль дрейфа", drift)):
        add(f"**{title}:**")
        add("")
        add("\n".join(_table(
            [
                [column["letter"], _fence(column["header"]), str(column["filled_rows"] - 1)]
                for column in book["journal"]["columns"]
            ],
            ["колонка", "заголовок дословно", "заполненных строк данных"],
        )))
        add("")
    add("**Сверка 2025 ↔ 2024:**")
    add("")
    add("\n".join(_table(
        [
            [_fence(h), "есть", "есть"] for h in comparison["in_both"]
        ] + [
            [_fence(h), "есть", "—"] for h in comparison["only_primary"]
        ] + [
            [_fence(h), "—", "есть"] for h in comparison["only_drift"]
        ],
        ["заголовок", "2025", "2024"],
    )))
    add("")
    add(f"Порядок общих колонок совпадает: **{'да' if comparison['same_order'] else 'нет'}**.")
    add("")

    add("## 3. Профили колонок журнала 2025")
    add("")
    add("\n".join(_table(
        [
            [
                _fence(p["header"]),
                f"{p['non_empty']} / {p['empty']}",
                f"{p['fill_share']:.1%}",
                str(p["distinct"]),
                ", ".join(f"{k}:{v}" for k, v in p["types"].items()),
                "·".join(str(p["text_length"][k]) for k in ("min", "median", "p95", "max")),
            ]
            for p in primary["profiles"]
        ],
        ["колонка", "непусто / пусто", "доля", "различных", "типы ячеек", "длина min·med·p95·max"],
    )))
    add("")
    add("**Аномалии по колонкам** (пусто — ни одной):")
    add("")
    rows_anomaly = [
        [
            _fence(p["header"]),
            *[str(p["anomalies"][k]) for k in (
                "outer_space", "double_space", "inner_newline", "bidi_marks",
                "nbsp", "numeric_as_text", "date_as_text",
            )],
        ]
        for p in primary["profiles"]
        if any(p["anomalies"].values())
    ]
    add("\n".join(_table(
        rows_anomaly,
        ["колонка", "крайние пробелы", "двойной пробел", "перевод строки",
         "bidi-метки", "nbsp", "число текстом", "дата текстом"],
    )))
    add("")
    add("**Полные распределения** для колонок с ≤ 50 различными значениями "
        "(кандидаты в справочники) — целиком, без усечения:")
    add("")
    for p in primary["profiles"]:
        if "frequencies" not in p:
            add(f"- {_fence(p['header'])} — {p['distinct']} различных значений, "
                "распределение целиком в JSON (`profiles[].top_values` — только верхушка)")
            continue
        add(f"- {_fence(p['header'])} — {p['distinct']} различных:")
        for entry in p["frequencies"]:
            add(f"  - {_fence(entry['value'])} — {entry['count']}")
    add("")
    for p in primary["profiles"]:
        if "date_forms" in p:
            forms = p["date_forms"]
            add(f"- даты в {_fence(p['header'])}: все {forms['as_datetime']} лежат "
                f"значением `datetime`, с ненулевым временем — {forms['with_nonzero_time']}; "
                f"диапазон {forms['min']} … {forms['max']}; "
                f"датой-текстом — {p['anomalies']['date_as_text']}")
    add("")

    add("## 4. Профили колонок журнала 2024 (сокращённо)")
    add("")
    add("\n".join(_table(
        [
            [
                _fence(p["header"]),
                f"{p['non_empty']} / {p['empty']}",
                f"{p['fill_share']:.1%}",
                str(p["distinct"]),
                ", ".join(f"{k}:{v}" for k, v in p["types"].items()),
            ]
            for p in drift["profiles"]
        ],
        ["колонка", "непусто / пусто", "доля", "различных", "типы ячеек"],
    )))
    add("")
    add("## 5. Покрытие каноничных шаблонов — сердце наряда (Q-17)")
    add("")
    rows_total = cov["rows_total"]
    add(f"Строк журнала: **{rows_total}**. Разрез по строкам (сумма сходится с "
        f"{rows_total}):")
    add("")
    add("\n".join(_table(
        [[k, str(v), f"{v / rows_total:.1%}"] for k, v in cov["row_coverage"].items()]
        + [["**сумма**", str(sum(cov["row_coverage"].values())), ""]],
        ["покрытие строки", "строк", "доля"],
    )))
    add("")
    add(f"Описания режутся на находки; всего фрагментов **{cov['fragments_total']}**. "
        "Разрез по фрагментам (сумма сходится с числом фрагментов):")
    add("")
    add("\n".join(_table(
        [[k, str(v), f"{v / cov['fragments_total']:.1%}"]
         for k, v in cov["fragment_kinds"].items()]
        + [["**сумма**", str(sum(cov["fragment_kinds"].values())), ""]],
        ["категория фрагмента", "фрагментов", "доля"],
    )))
    add("")
    add("### 5.1 Лестница послаблений")
    add("")
    add("Ответ «backbone накрывает N %» без разбивки бесполезен — он не говорит, чего")
    add("шаблону не хватает. Поэтому каждая ступень — **поимённое послабление**, и видно,")
    add("сколько добавляет каждое. База ступени `canon` — дословный шаблон канона")
    add("`מידה {N} חורגת {מעל המקסימום|מתחת למינימום} {עד|ב} {value}`, одинарные пробелы,")
    add(f"знак только перед числом. Знаменатель — {cov['backbone_total']} фрагментов, "
        "разобранных backbone-шаблоном в любой его форме.")
    add("")
    add("\n".join(_table(
        [
            [
                f"`{step['step']}`",
                step["note"],
                str(step["added"]),
                str(step["cumulative"]),
                f"{step['cumulative'] / cov['backbone_total']:.1%}",
            ]
            for step in cov["relaxation_ladder"]
        ],
        ["ступень", "что допускает", "+ добавила", "накопительно", "доля backbone"],
    )))
    add("")
    add("Сколько фрагментов требует каждого послабления (флаги независимы, "
        "сумма больше числа фрагментов — это норма):")
    add("")
    add("\n".join(_table(
        [[f"`{k}`", str(v)] for k, v in cov["relaxation_hits"].items()],
        ["послабление", "фрагментов"],
    )))
    add("")
    add("### 5.2 Чем разделены находки в одной ячейке")
    add("")
    add("\n".join(_table(
        [[f"`{k}`", str(v)] for k, v in cov["separators"].items()],
        ["разделитель", "описаний, где встретился"],
    )))
    add("")
    add("Находок в одной ячейке (сумма сходится с числом строк журнала):")
    add("")
    add("\n".join(_table(
        [[str(k), str(v)] for k, v in cov["fragments_per_row"].items()]
        + [["**сумма**", str(sum(cov["fragments_per_row"].values()))]],
        ["фрагментов в ячейке", "строк"],
    )))
    add("")
    add("### 5.3 Известный шум")
    add("")
    add("Флаги независимы: одно описание бывает разом и выборкой, и с приклеенным знаком,")
    add("и с опечаткой. Счёт — по описаниям, не по фрагментам.")
    add("")
    add("\n".join(_table(
        [[f"`{k}`", str(v)] for k, v in cov["noise"].items()],
        ["вид шума", "описаний"],
    )))
    add("")
    conflicts = cov["conflicts_word_vs_sign"]
    add(f"**Конфликт «слово против знака числа»: {len(conflicts)}.** Канон отдаёт приоритет "
        "словесному направлению, знак числа — вторичная сверка; здесь она расходится.")
    if conflicts:
        add("")
        add("\n".join(_table(
            [[str(c["row"]), _fence(c["text"]), c["word"], c["sign"]] for c in conflicts[:20]],
            ["строка", "фрагмент", "слово", "знак числа"],
        )))
        if len(conflicts) > 20:
            add("")
            add(f"Показаны первые 20 из {len(conflicts)}; полный список — в JSON "
                "(`coverage.conflicts_word_vs_sign`), он не усечён.")
    add("")
    add("### 5.4 Неразобранные формы — частотным списком, целиком")
    add("")
    add(f"Форм: **{len(cov['unparsed_forms'])}**, вхождений: "
        f"**{sum(f['count'] for f in cov['unparsed_forms'])}**. Форма — описание с числами,")
    add("заменёнными на `#`; список **не усечён**.")
    add("")
    add("\n".join(_table(
        [
            [str(form["count"]), form["kind"], form["reason"] or "—", str(form["row"]), _fence(form["form"])]
            for form in cov["unparsed_forms"]
        ],
        ["вхождений", "категория", "чего не хватает", "строка примера", "форма"],
    )))
    add("")
    if cov["context_prefixes"]:
        add("Клаузы контекста **перед** шаблоном (`context-prefix`), целиком:")
        add("")
        add("\n".join(_table(
            [[str(item["count"]), _fence(item["text"])] for item in cov["context_prefixes"]],
            ["вхождений", "клауза"],
        )))
        add("")
    if cov["context_suffixes"]:
        add("Хвосты **после** величины (`context-suffix`), целиком:")
        add("")
        add("\n".join(_table(
            [[str(item["count"]), _fence(item["text"])] for item in cov["context_suffixes"]],
            ["вхождений", "хвост"],
        )))
        add("")
    add("### 5.5 Pin-шаблон и качественные заключения")
    add("")
    add("Канон несёт второй шаблон — `מידה {N} פין {v} נכנס/לא נכנס` — и правило, что на")
    add("этапе 1 пин уходит в `comment`. Фрагмент с `פין` относится к пину, даже если в")
    add("нём есть и backbone: порядок проб объявлен, и величины у такого фрагмента нет.")
    add("")
    add(f"Дословно по канону — **{cov['fragment_kinds'].get('pin_canon', 0)}** фрагментов из "
        f"{cov['fragment_kinds'].get('pin_canon', 0) + cov['fragment_kinds'].get('pin_variant', 0)}. "
        "Формы целиком, без усечения:")
    add("")
    add("\n".join(_table(
        [[str(f["count"]), f["kind"], str(f["row"]), _fence(f["form"])] for f in cov["pin_forms"]],
        ["вхождений", "категория", "строка примера", "форма"],
    )))
    add("")
    add(f"Качественные (`מדיד` / `GO`) — **{cov['fragment_kinds'].get('gauge', 0)}** фрагментов, "
        "формы целиком:")
    add("")
    add("\n".join(_table(
        [[str(f["count"]), str(f["row"]), _fence(f["form"])] for f in cov["gauge_forms"]],
        ["вхождений", "строка примера", "форма"],
    )))
    add("")
    add("## 6. Ключ строки")
    add("")
    add("Постановкой ключ — **дата + `פק\"ע` + текст описания**. Дат в журнале больше")
    add("одной, и наряд не говорит какую; поэтому посчитаны **все** кандидаты, выбор — за")
    add("Cowork.")
    add("")
    add("\n".join(_table(
        [
            [
                _fence(c["date_header"]),
                str(c["rows_with_full_key"]),
                str(c["rows_without_date"]),
                str(c["rows_without_wo"]),
                str(c["rows_without_either"]),
                f"{c['pairs_seen_more_than_once']} / {c['rows_in_repeated_pairs']} / {c['max_rows_per_pair']}",
                f"{c['triples_seen_more_than_once']} / {c['rows_in_repeated_triples']} / {c['max_rows_per_triple']}",
            ]
            for c in primary["key"]["candidates"]
        ],
        [
            "колонка даты", "строк с полным ключом", "без даты", "без `פק\"ע`",
            "без обоих", "пар>1: пар / строк / макс", "троек>1: троек / строк / макс",
        ],
    )))
    add("")
    add("**Строки без даты или без `פק\"ע` ключа не образуют вовсе** — и это важнее дубля:")
    add("непропуск строки важнее дедупликации. Их нельзя ни склеить, ни отбросить молча;")
    add("на экране импорта они обязаны быть видимой категорией.")
    add("")
    for candidate in primary["key"]["candidates"]:
        if candidate["examples_repeated_triples"]:
            add(f"Примеры полных совпадений по тройке для {_fence(candidate['date_header'])}:")
            add("")
            add("\n".join(_table(
                [
                    [str(e["count"]), e["date"][:10], _fence(e["wo"]), _fence(e["text"][:70])]
                    for e in candidate["examples_repeated_triples"]
                ],
                ["строк", "дата", "`פק\"ע`", "описание"],
            )))
            add("")

    add("## 7. Кандидаты «краёв»")
    add("")
    edges = primary["edges"]
    add(f"Строк-кандидатов: **{len(edges)}** (целевой объём наряда — 60–120). Выбор")
    add("детерминированный: категории в фиксированном порядке, внутри категории — первое")
    add("вхождение по номеру строки. **Выбор делает Cowork**; здесь только материал.")
    add("")
    add(f"Чего в этой выборке нет намеренно: по одной строке на каждую из "
        f"{len(cov['pin_forms'])} pin-форм и {len(cov['gauge_forms'])} качественных форм — "
        "иначе выборка вышла бы за")
    add("верхнюю границу наряда. Обе формы перечислены целиком в §5.5 **с номером строки")
    add("примера**, так что расширить выборку ими — механическое действие, а не новый замер.")
    add("")
    add("\n".join(_table(
        [
            [
                str(edge["row"]),
                _fence(edge["wo"] or "—"),
                _fence(edge["item"] or "—"),
                ", ".join(f"`{r}`" for r in edge["reasons"]),
                _fence(edge["description"] or "—"),
            ]
            for edge in edges
        ],
        ["строка", "`פק\"ע`", "`מק\"ט`", "чем интересна", "описание"],
    )))
    add("")

    add("## 8. Детерминизм, сходимость счёта и отсутствие усечения")
    add("")
    add("Сходимость счёта — **механизм, а не утверждение**: проверки ниже прогоняются")
    add("самим инструментом на каждом запуске, и несошедшийся счёт роняет прогон, а не")
    add("оседает незамеченным в отчёте.")
    add("")
    add("\n".join(_table(
        [[name, "сходится" if ok else "**НЕ СХОДИТСЯ**", f"`{detail}`"] for name, ok, detail in verify_sums(primary)],
        ["что проверяется", "итог", "числа"],
    )))
    add("")
    add("- Скрипт читает книгу целиком: ни `head`, ни `limit`, ни «первых N» в счёте нет.")
    add("  Усечение есть **только** в показе — и там, где оно есть, названо числом и")
    add("  сопровождается ссылкой на полный список в JSON.")
    add("- Все отрицательные утверждения этого отчёта («такой формы нет», «встречается")
    add("  только здесь») получены полным счётом по всем строкам блока журнала.")
    add("- Повторный прогон на том же файле даёт побайтово тот же результат: отметок")
    add("  времени в выводе нет, все словари отсортированы, порядок выборки задан.")
    add("- `stdout`/`stderr` переключены на UTF-8 в начале скрипта — консоль рабочей")
    add("  машины `cp1255`, иначе печать иврита падает с `UnicodeEncodeError`.")
    add("")

    add("## 9. Находки — расхождения факта с каноном")
    add("")
    add("Канон этим нарядом **не правится** (наряд, «Чего не трогать»); ниже — материал")
    add("для его правки. Каждая находка названа числом из разделов выше.")
    add("")
    for number, (title, body) in enumerate(findings(primary, drift), 1):
        add(f"### 9.{number} {title}")
        add("")
        for line in body:
            # Таблица приходит списком строк — раскладываем, а не печатаем список.
            out.extend(line) if isinstance(line, list) else add(line)
        add("")

    add("## 10. Чего массив не показывает")
    add("")
    add("Честный перечень того, на что разведка ответа **не даёт**. Он существует не для")
    add("полноты изложения: без него числа выше читаются как ответ на вопрос, который им")
    add("не задавали.")
    add("")
    for line in BLIND_SPOTS:
        add(line)
    add("")
    return "\n".join(out) + "\n"


def strip_for_json(book: dict) -> dict:
    """Убрать из выгрузки сами строки журнала — в артефакт идут агрегаты.

    Массив целиком в git не кладётся никогда (`Import-Workflow.md`
    §Determinism / privacy). Отдельные значения не sensitive и остаются:
    без них выборка «краёв» была бы списком номеров строк без содержимого,
    то есть бесполезной.
    """
    trimmed = {k: v for k, v in book.items() if k != "rows"}
    coverage = dict(trimmed["coverage"])
    coverage.pop("per_row", None)
    trimmed["coverage"] = coverage
    return trimmed


def verify_sums(book: dict) -> list[tuple[str, bool, str]]:
    """Проверить, что счёт сходится — механизмом, а не утверждением в отчёте.

    Критерий приёмки 3 наряда `0033` требует, чтобы сумма строк по всем
    категориям каждого разреза равнялась числу строк листа. Это та же гарантия
    непропуска, что и на экране импорта, и место ей — в коде, который её
    считает: заявление в отчёте молчит ровно тогда, когда категория потерялась.
    """
    cov = book["coverage"]
    rows = book["journal"]["last_data_row"] - book["journal"]["first_data_row"] + 1
    checks = [
        (
            "строки по покрытию = строки журнала",
            sum(cov["row_coverage"].values()) == rows,
            f"{sum(cov['row_coverage'].values())} == {rows}",
        ),
        (
            "строки по числу находок = строки журнала",
            sum(cov["fragments_per_row"].values()) == rows,
            f"{sum(cov['fragments_per_row'].values())} == {rows}",
        ),
        (
            "фрагменты по категориям = все фрагменты",
            sum(cov["fragment_kinds"].values()) == cov["fragments_total"],
            f"{sum(cov['fragment_kinds'].values())} == {cov['fragments_total']}",
        ),
        (
            "находки, разложенные по ячейкам, = все фрагменты",
            sum(int(count) * int(size) for size, count in cov["fragments_per_row"].items())
            == cov["fragments_total"],
            f"{sum(int(c) * int(k) for k, c in cov['fragments_per_row'].items())}"
            f" == {cov['fragments_total']}",
        ),
        (
            "последняя ступень лестницы = все backbone-фрагменты",
            cov["relaxation_ladder"][-1]["cumulative"] == cov["backbone_total"],
            f"{cov['relaxation_ladder'][-1]['cumulative']} == {cov['backbone_total']}",
        ),
        (
            "профиль описания: непустых + пустых = строки журнала",
            next(p["non_empty"] + p["empty"] for p in book["profiles"] if p["header"] == DESCRIPTION_HEADER)
            == rows,
            str(rows),
        ),
        (
            "каждая неразобранная форма представлена строкой в выборке краёв",
            {f["row"] for f in cov["unparsed_forms"]} <= {e["row"] for e in book["edges"]},
            f"{len(cov['unparsed_forms'])} форм",
        ),
    ]
    return checks


def snapshot(paths: list[Path]) -> dict:
    return {
        path.name: {"size": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat()}
        for path in paths
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("primary", type=Path, help="основной массив (.xlsx)")
    parser.add_argument("drift", type=Path, nargs="?", help="контроль дрейфа (.xlsx)")
    parser.add_argument("--json", type=Path, help="куда положить машиночитаемую статистику")
    parser.add_argument("--md", type=Path, help="куда положить отчёт человеку")
    parser.add_argument(
        "--originals", type=Path, nargs="*", default=[],
        help="оригиналы, чью неизменность надо доказать (снимок до/после)",
    )
    args = parser.parse_args(argv)

    before = snapshot(args.originals)
    primary = probe(args.primary)
    drift = probe(args.drift, brief=True) if args.drift else None
    after = snapshot(args.originals)
    originals = {
        name: {"before": before[name], "after": after[name], "same": before[name] == after[name]}
        for name in sorted(before)
    }

    comparison = compare_headers(primary["journal"], drift["journal"]) if drift else {}
    payload = {
        "order": "docs/worklog/0033-import-journal-recon.md",
        "originals": originals,
        "primary": strip_for_json(primary),
        "drift": strip_for_json(drift) if drift else None,
        "header_comparison": comparison,
    }

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.md and drift:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(
            render_markdown(primary, drift, comparison, originals), encoding="utf-8", newline="\n"
        )

    failed = [name for name, ok, _ in verify_sums(primary) if not ok]
    if failed:
        raise SystemExit("счёт не сходится: " + "; ".join(failed))

    cov = primary["coverage"]
    print(f"rows: {cov['rows_total']}  coverage: {cov['row_coverage']}")
    print(f"fragments: {cov['fragments_total']}  kinds: {cov['fragment_kinds']}")
    print(f"backbone canon-exact: {cov['backbone_canon_exact']} of {cov['backbone_total']}")
    print(f"unparsed forms: {len(cov['unparsed_forms'])}  edges: {len(primary['edges'])}")
    for name, state in originals.items():
        print(f"original {name}: {'unchanged' if state['same'] else 'CHANGED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
