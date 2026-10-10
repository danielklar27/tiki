# mapping - 2026-10-10-onkyo (PILOT: first 2 products only)
Supplier: Onkyo price list "מחירון יוני 2026" (sheet "ONKYO", header: אחריות לשנתיים). Supplier/importer name and website are NOT in the source (not in knowledge/importers.md either). No image/media links in the source.

| source | sheet column |
|---|---|
| A (SAP) model | J model (prefixed "Onkyo"), and inside name A |
| C מלל SAP (short description) | A name suffix |
| B Dimension W/H/D | not used in name (see Q4) |
| E מחיר צרכן | D price (digits only) |
| F הערות ("במלאי") | E delivery, as written |
| header C1 "אחריות לשנתיים" | F warranty = שנתיים |
| - | C = Onkyo, H = לא הועלה, G empty, I empty (free), K empty |

Products: found in pilot scope 2 / included 2 / skipped 0 (rest of the ~1190-row sheet deliberately not processed, per pilot instruction). Row 3 note: "רסיברים הנחת משווק 40%" - dealer discount note, ignored; E column used as consumer price.
Missing in source: shipping info (left empty = free), product links, finishes (none listed, one row each).
Category: both -> רסיבר לקולנוע ביתי (exists in categories.json, id 158647).

## QUESTIONS
1. Delivery time (rows TX-NR5100, TX-NR6100): source says only "במלאי", no days. Kept as "במלאי". How many days should be written? Recommendation: Daniel gives a number (e.g. 7?) - not guessed.
2. VAT: does "מחיר צרכן" (3999 / 4600) include VAT? Source does not say. Assumed yes (consumer price). Recommend confirming.
3. Category: both -> "רסיבר לקולנוע ביתי" (7.2 channel AV network receivers). Alternative "מגבר לקולנוע ביתי" is not suitable. Recommend confirm.
4. Dimensions: source has W/H/D without units (435 x 160 x 328, 435 x 173.5 x 379.5, presumably mm). Left out of names. Add to names? Recommend no.
5. Warranty: taken from sheet header "אחריות לשנתיים" and written as "שנתיים" for both rows. Recommend confirm it applies to all items (also whether to write "24 חודשים").
6. Shipping: not mentioned for Onkyo; left empty (= free shipping). Recommend confirm.
7. Importer/supplier name and website for researcher: not in source - please provide (official importer icon applies per standing decision).
8. Model naming: J = "Onkyo TX-NR5100" / "Onkyo TX-NR6100" (brand + model for image search). Names include a short Hebrew descriptor ("רסיבר רשת 7.2", "THX" for NR6100); confirm style.
