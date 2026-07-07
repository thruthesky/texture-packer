---
name: texture-packer
description: 라리엔 PC/몬스터(mob)/NPC 의 3D 모델(FBX/GLB/glTF/.blend)을 16방향(기본) sprite frame 으로 Blender 렌더한 뒤 libGDX TexturePacker 로 빈틈 없는 packed atlas(assets/<kind>/<name>/<name>.png + .atlas)로 묶는 texture-packing 파이프라인. 다음 경우 사용 — (1) "pc/mob/npc 를 texture packing 해줘", "sprite sheet 를 atlas 로 패킹", "packed atlas 생성", (2) 캐릭터/몬스터 sprite 를 게임에 넣을 atlas 로 굽기(sheet.py 실행), (3) 기존 kind 를 같은 이름으로 재생성·교체, (4) 행동별 프레임 수(idle/walk/attack/hit/death/run 또는 npc look/talk/wave) 조정 packing, (5) grid 단일 통합 sheet(--texture-pack false) 생성, (6) gdx-tools jar·TexturePacker·발 정렬(align_feet)·256색 압축(compress_image)·pubspec 자동 갱신 등 packing 파이프라인 이해/디버깅. 라리엔의 sheet.py·_sheet_render.py·_sheet_build.py·align_feet.py·sheet-win.py 등 packing 코드 전체를 소유한다. 키워드 — texture packing, texture-packer, packed atlas, sprite sheet packing, gdx TexturePacker, sheet.py, pc packing, mob packing, npc packing, 16방향 아틀라스, .atlas, flame_texturepacker, 발 정렬, align_feet, 통짜 grid sheet.
metadata:
  author: laryen
  version: "1.0"
---

# texture-packer — 라리엔 PC/mob/NPC sprite packing

라리엔 캐릭터·몬스터·NPC 의 3D 모델을 **16방향 sprite frame → packed atlas** 로 굽는
파이프라인 전체(`scripts/`)를 소유하는 스킬. "pc/mob/npc 를 texture packing 해줘" 요청을
이 스킬의 `scripts/sheet.py` 로 자율 수행한다.

## 이 스킬이 소유한 코드 (모두 `scripts/` 안)

| 파일 | 역할 |
|---|---|
| `scripts/sheet.py` | **메인 CLI**(macOS). 렌더→packing→압축→pubspec 갱신 전 과정 오케스트레이션 |
| `scripts/_sheet_render.py` | Blender(`-b -P`)로 FBX/GLB/.blend → 방향별 frame PNG 렌더 |
| `scripts/_sheet_build.py` | `--texture-pack false` 시 균일 grid 단일 sheet 빌드 |
| `scripts/align_feet.py` | 프레임의 발(불투명 bbox 하단)을 셀 0.85 에 정렬(행동 전환 상하 점프 방지) |
| `scripts/sheet-win.py` · `sheet-preview-win.py` | Windows 형제(빌드/preview). sheet.py 와 동일 보조 스크립트 공유 |
| `scripts/combine_to_runtime_sheet.py` | 행동별 256 sheet → 런타임 128 단일 16×60 sheet 합성(legacy) |
| `scripts/gen_all_sheets.sh` | 보유 PC/몬스터 모델 일괄 생성 헬퍼 |
| `scripts/tools/*.jar` | libGDX TexturePacker(gdx 1.13.1) — 없으면 sheet.py 가 Maven 에서 자동 다운로드 캐시 |

> 🛑 **`compress_image.py` 는 이 스킬 소유가 아니다.** 범용 PNG 압축 도구라 프로젝트
> `scripts/compress_image.py` 에 남아 있고(`compress-image` 스킬이 공유), sheet.py 는
> `ROOT/scripts/compress_image.py` 를 참조한다. 이 스킬 scripts/ 로 옮기지 않는다.

## 핵심: 어디서 실행해도 프로젝트 루트를 자동으로 찾는다

이 스킬의 스크립트는 `.claude/skills/texture-packer/scripts/` 에 있지만, 산출물은 **프로젝트
루트**의 `assets/`·`game-assets/`·`pubspec.yaml` 을 대상으로 한다. `sheet.py` 등은
`_find_project_root()` 로 루트를 견고하게 탐색한다 — ① 환경변수 `LARYEN_ROOT`(pubspec 검증)
→ ② skill 위치 기준 4단계 상위(`scripts→texture-packer→skills→.claude→루트`) → ③
`git rev-parse --show-toplevel` → ④ cwd. **따라서 cwd 와 무관하게 절대 경로로 실행하면 된다.**

## 표준 워크플로우 (pc/mob/npc packing)

### 1. 실행 — kind 별 모델 폴더

| `--kind` | 모델 소스 폴더 | 행동(col) 순서 |
|---|---|---|
| `pc` | `game-assets/characters/` | idle · walk · attack · hit · death · run |
| `mob` | `game-assets/monsters/` | idle · walk · attack · hit · death · run |
| `npc` | `game-assets/blend/` | idle · look · talk · walk · wave |

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

# NPC — .blend, npc 전용 행동
python3 .claude/skills/texture-packer/scripts/sheet.py \
  --kind npc --name shopkeeper --character game-assets/blend/shopkeeper.blend
```

- `--character` 는 절대/상대 경로 또는 파일명만(파일명이면 `game-assets/<kind별폴더>/` 에서 찾음).
- 인자를 생략하면 터미널에서 순서대로 물어본다(대화형). 자율 실행 시 인자를 모두 준다.
- **신규 PC·몬스터는 반드시 16방향**(기본). `--directions 8` 은 legacy 재생성 전용.

### 2. 출력 (프로젝트 루트 기준)

```
assets/<kind>/<name>/<name>.png      # packed atlas 이미지 (256색 양자화)
assets/<kind>/<name>/<name>.atlas    # flame_texturepacker 가 읽는 trim/rotate 메타
```

`pubspec.yaml` 의 관리 블록(`# >>> AUTO(sheet.py packed actors) >>>`)에 이번 `<name>` 만
자동 추가된다(전체 폴더 등록 X).

### 3. 게임 적용 & 검증

1. **앱 재빌드 필요** — atlas 는 AssetManifest 스캔으로 감지되므로 hot reload/restart 로는
   새 atlas 가 안 잡힌다. pc/mob 는 *오직* `assets/<pc|mob>/<name>/<name>.atlas` 에서만
   로드된다(격자 `assets/render/actors/` 폐기, 2026-07-01 정책).
2. atlas 없는 pc/mob 은 투명 placeholder(안 보임) + `printMissingAtlasReport()` 로 목록화.
3. 시각 검증은 **DTD + iPhone 17 Pro Max** 로만(§CLAUDE.md 테스트 환경). analyze/단위테스트로
   갈음 금지.

### 4. 옵션 요약 (자세한 로직·소스는 [references/pipeline.md](references/pipeline.md))

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--texture-pack {true\|false}` | true | true=packed atlas, false=grid 단일 sheet(`_sheet_build.py`) |
| `--cell-size N` | 128 | atlas orig/cell 픽셀(pc/npc/mob 전부 128 통일) |
| `--render-res N` | 256 | frame 렌더 해상도(→ 128 로 자동 축소, `--scale-frames` 0.5) |
| `--color-compression {true\|false}` | true | 256색 FASTOCTREE 양자화(디스크만 절감, RAM 무관) |
| `--idle/--walk/--attack/--hit/--death/--run N` | 8/12/16/8/8/12 | 행동별 프레임 수 |
| `--look/--talk/--wave N` | — | npc 전용 행동 프레임 수 |
| `--scale-attack/--scale-run …` | — | 행동별 생성 scale(무기 잘림 방지, [references/pipeline.md](references/pipeline.md) §무기잘림) |
| `--weapon / --weapon-bone …` | — | 무기 손 본 장착(별도 weapon-attach 스킬과 병행) |
| `--directions {8\|16}` | 16 | 신규는 16 고정. 8 은 legacy 재생성 전용 |
| `--render-only / --build-only` | — | 렌더만 / packing만 |
| `--packer-cp PATH` | — | gdx jar classpath 수동 지정(기본은 `scripts/tools/` 자동) |

## 절대 규칙

- **신규 캐릭터/몬스터 sprite 는 16방향·128 cell 만.** "8방향으로 만들어 달라"는 거절하고
  16방향으로 안내한다(짝수 row 가 8방향과 동일하므로 8방향이 필요해도 16 한 장이면 됨).
- **캐릭터·애니 모델은 Mixamo rig**(본 이름 `mixamorig:`). PC 는 부위별 overlay 합성 없이
  세트 단위 통짜 sheet(All-or-Base). 몬스터는 장비 분리 없이 전체 모델 렌더.
- **RAM 은 W×H×4 로 고정** — `--color-compression` 은 디스크/번들 용량만 줄인다(OOM 무관).
  메모리 절감은 픽셀 축소(`--cell-size`)로만.
- **검증 불가 시 원점 복구** — packing 결과를 DTD 로 시각 검증하지 못하면 커밋하지 않는다.

## 이 스킬과 `asset` / `asset:sheet` 의 관계

- **texture-packer(이 스킬)** = packing 파이프라인 코드(sheet.py 계열)의 *소유·실행·SSOT*.
- **`asset:sheet`** = 상위 자산 생성 워크플로우(확장자 자동감지·내장 애니 매칭 안내)로,
  실행은 이 스킬의 `scripts/sheet.py` 를 호출한다.
- **`asset`** = 자산 생성 전반(3D 모델 생성·decor·tile·map). 캐릭터/몬스터 3D 모델은
  참조 이미지 필수(Hunyuan3D). 그 뒤 sprite packing 은 이 스킬로.
