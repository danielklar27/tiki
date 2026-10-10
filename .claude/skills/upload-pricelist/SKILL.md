---
name: upload-pricelist
description: End-to-end product upload for the Legacy Audio store on Konimbo — supplier price list → Google Sheet (Daniel approves) → verified facts + exact-model image → dedicated Hebrew copy per product → validated upload (hidden) → independent QA with routed fixes → publish what passed → report + logs + lessons. Use when Daniel sends a price list / supplier file / product list to upload, says "תעלה את המחירון", "/upload-pricelist", or approves a sheet created by this flow.
---

# Upload a price list to Konimbo (orchestrator)

Agents: `pricelist-agent` → `product-researcher` → `product-copywriter` → (you upload) →
`product-qa`. Deterministic work: `python tools/kon.py <cmd>` (JSON out). Daniel is needed at
ONE point — approving the sheet (plus answering questions only he can answer). Talk to him in
Hebrew, short and concrete. Read `knowledge/lessons.md` first; it overrides this file.
`knowledge/n8n_parity.md` lists every behaviour of the old n8n flow — none may be lost.

## Phase 0 — preflight (seconds; never skip)
1. `pip install -q -r requirements.txt`; `python tools/kon.py env-check`.
   Required: `KONIMBO_TOKEN`, `CLOUDINARY_*` ×3, `konimbo_read_items` 200/404 (404 = read works),
   `konimbo_read_categories` 200, `cloudinary` 200. Any failure → tell Daniel exactly what is
   missing (which secret / network access / token permission) and stop. No partial runs.
2. `kon.py categories --refresh` and `kon.py store-index`.

## Phase 1 — price list → sheet
1. Run id `YYYY-MM-DD-<supplier-slug>`; save the file under `runs/<run>/source/`.
2. Agent `pricelist-agent` (run id, source path, anything Daniel already said).
3. `kon.py find-existing --csv runs/<run>/draft.csv` — Daniel's rule: products already in the
   store are skipped, no question. "same code" → set the row's status (col H) to
   `קיים בחנות - דילוג`. "same model in title" → compare the finish: different finish = not a
   duplicate (keep); same finish = skip; can't tell = one question. List skipped rows in the summary.
4. Ask Daniel all questions in one AskUserQuestion batch (recommended answer first). Apply the
   answers to draft.csv.
5. Google Drive `create_file`: title `<supplier> - מוצרים להעלאה`, mimeType `text/csv`, content
   = draft.csv. Save the file id in `runs/<run>/sheet.json`. Send the link + 3-line summary. **Stop.**

## Phase 2 — approved sheet → run
1. Read the sheet back from Drive as CSV (he may have edited it) → `runs/<run>/approved.csv`.
2. `kon.py sheet-to-run runs/<run>/approved.csv --run <run>` (add `--rows` for a pilot subset).
3. `kon.py categories --check <every category>`; missing → ask Daniel before going on.
4. `kon.py category-examples "<category>"` for every category in the run (store conventions
   for the copywriter and QA).

## Phase 3 — research (facts + image)
Batches of 5 rows; up to 3 `product-researcher` agents in parallel. Skip rows whose
`facts.json` already has `image_url` (resumed run) unless they are in a fix round.

## Phase 4 — copy (one dedicated pass per product)
Same batches → `product-copywriter`. Each product gets its own pass with copywriting.md and its
own facts; the agent loops on `build-item` until there are no blocking errors.

## Phase 5 — upload hidden (you, deterministic)
For each row: `kon.py build-item --run R --row N` (exit 2 = blocking errors → back to the
responsible agent, never upload) → `kon.py kon-upsert --run R --row N`.

## Phase 6 — QA, routed fixes, publish
1. `product-qa` on the same batches (round 1).
2. For failed rows route `fix_for`: researcher items → `product-researcher` (fix mode),
   copywriter items → `product-copywriter` (fix mode), then Phase 5 again for those rows, then
   QA round 2. Max 2 fix rounds. `fix_for.daniel` items are collected for the final message
   (ask them together, not one by one).
3. Publish rows whose latest verdict is `pass`: `kon.py kon-publish <ids...> --run <run>`.
   **Until `lessons.md` contains "auto-publish approved by Daniel"**, send the report first and
   publish only after he says so (early runs are calibration). `kon-publish --hide` pulls an item back.

## Phase 7 — learn
From all `qa.json`: add general, repeatable `lesson_candidates` to `knowledge/lessons.md`
(dated, deduplicated). Brands/importers/glossary updates were made by the agents — check they
are sensible. Any later correction from Daniel: fix it in Konimbo AND record the lesson.

## Phase 8 — report and logs
1. `kon.py report --run <run>` → publish `runs/<run>/report.html` with the Artifact tool.
2. `kon.py run-to-csv --run <run>` → update the run's Google Sheet (status, IDs, notes).
3. `kon.py master-log` → update (or create once) the Drive sheet `Legacy Audio - מוצרים שהועלו`
   (id kept in `knowledge/drive.json`).
4. Message Daniel: published / hidden + why / questions only he can answer / report link.

## Phase 9 — save
Commit `knowledge/` and `runs/<run>/` (JSON, report — images and store snapshots are
gitignored) and push to the current branch. The container is temporary; unpushed = lost.

## Rules
- Never publish an item that has not passed QA in this run. Never delete Konimbo items.
  Never touch items outside this run (an existing item is updated only if Daniel said so).
- Never write a token/secret in a file, commit or message.
- A tool, auth or network failure stops the run with the exact error — no improvising around it.
- If Daniel's instruction conflicts with this file, follow Daniel and add the rule to lessons.md.
