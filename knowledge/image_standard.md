# Product image standard — Legacy Audio

Daniel's requirement, in his words: one clean image, white background, the product seen from
the front (or the angle that flatters it most — ~90% of the time that is the front), high
quality, and above all **of the exact product being uploaded — not another model or another
series in the same line.** A wrong-model image is worse than no image.

## Hard gates (an image that fails any of these is rejected)
1. **Exact model match.** Evidence is required and recorded in `research.json`:
   - the source page is the product page of exactly this model (title/URL/heading name the model), and
   - the image is the product image of that page (not a related product / "you may also like"), and
   - visible distinguishing features match (driver count/layout, ports, knobs, display, finish,
     size class). Series siblings (e.g. 5.1 vs 5.2, Mk II vs Mk III, 6" vs 8") are the #1 trap.
2. **Resolution:** source shortest side ≥ 800px (`img-fetch` marks smaller as `too_small`).
3. **Format accepted by Konimbo:** we always deliver JPEG (Konimbo does not accept WebP).
4. **No watermark, no text overlay, no retailer logo, no collage, no lifestyle/room scene.**
5. **Whole product visible, not cropped, not a detail/close-up.**

## Preferences (in order)
1. White / transparent background, front view.
2. Front 3/4 view if the front view is not available or clearly less flattering.
3. Colour/finish matching the sheet (if the sheet names a finish, the image must show it).

## Source priority
1. Manufacturer's official product page (`page-images`) — known domains in `brands.md`.
2. Manufacturer press/media kit or Israeli importer page.
3. Large authorised retailers with clean packshots (e.g. Crutchfield, Thomann, B&H, Richer Sounds, Audio Advice).
4. Google Images via SerpApi (`serp-images`) — only to discover pages; the page itself must still prove the model.

## Processing (done by `kon.py img-process`, never by hand)
EXIF rotate → flatten transparency on white → trim white margins → pad to square on white
with 6% margin → 1000×1000 → JPEG q92. Warnings to act on:
- `background_not_white` — prefer another candidate; accept only if nothing clean exists and say so.
- `upscaled` — source too small after trim; look for a bigger one.

## If no image passes
Do not upload a "close enough" image. Upload without images, mark `no_verified_image`, and
the final report lists it for Daniel with the best candidates found.
