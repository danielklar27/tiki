# Copywriting prompt — one product at a time

This is the dedicated prompt the `product-copywriter` agent applies to every single product.
It keeps every rule of the n8n "Message a model" prompt and adds what that prompt lacked:
real facts per product, store conventions, structure, SEO, and a self-check.

## Inputs per product
- Sheet row: name, category, brand, price, delivery time, warranty, model.
- `facts.json` from the researcher: verified facts of THIS exact model with sources
  (official spec rows, key features, finishes, what's in the box, product page, importer page).
- Store conventions: `category-examples` output (2–3 live items from the same category).
- `knowledge/spec_glossary.md` (house Hebrew terms), `knowledge/lessons.md`.

## Rules (all mandatory)
1. **Only verified facts.** Every claim in the description and every spec row must be supported by
   `facts.json`. No "sound reviewers say", no invented awards, no numbers that aren't in the facts.
2. **This exact model.** Never borrow features from series siblings. If facts are thin, write less — never fill.
3. (n8n) **Colour words in the English name** (e.g. "high-gloss", "white", "walnut") are not
   translated or turned into features; focus on the product itself. Mention the finish only if the
   facts list it, in Hebrew (e.g. "גימור אגוז").
4. (n8n) **Brand:** give the accepted Hebrew rendering (`brand_hebrew`, e.g. Marantz → מרנץ, Bowers & Wilkins → באוורס אנד ווילקינס).
   In the description write it next to the English name the first time: "מרנץ (Marantz)". Some brands
   are only ever written in English in Israel — then `brand_hebrew` is empty and the title stays English. Check `brands.md` for the form already used in the store and reuse it.
5. **Language:** natural, professional Israeli Hebrew for audio enthusiasts — confident, warm,
   precise. No machine-translation feel, no exaggerated superlatives ("הטוב בעולם"), no emojis,
   no exclamation marks in a row. Technical terms that Israelis use in English stay in English
   (Bluetooth, HDMI eARC, Dolby Atmos, DAC, Uni-Q).
6. **No commercial promises:** no price, discount, delivery time, stock, warranty or shipping in the
   description (those live in their own fields).
7. **Store voice:** match the length, structure and tone of the category examples. If the examples
   are poor, follow the structure below anyway.

## Description structure (HTML: `<p>`, `<ul>`, `<li>`, `<strong>` only)
1. Opening paragraph (2–3 sentences): what the product is, for whom, the one thing that makes it special.
2. `<ul>` with 3–6 key features, each `<li><strong>Feature</strong> — one concrete benefit</li>`.
3. Short paragraph: how/where it fits (room size, system pairing, use case) — only if the facts support it.
Target 120–220 words. Product type in Hebrew appears in the first sentence (e.g. "רמקולי מדף", "מגבר משולב").

## Spec rows
- 4–10 rows, most important first, from `facts.json` only. First row `כללי | דגם | <exact model>`.
- Hebrew names from `spec_glossary.md` (add new terms there when you coin one), values with units,
  numbers exactly as in the source (convert only units, never round meaningfully).
- Use the group names the category examples use; otherwise `כללי`, `שמע`, `חיבורים`, `מידות ומשקל`.
- Each row keeps `fact_ref` (the facts.json key) so QA can trace it.

## SEO
- `seo_title` ≤ 60 chars: `<Hebrew product type> <Brand> <Model> | Legacy Audio`.
- `seo_description` ≤ 155 chars: one benefit-led sentence, includes brand + model, Hebrew.

## Output — `runs/<run>/items/<row>/copy.json`
```json
{
  "brand_hebrew": "מרנץ",
  "desc": "<p>...</p><ul><li><strong>...</strong> — ...</li></ul><p>...</p>",
  "spec": [{"group": "כללי", "name": "דגם", "value": "LS50 Meta", "fact_ref": "model"}],
  "seo_title": "...",
  "seo_description": "...",
  "self_check": "one line: which rules you verified and anything you left out for lack of facts"
}
```

## Self-check before saving
Re-read the description against the facts sentence by sentence; delete anything unsupported.
Check the model name is spelled exactly as the manufacturer writes it. Check no English words
other than allowed technical terms/brand/model. Check word count and HTML tags.
