"""Render the PWA icon at the sizes the manifest + iOS need.

Run-once helper: produces icon-192.png, icon-512.png, icon-512-maskable.png,
and apple-touch-icon.png in client/public/. The output should be checked
into git so production builds don't need PIL.

Run from the repo root:
    .venv/bin/python client/scripts/build-icons.py

The visual design intentionally mirrors public/icon.svg — a felt-green
rounded square with an off-white playing card and a centered ace of spades.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
FELT = (7, 58, 35, 255)        # #073a23
CARD = (245, 245, 241, 255)    # off-white
INK = (12, 42, 29, 255)        # very dark green (treats as black on the card)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort serif font; fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width=0):
    """Pillow's rounded_rectangle is fine but takes a bbox tuple — wrap to
    a clearer signature."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill,
                           outline=outline, width=width)


def _draw_spade(draw: ImageDraw.ImageDraw, cx: float, cy: float, h: float, fill):
    """Spade roughly h tall, centered on (cx, cy). Two ovals + a triangle stem."""
    # Two lobes: tweak parameters to match the SVG glyph.
    lobe_w = h * 0.42
    lobe_h = h * 0.55
    lobe_y = cy - h * 0.05
    # Left lobe
    draw.ellipse(
        (cx - lobe_w * 0.95, lobe_y - lobe_h / 2,
         cx + 0.05 * lobe_w, lobe_y + lobe_h / 2),
        fill=fill,
    )
    # Right lobe
    draw.ellipse(
        (cx - 0.05 * lobe_w, lobe_y - lobe_h / 2,
         cx + lobe_w * 0.95, lobe_y + lobe_h / 2),
        fill=fill,
    )
    # Triangle pointing up that joins the two lobes into a heart.
    draw.polygon(
        [
            (cx, cy - h * 0.5),
            (cx - lobe_w * 0.95, lobe_y),
            (cx + lobe_w * 0.95, lobe_y),
        ],
        fill=fill,
    )
    # Stem (small triangle at the bottom).
    stem_w = h * 0.16
    stem_top = cy + lobe_h * 0.45
    stem_bottom = cy + lobe_h * 0.65
    draw.polygon(
        [
            (cx - stem_w, stem_bottom),
            (cx + stem_w, stem_bottom),
            (cx, stem_top),
        ],
        fill=fill,
    )


def _draw_card(canvas: Image.Image, *, side: int, safe_pad: int = 0) -> Image.Image:
    """Paint the icon onto a fresh canvas. `safe_pad` shrinks the card
    inset from the edges so a maskable icon's safe area covers the
    important glyphs."""
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Felt background fills the entire icon (so PWA "any" icon works on
    # platforms that don't honor maskable). Corner radius scales with size.
    bg_radius = int(side * 0.18)
    _rounded_rect(draw, (0, 0, side, side), bg_radius, fill=FELT)

    # Card placement — leave a margin and respect the safe-area padding.
    margin = int(side * 0.18) + safe_pad
    card_box = (margin, int(side * 0.14) + safe_pad,
                side - margin, side - int(side * 0.14) - safe_pad)
    card_radius = max(8, int(side * 0.05))
    _rounded_rect(draw, card_box, card_radius, fill=CARD,
                  outline=INK, width=max(2, int(side * 0.01)))

    # Tilt the card slightly: paste the card onto a rotated transparent canvas.
    # The simplest way: render as-is (no rotation) for raster cleanliness.
    # The SVG keeps the artistic tilt; the PNG icons stay upright for
    # maximum legibility at small sizes.

    # Big spade in the middle of the card.
    cx = (card_box[0] + card_box[2]) / 2
    cy = (card_box[1] + card_box[3]) / 2
    spade_h = (card_box[3] - card_box[1]) * 0.45
    _draw_spade(draw, cx, cy + spade_h * 0.05, spade_h, fill=INK)

    # Top-left and bottom-right "A". Bottom-right is rotated 180°.
    rank_size = int((card_box[3] - card_box[1]) * 0.16)
    font = _load_font(rank_size)
    pad_x = int((card_box[2] - card_box[0]) * 0.08)
    pad_y = int((card_box[3] - card_box[1]) * 0.05)
    draw.text(
        (card_box[0] + pad_x, card_box[1] + pad_y), "A",
        fill=INK, font=font,
    )
    # Bottom-right rotated rank — render to a small image then paste flipped.
    rank_img = Image.new("RGBA", (rank_size * 2, rank_size * 2), (0, 0, 0, 0))
    rank_draw = ImageDraw.Draw(rank_img)
    rank_draw.text((0, 0), "A", fill=INK, font=font)
    rank_rot = rank_img.rotate(180, resample=Image.Resampling.BICUBIC)
    img.alpha_composite(
        rank_rot,
        dest=(card_box[2] - rank_size * 2 - pad_x,
              card_box[3] - rank_size * 2 - pad_y),
    )

    canvas.alpha_composite(img)
    return canvas


def render(side: int, *, maskable: bool = False) -> Image.Image:
    """Build a single icon at the requested size."""
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    safe_pad = int(side * 0.10) if maskable else 0
    return _draw_card(canvas, side=side, safe_pad=safe_pad)


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
        ("apple-touch-icon.png", 180, False),
        ("favicon-32.png", 32, False),
    ]
    for name, size, maskable in targets:
        out = PUBLIC_DIR / name
        img = render(size, maskable=maskable)
        img.save(out, "PNG", optimize=True)
        print(f"wrote {out.relative_to(PUBLIC_DIR.parent.parent)} ({size}x{size}"
              + (", maskable" if maskable else "") + ")")


if __name__ == "__main__":
    main()
