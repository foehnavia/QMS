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

    assert "canon files (12):" in output
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
