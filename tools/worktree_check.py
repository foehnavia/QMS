#!/usr/bin/env python3
"""worktree_check.py -- зафиксировано ли то, поверх чего начинается наряд.

Входной контроль (`CLAUDE.md` §3, шаг 0) отвечает на вопрос «лежит ли на диске всё,
что назвал раздел "Вход"». Он не отвечает на второй, не менее важный: **зафиксировано
ли то, что лежит**. Файл на месте и файл закоммичен -- разные утверждения, и сегодня
между ними прошла целая работа.

**Основание -- наряд `0023` (2026-09-06).** Он исполнялся поверх незакоммиченной чужой
правки `docs/model/_overview.md`. Стоило это двух вещей. Первая: тест регрессии Q-09
покраснел ещё **до** начала работ -- не потому, что сторож сломан, а потому, что канон
уехал под ним; полчаса ушло на доказательство, что дефект не мой. Вторая: канон-хеш
сдвинулся **посреди** наряда, и отчёт назвал значение, которое к моменту приёмки уже
не воспроизводилось. Ни то, ни другое не было видно, пока не начали разбираться.

Причина не в том, что у кого-то лишний доступ. `docs/` -- слой Cowork, писать туда его
право; наряды и канон приезжают именно этим мостом. Причина в том, что **движение
канона не видно исполнителю**: `git status` показывает изменённый файл, но не говорит,
что это меняет канон-хеш, против которого сверяется зеркало и половина тестов.

Инструмент отвечает ровно на это:

    python tools/worktree_check.py

    VERDICT: CANON MOVED -- код 1. В `docs/model/` есть незакоммиченные правки; канон,
        против которого пойдёт работа, -- не тот, что в HEAD. Печатаются оба хеша.
        Для наряда это стоп-условие: остановиться и спросить, чья правка и что с ней.
    VERDICT: OK -- код 0. Канон совпадает с HEAD. Прочие незакоммиченные пути (мой
        собственный слой, `build/`) печатаются справочно и вердикта не меняют: своя
        незавершённая работа посреди наряда -- норма, чужой движущийся канон -- нет.

Печать ASCII-only: консоль рабочей машины cp1255 (`INFRASTRUCTURE` §8). Держится
тестом `test_printed_strings_are_ascii_only`.
"""
import argparse
import io
import pathlib
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.build_mirror import canon_hash, collect  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Слой канона -- единственный, чьё движение является стоп-условием наряда.
CANON_PREFIX = "docs/model/"
#: Остальной слой Cowork: наряды, спеки, реестр решений.
COWORK_PREFIX = "docs/"
#: Полоса исполнителя -- её незавершённость посреди наряда нормальна.
MINE_PREFIXES = ("src/", "tools/", "tests/")

LAYER_TITLES = {
    "canon": "canon (docs/model/, Cowork's layer)",
    "docs": "docs (Cowork's layer: naryads, specs, decisions)",
    "code": "code (src/, tools/, tests/ -- executor's layer)",
    "other": "other",
}
LAYER_ORDER = ("canon", "docs", "code", "other")


def layer_of(path):
    """Слой, которому принадлежит путь. Канон отделён от прочего `docs/` намеренно."""
    if path.startswith(CANON_PREFIX):
        return "canon"
    if path.startswith(COWORK_PREFIX):
        return "docs"
    if any(path.startswith(prefix) for prefix in MINE_PREFIXES):
        return "code"
    return "other"


def parse_status(payload):
    """Пути из вывода ``git status --porcelain -z --untracked-files=all``.

    Разбирается ``-z``, а не обычный вывод: без него git цитирует и экранирует имена
    с не-ASCII символами, а в этом репозитории такие имена штатны (иврит в фикстурах).
    Переименование приходит двумя записями подряд -- вторая это старый путь; берётся
    новый, он и лежит на диске.
    """
    entries = [entry for entry in payload.split("\0") if entry]
    paths = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in ("R", "C"):
            index += 1  # следом идёт путь-источник -- он нас не интересует
        paths.append(path)
    return paths


def group(paths):
    """Пути по слоям, внутри слоя -- по алфавиту."""
    grouped = {}
    for path in paths:
        grouped.setdefault(layer_of(path), []).append(path)
    return {layer: sorted(items) for layer, items in grouped.items()}


def report(paths, head_hash, worktree_hash, stream=None):
    """Напечатать состояние и вернуть код: 0 -- можно работать, 1 -- канон уехал."""
    # `sys.stdout` резолвится при вызове, а не в подписи: значение по умолчанию
    # вычисляется один раз при импорте, и вывод уходил бы в поток, захваченный
    # тогда, а не в текущий.
    stream = sys.stdout if stream is None else stream
    grouped = group(paths)

    if paths:
        print(f"uncommitted paths ({len(paths)}), by layer:", file=stream)
        for layer in LAYER_ORDER:
            if layer not in grouped:
                continue
            print(f"  {LAYER_TITLES[layer]}:", file=stream)
            for path in grouped[layer]:
                print(f"    - {path}", file=stream)
    else:
        print("uncommitted paths: none", file=stream)

    print(f"canon hash HEAD     : {head_hash}", file=stream)
    print(f"canon hash worktree : {worktree_hash}", file=stream)

    if grouped.get("canon"):
        print(
            "VERDICT: CANON MOVED - docs/model/ carries uncommitted edits, so the canon "
            "a naryad would run against is not the committed one. Stop: find out whose "
            "edit it is and what happens to it before starting work.",
            file=stream,
        )
        return 1

    if head_hash != worktree_hash:
        # Сюда попасть можно только правкой канона в обход `git status` -- например
        # файлом, попавшим в `.gitignore`. Отдельный диагноз, потому что список путей
        # в этом случае ничего не объясняет.
        print(
            "VERDICT: CANON MOVED - the canon hash differs from HEAD while git reports "
            "no uncommitted canon files. Something edits docs/model/ outside git's view.",
            file=stream,
        )
        return 1

    print("VERDICT: OK - canon matches HEAD; nothing is moving under the work.", file=stream)
    return 0


def _git(args):
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )


def head_canon_hash():
    """Канон-хеш по состоянию HEAD -- через временную распаковку, без переключения веток.

    Рабочее дерево не трогается принципиально: инструмент зовут посреди работы, и
    проверка, меняющая ветку под исполнителем, была бы хуже дефекта, который она ищет.
    """
    archive = _git(["archive", "HEAD", "docs/model"]).stdout
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            # `filter="data"` -- не для безопасности (архив свой), а чтобы поведение не
            # сменилось молча под Python 3.14, где фильтр становится обязательным.
            bundle.extractall(tmp, filter="data")
        model = pathlib.Path(tmp) / "docs" / "model"
        return canon_hash(model, collect(model))


def main(argv=None):
    argparse.ArgumentParser(
        description="Report whether the canon a naryad would run against is committed."
    ).parse_args(argv)

    status = _git(["status", "--porcelain", "-z", "--untracked-files=all"]).stdout
    paths = parse_status(status.decode("utf-8"))

    model = REPO_ROOT / "docs" / "model"
    return report(paths, head_canon_hash(), canon_hash(model, collect(model)))


if __name__ == "__main__":
    sys.exit(main())
