---
part_of: MIS-QMS/docs/model
entity: Import-Workflow
order: 90
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Import workflow — data source and ingestion (ETL)

> How raw Hebrew deviation records become deviations + findings. Entry point:
> `_overview.md` (process Steps 2–3).

> **FROZEN (2026-09-08, QMS-027).** No access to the live journal will be granted: the
> security review ruled that Teams is not to be touched. The only workaround — saving the
> file to disk by hand before every run — costs more than it saves at 3–10 deviations a day,
> so **manual entry is the sole route into the database**, not a stopgap. Nothing below is
> withdrawn: the contract is sound and was measured against the real corpus
> (`docs/analysis/0033-*`, 2025 archive, 1116 rows) — it simply has no route to its source.
> Unfreeze only if access appears; then re-measure drift, not the whole array.
> Registry: `decisions.md` 129–131.

## Source

- Excel in Teams, **Hebrew / RTL**, no direct system access (only via the responsible
  person or a copy). **Reachable in neither form — see the freeze note above.**
- The `מידה` (dimension) column is **vestigial and left empty**; the anchor
  (dimension, magnitude, direction) is in **free Hebrew text** in the description.
- Detection on the floor: the operator checks a part roughly every 2 hours; on a
  deviation, all parts since the last good check are separated; after the WO a
  sampling check is done, and a defect in the sample sends the whole WO to MRB.
- **Sign convention: `−` below the minimum, `+` above the maximum.**

## ETL (stage 1)

Auto-parse by regular expressions → correction → **operator approval** (moderation).

- Backbone pattern:
  `מידה {N} חורגת {מעל המקסימום=+ | מתחת למינימום=−} {עד|ב} {value}`
- Pin pattern: `מידה {N} פין {v} נכנס/לא נכנס`.
- **Direction comes from the max/min word (priority);** the number's sign is a
  secondary check / conflict flag.
- Much noise: typos (`מינמום`/`נינימום`), sign attached or missing, duplicated words.
- `X מתוך Y` (a sample) → `quantity = 9999`; a point sub-index is a bare number
  (`12 1`) → `dimension_point`.
- `מדיד` / `GO` are qualitative (no magnitude); a pin is measurable but, in stage 1,
  goes to `comment`.
- One Excel row → one Deviation with an array of findings; stage 1 is manual, one row
  at a time.

## Determinism / privacy

Parsing is **deterministic (regex), no LLM at runtime**. Individual values (item number
`מק"ט`, WO number `מנה`/`פק"ע`, a single Hebrew verdict) are **not sensitive** on their own
and are stored normally (working DB, tests, examples). Only a **complete real
document/protocol tied to the company** (an assembled `אישור חריגה`, a full protocol) is kept
out of vault and git; the working DB stays autonomous (`docs/_INDEX.md` -> "Не в волте / git").

## Deferred (stage 2+)

See `staging.md`: measurement types + precision grades; computing `value` from pins;
auto-load dedup; discovery context (`במהלך המדגם` / `מיון 100%` / planned) — not
handled; `הערה יצרן` (manufacturer note) — not handled.

## Related

`Deviation.md` · `Finding.md` · `staging.md`
