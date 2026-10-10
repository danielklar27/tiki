#!/usr/bin/env python3
"""
העלאת מוצר לקונימבו מתמונה מקומית:
  images/<קובץ>  ->  Pillow (1000x1000 WebP)  ->  Cloudinary (URL)  ->  POST לקונימבו

שימוש:
  python konimbo_upload.py speaker.jpg --title "Legacy Aeris" --category "רמקולים" \\
      --brand "Legacy Audio" --price 4290 --delivery-time "45 ימי עבודה" \\
      --warranty "שנתיים" --shipping-cost 60

משתני סביבה (או קובץ .env באותה תיקייה):
  KONIMBO_TOKEN            טוקן ה-API של קונימבו
  CLOUDINARY_CLOUD_NAME
  CLOUDINARY_API_KEY
  CLOUDINARY_API_SECRET
"""
import argparse
import hashlib
import io
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps

IMAGES_DIR = Path(__file__).parent / "images"
SIZE = (1000, 1000)
WEBP_QUALITY = 90
KONIMBO_ITEMS_URL = "https://api.konimbo.co.il/v1/items"

# מיפוי עלות משלוח -> shipping_option_ids (נוצרו ידנית בממשק קונימבו; ראה konimbo_automation_state)
SHIPPING_IDS = {"": "72064", "60": "44488", "120": "44318"}


def load_dotenv(path: Path) -> None:
    """טעינה מינימלית של .env (בלי תלות בספרייה חיצונית)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"חסר משתנה סביבה: {name}")
    return value


def optimize_image(path: Path, crop: bool = False) -> bytes:
    """פותח תמונה, מתקן כיוון EXIF, משנה ל-1000x1000 וממיר ל-WebP באיכות גבוהה.

    ברירת מחדל: שומר על יחס התמונה ומרפד ברקע לבן (בלי עיוות וחיתוך).
    עם --crop: חותך למרכז כדי למלא את כל הריבוע.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")

        if crop:
            img = ImageOps.fit(img, SIZE, Image.LANCZOS)
        else:
            img = ImageOps.pad(img, SIZE, Image.LANCZOS, color=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
        return buf.getvalue()


def upload_to_cloudinary(data: bytes, public_id: str) -> str:
    """העלאה חתומה ל-Cloudinary ב-REST ישיר. מחזיר secure_url."""
    cloud = require_env("CLOUDINARY_CLOUD_NAME")
    api_key = require_env("CLOUDINARY_API_KEY")
    api_secret = require_env("CLOUDINARY_API_SECRET")

    timestamp = str(int(time.time()))
    # החתימה: sha1 של הפרמטרים (ממוינים אלפביתית) + ה-secret
    to_sign = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(to_sign.encode()).hexdigest()

    resp = requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
        data={
            "api_key": api_key,
            "timestamp": timestamp,
            "public_id": public_id,
            "signature": signature,
        },
        files={"file": (f"{public_id}.webp", data, "image/webp")},
        timeout=60,
    )
    if not resp.ok:
        sys.exit(f"Cloudinary נכשל ({resp.status_code}): {resp.text}")
    return resp.json()["secure_url"]


def create_konimbo_item(args, image_url: str) -> dict:
    """יצירת מוצר בקונימבו (POST /v1/items) באותו מבנה של ה-workflow ב-n8n."""
    token = require_env("KONIMBO_TOKEN")
    shipping_cost = args.shipping_cost.strip()
    shipping_id = SHIPPING_IDS.get(shipping_cost)

    icons = [{"image_title": "אייקון יבואן רשמי", "title": "יבואן רשמי",
              "url": "/", "visible": "1", "index-visible": "0"}]
    if shipping_cost == "":
        icons.append({"image_title": "free shipping", "title": "משלוח חינם",
                      "url": "/", "visible": "1", "index-visible": "0"})

    item = {
        "title": args.title,
        "code": args.code or args.title,  # code קובע upsert: אותו מק"ט = עדכון
        "price": args.price,
        "store_category_title": args.category,  # חייב להתאים בדיוק לקטגוריה קיימת
        "brand": args.brand,
        "delivery_time": args.delivery_time,
        "warranty": args.warranty,
        "desc": args.desc,
        "visible": True,
        "zap_visable": True,  # האיות המקורי של קונימבו
        "set_icons": icons,
        "images": [{"url": image_url, "alt": args.title, "position": "1"}],
    }
    if shipping_id:
        item["shipping_option_ids"] = [shipping_id]
    else:
        print(f"אזהרה: עלות משלוח '{shipping_cost}' לא ממופה - יש להקצות משלוח ידנית")

    resp = requests.post(
        KONIMBO_ITEMS_URL,
        params={"token": token},
        json={"item": item},
        timeout=60,
    )
    if not resp.ok:
        sys.exit(f"קונימבו נכשל ({resp.status_code}): {resp.text}")
    return resp.json()


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")

    p = argparse.ArgumentParser(description="העלאת מוצר + תמונה לקונימבו")
    p.add_argument("image", help="שם קובץ בתוך תיקיית images (או נתיב מלא)")
    p.add_argument("--title", required=True, help="שם המוצר")
    p.add_argument("--category", required=True, help="קטגוריה (בדיוק כפי שקיימת בקונימבו)")
    p.add_argument("--brand", required=True, help="יצרן")
    p.add_argument("--price", required=True, help="מחיר צרכן כולל מע\"מ")
    p.add_argument("--delivery-time", default="", help="זמן אספקה")
    p.add_argument("--warranty", default="", help="אחריות")
    p.add_argument("--shipping-cost", default="",
                   help="עלות משלוח: ריק=חינם, 60, או 120")
    p.add_argument("--desc", default="", help="תיאור המוצר (HTML)")
    p.add_argument("--code", default="", help="מק\"ט (ברירת מחדל: שם המוצר)")
    p.add_argument("--crop", action="store_true", help="חיתוך למרכז במקום ריפוד לבן")
    p.add_argument("--dry-run", action="store_true",
                   help="רק אופטימיזציה ושמירה מקומית, בלי העלאה")
    args = p.parse_args()

    src = Path(args.image)
    if not src.is_absolute() and not src.exists():
        src = IMAGES_DIR / args.image
    if not src.exists():
        sys.exit(f"הקובץ לא נמצא: {src}")

    print(f"[1/4] מעבד תמונה: {src.name}")
    webp = optimize_image(src, crop=args.crop)
    print(f"      {src.stat().st_size / 1024:.0f}KB -> {len(webp) / 1024:.0f}KB (WebP 1000x1000)")

    if args.dry_run:
        out = src.with_suffix(".webp")
        out = out.with_name(out.stem + "_optimized.webp")
        out.write_bytes(webp)
        print(f"dry-run: נשמר ב-{out}")
        return

    print("[2/4] מעלה ל-Cloudinary...")
    image_url = upload_to_cloudinary(webp, public_id=src.stem)
    print(f"[3/4] כתובת התמונה: {image_url}")

    print("[4/4] יוצר מוצר בקונימבו...")
    result = create_konimbo_item(args, image_url)
    print("המוצר נוצר:", result)


if __name__ == "__main__":
    main()
