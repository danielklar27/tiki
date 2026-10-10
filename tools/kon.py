#!/usr/bin/env python3
"""Legacy Audio x Konimbo toolkit — the deterministic half of the upload agents.

Agents decide (which page, which image, what text); this script does everything that must
be done the same way every time (download, image processing, Cloudinary, Konimbo payload
rules, API calls, report). Every command prints JSON.

    python tools/kon.py -h
    python tools/kon.py <command> -h

Secrets come from env vars (or a .env file at the repo root, never committed):
    KONIMBO_TOKEN, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET,
    SERPAPI_KEY (optional fallback image search)
"""
import argparse
import contextlib
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
KNOWLEDGE = ROOT / "knowledge"

API = "https://api.konimbo.co.il/v1"
SHIPPING_IDS = {"": "72064", "60": "44488", "120": "44318"}
ICON_IMPORTER = {"image_title": "אייקון יבואן רשמי", "title": "יבואן רשמי",
                 "url": "/", "visible": "1", "index-visible": "0"}
ICON_FREE_SHIPPING = {"image_title": "free shipping", "title": "משלוח חינם",
                      "url": "/", "visible": "1", "index-visible": "0"}

IMG_SIZE = 1000
IMG_MARGIN = 0.06
MIN_SOURCE_SIDE = 800
JPEG_QUALITY = 92
WHITE_THRESHOLD = 242          # a pixel is "white" if every channel is >= this
CLOUDINARY_FOLDER = "legacy-audio/products"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
}

# Sheet headers -> keys. Matched by prefix after normalising the geresh.
COLUMNS = [
    ("עמודה א'", "name"), ("עמודה ב'", "category"), ("עמודה ג'", "brand"),
    ("עמודה ד'", "price"), ("עמודה ה'", "delivery_time"), ("עמודה ו'", "warranty"),
    ("עמודה ח", "status"), ("עמודה ט'", "shipping_cost"), ("עמודה י'", "model"),
    ("עמודה יא'", "source_link"),
]
SHEET_HEADERS = [
    "עמודה א': שם מוצר", "עמודה ב': קטגוריה", "עמודה ג': יצרן", "עמודה ד': מחיר",
    "עמודה ה': זמן אספקה", "עמודה ו': אחריות", "", "עמודה ח : סטטוס",
    "עמודה ט': עלות משלוח", "עמודה י': דגם יצרן", "עמודה יא': קישור מקור",
]
OPTIONAL_COLUMNS = {"model", "source_link"}
PLACEHOLDERS = {"לא צוין במחירון", "לא צוין", "-", "—", "n/a"}
ALLOWED_DESC_TAGS = {"p", "ul", "ol", "li", "strong", "b", "em", "br"}


# ---------------------------------------------------------------- helpers

def load_dotenv():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def die(msg, **extra):
    out({"ok": False, "error": msg, **extra})
    sys.exit(1)


def env(name):
    value = os.environ.get(name)
    if not value:
        die(f"missing env var {name}")
    return value


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_dir(run):
    return RUNS / run


def item_dir(run, row):
    return run_dir(run) / "items" / str(row)


def load_products(run):
    products = read_json(run_dir(run) / "products.json")
    if products is None:
        die(f"run {run} has no products.json — run sheet-to-run first")
    return products


def get_product(run, row):
    for p in load_products(run):
        if str(p["row"]) == str(row):
            return p
    die(f"row {row} not found in run {run}")


def set_status(run, row, **fields):
    path = item_dir(run, row) / "status.json"
    status = read_json(path, {"history": []})
    status.update(fields)
    status["history"].append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), **fields})
    write_json(path, status)
    return status


RETRY_STATUS = {429, 500, 502, 503, 504}


def http(method, url, retries=3, **kw):
    """requests.request with backoff (2s, 4s, 8s) on network errors and 429/5xx."""
    kw.setdefault("timeout", 90)
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, **kw)
            if r.status_code not in RETRY_STATUS or attempt == retries:
                return r
        except requests.RequestException:
            if attempt == retries:
                raise
        time.sleep(2 ** (attempt + 1))


# ---------------------------------------------------------------- Konimbo API

def kon_request(method, path, item=None, params=None, fatal=True):
    token = env("KONIMBO_TOKEN")
    params = {**(params or {}), "token": token}
    body = {"token": token, "item": item} if item is not None else None
    try:
        r = http(method, f"{API}{path}", params=params, json=body)
    except requests.RequestException as e:
        if fatal:
            die(f"Konimbo {method} {path} network error: {e}")
        return None, {"error": str(e)}
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:2000]}
    if not r.ok and fatal:
        die(f"Konimbo {method} {path} -> HTTP {r.status_code}", response=data)
    return r.status_code, data


def cmd_env_check(a):
    report = {v: bool(os.environ.get(v)) for v in
              ("KONIMBO_TOKEN", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
               "CLOUDINARY_API_SECRET", "SERPAPI_KEY")}
    if report["KONIMBO_TOKEN"]:
        code, _ = kon_request("GET", "/store_categories", fatal=False)
        report["konimbo_read_categories"] = code
        code, _ = kon_request("GET", "/items/0", params={"code": "__permission_probe__"}, fatal=False)
        # 404 = read works (item just doesn't exist); 401/403 = no read permission
        report["konimbo_read_items"] = code
    if all(report[k] for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")):
        try:
            r = requests.get(f"https://api.cloudinary.com/v1_1/{os.environ['CLOUDINARY_CLOUD_NAME']}/usage",
                             auth=(os.environ["CLOUDINARY_API_KEY"], os.environ["CLOUDINARY_API_SECRET"]),
                             timeout=30)
            report["cloudinary"] = r.status_code
        except requests.RequestException as e:
            report["cloudinary"] = f"network error: {e}"
    if report["SERPAPI_KEY"]:
        try:
            r = requests.get("https://serpapi.com/account.json",
                             params={"api_key": os.environ["SERPAPI_KEY"]}, timeout=30)
            report["serpapi"] = r.status_code
        except requests.RequestException as e:
            report["serpapi"] = f"network error: {e}"
    out(report)


def cmd_categories(a):
    cache = KNOWLEDGE / "categories.json"
    if a.refresh or not cache.exists():
        _, data = kon_request("GET", "/store_categories")
        cats = [{"id": c.get("id"), "title_he": c.get("title_he"), "parent_id": c.get("parent_id")}
                for c in data]
        write_json(cache, cats)
    cats = read_json(cache)
    titles = [c["title_he"] for c in cats if c.get("title_he")]
    if a.check:
        missing = [t for t in a.check if t not in titles]
        out({"ok": not missing, "missing": missing,
             "suggestions": {t: [c for c in titles if t.strip() in c or c in t][:5] for t in missing}})
        sys.exit(0 if not missing else 2)
    out({"count": len(titles), "titles": titles})


def code_for_id(item_id):
    """This store has lookup-by-code enabled: /items/{x} treats x as a CODE, never an id.
    Resolve an id to its code via the store snapshot (refreshed once if the id is missing)."""
    for attempt in (0, 1):
        for it in read_json(KNOWLEDGE / "store_items.json", []) or []:
            if str(it.get("id")) == str(item_id):
                if not it.get("code"):
                    die(f"item {item_id} has no code — cannot address it through the API")
                return it["code"]
        if attempt == 0:
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_store_index(None)
    die(f"item id {item_id} not found in the store")


def kon_item(method, item_id=None, code=None, item=None):
    code = code or code_for_id(item_id)
    return kon_request(method, "/items/0", item=item, params={"code": code})


def cmd_kon_get(a):
    _, data = kon_item("GET", item_id=a.id, code=a.code)
    if a.run and a.row:
        write_json(item_dir(a.run, a.row) / "konimbo_live.json", data)
    out(data)


def cmd_kon_update(a):
    item = read_json(a.file)
    _, data = kon_item("PUT", item_id=a.id, item=item)
    out(data)


def cmd_kon_publish(a):
    visible = not a.hide
    results = []
    for item_id in a.ids:
        _, data = kon_item("PUT", item_id=item_id, item={"visible": visible, "zap_visable": visible})
        if str(data.get("id")) != str(item_id):
            die(f"code lookup for {item_id} returned item {data.get('id')} — stopped", results=results)
        results.append({"id": item_id, "visible": data.get("visible")})
    if a.run:
        for p in load_products(a.run):
            st = read_json(item_dir(a.run, p["row"]) / "status.json", {})
            if str(st.get("konimbo_id")) in [str(i) for i in a.ids]:
                set_status(a.run, p["row"], published=visible, stage="published" if visible else "hidden")
    out(results)


# ---------------------------------------------------------------- store knowledge

def norm(text):
    return re.sub(r"[^0-9a-z\u0590-\u05ff]", "", (text or "").lower())


def cmd_store_index(a):
    """Snapshot of every item in the store — used for duplicate detection."""
    # /items returns 20 per page and ignores per_page/limit — walk ?page= until an empty page
    items, seen, page = [], set(), 1
    while True:
        code, data = kon_request("GET", "/items", params={
            "attributes": "id,title,code,brand,store_category_title,visible,price", "page": page},
            fatal=False)
        if code == 404:   # past the last page
            break
        if code != 200:
            die(f"Konimbo GET /items page {page} -> HTTP {code}", response=data)
        batch = data if isinstance(data, list) else data.get("items", [])
        new = [it for it in batch if it.get("id") not in seen]
        if not new:
            break
        seen.update(it.get("id") for it in new)
        items.extend(new)
        page += 1
    write_json(KNOWLEDGE / "store_items.json", items)
    out({"count": len(items), "pages": page - 1, "path": str(KNOWLEDGE / "store_items.json")})


def find_existing(products, items):
    results = []
    for p in products:
        model, name, brand = norm(p.get("model")), norm(p["name"]), norm(p["brand"])
        hits = []
        for it in items:
            title, code = norm(it.get("title")), norm(it.get("code"))
            if code and code == name:
                hits.append({**it, "match": "same code (upsert would UPDATE this item)"})
            elif model and len(model) >= 4 and model in title and (not brand or brand in norm(it.get("brand")) or brand in title):
                hits.append({**it, "match": "same model in title"})
        results.append({"row": p["row"], "name": p["name"], "model": p.get("model", ""), "existing": hits[:5]})
    return results


def cmd_find_existing(a):
    items = read_json(KNOWLEDGE / "store_items.json")
    if items is None:
        die("no store index — run store-index first")
    if a.csv:
        tmp_run = "_draft_check"
        cmd_sheet_to_run(argparse.Namespace(csv=a.csv, run=tmp_run, rows=None, quiet=True))
        products = load_products(tmp_run)
        shutil.rmtree(run_dir(tmp_run), ignore_errors=True)
    else:
        products = load_products(a.run)
    res = [r for r in find_existing(products, items) if r["existing"]]
    out({"rows_with_existing_items": len(res), "results": res})


def cmd_category_examples(a):
    cats = read_json(KNOWLEDGE / "categories.json")
    if cats is None:
        die("no categories cache — run categories --refresh first")
    cat = next((c for c in cats if c.get("title_he") == a.category), None)
    if not cat:
        die(f"category not found: {a.category}")
    _, data = kon_request("GET", "/items", params={
        "store_category_id": cat["id"], "visible": "true", "sort_by": "updated_at", "sort_order": "desc",
        "attributes": "id,title,brand,desc,spec,filters,seo_title,seo_description,images,set_icons"})
    items = (data if isinstance(data, list) else data.get("items", []))[: a.limit]
    path = KNOWLEDGE / "category_examples" / f"{cat['id']}.json"
    write_json(path, items)
    out({"category": a.category, "count": len(items), "path": str(path), "items": items})


# ---------------------------------------------------------------- sheet <-> run

def normalise_header(h):
    return h.replace("׳", "'").replace("`", "'").strip()


def cmd_sheet_to_run(a):
    text = Path(a.csv).read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    headers = [normalise_header(h) for h in next(reader)]
    index = {}
    for i, h in enumerate(headers):
        for prefix, key in COLUMNS:
            if h.startswith(prefix) and key not in index:
                index[key] = i
    missing = [k for _, k in COLUMNS if k not in index and k not in OPTIONAL_COLUMNS]
    if missing:
        die("sheet is missing columns", missing=missing, headers=headers)
    products, skipped = [], []
    for n, cells in enumerate(reader, start=2):        # row 1 = headers
        get = lambda k: cells[index[k]].strip() if k in index and index[k] < len(cells) else ""
        if not get("name"):
            continue
        p = {"row": n, **{k: get(k) for _, k in COLUMNS}}
        if p["status"] not in ("", "לא הועלה"):
            skipped.append({"row": n, "status": p["status"]})
            continue
        products.append(p)
    if getattr(a, "rows", None):
        wanted = {int(r) for r in a.rows.split(",")}
        products = [p for p in products if p["row"] in wanted]
    rd = run_dir(a.run)
    rd.mkdir(parents=True, exist_ok=True)
    if Path(a.csv).resolve() != (rd / "approved.csv").resolve():
        shutil.copy(a.csv, rd / "approved.csv")
    write_json(rd / "products.json", products)
    if getattr(a, "quiet", False):
        return
    out({"run": a.run, "products": len(products), "skipped": skipped,
         "brands": sorted({p["brand"] for p in products}),
         "categories": sorted({p["category"] for p in products})})


def cmd_run_to_csv(a):
    """Approved sheet + results -> CSV for updating the Google Sheet (status/ID columns)."""
    rows = list(csv.reader(io.StringIO((run_dir(a.run) / "approved.csv").read_text(encoding="utf-8-sig"))))
    headers = rows[0] + ["מזהה קונימבו", "הערות אוטומציה"]
    status_col = next(i for i, h in enumerate(rows[0]) if normalise_header(h).startswith("עמודה ח"))
    by_row = {p["row"]: p for p in load_products(a.run)}
    out_rows = [headers]
    for n, cells in enumerate(rows[1:], start=2):
        cells = cells + [""] * (len(rows[0]) - len(cells))
        extra = ["", ""]
        if n in by_row:
            st = read_json(item_dir(a.run, n) / "status.json", {})
            qa = read_json(item_dir(a.run, n) / "qa.json", {})
            if st.get("published"):
                cells[status_col] = "הועלה"
            elif st.get("konimbo_id"):
                cells[status_col] = "הועלה מוסתר - דורש בדיקה"
            else:
                cells[status_col] = "נכשל"
            extra = [str(st.get("konimbo_id", "")), "; ".join(qa.get("issues", []) + [flag_he(f) for f in st.get("flags", [])])]
        out_rows.append(cells + extra)
    buf = io.StringIO()
    csv.writer(buf).writerows(out_rows)
    path = run_dir(a.run) / "sheet_update.csv"
    path.write_text("﻿" + buf.getvalue(), encoding="utf-8")
    out({"path": str(path), "rows": len(out_rows) - 1})


# ---------------------------------------------------------------- page / search discovery

class _ImgCollector(HTMLParser):
    IMG_ATTRS = ("src", "data-src", "data-zoom-image", "data-large_image", "data-full",
                 "data-original", "data-lazy-src", "data-image", "data-hires", "content", "href")

    def __init__(self):
        super().__init__()
        self.found, self.title, self._in_title = [], "", False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta" and d.get("property", d.get("name", "")) in ("og:image", "og:image:secure_url", "twitter:image"):
            self.found.append((d.get("content"), "meta:" + d.get("property", d.get("name", ""))))
        if tag in ("img", "source", "a", "div", "figure", "li", "span"):
            for attr in self.IMG_ATTRS:
                v = d.get(attr)
                if v and (tag in ("img", "source") or re.search(r"\.(jpe?g|png|webp)(\?|$)", v, re.I)):
                    self.found.append((v, f"{tag}[{attr}] alt={d.get('alt', '')!r}"[:160]))
            for attr in ("srcset", "data-srcset"):
                if d.get(attr):
                    best = max((p.strip().split(" ") for p in d[attr].split(",") if p.strip()),
                               key=lambda parts: int(re.sub(r"\D", "", parts[1]) or 0) if len(parts) > 1 else 0)
                    self.found.append((best[0], f"{tag}[{attr}] alt={d.get('alt', '')!r}"[:160]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _jsonld_images(text):
    imgs = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        for m in re.finditer(r'"image"\s*:\s*(\[[^\]]*\]|"[^"]+"|\{[^}]*\})', block):
            imgs += re.findall(r'https?:[^"\s]+', m.group(1).replace("\\/", "/"))
    return imgs


def cmd_page_images(a):
    if Path(a.url).exists():
        text, base = Path(a.url).read_text(encoding="utf-8", errors="replace"), "file:///"
    else:
        try:
            r = http("GET", a.url, headers={**BROWSER_HEADERS, "Accept": "text/html"}, timeout=45)
        except requests.RequestException as e:
            die(f"fetch failed: {e}")
        if not r.ok:
            die(f"HTTP {r.status_code} for {a.url}")
        text, base = r.text, r.url
    p = _ImgCollector()
    p.feed(text)
    found = p.found + [(u, "json-ld") for u in _jsonld_images(text)]
    seen, results = set(), []
    for url, ctx in found:
        if not url or url.startswith("data:"):
            continue
        url = urljoin(base, html.unescape(url.strip()))
        low = url.lower()
        if url in seen or re.search(r"\.(svg|gif)(\?|$)|logo|icon|sprite|placeholder|spinner|blank\.", low):
            continue
        seen.add(url)
        results.append({"url": url, "context": ctx})
    out({"page": base, "title": html.unescape(p.title.strip()), "count": len(results),
         "images": results[: a.limit]})


def cmd_serp_images(a):
    r = http("GET", "https://serpapi.com/search.json", timeout=60, params={
        "engine": "google_images", "q": a.query, "api_key": env("SERPAPI_KEY"), "hl": "en"})
    if not r.ok:
        die(f"SerpApi HTTP {r.status_code}", response=r.text[:500])
    res = [{"original": i.get("original"), "width": i.get("original_width"),
            "height": i.get("original_height"), "title": i.get("title"),
            "source": i.get("source"), "page": i.get("link")}
           for i in r.json().get("images_results", []) if i.get("original")]
    out({"query": a.query, "results": res[: a.limit]})


# ---------------------------------------------------------------- images

def _flatten_on_white(img):
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg, True
    return img.convert("RGB"), False


def _white_mask(img):
    """L-mode mask: 255 where the pixel is near-white."""
    r, g, b = img.split()
    t = lambda ch: ch.point(lambda v: 255 if v >= WHITE_THRESHOLD else 0)
    return Image.composite(Image.composite(t(r), Image.new("L", img.size, 0), t(g)),
                           Image.new("L", img.size, 0), t(b))


def border_white_ratio(img):
    """Share of near-white pixels in the outer 4% frame — ~1.0 means a white packshot."""
    w, h = img.size
    bw, bh = max(1, w // 25), max(1, h // 25)
    mask = _white_mask(img)
    total = white = 0
    for box in ((0, 0, w, bh), (0, h - bh, w, h), (0, bh, bw, h - bh), (w - bw, bh, w, h - bh)):
        hist = mask.crop(box).histogram()
        total += sum(hist)
        white += hist[255]
    return round(white / total, 3) if total else 0.0


def analyse_image(path):
    with Image.open(path) as raw:
        fmt = raw.format
        img, had_alpha = _flatten_on_white(raw)
    w, h = img.size
    info = {"path": str(path), "format": fmt, "width": w, "height": h,
            "bytes": Path(path).stat().st_size, "transparent_bg": had_alpha,
            "border_white_ratio": border_white_ratio(img)}
    reasons = []
    if min(w, h) < MIN_SOURCE_SIDE:
        reasons.append(f"too_small (<{MIN_SOURCE_SIDE}px)")
    if not had_alpha and info["border_white_ratio"] < 0.85:
        reasons.append("background_not_white")
    info["warnings"] = reasons
    return info


def contact_sheet(entries, dest, tile=360, cols=3):
    entries = [e for e in entries if e.get("path")]
    if not entries:
        return None
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows * (tile + 28)), (200, 200, 200))
    draw = ImageDraw.Draw(sheet)
    for i, e in enumerate(entries):
        x, y = (i % cols) * tile, (i // cols) * (tile + 28)
        try:
            with Image.open(e["path"]) as im:
                im, _ = _flatten_on_white(im)
                im.thumbnail((tile - 8, tile - 8))
                sheet.paste(im, (x + (tile - im.width) // 2, y + 28 + (tile - im.height) // 2))
        except Exception:
            pass
        label = f"#{e['index']} {e.get('width', '?')}x{e.get('height', '?')} {e.get('format', '')}"
        if e.get("warnings"):
            label += " !"
        draw.rectangle((x, y, x + tile - 1, y + 27), fill=(30, 30, 30))
        draw.text((x + 6, y + 8), label, fill=(255, 255, 255))
    sheet.save(dest, quality=88)
    return str(dest)


def cmd_img_fetch(a):
    d = item_dir(a.run, a.row) / a.into
    d.mkdir(parents=True, exist_ok=True)
    index_path = d / "candidates.json"
    cands = read_json(index_path, [])
    for src in a.urls:
        entry = {"index": len(cands), "source": src}
        try:
            if Path(src).exists():
                data, ctype = Path(src).read_bytes(), ""
            else:
                u = urlparse(src)
                r = http("GET", src, timeout=60, headers={
                    **BROWSER_HEADERS, "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*",
                    "Referer": f"{u.scheme}://{u.netloc}/"})
                r.raise_for_status()
                data, ctype = r.content, r.headers.get("content-type", "")
            with Image.open(io.BytesIO(data)) as probe:
                ext = (probe.format or "img").lower()
            path = d / f"{entry['index']:02d}.{ext}"
            path.write_bytes(data)
            entry.update(analyse_image(path))
            entry["content_type"] = ctype
        except Exception as e:
            entry.update({"error": f"{type(e).__name__}: {e}"[:300]})
        cands.append(entry)
    write_json(index_path, cands)
    sheet = contact_sheet([c for c in cands if "error" not in c], d / "contact.jpg")
    out({"contact_sheet": sheet, "candidates": cands})


def process_image(src, dest, margin=IMG_MARGIN, trim=True):
    with Image.open(src) as raw:
        img, had_alpha = _flatten_on_white(raw)
    before = img.size
    bg_ratio = border_white_ratio(img)
    if trim:
        non_white = _white_mask(img).point(lambda v: 0 if v else 255)
        bbox = non_white.getbbox()
        if bbox:
            img = img.crop(bbox)
    trimmed = img.size
    content = round(IMG_SIZE * (1 - 2 * margin))
    side = max(img.size)
    warnings = []
    if not had_alpha and bg_ratio < 0.85:
        warnings.append("background_not_white")
    if side < content:
        warnings.append(f"upscaled ({side}px -> {content}px)")
    if side > content:
        img.thumbnail((content, content), Image.LANCZOS)
    elif side < content:
        scale = content / side
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (IMG_SIZE, IMG_SIZE), (255, 255, 255))
    canvas.paste(img, ((IMG_SIZE - img.width) // 2, (IMG_SIZE - img.height) // 2))
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True, subsampling=0)
    return {"source": str(src), "output": str(dest), "source_size": before,
            "product_size_after_trim": trimmed, "border_white_ratio": bg_ratio,
            "transparent_bg": had_alpha, "bytes": Path(dest).stat().st_size, "warnings": warnings}


def cmd_img_process(a):
    dest = a.out or str(item_dir(a.run, a.row) / "final.jpg")
    info = process_image(a.src, dest, margin=a.margin, trim=not a.no_trim)
    if a.run and a.row:
        set_status(a.run, a.row, stage="image_processed", final_image=dest)
    out(info)


def cloudinary_upload(path, public_id):
    cloud, key, secret = env("CLOUDINARY_CLOUD_NAME"), env("CLOUDINARY_API_KEY"), env("CLOUDINARY_API_SECRET")
    params = {"folder": CLOUDINARY_FOLDER, "invalidate": "true", "overwrite": "true",
              "public_id": public_id, "timestamp": str(int(time.time()))}
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params)) + secret
    params.update(api_key=key, signature=hashlib.sha1(to_sign.encode()).hexdigest())
    data = Path(path).read_bytes()
    r = http("POST", f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
             data=params, files={"file": (Path(path).name, data, "image/jpeg")}, timeout=120)
    if not r.ok:
        die(f"Cloudinary HTTP {r.status_code}", response=r.text[:1000])
    res = r.json()
    check = http("GET", res["secure_url"], timeout=60)   # prove the public URL really serves a JPEG
    return {"url": res["secure_url"], "width": res.get("width"), "height": res.get("height"),
            "format": res.get("format"), "bytes": res.get("bytes"),
            "public_check": {"status": check.status_code, "content_type": check.headers.get("content-type")}}


def slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s or hashlib.md5(text.encode()).hexdigest()[:12]


def cmd_cld_upload(a):
    if a.run and a.row:
        p = get_product(a.run, a.row)
        public_id = a.public_id or slug(f"{p['brand']} {p.get('model') or p['name']}")
    else:
        public_id = a.public_id or slug(Path(a.file).stem)
    res = cloudinary_upload(a.file, public_id)
    if res["public_check"]["status"] != 200 or "image/jpeg" not in (res["public_check"]["content_type"] or ""):
        die("uploaded but public URL does not serve a JPEG", result=res)
    if a.run and a.row:
        set_status(a.run, a.row, stage="image_hosted", image_url=res["url"])
    out(res)


# ---------------------------------------------------------------- payload / upload

def parse_days(text):
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def validate_desc(desc):
    """-> (blocking problems, warnings)"""
    blocking, warnings = [], []
    if not desc.strip():
        return ["empty description"], []
    bad = {t.lower() for t in re.findall(r"</?\s*([a-zA-Z0-9]+)", desc)} - ALLOWED_DESC_TAGS
    if bad:
        blocking.append(f"disallowed HTML tags in description: {sorted(bad)}")
    if re.search(r"\*\*|```|^#+ |\[[^\]]+\]\(", desc, re.M):
        blocking.append("markdown leftovers in description")
    text = re.sub(r"<[^>]+>", " ", desc)
    if not re.search(r"[\u0590-\u05FF]", text):
        blocking.append("description has no Hebrew")
    words = len(text.split())
    if not 80 <= words <= 300:
        warnings.append(f"description length {words} words (target 120-220)")
    if re.search(r"₪|משלוח|זמן אספקה|במלאי|הנחה|מבצע", text):
        warnings.append("commercial terms in description (price/shipping/stock)")
    return blocking, warnings


def build_item(product, facts, copy, image_url):
    """Business rules live here (shipping map, icons, code, visibility) — same every run.
    Returns (item, flags, errors). errors block the upload."""
    flags, errors = [], []
    raw_shipping = (product.get("shipping_cost") or "").strip()
    num = re.sub(r"[₪\s]", "", raw_shipping)
    shipping = str(int(float(num))) if re.fullmatch(r"\d+(\.\d+)?", num) else raw_shipping
    shipping_id = SHIPPING_IDS.get(shipping)
    icons = [dict(ICON_IMPORTER)] + ([dict(ICON_FREE_SHIPPING)] if shipping == "" else [])
    title = " ".join(x for x in (product["name"], copy.get("brand_hebrew", "")) if x).strip()

    price = re.sub(r"[,₪\s]", "", product.get("price", ""))
    if not re.fullmatch(r"\d+(\.\d+)?", price) or float(price) <= 0:
        errors.append(f"price is not a positive number: '{product.get('price')}'")
    for key in ("name", "category", "brand"):
        if not product.get(key, "").strip():
            errors.append(f"sheet field missing: {key}")

    spec_facts = (facts or {}).get("spec_facts", {})
    spec = []
    for s_row in copy.get("spec", []):
        if not s_row.get("name") or not str(s_row.get("value", "")).strip():
            continue
        if s_row.get("fact_ref") not in spec_facts:
            errors.append(f"spec row '{s_row.get('name')}' is not traced to a verified fact (fact_ref)")
            continue
        spec.append({"group": s_row.get("group") or "כללי", "name": s_row["name"],
                     "value": str(s_row["value"]), "position": str(len(spec) + 1)})
    if not spec:
        flags.append("no_spec")

    desc = copy.get("desc", "")
    blocking, warnings = validate_desc(desc)
    errors += blocking
    flags += [f"desc_warning: {w}" for w in warnings]

    item = {
        "title": title,
        "code": product["name"],
        "price": price,
        "store_category_title": product["category"],
        "brand": product["brand"],
        "desc": desc,
        "spec": spec,
        "visible": False,          # published only after QA pass
        "zap_visable": False,
        "set_icons": icons,
    }
    warranty = (product.get("warranty") or "").strip()
    if warranty and warranty.lower() not in PLACEHOLDERS:
        item["warranty"] = warranty
    else:
        flags.append("warranty_missing")
    days = parse_days(product.get("delivery_time"))
    if days is not None:
        item["delivery_time"] = days
    else:   # Daniel's rule: no guessing — he supplies the days
        errors.append(f"delivery time has no number of days: '{product.get('delivery_time', '')}' — ask Daniel")
    if shipping_id:
        item["shipping_option_ids"] = [shipping_id]
    else:
        flags.append(f"shipping_needs_review: '{raw_shipping}'")
    if image_url:
        if not re.match(r"https://res\.cloudinary\.com/.+\.jpe?g$", image_url):
            errors.append(f"image url is not our Cloudinary JPEG: {image_url}")
        item["images"] = [{"url": image_url, "alt": title, "position": "1"}]
    else:
        flags.append("no_verified_image")
    for key, limit in (("seo_title", 70), ("seo_description", 170)):
        if copy.get(key):
            item[key] = copy[key]
            if len(copy[key]) > limit:
                flags.append(f"{key}_too_long ({len(copy[key])} chars)")
    if isinstance(copy.get("filters"), list) and copy["filters"]:
        item["filters"] = [f for f in copy["filters"] if f.get("group_title") and f.get("group_value_title")]
    return item, flags, errors


def cmd_build_item(a):
    product = get_product(a.run, a.row)
    d = item_dir(a.run, a.row)
    facts, copy = read_json(d / "facts.json"), read_json(d / "copy.json")
    if facts is None:
        die("facts.json missing — the product-researcher agent writes it first")
    if copy is None:
        die("copy.json missing — the product-copywriter agent writes it first")
    status = read_json(d / "status.json", {})
    image_url = status.get("image_url") or facts.get("image_url", "")
    item, flags, errors = build_item(product, facts, copy, image_url)
    write_json(d / "payload.json", item)
    set_status(a.run, a.row, stage="payload_built" if not errors else "payload_blocked",
               flags=flags, errors=errors)
    out({"ok": not errors, "errors": errors, "flags": flags, "payload": item})
    sys.exit(0 if not errors else 2)


def cmd_kon_upsert(a):
    payload = read_json(item_dir(a.run, a.row) / "payload.json")
    if payload is None:
        die("payload.json missing — run build-item first")
    status = read_json(item_dir(a.run, a.row) / "status.json", {})
    if status.get("errors"):
        die("payload has blocking errors — fix and rebuild first", errors=status["errors"])
    if a.dry_run:
        set_status(a.run, a.row, stage="dry_run_ready")
        out({"dry_run": True, "would_post": payload})
        return
    _, data = kon_request("POST", "/items", item=payload)
    write_json(item_dir(a.run, a.row) / "konimbo.json", data)
    set_status(a.run, a.row, stage="uploaded_hidden", konimbo_id=data.get("id"), published=False)
    out({"id": data.get("id"), "title": data.get("title"), "visible": data.get("visible"),
         "images": data.get("images")})


FLAG_TEXT = {
    "shipping_needs_review": "עלות משלוח לא ממופה — להקצות משלוח ידנית",
    "delivery_time_not_numeric": "זמן אספקה לא מספרי — לא נשלח לקונימבו",
    "no_verified_image": "לא נמצאה תמונה מאומתת של הדגם",
    "no_description": "אין תיאור",
    "no_spec": "אין מפרט מאומת",
    "warranty_missing": "אחריות לא צוינה במחירון — לא נשלחה לחנות",
    "desc_warning": "הערה על התיאור",
    "seo_title_too_long": "כותרת SEO ארוכה מדי",
    "seo_description_too_long": "תיאור SEO ארוך מדי",
}


def flag_he(flag):
    key = re.match(r"[a-z_]*", flag).group()
    detail = flag[len(key):].lstrip(": ").strip()
    text = FLAG_TEXT.get(key, key or flag)
    return f"{text} ({detail})" if detail else text


# ---------------------------------------------------------------- report

REPORT_CSS = """
:root{--bg:#f6f5f2;--card:#fff;--text:#1d1d1b;--muted:#6b6a66;--line:#e4e2dc;
--ok:#1f7a4d;--ok-bg:#e3f3ea;--warn:#8a5a00;--warn-bg:#fdf1d8;--bad:#a12b2b;--bad-bg:#fbe5e5}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151514;--card:#1f1f1d;
--text:#ecebe7;--muted:#a3a19b;--line:#33322f;--ok:#7fd3a6;--ok-bg:#183126;--warn:#f0c46a;
--warn-bg:#352a12;--bad:#f19a9a;--bad-bg:#3a1c1c}}
:root[data-theme="dark"]{--bg:#151514;--card:#1f1f1d;--text:#ecebe7;--muted:#a3a19b;--line:#33322f;
--ok:#7fd3a6;--ok-bg:#183126;--warn:#f0c46a;--warn-bg:#352a12;--bad:#f19a9a;--bad-bg:#3a1c1c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}.stats{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.stat b{font-size:20px;display:block}.grid{display:grid;gap:14px;
grid-template-columns:repeat(auto-fill,minmax(250px,1fr))}.card{background:var(--card);
border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.img{aspect-ratio:1;background:#fff;display:flex;align-items:center;justify-content:center}
.img img{width:100%;height:100%;object-fit:contain}.noimg{color:#a12b2b;font-weight:600}
.body{padding:10px 12px 12px}.t{font-weight:600;margin:0 0 4px}.meta{color:var(--muted);font-size:13px}
.badge{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;margin:6px 0}
.ok{background:var(--ok-bg);color:var(--ok)}.warn{background:var(--warn-bg);color:var(--warn)}
.bad{background:var(--bad-bg);color:var(--bad)}ul{margin:6px 0 0;padding-inline-start:18px;font-size:13px}
"""


def cmd_report(a):
    products = load_products(a.run)
    cards, counts = [], {"published": 0, "hidden": 0, "failed": 0, "no_image": 0}
    for p in products:
        st = read_json(item_dir(a.run, p["row"]) / "status.json", {})
        qa = read_json(item_dir(a.run, p["row"]) / "qa.json", {})
        live = read_json(item_dir(a.run, p["row"]) / "konimbo_live.json", {}) or {}
        payload = read_json(item_dir(a.run, p["row"]) / "payload.json", {}) or {}
        img = next((i.get("url") for src in (live, payload) for i in (src.get("images") or []) if i.get("url")),
                   st.get("image_url"))
        if st.get("published"):
            badge, cls = "פורסם", "ok"; counts["published"] += 1
        elif st.get("konimbo_id"):
            badge, cls = "הועלה מוסתר — דורש טיפול", "warn"; counts["hidden"] += 1
        else:
            badge, cls = "לא הועלה", "bad"; counts["failed"] += 1
        if not img:
            counts["no_image"] += 1
        issues = qa.get("issues", []) + [flag_he(f) for f in st.get("flags", [])] + \
            [f"⚠ {w}" for w in qa.get("warnings", [])]
        e = html.escape
        cards.append(
            f'<article class="card"><div class="img">'
            + (f'<img src="{e(img)}" alt="{e(p["name"])}" loading="lazy">' if img else '<span class="noimg">אין תמונה מאומתת</span>')
            + f'</div><div class="body"><p class="t">{e(p["name"])}</p>'
            f'<div class="meta">{e(p["brand"])} · {e(p["category"])} · ₪{e(p["price"])}'
            + (f' · ID {e(str(st["konimbo_id"]))}' if st.get("konimbo_id") else "")
            + f'</div><span class="badge {cls}">{badge}</span>'
            + ("<ul>" + "".join(f"<li>{e(i)}</li>" for i in issues) + "</ul>" if issues else "")
            + "</div></article>")
    stats = "".join(f'<div class="stat"><b>{v}</b>{k}</div>' for k, v in (
        ("סה״כ", len(products)), ("פורסמו", counts["published"]),
        ("מוסתרים לטיפול", counts["hidden"]), ("לא הועלו", counts["failed"]),
        ("בלי תמונה", counts["no_image"])))
    doc = (f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>דוח העלאת מוצרים</title><style>{REPORT_CSS}</style></head><body><main>'
           f'<h1>דוח העלאה — {html.escape(a.run)}</h1>'
           f'<p class="sub">Legacy Audio × קונימבו · {time.strftime("%d.%m.%Y %H:%M")}</p>'
           f'<div class="stats">{stats}</div><div class="grid">{"".join(cards)}</div></main></body></html>')
    path = run_dir(a.run) / "report.html"
    path.write_text(doc, encoding="utf-8")
    out({"path": str(path), **counts, "total": len(products)})


def cmd_master_log(a):
    """Cumulative log of every product any run touched (the n8n "מוצרים שהועלו" tab)."""
    rows = [["תאריך ריצה", "ריצה", "שורה", "שם מוצר", "יצרן", "קטגוריה", "מזהה קונימבו", "סטטוס", "הערות"]]
    for products_path in sorted(RUNS.glob("*/products.json")):
        run = products_path.parent.name
        for p in read_json(products_path, []):
            st = read_json(item_dir(run, p["row"]) / "status.json", {})
            qa = read_json(item_dir(run, p["row"]) / "qa.json", {})
            state = "פורסם" if st.get("published") else ("מוסתר" if st.get("konimbo_id") else "לא הועלה")
            when = (st.get("history") or [{}])[-1].get("at", "")
            notes = "; ".join(qa.get("issues", []) + [flag_he(f) for f in st.get("flags", [])])
            rows.append([when, run, p["row"], p["name"], p["brand"], p["category"],
                         st.get("konimbo_id", ""), state, notes])
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    path = RUNS / "master_log.csv"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\ufeff" + buf.getvalue(), encoding="utf-8")
    out({"path": str(path), "rows": len(rows) - 1})


# ---------------------------------------------------------------- CLI

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p

    def run_row(p, required=True):
        p.add_argument("--run", required=required)
        p.add_argument("--row", required=required, type=int)

    add("env-check", cmd_env_check, "which secrets exist and what the Konimbo token may do")
    p = add("categories", cmd_categories, "list Konimbo categories / check titles exist")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--check", nargs="+", metavar="TITLE")

    p = add("sheet-to-run", cmd_sheet_to_run, "approved sheet CSV -> runs/<run>/products.json")
    p.add_argument("csv")
    p.add_argument("--run", required=True)
    p.add_argument("--rows", help="pilot subset, e.g. 2,3,5")
    p = add("run-to-csv", cmd_run_to_csv, "results -> CSV for updating the Google Sheet")
    p.add_argument("--run", required=True)

    p = add("page-images", cmd_page_images, "list image URLs on a product page (og/json-ld/img/srcset)")
    p.add_argument("url")
    p.add_argument("--limit", type=int, default=40)
    p = add("serp-images", cmd_serp_images, "Google Images via SerpApi (discovery fallback)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = add("img-fetch", cmd_img_fetch, "download candidate images (URLs or local paths) + contact sheet")
    run_row(p)
    p.add_argument("--into", default="candidates", help="subfolder (QA uses qa_images)")
    p.add_argument("urls", nargs="+")
    p = add("img-process", cmd_img_process, "trim/pad/resize to the 1000x1000 white JPEG standard")
    p.add_argument("src")
    p.add_argument("--out")
    p.add_argument("--margin", type=float, default=IMG_MARGIN)
    p.add_argument("--no-trim", action="store_true")
    run_row(p, required=False)
    p = add("cld-upload", cmd_cld_upload, "upload a JPEG to Cloudinary and verify the public URL")
    p.add_argument("file")
    p.add_argument("--public-id")
    run_row(p, required=False)

    p = add("build-item", cmd_build_item, "facts.json + copy.json + sheet row -> validated Konimbo payload")
    run_row(p)
    p = add("kon-upsert", cmd_kon_upsert, "POST payload.json to Konimbo (hidden)")
    run_row(p)
    p.add_argument("--dry-run", action="store_true", help="validate and record, don't POST")
    p = add("kon-get", cmd_kon_get, "read an item back from Konimbo")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--id")
    g.add_argument("--code")
    run_row(p, required=False)
    p = add("kon-update", cmd_kon_update, "PUT a partial item JSON file")
    p.add_argument("id")
    p.add_argument("file")
    p = add("kon-publish", cmd_kon_publish, "make items visible (after QA pass); --hide pulls them back")
    p.add_argument("ids", nargs="+")
    p.add_argument("--run")
    p.add_argument("--hide", action="store_true")

    add("store-index", cmd_store_index, "snapshot all store items (for duplicate detection)")
    p = add("find-existing", cmd_find_existing, "rows that already exist in the store")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run")
    g.add_argument("--csv")
    p = add("category-examples", cmd_category_examples, "live items of a category (store conventions)")
    p.add_argument("category")
    p.add_argument("--limit", type=int, default=3)
    add("master-log", cmd_master_log, "cumulative CSV of all runs (the old 'מוצרים שהועלו' tab)")

    p = add("report", cmd_report, "build runs/<run>/report.html")
    p.add_argument("--run", required=True)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
