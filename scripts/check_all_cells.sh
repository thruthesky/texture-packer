#!/usr/bin/env bash
# cell 잘림 배치 검사 — 여러 자산(blend/fbx/glb)을 한 번에 scale 1.0 으로 렌더·검사해 자산별
# 잘림 프로파일을 요약한다. flutter 실행 불필요(생성된 낱장 이미지만 verify_cells.py 로 검사).
# 사람 개발자가 "어떤 자산의 어떤 행동이 셀 밖으로 잘리나"를 한 명령으로 파악하는 용도.
#
# 사용:
#   bash check_all_cells.sh [kind] [glob]
#     kind : pc|mob|npc (기본 mob)
#     glob : 검사할 자산 glob (기본 game-assets/blend/*.blend). 예: 'game-assets/blend/a*.blend'
#
# 출력: 자산별 한 줄 — ✅ 정상 / ⚠️ 잘린 행동+권장 scale / ❓ 렌더 실패(애니 없음 등).
#   잘린 자산은 출력된 --scale-<action> 옵션으로 재생성(--auto-fit-scale 로 자동 조정도 가능).
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SHEET="$SCRIPT_DIR/sheet.py"
ROOT="${LARYEN_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
cd "$ROOT"

KIND="${1:-mob}"
GLOB="${2:-game-assets/blend/*.blend}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "=== cell 잘림 배치 검사 (kind=$KIND, scale 1.0, texture shading·8dir·최소 프레임) ==="
printf "%-22s %s\n" "자산" "잘림 프로파일"
printf "%-22s %s\n" "----" "------------"
n_ok=0 n_clip=0 n_err=0
for f in $GLOB; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"; name="${name%.*}"
  out="$(python3 "$SHEET" --kind "$KIND" --name "_chk_$name" --character "$f" \
    --animations default --shading texture --directions 8 \
    --idle 1 --walk 1 --attack 2 --hit 1 --death 1 --run 1 \
    --scale-idle 1 --scale-walk 1 --scale-run 1 --scale-attack 1 --scale-hit 1 --scale-death 1 \
    --render-only --outputs "$TMP/$name" < /dev/null 2>&1)"
  clip="$(echo "$out" | grep -oE 'scale-[a-z]+ [0-9.]+' | tr '\n' ' ')"
  if echo "$out" | grep -q '전 행동 정상'; then
    printf "%-22s ✅ 정상\n" "$name"; n_ok=$((n_ok + 1))
  elif [ -n "$clip" ]; then
    printf "%-22s ⚠️ --%s\n" "$name" "$clip"; n_clip=$((n_clip + 1))
  else
    printf "%-22s ❓ 렌더 실패(애니 없음/rig 불일치)\n" "$name"; n_err=$((n_err + 1))
  fi
  rm -rf "${TMP:?}/$name"
done
echo "----"
echo "정상 $n_ok · 잘림 $n_clip · 실패 $n_err"
echo "→ ⚠️ 자산은 위 --scale-<action> 옵션으로 재생성하거나 --auto-fit-scale 로 자동 조정."
