---
part_of: MIS-QMS/docs/model
entity: Finding
order: 60
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Finding

> A deviation on one dimension inside a deviation. Addressable for search;
> **carries no decision**. Entry point: `_overview.md`.

## Definition

A finding sits inside a `Deviation.md` and pins the deviation to one specific
dimension (`Characteristic.md`). A deviation can carry several findings
(`1..N`). A finding is addressable for search but has no decision of its own — the
decision lives on the deviation.

## Fields

- `dimension_main` — the dimension the finding is about; **used for canon binding**
  (via the characteristic's mapping, `CharacteristicGroup.md`).
- `dimension_point` — optional point index; **not used in search**.
- `direction` — `±` (sign convention: `−` below minimum, `+` above maximum;
  `Import-Workflow.md`).
- `value` — optional magnitude.
- `comment` — raw text for qualitative / unrecognized cases (e.g. `GO`/`מדיד`,
  pins in stage 1).
- **Affected zone** — reference label for deeper search (`reference/reference-data.md`).
- **Deviation type** — reference label for deeper search (`reference/reference-data.md`).

## Binding

A finding **references a characteristic** by FK on the row `(item, local#)`; it does
not store a bare dimension number. The canon (g-position) is reached through that
characteristic's mapping. Measurement fields sit on the finding; integrity remains at
the deviation level.

## Related

`Deviation.md` · `Characteristic.md` · `CharacteristicGroup.md` · `Inspection.md` · `Search.md`
