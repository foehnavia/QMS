---
part_of: MIS-QMS/docs/model
entity: Inspection
order: 70
canon: true
rev: "1.01"
updated: 2026-09-07
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

## What an inspection concludes — rev 1.01

> Revised 2026-09-07 (QMS-018). Until rev 1.00 `decisionInsp` was **binary and
> mandatory**, which forced a polar answer out of every study. Most studies do not
> have one: "the useful clearance in the assembled state drops by 20 %" is a
> measurement, not a verdict. The binary field made this file contradict itself — the
> section below states that an inspection *accumulates information and does not
> dictate the decision*, while the field demanded a decision-shaped answer.

- **`decisionInsp` is three-valued and optional.** Values: `approval possible` ·
  `approval not possible` · `inconclusive`. **Empty means "not assessed yet"** and is
  a legitimate state: the protocol is attached first, the reading of it comes later.
- **`inconclusive` and empty are different states.** `inconclusive` — the study was
  read and settles nothing about approvability; empty — nobody has read it yet.
- The wording is deliberate: the field says what the study **permits**, not what was
  decided. Some studies do land on an unambiguous answer, and when they do it is worth
  seeing at a glance — that is what the three positions are for.
- **`Conclusion` — short free text saying what the study found**, optional, up to 500
  characters (three or four sentences). It exists so a finding can be read in a list
  without opening the protocol file. It does **not** replace the protocol and carries
  no fixed structure: forcing "magnitude + unit" would exclude statements such as
  "−20 % of the useful clearance".

## Decision independence

- **`decisionInsp` is independent of `decisionDev`** (`Deviation.md`); it accumulates
  information and **does not dictate** the decision. `approval not possible` on an
  inspection alongside `approved — use as is` on the deviation is a valid combination:
  the study supplies evidence, the human decides.
- Consequently a deviation row is **never coloured or ranked by an inspection's
  position**, and no screen puts the two on one scale.

## Fields (minimum)

- `Inspection ID`
- `Type` (from an admin dictionary — initially `Solidworks assembly`,
  `Implantation torque test`; for growth: `Drilling force test`, functional checks;
  see `reference/reference-data.md`)
- link to the finding (`Finding.md`)
- `Inspection Result` (`decisionInsp` = `approval possible` / `approval not possible` /
  `inconclusive`; **optional** — empty means not assessed yet)
- `Conclusion` — short free text, **optional**, ≤ 500 characters
- `Protocol` — **a link to a file**, required. Protocols are filed exclusively as
  documents; the field stores the path as the operator supplied it. The file is never
  copied into the database (the same convention as deviation attachments), and its
  existence is **not** verified on entry — a protocol may sit on a share unreachable at
  the moment of typing, and a false refusal there costs more than a stale link.
  Required, because the existence of a written reusable analysis is the criterion by
  which the row is created at all.
- `Item` is derived from the deviation/finding, not stored separately.

## Where the "science" lives

**All the "science" lives in the protocol, not in fields:** method, statistics
(t-test, p), instrument + calibration, sample composition, worst-case modifications,
the "second part" (assembly partner / measurement medium), with/without-deviation
pictures. `Conclusion` is a reading aid pointing into that file, never a summary that
could stand in for it.

## Examples

- `Implantation torque test` — implant insertion torque under a drill deviation
  (dim 19, +).
- `Solidworks assembly` — worst-case assembly gap (CS-TB015A dim 32 −, partner
  C1-08375A); conclusion "clearance in the assembled state −20 %", position
  `approval possible`.

## Related

`Deviation.md` · `Finding.md` · `reference/reference-data.md` · `reference/output-document.md`
