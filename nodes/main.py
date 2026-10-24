"""promboard.photo-effects — 사진 효과 모음 노드 코드.

노드 하나(photo-effect)가 사진 한 장을 받아 고른 효과를 입혀 PNG 로 돌려준다.
AI 모델 없이 Pillow · numpy 만 쓰고 CPU 로 돈다.
노드 코드 약속(NODES · ctx · 입출력 모양)은 PromBoard docs/Scrum4/02_스키마-v0.md §6.

효과 5가지(설정 effect)와 세기 3단계(설정 strength: low · medium · high → 0 · 1 · 2)
  pixel     픽셀아트      세기 = 칸 크기(칸 수 128 · 80 · 48, 색 32 · 24 · 16)
  sketch    연필 스케치    세기 = 선 굵기 · 진하기(Lu · Xu · Jia 2012 연필화 방식 + 색 닷지 선)
  duotone   듀오톤        세기 = 두 색을 입히는 정도(원본과 섞는 비율)
  halftone  망점 인쇄      세기 = 점 크기(칸 수 160 · 110 · 72, Paper Shaders Halftone CMYK 를 옮긴 것)
  oil       유화          세기 = 붓 터치 크기(쿠와하라 필터 반지름 4 · 7 · 11, 긴 변 1024px 기준)
투명한 부분(알파)은 그대로 둔다. 원본이 불투명하면 RGB PNG 로 저장한다.
망점 인쇄 코드의 원본 · 라이선스(Apache-2.0)는 저장소의 NOTICE.
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


def _smoothstep(e0, e1, x):
    import numpy as np

    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _fft_len(n):
    """n 이상이면서 소인수가 2 · 3 · 5 뿐인 가장 작은 수 — FFT 가 빠른 길이."""
    while True:
        m = n
        for p in (2, 3, 5):
            while m % p == 0:
                m //= p
        if m == 1:
            return n
        n += 1


def _blur_f(a, sigma):
    """float 배열 흐림 — 상자 흐림을 가로 · 세로 세 번씩(가우시안에 가깝다). Pillow 흐림은 8비트 그림만 받는다."""
    import numpy as np

    r = max(1, round((np.sqrt(4.0 * sigma * sigma + 1.0) - 1.0) / 2.0))  # 세 번 겹친 분산 r(r+1) = sigma²
    n = 2 * r + 1
    a = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r + 1, r)
        for _ in range(3):
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis)
            a = (c[n:] - c[:-n]) / n if axis == 0 else (c[:, n:] - c[:, :-n]) / n
    return a


def _line_kernels(length, width):
    """8방향(0° · 22.5° · … · 157.5°) 선분 커널, 합 1. 4배로 그려 줄여 가장자리를 부드럽게 한다."""
    import numpy as np
    from PIL import Image, ImageDraw

    size = length | 1
    ss = 4
    kernels = []
    for i in range(8):
        a = np.pi * i / 8
        im = Image.new("L", (size * ss, size * ss), 0)
        c = size * ss / 2
        dx, dy = np.cos(a) * length * ss / 2, np.sin(a) * length * ss / 2
        ImageDraw.Draw(im).line((c - dx, c - dy, c + dx, c + dy), fill=255, width=max(1, round(width * ss)))
        k = np.asarray(im.resize((size, size), Image.BOX), dtype=np.float32)
        kernels.append(k / k.sum())
    return kernels


class _FftConv:
    """같은 크기 그림 여러 장을 FFT 로 합성곱한다(바깥은 0). 커널은 모두 같은 크기여야 한다."""

    def __init__(self, h, w, k):
        self.h, self.w, self.k = h, w, k
        self.shape = (_fft_len(h + k), _fft_len(w + k))

    def spec(self, a):
        import numpy as np

        return np.fft.rfft2(a.astype(np.float32), self.shape)

    def back(self, spec):
        import numpy as np

        o = self.k // 2
        return np.fft.irfft2(spec, self.shape)[o : o + self.h, o : o + self.w].astype(np.float32)


def pencil_sketch(ctx, rgba, level):
    """연필 스케치 — Lu · Xu · Jia(NPAR 2012) 「Combining Sketch and Tone for Pencil Drawing Production」 방식.

    ① 선: 밝기 기울기를 8방향 짧은 선분과 견줘 가장 잘 맞는 방향으로 나누고, 그 방향 선분으로 다시 그어
       윤곽을 연필 선으로 만든다. 이 선은 작은 닫힌 윤곽(눈 · 입)을 고리처럼 키우므로 40% 만 쓰고,
       잔 윤곽은 색 닷지(밝은 면은 하얗게, 경계만 남긴다) 선이 맡는다 — 논문에 없는 것.
    ② 명암: 밝기 분포를 연필화 분포(흰 종이 · 고른 중간 톤 · 짙은 곳 세 층, 논문 값)에 맞춘다. 고른 배경이
       통째로 짙어지지 않게 한 밝기에 몰린 화소는 잘라 고르게 나눈다(대비 제한 — 논문에 없는 것).
    ③ 빗금: 한 방향 빗금 무늬 H 를 명암 J 에 맞게 거듭제곱(H^β)해 칠한다. 논문은 β 를 전체 연립방정식으로
       풀지만 여기서는 둘레 창 안 최소제곱(β = 흐림(lnH·lnJ) / 흐림(lnH²))으로 줄였다.
    결과 = 선 × 빗금 명암, 종이 색 위.
    """
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps

    w, h = rgba.size
    f = _size_factor(rgba)
    gray_im = ImageOps.autocontrast(rgba.convert("L"), cutoff=0.5)
    length = max(7, round(7 * f)) | 1
    conv = _FftConv(h, w, length)

    # ① 선 — 잔 노이즈(기울기 0.02 아래)에서는 선을 긋지 않는다.
    g = np.asarray(gray_im.filter(ImageFilter.GaussianBlur(0.7 * f)), dtype=np.float32) / 255.0
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, :-1] = g[:, 1:] - g[:, :-1]
    gy[:-1, :] = g[1:, :] - g[:-1, :]
    grad = np.maximum(np.sqrt(gx * gx + gy * gy) - 0.02, 0.0)
    grad_spec = conv.spec(grad)
    kernels = [conv.spec(k) for k in _line_kernels(length, (1.0, 1.4, 2.0)[level] * f)]
    best = np.argmax(np.stack([conv.back(grad_spec * k) for k in kernels]), axis=0)
    ctx.check_cancel()
    ctx.progress(0.4, "sketch")
    strokes = None
    for i, k in enumerate(kernels):
        term = conv.spec(np.where(best == i, grad, 0.0)) * k
        strokes = term if strokes is None else strokes + term
    strokes = conv.back(strokes)
    darkness = (1.0, 1.4, 1.9)[level] * 0.75
    strokes = np.clip(strokes / (np.percentile(strokes, 99.5) + 1e-6) * darkness, 0.0, 1.0)
    gray = np.asarray(gray_im, dtype=np.float32)
    inv_blur = np.asarray(ImageOps.invert(gray_im).filter(ImageFilter.GaussianBlur((3.0, 5.0, 8.0)[level] * f)), dtype=np.float32)
    dodge = np.clip(gray / np.maximum(255.0 - inv_blur, 1.0), 0.0, 1.0) ** (1.2, 1.6, 2.0)[level]
    lines = dodge * (1.0 - 0.4 * strokes)
    ctx.check_cancel()
    ctx.progress(0.55, "sketch")

    # ② 명암 — 세 층 모양은 논문 값(밝은 층 σb 9 · 중간 층 105~225 · 짙은 층 μd 90 σd 11), 층 비율은 세기마다 정한 값
    v = np.arange(256, dtype=np.float64)
    bright = np.exp(-(255.0 - v) / 9.0) / 9.0
    mid = np.where((v >= 105) & (v <= 225), 1.0 / 120.0, 0.0)
    dark = np.exp(-((v - 90.0) ** 2) / (2 * 11.0**2)) / np.sqrt(2 * np.pi * 11.0)
    wb, wm, wd = ((76, 22, 2), (70, 26, 4), (60, 32, 8))[level]
    target = np.cumsum(wb * bright + wm * mid + wd * dark)
    target /= target[-1]
    g8 = np.asarray(gray_im.filter(ImageFilter.GaussianBlur(1.0 * f)))
    hist = np.bincount(g8.ravel(), minlength=256).astype(np.float64)
    cap = 3.0 * hist.sum() / 256
    for _ in range(4):
        hist = np.minimum(hist, cap) + np.maximum(hist - cap, 0.0).sum() / 256
    lut = np.searchsorted(target, np.cumsum(hist) / hist.sum()).clip(0, 255).astype(np.uint8)
    tone_im = Image.fromarray(lut[g8]).filter(ImageFilter.GaussianBlur(1.5 * f))
    tone = np.clip(np.asarray(tone_im, dtype=np.float32) / 255.0, 0.02, 1.0)
    ctx.check_cancel()
    ctx.progress(0.65, "sketch")

    # ③ 빗금 — 낟알 난수를 135° 방향으로 길게 끌어 연필로 같은 방향 빗금을 그은 면을 만든다.
    rng = np.random.default_rng(7)
    seed = Image.fromarray((rng.random((h, w)) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6 * f))
    seed = np.asarray(seed, dtype=np.float32) / 255.0
    hatch_len = max(9, round(16 * f)) | 1
    hatch_conv = _FftConv(h, w, hatch_len)
    hatch = hatch_conv.back(hatch_conv.spec(seed - seed.mean()) * hatch_conv.spec(_line_kernels(hatch_len, 1.0)[6]))
    texture = np.clip(0.55 + 0.10 * hatch / (hatch.std() + 1e-6), 0.08, 0.97)
    ln_tex = np.log(texture)
    ln_tone = np.log(tone)
    beta = _blur_f(ln_tex * ln_tone, 3.0 * f) / (_blur_f(ln_tex * ln_tex, 3.0 * f) + 1e-4)
    shade = np.exp(beta * ln_tex)
    paper = np.array([250, 247, 240], dtype=np.float32)
    return _to_image((lines * shade)[..., None] * paper)


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


# 망점 잉크 네 판 — (이름, 격자 각도°, 격자 밀기, 잉크 색, 점 크기에 더하는 값, 점 크기에 비례해 키우는 값).
# 칠하는 순서 K · C · M · Y. 값은 Paper Shaders Halftone CMYK 의 Vintage 프리셋.
HALFTONE_INKS = (
    ("k", 45.0, 0.0, (0x2D, 0x28, 0x24), 0.0, 0.0),
    ("c", 15.0, -0.5, (0x59, 0xAF, 0xC5), 0.15, 0.3),
    ("m", 75.0, -0.25, (0xD8, 0x69, 0x7C), 0.0, 0.0),
    ("y", 0.0, 0.2, (0xFA, 0xD8, 0x5C), 0.0, 0.2),
)
HALFTONE_PAPER = (0xFF, 0xFA, 0xF0)


def _dot_profile(n=4096):
    """점 하나의 진하기 표 — (거리 / 반지름)² 를 n 칸으로 나눠 (1 − smoothstep(0, 1, 거리 / 반지름))^1.2 를 미리 구한다."""
    import numpy as np

    t = np.sqrt(np.linspace(0.0, 1.0, n, dtype=np.float32))
    return ((1.0 - t * t * (3.0 - 2.0 * t)) ** 1.2).astype(np.float32)


def halftone(ctx, rgba, level):
    """CMYK 망점 — 잉크 네 판을 각도가 다른 점 격자로 찍어 오래된 잡지 인쇄처럼 만든다.

    Paper Shaders 「Halftone CMYK」 셰이더(Apache-2.0, NOTICE)를 numpy 로 옮겼다. 그 셰이더의 Vintage 프리셋과 같은
    sharp 방식이다. 픽셀마다 둘레 3×3 칸의 점을 가운데서 가장자리로 흐려지는 원으로 더한 뒤 문턱을 걸어, 가까운 점은
    잉크처럼 이어지고 가장자리는 매끈해진다. 점 크기는 그 픽셀 색에서 읽어 점이 사진 윤곽을 따라 잘린다.
    칸 가운데를 조금씩 흔들고(격자 흔들림), 잔 낟알로 점 가장자리와 종이를 거칠게 한다.
    고친 점: 대비를 1.25 에서 1.1 로 낮추고 잉크 양을 0.85제곱해 밝은 · 중간 톤이 덜 날아가게 했다(회색 단계 평균
    밝기 오차 0.09 → 0.06). 점 크기는 칸 수(긴 변 기준)로 정하고, 낟알은 픽셀 크기에 맞춘 값 노이즈로 바꾸고,
    점 모양 계산은 표로 미리 구하고, 메모리 안에서 빨리 돌도록 줄 묶음(띠)으로 나눠 계산한다.
    """
    import numpy as np
    from PIL import Image

    w, h = rgba.size
    cell = max(4.0, max(w, h) / (160, 110, 72)[level])  # 칸 한 변(px)
    contrast, softness, grid_noise, grain_mixer, grain_overlay = 1.1, 0.4, 0.45, 0.15, 0.1
    arr = np.asarray(rgba, dtype=np.float32) / 255.0
    rgb = np.clip((arr[..., :3] - 0.5) * contrast + 0.5, 0.0, 1.0)
    top = rgb.max(axis=2)
    lit = np.maximum(top, 1e-5)
    amount = {"c": (top - rgb[..., 0]) / lit, "m": (top - rgb[..., 1]) / lit, "y": (top - rgb[..., 2]) / lit, "k": 1.0 - top}
    rng = np.random.default_rng(7)
    # 값 노이즈 세 장(점 크기 거칠게 1 · 종이 낟알 2) — 낟알 한 칸 = 긴 변 1024px 기준 1px
    gw, gh = max(2, round(w / _size_factor(rgba))), max(2, round(h / _size_factor(rgba)))
    noise = [np.asarray(Image.fromarray(rng.random((gh, gw), dtype=np.float32), "F").resize((w, h), Image.BILINEAR)) for _ in range(3)]
    shrink = 1.0 - _smoothstep(0.55, 1.0, noise[0]) * grain_mixer
    general = 0.1 * softness + 0.1 * grid_noise
    profile = _dot_profile()
    last = np.float32(len(profile) - 1)

    # 판마다 격자 회전 · 칸마다 고정된 흔들림 표 · 픽셀마다 점 반지름(칸 단위). 칸 번호 범위는 그림 네 귀퉁이에서 구한다.
    xs = (np.arange(w, dtype=np.float32) + (0.5 - w / 2)) / cell
    y_ends = np.array([0.5 - h / 2, h - 0.5 - h / 2], dtype=np.float32) / cell
    corner_x = np.array([xs[0], xs[-1], xs[0], xs[-1]])
    corner_y = np.array([y_ends[0], y_ends[0], y_ends[1], y_ends[1]])
    plates = []
    for name, angle, shift, color, flood, gain in HALFTONE_INKS:
        a = np.deg2rad(angle)
        ca, sa = np.float32(np.cos(a)), np.float32(np.sin(a))
        cu = ca * corner_x - sa * corner_y + shift
        cv = sa * corner_x + ca * corner_y + shift
        i0, j0 = int(np.floor(cu.min())) - 2, int(np.floor(cv.min())) - 2
        nj = int(np.floor(cv.max())) + 3 - j0
        cells = (int(np.floor(cu.max())) + 3 - i0) * nj
        jitter_u = (rng.random(cells, dtype=np.float32) - 0.5) * grid_noise
        jitter_v = (rng.random(cells, dtype=np.float32) - 0.5) * grid_noise
        r = amount[name] ** 0.85 * (1.0 + general)  # 0.85제곱 — 밝은 톤의 점을 키워 출력 밝기를 원본에 가깝게
        r = (np.maximum(r + 0.15 + gain * r, 0.0) * arr[..., 3] + flood) * shrink
        absorb = 1.0 - np.array(color, dtype=np.float32) / 255.0
        plates.append((ca, sa, shift, i0, j0, nj, jitter_u, jitter_v, r, absorb))
    del amount, rgb, top, lit, shrink

    paper = np.array(HALFTONE_PAPER, dtype=np.float32) / 255.0
    out = np.empty((h, w, 3), dtype=np.float32)
    for y0 in range(0, h, 64):
        ctx.check_cancel()
        y1 = min(h, y0 + 64)
        ye = min(h, y1 + 1)  # 아래로 한 줄 더 — 띠 경계에서도 세로 차이를 구한다
        gy = ((np.arange(y0, ye, dtype=np.float32) + (0.5 - h / 2)) / cell)[:, None]
        ink = np.ones((y1 - y0, w, 3), dtype=np.float32)
        shape = np.zeros((y1 - y0, w), dtype=np.float32)
        for ca, sa, shift, i0, j0, nj, jitter_u, jitter_v, radius, absorb in plates:
            u = ca * xs - sa * gy + shift
            v = sa * xs + ca * gy + shift
            iu, iv = np.floor(u), np.floor(v)
            u -= iu  # 칸 안 위치 0~1
            v -= iv
            base = (iu.astype(np.int32) - i0) * nj + (iv.astype(np.int32) - j0)
            r = radius[y0:ye]
            inv_r2 = 1.0 / np.maximum(r * r, 1e-12)
            acc = np.zeros_like(u)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    idx = base + (dx * nj + dy)
                    du = u - (dx + 0.5) - jitter_u[idx]
                    dv = v - (dy + 0.5) - jitter_v[idx]
                    q = (du * du + dv * dv) * inv_r2  # (거리 / 반지름)²
                    np.minimum(q, 1.0, out=q)
                    acc += profile[(q * last).astype(np.int32)]
            acc *= 1.0 - softness + softness * (0.5 + 0.75 * r)
            # 이어진 점에 문턱 — 가장자리는 이웃 픽셀과의 차이만큼 넓혀 계단을 없앤다.
            edge = np.abs(np.diff(acc, axis=1, append=acc[:, -1:])) + np.abs(np.diff(acc, axis=0, append=acc[-1:, :]))
            cover = _smoothstep(0.5 - 0.5 * softness - edge, 0.5 + 0.5 * softness + 0.01, acc)[: y1 - y0]
            ink *= 1.0 - cover[..., None] * absorb
            np.maximum(shape, cover, out=shape)
        out[y0:y1] = paper + (ink - paper) * shape[..., None]
        ctx.progress(0.25 + 0.6 * y1 / h, "halftone")
    # 종이 낟알 — 흰 · 검은 잔 점을 살짝 얹는다.
    g = ((noise[1] + noise[2]) * 0.5) ** 1.3 * 2.0 - 1.0
    strength = (grain_overlay * np.abs(g)) ** 0.8 * 0.5
    speck = (g >= 0).astype(np.float32)[..., None]
    out += (speck - out) * strength[..., None]
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
