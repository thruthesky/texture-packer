"""비행체(드론·호버 유닛) 낱장 프레임에 **접지 그림자 + 본체 띄우기**를 합성한다.

🛑 **왜 필요한가 — 정렬 규칙이 비행체를 착륙시킨다.**

`align_feet.py` 는 모든 낱장의 *불투명 픽셀 bbox 하단* 을 셀의 `foot_frac`(0.85) 위치로
강제 이동한다. 다리로 걷는 액터에게는 이것이 정답이다(행동마다 카메라 배율이 달라 발 높이가
흔들리는 것을 막는다). 그런데 **비행체에게는 이 정렬이 곧 "고도 0 강제"** 다 — 3D 씬에서
기체를 아무리 z 로 띄워도 렌더된 낱장의 기체 아랫면이 bbox 하단이라, 정렬이 그것을 지면으로
끌어내린다.

실측(2026-08-11 `drone`): idle_E 8프레임의 콘텐츠 하단이 108/109/110/108/109/109/109/109 로
**고정**이고 상단만 27~70 으로 진동했다. 화면에서 이것은 "떠서 흔들리는 비행체" 가 아니라
**"찌그러졌다 펴지는 물체"** 로 읽힌다.

**해법은 정렬을 건드리는 것이 아니라, 정렬이 끝난 뒤에 프레임을 다시 조립하는 것이다:**

    ① 본체를 lift px 위로 올린다
    ② 원래 발 위치(= 지면 접점)에 타원 그림자를 그린다

그러면 최종 프레임의 bbox 하단은 **그림자** 가 되고, 런타임 앵커(0.5, 0.85)가 그림자를
지면에 놓으므로 **본체가 그 위에 떠 있는 그림** 이 된다. 코드 한 줄 없이, 자산만으로
부양감이 성립한다.

🛑 **반드시 `align_feet` *뒤* · TexturePacker *앞* 에서 돌려야 한다.**
  · 앞에서 돌리면 정렬이 그림자를 "발" 로 잡아 본체를 도로 내린다.
  · `_foot/` 마스크는 **건드리지 않는다**(다음 재굽기 때 같은 사고가 난다).

🛑 **런타임 hover 와 併用 금지.** 클라에서 스프라이트를 또 위로 올리면 그림자까지 함께 떠올라
**부양감이 역전**된다(cowork dron 에서 grok 이 지적한 리스크). 둘 중 하나만 쓴다 — 이 스크립트를
쓰면 클라는 한 줄도 고치지 않는다.

사용:
    python3 ground_shadow.py <frames_dir> [--lift 20] [--foot-frac 0.85]
        [--rx 26] [--ry 8] [--alpha 90] [--blur 2.5] [--no-lift death]
"""
import os
import sys
import argparse

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("[FAIL] Pillow 가 필요하다: pip install pillow", file=sys.stderr)
    sys.exit(2)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="비행체 프레임에 접지 그림자 + 본체 띄우기 합성")
    ap.add_argument("frames_dir", help="낱장 프레임 폴더(align_feet 를 마친 상태)")
    ap.add_argument("--lift", type=float, default=18.0,
                    help="본체를 위로 올릴 **화면 px**. 프레임 픽셀로는 orig/128 배 환산된다"
                         "(행동마다 캔버스가 달라서 — walk 139 · death 173). 기본 18")
    ap.add_argument("--foot-frac", type=float, default=0.85,
                    help="지면 접점 = 셀 높이의 이 비율. align_feet 와 같은 값이어야 한다")
    # 🛑 그림자를 **고정 크기로 두면 안 된다** — 8방향 액터는 보는 각도마다 실루엣 폭이 크게
    #    달라서(정면은 좁고 측면은 넓다), 같은 타원을 깔면 방향에 따라 "그림자만 동떨어져"
    #    보인다(사용자 지적 2026-08-11: "드론은 길쭉한데 그림자는 완전 동그래서 어색하다").
    #    그래서 **프레임마다 실루엣 폭을 재서 거기에 비례**시킨다.
    ap.add_argument("--width-ratio", type=float, default=0.44,
                    help="그림자 가로 반지름 = 그 프레임 실루엣 폭 × 이 값 (기본 0.44)")
    ap.add_argument("--flat", type=float, default=0.26,
                    help="그림자 세로/가로 비율. 작을수록 납작하고 길쭉하다 (기본 0.26 ≈ 1:3.8)")
    ap.add_argument("--min-rx", type=float, default=10.0, help="그림자 가로 반지름 최솟값 px")
    ap.add_argument("--alpha", type=int, default=90, help="그림자 진하기 0~255")
    ap.add_argument("--blur", type=float, default=2.5, help="그림자 가장자리 흐림 반경")
    ap.add_argument("--no-lift", default="death",
                    help="띄우지 않을 행동(쉼표 구분). 기본 death — 추락해 처박히는 연출이라 "
                         "띄우면 공중에서 죽는다")
    ap.add_argument("--shrink-with-lift", type=float, default=0.0,
                    help=">0 이면 lift 가 클수록 그림자를 이 비율만큼 작고 옅게(고도 표현). 기본 0=고정")
    return ap.parse_args(argv)


def action_of(filename):
    """`idle_E_03.png` → `idle`. 파일명 규약은 `{action}_{DIR}_{idx}.png`."""
    return filename.split("_", 1)[0]


def composite_one(im, lift, foot_y, rx, ry, alpha, blur, cx=None):
    """프레임 한 장: 본체를 lift 만큼 올리고, foot_y 에 타원 그림자를 깐다.

    `cx` 를 주면 그 x 를 그림자 중심으로 삼는다(실루엣 중심). 없으면 캔버스 중앙.
    🛑 캔버스 중앙 고정은 위험하다 — 액터가 프레임 안에서 한쪽으로 치우친 방향에서는
    그림자만 옆으로 어긋나 보인다."""
    w, h = im.size
    if cx is None:
        cx = w / 2.0

    # ── 그림자 레이어 — 지면 접점에 눕힌 타원 ──────────────────────────
    # 🛑 그림자는 **올리지 않는다**. 이것이 지면을 표시하는 유일한 기준점이라,
    #    같이 올리면 부양감이 사라진다(그림자와 본체가 함께 뜨면 그냥 "큰 물체" 다).
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if alpha > 0 and rx > 0 and ry > 0:
        d = ImageDraw.Draw(shadow)
        d.ellipse([cx - rx, foot_y - ry, cx + rx, foot_y + ry], fill=(0, 0, 0, alpha))
        if blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(blur))

    # ── 본체 — 위로 이동(캔버스 크기는 그대로. 넘치는 부분은 잘린다) ──────
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body.paste(im, (0, -int(round(lift))))

    # 그림자가 아래, 본체가 위
    return Image.alpha_composite(shadow, body)


def main(argv=None):
    a = parse_args(argv)
    if not os.path.isdir(a.frames_dir):
        print(f"[FAIL] 폴더가 없다: {a.frames_dir}", file=sys.stderr)
        return 2

    no_lift = {s.strip() for s in a.no_lift.split(",") if s.strip()}
    files = sorted(f for f in os.listdir(a.frames_dir) if f.endswith(".png"))
    if not files:
        print(f"[FAIL] png 가 없다: {a.frames_dir}", file=sys.stderr)
        return 2

    # 🛑 **행동마다 프레임 캔버스가 다르다.** sheet.py 의 auto-fit 이 잘리는 행동만 축소 렌더하고
    #    `laryen.actionScale.<action>` 으로 런타임에 되돌리기 때문이다(실측 drone: idle/attack
    #    128 · walk 139 · death 173). 그래서 **화면에서 같은 높이로 뜨려면 프레임 픽셀 상승량이
    #    행동마다 달라야 한다** — 모두에 같은 px 를 주면 행동이 바뀔 때 기체 높이가 튄다.
    #    환산: frame_lift = screen_lift × (orig / 128).
    CELL_BASE = 128.0

    # 셀 상단 여유를 행동별로 재서 잘림을 예고한다(최종 게이트는 sheet.py --verify-cells 지만,
    # 원인이 lift 라는 것은 이 단계에서만 알 수 있다).
    tops = {}   # action → (최소 상단 여유, 캔버스 높이)
    for fn in files:
        act = action_of(fn)
        if act in no_lift:
            continue
        with Image.open(os.path.join(a.frames_dir, fn)) as _im:
            im = _im.convert("RGBA")
            bb = im.getbbox()
            h = im.height
        if not bb:
            continue
        prev = tops.get(act)
        tops[act] = (bb[1] if prev is None else min(prev[0], bb[1]), h)
    for act, (top, h) in sorted(tops.items()):
        need = a.lift * (h / CELL_BASE)
        mark = "⚠️ 잘림" if need > top else "ok"
        print(f"     [{act}] 캔버스 {h} · 상단 여유 {top}px · 필요 {need:.1f}px → {mark}")
        if need > top:
            print(f"[WARN] {act}: lift 가 상단 여유를 넘는다 — "
                  f"--lift {top / (h / CELL_BASE):.0f} 이하를 권한다")

    n_lift = n_shadow = 0
    for fn in files:
        p = os.path.join(a.frames_dir, fn)
        act = action_of(fn)
        with Image.open(p) as _im:
            im = _im.convert("RGBA")
        h = im.height
        k = h / CELL_BASE                 # 이 행동의 캔버스 배율(orig/128)
        foot_y = a.foot_frac * h          # 지면 접점 — 런타임 anchor 0.85 와 같은 축

        lift = 0.0 if act in no_lift else a.lift * k

        # 🛑 이 프레임의 **실루엣**을 재서 그림자를 맞춘다 — 방향마다 폭이 다르므로
        #    고정 타원을 쓰면 "드론은 길쭉한데 그림자만 동그란" 어색함이 생긴다.
        bb = im.getbbox()
        if bb:
            body_w = bb[2] - bb[0]
            cx = (bb[0] + bb[2]) / 2.0        # 실루엣 가로 중심(캔버스 중앙이 아니다)
        else:
            body_w, cx = h * 0.5, im.width / 2.0
        rx = max(a.min_rx * k, body_w * a.width_ratio)
        ry = rx * a.flat
        al = a.alpha
        if a.shrink_with_lift > 0 and lift > 0:
            # 높이 뜰수록 그림자가 작고 옅어진다(선택)
            s = 1.0 - min(1.0, a.shrink_with_lift)
            rx, ry = rx * s, ry * s
            al = int(al * s)

        out = composite_one(im, lift, foot_y, rx, ry, al, a.blur, cx=cx)
        out.save(p)
        if n_shadow == 0:
            print(f"     예) {fn}: 실루엣 폭 {body_w:.0f} → 그림자 {rx * 2:.0f}×{ry * 2:.0f} "
                  f"(중심 x={cx:.0f})")
        n_shadow += 1
        if lift > 0:
            n_lift += 1

    print(f"[OK] ground_shadow — 프레임 {len(files)}장 · 그림자 {n_shadow} · 띄움 {n_lift} "
          f"(화면 lift={a.lift:.0f}px → 캔버스별 환산, foot={a.foot_frac}, "
          f"그림자=실루엣폭×{a.width_ratio} · 납작도 {a.flat} · a{a.alpha})")
    if no_lift:
        print(f"     띄우지 않은 행동: {', '.join(sorted(no_lift))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
