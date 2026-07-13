#!/usr/bin/env python3
r"""
Laryen **4-direction PREVIEW** sprite sheet generator CLI — **macOS + Windows**.

A lightweight preview variant of scripts/sheet.py (macOS) / sheet-win.py (Windows). Its purpose is
to quickly *eyeball* a character/monster's facing, pose, and animation matching. It differs from the
production sheet in three ways:
  (1) Renders **4 directions only** (N/E/S/W cardinals) instead of production 16/8. row count 4 = 1/4 the height.
  (2) Renders **3 frames per action only** (instead of production idle 8 / walk 12 etc.) — fixed 3 for every action.
  (3) Makes the **cell (image) bigger** (default **384px** vs. the production render cell — larger preview detail).
  -> 4 dir x 3 frame x 6 action = 18 col x 4 row. 384px cell -> 6912x1536 sheet (within 8192).

NOTE: this is NOT production asset generation. New PC/monster *runtime* sprites MUST be made with
sheet.py at 16 directions / 128 cell (CLAUDE.md SSOT). This script is a **human-eyeball preview only**,
and by default writes to the outputs/<name>_preview/ work folder so it never pollutes production assets/.

Cross-platform (macOS + Windows):
  Blender / Python resolution branches on sys.platform. On macOS it looks in
  /Applications/Blender.app and PATH; on Windows it reads the registry Uninstall keys + standard
  install locations. The build-step Python interpreter prefers python3 (macOS) or python/py
  (Windows). Everything else — the 4-direction preview logic — is identical on both.

Self-contained design (shared production helpers untouched):
  The production _sheet_render.py / _sheet_build.py only allow directions in {1, 8, 16} (4 rejected).
  To avoid *touching* those shared helpers, this script **auto-generates two helpers** next to them:
    scripts/_sheet_preview_render.py  — copy of the production render helper + a 4-direction patch.
    scripts/_sheet_preview_build.py   — copy of the production build helper + a 4-direction patch.
  Both files are *regenerated* from the production originals on every run (the originals are the SSOT),
  so fixing an original also keeps the preview helpers up to date (see _ensure_preview_helpers below).

Usage examples:
  # macOS (line continuation is backslash \):
  ./scripts/sheet_preview.py --character game-assets/characters/male.fbx --name male \
    --animations game-assets/animations/default

  # Windows PowerShell (line continuation is backtick `):
  py scripts\sheet_preview.py --character game-assets\characters\male.fbx --name male `
    --animations game-assets\animations\default

  # Make the cell even bigger (e.g. 512) — watch the 8192 limit depending on col count
  ./scripts/sheet_preview.py --character game-assets/monsters/demonic_king.fbx \
    --name demonic_king --animations game-assets/animations/default --shading texture --size 512

Options are identical to the production sheet except for these defaults:
  --directions  : fixed at 4 (not changeable — preview is 4-direction only).
  --size        : 384 (instead of the production render cell — a large preview).
  --idle/--walk/--run/--attack/--hit/--death : default to **3** each when omitted (instead of production 8~12).

Preview only specific actions (skip rendering the whole set):
  --only-attack                 render just the attack action (combine e.g. --only-attack --only-walk)
  --only attack                 same, one action
  --only idle,attack            a subset
  These override --actions and keep the canonical column order. Fastest way to eyeball one animation.
  Example — attack only:
    ./scripts/sheet_preview.py --character game-assets/blend/male.blend --name male \
      --animations game-assets/animations/default --only-attack

Per-action generation scale (--scale-<action>):
  Same as the production sheet — pass --scale-attack 0.8 (etc.) to shrink one action's model inside the
  cell so the preview matches the framing production will bake (e.g. a swung weapon that fits). Unset
  actions fall back to the global --scale. Unlike production, the preview never *prompts* for these (it
  is a non-interactive eyeball tool); pass them to mirror the exact scales your real atlas build will use.

Progress display:
  The render step now prints per-action markers plus percent · fps · ETA (like the production sheet) and
  a timing summary per pass. Use --verbose for the full Blender log.

Per-action character override:
  --character is the *default* model for every action. To render one action from a different model,
  pass --character-<action> (e.g. --character-attack other.fbx). Each overridden action is rendered in
  its own Blender pass (same animation folder, different mesh/rig) and composited into the same sheet.
  Example — body for idle/walk, a variant for attack:
    ./scripts/sheet_preview.py --character game-assets/characters/male.fbx --name male \
      --animations game-assets/animations/default --character-attack game-assets/characters/male_v2.fbx
"""
import argparse, glob, json, os, subprocess, sys, shutil, time

# Force stdout/stderr to UTF-8 so unicode output does not die with UnicodeEncodeError on
# Windows consoles (cp1252/cp949). Harmless no-op on macOS (already UTF-8).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Platform switch — macOS ('darwin') vs Windows ('win32'). Used only for Blender/Python resolution;
# all preview logic is platform-agnostic.
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"


def _fmt_dur(seconds):
    """Seconds -> short human form ('43s' · '2m28s' · '1h03m') for progress/speed/ETA display."""
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


HERE = os.path.dirname(os.path.abspath(__file__))
# Preview defaults — the three axes that differ from the production sheet.
PREVIEW_DIRECTIONS = 4            # (1) fixed at 4 directions (N/E/S/W cardinals)
PREVIEW_FRAMES_PER_ACTION = 3     # (2) fixed at 3 frames per action (when omitted)
PREVIEW_CELL_DEFAULT = "384"      # (3) bigger cell (image) — 384 vs. the production render cell
DEFAULT_ACTIONS = ["idle", "walk", "attack", "hit", "death", "run"]   # col order
# Suggested per-action generation scale (matches sheet.py SCALE_PROMPT_DEFAULTS).
# Only applied when the matching --scale-<action> is passed — the preview never *prompts* for it
# (it is a non-interactive eyeball tool). Passing --scale-attack 0.8 lets the preview reflect the
# same framing production will bake, so what you eyeball matches the real atlas. <1 shrinks the
# model in the cell (weapon/motion clipping avoidance); the preview shows exactly that shrink.
SCALE_PROMPT_DEFAULTS = {"idle": 1.0, "walk": 0.9, "run": 0.9, "attack": 0.8, "hit": 0.9, "death": 1.0}
TEXTURE_LIMIT = 8192
SUPPORTED_EXT = (".fbx", ".glb", ".gltf")
CHAR_EXT = SUPPORTED_EXT + (".blend",)

# Mapping production helper -> auto-generated preview helper (4 directions allowed).
_RENDER_SRC = os.path.join(HERE, "_sheet_render.py")
_BUILD_SRC  = os.path.join(HERE, "_sheet_build.py")
_RENDER_DST = os.path.join(HERE, "_sheet_preview_render.py")
_BUILD_DST  = os.path.join(HERE, "_sheet_preview_build.py")

EXAMPLES = r"""
4-direction preview — quick check (NOT production · human eyeballing):
  NOTE: new runtime sprites use sheet.py at 16 dir / 128 cell. This script is *preview only*.
  4 dir(N/E/S/W) x 3 frame x 6 action = 18 col x 4 row. Default 384px -> 6912x1536.
  Output -> outputs/<name>_preview/<name>.png (does NOT pollute production assets/)

  # macOS — Mixamo-rig character FBX + Mixamo animation folder
  ./scripts/sheet_preview.py --character game-assets/characters/male.fbx --name male \
    --animations game-assets/animations/default

  # Windows PowerShell — same
  py scripts\sheet_preview.py --character game-assets\characters\male.fbx --name male `
    --animations game-assets\animations\default

  # Bigger cell (512) — with 18 cols that's 9216 > 8192, so reduce actions via --actions or keep 384
  ./scripts/sheet_preview.py --character game-assets/monsters/demonic_king.fbx \
    --name demonic_king --animations game-assets/animations/default --shading texture --actions idle,walk,attack --size 512
"""


def _ensure_preview_helpers():
    """Generate *4-direction-allowed* preview helpers from production _sheet_render.py / _sheet_build.py.

    The originals are kept as the SSOT and the helpers are regenerated on every run (so they stay
    current when the originals change); the two shared helpers are never permanently forked. The patch
    is only the *two direction-handling lines* — define the 4-direction row labels as every 4th index of
    the 16-direction set (_DIR16[::4] = [E, S, W, N]), and add 4 to the {8,16} guard in the render helper.
    """
    # -- render helper -------------------------------------------------
    with open(_RENDER_SRC, encoding="utf-8") as f:
        render_src = f.read()
    # (a) Allow 4 in the directions guard. The production guard's allowed set has drifted over time
    #     (was {8,16}, then {1,8,16}); rather than string-match one exact wording, patch whichever of
    #     the known variants is present. Each _require_replaced asserts the replacement actually fired,
    #     so if production changes the guard again this fails loudly instead of silently rejecting 4.
    render_src = _require_replaced(
        render_src, "directions guard", [
            ('if DIRECTIONS not in (1, 8, 16):\n'
             '    raise Exception(f"directions 는 1, 8, 16 만 지원합니다: {DIRECTIONS}")',
             'if DIRECTIONS not in (1, 4, 8, 16):\n'
             '    raise Exception(f"directions must be 1, 4(preview), 8, or 16: {DIRECTIONS}")'),
            ('if DIRECTIONS not in (8, 16):\n'
             '    raise Exception(f"directions 는 8 또는 16 만 지원합니다: {DIRECTIONS}")',
             'if DIRECTIONS not in (4, 8, 16):\n'
             '    raise Exception(f"directions must be 4(preview), 8, or 16: {DIRECTIONS}")'),
        ])
    # (b) Add a 4-direction branch to the DIR_LABELS definition (every 4th of 16 = [E, S, W, N]).
    #     Note DIR_AZIMUTHS is already computed generically for N directions, so only the *labels*
    #     need a 4-direction case. The production line has been both `DIR_LABELS   = ...` (aligned)
    #     and `DIR_LABELS = ...` (single space, inside an `if DIRECTIONS == 1: ... else:` block).
    render_src = _require_replaced(
        render_src, "DIR_LABELS 4-direction branch", [
            ("DIR_LABELS = DIR16_LABELS if DIRECTIONS == 16 else DIR16_LABELS[::2]",
             "DIR_LABELS = (DIR16_LABELS if DIRECTIONS == 16\n"
             "                  else DIR16_LABELS[::2] if DIRECTIONS == 8\n"
             "                  else DIR16_LABELS[::4])   # 4-direction preview = [E, S, W, N]"),
            ("DIR_LABELS   = DIR16_LABELS if DIRECTIONS == 16 else DIR16_LABELS[::2]",
             "DIR_LABELS   = (DIR16_LABELS if DIRECTIONS == 16\n"
             "                else DIR16_LABELS[::2] if DIRECTIONS == 8\n"
             "                else DIR16_LABELS[::4])   # 4-direction preview = [E, S, W, N]"),
        ])
    # (c) Let an override pass skip overwriting _measure.json so the base character's body_ratio /
    #     foot_anchor stays authoritative for compositing (cfg["skip_measure"]). The stale-frame purge
    #     is now scoped by the production helper itself via _wipe_pngs(OUT_FRAMES, ONLY_ACTIONS), which
    #     the preview drives by setting cfg["only_actions"] per pass (see main()) — no purge patch needed.
    render_src = _require_replaced(
        render_src, "skip_measure guard", [
            ("measure_body_foot()\n",
             "if not cfg.get(\"skip_measure\"):\n"
             "    measure_body_foot()\n"),
        ], count=1)
    _write_if_changed(_RENDER_DST, _PREVIEW_BANNER + render_src)

    # -- build helper --------------------------------------------------
    with open(_BUILD_SRC, encoding="utf-8") as f:
        build_src = f.read()
    build_src = _require_replaced(
        build_src, "ROWS 4-direction branch", [
            ("ROWS    = _DIR16 if _NDIR == 16 else _DIR16[::2]",
             "ROWS    = (_DIR16 if _NDIR == 16\n"
             "           else _DIR16[::2] if _NDIR == 8\n"
             "           else _DIR16[::4])   # 4-direction preview = [E, S, W, N]"),
            ("ROWS = _DIR16 if _NDIR == 16 else _DIR16[::2]",
             "ROWS = (_DIR16 if _NDIR == 16\n"
             "        else _DIR16[::2] if _NDIR == 8\n"
             "        else _DIR16[::4])   # 4-direction preview = [E, S, W, N]"),
        ])
    _write_if_changed(_BUILD_DST, _PREVIEW_BANNER + build_src)


_PREVIEW_BANNER = (
    "# AUTO-GENERATED by sheet_preview.py — DO NOT EDIT.\n"
    "# This is a copy of production _sheet_render.py / _sheet_build.py + a 4-direction(preview) patch,\n"
    "# regenerated from the originals on every sheet_preview.py run (the originals are the SSOT). Edit the originals.\n"
)


def _require_replaced(src, what, variants, count=-1):
    """Apply the first (old, new) variant found in src; hard-fail if none match.

    The preview helpers are generated by patching the *production* _sheet_render.py / _sheet_build.py
    (the SSOT) via string replacement. When production is refactored, an old exact-match target silently
    stops matching and the patch becomes a no-op — which is exactly how the 4-direction preview broke
    (production's guard drifted 8,16 -> 1,8,16 and the preview kept looking for the old wording, so 4
    stayed rejected). To make that failure loud instead of silent, we try each known wording variant in
    order and raise if the production source matches none, so a future refactor fails at generation time
    with a clear message instead of at Blender-render time with a confusing 'directions ... 만 지원합니다'.
    """
    for old, new in variants:
        if old in src:
            return src.replace(old, new, count)
    raise SystemExit(
        f"sheet_preview.py: could not patch the production render/build helper for '{what}'.\n"
        f"   The production _sheet_render.py / _sheet_build.py wording changed and no known variant\n"
        f"   matched. Update the variants list in sheet_preview.py:_ensure_preview_helpers() to the\n"
        f"   current production source. (This guard exists because a silent no-op previously made the\n"
        f"   4-direction preview reject directions=4.)")


def _write_if_changed(path, content):
    """Skip rewriting (so mtime is untouched) when the content is identical."""
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == content:
                    return
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ─────────────────────────────────────────────────────────────────────────────
#  Blender resolution — macOS + Windows.
# ─────────────────────────────────────────────────────────────────────────────
def _blender_from_registry():
    """Read the Blender install path from the Windows registry Uninstall keys and return blender.exe.

    Windows-only (winreg import). Returns None on macOS / when not found."""
    try:
        import winreg
    except ImportError:
        return None
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    cands = []
    for root, base in hives:
        try:
            base_key = winreg.OpenKey(root, base)
        except OSError:
            continue
        with base_key:
            for i in range(winreg.QueryInfoKey(base_key)[0]):
                try:
                    sub = winreg.EnumKey(base_key, i)
                    with winreg.OpenKey(base_key, sub) as k:
                        try:
                            name = winreg.QueryValueEx(k, "DisplayName")[0]
                        except OSError:
                            continue
                        if "blender" not in str(name).lower():
                            continue
                        for val in ("InstallLocation", "DisplayIcon"):
                            try:
                                raw = winreg.QueryValueEx(k, val)[0]
                            except OSError:
                                continue
                            if not raw:
                                continue
                            raw = raw.strip('"')
                            exe = (os.path.join(raw, "blender.exe")
                                   if os.path.isdir(raw) else raw)
                            if exe.lower().endswith("blender.exe") and os.path.isfile(exe):
                                cands.append(os.path.abspath(exe))
                                break
                except OSError:
                    continue
    if cands:
        return sorted(set(cands))[-1]
    return None


def _find_blender_macos(explicit):
    """Find Blender on macOS — /Applications/Blender.app + PATH (same as sheet.py)."""
    cands = [explicit or None,
             "/Applications/Blender.app/Contents/MacOS/Blender",
             shutil.which("blender")]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None


def _find_blender_windows(explicit):
    """Find blender.exe in standard Windows install locations + PATH + registry (same as sheet-win.py)."""
    for p in (explicit or None, shutil.which("blender"), shutil.which("blender.exe")):
        if p and os.path.isfile(p):
            return p
    reg = _blender_from_registry()
    if reg:
        return reg
    env = os.environ
    roots = [
        env.get("ProgramFiles", r"C:\Program Files"),
        env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.path.join(env.get("LOCALAPPDATA", ""), "Programs"),
    ]
    patterns = []
    for r in roots:
        if r:
            patterns.append(os.path.join(r, "Blender Foundation", "Blender*", "blender.exe"))
            patterns.append(os.path.join(r, "Blender Foundation", "blender.exe"))
            patterns.append(os.path.join(r, "Blender*", "blender.exe"))
    for steam in (os.path.join(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam"),
                  os.path.join(env.get("ProgramFiles", r"C:\Program Files"), "Steam")):
        patterns.append(os.path.join(steam, "steamapps", "common", "Blender", "blender.exe"))
    up = env.get("USERPROFILE", "")
    if up:
        patterns.append(os.path.join(up, "scoop", "apps", "blender", "current", "blender.exe"))
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    found = sorted({os.path.abspath(f) for f in found if os.path.isfile(f)})
    if found:
        return found[-1]
    return None


def find_blender(explicit):
    """Find Blender for the current platform (macOS: Blender.app · Windows: registry + install dirs)."""
    if IS_WINDOWS:
        exe = _find_blender_windows(explicit)
        if exe:
            return exe
        sys.exit(
            "Could not find Blender (blender.exe).\n"
            "   -> Install Blender or pass the blender.exe path directly via --blender.\n"
            '     e.g. --blender "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe"\n'
            "   Install: https://www.blender.org/download/  (or winget install BlenderFoundation.Blender)"
        )
    # macOS (and any other POSIX) path.
    exe = _find_blender_macos(explicit)
    if exe:
        return exe
    sys.exit(
        "Could not find Blender.\n"
        "   -> Install Blender.app or pass the Blender path directly via --blender.\n"
        "     e.g. --blender /Applications/Blender.app/Contents/MacOS/Blender\n"
        "   Install: https://www.blender.org/download/")


def resolve_python(explicit):
    """Resolve the Python interpreter for the build step (_sheet_preview_build.py).

    macOS prefers python3; Windows prefers python / py. Falls back to the current interpreter.
    (Only used when 'uv' is not available.)"""
    if explicit:
        return [explicit]
    if IS_WINDOWS:
        py = shutil.which("python")
        if py:
            return [py]
        pyl = shutil.which("py")
        if pyl:
            return [pyl, "-3"]
        return [sys.executable]
    # macOS / POSIX — python3 first.
    py3 = shutil.which("python3")
    if py3:
        return [py3]
    py = shutil.which("python")
    if py:
        return [py]
    return [sys.executable]


def assert_mixamo_rig(path, role):
    """Verify the model file is a Mixamo rig (exit otherwise) — same as the production sheet."""
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except Exception as e:
        sys.exit(f"Could not read {role} file: {path} ({e})")
    if b"mixamorig" not in blob:
        sys.exit(
            f"ERROR: {role} is not a Mixamo rig (bone name 'mixamorig:' not found): {path}\n"
            f"   -> sheet_preview.py only supports a *Mixamo-rig character + Mixamo animations*.\n"
            f"   -> Auto-Rig the model (or download animations) at https://www.mixamo.com and export as FBX.")


def resolve_character(path, role):
    """Validate a character model path (auto-correcting extension), check format + Mixamo rig.

    Returns the resolved absolute-able path. Used for both --character and each per-action
    --character-<action> override so they all share identical checks.
    """
    if not os.path.isfile(path):
        alt = next((path + e for e in CHAR_EXT if os.path.isfile(path + e)), None)
        if alt:
            print(f"  info: '{path}' not found -> auto-corrected extension: {alt}")
            path = alt
        else:
            sys.exit(f"{role} model not found: {path}\n"
                     f"   -> Check the path/file name (supported extensions: {'/'.join(CHAR_EXT)}).")
    ext = os.path.splitext(path)[1].lower()
    if ext not in CHAR_EXT:
        sys.exit(f"Unsupported character format: {ext or '(no extension)'} — {path}\n"
                 f"   -> Supported extensions: {'/'.join(CHAR_EXT)}")
    if ext == ".blend":
        print(f"  info: .blend character ({role}) — opened directly in Blender to render.")
    else:
        assert_mixamo_rig(path, role)
    return path


def parse_size(s):
    if "x" in s.lower():
        a, b = s.lower().split("x")
        if int(a) != int(b):
            sys.exit(f"Cell must be square (Laryen SSOT): {s}")
        return int(a)
    return int(s)


def main():
    ap = argparse.ArgumentParser(
        description="FBX/GLB -> **4-direction 3-frame PREVIEW** sprite sheet (big 384 cell · human-check only · macOS+Windows)",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True)
    ap.add_argument("--actor", "--character", dest="character", required=True,
                    help="Actor (character/monster) model (.fbx / .glb / .gltf, mesh+rig). Import branches by extension. "
                         "This is the *default* model used for every action unless a per-action override "
                         "(--character-<action>) is given.")
    # Per-action character override — when set, that one action is rendered from a *different* model
    # (its own render pass) instead of --character. Lets a preview mix e.g. a body for idle/walk and a
    # variant for attack. Each value is a model path (.fbx/.glb/.gltf) just like --character.
    for _act in DEFAULT_ACTIONS:
        ap.add_argument(f"--character-{_act}", dest=f"character_{_act}", default=None,
                        help=f"Override the model used for the '{_act}' action only "
                             f"(default = --character). Same format as --character.")
    ap.add_argument("--animations", required=True,
                    help="External Mixamo animation folder ({action}.fbx/.glb) — *required*. Matching bones -> applied directly.")
    ap.add_argument("--name", "--kind", dest="name", required=True,
                    help="Output sprite/file name (preview only — no pc/npc/mob category). "
                         "Preview output is outputs/<name>_preview/<name>.png. (--kind is a "
                         "deprecated alias kept for backward compatibility.)")
    ap.add_argument("--cell-size", "--size", dest="cell_size", default=PREVIEW_CELL_DEFAULT,
                    help=f"Cell pixel size (preview default {PREVIEW_CELL_DEFAULT} — large preview). Sum(frames)*cell <= 8192")
    ap.add_argument("--k", type=float, default=128.0,
                    help="K = target on-screen body height px. display = K/body_ratio auto-computed (preview reference)")
    ap.add_argument("--idle", type=int, help=f"idle frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    ap.add_argument("--walk", type=int, help=f"walk frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    ap.add_argument("--run", type=int, help=f"run frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    ap.add_argument("--attack", type=int, help=f"attack frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    ap.add_argument("--hit", type=int, help=f"hit frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    ap.add_argument("--death", type=int, help=f"death frame count (defaults to {PREVIEW_FRAMES_PER_ACTION})")
    # Per-action generation scale — same as sheet.py. <1 shrinks that action's model inside the cell so
    # the preview matches the framing production will bake (e.g. --scale-attack 0.8 so a swung weapon
    # fits). Unset actions fall back to the global --scale (no change). Unlike the production script,
    # the preview never *prompts* for these (it is non-interactive) — pass them to mirror the exact
    # scales you will use in the real atlas build.
    for _act in DEFAULT_ACTIONS:
        _pd = SCALE_PROMPT_DEFAULTS.get(_act)
        ap.add_argument(f"--scale-{_act}", type=float, default=None, dest=f"scale_{_act}",
                        help=f"'{_act}' action generation scale (unset = global --scale)"
                             + (f". Production suggests {_pd:g}." if _pd is not None else "")
                             + " <1 renders the model smaller in the cell (matches production framing).")
    ap.add_argument("--weapon", default=None,
                    help="Weapon model (.fbx/.glb) — when set, attach to hand bone and render together (NOTE: T-pose character).")
    ap.add_argument("--weapon-bone", default=None, help="Weapon attach bone (default mixamorig:RightHand).")
    ap.add_argument("--weapon-loc", default=None, help="Weapon position tweak 'x,y,z' (meters).")
    ap.add_argument("--weapon-rot", default=None, help="Weapon rotation tweak 'rx,ry,rz' (degrees).")
    ap.add_argument("--weapon-scale", type=float, default=None, help="Weapon scale factor.")
    ap.add_argument("--margin", type=float, default=1.3, help="auto-fit safety margin factor (increase if weapon tip is clipped).")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="Overall model (character+weapon) size factor inside the cell (default 1.0=no change). "
                         ">1 bigger · <1 smaller. Shrink (e.g. 0.9) if the model/weapon/anim is too big for the "
                         "cell, enlarge (e.g. 1.1) if too small. Unlike margin (padding), this is an intentional "
                         "scale-up/down (same as sheet.py --scale).")
    ap.add_argument("--elev", type=float, default=30.0, help="Camera elevation (2:1=30 deg)")
    ap.add_argument("--shading", choices=["eevee", "texture"], default="eevee",
                    help="Render shading. eevee=PBR 3-point lighting (default, same as sheet.py) · "
                         "texture=WORKBENCH TEXTURE (avoids rendering metal black).")
    ap.add_argument("--vivid", type=int, default=5, choices=range(1, 10), metavar="1-9",
                    help="Color intensity (contrast) + brightness strength (1-9, default 5, same as "
                         "sheet.py). 5=moderately bright/vivid, 9=max, 1=no boost. Applied via "
                         "compositor after render so previews match production coloring.")
    ap.add_argument("--render-res", type=int, default=0,
                    help="Render resolution (default max(256, size*2)). Takes precedence when set.")
    ap.add_argument("--draft", action="store_true",
                    help="Ultra-fast preview — render_res=cell(1x), AA off. Just to quickly check direction/anim matching.")
    ap.add_argument("--png-colors", type=int, default=256,
                    help="PNG color count (palette quantization). Default 256. 0=lossless RGBA.")
    ap.add_argument("--actions", default=None, help="Action order/list (col layout order). "
                    f"Default = all: {','.join(DEFAULT_ACTIONS)}. Reorders/limits columns.")
    # Preview-only convenience: render just one (or a few) actions so you don't wait for the whole set.
    #   --only attack           (one action)
    #   --only idle,attack      (a subset)
    #   --only-attack           (boolean flag; combine e.g. --only-attack --only-walk)
    # Any of these narrow the set to those actions (canonical column order preserved); they override
    # --actions when both are given.
    ap.add_argument("--only", default=None, metavar="ACTION[,ACTION...]",
                    help="Preview only these actions (e.g. --only attack · --only idle,attack). "
                         "Shortcut so you don't render every action. Overrides --actions.")
    for _act in DEFAULT_ACTIONS:
        ap.add_argument(f"--only-{_act}", dest="only_flags", action="append_const", const=_act,
                        help=f"Preview only the '{_act}' action (combine e.g. --only-attack --only-walk).")
    ap.add_argument("--outputs", default=None,
                    help="Intermediate work folder. Default outputs/<name>_preview")
    ap.add_argument("--sheet-out", default=None,
                    help="Override sprite sheet PNG output folder (preview default outputs/<name>_preview)")
    ap.add_argument("--info-out", default=None,
                    help="Override manifest/layout output folder (preview default outputs/<name>_preview)")
    ap.add_argument("--blender", default="",
                    help="Blender path (auto-detected — macOS: /Applications/Blender.app · "
                         "Windows: registry + standard install locations — if omitted)")
    ap.add_argument("--python", default="", dest="python_bin",
                    help="Build-step Python interpreter path (auto-detects python3 on macOS · python/py on Windows)")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Print full Blender/uv logs (for debugging)")
    args = ap.parse_args()

    cell = parse_size(args.cell_size)
    directions = PREVIEW_DIRECTIONS   # fixed at 4 directions — preview only

    # -- resolve which actions to render --------------------------------
    # Precedence: --only-<action> flags / --only  >  --actions  >  all (DEFAULT_ACTIONS).
    # The "only" forms are a preview convenience so you can render just one action (e.g. --only-attack)
    # instead of the whole set. Unknown action names are rejected. Column order always follows the
    # canonical DEFAULT_ACTIONS order (so a subset stays laid out consistently), except an explicit
    # --actions list is honored verbatim (it may reorder columns).
    def _valid(names, src):
        bad = [a for a in names if a not in DEFAULT_ACTIONS]
        if bad:
            sys.exit(f"Unknown action(s) in {src}: {', '.join(bad)}\n"
                     f"   -> valid actions: {', '.join(DEFAULT_ACTIONS)}")
        return names

    only = list(dict.fromkeys(args.only_flags or []))          # from --only-<action> flags (dedup)
    if args.only:                                              # from --only a,b (merge with flags)
        only += [a.strip() for a in args.only.split(",") if a.strip()]
        only = list(dict.fromkeys(only))
    if only:
        _valid(only, "--only")
        actions = [a for a in DEFAULT_ACTIONS if a in only]    # canonical order, subset
        if args.actions:
            print(f"  info: --only overrides --actions -> rendering only: {', '.join(actions)}")
    elif args.actions:
        actions = _valid([a.strip() for a in args.actions.split(",") if a.strip()], "--actions")
    else:
        actions = list(DEFAULT_ACTIONS)

    # -- input existence checks (default character) --
    args.character = resolve_character(args.character, "character (--character)")
    char_ext = os.path.splitext(args.character)[1].lower()

    # -- per-action character overrides (--character-<action>) --
    # Map every action -> the model that renders it (default = args.character). An action whose
    # --character-<action> is set is validated and routed to that model in its own render pass.
    action_character = {a: args.character for a in actions}
    for a in DEFAULT_ACTIONS:
        ov = getattr(args, f"character_{a}", None)
        if ov:
            if a not in actions:
                print(f"  warn: --character-{a} given but '{a}' is not in --actions ({', '.join(actions)}) "
                      f"-> ignored.")
                continue
            action_character[a] = resolve_character(ov, f"character (--character-{a})")
            print(f"  info: action '{a}' uses override model -> {action_character[a]}")

    # -- weapon (--weapon, optional) --
    weapon_bone = "mixamorig:RightHand"
    weapon_loc = weapon_rot = [0.0, 0.0, 0.0]
    weapon_scale, weapon_ref_height = 1.0, 0.0
    if args.weapon:
        if not os.path.isfile(args.weapon):
            alt = next((args.weapon + e for e in SUPPORTED_EXT
                        if os.path.isfile(args.weapon + e)), None)
            if alt:
                print(f"  info: '{args.weapon}' not found -> auto-corrected extension: {alt}")
                args.weapon = alt
            else:
                sys.exit(f"Weapon model not found: {args.weapon}\n   -> Check the path/file name.")
        if os.path.splitext(args.weapon)[1].lower() not in SUPPORTED_EXT:
            sys.exit(f"Unsupported weapon format: {args.weapon} (supported: {'/'.join(SUPPORTED_EXT)})")
        def _triple(s, name):
            try:
                v = [float(x) for x in s.split(",")]
                assert len(v) == 3
                return v
            except Exception:
                sys.exit(f"{name} must be 'x,y,z' format (3 numbers): {s!r}")
        prof, prof_path = {}, os.path.splitext(args.weapon)[0] + ".attach.json"
        if os.path.isfile(prof_path):
            try:
                prof = json.load(open(prof_path, encoding="utf-8"))
            except Exception as e:
                sys.exit(f"Failed to parse weapon profile JSON: {prof_path}\n   {e}")
            print(f"  info: loaded weapon profile: {prof_path}")
        else:
            print(f"  warn: no weapon profile: {prof_path} -> proceeding with defaults/CLI.")
        weapon_bone = args.weapon_bone or prof.get("bone") or "mixamorig:RightHand"
        weapon_loc = _triple(args.weapon_loc, "--weapon-loc") if args.weapon_loc is not None \
            else [float(x) for x in prof.get("loc", [0.0, 0.0, 0.0])]
        weapon_rot = _triple(args.weapon_rot, "--weapon-rot") if args.weapon_rot is not None \
            else [float(x) for x in prof.get("rot", [0.0, 0.0, 0.0])]
        weapon_scale = args.weapon_scale if args.weapon_scale is not None \
            else float(prof.get("scale", 1.0))
        weapon_ref_height = float(prof.get("ref_height", 0.0))

    # -- animation source --
    if not os.path.isdir(args.animations):
        sys.exit(f"Animation folder not found: {args.animations}")
    def anim_file(a):
        return next((os.path.join(args.animations, a + e) for e in SUPPORTED_EXT
                     if os.path.isfile(os.path.join(args.animations, a + e))), None)
    have = [a for a in actions if anim_file(a)]
    if not have:
        sys.exit(f"No {{action}}.{{fbx|glb|gltf}} found in the animation folder: {args.animations}\n"
                 f"   needed (e.g.): " + ", ".join(f"{a}.fbx" for a in actions))
    miss_act = [a for a in actions if a not in have]
    if miss_act:
        print(f"  warn: missing animations (those actions render empty frames): {', '.join(miss_act)}")
    for a in have:
        assert_mixamo_rig(anim_file(a), f"animation '{a}' ({os.path.basename(anim_file(a))})")

    # (2) frames per action — default to 3 (preview) when omitted. Override only explicitly-set actions.
    frames = {a: PREVIEW_FRAMES_PER_ACTION for a in DEFAULT_ACTIONS}
    for a in ("idle", "walk", "run", "attack", "hit", "death"):
        v = getattr(args, a)
        if v is not None:
            frames[a] = v

    # Per-action generation scale — same contract as sheet.py. The render helper
    # (_sheet_render.py -> _sheet_preview_render.py) reads cfg["action_scales"] and uses
    # ACTION_SCALES.get(action, global scale) per action, so an unset action falls back to --scale.
    action_scales = {}
    for a in actions:
        ov = getattr(args, f"scale_{a}", None)
        action_scales[a] = float(ov) if ov is not None else float(args.scale)

    if args.render_res:
        render_res = args.render_res
    elif args.draft:
        render_res = cell
    else:
        render_res = max(256, cell * 2)

    name = args.name
    # Preview output goes to outputs/<name>_preview/ so it never pollutes production assets/.
    preview_dir = os.path.abspath(args.outputs) if args.outputs \
        else os.path.abspath(os.path.join("outputs", name + "_preview"))
    outputs = preview_dir
    frames_dir = os.path.join(outputs, "frames")
    measure_path = os.path.join(outputs, "_measure.json")
    sheet_out_dir = os.path.abspath(args.sheet_out) if args.sheet_out else preview_dir
    info_out_dir = os.path.abspath(args.info_out) if args.info_out else preview_dir

    cfg_base = {
        "animations_dir": os.path.abspath(args.animations),
        "use_embedded_anim": False,
        "outputs": outputs, "name": name, "frames_dir": frames_dir,
        "measure_path": measure_path,
        "sheet_out_dir": sheet_out_dir, "info_out_dir": info_out_dir,
        "kind": name, "k": args.k,   # "kind" is only a manifest label here (preview has no category)
        "size": cell, "directions": directions,
        "frames": frames, "actions": actions,
        "loop_actions": ["idle", "walk", "run"],
        "render_res": render_res, "elev": args.elev, "margin": args.margin,
        "scale": args.scale,
        "action_scales": action_scales,
        "shading": args.shading,
        "color_level": int(args.vivid),
        "png_colors": args.png_colors,
        "draft": args.draft,
        "weapon": (os.path.abspath(args.weapon) if args.weapon else None),
        "weapon_bone": weapon_bone,
        "weapon_loc": weapon_loc,
        "weapon_rot": weapon_rot,
        "weapon_scale": weapon_scale,
        "weapon_ref_height": weapon_ref_height,
    }
    os.makedirs(outputs, exist_ok=True)
    # Build (compositing) step config carries the *full* action list so every column is laid out,
    # regardless of how rendering was split across per-action characters.
    build_cfg_path = os.path.join(outputs, "_sheet_config.json")
    json.dump(cfg_base, open(build_cfg_path, "w"), indent=2)

    # -- group actions by their (possibly overridden) character into render passes --
    # The default character renders first (its pass writes _measure.json); every other character
    # then renders only its own action(s), purging only those frames so the base pass survives.
    # Each pass gets its own _sheet_config.json so the auto-generated render helper sees the right
    # character + a scoped ACTIONS subset.
    pass_chars = [os.path.abspath(args.character)]   # default first → authoritative measure
    for a in actions:
        ca = os.path.abspath(action_character[a])
        if ca not in pass_chars:
            pass_chars.append(ca)
    render_passes = []
    for i, char in enumerate(pass_chars):
        pass_actions = [a for a in actions if os.path.abspath(action_character[a]) == char]
        if not pass_actions:
            continue   # default character may render nothing if every action is overridden
        pcfg = dict(cfg_base)
        pcfg["character"] = char
        pcfg["actions"] = pass_actions
        # Scope this pass's render + stale-frame purge to just its actions. The production helper
        # purges via _wipe_pngs(OUT_FRAMES, ONLY_ACTIONS) and renders only ONLY_ACTIONS∩ACTIONS, so
        # setting only_actions here keeps an earlier base/default-character pass's frames intact while
        # this override pass replaces only its own action(s). (Replaces the old purge_actions patch.)
        pcfg["only_actions"] = pass_actions
        pcfg["skip_measure"] = (len(render_passes) > 0)   # only the first emitted pass measures
        pcfg_path = os.path.join(outputs, f"_sheet_config_pass{i}.json")
        json.dump(pcfg, open(pcfg_path, "w"), indent=2)
        render_passes.append((char, pass_actions, pcfg_path))

    # -- generate 4-direction-allowed preview helpers from production helpers (originals untouched, refreshed each run) --
    _ensure_preview_helpers()

    # -- info output --
    total_cols = sum(frames.get(a, PREVIEW_FRAMES_PER_ACTION) for a in actions)
    sheet_w, sheet_h = total_cols * cell, directions * cell
    over = sheet_w > TEXTURE_LIMIT or sheet_h > TEXTURE_LIMIT
    sheet_png = os.path.join(sheet_out_dir, name + ".png")
    manifest_png = os.path.join(info_out_dir, name + "_manifest.json")
    print("=" * 64)
    print(f"  platform   : {'Windows' if IS_WINDOWS else ('macOS' if IS_MACOS else sys.platform)}")
    print(f"  PREVIEW mode — 4 directions (N/E/S/W) · 3 frames per action · big {cell}px cell")
    print(f"  actor      : {args.character}  (format {char_ext}, name={args.name})")
    _overrides = [(a, action_character[a]) for a in actions
                  if os.path.abspath(action_character[a]) != os.path.abspath(args.character)]
    for a, ca in _overrides:
        print(f"    override : {a:<7} -> {ca}")
    print(f"  anim folder: {args.animations}  ({', '.join(actions)})")
    if args.weapon:
        _rh = f" ref_h={weapon_ref_height}(height-relative)" if weapon_ref_height else " (no size correction)"
        print(f"  weapon     : {args.weapon} -> {weapon_bone}  "
              f"loc={weapon_loc} rot={weapon_rot} scale={weapon_scale}{_rh}")
    print(f"  sheet out  : {sheet_png}  (preview — NOT production assets/)")
    print(f"  info out   : {manifest_png} · {name}_layout.md")
    print(f"  cell size  : {cell} x {cell} px   K(target body height)={args.k:.0f}px -> display=K/body_ratio")
    print(f"  shading    : {args.shading}" + ("  (PBR 3-point lighting)" if args.shading == "eevee" else "  (WORKBENCH TEXTURE)")
          + f"   vivid={args.vivid}/9 (contrast+brightness boost)")
    print(f"  framing    : auto-fit (full model incl. weapon), margin x{args.margin}, scale x{args.scale}"
          + ("" if args.scale == 1.0 else ("  <- bigger" if args.scale > 1.0 else "  <- smaller")))
    _scale_ov = {a: s for a, s in action_scales.items() if abs(s - float(args.scale)) > 1e-9}
    if _scale_ov:
        print(f"  act scale  : "
              + "   ".join(f"{a}={s:g}" for a, s in _scale_ov.items())
              + "   (per-action generation scale — matches production framing)")
    print(f"  render res : {render_res}px  ->  Lanczos3 downsample to {cell} (premul alpha)"
          + ("   draft(1x, AA off)" if args.draft else f"   ({render_res//cell}x supersample)"))
    print(f"  frames/cell: " + "   ".join(f"{a}={frames.get(a, PREVIEW_FRAMES_PER_ACTION)}" for a in actions))
    print(f"  preview    : {total_cols} col x {directions} row = {sheet_w} x {sheet_h} px"
          + ("   WARN over 8192!" if over else "   (within 8192 OK)"))
    print("=" * 64)
    if over:
        print(f"  WARN: preview sheet {sheet_w} x {sheet_h} > {TEXTURE_LIMIT} (texture limit).")
        print("     -> Reduce action count via --actions or lower --size.")

    blender = find_blender(args.blender)
    print(f"  Blender    : {blender}")

    if not args.build_only:
        multipass = len(render_passes) > 1
        for pi, (pchar, pacts, pcfg_path) in enumerate(render_passes):
            pass_frames = directions * sum(frames.get(a, PREVIEW_FRAMES_PER_ACTION) for a in pacts)
            tag = (f"  (pass {pi + 1}/{len(render_passes)} · {os.path.basename(pchar)} "
                   f"· {', '.join(pacts)})" if multipass else "")
            print(f"\n[1/2] Blender rendering (4-direction preview){tag} ... "
                  f"({pass_frames} frames = {directions} dir × "
                  f"{sum(frames.get(a, PREVIEW_FRAMES_PER_ACTION) for a in pacts)} frames)")
            t_r0 = time.monotonic()
            proc = subprocess.Popen(
                [blender, "-b", "-P", _RENDER_DST, "--", pcfg_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
            # Concise progress: every 12 frames print percent · speed · ETA · current action.
            # --verbose prints the full Blender log instead.
            saved, errs, render_done, cur_action = 0, [], False, ""
            for line in proc.stdout:
                line = line.rstrip()
                if line.startswith("####RENDER_DONE"):
                    render_done = True
                if args.verbose:
                    print(line); continue
                if line.startswith("####ACTION "):
                    cur_action = (line.split()[1] if len(line.split()) > 1 else "")
                    print(f"   > action {line[len('####ACTION '):]} rendering ...", flush=True)
                elif line.startswith("####"):
                    print("   " + line[4:])
                elif line.startswith("Saved:"):
                    saved += 1
                    if saved % 12 == 0 or saved == pass_frames:
                        el = time.monotonic() - t_r0
                        fps = saved / el if el > 0 else 0
                        eta = (pass_frames - saved) / fps if fps > 0 else 0
                        pct = int(saved / pass_frames * 100) if pass_frames else 0
                        tail = f" · {cur_action}" if cur_action else ""
                        print(f"   ... {saved}/{pass_frames} ({pct}%) · {fps:.1f} fps · "
                              f"ETA {_fmt_dur(eta)}{tail}", flush=True)
                elif any(k in line for k in ("Error", "Traceback", "Exception", "Failed")):
                    errs.append(line)
            proc.wait()
            # Count only this pass's frames (the base pass's frames coexist in frames_dir).
            pass_pngs = ([f for f in os.listdir(frames_dir)
                          if f.endswith(".png") and f.rsplit("_", 2)[0] in pacts]
                         if os.path.isdir(frames_dir) else [])
            actual_frames = len(pass_pngs)
            _r_dt = time.monotonic() - t_r0
            if proc.returncode == 0 and not render_done and actual_frames >= pass_frames:
                print(f"   warn: RENDER_DONE marker missing but frames {actual_frames}/{pass_frames} complete -> proceeding")
                render_done = True
            if proc.returncode != 0 or not render_done:
                print("   ERROR: render failed — check input FBX / Blender log:")
                for e in errs[-20:]:
                    print("     " + e)
                if not render_done and proc.returncode == 0:
                    print(f"     (exit code 0 but no RENDER_DONE marker + frames {actual_frames}/{pass_frames} "
                          "short — suspect FBX/GLB path/format. Use --verbose for full logs)")
                sys.exit("render failed")
            print(f"   OK render done — {actual_frames} frames · {_fmt_dur(_r_dt)}"
                  + (f" · {actual_frames / _r_dt:.1f} fps" if _r_dt > 0 else ""))

    if not args.render_only:
        print("\n[2/2] Compositing preview sprite sheet ...")
        uv = shutil.which("uv")
        if uv:
            cmd = [uv, "run", "--with", "numpy", "--with", "pillow", "python", _BUILD_DST, build_cfg_path]
        else:
            cmd = resolve_python(args.python_bin) + [_BUILD_DST, build_cfg_path]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        r, ok = None, False
        for line in out.stdout.splitlines():
            if line.strip().startswith("{"):
                r = json.loads(line); ok = True
        if not ok or out.returncode != 0:
            print(out.stdout[-1000:]); print(out.stderr[-2000:]); sys.exit("sheet compositing failed")
        if r.get("total_cells", 0) == 0:
            print(f"  ERROR: 0 rendered frames — frames/ is empty ({frames_dir}).\n"
                  f"     Make the render step succeed first (check --character path).")
            sys.exit("empty sheet — render failed")
        tb = r.get("total_bytes", 0)
        pc = r.get("png_colors", 256)
        comp = f"{pc}-color quantized" if pc > 0 else "lossless"
        sw, sh = r.get("size", [0, 0])
        print(f"  OK preview sheet  ->  {r['sheet_dir']}/{r['sheet']}  {sw}x{sh}"
              + (f"   ({tb/1e6:.1f}MB, {comp})" if tb else ""))
        for a in r["actions"]:
            warn = f"   WARN side-contact {a['clip_side']}" if a["clip_side"] else ""
            print(f"     {a['name']:<7} col {a['col_start']:>2}~{a['col_end']:<2}  cells={a['cells']}{warn}")
        print(f"  body_ratio={r['body_ratio']}  ->  recommended display={r['display_recommended']}px (K={args.k:.0f})"
              f"   foot_anchor={r['foot_anchor']}")
        print(f"  manifest: {r['manifest']}")
        print(f"     layout: {r['layout_md']}")

    print("\nDone (preview).")


if __name__ == "__main__":
    main()
