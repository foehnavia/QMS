---
part_of: MIS-QMS/docs/model
entity: Search
order: 100
canon: true
rev: "1.05"
updated: 2026-09-06
---

# Search — by levels

> Search is organized by levels, from the most exact to the descriptive. One rule
> holds for all: the **unit of output is always the whole deviation**, even when the
> match was on a single dimension. Entry point: `_overview.md`.

## Levels

- **Level 1 — exact.** Two sections, divided by **how the match was made** — never by
  whose part it is:
  - **by number** — the same part, the same local number, across **all of its
    revisions**;
  - **by canon** — the same canonical position (CG + g-index), across all parts **and
    all revisions, other revisions of the same part included**
    (`CharacteristicGroup.md`). Excluded from it is what the neighbouring section already
    showed — **the whole set it returned, one dimension per revision** — so nothing is
    listed twice. Excluding a single dimension is not enough, and the difference shows in
    the common case: the by-number section searches every revision of the part, so when a
    local number never moved it returns one dimension per revision, and dropping only one
    of them would send the same precedent through twice.

  This is the level the **deviation card** shows automatically (`DeviationCard.md`).

  > **Why the sections are cut this way (QMS-017, hand-run 2026-09-06).** They used to be
  > cut by part — "same part" and "*other* parts, same position" — and that was correct
  > while a part had one set of dimensions: same part plus same g-position then implied
  > the same local number, so the first section already covered it. A revision breaks the
  > implication: the same part can reach the same g-position under a **different** local
  > number. Such a precedent then belonged to neither section — the first missed it
  > because the number had moved, the second discarded it because the part was its own.
  > The partition now follows the mechanics of matching, and the exclusion is stated as
  > what it always meant: *do not repeat what the neighbouring section showed.*
- **Level 2 — descriptive. Not an automatic output — a search the engineer sets up**
  (revised 2026-09-03, QMS-016; supersedes the S5 ratification of an automatic
  "zone OR type" list). The purpose stands: find parts that **cannot be linked by a
  characteristic group** yet are close enough that an earlier decision means something.
  The mechanics change:
  - the engineer composes a set of parameters — **several at once**, never one. A single
    attribute (zone alone, type alone) returns half the database, which is noise, not a
    precedent;
  - the set is composed **for one case**, each time anew;
  - at this stage the set is **not saved**; saving filter sets and re-running them belongs
    with the query constructor of stage **1.5**;
  - it is a consumer of the **filter machinery** of the reference screen, not a second
    tab of automatic output.
  **Base parameter set** (closed 2026-09-06, Q-16 — base, not final; it will be adjusted in
  use): from the part — part type, connection type, dimension class; from the finding — zone,
  deviation type, direction, magnitude range; framing — period, presence of inspections.
  **Guard: at least two parameters.** The result is shown **on the list screen**, through the
  same filter machinery — no separate screen; entry is a button from the card that pre-fills
  the filters from the current finding. **Resolved deviations only by default, with a
  toggle.** Built together with part 2 of Q-14 (reference-screen mechanics), after S6.
- **Deep search — query constructor.** Arbitrary queries over any field of all levels
  (Item ↔ finding ↔ deviation ↔ inspection), with any logic (AND/OR, ranges, nesting).
  **Read-only**; a separate stage (**1.5**) with high priority, right after the base
  skeleton (`staging.md`).

## Revisions in the output (QMS-017)

Dimensions belong to a part revision (`Characteristic.md`), so a match may cross the
boundary between two issues of the same drawing. Such a match is **shown, never filtered
out** — the engineer decides what an older issue is worth — but it is **always marked**.

| Path | What carries the meaning | Across revisions |
|---|---|---|
| by canon: `(CG, g-index)` | the g-position — a canonical identity that survives re-numbering | resolved through the **mapping of the finding's own revision**; survives a moved local number, on the same part as on any other |
| by number: `(Item, local#)` | the local number alone | **the number may mean a different feature** in the other revision |

**Two marks, and each has exactly one meaning:**

- **On the row — "same part, another revision".** Set whenever the precedent's revision
  differs from the current one. It is what lets the engineer judge comparability at all: a
  tolerance moved between issues means an earlier "approved" was granted against limits no
  longer in force.
- **On the dimension — a warning sign (`!`).** One meaning wherever it appears: *this
  number is read against another revision, and there is nothing behind it but the number.*
  Hence:

  | Case | Row mark | `!` |
  |---|---|---|
  | previous revision, dimension **canon-bound** | yes | no — the g-position finds it regardless of numbering |
  | previous revision, dimension **not in a CG** | yes | yes |
  | current revision | no | no |

  The sign is never given a second meaning on a second screen: the same rule governs the
  precedent sections and the list of a part's own deviations opened from its card.

**How the two marks look — one property each, and the same on every screen.**

| Property | Says | Where |
|---|---|---|
| **colour** (red) | there is no canon behind this number — nothing to lean on but the number itself | the dimension cell, non-CG only |
| **weight** (bold) | this row is another issue of the drawing | the revision cell, on **every** screen that lists deviations |

The two are read together, not against each other: a row that is bold **and** red says
"earlier issue, and no canon either", which is exactly the sum of its parts. Neither
property is borrowed for the other's meaning, and neither changes appearance between the
precedent sections and the part's own deviation list — the same fact must not look
different on two screens (QMS-017, доводка наряда `0025`).

- Parts of the previous issue keep arriving from the shop for two to three months after
  a change, so cross-revision precedents are not a rare curiosity — they are the normal
  state during that window.
- **What is still lost, and what is not.** A **canon-bound** dimension whose local number
  moved between revisions **is found** — that is precisely what the canonical layer is
  for, and it is the same mechanism that links different parts. Lost is only the
  **non-canon** dimension whose number moved: nothing but the number ever linked it, and
  cross-revision re-linking is deliberately deferred (`Item.md`, Revision). It is raised
  by hand — the previous revision stays fully readable for exactly that purpose.

## Notes

- Reference lists **zone** / **deviation type** are populated by the operator (at
  entry) and cleaned by the administrator; a separate table.
- Zone and CG are distinct: zone is a soft search label; CG is the strict canon with
  geometry.

## Related

`DeviationCard.md` · `Finding.md` · `CharacteristicGroup.md` · `reference/reference-data.md` · `staging.md`
