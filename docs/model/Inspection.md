---
part_of: MIS-QMS/docs/model
entity: Inspection
order: 70
canon: true
rev: "1.02"
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

> Revised 2026-09-07 (QMS-018, hand run). Until rev 1.01 the criterion was the existence of
> an attached **file**, and `Tolerances review` was excluded from inspections outright. The
> hand run showed the exclusion too wide: some deviations are settled by the drawing alone
> — an outer diameter of 10.0 against an inner one of 9.9 does not fit, and no study will
> change that — and that verdict is a reusable precedent worth recording, while no document
> exists to attach.

- **The criterion is a reusable conclusion, not a file.** A row is created when the
  engineer has a conclusion worth reading again on the next identical deviation.
- **A row must carry at least one of the two: a protocol file, or a written conclusion.**
  A row with neither says nothing to the precedent search and must not exist — that is the
  invariant this section is about, and it is enforced by the schema, not by discipline.
- **`No protocol` is a deliberate, declared state**, marked by its own flag on the row and
  never inferred from an empty field. Unmarked by default: the ordinary inspection is a
  documented one, and waiving the document is a decision the engineer takes on purpose.
  With the flag set, the **conclusion becomes mandatory** — it is then the whole content of
  the record.
- **The routine drawing check does not oblige a row.** `Tolerances review` creates one only
  when its conclusion is worth keeping as a precedent; looking at a drawing and moving on
  records nothing. What changed in rev 1.02 is that such a row is now *possible*, not that
  it is *required*.
- The depth distinction stands: a serious, documented, reusable study is what the table is
  for, and a `No protocol` row is the narrow exception for a verdict that needs no document,
  not a licence to log every glance.

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
- `Conclusion` — short free text, ≤ 500 characters. **Optional when a protocol is
  attached** (it can be written after the file has been read); **mandatory when
  `No protocol` is set** — it is then the entire content of the record.
- `No protocol` — a flag, **unset by default**. Set means: this verdict needs no document,
  and the conclusion carries it. Never inferred from an empty protocol field: an empty
  field is an unfinished record, a set flag is a decision.
- `Protocol` — **a link to a file**, required **unless `No protocol` is set**. Protocols
  are filed exclusively as documents; the field stores the path as the operator supplied
  it. The file is never copied into the database (the same convention as deviation
  attachments), and its existence is **not** verified on entry — a protocol may sit on a
  share unreachable at the moment of typing, and a false refusal there costs more than a
  stale link.
- **Invariant across the three fields above:** every row carries a protocol file **or** a
  conclusion. Enforced in the schema by a constraint, not by the form — a record that says
  nothing is invisible to the precedent search, which is what the table exists for.
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
- `Tolerances review`, **`No protocol` set** — outer diameter 10.0 against an inner one of
  9.9: the parts cannot mate, and the drawing alone settles it. No document exists;
  conclusion "OD 10.0 vs ID 9.9 — no mating clearance, geometry excludes assembly",
  position `approval not possible`.

## Related

`Deviation.md` · `Finding.md` · `reference/reference-data.md` · `reference/output-document.md`
