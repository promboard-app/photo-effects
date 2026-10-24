# 사진 효과 모음 · Photo Effects

PromBoard 커뮤니티 플러그인 예시입니다. 캔버스에 **사진 효과** 노드 하나를 더합니다. 사진을 이으면 고른 효과를 입혀 PNG 로 내보냅니다.

- 플러그인 id: `promboard.photo-effects`
- AI 모델을 받지 않습니다. 그래픽카드 없이 CPU 로 돕니다(파이썬 Pillow · numpy).
- 긴 변이 2560px 를 넘는 사진은 2560px 로 줄여서 처리합니다. 투명한 부분은 그대로 둡니다.

## 효과

| 효과 | 바꾸는 모양 | 세기(약하게 · 보통 · 강하게)가 바꾸는 것 |
|---|---|---|
| 픽셀아트 | 큰 네모 칸과 적은 색 | 칸 크기 |
| 연필 스케치 | 종이 위 연필 선 | 선 굵기 · 진하기 |
| 듀오톤 | 보라 · 살구 두 색 | 두 색을 입히는 정도 |
| 망점 인쇄 | 잡지 인쇄 같은 색 점 | 점 크기 |
| 유화 | 붓으로 칠한 듯한 색 덩어리 | 붓 터치 크기 |

노드 위 손잡이를 끌면 원본과 결과를 나란히 견줘 볼 수 있습니다.

## 설치

1. PromBoard 앱 → 플러그인 매니저 → **커뮤니티 플러그인** → 둘러보기에서 「사진 효과 모음」을 설치합니다.
2. 코드가 든 플러그인이라 **제한 모드**를 끄고 플러그인을 켭니다.
3. 처음 실행할 때 실행 준비가 파이썬과 Pillow · numpy 를 받습니다(한 번만).
4. 캔버스에서 노드 추가 → 플러그인 → **사진 효과**. 이미지 노드나 소스 이미지를 왼쪽 입력에 잇고 ▷ 를 누릅니다.

## 플러그인 만드는 사람을 위한 메모

```
manifest.json            플러그인 정보 · 노드 정의(layout single + views compare)
icon.png
nodes/main.py            NODES = {"photo-effect": 함수}
nodes/requirements.in    받을 패키지(사람이 고치는 파일)
nodes/requirements-*.txt 운영체제별 해시 잠금 파일(만든 파일)
```

- 잠금 파일 다시 만들기(운영체제마다 `--python-platform` 을 바꿔서):
  `uv pip compile nodes/requirements.in --generate-hashes --python-version 3.12 --python-platform x86_64-pc-windows-msvc --index-url https://pypi.org/simple -o nodes/requirements-win.txt`
- 레지스트리에 올리는 zip · 등록 항목은 PromBoard 앱 저장소의 `server/src/tools/packPlugin.ts` 로 만듭니다.

---

## English

A PromBoard community plugin example. It adds one **Photo Effect** node to the canvas: connect a photo and it outputs a PNG with the chosen effect.

- Plugin id: `promboard.photo-effects`
- No AI model download. Runs on the CPU without a graphics card (Python Pillow + numpy).
- Photos whose long side exceeds 2560 px are downscaled to 2560 px. Transparency is kept.

| Effect | Look | Strength (low · medium · high) controls |
|---|---|---|
| Pixel art (픽셀아트) | big square cells, few colors | cell size |
| Pencil sketch (연필 스케치) | pencil lines on paper | line width and darkness |
| Duotone (듀오톤) | purple and apricot | how much of the two colors is applied |
| Halftone print (망점 인쇄) | magazine-style color dots | dot size |
| Oil paint (유화) | painterly color patches | brush size |

Drag the handle on the node to compare the original and the result.

**Install**: PromBoard → Plugin Manager → **Community plugins** → Browse → install "사진 효과 모음" (Photo Effects). Turn off **Restricted mode** and enable the plugin. The first run prepares Python with Pillow and numpy (once). Then add the node from Add node → Plugins → **사진 효과** (Photo Effect).

The plugin texts in the app are Korean only for now — the plugin manifest takes a single language.

## License

MIT — see [LICENSE](LICENSE). Pillow (MIT-CMU) and numpy (BSD-3-Clause) are installed from PyPI at prepare time and are not bundled.
