#!/usr/bin/env bash
# 보유 PC/몬스터 모델을 신규 파이프라인(셀256 · 행동별 별도 sheet · auto-fit · K/발anchor)으로
# 일괄 생성한다. sheet → assets/render/{characters|monsters}, 정보 → game-assets/sprites.
# 라리엔 게임(pubspec/로더)에는 적용하지 않는다 — 후속에서 일괄 적용.
#
# 사용: bash scripts/gen_all_sheets.sh   (오래 걸림 — 백그라운드 권장)
set -u
# 본 스크립트는 .claude/skills/texture-packer/scripts/ 로 이동했다. sheet.py 는 같은 폴더에,
# 프로젝트 루트(game-assets/·assets/ 기준)는 4단계 상위(scripts→texture-packer→skills→.claude→루트).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SHEET="$SCRIPT_DIR/sheet.py"
ROOT="${LARYEN_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
cd "$ROOT"
LOG=/tmp/laryen_gen_all.log
FRAMES="--idle 8 --walk 12 --run 12 --attack 12 --hit 8 --death 8"
ANIM="game-assets/animations/default"

run() {  # $1=경로 $2=kind $3=추가옵션
  echo "=================================================================="
  echo "▶ $(date '+%H:%M:%S')  $1  (kind=$2)"
  echo "=================================================================="
  "$SHEET" --character "$1" --kind "$2" $3 $FRAMES 2>&1 \
    | grep -E "▶|✓|body_ratio|행동별 sheet|MEASURE|❌|실패|완료" || true
}

echo "===== 일괄 sprite sheet 생성 시작: $(date) =====" | tee "$LOG"

# ── PC (SSOT: male/female 각 1 외형, 파일명 male*/female* — GAME-DESIGN §8.2.1.5) ──
# FBX(mixamorig)는 외부 애니메이션 폴더, GLB(내장 애니메이션)는 --animations 생략.
for f in game-assets/characters/male*.fbx game-assets/characters/female*.fbx; do
  [ -f "$f" ] && run "$f" character "--animations $ANIM" 2>&1 | tee -a "$LOG"
done
for f in game-assets/characters/male*.glb game-assets/characters/female*.glb; do
  [ -f "$f" ] && run "$f" character "" 2>&1 | tee -a "$LOG"   # GLB 내장 애니메이션
done

# ── 몬스터 (game-assets/monsters/*.fbx, mixamorig → 외부 애니메이션 폴더) ──
for m in ai_paladin ambusher_ai_gobln brute_ai_maw caster_ai_mut coward_ai_pumk \
         guardian_uriel packhunter_ai_yuku skirmisher_ai_priate trickster_ai_drake; do
  f="game-assets/monsters/$m.fbx"
  [ -f "$f" ] && run "$f" monster "--animations $ANIM" 2>&1 | tee -a "$LOG"
done

# ── 몬스터 GLB (sorceress, UE 스켈레톤 · 애니메이션 내장 없음 → 정적 폴백) ──
[ -f "game-assets/monsters/ai_mon_bone.glb" ] && \
  run "game-assets/monsters/ai_mon_bone.glb" monster "" 2>&1 | tee -a "$LOG"

echo "===== 일괄 생성 완료: $(date) =====" | tee -a "$LOG"
