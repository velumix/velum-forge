r"""High-Resolution Graphic, Signage, Awning, Pavement & Interior Texture Generator (Iteration 2 — Photorealistic Upgrade).

Improvements over Iteration 1:
  - Deeper authentic Miami forest-emerald `awning_news_cafe.png` (`#084A34`) with bold legible script logo
  - Seamless matching `road_asphalt_plain.png` (identical aggregate grain & lane stripes to `road_ocean_dr.png`)
  - Authentic weathered yellow curb texture with crisp stenciled `VALET ONLY` text (`curb_valet_only.png`)
  - Photorealistic `interior_news_cafe.png` (vintage Miami sepia/B&W photography gallery, backlit bar bottles, warm sconces — zero cartoonish icons!)
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

THIS_DIR = Path(__file__).resolve().parent
OUT_DIR = THIS_DIR / "textures_src"


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fdir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for n in names:
        p = fdir / n
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_center(draw: ImageDraw.ImageDraw, cx: float, cy: float, text: str, font, fill) -> None:
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((cx - tw * 0.5 - bb[0], cy - th * 0.5 - bb[1]), text, font=font, fill=fill)


def _add_fabric_weave(arr: np.ndarray, strength: float = 5.5, stripe_step: int = 0) -> np.ndarray:
    h, w, _ = arr.shape
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    weave = (np.sin(x * 1.15) * 0.5 + np.sin(y * 1.35) * 0.5) * strength
    rng = np.random.default_rng(42)
    grain = rng.normal(0.0, strength * 0.35, (h, w))
    out = arr.astype(np.float32) + (weave + grain)[..., None]
    if stripe_step > 0:
        seam = ((x % stripe_step) < 3).astype(np.float32) * (-12.0)
        out += seam[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def gen_awning_news_cafe() -> None:
    w, h = 2048, 512
    # Deep saturated Miami forest-emerald canvas (stays rich dark emerald even under bright AgX midday sun!)
    base = np.zeros((h, w, 3), dtype=np.uint8)
    base[..., 0] = 2
    base[..., 1] = 38
    base[..., 2] = 24
    grad = np.linspace(1.18, 0.84, h, dtype=np.float32)[:, None, None]
    arr = np.clip(base.astype(np.float32) * grad, 0, 255).astype(np.uint8)
    arr = _add_fabric_weave(arr, strength=3.5, stripe_step=256)

    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)

    # Crisp valance top fold seam at y = 325
    draw.rectangle([0, 320, w, 328], fill=(1, 22, 14))
    for dy in range(1, 14):
        draw.line([(0, 328 + dy), (w, 328 + dy)], fill=(2, 24 + dy, 15 + dy // 2))

    # Crisp white fabric binding along bottom edge
    draw.rectangle([0, h - 18, w, h], fill=(242, 244, 240))
    draw.rectangle([0, h - 22, w, h - 18], fill=(1, 18, 11))

    # Signature bold cursive white "News Cafe" centered cleanly in valance
    f_script = _font(["segoesc.ttf", "BRUSHSCI.TTF", "georgiai.ttf", "timesbi.ttf"], 118)
    _text_center(draw, w * 0.5 + 3, 412 + 3, "News Cafe", f_script, (1, 12, 8))
    _text_center(draw, w * 0.5, 412, "News Cafe", f_script, (250, 252, 248))
    img.save(OUT_DIR / "awning_news_cafe.png")


def gen_awning_hotel_800() -> None:
    """Warm tan & espresso striped awning for 'the hotel @ 800' on 8th Street (Photo 5)."""
    w, h = 1024, 512
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        if y < 332:
            band = (y // 26) % 2
            col = (140, 108, 82) if band == 0 else (104, 76, 55)
        else:
            col = (118, 88, 66)
        arr[y, :] = col
    arr = _add_fabric_weave(arr, strength=5.0, stripe_step=0)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 328, w, 336], fill=(68, 48, 34))
    draw.rectangle([0, h - 14, w, h], fill=(64, 46, 32))

    f_lbl = _font(["segoeui.ttf", "arialbd.ttf"], 76)
    _text_center(draw, w * 0.5 + 2, 420 + 2, "the hotel @ 800", f_lbl, (48, 32, 20))
    _text_center(draw, w * 0.5, 420, "the hotel @ 800", f_lbl, (246, 242, 234))
    img.save(OUT_DIR / "awning_hotel_800.png")


def gen_host_podium() -> None:
    w, h = 512, 768
    rng = np.random.default_rng(7)
    base = np.full((h, w, 3), (52, 56, 62), dtype=np.float32)
    arr = np.clip(base + rng.normal(0.0, 5.0, (h, w, 1)), 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, w - 16, h - 16], outline=(28, 32, 36), width=14)
    draw.rectangle([38, 38, w - 38, h - 38], outline=(76, 80, 86), width=4)

    cx, cy, sz = w // 2, h // 2 - 20, 128
    draw.rounded_rectangle([cx - sz, cy - sz, cx + sz, cy + sz], radius=14, fill=(240, 242, 244), outline=(24, 28, 32), width=6)
    for ang_deg in range(0, 360, 45):
        a = math.radians(ang_deg)
        draw.line([(cx, cy), (cx + int(86 * math.cos(a)), cy + int(86 * math.sin(a)))], fill=(32, 36, 42), width=6)
    draw.ellipse([cx - 58, cy - 58, cx + 58, cy + 58], outline=(32, 36, 42), width=8, fill=(240, 242, 244))
    _text_center(draw, cx, cy, "NC", _font(["georgiai.ttf", "timesbi.ttf"], 46), (20, 24, 28))
    _text_center(draw, cx, cy + sz + 44, "NEWS CAFE", _font(["georgia.ttf", "arialbd.ttf"], 32), (228, 232, 236))
    _text_center(draw, cx, cy + sz + 82, "800 OCEAN DRIVE", _font(["arial.ttf"], 22), (178, 184, 190))
    img.save(OUT_DIR / "host_podium_front.png")


def gen_menu_board() -> None:
    w, h = 512, 768
    img = Image.new("RGB", (w, h), (242, 238, 228))
    draw = ImageDraw.Draw(img)
    draw.rectangle([18, 18, w - 18, 128], fill=(9, 64, 45))
    _text_center(draw, w * 0.5, 58, "News Cafe", _font(["georgiai.ttf", "timesbi.ttf"], 54), (248, 246, 240))
    _text_center(draw, w * 0.5, 104, "SOUTH BEACH  •  EST. 1988  •  800 OCEAN DR", _font(["arialbd.ttf"], 18), (206, 224, 212))

    # Realistic food photo vignettes
    draw.rounded_rectangle([296, 152, 482, 294], radius=6, fill=(142, 92, 52), outline=(92, 62, 38), width=3)
    draw.ellipse([334, 170, 444, 276], fill=(238, 232, 220), outline=(170, 154, 134), width=3)
    draw.ellipse([352, 192, 412, 250], fill=(216, 148, 52))
    draw.ellipse([386, 188, 430, 232], fill=(236, 192, 78))
    draw.ellipse([362, 222, 404, 260], fill=(82, 138, 64))

    draw.rounded_rectangle([296, 316, 482, 458], radius=6, fill=(52, 84, 62), outline=(34, 58, 42), width=3)
    draw.ellipse([338, 336, 440, 436], fill=(244, 240, 234))
    draw.ellipse([356, 354, 422, 418], fill=(196, 62, 46))
    draw.ellipse([372, 370, 406, 404], fill=(236, 204, 144))

    f_sec = _font(["arialbd.ttf"], 21)
    f_item = _font(["arial.ttf"], 15)
    sections = [
        ("ALL-DAY BREAKFAST", 156, ["Big Breakfast ........ 22", "Eggs Benedict ........ 21", "Smoked Salmon ........ 24", "Avocado Toast ........ 18", "Pina Colada Pancakes . 19"]),
        ("LUNCH & DINNER", 342, ["Tony's Tomato Soup ... 14", "News Cafe Burger ..... 23", "Mahi-Mahi Tacos ...... 25", "Chicken Parmigiana ... 28", "Truffle Fries ........ 13"]),
        ("COCKTAILS & ESPRESSO", 530, ["Ocean Dr Mojito ...... 18", "Frozzie Rossie ....... 19", "Espresso Martini ..... 20", "Cuban Cafecito ........ 6", "Fresh Mimosa ......... 15"]),
    ]
    for title, y0, items in sections:
        draw.text((30, y0), title, font=f_sec, fill=(10, 66, 46))
        draw.line([(30, y0 + 27), (274, y0 + 27)], fill=(182, 168, 140), width=2)
        for idx, line in enumerate(items):
            draw.text((32, y0 + 35 + idx * 24), line, font=f_item, fill=(42, 44, 48))

    draw.rectangle([18, h - 54, w - 18, h - 18], fill=(224, 218, 204))
    _text_center(draw, w * 0.5, h - 36, "WELCOME — PLEASE SEE HOST TO BE SEATED", _font(["arialbd.ttf"], 15), (36, 44, 40))
    img.save(OUT_DIR / "menu_board_sheet.png")


def gen_street_signs() -> None:
    # 1. ONE WAY
    im = Image.new("RGB", (768, 256), (242, 244, 245))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, 760, 248], radius=22, fill=(22, 24, 26), outline=(242, 244, 245), width=8)
    d.polygon([(54, 128), (218, 44), (218, 92), (712, 92), (712, 164), (218, 164), (218, 212)], fill=(244, 246, 248))
    _text_center(d, 448, 128, "ONE WAY", _font(["arialbd.ttf"], 84), (18, 20, 22))
    im.save(OUT_DIR / "sign_one_way.png")

    # 2. STOP HERE FOR [Pedestrian]
    im = Image.new("RGB", (512, 512), (242, 244, 246))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([12, 12, 500, 500], radius=28, fill=(242, 244, 246), outline=(26, 28, 30), width=14)
    cx, cy, r = 256, 120, 84
    oct_pts = [(cx + r * math.cos(math.radians(22.5 + 45 * k)), cy + r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    d.polygon(oct_pts, fill=(196, 28, 32), outline=(244, 244, 244))
    _text_center(d, cx, cy, "STOP", _font(["arialbd.ttf"], 50), (248, 248, 248))
    _text_center(d, 214, 265, "HERE", _font(["arialbd.ttf"], 72), (22, 24, 26))
    _text_center(d, 198, 348, "FOR", _font(["arialbd.ttf"], 72), (22, 24, 26))
    d.polygon([(70, 425), (168, 385), (168, 410), (312, 410), (312, 440), (168, 440), (168, 465)], fill=(22, 24, 26))
    d.ellipse([362, 232, 404, 274], fill=(22, 24, 26))
    d.line([(383, 278), (383, 355)], fill=(22, 24, 26), width=22)
    d.line([(383, 295), (344, 342)], fill=(22, 24, 26), width=14)
    d.line([(383, 295), (422, 336)], fill=(22, 24, 26), width=14)
    d.line([(383, 350), (350, 434)], fill=(22, 24, 26), width=16)
    d.line([(383, 350), (420, 434)], fill=(22, 24, 26), width=16)
    im.save(OUT_DIR / "sign_stop_ped.png")

    # 3. NO PARKING / VALET ONLY
    im = Image.new("RGB", (384, 512), (242, 244, 245))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, 374, 502], radius=20, fill=(242, 244, 245), outline=(186, 32, 38), width=12)
    _text_center(d, 192, 94, "NO", _font(["arialbd.ttf"], 84), (186, 32, 38))
    _text_center(d, 192, 178, "PARKING", _font(["arialbd.ttf"], 60), (186, 32, 38))
    _text_center(d, 192, 250, "VALET", _font(["arialbd.ttf"], 54), (186, 32, 38))
    _text_center(d, 192, 314, "LOADING", _font(["arialbd.ttf"], 48), (186, 32, 38))
    _text_center(d, 192, 374, "ZONE", _font(["arialbd.ttf"], 48), (186, 32, 38))
    d.polygon([(70, 444), (120, 420), (120, 436), (264, 436), (264, 420), (314, 444), (264, 468), (264, 452), (120, 452), (120, 468)], fill=(186, 32, 38))
    im.save(OUT_DIR / "sign_no_parking.png")

    # 4. Street Blades
    for fname, txt, fsz in [("sign_street_ocean.png", "OCEAN DR", 108), ("sign_street_8th.png", "8th ST", 114)]:
        im = Image.new("RGB", (768, 224), (16, 108, 66))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([10, 10, 758, 214], radius=18, fill=(16, 108, 66), outline=(242, 246, 242), width=10)
        _text_center(d, 384, 112, txt, _font(["arialbd.ttf"], fsz), (246, 248, 246))
        im.save(OUT_DIR / fname)

    # 5. Blue ADA plaque
    im = Image.new("RGB", (256, 320), (20, 86, 168))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, 248, 312], radius=14, fill=(20, 86, 168), outline=(240, 244, 248), width=8)
    d.ellipse([112, 46, 148, 82], fill=(244, 246, 248))
    d.arc([72, 132, 174, 234], start=35, end=275, fill=(244, 246, 248), width=14)
    d.line([(126, 86), (126, 164), (174, 164), (190, 218)], fill=(244, 246, 248), width=14)
    _text_center(d, 128, 272, "ACCESSIBLE", _font(["arialbd.ttf"], 28), (244, 246, 248))
    im.save(OUT_DIR / "sign_ada_blue.png")

    # 6. Red FDC plaque
    im = Image.new("RGB", (256, 256), (198, 34, 34))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, 248, 248], radius=16, fill=(198, 34, 34), outline=(244, 244, 244), width=8)
    _text_center(d, 128, 128, "FDC", _font(["arialbd.ttf"], 94), (248, 248, 248))
    im.save(OUT_DIR / "sign_fdc_red.png")

    # 7. 804 Ocean Dr menu sign (deep matte charcoal-black w/ warm brass trim matching Photo 3)
    im = Image.new("RGB", (512, 512), (10, 12, 11))
    d = ImageDraw.Draw(im)
    d.rectangle([16, 16, 496, 496], outline=(168, 142, 86), width=6)
    _text_center(d, 256, 136, "OH! MEXICO", _font(["georgia.ttf", "arialbd.ttf"], 56), (240, 234, 218))
    _text_center(d, 256, 214, "804 OCEAN DRIVE", _font(["arialbd.ttf"], 30), (196, 156, 82))
    _text_center(d, 256, 298, "TACOS  •  TEQUILA", _font(["arialbd.ttf"], 32), (228, 232, 224))
    _text_center(d, 256, 384, "PATIO DINING", _font(["arial.ttf"], 28), (164, 186, 136))
    im.save(OUT_DIR / "sign_804_menu.png")

    # 8. Yellow Ocean Drive Curb Stencil: Bold crisp "VALET ONLY" (clearly legible in Photos 2, 3, 4!)
    cw, ch = 1024, 256
    rng_c = np.random.default_rng(314)
    cbase = np.full((ch, cw, 3), (222, 174, 38), dtype=np.float32) + rng_c.normal(0.0, 6.0, (ch, cw, 1))
    cim = Image.fromarray(np.clip(cbase, 0, 255).astype(np.uint8), mode="RGB")
    cd = ImageDraw.Draw(cim)
    _text_center(cd, cw * 0.5, ch * 0.50, "VALET ONLY", _font(["arialbd.ttf"], 156), (14, 14, 14))
    cfinal = np.asarray(cim, dtype=np.float32) + rng_c.normal(0.0, 4.0, (ch, cw, 1))
    Image.fromarray(np.clip(cfinal, 0, 255).astype(np.uint8), mode="RGB").save(OUT_DIR / "curb_valet_only.png")


def _make_asphalt_base(w: int, h: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = np.full((h, w, 3), (154, 155, 151), dtype=np.float32)
    fine = rng.normal(0.0, 9.0, (h, w, 1))
    coarse_sm = rng.normal(0.0, 10.0, (256, 256))
    coarse_im = Image.fromarray(np.clip(128 + coarse_sm * 2.5, 0, 255).astype(np.uint8)).resize((w, h), Image.Resampling.BILINEAR)
    coarse = (np.asarray(coarse_im, dtype=np.float32) - 128.0) * 0.34
    x_norm = np.linspace(0.0, 1.0, w)[None, :]
    wheel = -10.0 * (np.exp(-((x_norm - 0.34) / 0.08) ** 2) + np.exp(-((x_norm - 0.66) / 0.08) ** 2))
    return np.clip(base + fine + coarse[..., None] + wheel[..., None], 0, 255).astype(np.uint8)


def gen_road_textures() -> None:
    w, h = 2048, 2048
    # 1. Seamless plain Ocean Drive / 8th St asphalt with matching crisp white lane edge stripes!
    plain_arr = _make_asphalt_base(w, h, 102)
    pimg = Image.fromarray(plain_arr, mode="RGB")
    pd = ImageDraw.Draw(pimg)
    pd.rectangle([72, 0, 112, h], fill=(224, 226, 222))
    pd.rectangle([w - 112, 0, w - 72, h], fill=(224, 226, 222))
    pimg.save(OUT_DIR / "road_asphalt_plain.png")

    # 2. Hero Ocean Drive asphalt tile with 'Ocean Dr' street stencil & turn arrow (identical base grain -> ZERO seam!)
    arr = _make_asphalt_base(w, h, 101)
    img = Image.fromarray(arr, mode="RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([72, 0, 112, h], fill=(224, 226, 222))
    d.rectangle([w - 112, 0, w - 72, h], fill=(224, 226, 222))

    txt_im = Image.new("RGBA", (1024, 340), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt_im)
    _text_center(td, 512, 170, "Ocean Dr", _font(["arialbd.ttf"], 210), (226, 228, 224, 212))
    txt_rot = txt_im.rotate(90, expand=True).resize((440, 1100), Image.Resampling.LANCZOS)
    img.paste(txt_rot, (w // 2 - 220, 760), txt_rot)

    ax = w // 2
    d.rectangle([ax - 36, 260, ax + 36, 610], fill=(226, 228, 224))
    d.polygon([(ax, 120), (ax - 120, 290), (ax + 120, 290)], fill=(226, 228, 224))
    d.rectangle([ax - 230, 390, ax - 20, 455], fill=(226, 228, 224))
    d.polygon([(ax - 330, 422), (ax - 210, 342), (ax - 210, 502)], fill=(226, 228, 224))

    rng = np.random.default_rng(109)
    final = np.asarray(img, dtype=np.float32) + rng.normal(0.0, 5.5, (h, w, 1))
    Image.fromarray(np.clip(final, 0, 255).astype(np.uint8)).save(OUT_DIR / "road_ocean_dr.png")

    # 3. Emerald-green bike lane
    bw, bh = 512, 1024
    rng2 = np.random.default_rng(202)
    bbase = np.full((bh, bw, 3), (54, 122, 86), dtype=np.float32) + rng2.normal(0.0, 7.0, (bh, bw, 1))
    bimg = Image.fromarray(np.clip(bbase, 0, 255).astype(np.uint8))
    bd = ImageDraw.Draw(bimg)
    bd.rectangle([0, 0, 26, bh], fill=(236, 238, 234))
    bd.rectangle([bw - 26, 0, bw, bh], fill=(236, 238, 234))
    cx, cy = bw // 2, bh // 2
    bd.ellipse([cx - 56, cy + 72, cx + 56, cy + 184], outline=(238, 242, 238), width=14)
    bd.ellipse([cx - 56, cy - 184, cx + 56, cy - 72], outline=(238, 242, 238), width=14)
    bd.line([(cx, cy + 128), (cx, cy - 128)], fill=(238, 242, 238), width=14)
    bd.line([(cx - 48, cy - 30), (cx + 48, cy - 30)], fill=(238, 242, 238), width=14)
    bd.polygon([(cx, cy - 330), (cx - 64, cy - 236), (cx + 64, cy - 236)], fill=(238, 242, 238))
    bimg.save(OUT_DIR / "road_bike_lane.png")


def gen_interior_backdrop() -> None:
    """Photorealistic warm retro News Cafe interior wall: sepia Miami Deco photos, backlit mahogany bar & warm brass sconces."""
    w, h = 2048, 1024
    rng = np.random.default_rng(88)
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(h):
        t = y / h
        arr[y, :, 0] = 68 * (1 - t) + 26 * t
        arr[y, :, 1] = 48 * (1 - t) + 18 * t
        arr[y, :, 2] = 34 * (1 - t) + 12 * t
    arr += rng.normal(0.0, 3.0, (h, w, 1))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
    d = ImageDraw.Draw(img)

    # Rich dark mahogany wainscoting & brass picture rail
    d.rectangle([0, 620, w, h], fill=(30, 18, 12))
    d.rectangle([0, 610, w, 626], fill=(110, 76, 46))
    for px in range(40, w, 160):
        d.rectangle([px, 650, px + 120, 960], outline=(52, 32, 22), width=6)

    # Left half: Antique smoked-mirror mahogany back-bar cabinet (3D bottles & shelves sit in front of this!)
    d.rectangle([60, 120, 860, 606], fill=(24, 15, 10), outline=(74, 48, 28), width=12)
    for col_x in range(88, 840, 186):
        # Warm antiqued bronze mirror panes with subtle vertical warm cove glow
        d.rectangle([col_x, 148, col_x + 166, 580], fill=(44, 31, 20), outline=(66, 44, 26), width=4)
        for ry in range(160, 560, 130):
            d.rectangle([col_x + 10, ry, col_x + 156, ry + 18], fill=(82, 56, 30))

    # Right half: Authentic vintage framed sepia/B&W Miami Beach photography gallery (Art Deco facades, palms, ocean!)
    frame_specs = [
        (940, 130, 210, 250, "deco"),
        (1190, 160, 230, 210, "palm"),
        (1460, 120, 200, 260, "ocean"),
        (1700, 155, 225, 215, "deco"),
        (960, 410, 240, 170, "ocean"),
        (1240, 400, 200, 180, "palm"),
        (1490, 415, 240, 165, "deco"),
        (1760, 405, 190, 175, "palm"),
    ]
    for fx, fy, fw, fh, motif in frame_specs:
        d.rectangle([fx, fy, fx + fw, fy + fh], fill=(16, 12, 10), outline=(128, 102, 62), width=6)
        d.rectangle([fx + 14, fy + 14, fx + fw - 14, fy + fh - 14], fill=(186, 176, 160))
        px0, py0, px1, py1 = fx + 24, fy + 24, fx + fw - 24, fy + fh - 24
        d.rectangle([px0, py0, px1, py1], fill=(124, 114, 102))
        if motif == "deco":
            d.rectangle([px0, py0 + (py1 - py0) // 2, px1, py1], fill=(76, 68, 60))
            for k in range(3):
                bx0 = px0 + 12 + k * ((px1 - px0 - 24) // 3)
                d.rectangle([bx0, py0 + 24 + (k % 2) * 18, bx0 + 36, py1], fill=(48, 42, 38))
        elif motif == "palm":
            d.rectangle([px0, py0 + int((py1 - py0) * 0.65), px1, py1], fill=(78, 70, 62))
            d.line([(px0 + 40, py1), (px0 + 62, py0 + 34)], fill=(32, 28, 24), width=6)
            for ang in (-2.4, -1.7, -0.9, -0.2, 0.5):
                d.line([(px0 + 62, py0 + 34), (px0 + 62 + int(42 * math.cos(ang)), py0 + 34 + int(24 * math.sin(ang)))], fill=(32, 28, 24), width=4)
        else:
            d.rectangle([px0, py0 + int((py1 - py0) * 0.55), px1, py1], fill=(88, 78, 68))
            d.pieslice([px0 + 20, py0 + 30, px1 - 20, py1 - 10], 180, 360, fill=(46, 40, 36))

    # Warm amber brass wall sconce glow pools
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for sx in (460, 1170, 1680):
        gd.ellipse([sx - 130, 190, sx + 130, 450], fill=(255, 194, 104, 105))
        gd.ellipse([sx - 30, 290, sx + 30, 350], fill=(255, 240, 200, 230))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    img.save(OUT_DIR / "interior_news_cafe.png")


def gen_gallery_art_atlas(*, overwrite: bool = False) -> None:
    """Generate 8 individual museum-grade South Beach / Miami Art Deco fine-art paintings & sepia prints (4x2 grid, 2048x1024).

    Mounted inside 8 REAL 3D modeled beveled frames + 3D museum mat boards on News Cafe's interior gallery wall!
    Preserves custom museum-grade artwork if `gallery_art_atlas.png` already exists unless `overwrite=True`.
    """
    out_path = OUT_DIR / "gallery_art_atlas.png"
    if out_path.exists() and not overwrite:
        return
    w, h = 2048, 1024
    tw, th = 512, 512
    atlas = Image.new("RGB", (w, h), (235, 228, 214))

    def _tile(col_i: int, row_i: int, draw_fn) -> None:
        rng = np.random.default_rng(800 + row_i * 4 + col_i)
        sub = Image.new("RGB", (tw, th), (225, 215, 198))
        draw_fn(sub, rng)
        # Subtle archival cotton-paper fine grain & soft vignette
        arr = np.asarray(sub, dtype=np.float32)
        yy, xx = np.mgrid[0:th, 0:tw]
        rx = (xx - tw * 0.5) / (tw * 0.5)
        ry = (yy - th * 0.5) / (th * 0.5)
        vig = np.clip(1.0 - 0.14 * (rx * rx + ry * ry), 0.78, 1.0)
        arr = arr * vig[..., None] + rng.normal(0.0, 2.8, (th, tw, 1))
        atlas.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (col_i * tw, row_i * th))

    def _grad(sub: Image.Image, c_top: tuple, c_bot: tuple, y0: int = 0, y1: int = th) -> None:
        arr = np.asarray(sub, dtype=np.float32).copy()
        for y in range(max(0, y0), min(th, y1)):
            t = (y - y0) / max(1, y1 - y0 - 1)
            arr[y, :, 0] = c_top[0] * (1 - t) + c_bot[0] * t
            arr[y, :, 1] = c_top[1] * (1 - t) + c_bot[1] * t
            arr[y, :, 2] = c_top[2] * (1 - t) + c_bot[2] * t
        sub.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))

    def _draw_palm(d: ImageDraw.ImageDraw, bx: float, by: float, tx: float, ty: float, col: tuple, scale: float = 1.0) -> None:
        pts = []
        for k in range(14):
            t = k / 13.0
            cx = bx + (tx - bx) * (t ** 1.2) + 18 * scale * math.sin(t * math.pi)
            cy = by + (ty - by) * t
            pts.append((cx, cy))
        for k in range(len(pts) - 1):
            w_seg = max(3, int((13 - k * 0.65) * scale))
            d.line([pts[k], pts[k + 1]], fill=col, width=w_seg)
        # Graceful arched feathery fronds
        for ang_deg, flen in [(-165, 115), (-135, 130), (-100, 105), (-60, 110), (-25, 132), (10, 115), (38, 95), (-195, 92)]:
            a = math.radians(ang_deg)
            fpts = []
            for s in range(9):
                u = s / 8.0
                fx = tx + math.cos(a) * flen * scale * u
                fy = ty + math.sin(a) * flen * scale * u + 44 * scale * (u ** 2.1)
                fpts.append((fx, fy))
            d.line(fpts, fill=col, width=max(2, int(4 * scale)))
            for s in range(2, 9):
                px, py = fpts[s]
                d.line([(px, py), (px + math.cos(a + 0.9) * 14 * scale, py + 18 * scale)], fill=col, width=max(1, int(2 * scale)))

    # 1. Vintage Sepia Ocean Drive Art Deco Skyline & Palms
    def art_deco_sepia(sub, _rng):
        _grad(sub, (218, 204, 182), (242, 232, 212), 0, 340)
        _grad(sub, (152, 136, 116), (92, 80, 68), 340, th)
        d = ImageDraw.Draw(sub)
        # Stepped Art Deco hotel silhouette w/ eyebrow bands & flagpole spire
        d.rectangle([75, 165, 225, 385], fill=(122, 108, 94))
        d.rectangle([108, 120, 192, 165], fill=(104, 90, 78))
        d.line([(150, 75), (150, 120)], fill=(78, 66, 56), width=4)
        for ey in (205, 255, 305):
            d.rectangle([66, ey, 234, ey + 10], fill=(236, 226, 208))
            for wx in range(88, 210, 32):
                d.rectangle([wx, ey + 14, wx + 22, ey + 38], fill=(58, 48, 42))
        d.rectangle([240, 215, 420, 385], fill=(142, 128, 112))
        for ey in (245, 295, 340):
            d.rectangle([232, ey, 428, ey + 9], fill=(232, 222, 204))
            for wx in range(255, 405, 34):
                d.rectangle([wx, ey + 13, wx + 24, ey + 34], fill=(64, 54, 46))
        _draw_palm(d, 448, 495, 395, 185, (48, 40, 34), 0.95)
        _draw_palm(d, 52, 495, 82, 235, (64, 54, 46), 0.72)

    # 2. Miami Beach Atlantic Sunrise & Curved Coconut Palms (Warm Coastal Painting)
    def art_atlantic_sunrise(sub, _rng):
        _grad(sub, (98, 152, 188), (248, 202, 156), 0, 295)
        d = ImageDraw.Draw(sub)
        d.ellipse([205, 225, 315, 335], fill=(255, 232, 178))
        _grad(sub, (64, 138, 152), (32, 86, 108), 295, 415)
        _grad(sub, (224, 198, 162), (186, 156, 124), 415, th)
        # Shimmering sun reflection ripples on turquoise ocean
        for ry in range(304, 410, 12):
            rw = int(68 * (1.0 - (ry - 304) / 140.0) + 18)
            d.rectangle([260 - rw, ry, 260 + rw, ry + 4], fill=(252, 222, 168))
        _draw_palm(d, 95, 510, 175, 165, (28, 42, 36), 1.05)
        _draw_palm(d, 430, 510, 375, 220, (36, 52, 44), 0.78)

    # 3. Vintage 1930s South Beach Art Deco Travel Poster ("MIAMI BEACH")
    def art_deco_poster(sub, _rng):
        _grad(sub, (26, 92, 98), (236, 172, 136), 0, 330)
        _grad(sub, (18, 66, 74), (12, 44, 52), 330, th)
        d = ImageDraw.Draw(sub)
        # Art Deco sunburst rays
        for k in range(11):
            a = math.radians(-165 + k * 15)
            d.polygon([(256, 260), (256 + 320 * math.cos(a - 0.045), 260 + 320 * math.sin(a - 0.045)), (256 + 320 * math.cos(a + 0.045), 260 + 320 * math.sin(a + 0.045))], fill=(246, 212, 166))
        d.ellipse([186, 190, 326, 330], fill=(252, 228, 180))
        # Iconic pastel pink Art Deco tower foreground
        d.rectangle([168, 250, 344, 425], fill=(232, 164, 150))
        d.rectangle([205, 198, 307, 250], fill=(242, 184, 170))
        d.rectangle([238, 156, 274, 198], fill=(248, 228, 212))
        for y_b in (272, 314, 356):
            d.rectangle([156, y_b, 356, y_b + 10], fill=(248, 242, 232))
            d.rectangle([196, y_b + 12, 316, y_b + 34], fill=(24, 72, 78))
        d.rectangle([24, 24, tw - 24, th - 24], outline=(244, 226, 196), width=6)
        _text_center(d, 256, 466, "MIAMI BEACH", _font(["georgia.ttf", "arialbd.ttf"], 38), (248, 238, 218))

    # 4. Iconic South Beach Colorful Lifeguard Tower Painting
    def art_lifeguard_tower(sub, _rng):
        _grad(sub, (124, 192, 228), (218, 236, 244), 0, 325)
        _grad(sub, (46, 164, 168), (34, 134, 148), 325, 385)
        _grad(sub, (242, 224, 192), (214, 188, 152), 385, th)
        d = ImageDraw.Draw(sub)
        # Stilts & deck
        for sx in (185, 325):
            d.line([(sx, 330), (sx, 452)], fill=(122, 92, 68), width=12)
        d.line([(185, 340), (325, 442)], fill=(112, 84, 62), width=6)
        d.line([(325, 340), (185, 442)], fill=(112, 84, 62), width=6)
        d.rectangle([152, 316, 360, 336], fill=(244, 240, 232))
        # Coral & turquoise lifeguard cabin
        d.rectangle([188, 206, 324, 316], fill=(232, 98, 92))
        d.rectangle([208, 226, 304, 272], fill=(42, 68, 86))
        d.polygon([(160, 206), (256, 146), (352, 206)], fill=(42, 168, 156))
        d.rectangle([188, 282, 324, 294], fill=(248, 236, 112))
        # Red surf rescue buoy leaning against stairs
        d.ellipse([338, 250, 366, 314], fill=(214, 44, 48))

    # 5. Monochrome Fine-Art Photography: Palm Frond Canopy Study
    def art_bw_palm_study(sub, _rng):
        _grad(sub, (226, 222, 214), (178, 174, 166), 0, th)
        d = ImageDraw.Draw(sub)
        _draw_palm(d, 40, 510, 220, 140, (34, 34, 34), 1.45)
        _draw_palm(d, 480, 510, 340, 230, (68, 68, 68), 1.10)

    # 6. Vintage B&W News Cafe 1988 Corner Awning Archival Print
    def art_news_cafe_1988(sub, _rng):
        _grad(sub, (214, 208, 196), (176, 168, 156), 0, 240)
        _grad(sub, (132, 126, 118), (94, 88, 82), 240, th)
        d = ImageDraw.Draw(sub)
        # Building facade & 3 crisp horizontal breeze-block balcony bands
        d.rectangle([62, 86, 450, 410], fill=(228, 222, 210))
        for bz in (104, 174, 244):
            d.rectangle([52, bz, 460, bz + 34], fill=(244, 240, 232), outline=(146, 140, 130), width=3)
            for gx in range(64, 450, 20):
                d.ellipse([gx, bz + 10, gx + 10, bz + 22], fill=(122, 116, 108))
        # Classic dark awning + white script
        d.polygon([(52, 294), (460, 294), (478, 342), (34, 342)], fill=(38, 44, 40))
        _text_center(d, 256, 326, "News Cafe  •  1988", _font(["segoescb.ttf", "georgiai.ttf", "arialbd.ttf"], 28), (242, 240, 234))
        # Cafe tables silhouette beneath awning
        for tx in (110, 205, 305, 400):
            d.ellipse([tx - 24, 382, tx + 24, 396], fill=(230, 226, 218))
            d.line([(tx, 396), (tx, 448)], fill=(44, 42, 40), width=5)

    # 7. Warm Flamingo & Tropical Monstera Botanical Art Deco Painting
    def art_flamingo_deco(sub, _rng):
        _grad(sub, (246, 224, 216), (236, 186, 178), 0, th)
        d = ImageDraw.Draw(sub)
        d.ellipse([76, 76, 436, 436], fill=(250, 242, 232))
        d.arc([64, 64, 448, 448], 0, 360, fill=(198, 152, 82), width=5)
        # Stylized Deco flamingo silhouette
        d.ellipse([198, 248, 326, 336], fill=(228, 92, 112))
        d.line([(248, 332), (242, 430)], fill=(196, 72, 92), width=7)
        d.line([(278, 332), (292, 386), (258, 396)], fill=(196, 72, 92), width=6)
        neck = [(216, 266), (186, 210), (192, 152), (224, 134), (246, 146)]
        d.line(neck, fill=(228, 92, 112), width=16)
        d.ellipse([226, 128, 260, 158], fill=(228, 92, 112))
        d.polygon([(256, 140), (282, 152), (264, 166)], fill=(42, 36, 38))
        # Deep emerald tropical leaves framing corners
        for lx, ly, rx, ry in [(56, 356, 178, 456), (344, 66, 462, 168)]:
            d.ellipse([lx, ly, rx, ry], fill=(22, 88, 64))

    # 8. Coastal Sailboats on Biscayne Bay (Impressionist Oil Study)
    def art_biscayne_sails(sub, _rng):
        _grad(sub, (152, 198, 224), (238, 224, 198), 0, 290)
        _grad(sub, (42, 116, 142), (24, 72, 102), 290, th)
        d = ImageDraw.Draw(sub)
        # Soft painted cloud bands
        for cx, cy, rw, rh in [(125, 118, 95, 28), (348, 92, 115, 32), (252, 172, 84, 22)]:
            d.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=(248, 244, 236))
        # Crisp white racing sails + reflections
        for bx, by, sc in [(165, 338, 1.0), (318, 320, 0.78), (398, 308, 0.54)]:
            d.polygon([(bx, by - int(145 * sc)), (bx, by - int(18 * sc)), (bx - int(66 * sc), by - int(18 * sc))], fill=(250, 248, 242))
            d.polygon([(bx + 6, by - int(124 * sc)), (bx + 6, by - int(18 * sc)), (bx + int(52 * sc), by - int(18 * sc))], fill=(236, 232, 222))
            d.polygon([(bx - int(62 * sc), by - int(12 * sc)), (bx + int(56 * sc), by - int(12 * sc)), (bx + int(38 * sc), by + int(8 * sc)), (bx - int(48 * sc), by + int(8 * sc))], fill=(28, 44, 58))
            for r_i in range(4):
                ry = by + 16 + r_i * 12
                d.line([(bx - int(40 * sc), ry), (bx + int(34 * sc), ry)], fill=(214, 226, 228), width=3)

    _tile(0, 0, art_deco_sepia)
    _tile(1, 0, art_atlantic_sunrise)
    _tile(2, 0, art_deco_poster)
    _tile(3, 0, art_lifeguard_tower)
    _tile(0, 1, art_bw_palm_study)
    _tile(1, 1, art_news_cafe_1988)
    _tile(2, 1, art_flamingo_deco)
    _tile(3, 1, art_biscayne_sails)

    atlas.save(OUT_DIR / "gallery_art_atlas.png")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gen_awning_news_cafe()
    gen_awning_hotel_800()
    gen_host_podium()
    gen_menu_board()
    gen_street_signs()
    gen_road_textures()
    gen_interior_backdrop()
    gen_gallery_art_atlas()
    print(f"[Textures v3] Generated {len(list(OUT_DIR.glob('*.png')))} textures in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
