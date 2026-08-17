---
name: texture-packer
description: Flutter Flame(flame_texturepacker) 게임을 위한 3D 모델(FBX/GLB/glTF/.blend)을 16방향(기본) sprite frame 으로 Blender 렌더한 뒤 libGDX TexturePacker 로 packed atlas(assets/<kind>/<name>/<name>.png + .atlas)로 묶는 texture-packing 파이프라인. 모든 셀 128px 고정, color compression(256색)·color brightness(밝기·대비)·EEVEE shading 을 기본 자동 적용(각각 옵션으로 끔), --output 으로 결과 폴더 지정 시 <output>/<kind>/<name>/ 자동 저장. 다음 경우 사용 — (1) "pc/mob/npc 를 texture packing 해줘", "sprite sheet 를 atlas 로 패킹", "packed atlas 생성", (2) 캐릭터/몬스터/NPC sprite 를 Flame atlas 로 굽기(sheet.py), (3) 기존 kind 재생성·교체, (4) 행동별 프레임 수(idle/walk/attack/hit/death/run·npc look/talk/wave) 조정, (5) grid 단일 sheet(--texture-pack false), (6) 결과를 뷰어/다른 앱 폴더에 저장(--output ./viewer/assets), (7) TexturePacker·발 정렬(align_feet)·256색 압축·pubspec 자동 갱신 이해/디버깅. sheet.py 등 packing 코드 전체를 소유. 키워드 — texture packing, texture-packer, packed atlas, sprite sheet packing, gdx TexturePacker, sheet.py, flame_texturepacker, pc/mob/npc packing, 16방향 아틀라스, .atlas, align_feet, 통짜 grid sheet, --output.
metadata:
  author: laryen
  version: "2.0"
---

# texture-packer — Flutter Flame sprite packing

Flutter Flame(`flame_texturepacker`) 게임을 위해 캐릭터·몬스터·NPC 의 3D 모델을
**16방향 sprite frame → packed atlas** 로 굽는 파이프라인 전체(`scripts/`)를 소유하는 스킬.
"pc/mob/npc 를 texture packing 해줘" 요청을 이 스킬의 `scripts/sheet.py` 로 자율 수행한다.
라리엔에서 출발했지만 특정 게임에 묶이지 않고 **Flame 을 쓰는 모든 프로젝트**에서 동작한다
(pubspec.yaml 이 있는 프로젝트 루트를 자동 탐색).

## 이 스킬이 소유한 코드 (모두 `scripts/` 안)

| 파일 | 역할 |
|---|---|
| `scripts/sheet.py` | **메인 CLI**(macOS). 렌더→packing→압축→pubspec 갱신 전 과정 오케스트레이션 |
| `scripts/_sheet_render.py` | Blender(`-b -P`)로 FBX/GLB/.blend → 방향별 frame PNG 렌더(EEVEE·밝기 부스트) |
| `scripts/_sheet_build.py` | `--texture-pack false` 시 균일 grid 단일 sheet 빌드 |
| `scripts/align_feet.py` | 프레임의 발(불투명 bbox 하단)을 셀 0.85 에 정렬(행동 전환 상하 점프 방지) |
| `scripts/verify_cells.py` | **cell 잘림(clip) 자동 검사** — 낱장 프레임 4 테두리 불투명 픽셀로 셀 밖 잘림 판정 + 행동별 권장 `--scale-<action>`(flutter 실행 불필요) |
| `scripts/check_all_cells.sh` | **배치 cell 잘림 검사** — 여러 자산(`game-assets/characters/*.blend` 등)을 한 번에 렌더·검사해 자산별 잘림 프로파일 표로 요약(빠른 전체 스캔·최소 프레임, 정밀은 실제 프레임 수로 개별 실행) |
| `scripts/sheet-win.py` | Windows 형제(빌드). sheet.py 와 동일 보조 스크립트 공유 |
| `scripts/sheet-preview.py` | **preview 시트**(macOS+Windows 공용). 기본 4방향, `--directions 1\|4\|8\|16` 으로 16방향까지. sheet.py 설정 재사용 + Windows Blender/Python 탐지 |
| `scripts/combine_to_runtime_sheet.py` | 행동별 256 sheet → 런타임 128 단일 16×60 sheet 합성(legacy) |
| `scripts/gen_all_sheets.sh` | 보유 PC/몬스터 모델 일괄 생성 헬퍼 |
| `scripts/tools/*.jar` | libGDX TexturePacker(gdx 1.13.1) — 없으면 sheet.py 가 Maven 에서 자동 다운로드 캐시 |

> 🛑 **`compress_image.py` 는 이 스킬 소유가 아니다.** 범용 PNG 압축 도구라 프로젝트
> `scripts/compress_image.py` 에 남아 있고, sheet.py 는 `ROOT/scripts/compress_image.py` 를
> 참조한다. 이 스킬 scripts/ 로 옮기지 않는다.

## 핵심: 어디서 실행해도 프로젝트 루트를 자동으로 찾는다

이 스킬의 스크립트는 `.claude/skills/texture-packer/scripts/` 에 있지만, 산출물은 **프로젝트
루트**의 `assets/`·`pubspec.yaml` 을 대상으로 한다. `sheet.py` 등은 `_find_project_root()`
로 루트를 견고하게 탐색한다 — ① 환경변수 `LARYEN_ROOT`(pubspec.yaml 검증)로 명시 override
→ ② skill 위치 기준 4단계 상위(`scripts→texture-packer→skills→.claude→루트`) → ③
`git rev-parse --show-toplevel` → ④ cwd. **따라서 cwd 와 무관하게 절대 경로로 실행하면 된다.**
다른 프로젝트에서 쓰려면 그 프로젝트에 이 skill 을 두거나 `LARYEN_ROOT=<프로젝트루트>` 를 준다.

## 기본 정책 (2.0 — 4가지 자동 적용)

신규 packing 은 아래를 **기본 자동 적용**한다. 각각 옵션으로 끌 수 있다.

| 자동 적용 | 기본값 | 끄는 법 |
|---|---|---|
| **모든 셀 128px 고정** | `--cell-size 128` (pc/mob/npc 전부) | (변경 비권장) `--cell-size N` 으로 다른 값 지정 가능 |
| **color compression** — 256색 FASTOCTREE 양자화(번들 용량 절감) | `--color-compression true` | `--color-compression false` (무손실 RGBA) |
| **color brightness** — exposure+gamma 밝기·대비 부스트 | `--vivid 9` (1~9) | `--vivid 1` (무보정) |
| **shading EEVEE** — PBR 3점 조명 렌더 | `--shading eevee` | `--shading texture` (WORKBENCH TEXTURE) |

> **왜 128 고정인가:** 게임 표시 크기(display 128)와 1:1 이라 축소 렌더가 없어 화질 손실이
> 거의 없고, atlas page 픽셀이 작아져 iOS 등에서 actor atlas RAM(OOM 위험)을 직접 낮춘다.
> RAM 은 W×H×4 로 고정 — 메모리 절감은 셀 픽셀(cell-size)로만, 디스크 절감은 색 압축으로만.

## 표준 워크플로우 (pc/mob/npc packing)

### 1. 실행 — kind 별 모델 폴더

### 🚀 가장 쉬운 사용법 — **경로만 준다** (2026-07-28)

```bash
python3 .claude/skills/texture-packer/scripts/sheet.py ./game-assets/characters/mob/chassis/chassis.blend
```

경로에 이미 정보가 다 들어 있으므로 **kind·name·애니메이션·`--auto` 를 자동으로 채운다**.
`--kind mob --name chassis --animations … --auto` 를 매번 적을 필요가 없다.

- **모델 형식** — `.blend` · `.fbx` · `.glb` · `.gltf` 모두 된다(확장자로 import 자동 분기).
  예: NPC 5종은 `.fbx` 모델이다.
- **kind·name 추론** — `characters/<kind>/<name>/<name>.<ext>` → 그 kind·name.
  pc 만 성별 단계가 하나 더 있다: `characters/pc/<gender>/<name>/<name>.<ext>`.
  구 폴더명 `blend/` 도 하위호환으로 받는다(2026-07-28 `characters/` 로 개명).
  name 은 **파일명이 아니라 폴더명**(폴더가 자산의 단위이고 애니도 그 폴더에 함께 놓인다).
  구조를 못 알아보면 조용히 추측하지 않고 경고 후 기존 흐름(대화형·명시 옵션)으로 간다.
- **애니메이션 3단 우선순위** 🛑 **2026-08-12 부터 캐릭터 전용 애니는 ①에 있다**(아래 참조)
  1. **모델과 같은 폴더**의 `idle/walk/attack/death.fbx` — **현행 표준**. 일부만 있어도 되고,
     부족한 행동은 아래 순위에서 자동으로 채워 한 폴더로 합성한다(`find_model_folder_anims`).
     프로젝트의 캐릭터·애니가 모두 Mixamo rig 로 통일돼 있어 부분 교체가 안전하다.
  2. `game-assets/animations/<name>/` — **거의 비어 있다**(하위호환 경로). 전용 세트 45종은
     2026-08-12 에 ①로 옮겨졌고, 지금 남은 것은 **공용 모션 라이브러리 15종**
     (`default`·`slash`·`punch`·`sword`·`stab`·`bite` 등 — 특정 캐릭터 것이 아니다).
  3. `--animations` 값 → 4. `default`
- 🛑 **`--animations default` 를 함부로 명시하지 말 것** — ①의 자동 선택을 *덮어써서* 그 캐릭터
  전용 동작을 범용 사람 동작으로 갈아끼운다. **에러가 나지 않아** 발견이 가장 어렵다(실측:
  crusher 를 `--animations default` 로 구웠더니 자세가 통째로 달라졌다, 2026-08-12).
  **평소에는 `--animations` 를 아예 주지 않는 것이 정답**이고, 예외는 비인간형의
  `--animations built-in`(내장 애니 강제 — 빠뜨리면 사람 걸음이 씌워진다) 뿐이다.
  전체 재굽기 명령은 `tools/build_regen_manifest.py` 가 이 규칙을 자동으로 지켜 생성한다.
- **`--auto` 자동** — 경로만 준 단축 호출일 때만 켜진다. **개별 옵션을 주면 그 값이 이긴다.**
- 기존 방식(`--character` + `--kind` + `--name` 명시)은 **그대로 동작**한다 — 추론이 개입하지 않는다.

| `--kind` | 모델 소스 폴더 | 방향 · cell · 화면 크기 | 행동(col) 순서 |
|---|---|---|---|
| `pc` | `game-assets/characters/pc/<gender>/<name>/` | 16방향 · 128 · 128 | idle · walk · attack · death · run |
| `mob` | `game-assets/characters/mob/<name>/` | 16방향 · 128 · 128 | idle · walk · attack · death (run 기본 제외) |
| `npc` | `game-assets/characters/npc/<name>/` | **1방향**(정면 S) · 128 · 128 | idle 단일(24프레임) |
| `boss` | `game-assets/characters/boss/<name>/` | **8방향** · **256** · **256**(화면 2배) | mob 과 동일 |
| `minion` | `game-assets/characters/minion/<name>/` | **8방향** · **64** · **64**(화면 절반) | mob 과 동일 |

> 🛑 **`hit`(피격) 은 2026-07-20 에 제거**됐다 — 게임에서 hit 포즈가 화면에 사실상 안 나오는데
> (피격 플래시·파티클·사운드가 대체) atlas 만 키웠다. `--hit N` 옵션은 존재하지 않는다.
>
> 🛑 **모델 소스 폴더는 `GAME-ASSETS.md` 가 SSOT**(2026-07-27 canonical). 과거의
> `game-assets/characters`·`game-assets/monsters` 는 **존재하지 않는 경로**다.

```bash
# ★ 권장 — 경로만 (kind·name·애니·--auto 자동)
python3 .claude/skills/texture-packer/scripts/sheet.py ./game-assets/characters/pc/male/male_vector/male_vector.blend
python3 .claude/skills/texture-packer/scripts/sheet.py ./game-assets/characters/mob/chassis/chassis.blend
python3 .claude/skills/texture-packer/scripts/sheet.py ./game-assets/characters/boss/halucion_boss/halucion_boss.blend

# 프레임 수 등 일부만 바꾸고 싶을 때 — 준 옵션이 추론·auto 보다 우선한다
# (미지정 시 kind 기본값: mob/boss/minion = idle8·walk12·attack10·death6, pc = 8·12·16·8·run12)
python3 .claude/skills/texture-packer/scripts/sheet.py ./game-assets/characters/mob/chassis/chassis.blend \
  --idle 8 --walk 12 --attack 10 --death 6

# NPC — game-assets/characters/npc/<name>/ 에서 자동으로 찾는다
python3 .claude/skills/texture-packer/scripts/sheet.py --kind npc --name shopkeeper

# 기존 방식(전부 명시)도 그대로 동작한다
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind mob --name chassis \
  --character game-assets/characters/mob/chassis/chassis.blend --animations default --auto
```

#### 🧩 한 시트를 **여러 .blend 로** 굽기 — 행동별 모델(per-action model)

행동마다 다른 모델 파일을 쓸 수 있다. 예를 들어 attack 만 무기를 든 별도 `.blend` 로 굽고
나머지는 기본 모델로 굽는다. **파일 이름 규약만 지키면 옵션이 필요 없다.**

```
game-assets/characters/pc/male/male_claudean/
  male_claudean.blend            ← 기본 모델(idle·walk·death·run)
  male_claudean_attack.blend     ← attack 열만 이 모델로 렌더 (자동 발견)
  idle.fbx walk.fbx attack.fbx death.fbx run.fbx   ← 애니메이션(그대로 공유)
```

```bash
# 아무 옵션도 필요 없다 — <파일이름>_<action>.<확장자> 형제를 자동으로 집는다
py .claude\skills\texture-packer\scripts\sheet-win.py .\game-assets\characters\pc\male\male_claudean\male_claudean.blend

# 파일 이름이 규약과 다르면 명시(자동 발견보다 우선)
… --character-attack game-assets/characters/pc/male/male_claudean/변형.blend

# 자동 발견을 끄고 기본 모델 하나로만 굽기
… --no-action-models
```

- **규약은 `<모델파일이름>_<action>.<확장자>`** — 접두사가 핵심이다. 같은 폴더의 애니메이션은
  `attack.fbx` 처럼 *행동 이름 그대로* 놓이므로(§애니메이션 3단 우선순위 ①), 접두사가 없으면
  애니를 모델로 오인한다. 대상 행동은 `idle·walk·run·attack·death`(npc `look·talk·wave`).
- **모델 수만큼 Blender pass 가 늘고 결과는 한 장으로 합쳐진다.** 로그에
  `per-action models — 2 Blender passes: …` 가 뜨고, 각 pass 는 *자기 행동의 낱장만* 다시 굽는다.
- 🛑 **프레이밍·측정의 권위는 기본 모델(첫 pass)** 이다. 행동별 모델 pass 는 기본 모델의
  `ortho`(확대율)를 물려받고 `_measure.json`(body_ratio/foot_anchor)을 덮어쓰지 않는다 —
  안 그러면 모델마다 bbox 가 달라 **attack 열만 캐릭터 크기가 튄다**. 중심 정렬·발 정렬은
  각 모델 것으로 계산되므로 자세가 달라도 발 높이는 맞는다.
- **애니메이션은 모든 pass 가 같은 폴더를 쓴다** — 행동별 모델도 Mixamo rig 여야 한다
  (`.blend` 는 rig 검사 면제, `--build-only` 도 면제).
- 실측(2026-08-17 · pc 16방향 5행동): 단일 모델 47초 vs 행동별 모델 2 pass 43초 —
  두 번째 pass 는 자기 행동만 굽기 때문에 총 시간이 거의 늘지 않는다.
- **`sheet-preview.py` 도 규약·옵션·프레이밍 상속이 전부 동일** 하다(2026-08-17 3-파일 동기화).
  본 굽기 전에 `sheet-preview.py <모델>` 로 4방향 미리보기를 먼저 뽑아 어느 열이 어느 모델로
  나오는지 눈으로 확인하면 된다 — 미리보기가 본 굽기와 *같은* 확대율·측정 권위를 쓰므로
  "미리보기에선 맞았는데 본 굽기에서 크기가 다르다" 가 생기지 않는다.

- 인자를 전부 생략하면 터미널에서 순서대로 물어본다(대화형).
- **신규 PC·몬스터는 반드시 16방향**(기본). `--directions 8` 은 boss/minion 규격이거나 legacy 재생성 전용.
- 일괄 재생성은 `scripts/regen_mobs.sh`·`regen_pc.sh`·`regen_npc.sh`.

### 2. 출력 (기본: 프로젝트 루트의 `assets/`)

```
assets/<kind>/<name>/<name>.png      # packed atlas 이미지 (256색 양자화)
assets/<kind>/<name>/<name>.atlas    # flame_texturepacker 가 읽는 trim/rotate 메타
```

`pubspec.yaml` 의 관리 블록(`# >>> AUTO(sheet.py packed actors) >>>`)에 자동 등록된다.

#### `--output` — 결과 폴더 지정 (뷰어/다른 앱용)

`--output <DIR>` 을 주면 `<DIR>/<kind>/<name>/` 을 **자동 생성**해 거기에 `.png`·`.atlas` 를 저장한다.

```bash
# → ./viewer/assets/pc/male_vector/male_vector.{png,atlas}
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind pc --name male_vector \
  --character game-assets/characters/pc/male/male_vector/male_vector.blend --animations default \
  --output ./viewer/assets
```

- 상대경로는 실행 위치(cwd)가 아니라 **프로젝트 루트 기준**으로 해석된다(결과 위치가 예측 가능).
- 🛑 `--output` 지정 시 **루트 `pubspec.yaml` 자동 갱신은 건너뛴다** — 대상이 다른 앱/뷰어일 수
  있어 루트 pubspec 을 오염시키지 않는다. 필요하면 대상 앱에 수동 등록한다.
- 중간 작업(frames) 폴더는 `--outputs`(복수형)로 따로 지정한다(이름 혼동 주의).

### 3. 게임 적용 & 검증

1. **앱 재빌드 필요** — atlas 는 AssetManifest 스캔으로 감지되므로 hot reload/restart 로는
   새 atlas 가 안 잡힌다. `ActorAnimationSet.loadActor(kind)` 계열이 `assets/<kind>/<name>/<name>.atlas`
   를 로드한다(프로젝트별 로더 규약을 따른다).
2. atlas 없는 pc/mob 은 투명 placeholder(안 보임)로 처리될 수 있다(프로젝트 로더 정책에 따름).
3. 시각 검증은 **실제 Flame 앱에서** 수행한다 — analyze/단위테스트로 갈음하지 않는다.

### 3.5 cell 잘림(clip) 방지 — 자동 검사·조정 워크플로우 (flutter 불필요)

pc/npc/mob 의 큰 모션(run/attack 등)이나 큰 자산(뿔·날개·무기)이 셀 밖으로 잘리는 것을,
flutter 실행 없이 **생성 이미지 검사만으로** 잡아 자동 조정한다:

1. **전체 스캔** — 어떤 자산이 잘리나 한 번에(진행 표시·예상 시간):
   ```bash
   bash scripts/check_all_cells.sh mob 'game-assets/characters/*.blend'
   # → 자산별 [i/N] ✅ 정상 / ⚠️ 잘린 행동 + 권장 --scale-<action>
   ```
2. **자동 조정 재생성** — 잘린 자산을 `--auto-fit-scale` 로:
   ```bash
   sheet.py --kind mob --name <name> --character <file> --auto-fit-scale
   # 잘림 감지 → scale step 하강 → 재렌더 → 잘림 0 수렴(최대 6회, 0.6 하한)
   ```
   🛑 `--auto-fit-scale` 을 켜면 `--scale-<action>`·전역 `--scale` 은 **모두 무시** 되고 1.0(원본)에서
   시작해 auto-fit 이 필요한 만큼만 하강한다(대화형 scale 질문도 생략). scale 을 직접 지정하려면
   `--auto-fit-scale` 없이 `--scale-<action>` 을 쓴다(둘은 배타적 사용).
3. **개별 정밀 검사**(선택): `sheet.py … --render-only`(렌더 후 자동 검사) 또는
   `verify_cells.py --frames outputs/<name>/frames`.

🛑 원리: 작게 구운 scale 은 `.atlas` 의 `laryen.actionScale` 메타로 기록돼 게임 런타임이
`1/scale` 로 **원래 크기 복원** — 잘림 방지(작게 굽기)와 화면 크기(원래)가 분리된다.
난이도별 수렴(실측): 작은 잘림 1회 최소 하강 · 여러 행동 1회 · 큰 top 잘림 step 하강 여러 회
· 물리적 불가(여백 없음)만 0.6 하한 안전종료 + margin 조정 안내(상세 [references/pipeline.md §9](references/pipeline.md)).

### 4. 옵션 요약 (자세한 로직·소스는 [references/pipeline.md](references/pipeline.md))

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--output DIR` | (없음→`assets/`) | 결과 저장 베이스 폴더. `<DIR>/<kind>/<name>/` 자동 생성(pubspec 갱신 생략) |
| `--texture-pack {true\|false}` | true | true=packed atlas, false=grid 단일 sheet(`_sheet_build.py`) |
| `--cell-size N` | 128 | atlas orig/cell 픽셀(pc/mob/npc 전부 128 고정) |
| `--color-compression {true\|false}` | true | 256색 FASTOCTREE 양자화(디스크만 절감, RAM 무관) |
| `--vivid 1-9` | 9 | 밝기(exposure)+대비(gamma) 부스트. 1=무보정, 9=최대(기본) |
| `--shading {eevee\|texture}` | eevee | eevee=PBR 3점 조명, texture=WORKBENCH TEXTURE(금속/갑옷용) |
| `--render-res N` | max(256,cell) | frame 렌더 해상도(→ 128 로 자동 축소, `--scale-frames`) |
| `--idle/--walk/--attack/--death/--run N` | **kind 마다 다르다** — pc/npc `8/12/16/8/12`(`DEFAULT_FRAMES`) · **mob·boss·minion `8/12/10/6/12`**(`MONSTER_FRAMES`, 2026-08-12) | 행동별 프레임 수. 🛑 **`--hit` 은 없다** — hit 는 2026-07-20 규격에서 제거됐다(`FRAME_OPTION_ACTIONS`). 몬스터가 pc 보다 적은 이유·재생 속도 보존은 아래 §몬스터 프레임 규격 참조 |
| `--look/--talk/--wave N` | 8 | npc 전용 행동 프레임 수 |
| `--scale-<action>` | **미지정 시 대화형 질문**(기본 제안 **전부 1.0** — `SCALE_PROMPT_DEFAULTS`; 비대화형은 그 값 적용) | 행동별 생성 scale. `<1` 이면 모델을 작게 구워(무기/모션 128 셀 밖 잘림 방지) `.atlas` 의 `laryen.actionScale.<action>` 메타에 기록 → **게임 런타임이 1/scale 로 원래 크기 복원**([references/pipeline.md](references/pipeline.md) §6). 🛑 과거의 **walk 0.9 · attack 0.8 일괄 축소 프리셋은 폐기**됐다(2026-07-09 셀 확대 전환) — 셀 확대는 atlas RAM(iOS OOM)·page 폭(8192 한계)을 키우므로 *잘리지 않는 행동까지 무조건 키우지 않는다*. 잘리는 행동만 `--auto-fit-scale` 이 검출해 낮춘다. 🛑 `--auto-fit-scale` 사용 시 이 값은 **무시** 됨(1.0 에서 자동 조정) |
| `--weapon / --weapon-bone …` | — | 무기 손 본 장착 |
| `--character-<action> PATH` | — | **행동별 모델** — 그 행동만 다른 모델(.blend/.fbx/.glb)로 렌더해 같은 시트에 합친다(모델별 Blender pass). 대상 행동 `idle·walk·run·attack·death`(npc `look·talk·wave`) |
| `--action-models {true\|false}` | **true** | 모델 옆 `<파일이름>_<action>.<확장자>` 형제를 그 행동에 **자동** 사용(예 `male_claudean_attack.blend` → attack). `--no-action-models` 로 끔. 🛑 접두사 없는 `<action>.fbx` 는 *애니메이션* 이라 대상이 아니다 |
| `--directions {8\|16}` | 16(npc 8) | 신규는 16 고정. 8 은 legacy 재생성 전용 |
| `--run-animation {true\|false}` | — | mob run 애니 포함 여부(지정 시 대화형 질문 생략) |
| `--rotation [true\|false]` | **actor kind 는 false · 그 외 true** (미지정 시 대화형 질문·기본 제안 Y·**비대화형은 `kind not in ACTOR_KINDS`**) | 회전 packing(공간 절약·page 픽셀↓=RAM↓). 🛑 **`ACTOR_KINDS = ALL_KINDS` 라 pc·mob·npc·boss·minion 은 전부 actor** — 비대화형·`--auto` 어느 경로로도 **자동으로 false** 가 된다(발 어긋남·16방향 패킹 20분+ 방지). 대화형 질문에는 n 권장 경고가 뜬다. 정적 타일/decor 는 true 가 이득. `--no-rotation` 은 false 별칭 |
| `--strip-x-whitespaces [true\|false]` | **true**(미지정 시 대화형·비대화형 true) | 가로(X) 여백 trim. 좌우 투명 여백 제거 → 아틀라스 폭·page 픽셀(=RAM)↓(발 y 무관·안전) |
| `--strip-y-whitespaces [true\|false]` | **true**(미지정 시 대화형·비대화형 true) | 세로(Y) 여백 trim. 상하 투명 여백 제거 → page 높이·RAM↓. 발 점프(drop off)는 pack 후 `.atlas` offsetY 를 top-left 로 보정해 방지(libGDX bottom-left↔flame top-left 좌표계 정합, `fix_offset_y`) |
| `--strip-whitespace`·`--keep-whitespace` | (하위호환) | `--strip-x/y-whitespaces` 를 **동시** 설정하는 별칭 |
| `--render-only / --build-only` | — | 렌더만 / packing만 |
| `--outputs PATH` | `outputs/<name>` | 중간 frames 작업 폴더(결과 폴더인 `--output` 과 다름) |
| `--packer-cp PATH` | — | gdx jar classpath 수동 지정(기본은 `scripts/tools/` 자동) |
| `--verbose` | off | Blender/packer **전체 로그** 출력. 미지정(기본) 시 **간략 진행**만: 단계 `[1]렌더 [2]packing`, `N/총장(%)·장/s·ETA·현재 행동`, 단계별·총 소요시간(`✓ 렌더 완료 — 1024장 · 3m18s · 5.2장/s`) |
| `--verify-cells [true\|false]` | **true** | 렌더 후 낱장 프레임의 **cell 잘림(clip) 자동 검사**(flutter 불필요). run/attack 등 큰 모션이 셀 밖으로 잘리면 행동별 권장 `--scale-<action>` 출력. `--build-only`(재packing) 시에도 기존 프레임을 검사해 리포트(auto-fit 은 렌더 경로만) |
| `--auto-fit-scale` | off | 잘린 행동 발견 시 **scale 을 낮춰 자동 재렌더**(최대 6회·0.6 하한 → 잘림 0 수렴). pc/npc/mob 큰 모션·칼끝을 사람 개입 없이 셀 안에 맞춤. 🛑 **이 옵션을 켜면 `--scale-<action>`·전역 `--scale` 은 모두 무시** 되고 1.0(원본)에서 시작해 필요한 만큼만 하강(대화형 scale 질문도 건너뜀) |
| `--auto` | off | 🚀 **원클릭 최적 프리셋** — `--texture-pack true --auto-fit-scale --color-compression true --vivid 9 --strip-x-whitespaces true --strip-y-whitespaces true --shading eevee` 를 한 번에 켠다(`shading` 의 `true`=`eevee`). **rotation 은 `kind not in ACTOR_KINDS` 로 정해지므로 pc/mob/npc/boss/minion 이면 자동 false** — `--rotation false` 를 따로 병기할 필요가 없다. **`--kind mob` 이면 `--run-animation false` 도 자동**(run 애니 제외·디스크↓). **대화형 질문(texture-pack·color-compression·rotation·strip·scale·run-animation) 전부 없이** 잘림 없이 자동 조정 + 최대 압축으로 패킹. 🛑 개별 옵션을 함께 명시하면 **그 값이 우선**(auto 는 미지정 항목만 채움) — 예 `--auto --run-animation true` 는 mob 이라도 run 포함. auto-fit 이 켜지므로 `--scale-<action>`·전역 `--scale` 무시(1.0 자동 하강) |

## 런타임: Flutter/Flame 이 `.atlas`/`.png` 를 파싱해 게임 월드에 표시

packing 결과물이 게임에서 로드·렌더되는 소비 측 흐름(전체 소스·복구 SSOT 는
[references/flame-runtime.md](references/flame-runtime.md)):

```
assets/<cat>/<name>/<name>.{atlas,png}  (cat=pc|mob)
  ① AssetManifest 스캔 → name→cat (hasActorAtlas)            ← 앱 재빌드 필요(번들 시 고정)
  ② TexturePackerAtlas.load(path, useOriginalSize:true)      ← flame_texturepacker 가 trim/rotate 복원
  ③ atlas.findSpritesByName('walk_E') → SpriteAnimation.spriteList(frames, stepTime, loop)
       → _table[state][dir16]  (6 state × 16 dir)
  ④ MobComponent/PlayerComponent(=SpriteAnimationComponent):
       animation = animSet.getDir16(state, facing16)
       size = kActorDisplaySize × displayScaleFor(state)      ← laryen.actionScale 메타 배율 복원
       anchor = (0.5, 0.85);  position = worldToScreen(서버 world cm)   ← isometric 투영
```

핵심 규약(디버깅 시 이 값이 어긋나면 sprite 안 보임/깨짐):
- **region 이름** = `<action>_<DIR16>`(예 `walk_E`·`attack_SSW`) — packing 의 row/action 순서와
  런타임 `_atlasActions`·`kDir16Labels`(FLARE16)가 **동일 SSOT** 여야 정합.
- **atlas 추가/교체 후 앱 재빌드 필수** — `AssetManifest` 는 빌드 시 번들되어 hot reload/restart
  로 새 atlas 가 안 잡힌다.
- **pc/mob 는 오직 atlas 에서만 로드**(격자 폐기). 없으면 투명 placeholder + `missingAtlasKinds`
  리포트 → `sheet.py` 로 재생성.
- 화면 크기 = `kActorDisplaySize`(128), 발 정렬 `anchor (0.5,0.85)`, 행동 배율은 `.atlas` 의
  `laryen.actionScale.<action>` 메타에서 자동 복원(1/생성scale).

관련 코드: [actor_animation_set.dart](../../../lib/features/game/render/actor_animation_set.dart)
(`loadActorAtlas`·`_buildAtlasTable`·`getDir16`·`parseDisplayScales`) ·
[mob_component.dart](../../../lib/features/game/render/mob_component.dart) ·
[iso_projection.dart](../../../lib/features/game/render/iso_projection.dart).

## 실전 검증 예시 — `flutter/`(laryen_actor_viewer) 뷰어 앱으로 맵에 몹 띄우고 증명하기

이 리포에는 packing 결과를 **바로 눈으로 확인**하는 Flame 뷰어 앱 `flutter/`
(`laryen_actor_viewer`, flame 1.37 · flame_texturepacker 5.1)가 들어있다. `sheet.py`
로 구운 mob/pc atlas 를 이 앱 맵(잔디·도로·건물) 위에 스폰해 16방향·애니메이션·발
정렬을 실제로 검증한다. human-developer 가 "몬스터를 맵에 어떻게 띄워 확인하냐" 물으면
아래 순서를 그대로 안내한다. **아래는 `dreyer.blend`(망치 든 몬스터)로 실제 검증한 예다.**

### 1) atlas 를 뷰어 앱 assets 폴더로 굽기 — `--output ./flutter/assets`

```bash
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind mob --name dreyer \
  --character ./game-assets/mob/dreyer.blend --animations default \
  --output ./flutter/assets \
  --scale-attack .8
```

→ `flutter/assets/mob/dreyer/dreyer.{png,atlas}`(16방향 × idle8·walk12·attack10·death6
= **576 프레임** — mob 은 `MONSTER_FRAMES`, 2026-08-12). dreyer 는 hand 본에 **hammer(망치)** 가 붙어있어 body-only
framing 이 자동 적용(무기 1개 제외)되고, `--scale-attack .8` 은 `.atlas` 에
`laryen.actionScale.attack: 0.8` 메타로 주입 → 런타임이 1/0.8=**1.25 로 화면 보정**한다.

### 2) 뷰어 앱 pubspec 등록 + kind 별 로드/스폰 코드

`--output` 저장은 **루트** pubspec 만 건너뛴다. 대상은 뷰어 앱이므로 그 pubspec 에 수동 등록:

```yaml
# flutter/pubspec.yaml → flutter: assets:
    - assets/mob/hellion/
    - assets/mob/dreyer/      # ← 추가하고 flutter pub get
```

`lib/game/viewer_game.dart` 가 kind 별 atlas 를 `ActorAnimationSet.loadFrom(atlas,png)`
로 읽어 `_spawnWave()` 에서 맵에 스폰한다. **kind 당 1마리씩** 띄우려면 애님셋을 kind
별로 따로 로드하고 스펙 리스트로 1마리씩 스폰한다(hellion 왼쪽·dreyer 오른쪽):

```dart
_hellionAnimSet = await ActorAnimationSet.loadFrom(
    'assets/mob/hellion/hellion.atlas', 'assets/mob/hellion/hellion.png');
_dreyerAnimSet  = await ActorAnimationSet.loadFrom(
    'assets/mob/dreyer/dreyer.atlas',  'assets/mob/dreyer/dreyer.png');
// _spawnWave(): [(hellion,-240,40), (dreyer,240,40)] → kind 당 정확히 1마리
```

atlas 로드 실패(파일 없음/계약 불일치)면 그 kind 는 붉은 placeholder 로 뜬다 → `sheet.py`
재생성 신호. region 이름은 `<action>_<DIR16>` 규약이라 packing row 순서와 자동 정합한다.

### 3) 앱 실행 + 스크린샷으로 증명 (macOS)

```bash
cd flutter && flutter pub get
flutter run -d macos --debug          # 첫 빌드 수 분, 이후 증분 빌드는 수십 초
# 앱 창을 앞으로 세우고(자동 foreground 실패 대비) 창 영역만 캡처
osascript -e 'tell application "System Events" to tell process "laryen_actor_viewer" to set frontmost to true'
osascript -e 'tell application "System Events" to tell process "laryen_actor_viewer" to get {position, size} of window 1'
screencapture -x -R "x,y,w,h" tmp/proof.png     # 위 bounds 로 R 지정
```

앱이 뜨면 맵 위에서 PC(g)와 몹이 16방향 스프라이트로 걸어다니며 배틀한다. **atlas 교체·
추가 후에는 hot reload 로 안 잡히므로 앱을 재실행**(`flutter run` 종료 후 재실행 또는 Hot
restart)해야 새 atlas 가 번들된다. 코드 변경만이면 종료→재실행이 가장 확실하다.

### ⚠️ 색 압축은 **프로젝트 루트의 `scripts/compress_image.py` 유무**에 달려 있다

`--color-compression true`(기본)이면 `sheet.py` 가 `_find_project_root()` 로 찾은 루트의
`scripts/compress_image.py` 를 import 해 256색 양자화를 **in-place** 로 돌리고, import 가
실패하면 `uv run --with numpy --with pillow` 서브프로세스로 폴백한다.

- **그 파일이 있는 프로젝트**(예: laryen)에서는 **정상 동작한다** — 예전에 "이 리포엔 없어서
  스킵된다" 고 적혀 있던 서술은 **texture-packer 를 단독 clone 한 환경**의 이야기였다.
- **판정은 파일 존재 여부를 추측하지 말고 로그로 한다** — 출력에 **`⚠️ 압축 실패` 가 없으면
  압축된 것**이다.
- 없는 환경이면 256색 양자화가 스킵돼 무손실 RGBA PNG 가 그대로 남는다(디스크/번들만 커지고
  **atlas·게임 동작·RAM 엔 무관**). 줄이려면 그 스크립트를 루트 `scripts/` 에 두거나
  `pngquant --force 256 <파일>.png -o <파일>.png` 로 후처리한다.

🛑 **압축은 디스크만 줄인다. RAM 은 1바이트도 줄지 않는다**(`RAM ≈ 원본 PNG W × H × 4`).
RAM 을 줄이는 길은 셀 크기·프레임 수·자산 종류를 줄이는 것뿐이다.

## 절대 규칙

- **신규 캐릭터/몬스터 sprite 는 16방향·128 cell 만.** "8방향으로 만들어 달라"는 거절하고
  16방향으로 안내한다(짝수 row 가 8방향과 동일하므로 8방향이 필요해도 16 한 장이면 됨).
  - 🛑 **예외 — `--kind boss` · `--kind minion` 은 8방향이 규격이다**(2026-07-27 사용자 지시로
    신설). 보스는 소수 개체가 크게 등장하고 졸개는 다수가 작게 등장해, 둘 다 방향 해상도를
    절반으로 줄여 디스크·RAM 을 아끼는 것이 의도된 설계다. **이 두 kind 를 16방향으로
    "고쳐" 재생성하지 말 것** — 그것이 회귀다. `minion` 은 추가로 **cell 64 · 화면 표시 64**
    (다른 몹의 절반 크기)가 규격이다.
  - 8방향 sheet 의 region 접미사는 FLARE16 의 **짝수** 라벨(`E,SE,S,SW,W,NW,N,NE`)이고,
    런타임은 `.atlas` 헤더의 `laryen.directions: 8` 을 읽어 8칸 table 을 만든 뒤 16방향 facing 을
    `nearest8FromDir16` 으로 근사한다. 이 세 가지(생성 라벨·메타·런타임 근사)는 한 세트라
    하나만 바꾸면 방향이 통째로 어긋난다.
- 🛑 **몬스터 프레임 규격 — `idle 8 · walk 12 · attack 10 · death 6`(36프레임)**
  (2026-08-12 사용자 지시, `MONSTER_FRAMES`). pc/npc 는 종전대로 `8/12/16/8`+`run 12`(44프레임).
  - **왜 몬스터만 줄이나**: RAM ≈ page W×H×4 이고 packing 충전율이 89% 라 **셀 수 감축이 그대로
    RAM 감축**이다(전 종 실측 1112.4→899.3MB, **-19.2%** · 디스크 83.4→67.4MB). 화면에 동시에
    뜨는 개체 수가 압도적으로 많은 쪽이 몬스터라 같은 비율이라도 절대 절감량이 훨씬 크다.
    행동별 실픽셀 비중(mob 53종 실측) attack 38.4% · walk 26.5% · idle 17.9% · death 16.9% →
    무거운 attack(16→10)과 잠깐만 보이는 death(8→6)를 먼저 깎고, 상시 노출되는 idle 은 8 유지.
  - **화질 손실 0** — 축소 디코드(저사양 60%)와 달리 픽셀은 그대로 두고 낱장 수만 줄인다.
    확보한 예산을 축소 비율 완화에 되돌려 쓸 수 있다(`REGRESSION.md` §16).
  - 🛑 **재생 속도는 클라가 흡수한다** — `actor_animation_set.dart` 의 `_atlasActions` 는
    (낱장당 시간)이 아니라 **한 바퀴 목표 시간**을 갖고 `stepTime = cycle / frames.length` 로
    나눠 쓴다. 그래서 attack 이 pc 16장·mob 10장이어도 **둘 다 0.80초**다. 이 설계를 되돌려
    stepTime 을 고정하면 프레임을 줄인 자산만 애니가 빨라진다(발이 헛도는 "종종걸음").
  - **기존 자산 재작업은 Blender 재렌더 없이** 가능하다 — 출고 `.atlas`+`.png` 에서 낱장을
    복원 → 균등 데시메이션 → `--build-only` 재패킹(종당 ~16초, 전 종 65개 약 4분). 이때
    ① `--scale-frames 1.0`(자동값 0.5 는 이미 최종 크기인 낱장을 반토막 낸다)
    ② 원본 `laryen.actionScale.<action>` 을 `--scale-<action>` 으로 **재주입**(빠뜨리면 공격 시
    몬스터 크기가 틀어진다) ③ 8방향 자산은 `--directions 8` — 셋 다 필수다.
- 🛑 **`--build-only` 는 Mixamo rig 검사를 하지 않는다** — Blender 를 아예 띄우지 않아 모델·애니의
  rig 규격이 결과에 영향을 주지 않기 때문이다. 이 예외가 없으면 비인간형 자산(minion 등)은
  *재패킹조차* 못 한다(실측 `mini_red`). 렌더 경로(`--build-only` 없음)에서는 종전대로 검사한다.
- 🛑 **재굽기 뒤에는 반드시 `python3 tools/check_atlas_health.py` 를 돌린다 (2026-08-12 실측 사고)**
  — Blender 는 텍스처를 못 찾아도 **에러 없이 마젠타(분홍)로 렌더**한다. 굽기 로그는 "완료"라고
  나오고 프레임 수·방향·메타도 전부 정상이라 **픽셀을 보지 않으면 절대 못 잡는다.** 실제로 다른
  팀이 65종을 구워 커밋했는데 **ramon 73% · spider_cannon 86% · skitter 15%** 가 분홍색이었다.
  이 도구는 마젠타 비율·빈 이미지·프레임 규격·index 연속성·`.atlas` size ↔ PNG 세대 정합을 한 번에
  본다(문제 0이면 exit 0 이라 그대로 게이트로 쓸 수 있다). 손상되면 `git checkout` 으로 되돌린다.
- 🛑 **굽기 전에 `git lfs pull`** — 3D 모델(`.blend`)은 Git LFS 라 clone 직후엔 134바이트 포인터다.
  그 상태로 구우면 그 종은 전부 `File format is not supported` 로 실패한다(같은 사고에서
  **23종 실패 중 20종**이 이것이었고 107분을 버렸다). `build_regen_manifest.py` 가 이제 굽기 전에
  검사해 매니페스트 자체를 만들지 않고 `git lfs pull` 을 안내한다.
- 🛑 **자산을 다시 구웠으면 R2 발행까지 해야 사용자에게 간다 (2026-08-12 cowork 감사에서 적발)**
  — 몬스터·PC 상당수가 **앱 번들이 아니라 R2 lazy download** 다(`tools/assets/remote_assets.yaml`
  이 SSOT — 실측 몬스터 65종 중 **36종**이 `mob-dungeon`·`mob-seoul-districts` 팩). `assets/` 만
  다시 굽고 끝내면 **로컬만 새것이고 사용자 기기는 계속 구 자산을 받는다**(실측: 프레임 감축 직후
  R2 는 여전히 구 팩 `dba13c81`/25.29MiB 를 서빙 중이었다).
  - 확인: `python3 tools/assets/publish_r2.py --env staging --dry-run` 으로 로컬 `contentHash` 를
    구하고, `curl -s https://assets.laryen.com/catalog/{staging,production}.json` 의 해시와 비교한다.
    **다르면 아직 안 나간 것**이다.
  - 발행: `python3 tools/assets/publish_r2.py --env staging` (AI 자율 — production 무영향).
  - 🛑 **production 발행은 클라 릴리스 *뒤* 에** — R2 팩은 앱 버전과 무관하게 내려가므로, *구 클라 +
    새 자산* 조합이 생기면 그 자산만 애니가 빨라진다(구 클라는 고정 stepTime, 새 자산은 프레임이
    적다 → walk 1.2배·attack 1.6배 "종종걸음"). 자산 규격을 바꾸는 재굽기에서는 **새 클라가 스토어에
    올라간 뒤** production 을 발행한다. `minClientVersion` 을 올려 막는 방법은 **쓰지 말 것** — 구 클라가
    catalog 를 통째로 무시해 *신규 설치 사용자에게 그 몬스터가 아예 안 보인다*(더 나쁘다).
- 🛑 **`outputs/<name>/frames` 의 낱장은 세대를 신뢰하지 말 것** — 재렌더 원본이 남아 있어도 그것이
  현재 출고본과 같은 세대라는 보장이 없다(실측: 같은 crusher 인데 page 3792 vs 4147 로 불일치, 그리고
  프레임 감축 후에도 `outputs/*/_sheet_config.json` 109개가 `"attack": 16` 구 규격으로 남아 있다).
  거기서 `--build-only` 를 돌리면 **조용히 구 규격으로 원복된다.** 현재 픽셀을 보존하며 재작업하려면
  낱장을 **출고 `.atlas`+`.png` 에서 복원**해 쓴다.
- **캐릭터·애니 모델은 Mixamo rig**(본 이름 `mixamorig:`). PC 는 부위별 overlay 합성 없이
  세트 단위 통짜 sheet. 몬스터는 장비 분리 없이 전체 모델 렌더.
- **RAM 은 W×H×4 로 고정** — `--color-compression` 은 디스크/번들 용량만 줄인다(OOM 무관).
  메모리 절감은 픽셀 축소(`--cell-size`)·**프레임 수 감축**으로만.
- **검증 불가 시 원점 복구** — packing 결과를 실제 Flame 앱으로 시각 검증하지 못하면 커밋하지 않는다.

## 관련 워크플로우

- **texture-packer(이 스킬)** = packing 파이프라인 코드(sheet.py 계열)의 *소유·실행·SSOT*.
- 상위 자산 생성 워크플로우(확장자 자동감지·내장 애니 매칭 안내 등)는 실행 단계에서 이 스킬의
  `scripts/sheet.py` 를 호출한다. 3D 모델 자체 생성(참조 이미지 기반) 뒤 sprite packing 은 이 스킬로.
