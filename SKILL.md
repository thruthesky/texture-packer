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
| `scripts/check_all_cells.sh` | **배치 cell 잘림 검사** — 여러 자산(`game-assets/blend/*.blend` 등)을 한 번에 렌더·검사해 자산별 잘림 프로파일 표로 요약(빠른 전체 스캔·최소 프레임, 정밀은 실제 프레임 수로 개별 실행) |
| `scripts/sheet-win.py` · `sheet-preview-win.py` | Windows 형제(빌드/preview). sheet.py 와 동일 보조 스크립트 공유 |
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
| **color brightness** — exposure+gamma 밝기·대비 부스트 | `--vivid 5` (1~9) | `--vivid 1` (무보정) |
| **shading EEVEE** — PBR 3점 조명 렌더 | `--shading eevee` | `--shading texture` (WORKBENCH TEXTURE) |

> **왜 128 고정인가:** 게임 표시 크기(display 128)와 1:1 이라 축소 렌더가 없어 화질 손실이
> 거의 없고, atlas page 픽셀이 작아져 iOS 등에서 actor atlas RAM(OOM 위험)을 직접 낮춘다.
> RAM 은 W×H×4 로 고정 — 메모리 절감은 셀 픽셀(cell-size)로만, 디스크 절감은 색 압축으로만.

## 표준 워크플로우 (pc/mob/npc packing)

### 1. 실행 — kind 별 모델 폴더

| `--kind` | 모델 소스 폴더 | 행동(col) 순서 |
|---|---|---|
| `pc` | `game-assets/characters/` | idle · walk · attack · hit · death · run |
| `mob` | `game-assets/monsters/` | idle · walk · attack · hit · death (run 기본 제외) |
| `npc` | `game-assets/blend/` | idle · look · talk · walk · wave (8방향) |

```bash
# PC — Mixamo rig FBX + 애니메이션 폴더(game-assets/animations/<variant>)
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind pc --name male_victor \
  --character game-assets/characters/male_victor.fbx --animations default \
  --idle 8 --walk 12 --run 12 --attack 16 --hit 8 --death 8

# 몬스터 — 장비 분리 없이 전체 모델 16방향
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind mob --name demonic_king \
  --character game-assets/monsters/demonic_king.fbx --animations default

# NPC — .blend, npc 전용 행동(8방향)
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind npc --name shopkeeper --character game-assets/blend/shopkeeper.blend
```

- `--character` 는 절대/상대 경로 또는 파일명만(파일명이면 `game-assets/<kind별폴더>/` 에서 찾음).
- 인자를 생략하면 터미널에서 순서대로 물어본다(대화형). 자율 실행 시 인자를 모두 준다.
- **신규 PC·몬스터는 반드시 16방향**(기본). `--directions 8` 은 legacy 재생성 전용.

### 2. 출력 (기본: 프로젝트 루트의 `assets/`)

```
assets/<kind>/<name>/<name>.png      # packed atlas 이미지 (256색 양자화)
assets/<kind>/<name>/<name>.atlas    # flame_texturepacker 가 읽는 trim/rotate 메타
```

`pubspec.yaml` 의 관리 블록(`# >>> AUTO(sheet.py packed actors) >>>`)에 자동 등록된다.

#### `--output` — 결과 폴더 지정 (뷰어/다른 앱용)

`--output <DIR>` 을 주면 `<DIR>/<kind>/<name>/` 을 **자동 생성**해 거기에 `.png`·`.atlas` 를 저장한다.

```bash
# → ./viewer/assets/pc/male_victor/male_victor.{png,atlas}
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind pc --name male_victor \
  --character game-assets/characters/male_victor.fbx --animations default \
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
   bash scripts/check_all_cells.sh mob 'game-assets/blend/*.blend'
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
| `--vivid 1-9` | 5 | 밝기(exposure)+대비(gamma) 부스트. 1=무보정, 9=최대 |
| `--shading {eevee\|texture}` | eevee | eevee=PBR 3점 조명, texture=WORKBENCH TEXTURE(금속/갑옷용) |
| `--render-res N` | max(256,cell) | frame 렌더 해상도(→ 128 로 자동 축소, `--scale-frames`) |
| `--idle/--walk/--attack/--hit/--death/--run N` | 8/12/16/8/8/12 | 행동별 프레임 수 |
| `--look/--talk/--wave N` | 8 | npc 전용 행동 프레임 수 |
| `--scale-<action>` | **미지정 시 대화형 질문**(기본 제안 idle 1.0 · walk 0.9 · run 0.9 · attack 0.8 · hit 0.9 · death 1.0; npc 는 idle·walk 만·비대화형은 기본 제안값) | 행동별 생성 scale. 지정 안 하면 개발자에게 물어봄. `<1` 이면 모델을 작게 구워(무기/모션 128 셀 밖 잘림 방지) `.atlas` 의 `laryen.actionScale.<action>` 메타에 기록 → **게임 런타임이 1/scale 로 원래 크기 복원**([references/pipeline.md](references/pipeline.md) §6). 🛑 `--auto-fit-scale` 사용 시 이 값은 **무시** 됨(1.0 에서 자동 조정) |
| `--weapon / --weapon-bone …` | — | 무기 손 본 장착 |
| `--directions {8\|16}` | 16(npc 8) | 신규는 16 고정. 8 은 legacy 재생성 전용 |
| `--run-animation {true\|false}` | — | mob run 애니 포함 여부(지정 시 대화형 질문 생략) |
| `--rotation [true\|false]` | **true**(미지정 시 대화형 질문·기본 제안 Y·비대화형은 true) | 회전 packing(공간 절약·page 픽셀↓=RAM↓). 🛑 actor(pc/mob/npc)는 발 어긋남·패킹 지연 위험이 있어 대화형 질문에 n 권장 경고가 뜬다(명시적으로 `--rotation false` 로 끌 수 있음). 정적 타일/decor 는 true 가 이득. `--no-rotation` 은 false 별칭 |
| `--strip-x-whitespaces [true\|false]` | **true**(미지정 시 대화형·비대화형 true) | 가로(X) 여백 trim. 좌우 투명 여백 제거 → 아틀라스 폭·page 픽셀(=RAM)↓(발 y 무관·안전) |
| `--strip-y-whitespaces [true\|false]` | **true**(미지정 시 대화형·비대화형 true) | 세로(Y) 여백 trim. 상하 투명 여백 제거 → page 높이·RAM↓. 발 점프(drop off)는 pack 후 `.atlas` offsetY 를 top-left 로 보정해 방지(libGDX bottom-left↔flame top-left 좌표계 정합, `fix_offset_y`) |
| `--strip-whitespace`·`--keep-whitespace` | (하위호환) | `--strip-x/y-whitespaces` 를 **동시** 설정하는 별칭 |
| `--render-only / --build-only` | — | 렌더만 / packing만 |
| `--outputs PATH` | `outputs/<name>` | 중간 frames 작업 폴더(결과 폴더인 `--output` 과 다름) |
| `--packer-cp PATH` | — | gdx jar classpath 수동 지정(기본은 `scripts/tools/` 자동) |
| `--verbose` | off | Blender/packer **전체 로그** 출력. 미지정(기본) 시 **간략 진행**만: 단계 `[1]렌더 [2]packing`, `N/총장(%)·장/s·ETA·현재 행동`, 단계별·총 소요시간(`✓ 렌더 완료 — 1024장 · 3m18s · 5.2장/s`) |
| `--verify-cells [true\|false]` | **true** | 렌더 후 낱장 프레임의 **cell 잘림(clip) 자동 검사**(flutter 불필요). run/attack 등 큰 모션이 셀 밖으로 잘리면 행동별 권장 `--scale-<action>` 출력. `--build-only`(재packing) 시에도 기존 프레임을 검사해 리포트(auto-fit 은 렌더 경로만) |
| `--auto-fit-scale` | off | 잘린 행동 발견 시 **scale 을 낮춰 자동 재렌더**(최대 6회·0.6 하한 → 잘림 0 수렴). pc/npc/mob 큰 모션·칼끝을 사람 개입 없이 셀 안에 맞춤. 🛑 **이 옵션을 켜면 `--scale-<action>`·전역 `--scale` 은 모두 무시** 되고 1.0(원본)에서 시작해 필요한 만큼만 하강(대화형 scale 질문도 건너뜀) |
| `--auto` | off | 🚀 **원클릭 최적 프리셋** — `--texture-pack true --auto-fit-scale --color-compression true --vivid 5 --rotation true --strip-x-whitespaces true --strip-y-whitespaces true --shading eevee` 를 한 번에 켠다(`shading` 의 `true`=`eevee`). **`--kind mob` 이면 `--run-animation false` 도 자동**(run 애니 제외·디스크↓). **대화형 질문(texture-pack·color-compression·rotation·strip·scale·run-animation) 전부 없이** pc/mob/npc 를 잘림 없이 자동 조정 + 최대 압축으로 패킹. 🛑 개별 옵션을 함께 명시하면 **그 값이 우선**(auto 는 미지정 항목만 채움) — 예 `--auto --run-animation true` 는 mob 이라도 run 포함, `--auto --rotation false` 는 회전만 끄고 나머지 프리셋 유지. auto-fit 이 켜지므로 `--scale-<action>`·전역 `--scale` 무시(1.0 자동 하강) |

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

→ `flutter/assets/mob/dreyer/dreyer.{png,atlas}`(16방향 × idle8·walk12·attack16·hit8·
death8 = 832 프레임). dreyer 는 hand 본에 **hammer(망치)** 가 붙어있어 body-only
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

### ⚠️ 이 리포엔 `scripts/compress_image.py` 가 없다 — 색 압축 자동 스킵

`--color-compression true`(기본)이지만 이 리포 루트에 `scripts/compress_image.py` 가
없어서 256색 양자화가 **스킵**되고 무손실 RGBA PNG 가 그대로 남는다(예: dreyer.png ≈
7.5MB). atlas·게임 동작·RAM 엔 무관하고 **디스크/번들 용량만 커진다**. 줄이려면 그
스크립트를 두거나 `pngquant`(`pngquant --force 256 dreyer.png -o dreyer.png`)로 후처리.

## 절대 규칙

- **신규 캐릭터/몬스터 sprite 는 16방향·128 cell 만.** "8방향으로 만들어 달라"는 거절하고
  16방향으로 안내한다(짝수 row 가 8방향과 동일하므로 8방향이 필요해도 16 한 장이면 됨).
- **캐릭터·애니 모델은 Mixamo rig**(본 이름 `mixamorig:`). PC 는 부위별 overlay 합성 없이
  세트 단위 통짜 sheet. 몬스터는 장비 분리 없이 전체 모델 렌더.
- **RAM 은 W×H×4 로 고정** — `--color-compression` 은 디스크/번들 용량만 줄인다(OOM 무관).
  메모리 절감은 픽셀 축소(`--cell-size`)로만.
- **검증 불가 시 원점 복구** — packing 결과를 실제 Flame 앱으로 시각 검증하지 못하면 커밋하지 않는다.

## 관련 워크플로우

- **texture-packer(이 스킬)** = packing 파이프라인 코드(sheet.py 계열)의 *소유·실행·SSOT*.
- 상위 자산 생성 워크플로우(확장자 자동감지·내장 애니 매칭 안내 등)는 실행 단계에서 이 스킬의
  `scripts/sheet.py` 를 호출한다. 3D 모델 자체 생성(참조 이미지 기반) 뒤 sprite packing 은 이 스킬로.
