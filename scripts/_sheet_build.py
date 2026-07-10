"""
낱장 → *단일 통합* grid sprite sheet 합치기 — scripts/sheet.py 가 config json 으로 (uv run) 호출.

입력:  <frames_dir>/{action}_{DIR}_{idx:02d}.png   (_sheet_render.py 출력)
출력:  <sheet_out_dir>/{name}.png                  (1장, 16 row × Σframes col)
       <info_out_dir>/{name}_manifest.json + {name}_layout.md
       row = FLARE 16방향(기본) 또는 8방향, col = 모든 행동의 프레임을 ACTIONS 순서로 이어붙임
       (idle→walk→attack→hit→death→run). 각 행동의 col 범위(col_start/col_end)를 manifest 기록.
       cell = --size px(기본 128 — 모바일 OOM 회피), premultiplied-alpha Lanczos3 다운샘플(Pitfall ②).

OOM 회피 (2026-06-06): 행동별 분리 256 cell(한 액터 6장 ≈ 250MB VRAM)에서
단일 통합 128 cell(7680×2048 = 한 장 ≈ 63MB VRAM)로 전환 → 약 4배 절감.
화면 표시 = 128 × k(=kActorDisplayScale). 무기 포함 auto-fit 으로 셀 안 몸이 작아지면 k 로 보정.

런타임 보정값(_measure.json 의 head~foot 본 측정 → manifest):
  body_ratio          : 셀 안 몸 높이 비율(무기 무관). 무기가 클수록 작아진다.
  display_recommended : K / body_ratio  (K=목표 화면 몸 높이=kActorDisplaySize, *사람이 조정 가능*)
  foot_anchor         : 발의 셀 내 y(0~1, 위=0) = 도착지 정렬 anchor

결과 통계(JSON 한 줄)를 stdout 에 출력 → sheet.py 가 파싱해 사람용으로 표시.
호출: python3 scripts/_sheet_build.py <config.json>
"""
import os, sys, json
import numpy as np
from PIL import Image, ImageFile

cfg = json.load(open(sys.argv[1]))
SRC       = cfg["frames_dir"]
NAME      = cfg.get("name", "character")
CELL      = int(cfg["size"])
ACTIONS   = cfg["actions"]
FRAMES    = cfg["frames"]
KIND      = cfg.get("kind", "character")
K_TARGET  = float(cfg.get("k", 128.0))               # 목표 화면 몸 높이 px = kActorDisplaySize 의미
LOOP      = set(cfg.get("loop_actions", ["idle", "walk", "run"]))
SHEET_DIR = cfg.get("sheet_out_dir") or cfg.get("outputs")   # sprite sheet PNG 저장 폴더
INFO_DIR  = cfg.get("info_out_dir") or cfg.get("outputs")    # manifest/layout 저장 폴더
MEASURE   = cfg.get("measure_path")
# PNG 저장 색상 수(팔레트 양자화). 256(기본) → 무손실 대비 ~80%↓, 육안 차이 거의 없음.
# 0 → 양자화 끄고 무손실 RGBA 저장(색이 매우 중요한 자산용).
PNG_COLORS = int(cfg.get("png_colors", 256))
# 행동별 생성 scale {action: k} (기본 1.0). 사람 참조용으로 manifest 에 기록 — 런타임 display
# 역보정값(=1/k)은 sheet.py 가 actor_display_k.g.dart 에 별도로 기록한다(SSOT 는 그쪽).
ACTION_SCALES = cfg.get("action_scales", {}) or {}

# FLARE 방향 SSOT — sheet.py / _sheet_render.py 와 동일. 16방향(기본), 8 = 16의 짝수 인덱스.
_DIR16  = ["E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW",
           "W", "WNW", "NW", "NNW", "N", "NNE", "NE", "ENE"]
_NDIR   = int(cfg.get("directions", 16))
ROWS    = _DIR16 if _NDIR == 16 else _DIR16[::2]


def resize_premul(img, size):
    a = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:4]
    pm = np.concatenate([rgb * al, al], axis=-1)
    pim = Image.fromarray((pm * 255 + 0.5).astype(np.uint8), "RGBA").resize((size, size), Image.LANCZOS)
    b = np.asarray(pim, dtype=np.float32) / 255.0
    prgb, pal = b[..., :3], b[..., 3:4]
    out_rgb = np.where(pal > 1e-4, prgb / np.clip(pal, 1e-4, 1.0), 0.0)
    out = np.concatenate([np.clip(out_rgb, 0, 1), pal], axis=-1)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")


def save_png(img, path):
    """sprite sheet PNG 저장 — 색상 양자화(lossy) 또는 무손실 압축.

    3D 렌더 캐릭터는 안티앨리어싱·그라데이션으로 셀 한 장의 고유 RGBA 색이
    수십만 개라, zlib 무손실(optimize+compress 9)로는 ~2% 밖에 못 줄인다(실측).
    256색 팔레트 양자화(FASTOCTREE — RGBA 알파 보존 지원)는 ~80% 절감하면서
    RMSE<2·반투명 가장자리 유지로 육안 차이가 사실상 없다(검증 2026-06-05).
    PNG_COLORS=0 이면 양자화를 끄고 무손실 RGBA 로 저장한다.
    """
    rgba = img.convert("RGBA")
    if PNG_COLORS and PNG_COLORS > 0:
        # FASTOCTREE 는 RGBA(알파 포함) 양자화를 지원(MEDIANCUT 은 RGBA 불가).
        # dither off 가 sprite 에 깔끔(노이즈 없이 더 작게 압축).
        q = rgba.quantize(colors=PNG_COLORS, method=Image.FASTOCTREE, dither=Image.NONE)
        _save_png_ios_safe(q, path)
    else:
        _save_png_ios_safe(rgba, path, compress_level=9)
    return os.path.getsize(path)


def _save_png_ios_safe(im, path, compress_level=None):
    """iOS 시뮬레이터 디코더 호환을 위한 *표준* PNG 저장.

    PIL `save(optimize=True)` 는 전체 이미지를 *단일 거대 IDAT 청크* + sRGB/pHYs 메타로
    써서, **iOS 26.5 시뮬레이터의 이미지 디코더가 로드에 실패** 한다(실측 2026-06-18:
    male_quantum/male_chrome 가 26.5 시뮬레이터에서만 base 외형으로 fallback — 26.4·실기기는
    정상). 기본 male.png 는 다중 IDAT 라 로드돼 immortal 만 안 보였다. 다중 IDAT(64KB 분할)
    + 메타 청크 제거로 저장하면 실기기·26.4·26.5 시뮬레이터 모두 정상 로드된다."""
    im.info = {}                             # sRGB/pHYs 등 메타 청크 제거
    ImageFile.MAXBLOCK = 65536               # IDAT 64KB 분할(단일 거대 IDAT 회피)
    kw = {"optimize": False}
    if compress_level is not None:
        kw["compress_level"] = compress_level
    im.save(path, **kw)


def build_single():
    """모든 행동 → 단일 16 row × Σframes col sheet 1장.

    col 순서 = ACTIONS(idle/walk/attack/hit/death/run). 각 행동의 col 범위
    (col_start/col_end)를 함께 반환해 manifest·클라 layout(_mixamo16Layout) 정합을
    보장한다. 단일 통합으로 OOM(행동별 256 cell 6장 ≈ 250MB → 128 통합 ≈ 63MB) 회피.
    반환: (파일명, action_entries, total_cells, total_bytes, [w, h]).
    """
    total_cols = sum(int(FRAMES.get(a, 8)) for a in ACTIONS)
    sheet = Image.new("RGBA", (total_cols * CELL, len(ROWS) * CELL), (0, 0, 0, 0))
    # 발 정렬 목표 y — anchor SSOT(0.85). 각 프레임의 발(불투명 bbox 하단)을 셀의 이 y 에
    # 맞춰 수직 이동해 paste 한다. 행동별 scale(--scale-<action>)이나 무기 크기로 캐릭터가
    # 셀 안에서 작아져도(발 위치가 셀 중앙으로 떠올라도) 발을 항상 동일 y 에 고정하므로,
    # 행동 전환 시 상하 "점프" 가 원천 차단된다(scale·sheet 무관 고정 상수라 y 책정 불필요).
    foot_y = round(0.85 * CELL)
    entries, col_off, total_cells = [], 0, 0
    for act in ACTIONS:
        n = int(FRAMES.get(act, 8))
        cells = clip_top = clip_side = missing = 0
        for ri, d in enumerate(ROWS):
            for idx in range(n):
                fn = os.path.join(SRC, f"{act}_{d}_{idx:02d}.png")
                if not os.path.exists(fn):
                    missing += 1; continue
                src = Image.open(fn)
                bb = src.getbbox()                      # clip 통계(원본 해상도 기준)
                if bb:
                    cells += 1
                    if bb[1] <= 0 or bb[3] >= src.height: clip_top += 1
                    if bb[0] <= 0 or bb[2] >= src.width:  clip_side += 1
                cell_img = resize_premul(src, CELL)
                # 발 정렬 — cell_img 의 발(bbox 하단)을 foot_y 로 수직 이동(scale·무기 크기 무관).
                cb = cell_img.getbbox()
                shift_y = (foot_y - cb[3]) if cb else 0
                sheet.paste(cell_img, ((col_off + idx) * CELL, ri * CELL + shift_y), cell_img)
        entries.append({"name": act, "frames": n, "cols": n,
                        "col_start": col_off, "col_end": col_off + n,
                        "loop": act in LOOP, "cells": cells, "missing": missing,
                        "clip_top": clip_top, "clip_side": clip_side})
        col_off += n
        total_cells += cells
    os.makedirs(SHEET_DIR, exist_ok=True)
    fname = f"{NAME}.png"
    nbytes = save_png(sheet, os.path.join(SHEET_DIR, fname))
    return fname, entries, total_cells, nbytes, [sheet.width, sheet.height]


def layout_md(m):
    L = [f"# {m['name']} — 단일 통합 sprite sheet ({m['kind']})", "",
         f"- sheet: **`{m['sheet']}`**  ({m['size'][0]}×{m['size'][1]} px)",
         f"- cell: **{m['cell']}×{m['cell']}** px · {m['rows']} 방향(row) · **단일 통합(6행동 1장)**",
         f"- sheet 폴더: `{m['sheet_dir']}`",
         f"- body_ratio: **{m['body_ratio']}** (셀 안 몸 높이 비율, 무기 무관 — 클수록 몸이 큼)",
         f"- K(목표 화면 몸 높이) = **{m['k_target']}** px  (= kActorDisplaySize 의미)",
         f"- **권장 display = {m['display_recommended']}** px  = K / body_ratio",
         f"  - ⓘ *사람이 눈으로 보고* `{m['name']}_manifest.json` 의 `display_recommended` 를 조정할 수 있음",
         f"- **foot_anchor = {m['foot_anchor']}** (발의 셀 내 y, 0=위·1=아래) = 도착지 정렬 anchor",
         f"- 측정 본: head=`{m['head_bone']}`  feet=`{m['foot_bones']}`",
         "",
         "## 행동별 col 범위 (단일 sheet 내)", "",
         "| 행동 | col_start | col_end | 프레임 | loop | side접촉 |",
         "|---|---|---|---|---|---|"]
    for a in m["actions"]:
        L.append(f"| {a['name']} | {a['col_start']} | {a['col_end']} | {a['cols']} "
                 f"| {'loop' if a['loop'] else '1회'} | {a['clip_side']} |")
    L += ["", "## 방향(row) 매핑 — FLARE16 identity", "", "| row | 방향 |", "|---|---|"]
    for i, d in m["row_to_direction"].items():
        L.append(f"| {i} | {d} |")
    L += ["", "## Flame 로드 (참고)", "", "```dart",
          f"// cell {m['cell']}px → srcSize = Vector2({m['cell']}, {m['cell']})",
          f"// 단일 통합 sheet 1장 로드: actors/{m['name']}.png  (16 row × {sum(a['cols'] for a in m['actions'])} col)",
          "//   ActorAnimationSet.loadActor(images, '" + m['name'] + "')  // _mixamo16Layout 으로 col 범위 매핑",
          f"// 화면 표시: size = Vector2.all(kActorDisplaySize)   // = 128 × k(kActorDisplayScale)",
          f"// 도착지 정렬: anchor = Anchor(0.5, {m['foot_anchor']})",
          "```", ""]
    return "\n".join(L)


def main():
    measure = {}
    if MEASURE and os.path.exists(MEASURE):
        try:
            measure = json.load(open(MEASURE))
        except Exception:
            measure = {}
    body_ratio  = measure.get("body_ratio")
    # 발 정렬(build_single)이 모든 프레임 발을 셀 0.85 에 맞추므로, 실제 foot_anchor=0.85 가
    # 진실이다(measure 의 idle 측정값이 아니라 정렬 목표가 SSOT). 런타임 anchor(0.5,0.85)와 정합.
    foot_anchor = 0.85
    display = round(K_TARGET / body_ratio) if body_ratio else None

    fname, action_entries, total_cells, total_bytes, sheet_size = build_single()

    os.makedirs(INFO_DIR, exist_ok=True)
    manifest = {
        "name": NAME, "kind": KIND, "cell": CELL, "directions": _NDIR, "rows": len(ROWS),
        "row_to_direction": {str(i): d for i, d in enumerate(ROWS)},
        "sheet_dir": SHEET_DIR, "sheet": fname, "per_action_sheets": False,
        "size": sheet_size,                    # 단일 통합 sheet 의 [w, h] (예 [7680, 2048])
        "png_colors": PNG_COLORS,              # 0=무손실 RGBA, >0=팔레트 양자화 색상 수
        "total_bytes": total_bytes,
        "k_target": K_TARGET,
        "body_ratio": body_ratio,
        "display_recommended": display,        # = K / body_ratio. 사람이 manifest 보고 조정 가능.
        "foot_anchor": foot_anchor,            # 도착지 anchor (0~1, 위=0)
        "action_scales": ACTION_SCALES,        # 행동별 생성 scale(k). 런타임 display=1/k (actor_display_k.g.dart)
        "head_bone": measure.get("head_bone"),
        "foot_bones": measure.get("foot_bones"),
        "actions": action_entries,             # 각 행동의 col_start/col_end (단일 sheet 내 위치)
    }
    mpath = os.path.join(INFO_DIR, f"{NAME}_manifest.json")
    # encoding="utf-8" 명시 — Windows 기본(cp1252/cp949)에서는 한글/이모지 쓰기가
    # UnicodeEncodeError 로 죽는다(macOS/Linux 는 UTF-8 기본이라 무해한 no-op).
    json.dump(manifest, open(mpath, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    lpath = os.path.join(INFO_DIR, f"{NAME}_layout.md")
    open(lpath, "w", encoding="utf-8").write(layout_md(manifest))

    print(json.dumps({
        "name": NAME, "kind": KIND, "cell": CELL, "rows": len(ROWS),
        "sheet": fname, "size": sheet_size,
        "actions": [{"name": a["name"], "col_start": a["col_start"], "col_end": a["col_end"],
                     "cells": a["cells"], "clip_side": a["clip_side"]} for a in action_entries],
        "total_cells": total_cells, "total_bytes": total_bytes, "png_colors": PNG_COLORS,
        "body_ratio": body_ratio, "display_recommended": display, "foot_anchor": foot_anchor,
        "manifest": mpath, "layout_md": lpath, "sheet_dir": SHEET_DIR,
    }))


if __name__ == "__main__":
    main()
