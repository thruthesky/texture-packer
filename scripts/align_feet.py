#!/usr/bin/env python3
"""낱장 frame PNG 발(불투명 bbox 하단) 수직 정렬 — TexturePacker 前 처리.

각 낱장의 발(=불투명 픽셀 bbox 의 하단)을 캔버스 높이의 foot_frac(기본 0.85) 위치로 수직
이동(in-place)한다. 행동별 scale(sheet.py --scale-attack 등)로 캐릭터가 셀 안에서 작아지면,
_sheet_render.py 의 카메라가 몸 *중심* 을 겨냥하고 ortho_scale 을 행동마다 바꾸므로 발의 화면
y 가 행동마다 달라진다(attack 이 위로 뜸). 이를 모든 프레임에서 동일 y(0.85)로 고정해,
런타임 컴포넌트 anchor(0.5, 0.85)와 정합시켜 "발이 공중에 뜨는" 현상을 없앤다.

grid 경로(_sheet_build.py)의 발 정렬과 동일 원리·동일 상수(0.85)를 atlas 낱장에도 적용한다.
좌우(x)는 건드리지 않고 세로(y)만 shift 하므로 방향/포즈에 영향이 없다.

사용:  python3 align_feet.py <frames_dir> [foot_frac=0.85]
"""
import os
import sys

# 🛑 Windows 콘솔/파이프 기본 stdout 인코딩이 cp1252 이면, 아래 한글 print 가
# UnicodeEncodeError(charmap codec) 로 죽어 부모(sheet-win.py)가 "발 정렬 실패" 로
# 오판한다(정렬은 이미 끝났는데도). UTF-8 로 강제 재구성해 이 회귀를 막는다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from PIL import Image


def align_dir(frames_dir, foot_frac=0.85):
    # 🛑 발바닥 기준 = _foot/ 마스크(검 제외 캐릭터 실루엣, _sheet_render.py 가 프레임별 저장)의
    # alpha bbox 하단. 무기(검)가 발보다 아래로 내려가는 attack 프레임에서 *일반* bbox 하단은
    # 검 끝이라 발이 뜨고, 정점 투영은 발보다 위를 잡아 땅속에 박힌다. 검 제외 raster 의 bbox
    # 하단은 화면에 실제 보이는 발바닥이라 정확하다. 마스크 없으면 일반 bbox 폴백.
    mask_dir = os.path.join(frames_dir, "_foot")
    have_mask = os.path.isdir(mask_dir)
    used_mask = 0
    aligned = 0
    for fn in sorted(os.listdir(frames_dir)):
        if not fn.endswith(".png"):
            continue
        p = os.path.join(frames_dir, fn)
        im = Image.open(p).convert("RGBA")
        H = im.height
        target = round(foot_frac * H)
        cur_foot = None
        if have_mask:
            mp = os.path.join(mask_dir, fn)
            if os.path.isfile(mp):
                mim = Image.open(mp).convert("RGBA")
                mbb = mim.getbbox()  # 검 제외 실루엣 bbox — 하단 = 발바닥.
                if mbb:
                    cur_foot = round(mbb[3] / mim.height * H)  # 저해상 frac → 이 프레임 px
                    used_mask += 1
        if cur_foot is None:
            bb = im.getbbox()  # 폴백: 일반 bbox 하단(무기 포함 — attack 부정확 가능).
            if not bb:
                continue
            cur_foot = bb[3]
        shift = target - cur_foot
        if shift == 0:
            continue
        canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
        canvas.paste(im, (0, shift), im)  # 세로만 이동(x 불변 → 방향/포즈 무영향).
        canvas.save(p)
        aligned += 1
    return aligned, used_mask


def main():
    if len(sys.argv) < 2:
        sys.exit("사용: align_feet.py <frames_dir> [foot_frac=0.85]")
    frames_dir = sys.argv[1]
    foot_frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.85
    if not os.path.isdir(frames_dir):
        sys.exit(f"frames 폴더가 없습니다: {frames_dir}")
    n, used = align_dir(frames_dir, foot_frac)
    print(f"aligned {n} (foot_frac={foot_frac}, 마스크 기준={used}, bbox 폴백={n - used})")


if __name__ == "__main__":
    main()
