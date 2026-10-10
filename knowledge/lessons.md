# Lessons learned

Every agent reads this file before working. The QA agent and the orchestrator append to it
when they find a repeatable mistake or when Daniel corrects something. One lesson per bullet,
dated, concrete ("do X / never Y because Z"). Remove a lesson only when Daniel says it's wrong.

## Daniel's standing decisions (2026-10-10)
- 2026-10-10 — The "אייקון יבואן רשמי" icon is correct for EVERY brand the store sells — always add it.
- 2026-10-10 — Every colour/finish of a model is a SEPARATE product (own row, own name with the finish, own code, own image in that finish).
- 2026-10-10 — Delivery time comes from the sheet in days. If the sheet has no number (empty, "במלאי", "בהזמנה") — ask Daniel; never guess, never upload without it.
- 2026-10-10 — A product that already exists in the store is SKIPPED, no question asked. Exception: same model but a different finish is NOT a duplicate (finishes are separate products) — if unsure, ask.
- 2026-10-10 — Minor disagreements between the manufacturer's own sources (e.g. weight 8.4 vs 8.5 kg) are NOT a reason to drop a spec row: use the manufacturer's product page value (else the manual). Leave a row out only when the difference is critical (power, channels, connectivity, compatibility).
- 2026-10-10 — When a product has regional versions, Israel gets the EUROPEAN one (230V, EU tuner such as FM/DAB+, IEC ratings) unless Daniel says otherwise — use the European spec, don't drop the row.

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
