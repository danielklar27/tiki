# Konimbo API — reference for the upload agents

Sources: official docs (github.com/konimbo/API-Documentation, `v1/items.md`) + what the
old n8n automation verified in practice (Drive doc `konimbo_automation_state.md`).
The token is NEVER written in this repo. It comes from the `KONIMBO_TOKEN` env var.

## Endpoints (base `https://api.konimbo.co.il/v1`)

| Method | Path | Use |
|---|---|---|
| POST | `/items` | create — or update if `code` already exists (upsert) |
| GET | `/items/{id}` | read one item (needs READ permission) |
| GET | `/items/0?code={code}` | read by code (lookup-by-code must be enabled by Konimbo support) |
| PUT | `/items/{id}` | partial update (send only changed fields) |
| GET | `/store_categories` | list categories (`title_he`, `id`, `parent_id`) |
| DELETE | `/items/{id}` | move to trash (restorable) — agents never call this |

Body for POST/PUT: `{"token": "...", "item": {...}}`. GET: `token` as query param.
`tools/kon.py` sends the token in both places (the n8n flow used the query param and it worked).

## Fields we write

| Field | Type | Rule |
|---|---|---|
| `title` | string | sheet name + Hebrew brand name (same convention as n8n) |
| `code` | string | = sheet product name (kept from n8n so re-runs upsert the same item) |
| `price` | numeric | consumer price incl. VAT |
| `store_category_title` | string | must match an existing category EXACTLY (`kon.py categories --check`) |
| `brand` | string | manufacturer, English |
| `delivery_time` | **integer** (days) | docs say integer — n8n sent free text. `build-item` extracts the number |
| `warranty` | string | |
| `desc` | string (HTML) | Hebrew marketing description |
| `spec` | array `{group,name,value,position}` | REPLACES all rows on every call |
| `images` | array `{url,alt,position}` | REPLACES the whole set; max 12; **formats: jpeg/png/gif/bmp only — NO WebP** |
| `set_icons` | array `{image_title,title,url,visible,index-visible}` | only links icons that already exist in the store |
| `shipping_option_ids` | array of string ids | see map below |
| `visible` | bool | upload with `false`, QA publishes with `true` |
| `zap_visable` | bool | (sic — Konimbo's spelling) same as visible |

Fields that do NOT exist / do not work (verified by n8n, don't retry):
`store_category_id` (write), `icon_ids`, `default_shipping` (returned but not writable in practice).

## Shipping map (created manually in Konimbo admin)

| Sheet column ט' | id | note |
|---|---|---|
| empty | `72064` | explicit "free shipping" option (overrides old default) + free-shipping icon |
| `60` | `44488` | "משלוח בלבד 60" |
| `120` | `44318` | "משלוח בלבד 120" |
| anything else | — | no id sent, product flagged `shipping_needs_review` |

## Icons
- Always: `אייקון יבואן רשמי` (title "יבואן רשמי").
- Free shipping only: `free shipping` (title "משלוח חינם").

## Permissions we need on the token
- items: read + write (GET is required for QA — without it QA cannot verify anything).
- store_categories: read (category validation before upload).
`python tools/kon.py env-check` reports what the current token can do.
