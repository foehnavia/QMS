---
part_of: MIS-QMS/docs/model
entity: _overview
order: 10
canon: true
rev: "1.00"
updated: 2026-08-10
title: MIS-QMS — Production Deviations Database · Concept Overview
---

# MIS-QMS — Production Deviations Database · Concept (rev 1.00)

> **Canonical entry point.** This file plus the per-entity files in this
> directory (`docs/model/`) are the single source of truth for the MIS-QMS model.
> The source of truth is the **repository** `github.com/foehnavia/QMS`.
> The flattened copy in the Obsidian vault (`50_MIS-QMS/CONCEPT_full_rev1.00_EN.md`)
> is a **generated read-only mirror** — see `tools/build_mirror.py` and
> `docs/_INDEX.md` (Mirror & sync). On any discrepancy, **the repository prevails.**
>
> **History.** Supersedes the single-document `CONCEPT_full_rev1.00_EN.md` (sliced
> into this directory on 2026-08-10, task QMS-002 / Wave 0b) and the earlier
> `_CONCEPT.md` A–F snapshot of sessions 01–03 (retained as archived).
>
> **Status:** concept finalized (concept sessions 01–06 + revision A). Implementation
> and stack are not yet started; the design/build stage begins next.

---

## 0. How to read this model

This is the final concept of the deviations database — both **what the system is
made of** (entities, fields, reference data) and **how work flows through it**
(process, step by step, with the branch points at each step). It is written to be
usable as a development specification and, at the same time, understandable by a
reader who did not take part in the concept sessions.

Two guiding principles run through everything:

- **The system is the "head", not the "hands".** It stores, links, searches and
  shows; the engineer decides. The database's job is to give an exhaustive picture,
  not to make the call.
- **The part (Item) is the center.** Almost every grouping, sorting and query runs
  "from the part". Around it: its **dimensions** (characteristics), the **deviations**
  recorded against those dimensions, and a **canonical layer** that lets the same
  physical feature be compared across different parts.

**Where each thing lives (this directory):**

| File | Entity / topic |
|---|---|
| `_overview.md` (this file) | glossary, actors, save flow, end-to-end process, cross-cutting principles |
| `Item.md` | Item — the manufactured part; part classifiers |
| `Characteristic.md` | Characteristic (dimension); part states |
| `CharacteristicGroup.md` | CG / g-position (canonical layer) **and Mapping** |
| `Deviation.md` | Deviation; outcomes (`decisionDev`); quantity levels; WO / NCR |
| `Finding.md` | Finding; zone & deviation-type labels |
| `Inspection.md` | Inspection (research) |
| `DeviationCard.md` | Deviation card — the key deliverable |
| `Import-Workflow.md` | source data & ingestion (ETL) |
| `Search.md` | search by levels |
| `reference/reference-data.md` | reference tables (types, zone, deviation-type, inspection-type) |
| `reference/output-document.md` | `אישור חריגה` — form DS-QC.2-2 & field map |
| `staging.md` (parent dir) | rollout stages 1 → 1.5 → beyond |
| `decisions.md` (parent dir) | architectural decision register (incl. R1/R2/R3) |

---

## 1. Glossary — the objects the process operates on

Brief descriptions; full field-level detail is in each entity's own file.

| Object | Plain description | Detail |
|---|---|---|
| **Item** | A manufactured product with its own catalog number (item number). The central object. | `Item.md` |
| **Characteristic (dimension)** | One controlled dimension of a specific part. Exists only together with its part; matching numbers across parts are coincidental. | `Characteristic.md` |
| **g-position (canonical layer)** | A reference "dimension slot" shared by a group of similar parts (a CharacteristicGroup). Lets deviations be compared across parts by the same constructive location. | `CharacteristicGroup.md` |
| **Mapping** | A manual correspondence "this dimension of this part = this canonical g-position". | `CharacteristicGroup.md` |
| **Deviation** | A recorded non-conformance found on a batch of parts. A self-standing record with its own decision, quantity, date. | `Deviation.md` |
| **Finding** | A deviation on one specific dimension inside the event. Addressable for search; carries no decision. | `Finding.md` |
| **Deviation card** | The working screen of a single deviation; hosts the key deliverable (automatic prior-deviation overview). | `DeviationCard.md` |
| **Inspection (research)** | A serious, documented, reusable study of how a deviation affects the product. | `Inspection.md` |
| **Work Order (WO, `פק"ע`)** | The whole output produced under one production number on one machine. An **attribute** of the deviation, not an entity. | `Deviation.md` |
| **NCR** | The non-conformance report number kept by QA. A plain string attribute of the deviation. | `Deviation.md` |
| **`אישור חריגה` (deviation approval)** | The official output document, issued when a deviation is approved "use as is". | `reference/output-document.md` |

---

## 4. Actors

- **Operator (production):** detects deviations, separates suspect parts, records into
  the source Excel; during ETL, moderates the auto-parse.
- **Engineer:** studies the deviation, orders/records inspections, sets the decision.
  Never overruled by the system.
- **Administrator:** maintains reference data (types, CG/g-positions, zone,
  deviation-type, inspection-type dictionaries); cleans operator-populated lists.
- **QA:** owns NCR typing and the regulatory layer (out of this base's scope).

---

## 6. Save flow and canon resolution

- **Input binding:** the system first binds the input to what exists — is there an
  Item, does it have the needed dimensions. No dimension (non-CG) → the characteristic
  is **auto-created** on the Item (no form). No Item at all → an Item form plus a
  one-off seeding of CG dimensions (a missing CG may be created on the fly).
- **Findings** land on the Item's characteristics (FK on `(item, #)`); measurement
  fields (`direction`, `value`, `dimension_point`, `comment`, Affected zone, Deviation
  type) sit on the finding. Integrity is at the deviation level.
- **Canon binding is done early — before registration** (`CharacteristicGroup.md` →
  Mapping): the normal order is to create the mapping/link first, then register the
  deviation. Retroactive mapping is a data-loss risk and is **not** the default; the
  only exception is an urgent WO (register unlinked, map later).

---

## 7. Process — end to end (9 steps)

Each step: **what happens · why · branches.**

**Step 1 — A deviation is detected in production.**
The operator checks a part every ~2 h; on a deviation, all parts since the last good
check are separated; a post-WO sampling check can send the whole WO to MRB. *Why:*
this is the source that creates a record; it also fixes the sign convention (− below
min, + above max). *Branch:* single incident vs. a whole-WO deviation — this affects
which document is later issued (Step 9).

**Step 2 — Data arrives as a Hebrew table.**
Deviations are recorded in an Excel file in Teams, Hebrew/RTL, with no direct system
access. *Why:* it is the raw material; the "dimension" column is empty — the substance
is in the free Hebrew text. *Branch:* description quality varies from a clean formula
to typo-ridden text — handled next. (Detail: `Import-Workflow.md`.)

**Step 3 — Ingestion: auto-parse plus manual approval.**
The description is parsed by regex (dimension number, direction, magnitude), corrected,
and **approved by the operator**. One Excel row → one deviation with an array of
findings; stage 1 loads manually, one at a time. *Why:* the text is too noisy for full
trust, so a human is the final filter. *Branches:* direction from the max/min word
(number sign is secondary); a sample (`X מתוך Y`) → quantity 9999; qualitative signs
(`GO`, pin) → the comment field for now. (Detail: `Import-Workflow.md`.)

**Step 4 — Binding to the part and its dimensions.**
Before saving, the system binds the input to what exists; findings land on the Item's
characteristics; measurement data sits on the finding. *Why:* to keep integrity — a
deviation is stored and served whole, never split by dimension. *Branches:* part &
dimension exist → bind; part exists, dimension missing (non-CG) → the characteristic is
auto-created without a form; no part → a new-part form plus seeding of CG dimensions
(and, if the needed CG is missing, it can be created here). (Detail: `Item.md`,
`Characteristic.md`.)

**Step 5 — Canon binding, before registration.**
The dimension is linked to a g-position via mapping, using the "Create mapping / link"
buttons in the entry form (next to "Create Item"). The normal order is: map first, then
register. *Why:* the canon enables cross-part comparison and the immediate prior-
deviation overview (Step 6); deferring the link tends to lose it. *Branches:* mapping
exists → the g-position is shown (a read); no mapping → it is created here; the part has
no such position → code 99; **exception — an urgent WO:** register the dimension
unlinked and map later (exception, not the rule). (Detail: `CharacteristicGroup.md`.)

**Step 6 — Deviation card — the key deliverable.**
On entry, the card opens with an automatic overview of past deviations with a matching
(Item, dimension) pair or, for canon-bound dimensions, by matching (CG, g-index), plus a
query constructor for second-level search. *Why:* the engineer immediately sees prior
occurrences, decisions and justifications — decisions become uniform and precedent-based.
*Branches:* exact matches exist → lean on prior decisions; none → second-level
descriptive search (zone, deviation type). (Detail: `DeviationCard.md`, `Search.md`.)

**Step 7 — Study and, if needed, an inspection (research).**
The engineer assesses the impact. A serious, documented, reusable study is recorded as an
inspection, linked to the finding **and** to the (Item, dimension) pair; the routine
drawing check is not an inspection. *Why:* it accumulates evidence; its verdict is
independent and does not dictate the decision; all the "science" lives in the attached
protocol. *Branches:* zero inspections (the usual case) … or several (different
dimensions studied differently). (Detail: `Inspection.md`.)

**Step 8 — Decision on the deviation.**
The engineer sets `decisionDev` — a live decision that also weighs accompanying factors
(e.g. surface cleanliness: a broken tool causes burrs → reject even if the numbers are in
tolerance). *Why:* the key branch of the whole process — it drives the parts' fate and
which document, if any, is issued. *Branches:* the 4-value outcome dictionary
(approved / rejected / sorting / repair). (Detail: `Deviation.md`.)

**Step 9 — Closing document (on approval).**
On `approved`, the `אישור חריגה` document is issued on the standard QA form (DS-QC.2-2,
rev 2.0). Stage 1 fills it manually, so the base must carry all fields so that filling is
copy-from-card. *Why:* the official confirmation that the batch may be used; no document
is issued for scrap. *Branches:* one document per whole WO (several deviations listed
inside, each with its own approved quantity and description); exception — a single
incident approved before the batch reaches QC gets its own document. (Detail:
`reference/output-document.md`.)

---

## 10. Cross-cutting principles

- **Decisions are live, not procedural.** The engineer weighs accompanying factors (a
  broken tool → burrs → reject, even with in-tolerance numbers).
- **Cross-links between dimensions** ("A is approved if B is in tolerance") are **not a
  data structure** — only free text in `explanation` or the inspection.
- Search by (Item + dimension) matches on the finding, but the **unit of output is always
  the whole deviation**.

---

*Canonical source: repo `docs/model/`. Entry point: this file. Change control: `docs/decisions.md`.*
