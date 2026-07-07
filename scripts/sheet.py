#!/usr/bin/env python3
"""
라리엔 16/8방향 sprite sheet / packed atlas 생성 CLI (macOS).

FBX/GLB(glTF) 캐릭터·몬스터(메쉬+리그) → Blender 로 16방향(기본) 또는 8방향
개별 frame PNG 를 굽고 → TexturePacker atlas 또는 단일 grid sheet 로 묶는다.
확장자(.fbx / .glb / .gltf / .blend)를 보고 import 방식을 자동 분기한다(_sheet_render.py).

기본 품질 파이프라인(신규 권장):
  1. 개별 frame PNG: 기본 256×256px 로 렌더한다(--render-res 생략 시).
  2. TexturePacker 입력: 기본 --cell-size 160px 로 축소한다(--scale-frames 자동 0.625).
     🛑 160 이 최종·SSOT 최고 규정(actor_animation_set.dart _runtimeSpriteCellPx=160 과 일치).
  3. packed atlas: 투명 여백 trim + 필요 시 90도 회전 packing.
  4. color compression: 기본 256색 FASTOCTREE 팔레트 양자화.
  5. 게임 표시: 런타임 컴포넌트는 kActorDisplaySize(128px)에 축소 렌더한다.

산출물(2종, --texture-pack 로 선택):
  --texture-pack true  (기본)
    libGDX TexturePacker(gdx-tools, Java)로 frame 을 빈틈 없이 packing한다.
    출력: assets/<kind>/<name>/<name>.png + <name>.atlas
    런타임: ActorAnimationSet.loadActorAtlas + flame_texturepacker 가 trim offset·rotate 를 처리한다.

  --texture-pack false
    _sheet_build.py 로 균일 grid 단일 통합 sheet 를 만든다.
    출력: assets/<kind>/<name>/<name>.png
    추가 정보: game-assets/sprites/<name>_manifest.json + <name>_layout.md
    주의: 현재 게임 자동 로드는 기본 atlas 경로를 우선한다. grid 는 legacy/디버그/수동 통합용이다.

출력 경로(--kind + --name):
  --kind {pc,mob}  액터 카테고리(pc=플레이어/사람형, mob=몬스터). 값은 pc 또는 mob 만.
  --name NAME      texture 파일명(=실제 산출 파일 이름). 예: male_victor
  → assets/<kind>/<name>/<name>.png  (+ <name>.atlas — texture-pack true 일 때)
    예) --kind pc  --name male_victor  → assets/pc/male_victor/male_victor.{png,atlas}
        --kind mob --name demonic_king → assets/mob/demonic_king/demonic_king.{png,atlas}

결과 폴더 지정(--output — 선택):
  --output DIR     결과 저장 베이스 폴더(기본: 프로젝트 루트의 assets/). 지정 시
                   <DIR>/<kind>/<name>/<name>.{png,atlas} 로 자동 생성·저장한다.
                   예) --output ./viewer/assets → ./viewer/assets/pc/male_victor/male_victor.{png,atlas}
                   상대경로는 cwd 가 아니라 프로젝트 루트(ROOT) 기준으로 해석한다.
                   🛑 --output 지정 시 루트 pubspec.yaml 자동 갱신은 건너뛴다(별도 앱/뷰어 대상 가능).
                   ※ 중간 frames 폴더는 --outputs(복수형)로 따로 지정한다.

컬러 압축(--color-compression, 기본 true):
  256색 팔레트 양자화(FASTOCTREE, 알파 보존)로 PNG 번들 크기를 크게 줄인다.
  --color-compression false → 양자화 끔(무손실 RGBA).
  RAM/VRAM 은 W×H×4 로 고정이다. 압축은 *디스크/앱 번들 용량* 만 줄인다.

애니메이션(--animations — 필수, 인자 생략 시 대화형 선택):
  game-assets/animations/<variant>/ 아래 {action}.fbx/.glb/.gltf 를 두고 <variant> 를
  --animations 로 지정한다(예: default · sword · slash …). 인자를 생략하면 폴더 목록을
  보여주고 번호로 고른다. 캐릭터·애니 모두 Mixamo rig(본 이름 'mixamorig:')여야 한다.

대화형(interactive):
  --character / --kind / --name / --animations 를 생략하면 터미널에서 순서대로 물어본다.
  인자를 주면 그 인자를 그대로 쓰고 해당 프롬프트를 건너뛴다.

pubspec.yaml 자동 갱신:
  실행하면 이번에 만든 <name> 파일만 pubspec.yaml 의 관리 블록
  (`# >>> AUTO(sheet.py packed actors) >>>`)에 추가한다. 전체 폴더를 통째 등록하지 않고,
  실제 필요한 assets/<kind>/<name>/<name>.png[, .atlas] 만 등록한다.

게임에 적용하는 방법:
  1. 기존 kind 를 교체할 때는 같은 --name 으로 다시 생성한다.
     예: male_victor 교체 → --kind pc --name male_victor.
  2. 신규 atlas 파일은 pubspec 관리 블록에 자동 추가된다.
  3. 🛑 pc/mob 은 *오직* assets/<pc|mob>/<name>/<name>.atlas 에서만 로드된다(격자 actors/ 폐기,
     2026-07-01 정책). 앱을 재빌드하면 AssetManifest 스캔으로 atlas 를 감지해 ActorAnimationSet.
     loadActor(kind) 가 로드한다. atlas 가 없는 pc/mob 은 투명 placeholder(안 보임)로 처리되고
     "재생성 필요" 목록에 모여 로그로 알려진다(ActorAnimationSet.printMissingAtlasReport() 로 전체
     목록 확인) — 즉 sheet.py 로 packing 하지 않은 pc/mob 은 게임에 안 보인다(크래시는 없음).
     asset 추가/교체는 앱 재빌드 필요(hot reload/restart 로는 AssetManifest 재번들 안 됨).
  4. 완전히 새로운 PC 외형/몬스터 kind 는 Dart/서버 매핑도 필요하다.
     PC: appearance code → kind 매핑(kindForAppearanceCode / 서버 effectiveAppearance).
     mob: archetype/boss resolver → ActorAnimationSet.loadActor(<name>) 매핑.

production 정책(위반 거절):
  - --character 와 --animations 의 모든 모델은 *반드시 Mixamo rig* (본 이름 'mixamorig:').
  - 신규 PC·몬스터 애니메이션은 *반드시 16방향*(기본)으로 생성한다.
  - 신규 권장 출력은 texture-pack=true atlas, frame 256 → atlas orig 160 → display 128 이다.
  - --directions 8 은 *기존 legacy 재생성 호환* 전용이다(신규는 16방향).

사용 예:
  # 권장 — Mixamo rig 캐릭터(PC) + 애니 폴더 → packed atlas (기본: 256 render → 160 atlas)
  ./scripts/sheet.py --kind pc --name male_victor \
    --character game-assets/characters/male_victor.fbx --animations default \
    --idle 8 --walk 12 --run 12 --attack 16 --hit 8 --death 8

  # 몬스터 → assets/mob/demonic_king/...
  ./scripts/sheet.py --kind mob --name demonic_king \
    --character game-assets/monsters/demonic_king.fbx --animations default --shading texture

  # 균일 grid sheet(비-atlas) + 컬러 압축 끔 — legacy/디버그/수동 통합용
  ./scripts/sheet.py --kind pc --name male --character game-assets/characters/male.fbx \
    --animations default --texture-pack false --color-compression false

  # 대화형(인자 없이) — character/kind/name/animations 를 순서대로 물어봄
  ./scripts/sheet.py
"""
import argparse, glob, json, os, subprocess, sys, shutil, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_project_root(here):
    """라리엔 프로젝트 루트(assets/·game-assets/·pubspec.yaml 기준)를 찾는다.
    본 스크립트는 .claude/skills/texture-packer/scripts/ 로 이동했으므로 dirname(HERE)
    는 더 이상 repo 루트가 아니다(=texture-packer). 다음 순서로 견고하게 탐색한다:
      ① 환경변수 LARYEN_ROOT(pubspec.yaml 검증) — 명시 override
      ② skill 위치 기준 4단계 상위(scripts→texture-packer→skills→.claude→ROOT)
      ③ git rev-parse --show-toplevel(pubspec.yaml 검증)
      ④ 최후: 현재 작업 디렉토리(cwd)
    → 스크립트가 어디로 옮겨져도 assets/·game-assets/·pubspec.yaml 경로가 깨지지 않는다."""
    env = os.environ.get("LARYEN_ROOT")
    if env and os.path.isfile(os.path.join(env, "pubspec.yaml")):
        return os.path.abspath(env)
    cand = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
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


# repo 루트(assets/·game-assets/·pubspec.yaml 기준) — 출력·pubspec 경로 기준.
ROOT = _find_project_root(HERE)

# 기본 렌더/패킹 해상도.
# - DEFAULT_RENDER_RES: Blender 가 저장하는 개별 frame PNG 크기(기본 256×256).
# - DEFAULT_CELL_SIZE: TexturePacker atlas 의 원본 frame box(orig) 또는 grid cell 크기.
#   🛑 128 이 최종·SSOT 최고 규정(2026-07-05 pc/npc/mob 전부 128 통일) — 게임 표시 크기
#   (RUNTIME_DISPLAY_SIZE=128)와 1:1 이라 축소 렌더가 없어 화질 손실이 거의 없고, atlas page
#   픽셀이 (128/160)²=0.64배로 줄어 iOS OOM(actorAtlas RAM)을 직접 낮춘다. 과거 pc/npc 160 은
#   display 128 로 어차피 축소 렌더돼 여유 픽셀만 RAM 을 먹었다. 실제 로드(loadActorAtlas)는
#   .atlas 의 orig 값을 읽어 자동 대응하므로 런타임 코드 상수(_runtimeSpriteCellPx)와의
#   강제 일치는 불필요하다(그 상수는 dead 격자 로더 전용). render 256 → 128(scale-frames 자동 128/256=0.5).
# - RUNTIME_DISPLAY_SIZE: 게임 컴포넌트 표시 크기(기본 128×128). cell 은 화질 축, display 는 크기 축.
#   "게임도 128, texture 도 128"(2026-07-05 통일 전에는 "게임 128, texture 160").
DEFAULT_RENDER_RES = 256
DEFAULT_CELL_SIZE = 128
# pc/npc/mob 전부 128 통일(2026-07-05). 과거엔 pc/npc 160·mob 128 로 갈렸으나, display 가
# 어차피 128 이라 pc/npc 160 의 여유 픽셀은 화질 이득 없이 RAM(OOM)만 키웠다. --cell-size 를
# 명시하면 kind 와 무관하게 그 값을 쓴다(예: 큰 무기 휘두름이 128 셀에서 잘리면 --scale-attack 로
# 모델을 작게 굽는 게 cell 상향보다 우선 — 무기 잘림 3대 메커니즘, asset ssot.md §1.5).
DEFAULT_CELL_SIZE_MOB = 128
RUNTIME_DISPLAY_SIZE = 128

# 단일 통합 grid sheet 는 Σframes×cell (W) × directions×cell (H).
DEFAULT_FRAMES  = {"idle": 8, "walk": 12, "attack": 16, "hit": 8, "death": 8, "run": 12,
                   "look": 8, "talk": 8, "wave": 8}
DEFAULT_ACTIONS = ["idle", "walk", "attack", "hit", "death", "run"]   # pc col 순서(run 포함)
# mob 기본 행동 — run 제외(대부분 몬스터는 걷기만 하므로 atlas 에서 run 을 빼 디스크 절감).
# run 이 필요한 몬스터는 대화형 질문에 y 또는 --run N / --actions 로 명시하면 포함된다.
MOB_ACTIONS     = ["idle", "walk", "attack", "hit", "death"]
NPC_ACTIONS = ["idle", "look", "talk", "walk", "wave"]                # npc 전용 col 순서
FRAME_OPTION_ACTIONS = ["idle", "walk", "run", "attack", "hit", "death", "look", "talk", "wave"]
TEXTURE_LIMIT = 8192
SUPPORTED_EXT = (".fbx", ".glb", ".gltf")
CHAR_EXT = SUPPORTED_EXT + (".blend",)

# 액터 카테고리 → game-assets 모델 폴더(대화형 목록·확장자 자동보정용).
KIND_MODEL_DIR = {"pc": "game-assets/characters", "mob": "game-assets/monsters", "npc": "game-assets/blend"}
ANIM_ROOT = "game-assets/animations"

# ── libGDX TexturePacker(gdx-tools, Java) 자동 확보 ─────────────────────────────
# 비난독화 정식 jar 3종(gdx + gdx-tools + desktop natives)을 classpath 로 실행한다.
# (tommyettinger standalone runnable jar 는 난독화되어 pack.json 필드를 못 읽음 — 금지)
GDX_VERSION = "1.13.1"
GDX_MAVEN = "https://repo1.maven.org/maven2/com/badlogicgames/gdx"
GDX_JARS = {
    f"gdx-{GDX_VERSION}.jar":
        f"{GDX_MAVEN}/gdx/{GDX_VERSION}/gdx-{GDX_VERSION}.jar",
    f"gdx-tools-{GDX_VERSION}.jar":
        f"{GDX_MAVEN}/gdx-tools/{GDX_VERSION}/gdx-tools-{GDX_VERSION}.jar",
    f"gdx-platform-{GDX_VERSION}-natives-desktop.jar":
        f"{GDX_MAVEN}/gdx-platform/{GDX_VERSION}/gdx-platform-{GDX_VERSION}-natives-desktop.jar",
}
TP_MAIN_CLASS = "com.badlogic.gdx.tools.texturepacker.TexturePacker"

# pubspec.yaml 관리 마커(이 블록 안 항목만 sheet.py 가 관리 — 수동 편집 금지).
PUBSPEC_MARK_BEGIN = "    # >>> AUTO(sheet.py packed actors) — sheet.py 가 관리. 수동 편집 금지. >>>"
PUBSPEC_MARK_END   = "    # <<< AUTO(sheet.py packed actors) <<<"

EXAMPLES = rf"""
동작 요약:
  기본 입력/출력 품질:
    - 개별 frame PNG: {DEFAULT_RENDER_RES}×{DEFAULT_RENDER_RES}px (--render-res 기본)
    - packed atlas orig/cell: {DEFAULT_CELL_SIZE}×{DEFAULT_CELL_SIZE}px (--cell-size 기본)
    - 자동 축소: --scale-frames={DEFAULT_CELL_SIZE / DEFAULT_RENDER_RES:.2f}
    - 게임 표시: {RUNTIME_DISPLAY_SIZE}×{RUNTIME_DISPLAY_SIZE}px 컴포넌트에 축소 렌더
    - 컬러 압축: 256색 FASTOCTREE 양자화 기본 on(번들 크기 절감, RAM 절감 아님)

  기본 산출(texture-pack=true):
    assets/<pc|mob>/<name>/<name>.png
    assets/<pc|mob>/<name>/<name>.atlas
    pubspec.yaml 의 AUTO(sheet.py packed actors) 블록 자동 갱신

  grid 산출(texture-pack=false):
    assets/<pc|mob>/<name>/<name>.png
    game-assets/sprites/<name>_manifest.json
    game-assets/sprites/<name>_layout.md
    주의: grid 는 legacy/디버그/수동 통합용이다. 게임 자동 적용은 atlas 경로가 기본이다.

게임 적용:
  1. 기존 PC/몬스터를 교체하려면 기존 kind 와 같은 --name 으로 생성한다.
     예: --kind pc --name male_victor, --kind mob --name brute.
  2. 생성 후 pubspec 관리 블록이 자동 갱신된다.
  3. 앱 재빌드/재실행 후 ActorAnimationSet.loadActor 가 AssetManifest 를 스캔해
     assets/<pc|mob>/<name>/<name>.atlas 를 우선 로드한다. debug 중 hot restart 로 안 보이면
     flutter pub get 후 재실행한다.
  4. 새 kind 를 추가하면 코드 매핑도 추가한다.
     PC: appearance code/effectiveAppearance → kind 매핑.
     mob: archetype resolver → ActorAnimationSet.loadActor('<name>') 매핑.

주의:
  - --render-only 는 outputs/<name>/frames 에 개별 frame PNG 만 만들고 종료한다.
  - --build-only 는 기존 outputs/<name>/frames 를 재사용해 packing/build 만 다시 한다.
  - --color-compression=false 는 색 손실을 피하지만 파일 크기가 커진다.
  - --texture-pack=false 는 TexturePacker/Java 없이 동작하지만, atlas 자동 로드 이점이 없다.
  - --directions=8 은 legacy 재생성용이다. 신규 PC/mob 는 16방향을 사용한다.

예시:
  # packed atlas(기본) — PC male_victor
  ./scripts/sheet.py --kind pc --name male_victor \
    --character game-assets/characters/male_victor.fbx --animations default \
    --idle 8 --walk 12 --run 12 --attack 16 --hit 8 --death 8

  # 몬스터
  ./scripts/sheet.py --kind mob --name demonic_king \
    --character game-assets/monsters/demonic_king.fbx --animations default --shading texture

  # grid sheet(비-atlas) + 컬러 압축 끔
  ./scripts/sheet.py --kind pc --name male --character game-assets/characters/male.fbx \
    --animations default --texture-pack false --color-compression false

  # 기존 frame 재사용해서 160 atlas 만 다시 packing
  ./scripts/sheet.py --kind pc --name male_victor --animations default \
    --character game-assets/characters/male_victor.fbx --build-only

  # 대화형 — 인자 없이 실행하면 character/kind/name/animations 를 순서대로 물어봄
  ./scripts/sheet.py
"""


# ─────────────────────────────────────────────────────────────────────────────
#  공통 유틸
# ─────────────────────────────────────────────────────────────────────────────
def find_blender(explicit):
    cands = [explicit, "/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")]
    for p in cands:
        if p and os.path.exists(p):
            return p
    sys.exit("Blender 를 찾을 수 없습니다. --blender 로 경로를 지정하세요.")


def find_java(explicit):
    """java 실행 파일을 찾는다(macOS). Android Studio 의 JBR 도 후보에 포함."""
    cands = [
        explicit or None,
        shutil.which("java"),
        "/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java",
    ]
    jh = os.environ.get("JAVA_HOME")
    if jh:
        cands.append(os.path.join(jh, "bin", "java"))
    for p in cands:
        if p and os.path.isfile(p):
            return p
    sys.exit(
        "❌ Java(JRE) 를 찾을 수 없습니다 — TexturePacker 는 Java jar 라 실행에 필요합니다.\n"
        "   → java 를 설치하거나 --java 로 경로를 지정하세요.\n"
        "     예: /Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java\n"
        "   또는 texture packing 없이: --texture-pack false")


def assert_mixamo_rig(path, role):
    """모델 파일이 Mixamo rig 인지 검증(아니면 종료). FBX/GLB 바이너리에 'mixamorig' prefix
    가 있는지로 판정한다. sheet.py 는 Mixamo rig 캐릭터 + Mixamo 애니만 지원(본 일치 →
    retarget 없이 직접 적용 → 방향·자세 회귀 차단)."""
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except Exception as e:
        sys.exit(f"{role} 파일을 읽을 수 없습니다: {path} ({e})")
    if b"mixamorig" not in blob:
        sys.exit(
            f"❌ {role} 가 Mixamo rig 가 아닙니다 (본 이름 'mixamorig:' 미검출): {path}\n"
            f"   → sheet.py 는 *Mixamo rig 캐릭터 + Mixamo 애니메이션* 만 지원합니다.\n"
            f"   → https://www.mixamo.com 에서 모델 Auto-Rig(또는 애니 다운로드) 후 FBX export.")


def parse_size(s):
    if "x" in str(s).lower():
        a, b = str(s).lower().split("x")
        if int(a) != int(b):
            sys.exit(f"cell 은 정사각만 지원합니다(라리엔 SSOT): {s}")
        return int(a)
    return int(s)


def str2bool(v):
    """--texture-pack / --color-compression 의 문자열 true/false 파싱."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"true/false 를 기대하지만 받음: {v!r}")


# ─────────────────────────────────────────────────────────────────────────────
#  대화형(interactive) 헬퍼 — 인자 생략 시 순서대로 물어본다.
# ─────────────────────────────────────────────────────────────────────────────
def _interactive_ok():
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(msg, default=None):
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"{msg}{suffix}: ").strip()
    except EOFError:
        v = ""
    return v or (default or "")


def _choose(title, items, allow_manual=True):
    """번호 목록에서 하나 고르거나 직접 입력. 빈 items 면 직접 입력만."""
    print(f"\n{title}")
    for i, it in enumerate(items, 1):
        print(f"   {i}) {it}")
    hint = "번호 선택" + (" 또는 직접 입력" if allow_manual else "")
    while True:
        try:
            s = input(f"   → {hint}: ").strip()
        except EOFError:
            s = ""
        if s.isdigit() and 1 <= int(s) <= len(items):
            return items[int(s) - 1]
        if s and allow_manual:
            return s
        if not s and items:
            return items[0]
        print("   유효한 번호를 입력하세요.")


def list_anim_variants():
    root = os.path.join(ROOT, ANIM_ROOT)
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))


def list_models(kind):
    d = os.path.join(ROOT, KIND_MODEL_DIR.get(kind, ""))
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if os.path.splitext(f)[1].lower() in CHAR_EXT:
            out.append(f)
    return out


def prompt_missing(args):
    """필수 값(character/kind/name/animations)이 없으면 대화형으로 채운다."""
    interactive = _interactive_ok()

    # 1) kind (pc/mob/npc)
    if not args.kind:
        if not interactive:
            sys.exit("--kind {pc,mob,npc} 가 필요합니다(대화형 불가 — 터미널이 아닙니다).")
        args.kind = _choose("액터 카테고리를 고르세요 (--kind):", ["pc", "mob", "npc"], allow_manual=False)
    if args.kind not in ("pc", "mob", "npc"):
        sys.exit(f"--kind 는 pc, mob 또는 npc 만 가능합니다: {args.kind!r}")

    # 2) character (모델 파일)
    if not args.character:
        if not interactive:
            sys.exit("--character (모델 파일) 가 필요합니다(대화형 불가).")
        models = list_models(args.kind)
        base = KIND_MODEL_DIR[args.kind]
        chosen = _choose(f"모델 파일을 고르세요 (--character, {base}/):", models)
        # 목록에서 고른 파일명은 base 폴더 기준 상대경로로 완성.
        args.character = (os.path.join(base, chosen)
                          if chosen in models else chosen)

    # 3) name (산출 파일명) — 기본값 = 모델 파일 stem
    if not args.name:
        default_name = os.path.splitext(os.path.basename(args.character))[0]
        if not interactive:
            args.name = default_name
        else:
            args.name = _ask("산출 texture 이름 (--name)", default_name)

    # 4) animations (variant 폴더)
    if not args.animations:
        variants = list_anim_variants()
        if not interactive:
            sys.exit("--animations 가 필요합니다(대화형 불가).")
        args.animations = _choose(f"애니메이션 폴더를 고르세요 (--animations, {ANIM_ROOT}/):",
                                   variants)

    # 5) texture-pack / color-compression 확인(대화형일 때만, 이미 지정됐으면 건너뜀)
    if interactive and not args._texture_pack_explicit:
        args.texture_pack = str2bool(_ask(
            "texture packing(atlas) 사용? true/false", "true"))
    if interactive and not args._color_compression_explicit:
        args.color_compression = str2bool(_ask(
            "컬러 압축(256색) 사용? true/false", "true"))
    # 6) scale-attack (attack 무기 잘림 방지 — 대화형, --scale-attack 미지정 시 물어봄).
    #    attack 행동 모델을 이 배율로 작게 구워 검·도끼 휘두름이 셀 밖으로 잘리는 것을 막는다
    #    (기본 0.8 권장 — 잘리면 더 낮추고, 무기가 작으면 1.0). 작게 구운 만큼 화면 크기는
    #    런타임 kActorDisplayKByKind 로 보정한다(sheet.py 가 권장값 출력).
    if interactive and args.scale_attack is None:
        while True:
            s = _ask("--scale-attack? attack 모델 크기(무기 잘림 방지, 0.6~1.0)", "0.8")
            try:
                v = float(s)
            except ValueError:
                print("   숫자를 입력하세요."); continue
            if 0.6 <= v <= 1.0:
                args.scale_attack = v
                break
            print("   0.6 ~ 1.0 범위로 입력하세요.")
    # 7) mob run 애니 포함 여부 — 기본 제외(디스크 절감).
    #    우선순위: --run-animation(명시) > --run N/--actions(명시) > 대화형 질문 > 기본 제외.
    #    🛑 --run-animation 을 주면 대화형 질문을 *건너뛴다*(true/false 로 바로 결정).
    args._mob_include_run = (args.run is not None)
    if args.run_animation is None and args.kind == "mob" and args.actions is None \
            and args.run is None and interactive:
        args._mob_include_run = str2bool(_ask(
            "run(달리기) 애니 포함? 대부분 몬스터는 걷기만 하므로 기본 제외(디스크↓) [y/N]", "N"))
    # 8) 회전 packing — 기본 true. 미지정(--rotation/--no-rotation 둘 다 안 줌)이면 대화형으로
    #    물어보고(비대화형은 true), 명시했으면 그 값을 그대로 쓴다(질문 생략 — run-animation 과 동형).
    #    🛑 actor(pc/mob/npc)는 rotate+useOriginalSize offset 이 발 위치를 어긋나게 하고(attack 발 뜸)
    #    16방향(~1024프레임)은 패킹이 20분+ 걸리므로 off(false) 권장 — 질문에 경고를 명시해 개발자가
    #    인지하고 고르게 한다. 사용자 지시(2026-07-07): 기본 true + 미설정 시 물어봐서 설정.
    if args.rotation is None:
        if interactive:
            warn = ("  🛑 캐릭터/몬스터/NPC(pc/mob/npc)는 발 어긋남·패킹 지연으로 n(off) 권장"
                    if args.kind in ("pc", "mob", "npc") else "")
            args.rotation = str2bool(_ask(
                f"회전 packing(공간 절약) 켤까요?{warn} [Y/n]", "Y"))
        else:
            args.rotation = True  # 비대화형 기본 true (사용자 지시)
    return args


def resolve_animations_dir(spec):
    """--animations 값(variant 폴더명 또는 경로)을 실제 디렉토리로 해석."""
    # 1) 그대로 디렉토리?
    if os.path.isdir(spec):
        return os.path.abspath(spec)
    # 2) game-assets/animations/<spec>
    cand = os.path.join(ROOT, ANIM_ROOT, spec)
    if os.path.isdir(cand):
        return os.path.abspath(cand)
    variants = list_anim_variants()
    sys.exit(f"애니메이션 폴더를 찾을 수 없습니다: {spec}\n"
             f"   → {ANIM_ROOT}/ 하위 폴더: {', '.join(variants) or '(없음)'}")


# ─────────────────────────────────────────────────────────────────────────────
#  TexturePacker(gdx-tools) — 자동 확보 + 실행 + 페이지 압축
# ─────────────────────────────────────────────────────────────────────────────
def _download(url, dest):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "laryen-sheet/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, dest)
    except Exception:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def ensure_packer_classpath(explicit_cp):
    """gdx-tools classpath(gdx + gdx-tools + natives)를 확보(없으면 자동 다운로드).
    구분자는 OS(os.pathsep) — macOS 는 ':' . 반환: join 된 classpath 문자열."""
    if explicit_cp:
        parts = [p for p in explicit_cp.split(os.pathsep) if p.strip()]
        missing = [p for p in parts if not os.path.isfile(p)]
        if missing:
            sys.exit("--packer-cp 의 다음 jar 를 찾을 수 없습니다:\n   " + "\n   ".join(missing))
        return os.pathsep.join(os.path.abspath(p) for p in parts)

    tools_dir = os.path.join(HERE, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    cp_parts = []
    for name, url in GDX_JARS.items():
        dest = os.path.join(tools_dir, name)
        if not os.path.isfile(dest):
            print(f"  ⬇️  gdx-tools jar 자동 다운로드: {name}")
            try:
                _download(url, dest)
            except Exception as e:
                sys.exit(f"❌ jar 다운로드 실패({name}): {e}\n"
                         f"   → 수동 다운로드 후 --packer-cp 로 지정: {url}")
            print(f"     ✓ {os.path.getsize(dest)/1e6:.1f}MB → {dest}")
        cp_parts.append(os.path.abspath(dest))
    return os.pathsep.join(cp_parts)


def write_pack_json(frames_dir, args):
    """TexturePacker 설정(pack.json)을 frames_dir 에 쓴다(libGDX 관례)."""
    settings = {
        # 🛑 세로(Y) trim 은 *끈다* — 발 y 정렬(align_feet 0.85) 보존. 세로 trim 을 켜면 프레임마다
        # 다른 offset.y 가 생기고, flame_texturepacker 의 useOriginalSize offset 렌더가 이를 발
        # 위치에 어긋나게 반영해 attack(검이 오르내림)에서 발이 크게 점프한다(실측: off.y=9~19).
        # 세로 trim off → offset.y=0 → cell 세로가 그대로 유지돼 발이 anchor(0.85)에 고정된다.
        # 가로(X) trim 은 유지(발 y 무관, 아틀라스 가로 폭 절약).
        "stripWhitespaceX": bool(args.strip_whitespace),
        "stripWhitespaceY": False,
        "rotation": bool(getattr(args, "rotation", False)),
        "pot": bool(args.pot),
        "maxWidth": int(args.max_page_w),
        "maxHeight": int(args.max_page_h),
        "scale": [float(args.scale_frames)],
        "scaleSuffix": [""],
        "scaleResampling": ["bicubic"],
        "premultiplyAlpha": False,
        "edgePadding": True,
        "bleed": True,
        "paddingX": 2,
        "paddingY": 2,
        "duplicatePadding": True,
        "filterMin": "Nearest",
        "filterMag": "Nearest",
        "format": "RGBA8888",
        "ignoreBlankImages": True,
        "useIndexes": True,
        "alias": True,
        "square": False,
        # fast=true 필수 — 16방향 액터(~1024 프레임)는 정밀 패킹이 rotation 켜면 20분+ 안 끝난다.
        "fast": bool(getattr(args, "fast", True)),
        "outputFormat": "png",
        "atlasExtension": ".atlas",
        "prettyPrint": True,
    }
    path = os.path.join(frames_dir, "pack.json")
    json.dump(settings, open(path, "w", encoding="utf-8"), indent=2)
    return path, settings


def run_texture_packer(java, classpath, input_dir, output_dir, pack_name, verbose=False):
    """java -cp <gdx:gdx-tools:natives> TexturePacker <inputDir> <outputDir> <packName>."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [java, "-Djava.awt.headless=true", "-cp", classpath, TP_MAIN_CLASS,
           input_dir, output_dir, pack_name]
    if verbose:
        print("   $ " + " ".join(cmd))
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if verbose and out.stdout:
        print(out.stdout.rstrip())
    if out.returncode != 0:
        print("   ❌ TexturePacker 실행 실패:")
        print((out.stdout or "")[-1500:])
        print((out.stderr or "")[-2000:])
        sys.exit("TexturePacker 패킹 실패")
    return out


def align_frames_feet(frames_dir, foot_frac=0.85):
    """TexturePacker 前, 낱장 frame 의 발(불투명 bbox 하단)을 캔버스 foot_frac*H 로 수직 정렬.

    🛑 왜 필요: atlas 렌더(_sheet_render.py)는 카메라가 몸 *중심* 을 겨냥하고 행동마다
    ortho_scale(=ortho/scale)을 바꾸므로, --scale-<action>(예 attack 0.8)로 작게 구운 행동은
    발의 화면 y 가 다른 행동과 달라진다(attack 이 위로 뜸). 런타임 anchor 는 (0.5, 0.85) 고정
    이라, 프레임 안 발이 0.85 에 있어야 발이 땅에 붙는다. grid 경로(_sheet_build.py)는 이 정렬을
    하지만 atlas 경로는 안 거쳐 "발이 공중에 뜨는" 현상이 생겼다 — 그래서 여기서 동일 정렬을 한다.

    scripts/align_feet.py 를 호출(pillow 필요 → uv 로 격리 실행, compress_pages 와 동일 패턴)."""
    script = os.path.join(HERE, "align_feet.py")
    uv = shutil.which("uv")
    cmd = ([uv, "run", "--with", "pillow", "python3", script, frames_dir, str(foot_frac)]
           if uv else ["python3", script, frames_dir, str(foot_frac)])
    o = subprocess.run(cmd, capture_output=True, text=True)
    if o.returncode != 0:
        print("  ⚠️ 낱장 발 정렬 실패 — 정렬 없이 진행(발이 뜰 수 있음):\n     "
              + (o.stderr or o.stdout or "")[-300:])
    else:
        print(f"  ✓ 낱장 발 정렬(0.85) — {o.stdout.strip()}")


def inject_action_scales(atlas_path, action_scales):
    """`.atlas` 첫 page 헤더(`repeat:` 줄 뒤)에 액션별 *생성 scale* 을 custom 메타로 주입한다.

    형식(액션당 한 줄):  `laryen.actionScale.<action>: <scale>`  (예: attack 0.8)

    🛑 왜 atlas 에 넣나: sheet.py 가 `--scale-<action>` 으로 그 행동 모델을 작게 구운 값(0.8)을,
    런타임(actor_animation_set.dart)이 읽어 화면 표시 배율 1/scale(=1.25)로 자동 복원한다. 이로써
    game.config.dart 의 kind 별 수동 상수(actorAttackScaleByKind 등)가 불필요해진다.

    안전성: flame_texturepacker 파서는 page 헤더의 *모르는* `key: value` 줄을 switch default
    없이 조용히 무시하고, `_readEntry` 는 콜론이 있으면 블록 종료로 오판하지 않으므로 기존
    atlas 로딩을 깨지 않는다(런타임은 이 텍스트를 별도로 읽어 파싱한다). 사이드카 파일 대신
    atlas 단일 파일에 담아 자산 이동/삭제 시 동기화 사고를 원천 차단한다."""
    try:
        with open(atlas_path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError as e:
        print(f"  ⚠️ .atlas 열기 실패 — scale 메타 주입 생략: {e}")
        return
    meta = [f"laryen.actionScale.{a}: {float(s):g}" for a, s in action_scales.items()]
    out, injected = [], False
    for ln in lines:
        out.append(ln)
        if not injected and ln.strip().startswith("repeat:"):
            out.extend(meta)
            injected = True
    if not injected:
        # 헤더에 repeat 줄이 없는 예외적 포맷 — 주입 생략(런타임은 fallback 1.0).
        print("  ⚠️ .atlas 에 'repeat:' 헤더 줄이 없어 scale 메타 주입 생략(런타임 1.0 fallback).")
        return
    with open(atlas_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("  ✓ .atlas 액션 scale 메타 주입: "
          + ", ".join(f"{a}={float(s):g}" for a, s in action_scales.items()))


def compress_pages(pages, colors=256):
    """packed atlas 페이지 PNG(들)를 compress_image.py 의 q256 으로 *in-place* 압축.
    🛑 in-place 라야 .atlas 의 페이지 참조(basename)가 유지된다."""
    results = []
    direct = None
    try:
        # compress_image.py 는 범용 PNG 압축 도구라 프로젝트 scripts/ 에 남아 있다
        # (compress-image 스킬이 공유). skill 로 이동한 본 파이프라인은 ROOT/scripts 에서 import.
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import compress_image as _ci   # noqa: E402
        from PIL import Image
        direct = (_ci, Image)
    except (Exception, SystemExit):
        # 🛑 compress_image.py 는 numpy/pillow 부재 시 *sys.exit()*(SystemExit) 를 던진다.
        #    SystemExit 는 Exception 이 아니므로 반드시 함께 잡아야 프로세스가 죽지 않고
        #    아래 subprocess(uv 격리) 폴백으로 넘어간다.
        direct = None
    for p in pages:
        before = os.path.getsize(p)
        if direct is not None:
            _ci, Image = direct
            _ci.compress_q256(Image.open(p), p, colors=colors)   # in-place
        else:
            build = os.path.join(ROOT, "scripts", "compress_image.py")
            uv = shutil.which("uv")
            if uv:
                cmd = [uv, "run", "--with", "numpy", "--with", "pillow",
                       "python3", build, p, "--inplace", "--colors", str(colors)]
            else:
                cmd = ["python3", build, p, "--inplace", "--colors", str(colors)]
            o = subprocess.run(cmd, capture_output=True, text=True)
            if o.returncode != 0:
                print(f"     ⚠️ 압축 실패({os.path.basename(p)}) — 원본 유지:")
                print("       " + (o.stderr or o.stdout or "")[-400:])
                results.append((p, before, before))
                continue
        results.append((p, before, os.path.getsize(p)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  pubspec.yaml 자동 갱신 — 이번 <name> 파일만 관리 블록에 추가.
# ─────────────────────────────────────────────────────────────────────────────
def update_pubspec(rel_paths):
    """pubspec 의 sheet.py 관리 블록을 assets/pc·mob·npc 디스크 스캔 기반으로 갱신한다.

    🛑 race 방지 (2026-07-01 female 투명 사고 회고): 과거엔 rel_paths(이번 산출물)만 기존
    블록에 union 했는데, 여러 sheet.py 를 *병렬* 실행하면 A 가 female 을 추가한 pubspec 을
    B 가 (female 없는) 이전 상태로 덮어써 일부가 누락됐다(female 이 pubspec 미등록 → 번들 제외
    → AssetManifest 없음 → 투명 placeholder). 이제 assets/pc·mob·npc 디스크를 *전체 스캔* 해
    존재하는 모든 <name>.{atlas,png} 를 등록하므로, 어느 실행이든 디스크 진실을 반영해 누락이
    없다. rel_paths 는 이번 산출물(로그 표시·즉시 포함 보장용)."""
    pubspec = os.path.join(ROOT, "pubspec.yaml")
    if not os.path.isfile(pubspec):
        print(f"  ⚠️ pubspec.yaml 없음 — 갱신 건너뜀: {pubspec}")
        return
    lines = open(pubspec, encoding="utf-8").read().split("\n")

    def entry_line(rel):
        # 공백 등 특수문자 있으면 따옴표.
        return f'    - "{rel}"' if any(c in rel for c in ' ()') else f"    - {rel}"

    # 기존 블록 찾기.
    b = e = -1
    for i, ln in enumerate(lines):
        if ln.rstrip() == PUBSPEC_MARK_BEGIN.rstrip():
            b = i
        elif ln.rstrip() == PUBSPEC_MARK_END.rstrip():
            e = i
            break

    existing = set()
    if b != -1 and e != -1 and e > b:
        for ln in lines[b + 1:e]:
            s = ln.strip()
            if s.startswith("- "):
                existing.add(s[2:].strip().strip('"'))

    # assets/pc·mob·npc 디스크 전체 스캔 — 존재하는 <name>.atlas + *모든 페이지 png* 를 등록(race 무관).
    # 🛑 멀티페이지 대응: 세로 trim off 등으로 아틀라스가 8192 를 넘으면 TexturePacker 가 <name>.png,
    #    <name>2.png, <name>3.png … 여러 페이지로 분할한다. <name>.png 만 스캔하면 2페이지 이상이
    #    pubspec 에서 빠져(번들 제외 → 게임에서 투명) 회귀한다 → glob 으로 모든 <name>*.png 를 등록.
    scanned = set()
    for cat in ("pc", "mob", "npc"):
        base = os.path.join(ROOT, "assets", cat)
        if not os.path.isdir(base):
            continue
        for nm in sorted(os.listdir(base)):
            d = os.path.join(base, nm)
            if not os.path.isdir(d):
                continue
            if os.path.isfile(os.path.join(d, nm + ".atlas")):
                scanned.add(f"assets/{cat}/{nm}/{nm}.atlas")
            # <name>.png, <name>2.png … (TexturePacker 멀티페이지) 전부 등록.
            for png in glob.glob(os.path.join(d, nm + "*.png")):
                scanned.add(f"assets/{cat}/{nm}/{os.path.basename(png)}")
    want = scanned | set(rel_paths)
    added = sorted(want - existing)
    removed = sorted(existing - want)   # 블록에 있었으나 디스크에 없는 항목(빌드 실패 유발) → 제거
    union = sorted(want)                # 🛑 디스크 진실만 — 파일 없는 등록은 자동 제거(bundle 실패 방지)
    block = [PUBSPEC_MARK_BEGIN] + [entry_line(r) for r in union] + [PUBSPEC_MARK_END]

    if b != -1 and e != -1 and e > b:
        lines = lines[:b] + block + lines[e + 1:]
    else:
        # 블록이 없으면 옛 actor_textures anchor 또는 assets: 바로 뒤에 새로 삽입.
        anchor = next((i for i, ln in enumerate(lines)
                       if ln.strip() == "- assets/render/actor_textures/"), None)
        if anchor is None:
            # 최후: 'assets:' 줄 바로 뒤.
            anchor = next((i for i, ln in enumerate(lines)
                           if ln.rstrip() == "  assets:"), None)
        if anchor is None:
            print("  ⚠️ pubspec 삽입 지점을 못 찾음 — 갱신 건너뜀.")
            return
        lines = lines[:anchor + 1] + block + lines[anchor + 1:]

    open(pubspec, "w", encoding="utf-8").write("\n".join(lines))
    if added:
        print(f"  ✓ pubspec.yaml 갱신 — 추가: {', '.join(added)}")
    if removed:
        print(f"  ✓ pubspec.yaml 정리 — 제거(디스크에 파일 없음, bundle 실패 방지): {', '.join(removed)}")
    if not added and not removed:
        print(f"  ✓ pubspec.yaml — 변경 없음(디스크 진실 {len(union)}개 항목 반영).")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=(
            "FBX/GLB/.blend → 라리엔 16방향 sprite atlas 생성 "
            f"(기본: {DEFAULT_RENDER_RES}px frame → {DEFAULT_CELL_SIZE}px TexturePacker atlas, "
            "256색 압축, pubspec 자동갱신)"
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True)
    # ── 핵심 옵션(대화형 지원 — 생략 시 물어봄) ──
    ap.add_argument("--actor", "--character", dest="character", default=None,
                    help="액터(캐릭터/몬스터) 모델(.fbx / .glb / .gltf / .blend). 확장자로 import 자동 분기. "
                         "생략 시 대화형 선택(--kind 폴더에서).")
    ap.add_argument("--kind", default=None, choices=["pc", "mob", "npc"],
                    help="액터 카테고리 — pc(플레이어/사람형), mob(몬스터), npc(마을 NPC). 출력: assets/<kind>/<name>/.")
    ap.add_argument("--name", default=None,
                    help="산출 texture 파일명(예: male_victor). → assets/<kind>/<name>/<name>.{png,atlas}")
    ap.add_argument("--animations", default=None,
                    help=f"애니 variant 폴더명 또는 경로({ANIM_ROOT}/<name>). 생략 시 대화형 목록 선택. "
                         "모든 애니는 Mixamo(본 이름 'mixamorig:').")
    # ── texture packing / 컬러 압축 토글 ──
    ap.add_argument("--texture-pack", dest="texture_pack", type=str2bool,
                    nargs="?", const=True, default=True, metavar="true|false",
                    help="TexturePacker atlas 사용(기본 true). false=균일 grid sheet 1장(legacy/디버그/수동 통합용).")
    ap.add_argument("--color-compression", dest="color_compression", type=str2bool,
                    nargs="?", const=True, default=True, metavar="true|false",
                    help="256색 팔레트 양자화(기본 true, 번들 용량 절감). false=무손실 RGBA.")
    ap.add_argument("--run-animation", dest="run_animation", type=str2bool,
                    nargs="?", const=True, default=None, metavar="true|false",
                    help="mob 의 run(달리기) 애니 포함 여부(true/false). *지정하면 대화형 질문을 "
                         "건너뛴다*. 미지정 시 mob 은 기본 제외(대화형이면 물어봄), pc 는 항상 포함. "
                         "예: --run-animation false → run 없이(디스크↓), --run-animation true → run 포함.")
    # ── 렌더 옵션(기존 유지) ──
    ap.add_argument("--cell-size", "--size", dest="cell_size", default=None,
                    help=f"TexturePacker atlas orig/grid cell 픽셀 크기(기본: pc/npc={DEFAULT_CELL_SIZE}, "
                         f"mob={DEFAULT_CELL_SIZE_MOB} — 몬스터는 pc 만큼 선명할 필요 없어 낮춰 디스크 절감). "
                         f"기본 렌더 {DEFAULT_RENDER_RES}px frame 을 이 크기로 축소해 packing "
                         "(--scale-frames 자동 = cell/render_res). "
                         f"게임 표시는 {RUNTIME_DISPLAY_SIZE}px(kActorDisplaySize)로 축소 렌더. "
                         "grid: Σframes×cell ≤ 8192")
    ap.add_argument("--k", type=float, default=128.0,
                    help="K=목표 화면 몸 높이 px. display=K/body_ratio (grid manifest 기록)")
    ap.add_argument("--directions", type=int, default=None, choices=[8, 16],
                    help="방향 수(=row 수). pc/mob 기본 16, npc 기본 8. 16의 짝수 row 가 8방향과 일치")
    for a in FRAME_OPTION_ACTIONS:
        ap.add_argument(f"--{a}", type=int, help=f"{a} 프레임(셀) 수")
    for a in FRAME_OPTION_ACTIONS:
        ap.add_argument(f"--scale-{a}", type=float, default=None, dest=f"scale_{a}",
                        help=f"{a} 행동만 scale 오버라이드(미지정=전역 --scale). <1=그 행동 모델 작게")
    ap.add_argument("--weapon", default=None,
                    help="무기 모델(.fbx/.glb) — 캐릭터 손 본에 장착해 함께 렌더. 🛑 T-pose 캐릭터 필요.")
    ap.add_argument("--weapon-bone", default=None,
                    help="무기 부착 본(기본 mixamorig:RightHand). 방패 등은 mixamorig:LeftHand.")
    ap.add_argument("--weapon-loc", default=None, help="무기 위치 미세조정 'x,y,z'(미터).")
    ap.add_argument("--weapon-rot", default=None, help="무기 회전 미세조정 'rx,ry,rz'(도).")
    ap.add_argument("--weapon-scale", type=float, default=None, help="무기 스케일 배율.")
    ap.add_argument("--margin", type=float, default=1.3,
                    help="auto-fit 안전 여백 배율. 무기 끝이 잘리면 키운다(예 1.4).")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="셀 안 모델 전체 크기 배율(기본 1.0). >1 크게 · <1 작게.")
    ap.add_argument("--elev", type=float, default=30.0, help="카메라 고각(2:1=30°)")
    ap.add_argument("--shading", choices=["eevee", "texture"], default="eevee",
                    help="렌더 셰이딩. eevee=PBR 3점 조명(기본) · texture=WORKBENCH TEXTURE")
    ap.add_argument("--vivid", type=int, default=5, choices=range(1, 10), metavar="1-9",
                    help="색상 진하기(대비)+밝기 강도(1~9, 기본 5). 5=적당히 밝고 진하게, "
                         "9=최대, 1=부스트 없음. 렌더 후 compositor 로 자동 적용.")
    ap.add_argument("--render-res", type=int, default=0,
                    help=f"Blender 개별 frame 렌더 해상도(기본 max({DEFAULT_RENDER_RES}, --cell-size)). "
                         f"기본값 조합은 {DEFAULT_RENDER_RES}px render → {DEFAULT_CELL_SIZE}px atlas.")
    ap.add_argument("--draft", action="store_true", help="초고속 미리보기(render_res=cell·AA 끔)")
    ap.add_argument("--actions", default=None,
                    help="행동 순서/목록. 기본 pc/mob=idle,walk,attack,hit,death,run; npc=idle,look,talk,walk,wave")
    ap.add_argument("--output", default=None, dest="output_base",
                    help="결과 atlas/png 를 저장할 베이스 폴더(기본: 프로젝트 루트의 assets/). "
                         "지정하면 <output>/<kind>/<name>/<name>.{png,atlas} 로 자동 생성·저장한다. "
                         "예: --output ./viewer/assets → ./viewer/assets/<kind>/<name>/<name>.{png,atlas}. "
                         "🛑 --output 을 주면 pubspec.yaml 자동 갱신은 건너뛴다(대상 폴더가 다른 앱/뷰어일 수 "
                         "있어 루트 pubspec 을 오염시키지 않기 위함 — 필요 시 수동 등록). "
                         "중간 frames 폴더는 --outputs(복수형)로 따로 지정한다.")
    ap.add_argument("--outputs", default=None, help="중간 작업(frames) 폴더. 기본 outputs/<name>")
    ap.add_argument("--info-out", default=None,
                    help="manifest/layout 저장 폴더(grid 모드, 기본 game-assets/sprites)")
    ap.add_argument("--blender", default="")
    ap.add_argument("--render-only", action="store_true", help="렌더만(패킹/합치기 생략)")
    ap.add_argument("--build-only", action="store_true",
                    help="합치기/패킹만(기존 outputs/<name>/frames 낱장 재사용)")
    ap.add_argument("--verbose", action="store_true", help="Blender/packer 전체 로그 출력")
    # ── TexturePacker 전용 ──
    ap.add_argument("--java", default="", dest="java_bin", help="java 실행 파일(기본 자동 탐지)")
    ap.add_argument("--packer-cp", default="",
                    help=f"gdx-tools classpath(구분자 '{os.pathsep}'). 미지정 시 자동 다운로드.")
    ap.add_argument("--max-page-w", type=int, default=8192, help="packed page 최대 너비(기본 8192)")
    ap.add_argument("--max-page-h", type=int, default=2048, help="packed page 최대 높이(기본 2048)")
    ap.add_argument("--scale-frames", type=float, default=None,
                    help="패킹 전 낱장 리사이즈 배율. 미지정 시 아틀라스 orig=cell 이 되도록 자동 "
                         f"(cell/render_res, 기본 {DEFAULT_CELL_SIZE}/{DEFAULT_RENDER_RES}=0.625 → orig {DEFAULT_CELL_SIZE}). "
                         "명시값은 실험용이며, cell 과 orig 가 어긋나면 화면 비례 검증이 필요하다.")
    ap.add_argument("--rotation", type=str2bool, nargs="?", const=True, default=None,
                    metavar="true|false",
                    help="회전 packing(공간 절약). **기본 true**. 미지정 시 대화형으로 물어보고"
                         "(비대화형이면 true), `--rotation true|false` 로 명시하면 질문을 건너뛴다. "
                         "값 없이 `--rotation` 만 줘도 true(하위호환). 🛑 actor(pc/mob/npc)는 "
                         "`--rotation false` 권장 — flame_texturepacker 의 rotate + useOriginalSize "
                         "offset 렌더가 발 위치를 어긋나게 해(회전 프레임만 offset 스왑·부호변경) attack "
                         "등에서 발이 뜨고, 16방향(~1024프레임)은 패킹이 20분+ 걸린다. false 면 모든 "
                         "프레임이 단순 offset 경로라 발 정렬(0.85)이 화면에 정확히 반영된다. 정적 "
                         "타일/decor 등 발 정렬이 무관하고 프레임이 적은 자산은 true 로 공간을 절약한다.")
    ap.add_argument("--no-rotation", dest="rotation", action="store_const", const=False,
                    help="`--rotation false` 의 별칭(하위호환) — 회전 packing 을 끈다.")
    ap.add_argument("--pot", action="store_true", help="force POT 켬(기본 끔)")
    ap.add_argument("--strip-whitespace", dest="strip_whitespace", type=str2bool,
                    nargs="?", const=True, default=True, metavar="true|false",
                    help="가로(X) 여백 trim(기본 **true**). true 면 idle_ESE 처럼 좌우 투명 여백을 "
                         "잘라 아틀라스 가로 폭·page 픽셀(=RAM)을 줄인다(발 y 무관). false 면 원본 셀 "
                         "폭을 유지. 🛑 세로(Y) trim 은 발 정렬(0.85) 보존 위해 이 옵션과 무관하게 항상 off.")
    ap.add_argument("--keep-whitespace", dest="strip_whitespace", action="store_const", const=False,
                    help="`--strip-whitespace false` 의 별칭(하위호환) — 가로 여백 trim 을 끈다.")
    ap.add_argument("--no-fast", dest="fast", action="store_false",
                    help="정밀(느린) 패킹. 기본 fast=True(16방향 액터 필수).")
    ap.set_defaults(fast=True)

    # 사용자가 texture-pack / color-compression 를 명시했는지(대화형 확인 생략 판단용).
    argv = sys.argv[1:]
    tp_explicit = any(a == "--texture-pack" or a.startswith("--texture-pack=") for a in argv)
    cc_explicit = any(a == "--color-compression" or a.startswith("--color-compression=") for a in argv)
    args = ap.parse_args()
    args._texture_pack_explicit = tp_explicit
    args._color_compression_explicit = cc_explicit

    # ── 대화형: 빠진 값 채우기 ──
    args = prompt_missing(args)

    # cell 크기: --cell-size 미지정이면 kind 기본(pc/npc/mob 전부 128 통일, 2026-07-05).
    if args.cell_size is None:
        cell = DEFAULT_CELL_SIZE_MOB if args.kind == "mob" else DEFAULT_CELL_SIZE
    else:
        cell = parse_size(args.cell_size)
    if args.directions is None:
        args.directions = 8 if args.kind == "npc" else 16
    if args.actions is None:
        if args.kind == "npc":
            args.actions = ",".join(NPC_ACTIONS)
        elif args.kind == "mob":
            # mob 기본은 run 제외(디스크 절감). 포함 결정 우선순위:
            #   --run-animation(명시) > --run N > 대화형 답(_mob_include_run) > 기본 제외.
            if args.run_animation is not None:
                include_run = args.run_animation            # 명시값이 최우선(질문 없이 true/false)
            else:
                include_run = (args.run is not None) or getattr(args, "_mob_include_run", False)
            args.actions = ",".join(DEFAULT_ACTIONS if include_run else MOB_ACTIONS)
        else:  # pc
            args.actions = ",".join(DEFAULT_ACTIONS)
    directions = args.directions
    actions = [a.strip() for a in args.actions.split(",") if a.strip()]
    if args.kind == "npc":
        if directions != 8:
            sys.exit("--kind npc 는 8방향만 지원합니다. --directions 8 로 생성하세요.")
        if actions != NPC_ACTIONS:
            sys.exit("--kind npc 는 idle,look,talk,walk,wave 5개 애니메이션만 지원합니다.")
    elif directions == 8:
        print("  ⚠️  --directions 8 은 PC/mob legacy sheet 재생성 호환용입니다(신규 PC/mob 는 16방향).")
    name = args.name

    # ── 입력(모델) 검증 ──
    if not os.path.isfile(args.character):
        # kind 폴더 기준 상대경로도 시도.
        cand = os.path.join(ROOT, KIND_MODEL_DIR[args.kind], args.character)
        if os.path.isfile(cand):
            args.character = cand
        else:
            alt = next((args.character + e for e in CHAR_EXT
                        if os.path.isfile(args.character + e)), None)
            if alt:
                print(f"  ℹ️  '{args.character}' 없음 → 확장자 자동 보정: {alt}")
                args.character = alt
            else:
                sys.exit(f"캐릭터 모델이 없습니다: {args.character}\n"
                         f"   → 지원 확장자: {'/'.join(CHAR_EXT)}")
    char_ext = os.path.splitext(args.character)[1].lower()
    if char_ext not in CHAR_EXT:
        sys.exit(f"지원하지 않는 캐릭터 형식: {char_ext or '(확장자 없음)'} — {args.character}")
    if char_ext == ".blend":
        print("  ℹ️  .blend 캐릭터 — Blender 로 직접 열어 렌더.")
    else:
        assert_mixamo_rig(args.character, "캐릭터(--character)")

    # ── 무기(선택) ──
    weapon_bone = "mixamorig:RightHand"
    weapon_loc = weapon_rot = [0.0, 0.0, 0.0]
    weapon_scale, weapon_ref_height = 1.0, 0.0
    if args.weapon:
        if not os.path.isfile(args.weapon):
            alt = next((args.weapon + e for e in SUPPORTED_EXT
                        if os.path.isfile(args.weapon + e)), None)
            if alt:
                print(f"  ℹ️  '{args.weapon}' 없음 → 확장자 자동 보정: {alt}")
                args.weapon = alt
            else:
                sys.exit(f"무기 모델이 없습니다: {args.weapon}")
        if os.path.splitext(args.weapon)[1].lower() not in SUPPORTED_EXT:
            sys.exit(f"지원하지 않는 무기 형식: {args.weapon} (지원: {'/'.join(SUPPORTED_EXT)})")

        def _triple(s, nm):
            try:
                v = [float(x) for x in s.split(",")]
                assert len(v) == 3
                return v
            except Exception:
                sys.exit(f"{nm} 는 'x,y,z' 형식(숫자 3개)이어야 합니다: {s!r}")
        prof, prof_path = {}, os.path.splitext(args.weapon)[0] + ".attach.json"
        if os.path.isfile(prof_path):
            try:
                prof = json.load(open(prof_path, encoding="utf-8"))
            except Exception as e:
                sys.exit(f"무기 프로파일 JSON 파싱 실패: {prof_path}\n   {e}")
            print(f"  ℹ️  무기 프로파일 로드: {prof_path}")
        else:
            print(f"  ⚠️  무기 프로파일 없음: {prof_path} → 기본값/CLI 로 진행.")
        weapon_bone = args.weapon_bone or prof.get("bone") or "mixamorig:RightHand"
        weapon_loc = _triple(args.weapon_loc, "--weapon-loc") if args.weapon_loc is not None \
            else [float(x) for x in prof.get("loc", [0.0, 0.0, 0.0])]
        weapon_rot = _triple(args.weapon_rot, "--weapon-rot") if args.weapon_rot is not None \
            else [float(x) for x in prof.get("rot", [0.0, 0.0, 0.0])]
        weapon_scale = args.weapon_scale if args.weapon_scale is not None \
            else float(prof.get("scale", 1.0))
        weapon_ref_height = float(prof.get("ref_height", 0.0))

    # ── 애니메이션 폴더 해석 + 검증 ──
    animations_dir = resolve_animations_dir(args.animations)

    def anim_file(a):
        return next((os.path.join(animations_dir, a + e) for e in SUPPORTED_EXT
                     if os.path.isfile(os.path.join(animations_dir, a + e))), None)
    have = [a for a in actions if anim_file(a)]
    if not have:
        sys.exit(f"애니 폴더에 {{action}}.{{fbx|glb|gltf}} 가 하나도 없습니다: {animations_dir}\n"
                 f"   필요(예): " + ", ".join(f"{a}.fbx" for a in actions))
    miss_act = [a for a in actions if a not in have]
    if miss_act:
        print(f"  ⚠️  애니 누락(해당 행동은 빈 프레임): {', '.join(miss_act)}")
    for a in have:
        assert_mixamo_rig(anim_file(a), f"애니메이션 '{a}'({os.path.basename(anim_file(a))})")

    frames = {a: int(DEFAULT_FRAMES.get(a, 8)) for a in actions}
    for a in FRAME_OPTION_ACTIONS:
        v = getattr(args, a)
        if v is not None and a in frames:
            frames[a] = v
    action_scales = {}
    for a in actions:
        ov = getattr(args, f"scale_{a}")
        action_scales[a] = float(ov) if ov is not None else float(args.scale)
    if args.render_res:
        render_res = args.render_res
    elif args.draft:
        render_res = cell
    else:
        render_res = max(DEFAULT_RENDER_RES, cell)   # 기본: 256 raw frame → 160 atlas/grid cell.

    # ── scale-frames 자동: 미지정 시 아틀라스 프레임 orig 를 런타임 sprite cell 과 같게 맞춘다
    # (cell/render_res, 기본 render 256 · cell 160 → 0.625 → atlas orig 160). 아틀라스는 이 orig 를
    # 컴포넌트 kActorDisplaySize(128)에 축소 렌더하므로 화면 크기가 정합한다(cell 은 화질 축, 표시는 128).
    # 값을 명시하면 그대로 사용하되, orig 와 런타임 표시 비례를 직접 시각 검증해야 한다.
    if args.scale_frames is None:
        args.scale_frames = cell / render_res

    # ── 출력 경로: <output_base>/<kind>/<name>/ (기본 output_base = ROOT/assets) ──
    # --output 미지정 → 프로젝트 루트의 assets/ (Flutter Flame 표준 자산 폴더).
    # --output DIR 지정 → 그 폴더 아래 <kind>/<name>/ 을 자동 생성(예: --output ./viewer/assets
    #   → ./viewer/assets/<kind>/<name>/). 상대경로는 cwd 가 아니라 프로젝트 루트(ROOT) 기준으로
    #   해석해, 스크립트를 어디서 실행하든 결과 위치가 동일하게 예측된다.
    if args.output_base:
        output_base = args.output_base if os.path.isabs(args.output_base) \
            else os.path.abspath(os.path.join(ROOT, args.output_base))
    else:
        output_base = os.path.join(ROOT, "assets")
    out_folder = os.path.join(output_base, args.kind, name)
    outputs = os.path.abspath(args.outputs) if args.outputs \
        else os.path.abspath(os.path.join(ROOT, "outputs", name))
    frames_dir = os.path.join(outputs, "frames")
    measure_path = os.path.join(outputs, "_measure.json")
    info_out_dir = os.path.abspath(args.info_out) if args.info_out \
        else os.path.abspath(os.path.join(ROOT, "game-assets", "sprites"))

    # grid 모드 컬러 압축: color-compression true → 256색 양자화, false → 0(무손실).
    png_colors = 256 if args.color_compression else 0

    cfg = {
        "character": os.path.abspath(args.character),
        "animations_dir": animations_dir,
        "use_embedded_anim": False,
        "outputs": outputs, "name": name, "frames_dir": frames_dir,
        "measure_path": measure_path,
        "sheet_out_dir": out_folder, "info_out_dir": info_out_dir,
        "kind": name, "k": args.k,
        "size": cell, "directions": directions,
        "frames": frames, "actions": actions,
        "action_scales": action_scales,
        "loop_actions": (["idle", "walk"] if args.kind == "npc" else ["idle", "walk", "run"]),
        "render_res": render_res, "elev": args.elev, "margin": args.margin,
        "scale": args.scale, "shading": args.shading,
        "color_level": int(args.vivid),
        "png_colors": png_colors, "draft": args.draft,
        "weapon": (os.path.abspath(args.weapon) if args.weapon else None),
        "weapon_bone": weapon_bone, "weapon_loc": weapon_loc,
        "weapon_rot": weapon_rot, "weapon_scale": weapon_scale,
        "weapon_ref_height": weapon_ref_height,
    }
    os.makedirs(outputs, exist_ok=True)
    cfg_path = os.path.join(outputs, "_sheet_config.json")
    json.dump(cfg, open(cfg_path, "w"), indent=2)

    total_cols = sum(frames.get(a, 8) for a in actions)
    grid_w, grid_h = total_cols * cell, directions * cell
    over = grid_w > TEXTURE_LIMIT or grid_h > TEXTURE_LIMIT
    rel_folder = os.path.relpath(out_folder, ROOT)
    print("=" * 64)
    print(f"  액터       : {args.character}  (형식 {char_ext}, kind={args.kind}, name={name})")
    print(f"  애니 폴더  : {animations_dir}  ({', '.join(actions)})")
    if args.weapon:
        print(f"  무기 장착  : {args.weapon} → {weapon_bone}")
    mode = "packed atlas (TexturePacker)" if args.texture_pack else f"grid sheet (균일 {cell})"
    print(f"  산출 방식  : {mode}")
    print(f"  출력 폴더  : {rel_folder}/{name}.png" + ("  + .atlas" if args.texture_pack else ""))
    print(f"  셰이딩     : {args.shading}" + ("  (PBR 3점 조명)" if args.shading == "eevee" else "  (WORKBENCH TEXTURE)"))
    print(f"  색상 강도  : vivid={args.vivid}/9  (대비+밝기 부스트, 5=중간)")
    print(f"  컬러 압축  : " + ("256색 양자화(~80%↓, 육안 동일)" if args.color_compression else "무손실 RGBA"))
    print(f"  cell 크기  : {cell}px   렌더 {render_res}px" + ("  ⚡draft" if args.draft else ""))
    print(f"  행동/셀 수 : " + "   ".join(f"{a}={frames.get(a, 8)}" for a in actions))
    if not args.texture_pack:
        print(f"  grid sheet : {total_cols} col × {directions} row = {grid_w} x {grid_h} px"
              + ("   ⚠️ 8192 초과!" if over else "   (8192 이내 OK)"))
    print("=" * 64)

    blender = find_blender(args.blender)
    total_frames = directions * sum(frames.get(a, 8) for a in actions)

    # ── [1] Blender 렌더 → 낱장 ──
    if not args.build_only:
        print("\n[1] Blender 렌더 중 …")
        proc = subprocess.Popen(
            [blender, "-b", "-P", os.path.join(HERE, "_sheet_render.py"), "--", cfg_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace",
        )
        saved, errs, render_done = 0, [], False
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith("####RENDER_DONE"):
                render_done = True
            if args.verbose:
                print(line); continue
            if line.startswith("####"):
                print("   " + line[4:])
            elif line.startswith("Saved:"):
                saved += 1
                if saved % 24 == 0 or saved == total_frames:
                    pct = int(saved / total_frames * 100) if total_frames else 0
                    print(f"   … {saved}/{total_frames} ({pct}%)", flush=True)
            elif any(k in line for k in ("Error", "Traceback", "Exception", "Failed")):
                errs.append(line)
        proc.wait()
        actual_frames = (len([f for f in os.listdir(frames_dir) if f.endswith(".png")])
                         if os.path.isdir(frames_dir) else 0)
        if proc.returncode == 0 and not render_done and actual_frames >= total_frames:
            print(f"   ⚠️ RENDER_DONE 마커 누락이나 frames {actual_frames}/{total_frames} 완성 → 진행")
            render_done = True
        if proc.returncode != 0 or not render_done:
            print("   ❌ 렌더 실패 — 입력 FBX / Blender 로그 확인:")
            for e in errs[-20:]:
                print("     " + e)
            sys.exit("렌더 실패")

    if args.render_only:
        print("\n(--render-only) 낱장:", frames_dir, "\n완료.")
        return

    # ── [2] 합치기/패킹 ──
    rel_paths = []
    if args.texture_pack:
        print("\n[2] TexturePacker 로 packed atlas 만드는 중 …")
        if not os.path.isdir(frames_dir) or not any(
                f.endswith(".png") for f in os.listdir(frames_dir)):
            sys.exit(f"패킹할 낱장 PNG 가 없습니다: {frames_dir}")
        java = find_java(args.java_bin)
        print(f"  Java       : {java}")
        classpath = ensure_packer_classpath(args.packer_cp)
        # TexturePacker 前: 낱장 발(0.85) 정렬 — 행동별 scale(attack 등)의 발 뜸 방지(anchor 정합).
        align_frames_feet(frames_dir)
        # 🛑 _foot/ 마스크는 발 정렬(align_frames_feet) *전용* 이다 — 검·무기를 뺀 캐릭터 실루엣으로
        # 진짜 발 위치를 찾는 빌드용 보조 프레임이며, 런타임 렌더(findSpritesByName('<action>_<DIR>'))
        # 에는 전혀 쓰이지 않는다(이름 패턴 불일치). packing 폴더에 남으면 <name>2.png 로 함께 구워져
        # 런타임에 상주만 하고 안 그려지는 순수 RAM 낭비(종당 ~2MB·actor 전체 ~87MB, iOS OOM)다.
        # 발 정렬을 마쳤으니 packing 직전에 빼고, 끝나면 복원한다(다음 --build-only 재사용 위해 보존).
        foot_dir = os.path.join(frames_dir, "_foot")
        foot_stash = os.path.join(outputs, ".foot_stash")
        foot_stashed = False
        if os.path.isdir(foot_dir):
            if os.path.isdir(foot_stash):
                shutil.rmtree(foot_stash)
            shutil.move(foot_dir, foot_stash)
            foot_stashed = True
        try:
            pack_json_path, settings = write_pack_json(frames_dir, args)
            print(f"  설정: rotation={settings['rotation']} pot={settings['pot']} "
                  f"maxPage={settings['maxWidth']}x{settings['maxHeight']} "
                  f"scale={settings['scale'][0]} fast={settings['fast']}")
            run_texture_packer(java, classpath, frames_dir, out_folder, name, args.verbose)
        finally:
            if foot_stashed:
                shutil.move(foot_stash, foot_dir)  # 다음 --build-only 재사용 위해 복원
        atlas = os.path.join(out_folder, name + ".atlas")
        pages = sorted(glob.glob(os.path.join(out_folder, name + "*.png")))
        if not os.path.isfile(atlas) or not pages:
            sys.exit(f"패킹 산출물이 없습니다(atlas={atlas}, pages={pages}). --verbose 로 확인.")
        print(f"  ✓ packed atlas → {os.path.relpath(atlas, ROOT)}")
        # 액션별 생성 scale 을 .atlas 헤더에 주입 → 런타임이 1/scale 로 display 배율 자동 복원.
        inject_action_scales(atlas, action_scales)
        if args.color_compression:
            print(f"  [3] 페이지 PNG 압축 중 … (q256 · in-place)")
            for p, before, after in compress_pages(pages, colors=256):
                pct = 100 * (before - after) / before if before else 0
                print(f"     {os.path.basename(p)}  {before/1e6:.1f}MB → {after/1e6:.1f}MB  ({pct:.0f}% 작아짐)")
        for p in pages:
            print(f"     page: {os.path.relpath(p, ROOT)}  ({os.path.getsize(p)/1e6:.1f}MB)")
        # pubspec 등록 대상: atlas + 모든 페이지 PNG.
        rel_paths = [os.path.relpath(atlas, ROOT)] + [os.path.relpath(p, ROOT) for p in pages]
    else:
        print("\n[2] 균일 통합 grid sprite sheet 합치는 중 …")
        build = os.path.join(HERE, "_sheet_build.py")
        uv = shutil.which("uv")
        cmd = ([uv, "run", "--with", "numpy", "--with", "pillow", "python3", build, cfg_path]
               if uv else ["python3", build, cfg_path])
        out = subprocess.run(cmd, capture_output=True, text=True)
        r, ok = None, False
        for line in out.stdout.splitlines():
            if line.strip().startswith("{"):
                r = json.loads(line); ok = True
        if not ok or out.returncode != 0:
            print(out.stdout[-1000:]); print(out.stderr[-2000:]); sys.exit("sheet 합치기 실패")
        if r.get("total_cells", 0) == 0:
            print(f"  ❌ 렌더된 프레임 0개 — frames/ 가 비었습니다 ({frames_dir}).")
            sys.exit("빈 시트 — 렌더 실패")
        tb = r.get("total_bytes", 0)
        pc = r.get("png_colors", 256)
        comp = f"{pc}색 양자화" if pc > 0 else "무손실"
        sw, sh = r.get("size", [0, 0])
        png_path = os.path.join(out_folder, name + ".png")
        print(f"  ✓ grid sheet → {os.path.relpath(png_path, ROOT)}  {sw}x{sh}"
              + (f"   ({tb/1e6:.1f}MB, {comp})" if tb else ""))
        print(f"  📄 manifest: {r.get('manifest')}")
        rel_paths = [os.path.relpath(png_path, ROOT)]

    # ── [끝] pubspec.yaml 갱신 (기본 assets/ 출력일 때만) ──
    # --output 지정 시엔 대상이 루트 assets/ 가 아닐 수 있어(예: 별도 뷰어 앱) 루트 pubspec 을
    # 건드리지 않는다 — 그 폴더는 사용자가 관리하는 커스텀 위치이므로 자동 등록을 건너뛴다.
    if args.output_base:
        print(f"\n[pubspec] --output 지정 → 루트 pubspec.yaml 자동 갱신 건너뜀. "
              f"결과: {os.path.relpath(out_folder, ROOT)}/  (필요 시 대상 앱에 수동 등록)")
    else:
        print("\n[pubspec] 갱신 중 …")
        update_pubspec(rel_paths)

    print("\n완료.")


if __name__ == "__main__":
    main()
