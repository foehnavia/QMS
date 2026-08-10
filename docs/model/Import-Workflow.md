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

## Source

- Excel in Teams, **Hebrew / RTL**, no direct system access (only via the responsible
  person or a copy).
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

Parsing is **deterministic (regex), no LLM at runtime**. Real deviation data (WO,
item numbers, Hebrew verdicts) is **autonomous** — never in vault or git
(`docs/_INDEX.md` → "Not in vault / git"; RULES §5).

## Deferred (stage 2+)

See `staging.md`: measurement types + precision grades; computing `value` from pins;
auto-load dedup; discovery context (`במהלך המדגם` / `מיון 100%` / planned) — not
handled; `הערה יצרן` (manufacturer note) — not handled.

## Related

`Deviation.md` · `Finding.md` · `staging.md`
