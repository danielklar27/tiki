# Lessons learned

Every agent reads this file before working. The QA agent and the orchestrator append to it
when they find a repeatable mistake or when Daniel corrects something. One lesson per bullet,
dated, concrete ("do X / never Y because Z"). Remove a lesson only when Daniel says it's wrong.

## OPEN — before the next price list
- 2026-10-10 — Daniel: descriptions are too long and too detailed (irrelevant info). He will send example descriptions. BEFORE starting the next sheet, REMIND Daniel to send them, and rewrite copywriting.md from them. Remove this item once done.

## Daniel's standing decisions (2026-10-10)
- 2026-10-10 — The "אייקון יבואן רשמי" icon is correct for EVERY brand the store sells — always add it.
- 2026-10-10 — Every colour/finish of a model is a SEPARATE product (own row, own name with the finish, own code, own image in that finish).
- 2026-10-10 — Delivery time comes from the sheet in days. If the sheet has no number (empty, "במלאי", "בהזמנה") — ask Daniel; never guess, never upload without it.
- 2026-10-10 — A product that already exists in the store is SKIPPED, no question asked. Exception: same model but a different finish is NOT a duplicate (finishes are separate products) — if unsure, ask.
- 2026-10-10 — Minor disagreements between the manufacturer's own sources (e.g. weight 8.4 vs 8.5 kg) are NOT a reason to drop a spec row: use the manufacturer's product page value (else the manual). Leave a row out only when the difference is critical (power, channels, connectivity, compatibility).
- 2026-10-10 — When a product has regional versions, Israel gets the EUROPEAN one (230V, EU tuner such as FM/DAB+, IEC ratings) unless Daniel says otherwise — use the European spec, don't drop the row.
- 2026-10-10 — Whenever anything in a sheet is uncertain (a missing/unclear value, an odd price, ambiguous finish/category/warranty/delivery), ASK Daniel — one AskUserQuestion batch before the sheet goes to him. Never guess to avoid asking.

## From the first Onkyo pilot (2026-10-10)
- 2026-10-10 — The store index used to read only page 1 (20 of ~1935 items), so find-existing missed live duplicates and two already-existing receivers were uploaded again (hidden). `store-index` now walks every page; if its count is ever ~20 again, STOP — the duplicate check is blind.
- 2026-10-10 — Konimbo here addresses items by CODE only (`/items/0?code=`); `kon.py` resolves ids to codes via store_items.json. Never call `/items/{id}` directly.
- 2026-10-10 — Onkyo EMEA spec sheets list "1*jack 3.5mm" under audio inputs — it is the AccuEQ setup-mic jack, NOT an audio input. Check input lists against the manual's panel pages.
- 2026-10-10 — US-only streaming services (Pandora, SiriusXM) never go into specs for the European/Israeli unit.
- 2026-10-10 — SEO text must keep qualifiers: 8K on HDMI inputs 1–3 is not "six HDMI inputs with 8K".

## From the old n8n automation (2026-07 → 2026-10)
- 2026-10-10 — Images almost never landed (~1 in 100). Likely causes, all designed out:
  1. Searching Google Images with the raw sheet name (sizes, Hebrew) → weak results. Search by brand + exact model.
  2. The vision model got image *URLs*; sites block hotlinking → error → `On Error: Continue` → silently no image.
     Now: we download the file ourselves and look at the local file.
  3. Konimbo received third-party URLs (thumbnails, hotlink-blocked, often WebP — Konimbo accepts only
     jpeg/png/gif/bmp). Now: we always send our own Cloudinary JPEG URL.
  4. Nothing verified the result after upload. Now: QA re-reads every item with GET.
- 2026-10-10 — `delivery_time` is an integer field in the docs; n8n sent text like "45 ימי עבודה". Send the number of days.
- 2026-10-10 — `images` and `spec` REPLACE the whole set on every POST/PUT — always send the complete list.
