---
part_of: MIS-QMS/docs/model
entity: output-document
order: 120
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Output document — `אישור חריגה`

> The official output, issued on approval. Entry point: `_overview.md` (process
> Step 9).

**Form:** `טופס תיעוד קבלת החלטה בעקבות אישור חריג למנה` · MIS Forms · QA&RA / Quality
Control · **DS-QC.2-2, rev 2.0, effective 2024/12/16**. Analyzed on a real instance
(WO W26007336, Item MT-SRH19A, 2 deviations).

- **Issued only on `approved`** (`Deviation.md`). The `לא קביל` ("not acceptable")
  checkbox on the form is vestigial and unused in practice; no document is filled for
  scrap.
- **One document per whole WO / `מנה`**, listing several deviations inside, each with
  its own `כמות שאושרה` (approved quantity) and description. Exception: a standalone
  incident that must be approved before the batch reaches QC gets its own document.
- **Stage 1 — filled manually.** Auto-generation and its trigger are out of stage 1
  scope (`staging.md`). Requirement to the base: **carry all fields so that filling is
  copy-from-card**.

## Form field ↔ database map

| Form field (Hebrew) | Meaning | Source |
|---|---|---|
| מק"ט | Item number | Item |
| פק"ע | Work order | Deviation.WO |
| מקושר לטופס תקלה (NCR) | Linked to NCR | Deviation.NCR — manual, may arrive later |
| כמות שאושרה | Approved quantity | Deviation.quantity (per deviation) |
| תיאור החריגה | Deviation description | Deviation findings (dimension, direction, magnitude) |
| הרציונל לאישור החריגה | Rationale | `explanation` |
| תיעוד בדיקות שבוצעו | Inspections performed | Inspection **type** from the dictionary, substituted into a standard phrase |
| הערכת הסיכון | Risk assessment | **Not a base field** — template constant (QA boilerplate, ~99 % unchanged) |
| קבלת החלטה: סיכון קביל | Decision | `decisionDev = approved` |
| אושר על ידי (תפקיד / שם / תאריך) | Approved by | **Not base fields** — single user; date from `decision_date` (default system time) |
| Page 2 — drawing / screenshot | Attachment | Inspection protocol |

## Related

`Deviation.md` · `Inspection.md` · `staging.md`
