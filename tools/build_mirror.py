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

**The guard has two halves, and they answer different questions (QMS-019).**

- ``source_hash`` — over the **canon set**. Answers *which generation of the canon this
  mirror was made from*. Goes red when the canon moves on: verdict ``STALE``.
- ``body_hash`` — over the **mirror's own body**, everything below the YAML front matter.
  Answers *is this file still the file that was generated*. Goes red when the artefact is
  damaged in transit while its banner stays intact: verdict ``CORRUPT``. A banner that no
  longer parses is ``CORRUPT`` too, and for a reason worth stating: the generator has never
  written a mirror without front matter, so an unreadable banner is damage, never age.

The second half exists because the first one cannot see damage. On 2026-09-06 the vault
copy had lived bloated ~3.95x (160 184 B against a generated 40 596 B) for ten days while
``--check`` reported ``OK`` every time: the banner was untouched, and the banner was all
the guard looked at. The front matter is deliberately **outside** ``body_hash`` — the stamp
lives inside it, so covering it would be recursive; edits confined to the banner stay the
business of ``source_hash``.

Verdicts and exit codes: ``OK`` 0 · ``STALE`` 1 · ``UNVERIFIED`` 1 (mirror predates
``body_hash``) · ``CORRUPT`` 3. Code 2 is left alone — argparse uses it for a bad command
line, and a corrupt mirror must not be indistinguishable from a typo.

Usage:
    # regenerate into the repo, then hand the artefact over the bridge
    python tools/build_mirror.py --out build/mirror/CONCEPT_mirror_EN.md

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

#: Место под отпечаток тела на первом проходе сборки (см. ``build``).
BODY_HASH_PLACEHOLDER = f"{HASH_PREFIX}{'0' * 64}"


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


def _normalised(body):
    """CRLF -> LF. The single normalisation the stamp and the reported size share."""
    return body.replace("\r\n", "\n")


def body_hash(body):
    """sha256 over the mirror body - the file's own fingerprint (QMS-019).

    The body is everything below the YAML front matter. The banner itself stays out:
    the stamp lives in it, so hashing it would be recursive.

    Line endings are normalised **CRLF -> LF**, exactly as in ``canon_hash`` and for the
    same reason: the artefact crosses the bridge, a git checkout and Obsidian on two
    machines. Without normalisation the guard would go red on a semantically intact file,
    which is the one failure mode ("the guard is there, nobody believes it") that Q-09
    was opened to prevent.
    """
    digest = hashlib.sha256()
    digest.update(_normalised(body).encode("utf-8"))
    return f"{HASH_PREFIX}{digest.hexdigest()}"


def build(items, source_hash):
    """Assemble the mirror, stamped with both hashes.

    Two passes, and the reason is a silent trap. The stamp must match the body **as the
    parser hands it back** - ``parse_front_matter`` strips the leading newlines off it.
    Hashing the string the generator happens to hold instead would differ by exactly those
    blank lines, and the guard would go red on its own freshly built mirror. So: assemble
    with a placeholder, parse that draft, hash what came back, assemble again. Re-stamping
    touches the banner only, so the body of the second pass is the body that was hashed.
    """
    if not items:
        raise SystemExit("build_mirror: no canon files found")
    draft = _assemble(items, source_hash, BODY_HASH_PLACEHOLDER)
    _meta, body = parse_front_matter(draft)
    return _assemble(items, source_hash, body_hash(body))


def _assemble(items, source_hash, body_stamp):
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
        f'body_hash: "{body_stamp}"\n'
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


def check(model_dir, mirror_path, stream=None):
    """Report the mirror's state: OK / CORRUPT / STALE / UNVERIFIED.

    Two questions, asked in this order (QMS-019):

    1. **Is the file intact?** The banner has to parse at all, and ``body_hash`` has to
       match a fresh hash of the body.
    2. **Is it current?** ``source_hash`` against the canon as it is now.

    The order is the point. A damaged mirror must not be reported as merely "stale":
    those are different diagnoses calling for different actions - stale means regenerate
    from the canon, corrupt means carry the artefact over again and find out what damaged
    it. Answering the freshness question first would hide the worse of the two.

    Returns 0 (OK), 1 (STALE / UNVERIFIED) or 3 (CORRUPT). Never 2: argparse spends that
    on a bad command line. Writes nothing - the check is run against the vault copy too.

    Printed output stays **ASCII-only**: the work machine's console is cp1255 and a stray
    dash would come out mangled at best (INFRASTRUCTURE section 8).
    """
    # `sys.stdout` резолвится при вызове, а не в подписи (см. worktree_check).
    stream = sys.stdout if stream is None else stream
    items = collect(model_dir)
    if not items:
        print("build_mirror --check: no canon files found", file=stream)
        return 1

    expected = canon_hash(model_dir, items)
    if not mirror_path.exists():
        print(f"build_mirror --check: mirror not found: {mirror_path}", file=stream)
        return 1

    raw = mirror_path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(raw)
    stamped = meta.get("source_hash", "")
    stamped_body = meta.get("body_hash", "")

    print(f"canon files ({len(items)}), in hashing order:", file=stream)
    for relative, _path in canon_files(model_dir, items):
        print(f"  - {relative}", file=stream)
    print(f"canon  hash: {expected}", file=stream)
    print(f"mirror hash: {stamped or '(not stamped)'}", file=stream)

    # --- 1. Integrity of the file itself --------------------------------------------
    #
    # An unreadable banner is damage, not age. The generator has never written a mirror
    # without front matter, so a file whose banner does not parse cannot be an older
    # build — while ``parse_front_matter`` reports that case the same way it reports a
    # missing field: empty metadata. Left undistinguished, a mirror truncated mid-banner
    # came out as UNVERIFIED, telling the reader to re-stamp a wrecked file instead of
    # sending them to find out what wrecked it.
    if FM_RE.match(raw) is None:
        print(f"body size actual : {len(_normalised(raw).encode('utf-8'))} bytes", file=stream)
        print(
            "VERDICT: CORRUPT - mirror has no readable YAML front matter; the generator "
            "always writes one, so this file was damaged after generation. Carry the "
            "artefact over again and find out what damaged it.",
            file=stream,
        )
        return 3

    if not stamped_body:
        print(
            "VERDICT: UNVERIFIED - mirror carries no body_hash; it predates the "
            "integrity guard. Re-stamp it by regenerating.",
            file=stream,
        )
        return 1

    actual_body = body_hash(body)
    if stamped_body != actual_body:
        normalised = _normalised(body)
        print(f"body hash stamped: {stamped_body}", file=stream)
        print(f"body hash actual : {actual_body}", file=stream)
        # The size is printed alongside the hash because it is what identified the
        # 2026-09-06 incident by eye: the hash says "not it", the size says "four
        # times too big".
        print(
            f"body size actual : {len(normalised.encode('utf-8'))} bytes",
            file=stream,
        )
        print(
            "VERDICT: CORRUPT - mirror body does not match its own stamp; the file was "
            "damaged after generation. Carry the artefact over again and find out what "
            "damaged it. (Canon freshness not judged: fix the file first.)",
            file=stream,
        )
        return 3

    # --- 2. Freshness against the canon ---------------------------------------------
    if not stamped:
        print(
            "VERDICT: STALE - mirror carries no source_hash; regenerate it "
            "(it predates the content guard).",
            file=stream,
        )
        return 1
    if stamped != expected:
        print(
            "VERDICT: STALE - canon changed since this mirror was generated; "
            "regenerate and carry the artefact over.",
            file=stream,
        )
        return 1
    print("VERDICT: OK - mirror matches the canon, body matches its stamp.", file=stream)
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
    # Оба штампа печатаются: один опознаёт поколение канона, второй — сам файл.
    stamped, _body = parse_front_matter(args.out.read_text(encoding="utf-8"))
    print(f"build_mirror: body_hash   {stamped['body_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
