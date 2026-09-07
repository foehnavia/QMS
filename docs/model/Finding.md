---
part_of: MIS-QMS/docs/model
entity: Finding
order: 60
canon: true
rev: "1.01"
updated: 2026-09-07
---

# Finding

> A deviation on one dimension inside a deviation. Addressable for search, and
> **carrying its own outcome** (rev 1.01). Entry point: `_overview.md`.

## Definition

A finding sits inside a `Deviation.md` and pins the deviation to one specific
dimension (`Characteristic.md`). A deviation can carry several findings
(`1..N`).

## Outcome — the finding's own decision (rev 1.01)

> Revised 2026-09-07 (QMS-025), by use rather than by argument. Until rev 1.00 a finding
> **carried no decision** and everything was read off the deviation. The hand run showed
> what that costs: a deviation with one finding reads unambiguously, a deviation with two
> or more does not — the screen says the batch was rejected and cannot say **which
> dimension rejected it**. The engineer then opens records to find out, which is the work
> the base exists to remove.

- **`outcome`** — `permitted` · `not permitted` · **empty = not decided yet**. Empty is the
  normal state of a freshly registered deviation: findings are entered at registration,
  and the judgement comes later.
- **Set on the finding itself**, in its own form. Nothing is blocked there — any of the
  three states is legal at any time.
- **This is not the deviation's outcome and does not replace it.** They answer different
  questions:

  | | Question | About |
  |---|---|---|
  | finding `outcome` | did this dimension pass | geometry, one dimension |
  | `decisionDev` | what happens to the batch | disposition and quantity |

  A deviation with two findings, one permitted and one not, goes to **sorting** — sorted by
  the criterion of the second one. The batch verdict does not follow from the dimension
  verdict, but it is unexplainable without it: the first is the **input** to the second.
- **The invariant that binds them** (`Deviation.md`): a deviation may carry
  `approved — use as is` **only** when every one of its findings is `permitted`.
- **An inspection has no outcome at all** (`Inspection.md` rev 1.03). It supplies the
  information; the judgement is here. Before rev 1.01 the verdict sat on the inspection
  because the finding had nowhere to put one — and that placed a judgement on a record whose
  own canon says it does not judge.

## Fields

- `dimension_main` — the dimension the finding is about; **used for canon binding**
  (via the characteristic's mapping, `CharacteristicGroup.md`).
- `dimension_point` — optional point index; **not used in search**.
- `direction` — `±` (sign convention: `−` below minimum, `+` above maximum;
  `Import-Workflow.md`).
- `value` — optional magnitude.
- `outcome` — `permitted` / `not permitted` / empty (see above).
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
