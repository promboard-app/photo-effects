"""README 그림의 재료 — 이 저장소의 nodes/main.py 를 서버 없이 그대로 돌려 효과 결과를 만든다.

사용(저장소 루트에서, nodes/requirements.in 의 패키지를 깐 파이썬으로):
    python -I -B docs/scripts/make_results.py <작업 폴더>
예제 사진 세 장(park · friends · desk, GPT Image 2.5 로 만든 사진)은 Ultralytics YOLO 예시 플러그인 저장소의 cards/ 에서
받는다(처음 한 번) → <작업>/photos/. 사진마다 manifest 의 효과 전부 × 세기 3가지를 돌려 <작업>/fx/<사진>/<효과>-<세기>-effect.png 로 쓴다.
"""
import importlib.util
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
work = os.path.abspath(sys.argv[1])
PHOTOS = ("park", "friends", "desk")
CARDS = "https://raw.githubusercontent.com/promboard-app/yolo/e304aa1/cards/{}.jpg"
#: 효과 · 세기 — manifest.json 의 알약 값을 그대로 쓴다(효과를 더하거나 빼면 따라간다)
_settings = {s["id"]: s for s in json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))["nodes"][0]["settings"]}
EFFECTS = tuple(o["value"] for o in _settings["effect"]["options"])
STRENGTHS = tuple(o["value"] for o in _settings["strength"]["options"])

photos = os.path.join(work, "photos")
os.makedirs(photos, exist_ok=True)
for name in PHOTOS:
    dst = os.path.join(photos, name + ".jpg")
    if not os.path.exists(dst):
        req = urllib.request.Request(CARDS.format(name), headers={"User-Agent": "PromBoard-plugin-readme/1.0"})
        with urllib.request.urlopen(req) as r, open(dst, "wb") as f:
            f.write(r.read())

spec = importlib.util.spec_from_file_location("pe_main", os.path.join(ROOT, "nodes", "main.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Ctx:
    def __init__(self, out, prefix):
        self.out, self.prefix = out, prefix

    def progress(self, *_a, **_k):
        return True

    def check_cancel(self):
        pass

    def log(self, *_a, **_k):
        pass

    def out_path(self, name):
        return os.path.join(self.out, self.prefix + name)


for name in PHOTOS:
    out = os.path.join(work, "fx", name)
    os.makedirs(out, exist_ok=True)
    for effect in EFFECTS:
        for strength in STRENGTHS:
            mod.NODES["photo-effect"](Ctx(out, f"{effect}-{strength}-"), {"image": os.path.join(photos, name + ".jpg")},
                                      {"effect": effect, "strength": strength})
    print(name, "done", flush=True)
