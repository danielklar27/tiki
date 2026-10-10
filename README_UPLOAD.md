# העלאת מחירונים לקונימבו — Legacy Audio

מחירון ספק → שיטס (אישור שלך) → מחקר מוצר + תמונה מאומתת של הדגם המדויק + תיאור ומפרט →
העלאה מוסתרת → QA עצמאי → פרסום מה שעבר → דוח.

## הפעלה
בסשן Claude Code על הריפו הזה: מצרפים את קובץ המחירון וכותבים `/upload-pricelist`.
התערבות שלך: רק אישור השיטס.

## חלקים
| קובץ | תפקיד |
|---|---|
| `.claude/skills/upload-pricelist/SKILL.md` | המנהל — מריץ את כל השלבים |
| `.claude/agents/pricelist-agent.md` | מחירון → שיטס + שאלות |
| `.claude/agents/product-uploader.md` | מחקר, תמונה, תיאור, העלאה מוסתרת, תיקונים |
| `.claude/agents/product-qa.md` | בדיקה עצמאית של כל מוצר שעלה |
| `tools/kon.py` | כלים קבועים: API קונימבו, עיבוד תמונות, Cloudinary, דוח |
| `knowledge/` | ידע מצטבר: API, תקן תמונות, מותגים, לקחים |
| `runs/<run>/` | היסטוריית ריצות (JSON ודוחות) |

## הגדרה חד-פעמית
1. **רשת:** הגדרות הסביבה ← Network access ← Full (צריך גישה לאתרי יצרנים משתנים).
2. **משתני סביבה** (בהגדרות הסביבה, לא בקבצים):
   `KONIMBO_TOKEN`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`,
   ואופציונלי `SERPAPI_KEY`.
3. **טוקן קונימבו** עם קריאה + כתיבה למוצרים, וקריאה לקטגוריות.
4. בדיקה: `python tools/kon.py env-check`.
