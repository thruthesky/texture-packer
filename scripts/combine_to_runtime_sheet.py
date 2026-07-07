#!/usr/bin/env python3
"""행동별 256 sprite → 현행 런타임 128 단일 sheet(16 row × 60 col) 합성.

새 파이프라인(sheet.py)은 행동별 별도 256 sheet(<name>_<action>.png)를 만들지만,
현행 게임 런타임(ActorAnimationSet._sprite16x60SrcSize + _mixamo16Layout)은
*단일 sheet 16×60 · 128 cell* 을 기대한다. 본 스크립트가 그 간극을 메운다.

입력:  assets/render/{characters|monsters}/<name>_<action>.png  (16 row × N col, 256 cell)
출력:  assets/render/ai/laryen_<name>_sheet.png                  (16 row × 60 col, 128 cell)

행동 순서/프레임(= _mixamo16Layout): idle8 walk12 attack12 hit8 death8 run12 = 60 col.
256→128 다운샘플은 premultiplied-alpha Lanczos3(엣지 halo 방지, Pitfall ②).

사용: ./scripts/combine_to_runtime_sheet.py characters:female1 characters:male1 monsters:brute_ai_maw ...
      (인자 없으면 characters/female1,male1 + monsters 전체 자동)
"""
import sys, os, glob, subprocess
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_project_root(here):
    """라리엔 프로젝트 루트(assets/render/ 기준)를 찾는다. 본 파일은
    .claude/skills/texture-packer/scripts/ 로 이동했으므로 dirname(HERE) 는 repo 루트가
    아니다. ① LARYEN_ROOT env ② skill 4단계 상위 ③ git rev-parse ④ cwd 순서로 탐색."""
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


ROOT = _find_project_root(HERE)
LAYOUT = [("idle", 8), ("walk", 12), ("attack", 12), ("hit", 8), ("death", 8), ("run", 12)]  # 60 col
CELL = 128


def resize_premul(img, size):
    a = np.asarray(img.convert("RGBA"), np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:4]
    pm = np.concatenate([rgb * al, al], -1)
    pim = Image.fromarray((pm * 255 + .5).astype(np.uint8), "RGBA").resize((size, size), Image.LANCZOS)
    b = np.asarray(pim, np.float32) / 255.0
    prgb, pal = b[..., :3], b[..., 3:4]
    out = np.concatenate([np.clip(np.where(pal > 1e-4, prgb / np.clip(pal, 1e-4, 1), 0), 0, 1), pal], -1)
    return Image.fromarray((out * 255 + .5).astype(np.uint8), "RGBA")


def combine(kind, name):
    srcdir = os.path.join(ROOT, "assets", "render", kind)
    total = sum(n for _, n in LAYOUT)                 # 60
    sheet = Image.new("RGBA", (total * CELL, 16 * CELL), (0, 0, 0, 0))
    col, missing = 0, []
    for action, n in LAYOUT:
        p = os.path.join(srcdir, f"{name}_{action}.png")
        if not os.path.exists(p):
            missing.append(action); col += n; continue
        src = Image.open(p).convert("RGBA")           # 16 row × n col, 256 cell
        scol = src.width // 256                        # 실제 col 수(보통 n)
        for r in range(16):
            for c in range(min(n, scol)):
                cell = src.crop((c * 256, r * 256, c * 256 + 256, r * 256 + 256))
                cell128 = resize_premul(cell, CELL)
                sheet.paste(cell128, ((col + c) * CELL, r * CELL), cell128)
        col += n
    out = os.path.join(ROOT, "assets", "render", "ai", f"laryen_{name}_sheet.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    warn = f"  ⚠️ 누락 {missing}" if missing else ""
    print(f"  ✓ {kind}/{name} → assets/render/ai/laryen_{name}_sheet.png  ({sheet.width}x{sheet.height}){warn}")


def main():
    targets = []
    args = sys.argv[1:]
    if args:
        for a in args:
            kind, name = a.split(":", 1)
            targets.append((kind, name))
    else:
        for n in ("female1", "male1"):
            if os.path.exists(os.path.join(ROOT, "assets/render/characters", f"{n}_idle.png")):
                targets.append(("characters", n))
        for p in sorted(glob.glob(os.path.join(ROOT, "assets/render/monsters", "*_idle.png"))):
            targets.append(("monsters", os.path.basename(p)[:-len("_idle.png")]))
    print(f"=== {len(targets)} 모델 → 128 단일 sheet 합성 ===")
    for kind, name in targets:
        combine(kind, name)
    print("완료.")


if __name__ == "__main__":
    main()
