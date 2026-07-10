"""
라리엔 16/8방향 sprite 렌더 (Blender 4.4+, EEVEE) — scripts/sheet.py 가 config json 으로 호출.

FBX/GLB(glTF) 캐릭터(메쉬+리그) → 16 또는 8방향 × 행동별 낱장 PNG.
**확장자(.fbx / .glb / .gltf)로 import 방식을 자동 분기**한다.
방향 수는 cfg["directions"] (16 기본 / 8). azimuth = (270 + 360/N * i) % 360.

애니메이션 소스(cfg["use_embedded_anim"] / cfg["animations_dir"]):
  - 내장(use_embedded_anim=True, animations_dir=None): 액터 파일에 baked 된 애니메이션
    (tripo3d.ai 가 6 애니메이션을 넣은 FBX, sorceress.games Text-to-Animation GLB 등)을
    행동 이름(idle/walk/…)에 자동 매칭. 클립 이름이 별칭(공격=slash, 사망=defeat_<n>,
    피격=hit_x_x)이라도 ACTION_ALIASES 부분 매칭으로 인식한다.
  - 외부(animations_dir=<dir>): 폴더의 {action}.fbx/.glb 를 import 해 적용(개발자 직접).

핵심:
  - import: 캐릭터 1개 + (외부 모드) 각 애니 action merge (임시 Armature/메쉬 삭제)
  - Hips(root motion 추적 골반 본) 이름은 리그마다 다름 → 자동 감지(mixamorig:Hips/pelvis/root)
  - 누움 자동 감지 → 세우기 보정 (FBX 는 보통 Z-up; glTF 는 importer 가 +Y→+Z 자동 변환)
  - **auto-fit framing** — 무기 포함 전체 모델 bbox 를 margin 여유로 셀에 담는다.
    include-weapon/character-size 옵션은 폐지(큰 무기면 캐릭터가 셀 안에서 작아지고,
    그 비율 body_ratio 를 측정해 런타임 K 로 화면 크기를 보정한다).
  - **body_ratio / foot_anchor 측정** — head~foot 본을 화면(0~1)으로 투영해
    ① body_ratio(몸 높이 비율, 무기 무관) ② foot_anchor(발의 셀 내 y=도착지) 를
    measure_path json 으로 출력 → _sheet_build.py 가 manifest 에 기록, display=K/body_ratio.
  - 카메라 N방향(16 기본/8) 공전(2:1 dimetric) + 3점 조명(카메라 자식) + AgX→Standard
  - per-frame Hips 추적(root motion 상쇄 = in-place cycle)
  - 애니메이션이 없으면 정적(rest/T-pose) 16방향 폴백(정적 몹/오브젝트용)

호출: blender -b -P scripts/_sheet_render.py -- <config.json>
"""
import bpy, math, os, sys, json, functools, re
from mathutils import Vector, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view

print = functools.partial(print, flush=True)   # ####정보를 즉시 flush(렌더 로그와 시간순 정렬)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
cfg = json.load(open(argv[0]))

CHARACTER      = cfg["character"]
ANIM_DIR       = cfg.get("animations_dir")           # None → 캐릭터 파일 내장 애니메이션 사용
USE_EMBEDDED   = bool(cfg.get("use_embedded_anim", ANIM_DIR is None))
FRAMES         = cfg["frames"]                       # {"idle":8, ...}
ACTIONS        = cfg["actions"]                      # ["idle","walk","attack","hit","death","run"]
# ONLY_ACTIONS(선택): auto-fit 재렌더 시 *잘린 행동만* 다시 굽기 위한 부분 렌더 화이트리스트.
# None(기본) → ACTIONS 전체 렌더(+ 낱장 폴더 전체 wipe). 리스트가 주어지면(예 ["attack"]) 그
# 행동들의 낱장·_foot 마스크만 지우고 그 행동만 재렌더한다 → 정상적으로 구워진 다른 행동(idle/walk
# 등)의 낱장은 *보존* 되어 불필요한 재렌더가 사라진다(sheet.py/sheet-win.py auto-fit 최적화).
# 🛑 framing(ortho_base)은 행동과 무관하게 몸 bbox 에서 한 번 계산되므로, 부분 재렌더해도 남은
# 행동과 셀 크기가 정합한다(재렌더 attack 프레임이 보존된 idle 프레임과 같은 크기 기준).
ONLY_ACTIONS   = cfg.get("only_actions")             # None=전체 · 리스트=그 행동만 재렌더
LOOP           = set(cfg.get("loop_actions", ["idle", "walk", "run"]))
OUT_FRAMES     = cfg["frames_dir"]
RENDER_RES     = int(cfg["render_res"])
ELEV_DEG       = float(cfg["elev"])
MARGIN         = float(cfg.get("margin", 1.3))       # auto-fit 안전 여백(전체 모델 + 무기 휘두름 여유)
# SCALE: 셀 안에서 모델 전체(캐릭터+무기)를 키우거나(>1) 줄이는(<1) 사용자 배율. MARGIN(잘림
# 방지 여백)과 달리 "이 자산을 의도적으로 크게/작게" 의 의미. ortho 를 SCALE 로 나누므로
# SCALE↑ → 보이는 영역↓ → 모델 크게, SCALE↓ → 영역↑ → 모델 작게(직관 일치). 기본 1.0=무변화.
SCALE          = float(cfg.get("scale", 1.0))
# 행동(애니메이션)별 *최종* scale {action: scale} — 전역 --scale 의 행동별 버전(전역값 포함:
# sheet.py 가 --scale-<a> 지정시 그 값, 미지정시 전역 --scale 로 채워 보낸다). scale<1 → 그
# 행동 렌더 시 ortho 를 base/scale 로 키워 모델을 작게 그린다 → run/attack 의 칼 휘두름·팔다리가
# 셀 안에 들어옴(무기 잘림 방지). cell 은 균일 128. 작게 구운 만큼 화면이 작아지면, 사람이
# dart config kActorDisplayKByKind 에 1/scale 을 입력해 화면 몸 크기를 유지한다(SSOT 는 dart).
ACTION_SCALES  = cfg.get("action_scales", {}) or {}
CELL_PX        = int(cfg["size"])
MEASURE_PATH   = cfg.get("measure_path")             # body_ratio/foot_anchor 측정 결과 저장 경로
# 셰이딩 모드: "eevee"(기존 PBR 조명) | "texture"(WORKBENCH TEXTURE — metallic/갑옷 자산을
# 밝고 텍스처 색 그대로. EEVEE 가 raytracing 미사용 시 금속을 검게 렌더하는 문제 회피).
SHADING        = cfg.get("shading", "eevee")
# 색상 진하기(대비)+밝기 강도 1~9(기본 5). 렌더 결과를 compositor BrightContrast 로 후처리해
# 자동으로 밝고 진하게 만든다(WORKBENCH/EEVEE 무관, 알파 통과). 5=적당한 부스트, 9=최대, 1=무보정.
COLOR_LEVEL    = int(cfg.get("color_level", 5))
# draft: 초고속 미리보기 — render_res=cell(1x)·AA 끔·텍스처 디스크검색 끔. 방향/애니 매칭 확인용.
DRAFT          = bool(cfg.get("draft", False))
# 무기 장착(선택): WEAPON=None 이면 무기 없음. 손 본(WEAPON_BONE)에 메쉬를 armature modifier 로 고정.
WEAPON         = cfg.get("weapon")
WEAPON_BONE    = cfg.get("weapon_bone", "mixamorig:RightHand")
WEAPON_LOC     = cfg.get("weapon_loc", [0.0, 0.0, 0.0])
WEAPON_ROT     = cfg.get("weapon_rot", [0.0, 0.0, 0.0])
WEAPON_SCALE   = float(cfg.get("weapon_scale", 1.0))
# 무기 크기 자동보정 기준 키(프로파일 ref_height). >0 이면 현재 캐릭터 키 비례로 무기 스케일.
WEAPON_REF_H   = float(cfg.get("weapon_ref_height", 0.0))

# FLARE 방향 SSOT — 16방향(기본). 8방향 = 16방향의 짝수 인덱스(E,SE,S,SW,W,NW,N,NE = 0,2,…,14).
# sheet.py / _sheet_build.py 와 동일. azimuth = (270 + 360/N * i) % 360 (maria 8방향 검증).
DIR16_LABELS = ["E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW",
                "W", "WNW", "NW", "NNW", "N", "NNE", "NE", "ENE"]
DIRECTIONS = int(cfg.get("directions", 16))
if DIRECTIONS not in (1, 8, 16):
    raise Exception(f"directions 는 1, 8, 16 만 지원합니다: {DIRECTIONS}")
if DIRECTIONS == 1:
    # npc 단방향(2026-07-10) — 정면(S, 남향) 1방향만 렌더한다(idle 단일 애니로 고정 서 있기,
    # 이동이 없어 방향 전환 불필요). azimuth 는 16방향 S(index 4)와 동일한 0.0(=(270+90)%360).
    DIR_LABELS = ["S"]
    DIR_AZIMUTHS = [0.0]
else:
    DIR_LABELS = DIR16_LABELS if DIRECTIONS == 16 else DIR16_LABELS[::2]
    DIR_AZIMUTHS = [(270 + 360.0 / DIRECTIONS * i) % 360 for i in range(DIRECTIONS)]
CAM_RADIUS = 12.0
# Hips(root motion 추적용 골반 본)는 리그마다 이름이 다르다 → import 후 자동 감지(detect_hips).
# 우선순위: mixamorig:Hips(Mixamo) > pelvis/Hips(Unreal Mannequin·표준) > root.
HIPS_CANDIDATES = ["mixamorig:Hips", "mixamorig:hips", "pelvis", "Pelvis",
                   "Hips", "hips", "Bip01_Pelvis", "Bip001 Pelvis", "root", "Root"]
# body_ratio/foot_anchor 측정용 본(리그 무관 자동 탐지). head ~ foot 거리 = 몸 높이(무기 제외).
HEAD_CANDIDATES = ["mixamorig:Head", "head", "Head", "Bip01_Head"]
FOOT_KEYWORDS   = ["foot", "ankle", "toe", "ball"]   # 발 본 부분 매칭(좌우 모두 수집 → 최하단 사용)

os.makedirs(OUT_FRAMES, exist_ok=True)
# 이전 실행의 낱장 PNG 를 제거(스테일 프레임 오염 방지). 프레임 수가 바뀌거나 (예: --attack
# 12 → 4) 다른 캐릭터/클립으로 재실행하면 옛 {action}_{DIR}_{idx}.png 가 남아 빌드 시 섞여
# 들어가 "공격인데 서 있는/누운 포즈" 같은 회귀를 일으키기 때문이다.
#   · 전체 렌더(ONLY_ACTIONS=None) → 모든 낱장 wipe.
#   · 부분 재렌더(ONLY_ACTIONS=[...]) → 그 행동의 낱장·_foot 마스크만 wipe(나머지 보존).
#     파일명 규약 `{action}_{DIR}_{idx}.png` 의 prefix `{action}_` 로 선별 삭제한다.
def _wipe_pngs(_dir, only=None):
    if not os.path.isdir(_dir):
        return
    prefixes = tuple(f"{a}_" for a in only) if only else None
    for _f in os.listdir(_dir):
        if not _f.endswith(".png"):
            continue
        if prefixes and not _f.startswith(prefixes):
            continue                                 # 보존 대상(재렌더 안 하는 행동)
        try:
            os.remove(os.path.join(_dir, _f))
        except OSError:
            pass

_wipe_pngs(OUT_FRAMES, ONLY_ACTIONS)
_wipe_pngs(os.path.join(OUT_FRAMES, "_foot"), ONLY_ACTIONS)   # 발 마스크도 같은 범위로 정리
bpy.ops.wm.read_factory_settings(use_empty=True)

# ── import 헬퍼: 확장자로 FBX / glTF(GLB) 자동 분기 ──────────────────
# use_custom_props=False: Mixamo FBX 의 custom prop(Short 타입)을 읽지 않아
# "WARNING: User property type 'Short' is not supported" 경고를 원천 차단(리그/애니 무관).
def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        # use_image_search=False (★ import 가속 핵심): FBX importer 가 연관 텍스처를 찾으려
        # FBX 폴더/하위 디렉토리를 *재귀 스캔* 하는 동작을 끈다. game-assets/monsters/ 처럼
        # 대용량 FBX(100MB×N)가 모인 폴더에서는 이 스캔이 import 를 수십 초~분 단위로 막는다.
        # tripo3d.ai/Mixamo FBX 는 텍스처가 *임베드(packed)* 라 외부 검색이 불필요하므로 끈다
        # — 임베드 텍스처는 이 옵션과 무관하게 그대로 추출·사용된다(품질 영향 없음).
        bpy.ops.import_scene.fbx(filepath=path, use_custom_props=False,
                                 use_image_search=False)
    elif ext in (".glb", ".gltf"):
        # glTF importer 가 +Y up → Blender +Z up 으로 자동 변환(보통 서있는 상태로 들어옴).
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".blend":
        # .blend 캐릭터 — 파일을 통째로 연다(씬 교체). 검 등이 본에 parent(또는 armature
        # modifier) 돼 있으면 애니를 본에 적용할 때 함께 따라 움직인다(별도 무기 부착 불필요).
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        raise Exception(f"지원하지 않는 모델 형식: {ext!r} ({path})")

# ── 캐릭터 import (FBX/GLB/.blend 자동 분기) ──────────────────────────
_acts_before_char = set(bpy.data.actions.keys())
import_model(CHARACTER)
# .blend 는 통째로 열려 자체 카메라/조명을 포함 — _sheet_render 가 자체 생성하므로 제거(중복/과노출 방지).
if os.path.splitext(CHARACTER)[1].lower() == ".blend":
    for _o in list(bpy.data.objects):
        if _o.type in ("LIGHT", "CAMERA"):
            bpy.data.objects.remove(_o, do_unlink=True)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if arm is None:
    raise Exception("캐릭터 모델에 Armature(리그)가 없습니다: " + CHARACTER)
if arm.animation_data is None:
    arm.animation_data_create()
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
# 머티리얼 없는 헬퍼/디버그 메시(Icosphere 등)는 캐릭터가 아니므로 제거.
# (framing bbox·렌더 오염 방지 — 캐릭터 sprite 는 항상 텍스처 머티리얼을 가진다)
_helpers = [m for m in meshes if not m.data.materials]
for _m in _helpers:
    print(f"####SKIP 머티리얼 없는 메시 제외: {_m.name!r} (verts={len(_m.data.vertices)})")
    bpy.data.objects.remove(_m, do_unlink=True)
if _helpers:
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
# 캐릭터 파일에 *내장*된 애니메이션(주로 GLB) = import 로 새로 생긴 action 들.
EMBEDDED_ACTIONS = [bpy.data.actions[k] for k in bpy.data.actions.keys()
                    if k not in _acts_before_char]
print(f"####CHAR armature={arm.name!r} meshes={[m.name for m in meshes]} "
      f"bones={len(arm.data.bones)} embedded_anims={len(EMBEDDED_ACTIONS)}")

# framing 에서 제외할 무기 메쉬 이름(--weapon 부착분 기록). .blend 의 bone-parent 무기는
# framing 단계에서 parent_type=='BONE' 으로 자동 식별되므로 여기엔 추가하지 않는다.
WEAPON_MESH_NAMES = set()

# ── 무기 장착 (선택) — 캐릭터 손 본에 무기 메쉬를 armature modifier 로 고정 ──
# --character 가 T-pose 일 때 rest 손 본(WEAPON_BONE) head 위치에 무기를 정렬하고,
# 그 본 100% weight 로 바인딩한다 → 애니로 손이 움직이면 무기가 손목을 그대로 따라간다
# (검 든 자세 자동). 무기는 메쉬만 사용(자체 armature/empty 제거). grip 위치/방향은 무기마다
# 달라 WEAPON_LOC(미터)·WEAPON_ROT(도)·WEAPON_SCALE 로 손 본 head 기준 미세조정한다.
if WEAPON:
    _before = set(o.name for o in bpy.data.objects)
    import_model(WEAPON)
    _wnew = [o for o in bpy.data.objects if o.name not in _before]
    for _o in list(_wnew):                       # 무기 자체 armature/empty 등은 제거(메쉬만 사용)
        if _o.type != "MESH":
            bpy.data.objects.remove(_o, do_unlink=True)
    _char_names = set(m.name for m in meshes)
    wmeshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in _char_names]
    if WEAPON_BONE not in arm.data.bones:
        print(f"####WARN 무기 부착 본 미발견: {WEAPON_BONE!r} → 무기 장착 생략")
    elif not wmeshes:
        print(f"####WARN 무기 메쉬 없음 → 장착 생략: {WEAPON}")
    else:
        hand = arm.matrix_world @ arm.data.bones[WEAPON_BONE].head_local   # rest 손 본 head(월드)
        # 캐릭터 키(head~foot 본) 비례 자동 스케일 — 작은 캐릭터엔 작게, 큰 mob 엔 크게.
        # ref_height(프로파일을 만든 기준 캐릭터 키) 대비 현재 캐릭터 키 비율을 무기에 곱한다.
        auto_scale = 1.0
        if WEAPON_REF_H > 1e-6:
            _names = set(arm.pose.bones.keys())
            _hb = next((c for c in HEAD_CANDIDATES if c in _names), None) \
                or next((pb.name for pb in arm.pose.bones if "head" in pb.name.lower()), None)
            _fbs = [pb for pb in arm.pose.bones if any(k in pb.name.lower() for k in FOOT_KEYWORDS)
                    and "ik" not in pb.name.lower() and "ctrl" not in pb.name.lower()]
            if _hb and _fbs:
                _chz = (arm.matrix_world @ arm.pose.bones[_hb].head).z
                _cfz = min((arm.matrix_world @ pb.head).z for pb in _fbs)
                char_h = abs(_chz - _cfz)
                auto_scale = char_h / WEAPON_REF_H
                print(f"####WEAPON 크기 자동보정: 캐릭터 키={char_h:.3f} / ref={WEAPON_REF_H:.3f} "
                      f"→ auto_scale={auto_scale:.3f}")
        total_scale = WEAPON_SCALE * auto_scale
        extra = (Matrix.Translation(Vector(WEAPON_LOC) * auto_scale)
                 @ Euler([math.radians(a) for a in WEAPON_ROT], "XYZ").to_matrix().to_4x4()
                 @ Matrix.Scale(total_scale, 4))
        for wm in wmeshes:
            m = wm.matrix_world.copy()
            m.translation = hand                  # 무기 origin → 손 본 head 로 이동
            m = Matrix.Translation(hand) @ extra @ Matrix.Translation(-hand) @ m  # 손 피벗 미세조정
            wm.parent = arm                       # arm object 변환(세우기 보정 등) 추종
            wm.matrix_parent_inverse = arm.matrix_world.inverted()
            wm.matrix_world = m
            vg = wm.vertex_groups.new(name=WEAPON_BONE)
            vg.add(list(range(len(wm.data.vertices))), 1.0, "REPLACE")
            mod = wm.modifiers.new("WeaponRig", "ARMATURE")
            mod.object = arm                      # WEAPON_BONE 본 pose 변형 추종(손목 따라감)
            WEAPON_MESH_NAMES.add(wm.name)        # framing 제외용(무기 휘두름이 셀을 키우지 않게)
            print(f"####WEAPON '{wm.name}' → {WEAPON_BONE} 부착 "
                  f"(verts={len(wm.data.vertices)} loc={WEAPON_LOC} rot={WEAPON_ROT} scale={WEAPON_SCALE})")
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]   # 렌더 대상에 무기 포함
        bpy.context.view_layer.update()

# ── Hips(root motion 추적 골반 본) 자동 감지 ─────────────────────────
def detect_hips(arm):
    names = set(arm.pose.bones.keys())
    for c in HIPS_CANDIDATES:
        if c in names:
            return c
    for pb in arm.pose.bones:                         # 후보 실패 → pelvis/hips 부분 매칭
        low = pb.name.lower()
        if "pelvis" in low or "hips" in low:
            return pb.name
    return None

HIPS = detect_hips(arm)
print(f"####HIPS bone={HIPS!r} (root motion 추적)" if HIPS
      else "####WARN Hips 본 미검출 → root motion 추적 생략(타깃 고정)")

# ── 리그 자동 감지 + retarget (Mixamo ↔ Tripo3D 등 본 이름이 다른 리그 호환) ──
# 표준 humanoid 역할 → 리그별 본 이름. 새 리그(UE 등)는 여기 한 줄 추가하면 retarget 지원.
RIG_BONES = {
    "mixamorig": {
        "hips": "mixamorig:Hips", "spine": "mixamorig:Spine", "spine1": "mixamorig:Spine1",
        "spine2": "mixamorig:Spine2", "neck": "mixamorig:Neck", "head": "mixamorig:Head",
        "l_shoulder": "mixamorig:LeftShoulder", "l_arm": "mixamorig:LeftArm",
        "l_forearm": "mixamorig:LeftForeArm", "l_hand": "mixamorig:LeftHand",
        "r_shoulder": "mixamorig:RightShoulder", "r_arm": "mixamorig:RightArm",
        "r_forearm": "mixamorig:RightForeArm", "r_hand": "mixamorig:RightHand",
        "l_upleg": "mixamorig:LeftUpLeg", "l_leg": "mixamorig:LeftLeg",
        "l_foot": "mixamorig:LeftFoot", "l_toe": "mixamorig:LeftToeBase",
        "r_upleg": "mixamorig:RightUpLeg", "r_leg": "mixamorig:RightLeg",
        "r_foot": "mixamorig:RightFoot", "r_toe": "mixamorig:RightToeBase",
    },
    "tripo": {   # Tripo3D.ai auto-rig (L_/R_ prefix, Waist/Spine01/Upperarm/Thigh/Calf)
        "hips": "Hip", "spine": "Waist", "spine1": "Spine01", "spine2": "Spine02",
        "neck": "NeckTwist01", "head": "Head",
        "l_shoulder": "L_Clavicle", "l_arm": "L_Upperarm", "l_forearm": "L_Forearm", "l_hand": "L_Hand",
        "r_shoulder": "R_Clavicle", "r_arm": "R_Upperarm", "r_forearm": "R_Forearm", "r_hand": "R_Hand",
        "l_upleg": "L_Thigh", "l_leg": "L_Calf", "l_foot": "L_Foot", "l_toe": "L_ToeBase",
        "r_upleg": "R_Thigh", "r_leg": "R_Calf", "r_foot": "R_Foot", "r_toe": "R_ToeBase",
    },
    "ue": {   # Unreal Engine Mannequin (pelvis/spine_NN/clavicle_l/upperarm_l/lowerarm_l/thigh_l/calf_l)
        "hips": "pelvis", "spine": "spine_01", "spine1": "spine_03", "spine2": "spine_05",
        "neck": "neck_01", "head": "head",
        "l_shoulder": "clavicle_l", "l_arm": "upperarm_l", "l_forearm": "lowerarm_l", "l_hand": "hand_l",
        "r_shoulder": "clavicle_r", "r_arm": "upperarm_r", "r_forearm": "lowerarm_r", "r_hand": "hand_r",
        "l_upleg": "thigh_l", "l_leg": "calf_l", "l_foot": "foot_l", "l_toe": "ball_l",
        "r_upleg": "thigh_r", "r_leg": "calf_r", "r_foot": "foot_r", "r_toe": "ball_r",
    },
}

def detect_rig(bone_names):
    names = set(bone_names)
    best, score = None, 0
    for rig, roles in RIG_BONES.items():
        s = sum(1 for bn in roles.values() if bn in names)
        if s > score:
            best, score = rig, s
    return best if score >= 8 else None     # 최소 8역할 매칭해야 그 리그로 인정

def build_mapping(src_rig, tgt_rig):
    s, t = RIG_BONES[src_rig], RIG_BONES[tgt_rig]
    return {s[r]: t[r] for r in s if r in t}    # {src_bone: tgt_bone}

def _rotm(M):
    return M.to_quaternion().to_matrix()        # 순수 회전 3x3(scale 제거)

def _tgt_bone_order(tgt):
    """캐릭터 본을 root-first 로 나열(부모가 자식보다 먼저)."""
    order = []
    def _rec(b):
        order.append(b.name)
        for c in b.children:
            _rec(c)
    for b in tgt.data.bones:
        if not b.parent:
            _rec(b)
    return order

def _tgt_rel_rest(tgt, order):
    """각 본의 부모-상대 rest 회전(3x3). armature_apply 후 다시 호출해 갱신."""
    rel = {}
    for bn in order:
        bone = tgt.data.bones[bn]
        M = (bone.parent.matrix_local.inverted() @ bone.matrix_local) if bone.parent else bone.matrix_local
        rel[bn] = _rotm(M)
    return rel

def retarget_action(src_arm, src_action, mapping, out_name):
    """src(애니) 본의 *rest 대비 로컬 회전* 을 tgt(캐릭터) 본의 rest 에 적용(상대 회전):
        target = tgt_rest @ src_rest⁻¹ @ src_pose
    tgt 의 rest 를 *변경하지 않으므로*, 본 이름이 같아 retarget 없이 직접 적용되는
    Tripo3d 자체 애니(idle/walk 등)와 한 sheet 안에 섞여도 서로 깨지지 않는다.
    (과거 rest 정렬 방식은 armature_apply 로 tgt rest 를 바꿔, 같은 실행의 직접 적용
    애니를 깨뜨렸다.) rest pose(A↔T) 차이는 상대 회전이라 자동 흡수되고 팔 꺾임도 없다.
    다만 *검 든 모델 + mixamo 빈손 애니* 는 손목 자세가 빈손 기준이라 검이 다소 앞으로
    올 수 있다 — 가장 자연스러운 건 Tripo3d 자체 애니를 직접 적용하는 것이다
    (scripts/bake_tripo_anim.py 로 추출)."""
    tgt = arm
    tgt_rest = {mapping[s]: _rotm(tgt.matrix_world @ tgt.data.bones[mapping[s]].matrix_local)
                for s in mapping if s in src_arm.data.bones and mapping[s] in tgt.data.bones}
    src_rest = {s: _rotm(src_arm.matrix_world @ src_arm.data.bones[s].matrix_local)
                for s in mapping if s in src_arm.data.bones and mapping[s] in tgt_rest}
    inv = {mapping[s]: s for s in src_rest}      # {tgt_bone: src_bone}
    arm_t_inv = _rotm(tgt.matrix_world).inverted()
    f0, f1 = int(src_action.frame_range[0]), int(src_action.frame_range[1])
    src_arm.animation_data.action = src_action
    scn = bpy.context.scene
    src_pose = {}
    for f in range(f0, f1 + 1):
        scn.frame_set(f)
        src_pose[f] = {s: _rotm(src_arm.matrix_world @ src_arm.pose.bones[s].matrix) for s in src_rest}
    order = _tgt_bone_order(tgt)
    rel = _tgt_rel_rest(tgt, order)
    act = bpy.data.actions.new(out_name)
    if not tgt.animation_data:
        tgt.animation_data_create()
    tgt.animation_data.action = act
    for pb in tgt.pose.bones:
        pb.rotation_mode = "QUATERNION"
    for f in range(f0, f1 + 1):
        objr = {}
        for bn in order:
            bone = tgt.data.bones[bn]
            par = objr[bone.parent.name] if bone.parent else Matrix.Identity(3)
            if bn in inv:
                s = inv[bn]
                # src 가 자기 rest 에서 회전한 양(로컬)을 tgt rest 에 적용 → rest 변경 없음.
                local = src_rest[s].inverted() @ src_pose[f][s]
                target_obj = arm_t_inv @ (tgt_rest[bn] @ local)
                basis = (par @ rel[bn]).inverted() @ target_obj
            else:
                basis = Matrix.Identity(3)
            pb = tgt.pose.bones[bn]
            pb.rotation_quaternion = basis.to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=f)
            objr[bn] = par @ rel[bn] @ basis
    act.use_fake_user = True
    return act

def _reset_pose(a):
    if a.animation_data:
        a.animation_data.action = None
    for pb in a.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)

# ── 애니메이션 import: 본 이름이 캐릭터와 같으면 그대로, 다르면(Mixamo 애니 ↔
#    Tripo3D 캐릭터 등) 리그 감지 후 retarget 해 적용. 임시 오브젝트는 삭제 ──
def import_action(path, name):
    before_a = set(bpy.data.actions.keys())
    before_o = set(o.name for o in bpy.data.objects)
    import_model(path)
    new_a = [bpy.data.actions[k] for k in bpy.data.actions.keys() if k not in before_a]
    new_o = [o for o in bpy.data.objects if o.name not in before_o]
    src_act = new_a[0] if new_a else None
    src_arm = next((o for o in new_o if o.type == "ARMATURE"), None)
    # 🛑 Mixamo 중복 export 접두사(mixamorig1:/mixamorig2: 등)를 mixamorig: 로 정규화한다(2026-07-10).
    # 애니 fbx 본 이름이 mixamorig1:Hips 인데 캐릭터는 mixamorig:Hips 라 교집합 0 → 정적·뒤집힘 렌더
    # 되던 회귀(ryen 실측). 본 이름 변경 시 그 armature 의 action fcurve data_path 도 Blender 가 자동
    # 갱신하므로, 정규화 후엔 캐릭터 rig 와 본이 일치해 '직접적용' 경로를 탄다.
    if src_arm:
        _n = 0
        for _b in src_arm.data.bones:
            _nn = re.sub(r"^mixamorig\d+:", "mixamorig:", _b.name)
            if _nn != _b.name:
                _b.name = _nn
                _n += 1
        if _n:
            print(f"####INFO 애니 본 접두사 정규화 mixamorig<N>: → mixamorig: ({_n}본)")
    result = None
    if src_act and src_arm:
        char_bones = set(b.name for b in arm.data.bones)
        anim_bones = set(b.name for b in src_arm.data.bones)
        common = char_bones & anim_bones
        if len(common) >= max(8, int(len(anim_bones) * 0.5)):
            src_act.name = name + "__act"; src_act.use_fake_user = True   # 같은 리그 → 그대로
            result = src_act
            print(f"####ANIM {name} 직접적용(본 {len(common)}개 일치)")
        else:
            src_rig, tgt_rig = detect_rig(anim_bones), detect_rig(char_bones)
            if src_rig and tgt_rig and src_rig != tgt_rig:
                mp = build_mapping(src_rig, tgt_rig)
                result = retarget_action(src_arm, src_act, mp, name + "__act")
                print(f"####ANIM {name} retarget {src_rig}→{tgt_rig} ({len(mp)}본 매핑)")
            else:
                print(f"####WARN {name} 본 불일치+리그 미감지 → 정적 "
                      f"(애니리그={src_rig}, 캐릭터리그={tgt_rig})")
    elif src_act:
        src_act.name = name + "__act"; src_act.use_fake_user = True
        result = src_act
    for o in new_o:
        bpy.data.objects.remove(o, do_unlink=True)
    _reset_pose(arm)            # retarget 으로 변형된 캐릭터 pose 를 rest 로 복구
    return result

# 내장 애니메이션 이름 → 행동(ACTIONS) 매칭용 별칭(부분 문자열, 소문자 비교).
# tripo3d.ai 가 FBX 에 baked 하는 클립 이름 규칙을 1순위로 포함한다:
#   · idle / run / walk → 행동명과 동일
#   · attack → "slash" 등 무기별 이름으로 표시될 수 있음
#   · hit    → "hit_x_x" (예: hit_a_b / hit_1_2) → "hit" 부분 매칭
#   · death  → "defeat_<n>" (예: defeat_1) → "defeat" 부분 매칭
ACTION_ALIASES = {
    "idle":   ["idle", "breath", "stand", "rest", "tpose", "t-pose"],
    "walk":   ["walk"],
    "run":    ["run", "sprint", "jog"],
    "attack": ["attack", "slash", "swing", "cast", "spell", "strike",
               "punch", "shoot", "stab", "chop", "thrust", "combo", "smash"],
    "hit":    ["hit", "hurt", "damage", "flinch", "stagger", "impact", "pain", "react"],
    "death":  ["death", "die", "dead", "defeat", "ko", "fall", "collapse"],
}

def match_embedded(actions_wanted, embedded):
    """캐릭터 파일 내장 action 들을 행동 이름에 매칭 → {action_name: Action}."""
    result, used = {}, set()
    for want in actions_wanted:
        keys = ACTION_ALIASES.get(want, [want])
        exact = next((a for a in embedded                       # 1) 정확히 같은 이름 우선
                      if a not in used and a.name.lower() == want), None)
        pick = exact or next((a for a in embedded               # 2) 별칭 부분 문자열 매칭
                              if a not in used and any(k in a.name.lower() for k in keys)), None)
        if pick:
            result[want] = pick
            used.add(pick)
    # 🛑 fallback(npc, 2026-07-10): idle 을 원하는데 별칭으로 못 찾았고 내장 애니가 정확히 1개면 그걸
    # idle 로 쓴다. Mixamo export 는 애니 이름이 "mixamo.com"(별칭 밖)이라 매칭 실패 → npc idle 정적·
    # 뒤집힘 회귀 방지(ryen 실측). 내장이 여럿(pc/mob)이면 적용 안 함(오매칭 방지).
    if "idle" in actions_wanted and "idle" not in result and len(embedded) == 1:
        result["idle"] = embedded[0]
    return result

actions = {}
if USE_EMBEDDED:
    # 캐릭터 파일 내장 애니메이션을 행동에 매칭(주로 GLB; sorceress Text-to-Animation 등)
    avail = ", ".join(a.name for a in EMBEDDED_ACTIONS) or "(없음)"
    print(f"####EMBED 내장 애니 후보: {avail}")
    matched = match_embedded(ACTIONS, EMBEDDED_ACTIONS)
    for name in ACTIONS:
        a = matched.get(name)
        if a:
            a.use_fake_user = True
            actions[name] = a
            print(f"####ANIM {name} ← '{a.name}' frames=({a.frame_range[0]:.0f},{a.frame_range[1]:.0f})")
        else:
            print(f"####WARN 내장 애니 매칭 실패(정적 폴백): {name}")
    if not actions:
        print("####WARN 내장 애니메이션이 없거나 하나도 매칭되지 않음 → 정적(T-pose) 16방향 렌더. "
              "애니메이션이 필요하면 Animate 단계를 거친 GLB 를 쓰거나 --animations 폴더를 지정하세요.")
else:
    # 외부 폴더에서 {action}.fbx/.glb/.gltf import 해서 적용(개발자 직접)
    EXTS = (".fbx", ".glb", ".gltf")
    for name in ACTIONS:
        p = next((os.path.join(ANIM_DIR, name + e) for e in EXTS
                  if os.path.exists(os.path.join(ANIM_DIR, name + e))), None)
        if p:
            a = import_action(p, name)
            if a:
                actions[name] = a
                print(f"####ANIM {name} frames=({a.frame_range[0]:.0f},{a.frame_range[1]:.0f})")
            else:
                print(f"####WARN action 없음(빈 파일): {p}")
        else:
            print(f"####WARN 애니 파일 없음: {ANIM_DIR}/{name}.(fbx|glb|gltf)")

def bind(name):
    a = actions.get(name)
    if not a:
        return None
    ad = arm.animation_data
    ad.action = a
    if hasattr(ad, "action_suitable_slots"):
        s = ad.action_suitable_slots
        if s and getattr(ad, "action_slot", None) is None:
            ad.action_slot = s[0]
    return a

# ── 누움 자동 감지 → 세우기 ──────────────────────────────────────────
def bbox(objs):
    xs, ys, zs = [], [], []
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))

first = next((n for n in ACTIONS if n in actions), None)
if first:
    bind(first)
    bpy.context.scene.frame_set(int(actions[first].frame_range[0]))
    bpy.context.view_layer.update()

# ── 세우기 보정 — 발→머리 본 벡터를 +Z 로 정렬해 *항상* 똑바로 세운다 ──
# mesh bbox 만으론 "누움"은 알아도 "어느 방향으로 세울지"(앞/뒤로 누움·거꾸로)를 모른다 →
# 무조건 X+90° 로 세우면 머리가 -Y 로 누운 캐릭터는 거꾸로 선다. head 본·foot 본의 *실제
# 위치* 로 회전 축·각을 정하면, tripo3d(rest Z-up)처럼 비표준 캐릭터에 표준 mixamo 애니
# (rest Y-up)를 직접 적용해 누워/거꾸로가 돼도 항상 머리가 위(+Z)로 선다(모든 캐릭터 일반).
def _upright_by_bones():
    names = set(arm.pose.bones.keys())
    hb = next((c for c in HEAD_CANDIDATES if c in names), None) \
        or next((pb.name for pb in arm.pose.bones if "head" in pb.name.lower()), None)
    fbs = [pb for pb in arm.pose.bones if any(k in pb.name.lower() for k in FOOT_KEYWORDS)
           and "ik" not in pb.name.lower() and "ctrl" not in pb.name.lower()]
    if not hb or not fbs:
        return False
    head = arm.matrix_world @ arm.pose.bones[hb].head
    feet = [arm.matrix_world @ pb.head for pb in fbs]
    foot = sum(feet, Vector((0, 0, 0))) / len(feet)
    v = head - foot                       # 발→머리(이 벡터가 +Z 를 향해야 똑바로 섬)
    if v.length < 1e-6:
        return False
    v = v.normalized()
    up = Vector((0, 0, 1))
    if v.dot(up) > 0.985:                  # 이미 똑바로(약 ±10° 이내) → 보정 불필요
        print("####INFO 캐릭터 서있음(보정 불필요)")
        return True
    axis = v.cross(up)
    if axis.length < 1e-6:                 # 정확히 거꾸로(v ≈ -Z) → X축 180°
        axis, angle = Vector((1, 0, 0)), math.pi
    else:
        axis, angle = axis.normalized(), v.angle(up)
    arm.matrix_world = Matrix.Rotation(angle, 4, axis) @ arm.matrix_world
    bpy.context.view_layer.update()
    print(f"####INFO 본 기반 세우기: 발→머리 벡터를 +Z 로 {math.degrees(angle):.0f}° 정렬")
    return True

if not _upright_by_bones():
    # head/foot 본 미검출 → mesh bbox 폴백(누움이면 키축 추정으로 X/Y 90° 회전)
    (bx0, bx1), (by0, by1), (bz0, bz1) = bbox(meshes)
    hx, hy, hz = bx1 - bx0, by1 - by0, bz1 - bz0
    if hz < max(hx, hy) * 0.7:
        if hy >= hx:
            arm.rotation_euler.x += math.radians(90)
        else:
            arm.rotation_euler.y += math.radians(90)
        bpy.context.view_layer.update()
        print("####INFO 누움 감지(mesh bbox 폴백) → 세우기 보정")
    else:
        print("####INFO 캐릭터 서있음(보정 불필요)")

# ── framing — 캐릭터(무기 제외) 기준: 캐릭터를 *항상 원래 크기*로 렌더한다 ──────
# 무기(검 등: .blend 의 bone-parent / --weapon 부착 / 손 본 vertex-group 스키닝 메쉬)는
# framing 에서 *제외* 한다.
# → attack 에서 칼을 크게 휘둘러도 그 때문에 셀이 커지지(=idle 포함 캐릭터가 작아지지) 않는다.
# 칼이 셀을 넘는 *그 프레임의 칼끝만* 잘린다(전체 캐릭터는 정상 크기 — 사용자 요청:
# "framing 확대는 칼 휘두름 그 한 경우만, 전체 캐릭터를 작게 하면 안 된다").
elev = math.radians(ELEV_DEG)

def _is_hand_skinned_weapon(o):
    """손 본(RightHand/LeftHand 계열)에만 스키닝된 메쉬 = grip-align 부착 무기.
    blend-weapon-attach 스킬이 무기를 손 본 vertex group 100% weight + Armature modifier 로
    붙이므로(bone-parent 가 아니라 export 보존을 위해 스키닝), parent_type=='BONE' 으로는
    잡히지 않는다. 캐릭터 몸 메쉬는 Spine/Leg 등 여러 본에 weight 되므로 vertex group 이 전부
    'Hand' 일 수 없다 → vertex group 이 모두 손 본이면 무기로 간주해 framing 에서 제외한다."""
    if o.type != "MESH" or not o.vertex_groups:
        return False
    return all("Hand" in g.name for g in o.vertex_groups)

_wnames = set(o.name for o in meshes
              if o.parent_type == "BONE" or _is_hand_skinned_weapon(o)) | WEAPON_MESH_NAMES
body = [o for o in meshes if o.name not in _wnames] or meshes
(cx0, cx1), (cy0, cy1), (cz0, cz1) = bbox(body)
target = Vector(((cx0 + cx1) / 2, (cy0 + cy1) / 2, (cz0 + cz1) / 2))
char_h = cz1 - cz0
char_w = max(cx1 - cx0, cy1 - cy0)
# MARGIN 으로 여백을 두고, SCALE 로 나눠 모델 전체를 키움(>1)/줄임(<1). SCALE=1 이면 무변화.
# base ortho (= 무기 제외 몸 bbox × margin). 행동별 scale 은 _ascale 로 렌더 시 나눈다.
ortho = max(char_h, char_w) * MARGIN
def _ascale(name):
    # 그 행동의 최종 scale. sheet.py 가 전역 --scale 까지 채워 보내지만, 직접 cfg 호출 등으로
    # ACTION_SCALES 가 비어 있으면 전역 SCALE 을 기본값으로 쓴다(이중 적용 없음). 0 가드.
    return float(ACTION_SCALES.get(name, SCALE)) or 1.0
print(f"####FRAMING mode=body-only(무기 {len(_wnames)}개 제외) margin x{MARGIN} "
      f"scale(전역)x{SCALE} ortho_base={ortho:.3f} body_h={char_h:.2f} body_w={char_w:.2f}")

# Hips 추적 타겟 (root motion 상쇄 = in-place cycle)
_hips0 = (arm.matrix_world @ arm.pose.bones[HIPS].head) if arm.pose.bones.get(HIPS) else target
_ofs = target - _hips0
def cur_target():
    pb = arm.pose.bones.get(HIPS)
    return (arm.matrix_world @ pb.head) + _ofs if pb else target

# ── 카메라 ────────────────────────────────────────────────────────────
cam = bpy.data.objects.new("SpriteCam", bpy.data.cameras.new("SpriteCam"))
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = ortho / _ascale("idle")  # measure 는 idle 기준
cam.data.clip_start = 0.01; cam.data.clip_end = 1000.0

def place_camera(az_deg, tgt):
    az = math.radians(az_deg)
    cam.location = tgt + Vector((CAM_RADIUS * math.cos(elev) * math.sin(az),
                                 -CAM_RADIUS * math.cos(elev) * math.cos(az),
                                 CAM_RADIUS * math.sin(elev)))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()

# ── 조명 3점 (카메라 자식 → 공전해도 셰이딩 일관) ────────────────────
def add_sun(name, energy, rot):
    d = bpy.data.lights.new(name, "SUN"); d.energy = energy
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.parent = cam
    o.rotation_euler = tuple(math.radians(a) for a in rot)
add_sun("Key", 4.0, (-35, 25, 0))
add_sun("Fill", 1.3, (-10, -40, 0))
add_sun("Rim", 2.5, (210, 0, 0))
world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[1].default_value = 0.25

# ── 발광(emissive) 머티리얼 보정 — 라이트세이버 칼날 등 ───────────────────
# WORKBENCH(TEXTURE) 는 emission shader 를 *전혀* 렌더하지 않고 base color 만 보여준다.
# 라이트세이버 칼날 머티리얼은 base=어두운 색(파랑) + Emission Strength>0(빛남) 으로 저작돼
# 있어, WORKBENCH 에서는 빛나지 않는 *납작한 파란 막대* 로 나온다(실측 회귀).
# → emissive 머티리얼(Emission Strength>0)을 자동 탐지해 base color 를 "빛나는 코어"로
#   끌어올린다. 칼날 고유 색조(파랑)를 유지하되, WORKBENCH 음영에 먹히지 않게 밝게 부스트해
#   *빛나는 파란 칼날* 로 보이게 한다(원래의 납작한 어두운 파랑 → 발광 파랑).
# EEVEE 는 emission 을 정상 렌더하므로 건드리지 않는다.
def _principled(mat):
    if not mat.use_nodes:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)

def _emission_strength(bsdf):
    inp = bsdf.inputs.get("Emission Strength")
    if inp is None or inp.is_linked:
        return 0.0
    try:
        return float(inp.default_value)
    except Exception:
        return 0.0

if SHADING == "texture":
    _glow_fixed = []
    for _mat in bpy.data.materials:
        _bsdf = _principled(_mat)
        if _bsdf is None:
            continue
        _strength = _emission_strength(_bsdf)
        if _strength <= 1e-4:
            continue
        # 칼날 색조(base color 우선 — 칼날 고유색. 없으면 emission 색)를 가져온다.
        _bcv = _bsdf.inputs.get("Base Color")
        if _bcv is not None and not _bcv.is_linked:
            _tint = list(_bcv.default_value)[:3]
        else:
            _ec = _bsdf.inputs.get("Emission Color")
            _tint = list(_ec.default_value)[:3] if _ec is not None else [1.0, 1.0, 1.0]
        # 빛나는 코어: 색조를 최대 채도로 정규화(가장 밝은 채널=1.0)한 뒤 어두운 채널을 살짝
        # 들어올려(+0.25) 발광체처럼 밝게. 파랑(1.0 채널)은 유지되고 전체가 환하게 빛나는 파란
        # 칼날이 된다. (흰색으로 빼지 않으므로 칼날 고유색 유지)
        _mx = max(_tint) or 1.0
        _core = [min(1.0, c / _mx + 0.25) for c in _tint]
        # ★ WORKBENCH TEXTURE 는 *이미지 텍스처가 없는* 머티리얼은 base color node 가 아니라
        #   mat.diffuse_color(뷰포트/워크벤치 표시색)를 렌더한다 → 반드시 둘 다 흰 코어로 세팅.
        _bc = _bsdf.inputs.get("Base Color")
        if _bc is not None and not _bc.is_linked:
            _bc.default_value = (_core[0], _core[1], _core[2], 1.0)
        _mat.diffuse_color = (_core[0], _core[1], _core[2], 1.0)
        _glow_fixed.append((_mat.name, round(_strength, 2)))
    if _glow_fixed:
        print(f"####GLOW WORKBENCH emissive→발광 코어 보정: {_glow_fixed}")

# ── 렌더 설정 (SHADING 모드 분기) ─────────────────────────────────────
scene = bpy.context.scene
if SHADING == "texture":
    # WORKBENCH + TEXTURE: 텍스처 색을 밝고 일관되게(조명 의존 적게) 표시.
    # EEVEE 가 metallic/PBR(갑옷·로봇)에서 raytracing 미사용 시 금속을 검게 렌더하는
    # 문제를 회피 → 원본 모델 색 그대로. (Tripo3D 등 PBR 캐릭터 sprite 에 권장)
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"; sh.color_type = "TEXTURE"
    sh.show_shadows = False
    sh.show_cavity = not DRAFT; sh.cavity_type = "WORLD"  # 패널 경계 음영(평면 방지). draft 는 끔.
    # AA: 일반은 "8"(512→256→128 다운샘플이 추가 AA 제공하므로 16 불필요). draft 는 끔(최고속).
    scene.display.render_aa = "OFF" if DRAFT else "8"
else:
    # 기존 EEVEE: 3점 SUN + 환경광 PBR 렌더(위 add_sun/world 설정 사용).
    try:
        scene.eevee.taa_render_samples = 4 if DRAFT else 16   # 64→16(렌더↓, 품질 유지), draft=4
    except Exception:
        pass
    # 🛑 그림자 전면 비활성 (Blender 4.2+/5.x EEVEE-Next 크래시 회피).
    # EEVEE-Next 는 shadow atlas 에 *프레임당 갱신 한도* 가 있어, 3 SUN × 수백~수천 프레임을
    # 한 세션에서 연속 렌더하면 "Reached max shadow updates" → EXCEPTION_ACCESS_VIOLATION 으로
    # GPU 백엔드가 죽는다(실측: Blender 5.1.2, sprite sheet 1024 프레임). 평면(isometric)
    # 플랫 라이팅 sprite 에는 그림자가 불필요하고 방향마다 자기그림자가 달라 오히려 해로우므로,
    # 전역 EEVEE 그림자 + 각 SUN 의 use_shadow 를 모두 끈다(WORKBENCH texture 경로와 동일 의도).
    try:
        scene.eevee.use_shadows = False                       # 전역 EEVEE 그림자 OFF
    except Exception:
        pass
    for _lt in bpy.data.lights:
        try:
            _lt.use_shadow = False                            # 각 SUN 그림자 OFF (atlas 미사용)
        except Exception:
            pass
r = scene.render
r.resolution_x = RENDER_RES; r.resolution_y = RENDER_RES; r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"   # AgX 회피

# ── 색상 진하기(대비)+밝기 부스트 — view_settings exposure+gamma (COLOR_LEVEL 1~9) ──
# 렌더 엔진(WORKBENCH/EEVEE) 무관하게 렌더 파이프라인의 *표준 최종 색 변환 단계* 에서
# 이미지를 밝고 진하게 만든다(compositor 불필요 → Blender 4/5 버전 차이·node group 규약
# 리스크 없음). exposure↑ = 전체 밝기↑(2^stop), gamma<1 = 어두운 톤을 눌러 대비/색 진하기↑.
# gamma<1 로 살짝 어두워지는 만큼 exposure 로 보상해 baseline 보다 항상 밝게 유지한다.
#   level 5(기본) → exposure +0.45 · gamma 0.875 (적당히 밝고 진하게)
#   level 9       → exposure +0.90 · gamma 0.75  (최대)
#   level 1       → 무보정(exposure 0 · gamma 1.0)
# ※ 실측 검증(Blender 5.1.2, Standard view transform): exposure 0.3→0.9 로 평균 밝기
#    0.69→0.86 상승, gamma 0.95→0.75 로 대비(std) 0.17→0.22 상승 확인.
def _setup_color_boost(level):
    level = max(1, min(9, int(level)))
    t = (level - 1) / 8.0            # 0.0(lv1) ~ 1.0(lv9), lv5=0.5
    vs = scene.view_settings
    if t <= 1e-6:
        print(f"####COLOR level={level} → 무보정(exposure 0 · gamma 1.0)")
        return
    vs.exposure = t * 0.9            # 밝기: +0 ~ +0.9 stop (lv5=+0.45)
    vs.gamma = 1.0 - t * 0.25        # 대비/진하기: 1.0 ~ 0.75 (lv5=0.875, <1=대비↑)
    print(f"####COLOR level={level} exposure={vs.exposure:.3f} gamma={vs.gamma:.3f}")

_setup_color_boost(COLOR_LEVEL)

def sample_frames(a, n, is_loop):
    s = int(a.frame_range[0]); e = int(a.frame_range[1])
    # 🛑 n<=1(행동당 1프레임) 은 non-loop 의 (n-1) 나눗셈에서 ZeroDivisionError 를 낸다 →
    # 프레임 하나면 시작 프레임만 반환(정지 애니 e<=s 와 동일 처리). --idle 1 등 단일 프레임 지원.
    if e <= s or n <= 1:
        return [s] * max(1, n)
    if is_loop:                                       # loop: end 미포함(첫=끝 중복 방지)
        return [s + round((e - s) * i / n) for i in range(n)]
    return [s + round((e - s) * i / (n - 1)) for i in range(n)]

# ── body_ratio / foot_anchor 측정 (head~foot 본, 무기 무관) → measure json ──
def _detect_head():
    names = set(arm.pose.bones.keys())
    for c in HEAD_CANDIDATES:
        if c in names:
            return c
    return next((pb.name for pb in arm.pose.bones if "head" in pb.name.lower()), None)

def _foot_bones():
    # IK/컨트롤 본(ik_foot_root 등)은 실제 발 위치와 달라 제외 → deform 발 본만 사용
    return [pb for pb in arm.pose.bones
            if any(k in pb.name.lower() for k in FOOT_KEYWORDS)
            and "ik" not in pb.name.lower() and "ctrl" not in pb.name.lower()]

def measure_body_foot():
    # rest/첫 프레임, S방향(정면) 카메라에서 head·foot 본을 화면(0~1)으로 투영.
    if first:
        bind(first)
        bpy.context.scene.frame_set(int(actions[first].frame_range[0]))
    else:
        arm.animation_data.action = None
    bpy.context.view_layer.update()
    s_idx = DIR_LABELS.index("S") if "S" in DIR_LABELS else 0
    place_camera(DIR_AZIMUTHS[s_idx], cur_target())
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    head = _detect_head()
    feet = _foot_bones()
    res = {"head_bone": head, "foot_bones": [pb.name for pb in feet],
           "body_ratio": None, "foot_anchor": None}
    if head and feet:
        head_w = arm.matrix_world @ arm.pose.bones[head].head
        foot_ws = [arm.matrix_world @ pb.head for pb in feet]
        head_y = world_to_camera_view(scene, cam, head_w).y          # 0(아래)~1(위)
        foot_y = min(world_to_camera_view(scene, cam, w).y for w in foot_ws)
        body_ratio = abs(head_y - foot_y)                            # 화면 세로 비율(몸 높이/셀)
        foot_anchor = round(1.0 - foot_y, 4)                         # 이미지 좌표(위=0) 발 y = 도착지
        res["body_ratio"] = round(body_ratio, 4)
        res["foot_anchor"] = foot_anchor
        print(f"####MEASURE body_ratio={body_ratio:.4f} foot_anchor={foot_anchor:.4f} "
              f"head={head!r} feet={len(feet)}")
    else:
        print(f"####WARN body/foot 본 미검출 → 측정 생략 (head={head!r} feet={len(feet)})")
    if MEASURE_PATH:
        os.makedirs(os.path.dirname(MEASURE_PATH) or ".", exist_ok=True)
        json.dump(res, open(MEASURE_PATH, "w", encoding="utf-8"))
    return res

measure_body_foot()

# ── 렌더 루프 ─────────────────────────────────────────────────────────
# 무기(검 등) 메시 — 발 측정 렌더에서 숨긴다(발바닥만 남기려고). body(무기 제외)의 여집합.
_weapon_objs = [o for o in meshes if o.name not in set(m.name for m in body)]
# 발 측정용 마스크(검 제외 캐릭터 실루엣) 저장 폴더. align_feet 가 이 폴더의 bbox 하단(=발바닥)을
# 읽어 세로 정렬한다. Render Result.pixels 는 headless 에서 비어 신뢰 불가 → 파일로 저장해 PIL 이 읽음.
FOOT_MASK_DIR = os.path.join(OUT_FRAMES, "_foot")
# 🛑 스테일 _foot 마스크 정리는 파일 상단 _wipe_pngs(ONLY_ACTIONS) 가 이미 *범위에 맞게*
# 수행한다(전체 렌더=전부 wipe · 부분 재렌더=그 행동만 wipe). 여기서 무조건 전부 지우면 부분
# 재렌더 시 보존해야 할 다른 행동의 마스크까지 삭제돼 align_feet 발 정렬이 틀어진다 → 폴더 생성만.
os.makedirs(FOOT_MASK_DIR, exist_ok=True)


def _render_foot_mask(fname):
    """검(무기)을 숨기고 *캐릭터만* 저해상 렌더해 FOOT_MASK_DIR/fname 에 저장.

    🛑 정확한 발바닥 SSOT (두 팀 회고 종합): align_feet 의 세로 정렬 기준이 부정확하면 발이 뜨거나
    (검을 발로 오인) 땅속에 박힌다(정점 투영이 실제 발보다 위). 여기서 무기를 숨긴 캐릭터 raster 를
    남기면 그 alpha bbox 하단이 *화면에 실제 보이는 발바닥* 이다(투영 오차·검 오인 둘 다 없음).
    저해상(64) + WORKBENCH 라 최종(EEVEE) 대비 렌더 비용이 매우 작다. 🛑 회귀 없음: 마스크는
    alpha(실루엣) 하단만 쓰므로 셰이딩 엔진(WORKBENCH/EEVEE)과 무관하게 발바닥 위치가 동일하다.
    최종(검 포함) 렌더는 그대로 EEVEE 라 게임 화질도 안 바뀐다."""
    r = scene.render
    hidden = []
    for o in _weapon_objs:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    ox, oy, opct, ofp, oeng = (r.resolution_x, r.resolution_y,
                               r.resolution_percentage, r.filepath, r.engine)
    r.resolution_x = r.resolution_y = 64
    r.resolution_percentage = 100
    r.engine = "BLENDER_WORKBENCH"   # 실루엣 alpha 만 필요 → 고속(색/조명 무관, film_transparent 유지)
    r.filepath = os.path.join(FOOT_MASK_DIR, fname)
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        for o in hidden:
            o.hide_render = False
        (r.resolution_x, r.resolution_y,
         r.resolution_percentage, r.filepath, r.engine) = ox, oy, opct, ofp, oeng

# 렌더 대상 행동 — ONLY_ACTIONS 가 주어지면 그 부분집합만(auto-fit 부분 재렌더), 아니면 전체.
# 순서는 ACTIONS 를 유지(로그·진행률 일관). ONLY_ACTIONS 에 없는 행동은 이미 구워진 낱장을
# 그대로 두고 건드리지 않는다(위 _wipe_pngs 가 그 행동만 지웠으므로 보존됨).
_render_actions = ([a for a in ACTIONS if a in set(ONLY_ACTIONS)] if ONLY_ACTIONS else list(ACTIONS))
if ONLY_ACTIONS:
    print(f"####PARTIAL 부분 재렌더 — 대상 행동만: {_render_actions} (나머지 보존)")
total = 0
for name in _render_actions:
    a = bind(name)
    n = int(FRAMES.get(name, 8))
    # 행동별 scale. 🛑 셀(캔버스) 확대 방식(2026-07-09): scale<1 은 *모델을 작게 굽는 게 아니라*
    # 셀(orig)을 1/scale 배로 키워 무기 끝을 담는다 — body 는 원본 픽셀 밀도로 유지돼 화질 손실이 0.
    #  · ortho_scale = ortho/scale (카메라가 1/scale 넓게 담아 칼끝 포함, 기존과 동일)
    #  · resolution  = RENDER_RES/scale (해상도도 1/scale 로 키움 → 픽셀 밀도 resolution/ortho_scale
    #                  = RENDER_RES/ortho 로 *모든 행동 동일*. body 는 idle 과 같은 픽셀 수로 선명)
    # → orig 이 자동으로 base_cell/scale(예 128/0.8=160)로 커지고, 런타임(actor_animation_set.dart)이
    #   .atlas `laryen.actionScale.<action>`(=scale) 메타로 size=128/scale 표시 → 화면 스케일
    #   size/orig=1:1(선명) + body 화면 크기는 행동 무관 동일(발 anchor 0.85 정합). scale>1(모델 확대)
    #   은 셀 축소가 아니므로 해상도를 키우지 않고 기존 동작(RENDER_RES 고정) 유지.
    _sc = _ascale(name)
    cam.data.ortho_scale = ortho / _sc
    _res = round(RENDER_RES / _sc) if _sc < 1.0 else RENDER_RES  # scale<1 → 셀 확대(해상도 키움)
    r.resolution_x = r.resolution_y = _res
    if abs(_sc - 1.0) > 1e-6:
        print(f"####ASCALE {name} scale={_sc:g} → ortho={cam.data.ortho_scale:.3f} res={_res} "
              f"({'셀 확대' if _sc < 1 else '모델 확대'} ×{1.0/_sc:.3f} · 런타임 보정 → atlas 메타)")
    if a:
        frames = sample_frames(a, n, name in LOOP)
    else:
        # 애니메이션 없음 → rest(T-pose) 포즈를 n프레임 정적 렌더(정적 몹/오브젝트 폴백)
        arm.animation_data.action = None
        bpy.context.view_layer.update()
        frames = [bpy.context.scene.frame_current] * n
        print(f"####INFO 정적 렌더(애니없음): {name} x{n}")
    # 현재 작업 진행 마커 — sheet.py 가 읽어 "▶ 행동 idle 렌더 …" 로 간략 표시(--verbose 는 전체 로그).
    print(f"####ACTION {name} {DIRECTIONS}dir×{len(frames)}f={DIRECTIONS * len(frames)}")
    for label, az in zip(DIR_LABELS, DIR_AZIMUTHS):
        for idx, fr in enumerate(frames):
            bpy.context.scene.frame_set(fr)
            bpy.context.view_layer.update()
            place_camera(az, cur_target())            # 매 프레임 Hips 추적
            fname = f"{name}_{label}_{idx:02d}.png"
            r.filepath = os.path.join(OUT_FRAMES, fname)
            bpy.ops.render.render(write_still=True)   # 최종(검 포함)
            _render_foot_mask(fname)                  # 검 제외 캐릭터 실루엣 → _foot/fname (발 정렬용)
            total += 1
print(f"####FOOTMASK saved → {FOOT_MASK_DIR}")
print(f"####RENDER_DONE frames={total}")
