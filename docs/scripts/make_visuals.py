"""README 그림 · 움짤을 만든다(make_results.py 결과로).

사용(저장소 루트에서):
    python -I -B docs/scripts/make_visuals.py <작업 폴더(make_results 결과)> docs <ko|en> [hero,strength,gif]
언어별 그림(hero.jpg · strength.jpg)은 docs/<언어>/ 에, 글자 없는 움짤(compare.gif)은 두 언어가 같이 쓰도록 docs/ 에 쓴다.
움짤은 언어와 상관없으니 한 번만 만들면 된다.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

work, docs, lang = sys.argv[1:4]
fx_dir = os.path.join(work, "fx")
photo_dir = os.path.join(work, "photos")
out = os.path.join(docs, lang)
os.makedirs(out, exist_ok=True)

EFFECTS = ["pixel", "sketch", "duotone", "halftone", "oil"]
NAMES = {
    "ko": {"original": "원본", "pixel": "픽셀아트", "sketch": "연필 스케치", "duotone": "듀오톤", "halftone": "망점 인쇄",
           "oil": "유화", "low": "약하게", "medium": "보통", "high": "강하게", "strength": "세기"},
    "en": {"original": "Original", "pixel": "Pixel art", "sketch": "Pencil sketch", "duotone": "Duotone",
           "halftone": "Halftone print", "oil": "Oil paint", "low": "Low", "medium": "Medium", "high": "High",
           "strength": "Strength"},
}[lang]


def res(photo, effect, strength="medium"):
    return Image.open(os.path.join(fx_dir, photo, f"{effect}-{strength}-effect.png")).convert("RGB")


def orig(photo):
    return Image.open(os.path.join(photo_dir, f"{photo}.jpg")).convert("RGB")


# ── 대표 그림: 공원 사진 한 장을 여섯 조각으로(원본 + 효과 다섯, 세기 보통) ─────────────
def hero():
    src = orig("park")
    imgs = [src] + [res("park", e) for e in EFFECTS]
    names = ["original"] + EFFECTS
    y0, y1 = 96, 96 + 864  # 16:9 로 자른다
    strip = src.width // 6
    gap, pad = 6, 24
    canvas = Image.new("RGB", (src.width + gap * 5 + pad * 2, (y1 - y0) + pad * 2), C.BG)
    for i, (im, n) in enumerate(zip(imgs, names)):
        part = im.crop((i * strip, y0, (i + 1) * strip, y1))
        part = C.label_on_image(part, NAMES[n], size=24, pos="mb", margin=20, active=(n != "original"))
        canvas.paste(part, (pad + i * (strip + gap), pad))
    canvas.save(os.path.join(out, "hero.jpg"), quality=88, optimize=True, progressive=True)


# ── 세기 비교: 효과 5 × 약하게 · 보통 · 강하게(두 친구 사진의 얼굴 쪽) ─────────────────
def strength():
    box = (150, 120, 870, 600)  # friends.jpg 두 얼굴과 윗몸
    tw, th, label_w = 420, 280, 190
    gap, pad, head = 12, 24, 60
    canvas = Image.new("RGB", (pad * 2 + label_w + tw * 3 + gap * 2, pad + head + th * 5 + gap * 4 + pad), C.BG)
    d = ImageDraw.Draw(canvas)
    d.text((pad, pad + 10), NAMES["strength"], font=C.font(22, "Regular"), fill=C.MUTED)
    for j, s in enumerate(["low", "medium", "high"]):
        C.pill(d, (pad + label_w + j * (tw + gap) + tw // 2, pad + 4), NAMES[s], size=22, anchor="mt",
               active=(s == "medium"))
    for i, e in enumerate(EFFECTS):
        y = pad + head + i * (th + gap)
        d.text((pad, y + th // 2 - 14), NAMES[e], font=C.font(26), fill=C.TEXT)
        for j, s in enumerate(["low", "medium", "high"]):
            t = res("friends", e, s).crop(box).resize((tw, th), Image.LANCZOS)
            C.paste_round(canvas, t, (pad + label_w + j * (tw + gap), y), radius=10)
    canvas.save(os.path.join(out, "strength.jpg"), quality=88, optimize=True, progressive=True)


# ── 움짤(글자 없음): 노드의 원본 ↔ 결과 손잡이처럼, 왼쪽 원본 · 오른쪽 효과(EFFECTS 순서, 세기 보통) ──
def compare_gif():
    W, H, fps, n = 600, 400, 15, 34
    base = C.fit(orig("desk"), W, H)
    frames = []
    for e in EFFECTS:
        eff = C.fit(res("desk", e), W, H)
        for k in range(n):
            # 오른쪽 끝 → 왼쪽 20% → 가운데쯤에서 잠깐 멈춤
            p = k / (n - 1)
            pos = 0.94 - 0.74 * (0.5 - 0.5 * math.cos(math.pi * min(1, p * 1.6)))
            if p > 0.62:
                pos = 0.2 + 0.35 * (0.5 - 0.5 * math.cos(math.pi * (p - 0.62) / 0.38))
            x = int(W * pos)
            fr = base.copy()
            fr.paste(eff.crop((x, 0, W, H)), (x, 0))
            d = ImageDraw.Draw(fr)
            d.line((x, 0, x, H), fill=(255, 255, 255), width=3)
            d.ellipse((x - 16, H // 2 - 16, x + 16, H // 2 + 16), fill=(255, 255, 255), outline=(0, 0, 0), width=2)
            d.polygon([(x - 9, H // 2), (x - 3, H // 2 - 6), (x - 3, H // 2 + 6)], fill=(40, 40, 40))
            d.polygon([(x + 9, H // 2), (x + 3, H // 2 - 6), (x + 3, H // 2 + 6)], fill=(40, 40, 40))
            frames.append(fr)
    return C.save_gif(frames, os.path.join(docs, "compare.gif"), fps, colors=160, dither="bayer:bayer_scale=3")


jobs = sys.argv[4].split(",") if len(sys.argv) > 4 else ["hero", "strength", "gif"]
if "hero" in jobs:
    hero()
if "strength" in jobs:
    strength()
if "gif" in jobs:
    print("compare.gif", compare_gif())
for f in sorted(os.listdir(out)):
    print(f, os.path.getsize(os.path.join(out, f)))
