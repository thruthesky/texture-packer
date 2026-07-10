#!/usr/bin/env python3
"""cell 잘림(clip/cut-off) 자동 검사 — flutter 실행 없이 생성된 프레임/atlas 이미지만으로
pc/npc/mob 애니메이션이 셀 밖으로 잘렸는지 판정하고, 행동별 권장 --scale-<action> 을 제시한다.

🛑 핵심 개념: sheet.py 는 각 프레임을 정사각 셀(render_res, 예 256/512)에 렌더한다. 모델·무기가
크면(run/attack 의 검 휘두름 등) 셀 경계 밖으로 나가 *clip* 되고, 그 흔적이 **프레임 테두리의
불투명(alpha>0) 픽셀** 로 남는다. 테두리에 불투명이 있으면 = 그 방향으로 잘렸다는 뜻이다.
→ 잘린 정도에 비례해 --scale-<action> 을 낮추면(모델을 작게 구우면) 셀 안에 들어온다.

발 정렬(align_feet 0.85) 이후 프레임 기준: 정상 프레임은 4 테두리가 모두 투명해야 한다
(발은 0.85 위치, 아래 15% 여백). 어느 테두리든 불투명이면 그 방향 clip.

사용:
  # 낱장 프레임 폴더 검사(sheet.py 렌더 직후 frames/ 검사에 사용 — packing 전)
  verify_cells.py --frames outputs/<name>/frames [--margin 2] [--alpha 8] [--json]
  # packed atlas 검사(orig=cell 대비 packed size 가 셀을 넘는지 — trim 후라 근사)
  verify_cells.py --atlas assets/<kind>/<name>/<name>.atlas

exit code: 0=잘림 없음(정상) · 2=잘림 발견(권장 scale 출력) · 1=입력/실행 오류.
"""
import argparse
import glob
import json
import os
import re
import sys

# Windows 콘솔(cp1252/cp949)에서 →·✓·⚠️·❌ 등 유니코드 출력이 UnicodeEncodeError 로 죽지 않도록
# stdout/stderr 를 UTF-8 로 강제한다(Python 3.7+). sheet-win.py 와 동일한 방어(win 포트 정합).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("필수 패키지 누락: pip install pillow numpy  (또는 uv run --with pillow --with numpy …)")

# 낱장 프레임 파일명: <action>_<DIR16>_<idx>.png (예 attack_ENE_04.png). _sheet_render.py 출력 규약.
_FRAME_RE = re.compile(r"^(?P<action>[a-z]+)_(?P<dir>[A-Z]+)_(?P<idx>\d+)\.png$")

# 행동별 scale 하한 = 셀 확대 상한. 🛑 셀 확대 방식(2026-07-09): scale<1 은 body 를 줄이는 게
# 아니라 셀(캔버스)을 1/scale 배로 키워 무기 끝을 담는다(body 는 원본 픽셀 밀도 유지 → 화질 손실
# 0). scale=1/셀배율 이므로 0.667 → 셀 최대 1.5배(128→192)로 제한해 iOS OOM(atlas RAM)을 통제한다.
# 0.667 하한에서도 잔여 잘림이면 무기 모델 축소/카메라·margin 조정이 필요하다.
SCALE_MIN = 0.667


def edge_opacity(img, margin, alpha_thresh):
    """프레임 4 테두리(margin px 두께)의 불투명(alpha>thresh) 픽셀 수와, 각 변을 따라 불투명이
    차지하는 비율(0~1)을 반환. 비율(frac)이 clip 심각도 근사 — 테두리를 따라 넓게 불투명할수록
    모델이 그 방향으로 많이 삐져나가 잘린 것이다(잘린 부분은 이미 없어 정확한 폭은 반복 검사로 수렴).

    🛑 '안쪽 깊이'로 재면 캐릭터 몸통 세로 길이를 잘림으로 오판한다(테두리에 닿은 몸통이 안쪽까지
    연속 불투명이라 깊이가 셀에 육박). 그래서 *테두리 라인 위의 불투명 비율* 만 심각도로 쓴다.

    🛑 견고성: alpha 채널이 없는 이미지(RGB 등)는 clip 판정 불가(convert 시 alpha=255 전체 불투명
    → 테두리 다 불투명 → false positive)이므로 None 을 반환해 스킵한다. 또 margin 이 프레임 절반
    이상인 초소형/비정상 프레임은 테두리가 전체를 덮어 오판하므로 margin 을 프레임 1/4 로 클램프한다."""
    if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
        return None  # alpha 없음 → clip 판정 불가(스킵 신호)
    a = np.asarray(img.convert("RGBA"))[:, :, 3]
    h, w = a.shape
    m = max(1, min(int(margin), (min(h, w) // 4) or 1))  # 초소형 프레임 오판 방지
    op = a > alpha_thresh
    counts = {
        "top": int(op[:m, :].sum()),
        "bottom": int(op[h - m:, :].sum()),
        "left": int(op[:, :m].sum()),
        "right": int(op[:, w - m:].sum()),
    }
    # 각 변 테두리 픽셀 중 불투명 비율(0~1). top/bottom 는 폭 w, left/right 는 높이 h 기준.
    frac = {
        "top": counts["top"] / float(m * w),
        "bottom": counts["bottom"] / float(m * w),
        "left": counts["left"] / float(m * h),
        "right": counts["right"] / float(m * h),
    }
    return counts, frac, (h, w)


def verify_frames(frames_dir, margin=2, alpha_thresh=8):
    """frames_dir 의 모든 낱장 프레임을 검사해 행동별 잘림 집계와 권장 scale 을 만든다."""
    paths = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not paths:
        return None
    # action → {frames, clipped, max_depth, worst_frame, dirs, cell}
    per_action = {}
    for p in paths:
        name = os.path.basename(p)
        m = _FRAME_RE.match(name)
        if not m:
            continue  # _foot 마스크 등 규약 외 파일 무시
        action = m.group("action")
        try:
            eo = edge_opacity(Image.open(p), margin, alpha_thresh)
        except Exception:
            continue
        if eo is None:
            continue  # alpha 채널 없음(RGB 등) → clip 판정 불가, 스킵(false positive 방지)
        counts, frac, (ch, cw) = eo
        rec = per_action.setdefault(action, {
            "frames": 0, "clipped": 0, "max_frac": 0.0, "worst": None,
            "edges": {"top": 0, "bottom": 0, "left": 0, "right": 0}, "cell": (ch, cw),
            # worst_edges: 최악(가장 많이 잘린) 프레임이 *어느 변으로 얼마나* 잘렸는지({top:0.1,…}).
            # 전 프레임 목록은 만들지 않는다 — 사용자 지시(2026-07-09): 프레임 전수 기록은 느리니
            # '최악 프레임'만 기록하면 충분. worst(파일명)+worst_edges 한 쌍으로 clip.log·최종 요약을 낸다.
            "worst_edges": {},
        })
        rec["frames"] += 1
        maxf = max(frac.values())
        if maxf > 0:  # 어느 테두리든 불투명 → clip
            rec["clipped"] += 1
            for e, fv in frac.items():
                if fv > 0:
                    rec["edges"][e] += 1
            if maxf > rec["max_frac"]:
                rec["max_frac"] = maxf
                rec["worst"] = name
                # 최악 프레임의 변별 잘림 비율만 기록(전수 목록 대신 — 가볍고 빠름).
                rec["worst_edges"] = {e: round(fv, 4) for e, fv in frac.items() if fv > 0}
    # 권장 scale: 잘린 변의 최대 불투명 비율(max_frac)만큼 모델이 셀을 넘었다고 근사 → 여유 6% 더해
    #   축소. 정확한 잘린 폭은 프레임만으론 알 수 없으므로, 이 값으로 재생성→재검사를 반복해 수렴한다.
    for action, rec in per_action.items():
        if rec["clipped"] > 0:
            rec["recommended_scale"] = max(SCALE_MIN, round(1.0 - rec["max_frac"] - 0.06, 2))
        else:
            rec["recommended_scale"] = None
    return per_action


def print_report(per_action, source):
    """행동별 잘림 리포트를 사람이 읽게 출력. 잘림 있으면 True 반환(exit 2 판단)."""
    any_clip = False
    print(f"\n🔍 cell 잘림 검사 — {source}")
    ok_actions, bad_actions = [], []
    for action in sorted(per_action):
        rec = per_action[action]
        if rec["clipped"] == 0:
            ok_actions.append(f"{action}({rec['frames']})")
            continue
        any_clip = True
        bad_actions.append(action)
        edges = ", ".join(f"{e}×{n}" for e, n in rec["edges"].items() if n)
        # 최악 프레임이 어느 변으로 잘렸는지(worst_edges) 한 줄로 — 전수 목록 대신 최악만(빠름).
        we = ", ".join(f"{k}={v*100:.0f}%" for k, v in rec.get("worst_edges", {}).items())
        print(f"  ⚠️ {action:6} — {rec['clipped']}/{rec['frames']} 프레임 잘림 · "
              f"테두리불투명 최대 {rec['max_frac'] * 100:.0f}% · 변[{edges}]")
        print(f"        · 최악 프레임: {rec['worst']}  ({rec['max_frac']*100:.0f}% [{we}])")
        print(f"        → 권장 --scale-{action} {rec['recommended_scale']} "
              f"(현재보다 작게 구우면 셀 안에 들어옴)")
    if ok_actions:
        print(f"  ✓ 잘림 없음: {', '.join(ok_actions)}")
    if any_clip:
        rec_opts = " ".join(f"--scale-{a} {per_action[a]['recommended_scale']}" for a in bad_actions)
        print(f"\n  🛑 잘린 행동 {len(bad_actions)}종 — 아래 옵션으로 재생성 권장:")
        print(f"     {rec_opts}")
    else:
        print("  ✅ 전 행동 잘림 없음 — cell 정상.")
    return any_clip


def main():
    ap = argparse.ArgumentParser(description="cell 잘림(clip) 자동 검사 + 권장 scale")
    ap.add_argument("--frames", help="낱장 프레임 폴더(frames/) — 렌더 직후 검사에 권장")
    ap.add_argument("--atlas", help="packed .atlas — orig 대비 packed size 로 근사 검사")
    ap.add_argument("--margin", type=int, default=2, help="테두리 검사 두께 px(기본 2)")
    ap.add_argument("--alpha", type=int, default=8, help="불투명 판정 alpha 임계(기본 8)")
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로 출력(자동화용)")
    args = ap.parse_args()

    if args.frames:
        per_action = verify_frames(args.frames, args.margin, args.alpha)
        if per_action is None:
            print(f"❌ 프레임 없음: {args.frames}")
            return 1
        if args.json:
            print(json.dumps(per_action, ensure_ascii=False, indent=2))
            clipped = any(r["clipped"] > 0 for r in per_action.values())
            return 2 if clipped else 0
        clipped = print_report(per_action, args.frames)
        return 2 if clipped else 0
    if args.atlas:
        return verify_atlas(args.atlas, args.json)
    ap.error("--frames 또는 --atlas 중 하나를 지정하세요.")


def verify_atlas(atlas_path, as_json):
    """🛑 정보성 *근사* 검사 — 자동 판정/게이트에 쓰지 말 것(팀 지적4).

    packed .atlas 는 trim 후라 원본 clip 을 *직접 못 본다*. 여기서는 `size>=orig`(여백 0=셀을
    꽉 채움)를 clip '후보'로만 표시하는데, stripWhitespace off·여백 없는 *정상* 자산도 전부
    후보로 찍힌다(실측: male_chrome.atlas 1024 region 전부). 따라서 잘림 여부의 실제 판정은
    렌더 직후 낱장 `--frames` 로만 하고, 이 `--atlas` 는 참고 정보로만 쓴다.
    🛑 exit code 는 *항상 0*(정보성) — 자동 흐름이 exit 2 를 '잘림'으로 오판하지 않게 한다."""
    try:
        with open(atlas_path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"❌ .atlas 열기 실패: {e}")
        return 1
    # region 블록에서 size/orig/offset 파싱(간단 스캔).
    regions = re.findall(
        r"\n(\w[\w-]*)\n(?:\s+\w+:.*\n)*?\s+size:\s*(\d+),\s*(\d+)\n\s+orig:\s*(\d+),\s*(\d+)\n\s+offset:\s*(-?\d+),\s*(-?\d+)",
        text)
    suspects = []
    for nm, sw, sh, ow, oh, ox, oy in regions:
        sw, sh, ow, oh, ox, oy = map(int, (sw, sh, ow, oh, ox, oy))
        if sw >= ow or sh >= oh:
            suspects.append((nm, sw, sh, ow, oh))
    print(f"\n🔍 atlas *근사* 검사(정보성) — {atlas_path}  (region {len(regions)}개)")
    print("  🛑 이 검사는 부정확한 근사다 — 자동 판정 금지. 정확한 잘림 판정은 `--frames`(렌더 직후 낱장).")
    if suspects:
        print(f"  ℹ️ 여백 0(꽉 찬) region {len(suspects)}개 — *정상일 수 있음*(trim off·여백 없는 자산). 정밀은 --frames:")
        for nm, sw, sh, ow, oh in suspects[:12]:
            print(f"      {nm}  size {sw}×{sh} / orig {ow}×{oh}")
    else:
        print("  ℹ️ 여백 있는 region 만(꽉 찬 셀 없음).")
    return 0  # 항상 정보성(자동 게이트 오판 방지 — 실제 판정은 --frames)


if __name__ == "__main__":
    sys.exit(main())
