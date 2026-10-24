"""README 그림 공통 — 색 · 글꼴 · 알약 라벨 · 화살표 · 체크무늬 · GIF 저장.

글꼴은 Pretendard(한글) 를 쓴다. README_FONT_DIR 에 Pretendard-*.otf 가 든 폴더를 주거나, Windows 사용자 글꼴 폴더에 설치해 둔다.
GIF 는 ffmpeg(PATH)로 만든다.
"""
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.environ.get("README_FONT_DIR") or os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")

BG = (23, 23, 23)
CARD = (35, 35, 35)
STAGE = (0, 0, 0)
LINE = (58, 58, 58)
CHIP = (40, 40, 40)
TEXT = (255, 255, 255)
MUTED = (165, 165, 165)
PURPLE = (136, 63, 215)
PURPLE_TEXT = (187, 134, 252)
PURPLE_DIM = (51, 39, 64)

_fonts = {}


def font(size, weight="SemiBold"):
    key = (size, weight)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, f"Pretendard-{weight}.otf"), size)
    return _fonts[key]


def text_size(draw, s, f):
    l, t, r, b = draw.textbbox((0, 0), s, font=f)
    return r - l, b - t


def pill(draw, xy, s, size=26, active=False, anchor="lt", pad=(18, 9), weight="SemiBold"):
    """알약 라벨. anchor: lt(왼쪽 위) · mt(가운데 위) · mb(가운데 아래) · lb · rb · rt. 그린 상자를 돌려준다."""
    f = font(size, weight)
    l, t, r, b = draw.textbbox((0, 0), s, font=f)
    w, h = r - l + pad[0] * 2, size + pad[1] * 2
    x, y = xy
    if anchor[0] == "m":
        x -= w // 2
    elif anchor[0] == "r":
        x -= w
    if anchor[1] == "b":
        y -= h
    box = (x, y, x + w, y + h)
    draw.rounded_rectangle(box, radius=h // 2, fill=PURPLE_DIM if active else CHIP, outline=PURPLE if active else LINE,
                           width=2)
    draw.text((x + pad[0] - l, y + (h - size) // 2 - t + int(size * 0.06)), s, font=f,
              fill=PURPLE_TEXT if active else TEXT)
    return box


def label_on_image(img, s, size=26, pos="lb", margin=16, active=False):
    """사진 위에 반투명 검은 알약 라벨. pos: lt · lb · mt · mb · rt · rb."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font(size)
    l, t, r, b = d.textbbox((0, 0), s, font=f)
    w, h = r - l + 32, size + 18
    x = margin if pos[0] == "l" else (img.width - w) // 2 if pos[0] == "m" else img.width - w - margin
    y = margin if pos[1] == "t" else img.height - h - margin
    fill = (51, 39, 64, 235) if active else (0, 0, 0, 175)
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill,
                        outline=(136, 63, 215, 255) if active else (255, 255, 255, 50), width=2)
    d.text((x + 16 - l, y + (h - size) // 2 - t + int(size * 0.06)), s, font=f,
           fill=(187, 134, 252, 255) if active else (255, 255, 255, 255))
    base = img.convert("RGBA")
    base.alpha_composite(layer)
    return base.convert(img.mode if img.mode in ("RGB", "RGBA") else "RGB")


def arrow(draw, x0, y, x1, color=MUTED, width=4, head=14):
    draw.line((x0, y, x1 - head, y), fill=color, width=width)
    draw.polygon([(x1, y), (x1 - head - 2, y - head * 0.7), (x1 - head - 2, y + head * 0.7)], fill=color)


def checker(size, cell=16, a=(70, 70, 70), b=(52, 52, 52)):
    w, h = size
    im = Image.new("RGB", size, a)
    d = ImageDraw.Draw(im)
    for yy in range(0, h, cell):
        for xx in range(0, w, cell):
            if (xx // cell + yy // cell) % 2:
                d.rectangle((xx, yy, xx + cell - 1, yy + cell - 1), fill=b)
    return im


def round_corners(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (0, 0), mask)
    return out


def paste_round(canvas, img, xy, radius=14):
    r = round_corners(img, radius)
    canvas.paste(r, xy, r)


def fit(img, w, h, method=Image.LANCZOS):
    """가운데를 잘라 w×h 로 채운다."""
    s = max(w / img.width, h / img.height)
    r = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), method)
    x = (r.width - w) // 2
    y = (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def contain(img, w, h, method=Image.LANCZOS):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), method)


def save_gif(frames, path, fps, colors=128, dither="bayer:bayer_scale=4", stats="diff"):
    """프레임(PIL RGB) → ffmpeg 팔레트 두 번 → GIF. 파일 크기를 돌려준다.
    stats="diff" 는 바뀌는 부분 색을 우선한다. 조금씩 자라는 면은 색이 빠질 수 있어 그런 그림은 "full" 을 쓴다."""
    with tempfile.TemporaryDirectory() as tmp:
        for i, fr in enumerate(frames):
            fr.convert("RGB").save(os.path.join(tmp, f"f{i:05d}.png"))
        pat = os.path.join(tmp, "f%05d.png")
        pal = os.path.join(tmp, "pal.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", pat,
                        "-vf", f"palettegen=max_colors={colors}:stats_mode={stats}", pal], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", pat, "-i", pal,
                        "-lavfi", f"paletteuse=dither={dither}:diff_mode=rectangle", "-loop", "0", path], check=True)
    return os.path.getsize(path)


def read_frames(path, every=1, start=0, count=None):
    import av

    out = []
    with av.open(path) as c:
        for i, f in enumerate(c.decode(video=0)):
            if i < start or (i - start) % every:
                continue
            out.append(f.to_image())
            if count and len(out) >= count:
                break
    return out
