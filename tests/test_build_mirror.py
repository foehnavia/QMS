"""Сторож зеркала по содержимому — Q-09 (критерий 13 наряда 0005).

Прежний сторож сверял `source_version` зеркала с `rev` канона, а `rev` поднимался
руками: пропустили подъём — сторож зелёный, зеркало устарело. Смысл затеи в том,
чтобы проверка перестала зависеть от ручного поля, поэтому главный тест здесь —
**красный вердикт после правки канона без подъёма `rev`**.

Правки канона делаются во временной копии: `docs/model/` — слой Cowork.
"""

from __future__ import annotations

import ast
import io
import shutil
from pathlib import Path

import pytest

from tools.build_mirror import (
    body_hash,
    build,
    canon_hash,
    check,
    collect,
    main,
    parse_front_matter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = REPO_ROOT / "docs" / "model"


@pytest.fixture
def canon(tmp_path: Path) -> Path:
    """Полная копия канона во временном каталоге — оригинал не трогаем."""
    target = tmp_path / "model"
    shutil.copytree(MODEL, target)
    return target


def _mirror(canon_dir: Path, out: Path) -> Path:
    items = collect(canon_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(items, canon_hash(canon_dir, items)), encoding="utf-8")
    return out


def _verdict(canon_dir: Path, mirror: Path) -> tuple[int, str]:
    stream = io.StringIO()
    code = check(canon_dir, mirror, stream=stream)
    return code, stream.getvalue()


# --- Штамп ------------------------------------------------------------------------


def test_mirror_carries_a_source_hash(canon: Path, tmp_path: Path) -> None:
    mirror = _mirror(canon, tmp_path / "mirror.md")
    meta, _body = parse_front_matter(mirror.read_text(encoding="utf-8"))

    assert meta["source_hash"].startswith("sha256:")
    # `source_version` остаётся — его читает человек, а не сторож.
    assert meta["source_version"] == "1.00"


def test_hash_is_stable_across_reruns(canon: Path) -> None:
    """Пересборка неизменного канона даёт тот же хеш — иначе сторож бесполезен."""
    assert canon_hash(canon, collect(canon)) == canon_hash(canon, collect(canon))


def test_hash_ignores_line_endings(canon: Path) -> None:
    """CRLF после checkout на Windows не должен выглядеть как правка канона."""
    before = canon_hash(canon, collect(canon))

    for path in list(canon.glob("*.md")) + list((canon / "reference").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="")

    assert canon_hash(canon, collect(canon)) == before


def test_hash_notices_a_rename(canon: Path) -> None:
    """Путь входит в хеш: переименование — изменение, даже если текст тот же."""
    before = canon_hash(canon, collect(canon))
    (canon / "Search.md").rename(canon / "Search2.md")

    assert canon_hash(canon, collect(canon)) != before


# --- Критерий 13: зелёный на свежем, красный после правки --------------------------


def test_check_is_green_on_a_freshly_generated_mirror(canon: Path, tmp_path: Path) -> None:
    mirror = _mirror(canon, tmp_path / "mirror.md")

    code, output = _verdict(canon, mirror)

    assert code == 0
    assert "VERDICT: OK" in output


def test_check_goes_red_when_canon_changes_without_a_rev_bump(
    canon: Path, tmp_path: Path
) -> None:
    """Сердце Q-09: правка канона видна сторожу **без** подъёма `rev` руками."""
    mirror = _mirror(canon, tmp_path / "mirror.md")
    assert _verdict(canon, mirror)[0] == 0

    victim = canon / "Search.md"
    text = victim.read_text(encoding="utf-8")
    # `rev` читается из файла, а не вписывается константой. Прибитая версия делала тест
    # красным при каждой правке канона (упал на `rev: "1.02"`, наряд 0022) — сообщая при
    # этом не о стороже, а о том, что Cowork поработал. Проверяется, что поле **не
    # изменилось**, а какое оно — дело канона.
    rev_line = next(line for line in text.splitlines() if line.startswith("rev:"))
    # Правим тело, поле `rev` намеренно не трогаем — прежний сторож это пропускал.
    victim.write_text(text + "\nA sentence added after the mirror was built.\n", encoding="utf-8")

    code, output = _verdict(canon, mirror)

    assert code == 1
    assert "VERDICT: STALE" in output
    assert rev_line in victim.read_text(encoding="utf-8")


def test_check_explains_which_files_it_hashed(canon: Path, tmp_path: Path) -> None:
    """Расхождение надо объяснять, а не только констатировать."""
    mirror = _mirror(canon, tmp_path / "mirror.md")

    _code, output = _verdict(canon, mirror)

    assert "canon files (12), in hashing order:" in output
    assert "- Search.md" in output
    assert "- reference/reference-data.md" in output


def test_check_calls_a_mirror_without_a_source_hash_stale(canon: Path, tmp_path: Path) -> None:
    """Зеркало, собранное до сторожа, штампа канона не несёт — это тоже «устарело».

    Строка вырезается точечно, тело остаётся байт в байт. Прежняя пересборка через
    `splitlines()` съедала завершающий перевод строки — после QMS-019 сторож считает
    и тело, и такой файл доложился бы как `CORRUPT`. Диагноз был бы верным (тело
    действительно испорчено), но тест проверял бы не то, ради чего написан.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    text = mirror.read_text(encoding="utf-8")
    victim = next(line for line in text.splitlines() if line.startswith("source_hash:"))
    mirror.write_text(text.replace(victim + "\n", "", 1), encoding="utf-8")

    code, output = _verdict(canon, mirror)

    assert code == 1
    assert "no source_hash" in output


def test_check_reports_a_missing_mirror(canon: Path, tmp_path: Path) -> None:
    code, output = _verdict(canon, tmp_path / "nowhere.md")

    assert code == 1
    assert "mirror not found" in output


def test_check_writes_nothing(canon: Path, tmp_path: Path) -> None:
    """Проверка обязана быть безопасной — её зовут и против волта."""
    mirror = _mirror(canon, tmp_path / "mirror.md")
    before = mirror.read_bytes()
    canon_before = {p: p.read_bytes() for p in canon.rglob("*.md")}

    _verdict(canon, mirror)

    assert mirror.read_bytes() == before
    assert {p: p.read_bytes() for p in canon.rglob("*.md")} == canon_before


# --- Прогон как командой -----------------------------------------------------------


def test_main_writes_the_artefact_and_creates_the_directory(
    canon: Path, tmp_path: Path, capsys
) -> None:
    out = tmp_path / "build" / "mirror" / "CONCEPT_mirror_EN.md"

    code = main(["--model", str(canon), "--out", str(out)])

    assert code == 0 and out.exists()
    printed = capsys.readouterr().out
    assert "source_hash sha256:" in printed


def test_main_check_returns_one_on_a_stale_mirror(canon: Path, tmp_path: Path) -> None:
    mirror = _mirror(canon, tmp_path / "mirror.md")
    (canon / "Finding.md").write_text("---\ncanon: true\norder: 60\n---\n\nchanged\n", encoding="utf-8")

    assert main(["--model", str(canon), "--check", str(mirror)]) == 1


def test_main_demands_out_or_check(canon: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--model", str(canon)])


# --- Ревью S5, дефект 3: порядок хеширования не зависит от платформы --------------

#: Эталон рецепта хеширования на фиксированном наборе (см. `_recipe_canon`).
#: Меняется только вместе с рецептом — тогда эта константа и должна упасть.
RECIPE_HASH = "sha256:19abe33444a5e060da9565dc6367822c7d52e32e7bd91d85f73aec9e37f22beb"


def _recipe_canon(root: Path) -> Path:
    """Крошечный синтетический канон с фиксированным содержимым.

    Эталон считаем **не** по настоящему `docs/model/`: тот правит Cowork, и
    константа падала бы при каждой правке канона, ничего не сообщая о рецепте.
    Имена подобраны так, что регистрозависимый и регистронезависимый порядок
    различаются: ASCII ставит `Alpha` < `Zeta` < `_overview` < `beta`, а
    casefold — `_overview` < `alpha` < `beta` < `zeta`.
    """
    model = root / "recipe"
    (model / "reference").mkdir(parents=True)
    for name, order in (("_overview.md", 10), ("Alpha.md", 20), ("Zeta.md", 30), ("beta.md", 40)):
        (model / name).write_text(
            f'---\ncanon: true\norder: {order}\nrev: "1.00"\n---\n\nbody of {name}\n',
            encoding="utf-8",
        )
    (model / "reference" / "ref.md").write_text(
        '---\ncanon: true\norder: 50\nrev: "1.00"\n---\n\nbody of ref\n', encoding="utf-8"
    )
    return model


def test_hashing_order_is_a_plain_string_sort(tmp_path: Path) -> None:
    """Порядок — по строке пути, а не по объекту `Path`.

    Сортировка `pathlib.Path` зависит от платформы: на Windows сравнение
    регистронезависимое, на Linux — нет. Хеш зависит от порядка, поэтому
    зеркало, проштампованное на рабочей машине, читалось бы как устаревшее при
    проверке из Linux-сессии — сторож ломался бы ровно в том сценарии, ради
    которого сделан.
    """
    from tools.build_mirror import canon_files

    model = _recipe_canon(tmp_path)
    order = [relative for relative, _path in canon_files(model, collect(model))]

    assert order == sorted(order)
    assert order == ["Alpha.md", "Zeta.md", "_overview.md", "beta.md", "reference/ref.md"]


def test_hashing_order_does_not_follow_the_assembly_order(tmp_path: Path) -> None:
    """Последовательность хеширования не зависит от поля `order`.

    Сам хеш при перенумерации меняется — и правильно: `order` управляет порядком
    секций в собранном зеркале, поэтому зеркало действительно устаревает. Здесь
    проверяется только то, что **последовательность файлов** остаётся прежней:
    иначе перенумерация тасовала бы хеш ещё и через порядок, и причину
    расхождения нельзя было бы объяснить по списку в выводе `--check`.
    """
    from tools.build_mirror import canon_files

    model = _recipe_canon(tmp_path)
    order_before = [relative for relative, _ in canon_files(model, collect(model))]

    victim = model / "Alpha.md"
    victim.write_text(
        victim.read_text(encoding="utf-8").replace("order: 20", "order: 99"), encoding="utf-8"
    )

    assert [relative for relative, _ in canon_files(model, collect(model))] == order_before


def test_hash_recipe_matches_the_recorded_constant(tmp_path: Path) -> None:
    """Эталон рецепта: любая будущая смена способа считать хеш видна сразу.

    Если этот тест упал, а `_recipe_canon` не менялся — изменился рецепт, и все
    зеркала в обращении нужно перештамповать.
    """
    model = _recipe_canon(tmp_path)

    assert canon_hash(model, collect(model)) == RECIPE_HASH


# --- QMS-019: сторож считает и тело, а не только паспорт ---------------------------
#
# Инцидент 2026-09-06: копия зеркала в волте десять дней жила раздутой в 3,95 раза
# (160 184 Б против генераторных 40 596 Б), и `--check` всё это время отвечал `OK` —
# шапка была цела, а кроме шапки сторож ничего не смотрел.


def _halves(mirror: Path) -> tuple[str, str]:
    """Шапка и тело — ровно там, где их делит `parse_front_matter`.

    Тело отдаётся `lstrip`-нутым по той же причине, по какой его так отдаёт парсер:
    сторож штампует именно эту строку. Режь тест иначе — он проверял бы не ту
    величину, которой сторож меряет.
    """
    text = mirror.read_text(encoding="utf-8")
    marker = "\n---\n"
    end = text.index(marker, len("---")) + len(marker)
    return text[:end], text[end:].lstrip("\n")


def _replace_body(mirror: Path, body: str) -> None:
    """Подменить тело, оставив шапку — и оба штампа в ней — нетронутыми."""
    header, _body = _halves(mirror)
    mirror.write_text(header + "\n" + body, encoding="utf-8")


def test_mirror_carries_a_body_hash(canon: Path, tmp_path: Path) -> None:
    mirror = _mirror(canon, tmp_path / "mirror.md")
    meta, _body = parse_front_matter(mirror.read_text(encoding="utf-8"))

    assert meta["body_hash"].startswith("sha256:")
    # Два штампа отвечают на разные вопросы и совпасть не могут.
    assert meta["body_hash"] != meta["source_hash"]


def test_the_stamp_matches_the_body_the_parser_returns(canon: Path, tmp_path: Path) -> None:
    """Симметрия генератора и проверки — бесшумная ловушка наряда 0023 §2.2.

    Парсер отдаёт тело без ведущих переводов строки. Посчитай генератор отпечаток по
    той строке, что держит он сам, — штампы разошлись бы на пустой строке, и сторож
    краснел бы на собственном свежем зеркале.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    meta, body = parse_front_matter(mirror.read_text(encoding="utf-8"))

    assert meta["body_hash"] == body_hash(body)
    # И разрез теста совпадает с разрезом парсера — иначе тесты ниже мнимые.
    assert _halves(mirror)[1] == body


def test_the_2026_09_06_incident_reads_corrupt(canon: Path, tmp_path: Path) -> None:
    """Воспроизведение инцидента: тело учетверено, шапка нетронута.

    Сегодняшний сторож отвечает здесь `OK`. После наряда — `CORRUPT`, и отдельно
    проверяется, что это **не** `OK` и **не** `STALE`: канон-то не двигался.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    header_before, body = _halves(mirror)
    _replace_body(mirror, body * 4)
    assert _halves(mirror)[0] == header_before

    code, output = _verdict(canon, mirror)

    assert code == 3
    assert "VERDICT: CORRUPT" in output
    assert "VERDICT: OK" not in output
    assert "VERDICT: STALE" not in output
    # Оба отпечатка и размер — размер опознал инцидент глазами раньше хеша.
    assert "body hash stamped:" in output
    assert "body hash actual :" in output
    assert f"body size actual : {len((body * 4).encode('utf-8'))} bytes" in output


def test_a_truncated_body_reads_corrupt(canon: Path, tmp_path: Path) -> None:
    """Порча бывает и в минус: недоехавший через мост файл — тоже испорченный."""
    mirror = _mirror(canon, tmp_path / "mirror.md")
    _header, body = _halves(mirror)
    _replace_body(mirror, body[: len(body) // 2])

    code, output = _verdict(canon, mirror)

    assert code == 3
    assert "VERDICT: CORRUPT" in output


def test_corruption_outranks_a_canon_that_moved_on(canon: Path, tmp_path: Path) -> None:
    """Порядок диагнозов: тело важнее свежести.

    Испорченное зеркало не докладывается как «устарело» — это разные диагнозы и
    разные действия: устарело → перегенерировать из канона; испорчено → перенести
    артефакт заново и выяснить, что его испортило.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    _header, body = _halves(mirror)
    _replace_body(mirror, body * 4)
    (canon / "Finding.md").write_text(
        '---\ncanon: true\norder: 60\n---\n\nchanged\n', encoding="utf-8"
    )

    code, output = _verdict(canon, mirror)

    assert code == 3
    assert "VERDICT: CORRUPT" in output
    assert "VERDICT: STALE" not in output


def test_a_crlf_copy_stays_ok(canon: Path, tmp_path: Path) -> None:
    """Перенос не ломает штамп.

    Зеркало проходит мост, git-checkout и Obsidian на двух машинах. Не нормализуй
    сторож переводы строки — он краснел бы на семантически целом файле, а это ровно
    тот отказ, ради которого затевался Q-09.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    copy = tmp_path / "vault-copy.md"
    copy.write_text(
        mirror.read_text(encoding="utf-8").replace("\n", "\r\n"), encoding="utf-8", newline=""
    )
    assert b"\r\n" in copy.read_bytes()

    code, output = _verdict(canon, copy)

    assert code == 0
    assert "VERDICT: OK" in output


def test_a_mirror_without_a_body_hash_reads_unverified(canon: Path, tmp_path: Path) -> None:
    """Зеркало прежней сборки: штампа тела нет, судить о целости нечем.

    Это не `OK` (не проверено) и не `CORRUPT` (порчи не видно) — отдельный вердикт,
    снимаемый перештамповкой. Действующие зеркала в обращении сейчас именно такие —
    объявлено в наряде 0023 §5.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    text = mirror.read_text(encoding="utf-8")
    victim = next(line for line in text.splitlines() if line.startswith("body_hash:"))
    mirror.write_text(text.replace(victim + "\n", "", 1), encoding="utf-8")

    code, output = _verdict(canon, mirror)

    assert code == 1
    assert "VERDICT: UNVERIFIED" in output
    assert "regenerating" in output


def test_a_mirror_truncated_inside_the_banner_reads_corrupt(canon: Path, tmp_path: Path) -> None:
    """Нечитаемая шапка — порча, а не старая сборка.

    `parse_front_matter` на несовпавшем выражении отдаёт пустые метаданные, и «шапку
    не разобрать» становилось неотличимо от «зеркала прежней сборки»: разрушенный
    файл советовал себя перештамповать вместо того, чтобы звать разбираться.
    Различает их то, что генератор шапку пишет **всегда**.
    """
    mirror = _mirror(canon, tmp_path / "mirror.md")
    full = mirror.read_text(encoding="utf-8")
    mirror.write_text(full[:300], encoding="utf-8")
    assert len(full) > 300

    code, output = _verdict(canon, mirror)

    assert code == 3
    assert "VERDICT: CORRUPT" in output
    assert "VERDICT: UNVERIFIED" not in output
    assert "no readable YAML front matter" in output


def test_printed_strings_are_ascii_only() -> None:
    """Вывод сторожа — ASCII, потому что консоль рабочей машины cp1255.

    Правило держится тестом, а не памятью: до QMS-019 в вердиктах стояло длинное
    тире, и на машине оно печаталось как `?`. Проверяются строковые константы внутри
    вызовов `print` — включая куски f-строк, где не-ASCII и завёлся.
    """
    source = (REPO_ROOT / "tools" / "build_mirror.py").read_text(encoding="utf-8")
    offenders = [
        (piece.lineno, piece.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
        for piece in ast.walk(node)
        if isinstance(piece, ast.Constant)
        and isinstance(piece.value, str)
        and not piece.value.isascii()
    ]

    assert offenders == []


def test_main_returns_three_on_a_corrupt_mirror(canon: Path, tmp_path: Path) -> None:
    """Код доходит до командной строки, а не теряется в `main`."""
    mirror = _mirror(canon, tmp_path / "mirror.md")
    _header, body = _halves(mirror)
    _replace_body(mirror, body * 4)

    assert main(["--model", str(canon), "--check", str(mirror)]) == 3


def test_argparse_keeps_code_two(canon: Path) -> None:
    """Код 2 занят argparse — `CORRUPT` не имеет права им прикидываться.

    Иначе испорченное зеркало было бы неотличимо от опечатки в командной строке.
    """
    with pytest.raises(SystemExit) as exc:
        main(["--model", str(canon)])

    assert exc.value.code == 2
