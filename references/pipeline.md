# texture-packer 파이프라인 — 핵심 개념·로직·소스코드 (복구 SSOT)

이 문서만 보고도 packing 파이프라인 전체를 복구/재생성할 수 있어야 한다. 코드를 임의로
바꾸지 말고 아래 규약을 그대로 따른다.

## 목차
1. [핵심 개념 — 전체 흐름](#1-핵심-개념--전체-흐름)
2. [프로젝트 루트 탐색 (이동 후 필수)](#2-프로젝트-루트-탐색-이동-후-필수)
3. [경로/출력 규약](#3-경로출력-규약)
4. [libGDX TexturePacker jar 자동 다운로드](#4-libgdx-texturepacker-jar-자동-다운로드)
5. [256색 압축 — compress_image.py 공유](#5-256색-압축--compress_imagepy-공유)
6. [발 정렬 + 무기 잘림 3대 메커니즘](#6-발-정렬--무기-잘림-3대-메커니즘)
7. [해상도/셀 SSOT](#7-해상도셀-ssot)
8. [Windows 형제 파일](#8-windows-형제-파일)
9. [cell 잘림 자동 검사 + auto-fit (verify_cells.py)](#9-cell-잘림-자동-검사--auto-fit-verify_cellspy)

---

## 1. 핵심 개념 — 전체 흐름

`sheet.py` 가 오케스트레이션하는 단계(macOS):

```
3D 모델(.fbx/.glb/.gltf/.blend)
  │  _sheet_render.py  (blender -b -P … -- <config.json>)
  ▼
방향별 frame PNG (render_res 256, 16 row)   ← align_feet 로 발 0.85 정렬
  │  ── --texture-pack true (기본) ──▶ libGDX TexturePacker(gdx-tools jar)
  │                                     → assets/<kind>/<name>/<name>.png + .atlas
  │  ── --texture-pack false ──▶ _sheet_build.py (균일 grid 단일 sheet)
  │                                     → assets/<kind>/<name>/<name>.png
  ▼
256색 FASTOCTREE 압축 (compress_image.py, in-place)
  ▼
pubspec.yaml 관리 블록에 이번 <name> 만 자동 추가
```

- `_sheet_render.py`·`_sheet_build.py`·`align_feet.py` 는 **config.json/인자 기반**이라 자체
  ROOT 계산이 없다 → skill 로 옮겨도 수정 불필요. `sheet.py` 가 절대경로를 config 에 넣어준다.
- `sheet.py` 는 `blender -b -P os.path.join(HERE, "_sheet_render.py")` 로 렌더 스크립트를
  같은 폴더(HERE=skill scripts)에서 찾는다 → 함께 옮겼으므로 정상.

## 2. 프로젝트 루트 탐색 (이동 후 필수)

`sheet.py`·`sheet-win.py`·`combine_to_runtime_sheet.py` 는 `.claude/skills/texture-packer/scripts/`
로 이동했으므로 과거의 `ROOT = os.path.dirname(HERE)` 는 더 이상 repo 루트가 아니다(=texture-packer).
아래 함수로 견고하게 탐색한다(이 로직을 **삭제/단순화하면 산출 경로가 전부 깨진다**):

```python
def _find_project_root(here):
    """① LARYEN_ROOT env(pubspec 검증) ② skill 4단계 상위 ③ git rev-parse ④ cwd"""
    env = os.environ.get("LARYEN_ROOT")
    if env and os.path.isfile(os.path.join(env, "pubspec.yaml")):
        return os.path.abspath(env)
    cand = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))  # scripts→texture-packer→skills→.claude→ROOT
    if os.path.isfile(os.path.join(cand, "pubspec.yaml")):
        return cand
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=here, text=True, stderr=subprocess.DEVNULL).strip()
        if top and os.path.isfile(os.path.join(top, "pubspec.yaml")):
            return top
    except Exception:
        pass
    return os.getcwd()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = _find_project_root(HERE)
```

- `gen_all_sheets.sh` 는 같은 원리로 `SCRIPT_DIR/../../../..` 를 `ROOT` 로 잡고 `cd "$ROOT"`,
  sheet.py 는 `SHEET="$SCRIPT_DIR/sheet.py"` 절대경로로 호출한다.
- **스킬 폴더를 다른 위치로 옮기면** 4단계 상위 가정이 깨진다 → 그때는 `LARYEN_ROOT` env 를
  주거나 git repo 안에서 실행(③ fallback)한다.

## 3. 경로/출력 규약

```python
KIND_MODEL_DIR = {"pc": "game-assets/characters",
                  "mob": "game-assets/monsters",
                  "npc": "game-assets/blend"}
ANIM_ROOT = "game-assets/animations"   # <variant>/{action}.fbx

# 모델 탐색:  os.path.join(ROOT, KIND_MODEL_DIR[kind], <character>)
# 출력 폴더:  os.path.join(output_base, kind, name)   → <name>.png / <name>.atlas
#   output_base = --output DIR 지정 시 그 경로(절대경로 아니면 ROOT 기준 상대 해석),
#                 미지정 시 os.path.join(ROOT, "assets")  ← 기본
# grid 정보:  os.path.join(ROOT, "game-assets", "sprites")  (--texture-pack false)
# 작업 폴더:  os.path.join(ROOT, "outputs", name)          (--outputs 미지정 시)
# pubspec:    os.path.join(ROOT, "pubspec.yaml")
```

```python
# --output 처리 (sheet.py / sheet-win.py 동일)
if args.output_base:
    output_base = args.output_base if os.path.isabs(args.output_base) \
        else os.path.abspath(os.path.join(ROOT, args.output_base))   # cwd 아님 — ROOT 기준
else:
    output_base = os.path.join(ROOT, "assets")
out_folder = os.path.join(output_base, args.kind, name)
```

- pubspec 관리 블록: `# >>> AUTO(sheet.py packed actors) >>>` … 이번 `<name>` 의
  `assets/<kind>/<name>/<name>.png[, .atlas]` 만 추가(전체 폴더 등록 금지).
- 🛑 `--output` 지정 시 **루트 pubspec.yaml 자동 갱신은 건너뛴다** — 대상이 루트 `assets/` 가
  아닌 별도 앱/뷰어일 수 있어 루트 pubspec 을 오염시키지 않는다(기본 출력일 때만 update_pubspec 호출).
- 🛑 게임 pc/mob 로드는 *오직* `assets/<pc|mob>/<name>/<name>.atlas`. 격자
  `assets/render/actors/` 는 폐기(2026-07-01). atlas 없으면 투명 placeholder + 재생성 목록 로그.

## 4. libGDX TexturePacker jar 자동 다운로드

```python
GDX_VERSION = "1.13.1"   # GDX_MAVEN = Maven central
GDX_JARS = {
    "gdx-1.13.1.jar":                          ".../gdx/1.13.1/gdx-1.13.1.jar",
    "gdx-tools-1.13.1.jar":                    ".../gdx-tools/1.13.1/gdx-tools-1.13.1.jar",
    "gdx-platform-1.13.1-natives-desktop.jar": ".../gdx-platform/1.13.1/…-natives-desktop.jar",
}
# tools_dir = os.path.join(HERE, "tools")   ← skill scripts/tools/ (gitignore, 다운로드 캐시)
#   jar 없으면 Maven 에서 _download 후 캐시. --packer-cp 로 수동 지정 가능.
```

- `scripts/tools/*.jar` 는 gitignore(자동 다운로드 캐시)라 git 추적 안 됨. skill 이동 시
  일반 `mv` 로 옮긴다(`git mv` 는 미추적이라 실패). 없으면 첫 실행에 자동 재다운로드.
- packing 은 `java -cp <jars> com.badlogic.gdx.tools.texturepacker.TexturePacker …` 로 실행.
  **Java 필요**(`--java` 로 경로 지정 가능). trim(투명 여백 제거) + 필요 시 90도 rotate packing.

## 5. 256색 압축 — compress_image.py 공유

`compress_image.py` 는 **이 스킬 소유가 아니다**. 범용 PNG 압축 도구라 프로젝트
`scripts/compress_image.py` 에 있고 `compress-image` 스킬이 공유한다. sheet.py 는 이렇게 참조:

```python
def compress_pages(pages, colors=256):
    """packed atlas 페이지 PNG(들)를 compress_image.py 의 q256 으로 in-place 압축.
       🛑 in-place 라야 .atlas 의 페이지 참조(basename)가 유지된다."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))   # ← HERE 아님! 프로젝트 scripts/
        import compress_image as _ci
        from PIL import Image
        direct = (_ci, Image)
    except (Exception, SystemExit):   # numpy/pillow 부재 시 SystemExit → uv 격리 폴백
        direct = None
    for p in pages:
        if direct is not None:
            _ci, Image = direct
            _ci.compress_q256(Image.open(p), p, colors=colors)   # in-place
        else:
            build = os.path.join(ROOT, "scripts", "compress_image.py")   # ← 프로젝트 scripts/
            # uv run --with numpy --with pillow python3 <build> <p> --inplace --colors <n>
```

- 🛑 `sys.path.insert(0, HERE)` 로 되돌리지 말 것 — HERE 는 skill scripts 라 거기엔
  compress_image.py 가 없다. 반드시 `os.path.join(ROOT, "scripts")`.
- RAM 은 W×H×4 로 고정. 압축은 **디스크/번들 용량만** 줄인다(OOM 무관 — game-memory.md SSOT).

## 6. 발 정렬 + 무기 잘림 3대 메커니즘

무기(검·도끼)가 run/attack 에서 cell(128) 밖으로 잘리는 문제는 **cell 128 유지한 채**
아래 3가지를 *한 세트*로 적용해 해결한다(하나라도 빠지면 "검 잘림" 또는 "행동 전환 점프"):

1. **행동별 생성 scale** — `--scale-attack 0.8 --scale-run 0.9` 로 그 행동만 모델을 작게
   그려(`ortho=base/scale`) 무기가 셀 안에 들어오게 한다.
2. **발 y 정렬(자동)** — `align_feet.py` / `_sheet_build.py` 가 모든 프레임의 발(불투명 bbox
   하단)을 셀 0.85 에 고정 정렬 → 행동 전환 상하 "점프" 원천 차단. 목표 y(0.85)는 scale·무기
   크기와 무관한 고정 상수.
3. **런타임 화면 보정** — `kActorDisplayKByKind`(actor_animation_set.dart, 사람 편집 const)에
   `1/scale`(0.8→1.25) 입력 → 작게 구운 만큼 화면에서 키워 몸 크기 유지. sheet.py 가 생성 후
   권장값을 출력한다(python→dart 자동 생성 금지).

> 상세 SSOT·FAQ 는 `.claude/skills/asset/references/ssot.md §1.5`.

## 7. 해상도/셀 SSOT

```python
DEFAULT_RENDER_RES = 256   # frame 렌더 해상도
DEFAULT_CELL_SIZE  = 128   # atlas orig/cell (2026-07-05 pc/npc/mob 전부 128 통일)
# --scale-frames 자동 = CELL/RENDER = 128/256 = 0.5
DEFAULT_FRAMES  = {"idle":8, "walk":12, "attack":16, "hit":8, "death":8, "run":12, "look":?, "talk":?, "wave":?}
DEFAULT_ACTIONS = ["idle","walk","attack","hit","death","run"]   # pc/mob col 순서
NPC_ACTIONS     = ["idle","look","talk","walk","wave"]           # npc col 순서
```

- 과거 pc/npc 160·mob 128 로 갈렸으나 display 가 어차피 128 이라 pc/npc 160 의 여유 픽셀은
  화질 이득 없이 iOS OOM(actorAtlas RAM)만 키웠다 → 128 통일(texture=display 1:1).
- 출시 4플랫폼(Android/iOS/Windows/macOS) native 8192 단축이라 7680×2048 단일 통짜 sheet OK
  (Web 미출시 → 4096 제한 무관).

## 8. Windows 형제 파일

`sheet-win.py`·`sheet-preview-win.py` 는 macOS `sheet.py` 의 Windows 판으로, 같은 보조
스크립트(`_sheet_render.py`·`_sheet_build.py`·`align_feet.py`)를 `os.path.join(HERE, …)` 로
공유한다 → 함께 이 스킬 scripts/ 에 있어야 정상. `_find_project_root` 로직·compress_image
경로(`ROOT/scripts`)를 sheet.py 와 동일하게 유지한다. `sheet-preview-win.py` 는 4방향 preview
허용 패치를 production `_sheet_render.py`/`_sheet_build.py` 에서 복사 생성하며, 출력은
`outputs/<name>_preview/`(production assets/ 오염 없음).

## 9. cell 잘림 자동 검사 + auto-fit (verify_cells.py)

flutter 실행 없이 **생성된 프레임 이미지만으로** run/attack 등 큰 모션이 셀 밖으로 잘렸는지
판정하고, 잘리면 `--scale-<action>` 을 자동 조정해 재렌더로 수렴한다.

### 핵심 개념
sheet.py 는 각 프레임을 정사각 셀(render_res)에 렌더한다. 모델·무기가 크면(검 휘두름 등) 셀
경계 밖으로 나가 clip 되고, 그 흔적이 **프레임 테두리의 불투명(alpha>0) 픽셀** 로 남는다.
테두리에 불투명이 있으면 그 방향으로 잘린 것 → scale 을 낮춰(모델을 작게) 셀 안에 넣는다.

### 핵심 로직 — verify_cells.py
🛑 심각도는 '안쪽 깊이'가 아니라 **테두리 라인 위 불투명 비율(frac)** 로 잰다. 깊이로 재면
캐릭터 몸통 세로 길이를 잘림으로 오판한다(테두리에 닿은 몸통이 안쪽까지 연속 불투명 → 깊이가
셀에 육박).

```python
op = (alpha > thresh)                          # margin=2, thresh=8
counts = {"top": op[:m,:].sum(), "bottom": op[h-m:,:].sum(),
          "left": op[:,:m].sum(), "right": op[:,w-m:].sum()}
frac = {변: counts[변] / (테두리 픽셀 수)}       # 0~1 (top/bottom=m*w, left/right=m*h)
# clip 판정: max(frac) > 0 인 프레임을 그 행동의 clip 으로 집계.
# 권장 scale: max(0.6, round(1.0 - max_frac - 0.06, 2))  ← 잘린 비율만큼 축소 + 여유 6%.
```
행동별 리포트(잘린 프레임 수·테두리 방향·최악 프레임·권장 scale), `--json`, exit code(0 정상 / 2 잘림).

### auto-fit 재렌더 루프 — sheet.py
```python
for _fit in range(1 + (3 if args.auto_fit_scale else 0)):
    if _fit > 0: cfg["action_scales"] = action_scales; json.dump(cfg, ...)  # 낮춘 scale 반영
    <Blender 렌더>
    if not args.verify_cells: break
    rec = verify_cells_and_report(frames_dir)   # {action: 권장scale} · 잘림 없으면 {}
    if not rec: break                            # 잘림 0 → 완료
    if _fit >= max_fit: break                    # 최대 반복 도달
    for a, s in rec.items():
        if s < action_scales[a]: action_scales[a] = s   # 잘린 행동만 낮춰 재렌더
```
- `--verify-cells`(기본 true): 렌더 후 자동 검사 + 권장 scale 출력.
- `--auto-fit-scale`: 잘리면 권장 scale 로 자동 재렌더(최대 3회 수렴). 렌더는 항상 `--frames`
  (렌더 직후 낱장) 검사 — 잘림은 렌더에서 확정되므로 align_feet(세로 정렬) 전이라도 판정이 유효.

### 검증(실측 2026-07-07, blend 자산 + texture shading)
| 시나리오 | 결과 |
|---|---|
| ambusher.blend scale 1.0 | death 2/16 clip(1%) → auto-fit `--scale-death 0.93` → **1회 재렌더 잘림 0** |
| 큰 잘림 유발(scale 1.4) | **6종 행동 clip**(attack 47%·death 40%·hit 35%·idle 35%·run 28%·walk 14%) → 각각 다른 권장(0.6~0.8) → **1회 수렴** |
| brute.blend scale 1.0 | death 4/16 clip(7%) → 0.87 (다른 자산도 정확) |
| false positive | 전 행동 scale 0.7(작게) → **잘림 0**(작게 구운 건 정상 판정) |
| 육안 교차 | ai_paladin `attack_W_04` 방패·검 상단 clip = top 검출과 일치 |
| **전체 packing 통합**(scale 1.3 + Y trim) | 6종 clip → auto-fit 재렌더 잘림 0 → atlas 생성. `laryen.actionScale` 메타에 auto-fit scale(attack 0.6·idle 0.68·walk 0.84…) 기록(런타임 1/scale 원래 크기 복원) + Y trim `offset y≠0`(fix_offset_y 보정) — **auto-fit·메타·발 보정이 한 atlas 에 정합** |
| **npc kind**(mannequin, 8dir, look/talk/wave) | scale 1.3 → npc 전용 행동 5종(idle/look/talk/walk/wave) clip(bottom 위주) → auto-fit(look 0.83·talk 0.86·wave 0.8…) → 재렌더 잘림 0. scale 1.0 자연 상태는 잘림 0 — **mob 과 다른 행동 세트에서도 검사·auto-fit 정확**(pc/npc/mob 커버) |
| **pc kind**(ambusher --kind pc) | scale 1.3 → 6종 clip → auto-fit(attack 0.68·death 0.6·walk 0.84…) → 재렌더 잘림 0. mob 과 동일 행동·경로에서 pc 로도 수렴 실증 |
| **--build-only 검사** | 잘림 있는 기존 프레임(attack scale 1.3) 재packing → `[검사]` 가 attack 26%·death 1% clip 감지 + 권장 scale + 🛑 재렌더 권장 출력 후 packing 계속(auto-fit 은 렌더 경로만) |
| **16방향(production) + 프레임 1** | 🐛 버그 발견·수정: `--idle 1` 등 프레임 1 → `sample_frames` 의 `(n-1)` 나눗셈 ZeroDivisionError 로 렌더 크래시 → `n<=1` 가드 추가([_sheet_render.py](../scripts/_sheet_render.py) `sample_frames`). 수정 후 16방향 렌더 성공(112장) → attack 26% clip → auto-fit 0.68 → 재렌더 잘림 0 |
| **verify `--atlas` + auto-fit 안전** | packed atlas 근사 검사(`--atlas`): region 96개 파싱·여백 판정 동작(정밀은 `--frames`). auto-fit **무한루프 이중 방어** — `for _fit in range(_max_fit+1)`(최대 4회 렌더) + SCALE_MIN(0.6) 도달 시 `if not _changed: break` 조기 종료 |
| **verify_cells 도구 견고성** | 🐛 edge case 오판 수정: **alpha 채널 없는 이미지(RGB)** → `convert("RGBA")` 시 alpha=255 전체 불투명 → 테두리 다 불투명 → false positive. `edge_opacity` 가 alpha 없으면 `None` 반환→스킵. 또 margin 을 프레임 1/4 로 클램프(초소형 프레임 오판 방지). 재검증: RGB 스킵·좌우끝 clip 0.62 정확·정상 RGBA(ai_paladin attack 11%→0.83) 회귀 없음 |
| **grid sheet 경로(`--texture-pack false`)** | 균일 128 통짜 sheet(`_sheet_build.py`, 1536×1024) 생성 경로에서도 검사+auto-fit 동작 — attack 26% clip → auto-fit 0.68 → 재렌더 잘림 0 → grid sheet 생성. **packed atlas·grid sheet 두 산출 방식 모두 검사·auto-fit 지원**(검사는 렌더 직후 낱장 기준이라 산출 방식과 무관) |
