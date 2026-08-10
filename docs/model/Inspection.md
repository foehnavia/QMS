---
part_of: MIS-QMS/docs/model
entity: Inspection
order: 70
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Inspection (research)

> A serious, documented, reusable study of how a deviation affects the product
> (e.g. implantation-torque test, SolidWorks assembly check). Distinguished from
> more primitive checks (visual, dimensional, tolerance review) by **depth**. A
> **separate table**. Entry point: `_overview.md`.
>
> Terminology (rev 1.00): renamed **Inspection → "research / исследование"** to
> separate it from primitive checks. The table/field name `Inspection` is retained.

## When a row is created

- **Only** when a serious, documented, reusable study of the deviation's impact
  exists (a written summary).
- The routine primary check (`Tolerances review` — a drawing check, including a quick
  visual look at part fit in SolidWorks) yields a **finding** and creates **no**
  inspection row.
- The criterion is the existence of a **reusable written analysis**, not the tool.

## Linkage

- **Linked to a finding** and, explicitly, **to the (Item, dimension) pair** — because
  search for deviations and inspections runs on that pair. `0..N` per deviation.
- This gives the mirror search "all inspections by (Item, dimension)" alongside "all
  deviations by (Item, dimension)" (`Search.md`, `DeviationCard.md`).
- Different dimensions of one deviation may carry different inspections.

## Decision independence

- **`decisionInsp`** is independent of `decisionDev` (`Deviation.md`); it accumulates
  information and **does not dictate** the decision.

## Fields (minimum)

- `Inspection ID`
- `Type` (from an admin dictionary — initially `Solidworks assembly`,
  `Implantation torque test`; for growth: `Drilling force test`, functional checks;
  see `reference/reference-data.md`)
- link to the finding (`Finding.md`)
- `Inspection Result` (`decisionInsp` = `Deviation approved` / `Deviation not
  approved`)
- `Protocol` (the attached summary document)
- `Item` is derived from the deviation/finding, not stored separately.

## Where the "science" lives

**All the "science" lives in the protocol, not in fields:** method, statistics
(t-test, p), instrument + calibration, sample composition, worst-case modifications,
the "second part" (assembly partner / measurement medium), with/without-deviation
pictures.

## Examples

- `Implantation torque test` — implant insertion torque under a drill deviation
  (dim 19, +).
- `Solidworks assembly` — worst-case assembly gap (CS-TB015A dim 32 −, partner
  C1-08375A), verdict approved.

## Related

`Deviation.md` · `Finding.md` · `reference/reference-data.md` · `reference/output-document.md`
