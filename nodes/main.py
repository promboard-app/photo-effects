"""promboard.photo-effects — 사진 효과 모음 노드 코드.

노드 하나(photo-effect)가 사진 한 장을 받아 고른 효과를 입혀 PNG 로 돌려준다.
AI 모델 없이 Pillow · numpy 만 쓰고 CPU 로 돈다.
노드 코드 약속(NODES · ctx · 입출력 모양)은 PromBoard docs/Scrum4/02_스키마-v0.md §6.

효과 5가지(설정 effect)와 세기 3단계(설정 strength: low · medium · high → 0 · 1 · 2)
  pixel     픽셀아트      세기 = 칸 크기(칸 수 128 · 80 · 48, 색 32 · 24 · 16)
  sketch    연필 스케치    세기 = 선 굵기 · 진하기
  duotone   듀오톤        세기 = 두 색을 입히는 정도(원본과 섞는 비율)
  halftone  망점(팝아트)   세기 = 점 크기
  oil       유화          세기 = 붓 터치 크기(쿠와하라 필터 반지름 4 · 7 · 11, 긴 변 1024px 기준)
투명한 부분(알파)은 그대로 둔다. 원본이 불투명하면 RGB PNG 로 저장한다.
"""

# 긴 변이 이보다 크면 줄여서 처리한다(메모리 · 시간 상한). manifest 설명과 같아야 한다.
MAX_SIDE = 2560

LEVELS = {"low": 0, "medium": 1, "high": 2}


def _load(path):
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im.load()
        rgba = ImageOps.exif_transpose(im).convert("RGBA")
    w, h = rgba.size
    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        rgba = rgba.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return rgba


def _size_factor(img):
    """효과 크기를 사진 크기에 맞추는 배율 — 긴 변 1024px 를 1 로 본다."""
    return max(img.size) / 1024


def _to_image(arr):
    import numpy as np
    from PIL import Image

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def pixel_art(ctx, rgba, level):
    from PIL import Image, ImageEnhance

    cells = (128, 80, 48)[level]
    colors = (32, 24, 16)[level]
    w, h = rgba.size
    cell = max(2, round(max(w, h) / cells))
    sw, sh = -(-w // cell), -(-h // cell)
    small = rgba.resize((sw, sh), Image.BOX)
    rgb = ImageEnhance.Color(small.convert("RGB")).enhance(1.15)
    ctx.check_cancel()
    flat = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    flat.putalpha(small.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    # 칸을 정확히 같은 크기로 키운 뒤 원래 크기로 자른다(가장자리 칸만 잘린다).
    return flat.resize((sw * cell, sh * cell), Image.NEAREST).crop((0, 0, w, h))


def pencil_sketch(ctx, rgba, level):
    import numpy as np
    from PIL import ImageFilter, ImageOps

    radius = (3.0, 6.0, 10.0)[level] * _size_factor(rgba)
    gamma = (1.1, 1.5, 2.0)[level]
    shade = (0.1, 0.22, 0.35)[level]
    gray = ImageOps.autocontrast(rgba.convert("L"), cutoff=0.5)
    blur = ImageOps.invert(gray).filter(ImageFilter.GaussianBlur(max(1.0, radius)))
    g = np.asarray(gray, dtype=np.float32)
    b = np.asarray(blur, dtype=np.float32)
    ctx.check_cancel()
    # 색 닷지: 밝은 면은 종이처럼 하얗게, 경계만 연필 선으로 남는다.
    dodge = np.clip(g * 255.0 / np.maximum(255.0 - b, 1.0), 0, 255) / 255.0
    tone = dodge**gamma * ((1.0 - shade) + shade * g / 255.0)
    grain = np.random.default_rng(7).normal(0.0, 0.025, tone.shape).astype(np.float32)
    tone = np.clip(tone + grain * tone, 0.0, 1.0)
    paper = np.array([250, 247, 240], dtype=np.float32)
    return _to_image(tone[..., None] * paper)


def duotone(ctx, rgba, level):
    import numpy as np
    from PIL import ImageOps

    t = np.asarray(ImageOps.autocontrast(rgba.convert("L"), cutoff=1), dtype=np.float32) / 255.0
    if level == 2:
        t = t * t * (3.0 - 2.0 * t)  # 강하게는 대비를 조금 더
    dark = np.array([40, 22, 96], dtype=np.float32)  # 짙은 보라
    light = np.array([255, 186, 120], dtype=np.float32)  # 살구색
    duo = dark + (light - dark) * t[..., None]
    mix = (0.55, 0.8, 1.0)[level]
    orig = np.asarray(rgba.convert("RGB"), dtype=np.float32)
    return _to_image(orig * (1.0 - mix) + duo * mix)


def halftone(ctx, rgba, level):
    """CMYK 망점 — 네 잉크를 각자 다른 각도의 점 격자로 찍어 인쇄물(팝아트) 느낌을 낸다."""
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    w, h = rgba.size
    spacing = max(4.0, max(w, h) / (150, 105, 70)[level])
    vivid = ImageEnhance.Color(ImageOps.autocontrast(rgba.convert("RGB"), cutoff=1)).enhance(1.3)
    rgb = np.asarray(vivid, dtype=np.float32) / 255.0
    # 검은 잉크는 어두운 곳에만 쓴다 — 밝은 회색까지 검은 점으로 찍으면 화면이 지저분해진다. 나머지는 세 색 점이 맡는다.
    k = np.clip((1.0 - rgb.max(axis=2) - 0.4) / 0.6, 0.0, 1.0)
    rest = np.maximum(1.0 - k, 1e-6)
    inks = {
        "c": ((1.0 - rgb[..., 0] - k) / rest, 15.0),
        "m": ((1.0 - rgb[..., 1] - k) / rest, 75.0),
        "y": ((1.0 - rgb[..., 2] - k) / rest, 0.0),
        "k": (k, 45.0),
    }
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    xs += 0.5
    ys += 0.5
    aa = 1.0 / spacing  # 1픽셀 = 칸 단위로 이만큼 — 점 가장자리를 1픽셀에 걸쳐 부드럽게
    cover = {}
    for i, (name, (amount, angle)) in enumerate(inks.items()):
        ctx.check_cancel()
        # 칸 가운데에서 잉크 양을 읽으려고 칸 크기만큼 흐린 판을 쓴다.
        plate = Image.fromarray((np.clip(amount, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(spacing / 2.5))
        plate = np.asarray(plate, dtype=np.float32) / 255.0
        a = np.deg2rad(angle)
        ca, sa = np.float32(np.cos(a)), np.float32(np.sin(a))
        u = (xs * ca + ys * sa) / spacing
        v = (ys * ca - xs * sa) / spacing
        cu = np.floor(u) + 0.5
        cv = np.floor(v) + 0.5
        cx = np.clip(((cu * ca - cv * sa) * spacing).astype(np.int32), 0, w - 1)
        cy = np.clip(((cu * sa + cv * ca) * spacing).astype(np.int32), 0, h - 1)
        radius = np.sqrt(plate[cy, cx] / np.pi)  # 점 넓이 = 잉크 양
        dist = np.hypot(u - cu, v - cv)
        cover[name] = np.clip((radius - dist) / aa + 0.5, 0.0, 1.0)
        ctx.progress(0.25 + 0.15 * (i + 1), "halftone")
    # 종이 위에 잉크를 겹쳐 찍는다. 잉크 색은 인쇄 잉크에 가깝게(순수 RGB 보다 덜 쨍하다).
    ink_colors = {
        "c": (0.0, 0.66, 0.92),
        "m": (0.92, 0.1, 0.55),
        "y": (1.0, 0.92, 0.05),
        "k": (0.12, 0.11, 0.13),
    }
    out = np.ones((h, w, 3), dtype=np.float32) * np.array([1.0, 0.985, 0.95], dtype=np.float32)
    for name, ink in ink_colors.items():
        out *= 1.0 - cover[name][..., None] * (1.0 - np.array(ink, dtype=np.float32))
    return _to_image(out * 255.0)


def oil_paint(ctx, rgba, level):
    """쿠와하라 필터 — 픽셀마다 네 방향 칸 중 색이 가장 고른 칸의 평균을 써서 붓으로 칠한 덩어리를 만든다."""
    import numpy as np
    from PIL import ImageEnhance

    r = max(2, round((4, 7, 11)[level] * _size_factor(rgba)))
    k = r + 1
    rgb = np.asarray(ImageEnhance.Color(rgba.convert("RGB")).enhance(1.12), dtype=np.float64) / 255.0
    h, w = rgb.shape[:2]
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    pad = ((r, r), (r, r))

    def integral(a):
        s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
        s[1:, 1:] = a.cumsum(0).cumsum(1)
        return s

    def window(s, oy, ox):
        return s[oy + k : oy + k + h, ox + k : ox + k + w] - s[oy : oy + h, ox + k : ox + k + w] - s[oy + k : oy + k + h, ox : ox + w] + s[oy : oy + h, ox : ox + w]

    lum_p = np.pad(lum, pad, mode="edge")
    s_l = integral(lum_p)
    s_l2 = integral(lum_p * lum_p)
    s_c = [integral(np.pad(rgb[..., c], pad, mode="edge")) for c in range(3)]
    n = float(k * k)
    best_var = np.full((h, w), np.inf)
    out = np.zeros((h, w, 3), dtype=np.float64)
    for i, (oy, ox) in enumerate(((0, 0), (0, r), (r, 0), (r, r))):
        ctx.check_cancel()
        mean = window(s_l, oy, ox) / n
        var = window(s_l2, oy, ox) / n - mean * mean
        better = var < best_var
        best_var = np.where(better, var, best_var)
        for c in range(3):
            out[..., c] = np.where(better, window(s_c[c], oy, ox) / n, out[..., c])
        ctx.progress(0.25 + 0.15 * (i + 1), "oil")
    return _to_image(out * 255.0)


EFFECTS = {"pixel": pixel_art, "sketch": pencil_sketch, "duotone": duotone, "halftone": halftone, "oil": oil_paint}


def photo_effect(ctx, inputs, settings):
    ctx.progress(0.05, "load")
    rgba = _load(inputs["image"])
    alpha = rgba.getchannel("A")
    ctx.check_cancel()
    ctx.progress(0.2, "effect")
    out = EFFECTS[settings["effect"]](ctx, rgba, LEVELS[settings["strength"]])
    ctx.check_cancel()
    opaque = alpha.getextrema() == (255, 255)
    if opaque:
        out = out.convert("RGB")
    elif out.mode != "RGBA":
        out = out.convert("RGB")
        out.putalpha(alpha)
    path = ctx.out_path("effect.png")
    ctx.progress(0.9, "save")
    out.save(path, "PNG")
    ctx.progress(1.0, "done")
    return {"image": path}


NODES = {"photo-effect": photo_effect}
