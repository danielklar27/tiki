---
name: upload-pricelist
description: End-to-end product upload for the Legacy Audio store on Konimbo — supplier price list → Google Sheet (Daniel approves) → research + verified exact-model images + Hebrew description/spec → upload hidden → independent QA → publish what passed → report. Use when Daniel sends a price list / supplier file / product list to upload, says "תעלה את המחירון", "/upload-pricelist", or approves a sheet created by this flow.
---

# Upload a price list to Konimbo (orchestrator)

You run three subagents (`pricelist-agent`, `product-uploader`, `product-qa`) and the
deterministic toolkit `python tools/kon.py`. Daniel is involved at ONE point: approving the
sheet. Everything else runs to the end and lands in one report. Talk to Daniel in Hebrew,
short and concrete.

Read `knowledge/lessons.md` before starting — it overrides this file where they conflict.

## Phase 0 — preflight (always, takes seconds)
`pip install -q -r requirements.txt` then `python tools/kon.py env-check`.
Required to continue: `KONIMBO_TOKEN`, the three `CLOUDINARY_*` values, Konimbo reachable,
`konimbo_read_items` = 200 or 404 (404 means read works), `cloudinary` = 200.
If anything fails, tell Daniel exactly what is missing (secret name / network access / token
permission) and stop — never run a partial pipeline. Then `python tools/kon.py categories --refresh`.

## Phase 1 — price list → sheet
1. Run id: `YYYY-MM-DD-<supplier-slug>`. Save the file Daniel sent under `runs/<run>/source/`.
2. Agent `pricelist-agent` with the run id, the source path and anything Daniel already said.
3. Ask Daniel the agent's QUESTIONS (AskUserQuestion, recommended answer first; batch them).
   Apply the answers to `runs/<run>/draft.csv` (re-run the agent only if the answers change the mapping).
4. Create the Google Sheet with the Google Drive connector: `create_file`, title
   `<supplier> - מוצרים להעלאה`, mimeType `text/csv`, content = draft.csv. Save the file id in
   `runs/<run>/sheet.json`.
5. Send Daniel the link + a 3-line summary (count, categories, anything unusual) and **stop**.
   This is the only approval gate.

## Phase 2 — approved sheet → run
When Daniel approves: read the sheet back from Drive (he may have edited it) as CSV, save
`runs/<run>/approved.csv`, then `python tools/kon.py sheet-to-run runs/<run>/approved.csv --run <run>`
and `python tools/kon.py categories --check <every category>`. A missing category → ask Daniel
(show the suggestions) before uploading anything in it.

## Phase 3 — upload (hidden)
Split the rows into batches of 5. Run `product-uploader` agents in parallel, up to 3 at a time,
each with the run id and its rows. Collect their one-line results. A tool/auth/network error
stops the run — report it, don't improvise.

## Phase 4 — QA, fix loop, publish
1. `product-qa` agents on the same batches (round 1).
2. Rows that failed with fixable issues → `product-uploader` in fix mode with the QA issues and
   `fix_instructions` → `product-qa` again (round 2). Max 2 fix rounds; after that the row stays
   hidden and goes to Daniel's list.
3. Publish every row whose latest `qa.json` verdict is `pass`:
   `python tools/kon.py kon-publish <ids...> --run <run>`.

## Phase 5 — learn
Collect `lesson_candidates` from all `qa.json` files. Add to `knowledge/lessons.md` only
general, repeatable rules (dated, one bullet each, no duplicates of existing lessons). New brand
facts go to `knowledge/brands.md`. When Daniel later corrects anything (an image, a category, a
wording), fix it in Konimbo AND add the lesson — that is how the flow gets better than him.

## Phase 6 — report
1. `python tools/kon.py report --run <run>` → publish `runs/<run>/report.html` with the Artifact
   tool (private page; Daniel opens it on his phone).
2. `python tools/kon.py run-to-csv --run <run>` → update the Google Sheet (statuses, Konimbo IDs, notes).
3. Message Daniel: N published, M hidden + why (only what needs him), link to the report.

## Phase 7 — save
Commit `knowledge/` and `runs/<run>/` (JSON + report; images are gitignored) and push to the
current branch. The container is temporary — anything not pushed (lessons included) is lost.

## Rules
- Never publish an item that has not passed QA in this run.
- Never put a token or secret in a file, commit, or message.
- Never delete Konimbo items. Never touch items that are not in this run.
- If Daniel's instruction conflicts with this file, follow Daniel and add the rule to lessons.md.
