"""Сторож зеркала по содержимому — Q-09 (критерий 13 наряда 0005).

Прежний сторож сверял `source_version` зеркала с `rev` канона, а `rev` поднимался
руками: пропустили подъём — сторож зелёный, зеркало устарело. Смысл затеи в том,
чтобы проверка перестала зависеть от ручного поля, поэтому главный тест здесь —
**красный вердикт после правки канона без подъёма `rev`**.

Правки канона делаются во временной копии: `docs/model/` — слой Cowork.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from tools.build_mirror import build, canon_hash, check, collect, main, parse_front_matter

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
    assert 'rev: "1.00"' in text
    # Правим тело, поле `rev` намеренно не трогаем — прежний сторож это пропускал.
    victim.write_text(text + "\nA sentence added after the mirror was built.\n", encoding="utf-8")

    code, output = _verdict(canon, mirror)

    assert code == 1
    assert "VERDICT: STALE" in output
    assert 'rev: "1.00"' in victim.read_text(encoding="utf-8")


def test_check_explains_which_files_it_hashed(canon: Path, tmp_path: Path) -> None:
    """Расхождение надо объяснять, а не только констатировать."""
    mirror = _mirror(canon, tmp_path / "mirror.md")

    _code, output = _verdict(canon, mirror)

    assert "canon files (12), in hashing order:" in output
    assert "- Search.md" in output
    assert "- reference/reference-data.md" in output


def test_check_calls_a_mirror_without_a_hash_stale(canon: Path, tmp_path: Path) -> None:
    """Зеркало, собранное до сторожа, штампа не несёт — это тоже «устарело»."""
    mirror = _mirror(canon, tmp_path / "mirror.md")
    text = mirror.read_text(encoding="utf-8")
    mirror.write_text(
        "\n".join(line for line in text.splitlines() if not line.startswith("source_hash:")),
        encoding="utf-8",
    )

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
    out = tmp_path / "build" / "mirror" / "CONCEPT_full_rev1.00_EN.md"

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
