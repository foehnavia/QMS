#!/usr/bin/env python3
"""
build_mirror.py — regenerate the flat vault mirror from the sliced canon.

The canonical MIS-QMS model is the set of sliced files in ``docs/model/``
(``_overview.md`` + per-entity files + ``reference/``). Not every session has
repository access (e.g. a phone session with the Obsidian vault connected but not
the repo), so the vault keeps ONE read-only flattened copy for offline reading.

This script produces that mirror deterministically: it collects every model file
carrying ``canon: true`` in its front matter, orders them by the ``order`` field,
strips per-file front matter, and concatenates the bodies under a mirror banner
whose ``source_version`` equals the canon rev. Deterministic (no wall clock) so a
re-run over an unchanged canon yields a byte-identical file — a mismatch is drift.

**Staleness is detected by content, not by a hand-maintained field (Q-09).** The
banner also carries ``source_hash`` — a sha256 over the canon files that went into
the mirror. ``source_version`` is still written, for a human to read, but the guard
no longer depends on someone remembering to bump ``rev``: edit any canon file and
``--check`` goes red on the next run.

Usage:
    # regenerate into the repo, then hand the artefact over the bridge
    python tools/build_mirror.py --out build/mirror/CONCEPT_full_rev1.00_EN.md

    # verify an existing mirror against the current canon (no writes)
    python tools/build_mirror.py --check <path-to-mirror>

Rule: run this ONLY from a repo-connected session/machine, at the close of any
session that changed docs/model/. Sessions without repo access must never write
the mirror (they cannot see the canon). The generator writes **into the repo**;
carrying the file into the vault is Cowork's step — Claude Code never writes to
the vault (INFRA-013). See docs/_INDEX.md → "Mirror & sync".
"""
import argparse
import hashlib
import pathlib
import re
import sys

FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)

HASH_PREFIX = "sha256:"


def parse_front_matter(text):
    """Return (meta: dict[str,str], body: str). Minimal YAML: flat key: value."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, m.group(2).lstrip("\n")


def collect(model_dir):
    files = list(model_dir.glob("*.md")) + list((model_dir / "reference").glob("*.md"))
    items = []
    for f in files:
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        if str(meta.get("canon", "")).lower() != "true":
            continue
        try:
            order = int(meta.get("order", "999999"))
        except ValueError:
            order = 999999
        items.append((order, f.name, meta, body, f))
    items.sort(key=lambda t: (t[0], t[1]))
    return items


def canon_files(model_dir, items):
    """The canon set in **hashing order**: (relative posix path, path) pairs.

    Ordered by the relative path **as a string**, deliberately not by sorting
    ``pathlib.Path`` objects: path comparison is platform-dependent — case-insensitive
    on Windows, case-sensitive elsewhere — so sorting the objects puts ``_overview.md``
    first on Windows and after ``Search.md`` on Linux over the very same files. The hash
    depends on order, so a mirror stamped on the work machine would read STALE when
    checked from a Linux session: the guard would break in exactly the scenario it
    exists for.

    The ``order`` field is not used here: it drives assembly, not identity, so the
    hashing sequence stays put when someone renumbers the canon. The hash itself still
    changes then — and rightly so, because the assembled mirror does. A rename changes
    both, since the relative path is hashed alongside the body.
    """
    pairs = [(item[4].relative_to(model_dir).as_posix(), item[4]) for item in items]
    return sorted(pairs, key=lambda pair: pair[0])


def canon_hash(model_dir, items):
    """sha256 over the canon set — the mirror's staleness detector (Q-09).

    Line endings are normalised **CRLF -> LF** before hashing: a checkout on Windows
    would otherwise produce a different hash for byte-identical content and the guard
    would cry wolf on every clone. The relative path is hashed alongside the body, so
    renaming a file is a change even when its text is untouched.
    """
    digest = hashlib.sha256()
    for relative, path in canon_files(model_dir, items):
        body = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body.encode("utf-8"))
        digest.update(b"\0")
    return f"{HASH_PREFIX}{digest.hexdigest()}"


def build(items, source_hash):
    if not items:
        raise SystemExit("build_mirror: no canon files found")
    rev = items[0][2].get("rev", "?")            # _overview (order 10) carries the rev
    updated = items[0][2].get("updated", "")
    header = (
        "---\n"
        "type: note\n"
        "domain: [mis-qms]\n"
        "status: open\n"
        "role: concept-mirror\n"
        "read_at_start: no\n"
        f'version: "{rev}"\n'
        f"updated: {updated}\n"
        f'source_version: "{rev}"\n'
        f'source_hash: "{source_hash}"\n'
        "mirror_of: docs/model/\n"
        "generated_by: tools/build_mirror.py\n"
        "language: en\n"
        "tags: [project/mis-qms, topic/entity-model]\n"
        "aliases: [MIS-QMS Full Concept (mirror), CONCEPT_full EN mirror]\n"
        "---\n\n"
        f"# MIS-QMS — Production Deviations Database · Full Concept (rev {rev}) — VAULT MIRROR\n\n"
        "> [!warning] Generated mirror — do not edit here.\n"
        "> This is a **read-only flattened copy** of the sliced canon in the repository\n"
        "> `github.com/foehnavia/QMS` → `docs/model/`. It exists so that sessions without\n"
        "> repo access (e.g. a phone session with only the vault connected) can read the\n"
        f"> whole concept offline. **Canon is the repo; on any discrepancy the repo prevails.**\n"
        f"> Regenerate with `tools/build_mirror.py` from a repo-connected session whenever\n"
        f"> `docs/model/` changes. Staleness is checked by `source_hash` over the canon\n"
        f"> files — `python tools/build_mirror.py --check <this file>`; `source_version`\n"
        f"> (**{rev}**) is for humans.\n\n"
        "---\n"
    )
    parts = [header]
    for _order, name, _meta, body, _path in items:
        parts.append(f"\n\n<!-- from docs/model/{name} -->\n\n{body.rstrip()}\n")
    return "".join(parts).rstrip() + "\n"


def check(model_dir, mirror_path, stream=sys.stdout):
    """Compare a mirror's stamped hash with the canon as it is now.

    Returns 0 when they match, 1 otherwise. Writes nothing: the check must be safe
    to run from anywhere, including against a mirror already sitting in the vault.
    The file list is printed alongside the verdict so a mismatch can be explained,
    not merely announced.
    """
    items = collect(model_dir)
    if not items:
        print("build_mirror --check: no canon files found", file=stream)
        return 1

    expected = canon_hash(model_dir, items)
    if not mirror_path.exists():
        print(f"build_mirror --check: mirror not found: {mirror_path}", file=stream)
        return 1

    meta, _body = parse_front_matter(mirror_path.read_text(encoding="utf-8"))
    stamped = meta.get("source_hash", "")

    print(f"canon files ({len(items)}), in hashing order:", file=stream)
    for relative, _path in canon_files(model_dir, items):
        print(f"  - {relative}", file=stream)
    print(f"canon  hash: {expected}", file=stream)
    print(f"mirror hash: {stamped or '(not stamped)'}", file=stream)

    if not stamped:
        print(
            "VERDICT: STALE — mirror carries no source_hash; regenerate it "
            "(it predates the content guard).",
            file=stream,
        )
        return 1
    if stamped != expected:
        print(
            "VERDICT: STALE — canon changed since this mirror was generated; "
            "regenerate and carry the artefact over.",
            file=stream,
        )
        return 1
    print("VERDICT: OK — mirror matches the canon.", file=stream)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="docs/model", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, help="where to write the mirror artefact")
    ap.add_argument(
        "--check",
        type=pathlib.Path,
        metavar="MIRROR",
        help="verify an existing mirror against the canon; writes nothing",
    )
    args = ap.parse_args(argv)

    if args.check is not None:
        return check(args.model, args.check)
    if args.out is None:
        ap.error("one of --out or --check is required")

    items = collect(args.model)
    source_hash = canon_hash(args.model, items)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(items, source_hash), encoding="utf-8")
    print(f"build_mirror: wrote {args.out} from {len(items)} canon files "
          f"(rev {items[0][2].get('rev','?')})")
    print(f"build_mirror: source_hash {source_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
