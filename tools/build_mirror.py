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

Usage:
    python tools/build_mirror.py \
        --model docs/model \
        --out   /path/to/Vault_01/50_MIS-QMS/CONCEPT_full_rev1.00_EN.md

Rule: run this ONLY from a repo-connected session/machine, at the close of any
session that changed docs/model/. Sessions without repo access must never write
the mirror (they cannot see the canon). See docs/_INDEX.md → "Mirror & sync".
"""
import argparse
import pathlib
import re
import sys

FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


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
        items.append((order, f.name, meta, body))
    items.sort(key=lambda t: (t[0], t[1]))
    return items


def build(items):
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
        f"> `docs/model/` changes. `source_version` here (**{rev}**) must equal the canon rev.\n\n"
        "---\n"
    )
    parts = [header]
    for _order, name, _meta, body in items:
        parts.append(f"\n\n<!-- from docs/model/{name} -->\n\n{body.rstrip()}\n")
    return "".join(parts).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="docs/model", type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args(argv)
    items = collect(args.model)
    args.out.write_text(build(items), encoding="utf-8")
    print(f"build_mirror: wrote {args.out} from {len(items)} canon files "
          f"(rev {items[0][2].get('rev','?')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
