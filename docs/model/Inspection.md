---
part_of: MIS-QMS/docs/model
entity: Inspection
order: 70
canon: true
rev: "1.03"
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

## What an inspection concludes — rev 1.03

> Revised twice on 2026-09-07. **rev 1.01:** `decisionInsp` was binary and mandatory, which
> forced a polar answer out of studies that do not have one — it became three-valued and
> optional. **rev 1.03 (QMS-025): the field is removed altogether.** The three positions
> were a workaround for a missing home: the finding had no state of its own, so "the quick
> answer" had nowhere to live but the inspection. Once the finding gained its `outcome`
> (`Finding.md` rev 1.01), the field on the inspection became a second verdict beside the
> real one — two near-identical words meaning different things, side by side on one screen.

- **An inspection carries no verdict.** It has a type, a written conclusion and a protocol.
  That is all, and that is the point.
- **`Conclusion` — short free text saying what the study found**, up to 500 characters
  (three or four sentences), so a finding can be read in a list without opening the file.
  Optional when a protocol is attached; **mandatory when `No protocol` is set**.
- **Several inspections per finding stay possible and stay unranked.** A leak test plus a
  functional check on the same dimension is rare but real; each states its own findings in
  its own words, and the engineer reads them and decides — on the finding.

## Decision independence — now structural

- **An inspection has no verdict field**, so it cannot dictate anything. What used to be a
  rule enforced by care (`decisionInsp` is independent of `decisionDev`) is enforced by the
  absence of the field itself (rev 1.03, QMS-025).
- The judgement on the dimension lives on the finding (`Finding.md` rev 1.01); the judgement
  on the batch lives on the deviation (`Deviation.md`). An inspection informs both and is
  neither.
- Consequently no screen ranks or colours a row by anything an inspection says.

## Fields (minimum)

- `Inspection ID`
- `Type` (from an admin dictionary — the starting set is `Solidworks assembly`,
  `Implantation torque test`, `Tolerances review`; for growth: `Drilling force test`,
  functional checks; see `reference/reference-data.md`)
- link to the finding (`Finding.md`)
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
  C1-08375A); conclusion "clearance in the assembled state −20 %". The judgement that
  follows from it is recorded on the finding, not here.
- `Tolerances review`, **`No protocol` set** — outer diameter 10.0 against an inner one of
  9.9: the parts cannot mate, and the drawing alone settles it. No document exists;
  conclusion "OD 10.0 vs ID 9.9 — no mating clearance, geometry excludes assembly"; the
  finding is then set to `not permitted`.

## Related

`Deviation.md` · `Finding.md` · `reference/reference-data.md` · `reference/output-document.md`
