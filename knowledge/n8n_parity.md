# n8n → agents: parity checklist

Source: Drive doc `konimbo_automation_state.md` (state of 2026-07-12). If the live n8n workflow
changed after that date, export it (n8n editor → ⋯ → Download) and re-check this list against it.

## Every n8n node / behaviour and where it lives now

| # | n8n | Now | Status |
|---|---|---|---|
| 1 | Trigger (manual) | `/upload-pricelist` | ✅ |
| 2 | Google Sheets: Get rows (Sheet1, fixed headers A–I) | Drive connector read → `kon.py sheet-to-run` (same headers + J model, K source link) | ✅ |
| 3 | Limit (rows per run) | batches of 5, `--rows` for a pilot subset, dry-run mode | ✅ |
| 4 | OpenAI "Message a model" — Hebrew marketing description + spec + brand_hebrew, strict JSON | `product-copywriter` agent — one dedicated call per product with the prompt in `copywriting.md` (all n8n prompt rules kept, see below) + the verified facts of that exact product | ✅ improved |
| 4a | Prompt rule: ignore English colour words in the name, don't translate them | copywriting.md rule 3 | ✅ |
| 4b | Prompt rule: 4–8 spec rows, omit anything not known for sure | now stronger: every spec row must come from an official source (facts.json) and carries its source; 4–10 rows | ✅ improved |
| 4c | Prompt rule: Hebrew brand name, woven into the description next to the English name | copywriting.md rule 4; brand_hebrew also goes into the title (as n8n) | ✅ |
| 4d | Strict JSON output (additionalProperties false) | `build-item` validates copy.json / facts.json and blocks upload on errors | ✅ |
| 5 | SerpApi Google Images (no exact-phrase quotes) | WebSearch on the manufacturer's domain → product page → `page-images`; SerpApi optional fallback only | ✅ replaced |
| 6 | Code node: baseItem, image scoring, candidates | `kon.py build-item` (business rules) + `img-fetch` (size/background analysis) | ✅ |
| 7 | Pick Best Image (gpt-4o-mini vision on URLs, On Error: Continue) | researcher looks at the downloaded files itself; exact-model evidence required; failures are reported, never silent | ✅ improved |
| 8 | Finalize Item: images [{url, alt=title, position 1}] | `build-item` — same, but our own Cloudinary JPEG | ✅ |
| 9 | title = sheet name + brand_hebrew | `build-item` | ✅ |
| 10 | code = sheet name (upsert key) | `build-item` | ✅ |
| 11 | store_category_title, brand, price, warranty, delivery_time | `build-item` (delivery_time sent as integer days per API docs) | ✅ |
| 12 | visible + zap_visable true | uploaded hidden → set true only after QA pass (`kon-publish`) | ✅ changed on purpose |
| 13 | Icons: "אייקון יבואן רשמי" always, "free shipping" when shipping empty | `build-item` | ✅ |
| 14 | Shipping map "" →72064, 60 →44488, 120 →44318, else needs review | `build-item` | ✅ |
| 15 | HTTP POST /v1/items (token as query param, body {item}) | `kon-upsert` (token in query + body, retries on 429/5xx) | ✅ |
| 16 | Log Created Product → tab "מוצרים שהועלו" (name, ID, notes) | run sheet updated with status/ID/notes + cumulative `kon.py master-log` sheet + HTML report | ✅ |

## Added beyond n8n
- Exact-model image gate with recorded evidence; JPEG only (Konimbo rejects WebP).
- Spec rows each traced to an official source (manufacturer spec page/datasheet, Israeli importer); QA re-verifies every row.
- Independent QA reading the live item back (GET) — image Konimbo actually stored, every field, colour consistency.
- Hidden upload → publish only after QA; `kon-hide` to pull an item back.
- Duplicate check against the existing store before anything is created (`store-index` / `find-existing`).
- Store conventions: the copywriter reads existing items of the same category (`category-examples`) to match title style, spec names/groups, description length.
- SEO title + meta description per product.
- Placeholder guard: "לא צוין במחירון" / "יתומחר בנפרד" are never sent to the store as text.
- Description HTML validation (allowed tags, no markdown/English leftovers).
- Retries with backoff; resumable runs (status.json per product); dry-run mode for pilots.
- Learning loop: lessons.md, brands.md, importers.md, spec_glossary.md grow with every run and every correction.
