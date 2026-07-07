# 런타임 — Flutter/Flame 이 `.atlas`/`.png` 를 파싱해 게임 월드에 표시하는 법 (복구 SSOT)

packing 결과물(`assets/<pc|mob>/<name>/<name>.{png,atlas}`)이 **게임에서 어떻게 로드되고
화면에 그려지는가**. 이 문서만 보고도 런타임 로드·렌더 경로를 복구/재생성할 수 있어야 한다.
코드를 임의로 바꾸지 말고 아래 규약·소스를 그대로 따른다.

## 목차
1. [핵심 개념 — 파일에서 화면까지](#1-핵심-개념--파일에서-화면까지)
2. [의존성·경로 캐시](#2-의존성경로-캐시)
3. [atlas 감지 — AssetManifest 스캔](#3-atlas-감지--assetmanifest-스캔)
4. [atlas 로드 — TexturePackerAtlas.load](#4-atlas-로드--texturepackeratlasload)
5. [region → SpriteAnimation 테이블 빌드](#5-region--spriteanimation-테이블-빌드)
6. [행동 배율 메타 파싱 (laryen.actionScale)](#6-행동-배율-메타-파싱-laryenactionscale)
7. [컴포넌트 렌더 — size·anchor·animation](#7-컴포넌트-렌더--sizeanchoranimation)
8. [Isometric 투영 — world ↔ screen](#8-isometric-투영--world--screen)
9. [누락 atlas 처리 (placeholder + 리포트)](#9-누락-atlas-처리-placeholder--리포트)
10. [메모리 — atlas page RAM·LRU dispose](#10-메모리--atlas-page-ramlru-dispose)
11. [핵심 파일·심볼 맵](#11-핵심-파일심볼-맵)

---

## 1. 핵심 개념 — 파일에서 화면까지

```
assets/<cat>/<name>/<name>.atlas  (텍스트: region <action>_<DIR16>, xy/size/orig/offset/rotate)
assets/<cat>/<name>/<name>.png    (packed page 이미지, cat=pc|mob)
  │  ① AssetManifest 스캔 → name→cat 맵 (hasActorAtlas)
  │  ② TexturePackerAtlas.load(...) → region 별 Sprite (flame_texturepacker 가 trim/rotate 처리)
  │  ③ findSpritesByName('walk_E') → SpriteAnimation.spriteList(frames, stepTime, loop)
  │        → _table[state.index][dir16] (6 state × 16 dir)
  ▼
ActorAnimationSet  ← PlayerComponent / MobComponent(= SpriteAnimationComponent) 가 보유
  │  ④ animation = animSet.getDir16(state, facing16)   (매 상태/방향 변화마다 교체)
  │  ⑤ size = kActorDisplaySize × displayScaleFor(state), anchor = (0.5, 0.85)
  │  ⑥ position = worldToScreen(서버 world cm)          (isometric 투영)
  ▼
게임 월드(IsoHuntWorld)에 Y-sort priority 로 depth 정렬되어 렌더
```

**설계 의도**: packing 은 격자(grid)가 못 하는 *trim(투명 여백 제거) offset·90° rotate* 로
page 를 촘촘히 채운다. 런타임은 `flame_texturepacker` 가 그 offset/rotate 를 복원해 렌더하므로,
게임 코드는 region 이름(`<action>_<DIR16>`)만 알면 격자와 **drop-in 정합**(같은
`_table[state][dir16]` 구조, `directionCount=16`)으로 동작한다.

## 2. 의존성·경로 캐시

`pubspec.yaml`:
```yaml
flame: ^1.37.0
flame_texturepacker: ^5.1.1
```

경로 캐시 — 신규 packing 경로 `assets/<pc|mob>/<name>/` 는 `assets/render/` *밖*이라
game.images(prefix `assets/render/`)로 못 읽는다. 전용 캐시 2종을 쓴다
([actor_animation_set.dart:853](../../../../lib/features/game/render/actor_animation_set.dart#L853)):

```dart
/// `.atlas` 텍스트 전용 캐시(prefix 'assets/').
static final AssetsCache _atlasAssets = AssetsCache(prefix: 'assets/');
/// atlas page PNG 전용 이미지 캐시(prefix 'assets/'). LRU dispose 는 clearAtlasPage 로.
static final Images _atlasPageImages = Images(prefix: 'assets/');
```

## 3. atlas 감지 — AssetManifest 스캔

번들된 `.atlas` 를 **컴파일된 AssetManifest** 로 스캔해 `name→cat`(pc|mob) 맵을 만든다
(하드코딩 아님 → drift 없음, 메모이즈). [actor_animation_set.dart:896](../../../../lib/features/game/render/actor_animation_set.dart#L896):

```dart
static Future<Map<String, String>> _loadAtlasManifest() async {
  final m = await AssetManifest.loadFromAssetBundle(rootBundle);
  const ext = '.atlas';
  const cats = ['pc', 'mob'];
  final out = <String, String>{};
  for (final p in m.listAssets()) {
    if (!p.endsWith(ext)) continue;
    for (final cat in cats) {
      final dir = 'assets/$cat/';
      if (p.startsWith(dir)) {
        // p = assets/<cat>/<name>/<name>.atlas → name = 첫 폴더 세그먼트.
        final name = p.substring(dir.length).split('/').first;
        if (name.isNotEmpty) out[name] = cat;
        break;
      }
    }
  }
  return out;
}

static Future<bool> hasActorAtlas(String kind) async =>
    (_atlasCategories ??= await _loadAtlasManifest()).containsKey(kind);
```

🛑 그래서 **atlas 추가/교체 후 앱 재빌드 필요** — AssetManifest 는 빌드 시 번들되므로 hot
reload/restart 로는 새 atlas 가 안 잡힌다.

## 4. atlas 로드 — TexturePackerAtlas.load

[actor_animation_set.dart:976](../../../../lib/features/game/render/actor_animation_set.dart#L976):

```dart
static Future<ActorAnimationSet> loadActorAtlas(String kind) async {
  final cat = (_atlasCategories ??= await _loadAtlasManifest())[kind] ?? 'pc';
  final atlasPath = '$cat/$kind/$kind.atlas';
  final atlas = await TexturePackerAtlas.load(
    atlasPath,
    images: _atlasPageImages,   // prefix 'assets/' — 새 경로 page 로드 전용 캐시.
    assets: _atlasAssets,       // `.atlas` 텍스트 전용(prefix 'assets/').
    assetsPrefix: '',           // 패키지 prefix 연산 비활성 → 경로 해석 결정론.
    useOriginalSize: true,      // trim 프레임을 원본 box 기준으로 offset 렌더.
  );
  var scales = const <ActorState, double>{};
  try {
    scales = parseDisplayScales(await _atlasAssets.readFile(atlasPath));
  } catch (_) {/* 배율 1.0 fallback */}
  // sourceKey='<cat>/<kind>/<kind>.png' — page 는 _atlasPageImages 에 이 키로 캐시.
  return ActorAnimationSet._(_buildAtlasTable(atlas), 16, '$cat/$kind/$kind.png', scales);
}
```

- `useOriginalSize: true` 가 핵심 — packing 시 trim 된 프레임을 **원본 cell box(128) 기준**으로
  offset 렌더해, 프레임마다 잘린 여백이 달라도 앵커가 흔들리지 않는다.
- `assetsPrefix: ''` — 패키지 내부 prefix 연산을 끄고 우리 캐시(prefix 'assets/')로 경로 해석을
  결정론적으로 맞춘다.

## 5. region → SpriteAnimation 테이블 빌드

region 이름 규약 = `<action>_<DIR16>`(예 `walk_E`, `attack_SSW`), 프레임은 `index:N`.
파서가 전역 index 로 정렬하므로 `findSpritesByName` 이 순서 맞는 프레임 리스트를 준다.
[actor_animation_set.dart:1010](../../../../lib/features/game/render/actor_animation_set.dart#L1010):

```dart
/// action → (라벨, stepTime, loop). 격자 로더와 동일 값이라야 두 경로 애니 속도 정합.
static const List<(ActorState, String, double, bool)> _atlasActions = [
  (ActorState.idle,   'idle',   0.12, true),
  (ActorState.walk,   'walk',   0.08, true),
  (ActorState.attack, 'attack', 0.05, false),
  (ActorState.hit,    'hit',    0.07, false),
  (ActorState.death,  'death',  0.10, false),
  (ActorState.run,    'run',    0.05, true),
];

static List<List<SpriteAnimation?>> _buildAtlasTable(TexturePackerAtlas atlas) {
  final table = List<List<SpriteAnimation?>>.generate(
    ActorState.values.length,
    (_) => List<SpriteAnimation?>.filled(16, null),
  );
  for (var dir = 0; dir < 16; dir++) {
    final suffix = kDir16Labels[dir]; // 'E','ESE',… (region 접미사 SSOT)
    for (final (state, action, step, loop) in _atlasActions) {
      final frames = atlas.findSpritesByName('${action}_$suffix');
      if (frames.isEmpty) continue; // 누락 → null(getDir16 가 idle 로 fallback)
      table[state.index][dir] =
          SpriteAnimation.spriteList(frames, stepTime: step, loop: loop);
    }
  }
  // run 이 없는 자산(대부분 몬스터)은 run 상태를 walk 로 대체(정지 idle fallback 회피).
  for (var dir = 0; dir < 16; dir++) {
    table[ActorState.run.index][dir] ??= table[ActorState.walk.index][dir];
  }
  return table;
}
```

facing 조회 — 16dir 은 identity, 8dir sheet 는 인접 row 근사. 누락 시 idle fallback.
[actor_animation_set.dart:91](../../../../lib/features/game/render/actor_animation_set.dart#L91):

```dart
SpriteAnimation getDir16(ActorState state, int dir16) {
  final i = directionCount == 16 ? dir16 : nearest8FromDir16(dir16);
  return _table[state.index][i] ?? _table[ActorState.idle.index][i]!;
}
```

`kDir16Labels` = `['E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW','N','NNE','NE','ENE']`
(FLARE16 순서 = packing 시 row 순서와 동일 SSOT).

## 6. 행동 배율 메타 파싱 (laryen.actionScale)

packing 시 무기 잘림 방지로 그 행동만 작게 구운 값(`--scale-attack 0.8`)이 `.atlas` 헤더에
`laryen.actionScale.attack: 0.8` 로 기록된다. 런타임은 이를 읽어 **표시 배율 1/gen=1.25** 로
자동 복원해 화면 몸 크기를 행동 무관 동일하게 유지한다(과거 `game.config.dart` 수동 상수 폐지).
[actor_animation_set.dart:289](../../../../lib/features/game/render/actor_animation_set.dart#L289):

```dart
double displayScaleFor(ActorState state) => _displayScaleByState[state] ?? 1.0;

@visibleForTesting
static Map<ActorState, double> parseDisplayScales(String atlasText) {
  const prefix = 'laryen.actionScale.';
  final actionToState = <String, ActorState>{
    for (final (state, action, _, _) in _atlasActions) action: state,
  };
  final out = <ActorState, double>{};
  for (final raw in const LineSplitter().convert(atlasText)) {
    final line = raw.trim();
    if (!line.startsWith(prefix)) continue;
    final colon = line.indexOf(':');
    if (colon < 0) continue;
    final action = line.substring(prefix.length, colon).trim();
    final gen = double.tryParse(line.substring(colon + 1).trim());
    final state = actionToState[action];
    if (state == null || gen == null || gen <= 0) continue;
    out[state] = 1.0 / gen; // 생성 scale 0.8 → 표시 배율 1.25
  }
  return out;
}
```

🛑 enum index 를 배열 인덱스로 쓰지 않는다(`ActorState` 는 respawn 이 중간·run 이 끝이라 위험)
— action 이름 → state 매핑으로 찾는다.

## 7. 컴포넌트 렌더 — size·anchor·animation

`MobComponent`·`PlayerComponent` 는 **`SpriteAnimationComponent` 상속**. atlas 로 만든
`ActorAnimationSet` 을 보유하고, 상태/방향 변화마다 `animation` 을 교체한다.
[mob_component.dart:113](../../../../lib/features/game/render/mob_component.dart#L113):

```dart
MobComponent({required Vector2 position, required this.animSet, ...})
    : super(
        position: position,
        size: Vector2.all(kActorDisplaySize),  // = 128 × kActorDisplayScale
        anchor: const Anchor(0.5, 0.85),       // 발 0.85 정렬(Y-sort sortY=position.y SSOT)
      );

@override
Future<void> onLoad() async {
  await super.onLoad();
  animation = animSet.getDir16(_state, _facing);
  _applyDisplaySize(_state);                    // 행동별 배율 정합
  ActorAnimationSet.desyncPhase(this, spawnId); // 동시 전환 위상 분산(합체 착시 방지)
}

/// 행동 배율을 매 상태 변화에 적용 — 화면 몸 크기를 행동 무관 동일하게(무기 잘림 SSOT).
void _applyDisplaySize(ActorState s) {
  final want = kActorDisplaySize * animSet.displayScaleFor(s);
  if ((size.x - want).abs() > 0.01) size = Vector2.all(want);
}
```

- `kActorDisplaySize = 128.0 * kActorDisplayScale` — pc/mob/npc 모두 화면 128 로 그린다
  (texture=display 1:1, self/remote/mob 정합). [actor_animation_set.dart:33](../../../../lib/features/game/render/actor_animation_set.dart#L33).
- `anchor (0.5, 0.85)` — 스프라이트 발이 world 좌표에 오도록. Y-sort depth 는 `sortY = position.y`.
- `animation` setter 는 다른 객체 할당 시 ticker 를 `currentTime=0` 리셋 → 같은 상태로 동시
  전환된 액터가 같은 프레임을 그려 "합체"로 보임 → `desyncPhase(seed)` 로 위상 분산.

## 8. Isometric 투영 — world ↔ screen

서버 position/velocity 는 *world cartesian*(cm). 화면 배치는 isometric 투영으로 변환한다.
[iso_projection.dart](../../../../lib/features/game/render/iso_projection.dart):

```dart
Vector2 worldToScreen(Vector2 world) =>
    Vector2(world.x - world.y, (world.x + world.y) * 0.5);

/// hot path GC 차단용 in-place 변형(할당 0). 보관 호출은 worldToScreen(새 객체) 사용.
void worldToScreenInto(Vector2 world, Vector2 out) => /* out.setValues(...) */;

/// 역함수 — 두 식 연립: x=sx*0.5+sy, y=sy-sx*0.5.
Vector2 screenToWorld(Vector2 screen) =>
    Vector2(screen.x * 0.5 + screen.y, screen.y - screen.x * 0.5);
```

매 프레임 SNAP(서버 상태) 적용 시 in-place 로 컴포넌트 position 갱신
([mob_component.dart:291](../../../../lib/features/game/render/mob_component.dart#L291)):

```dart
worldToScreenInto(s.position, position); // Phase 1-D: in-place(GC 차단)
worldToScreenInto(s.velocity, velocity);
```

## 9. 누락 atlas 처리 (placeholder + 리포트)

pc/mob 는 *오직* atlas 에서만 로드된다(격자 폐기, 2026-07-01). atlas 없거나 로드 실패면 **투명
placeholder** 를 반환해 크래시/검정 화면을 막고(캐릭터만 안 보임), 그 kind 를 모아 로그로
"texture packing 필요"를 알린다. [actor_animation_set.dart:1042](../../../../lib/features/game/render/actor_animation_set.dart#L1042):

```dart
static Future<ActorAnimationSet> loadActor(Images images, String kind) async {
  if (await hasActorAtlas(kind)) {
    try {
      return await loadActorAtlas(kind);
    } catch (e) {
      print('[actor] ⚠️ 아틀라스 로드 실패 "$kind": $e — placeholder(자산 확인 필요)');
      return _missingPlaceholderSet();
    }
  }
  _reportMissingAtlas(kind);            // missingAtlasKinds 에 수집
  return _missingPlaceholderSet();      // 투명 1×1, 6state×16dir 채움
}
```

→ 안 보이는 pc/mob 은 `printMissingAtlasReport()` 목록으로 확인 후 `sheet.py --kind <cat>
--name <name>` 로 재생성(이 스킬의 packing 워크플로우).

## 10. 메모리 — atlas page RAM·LRU dispose

- 16dir × 6state 스프라이트가 atlas page 한 장(ui.Image)을 **공유** — 그 page 하나를 clear 하면
  전부 해제된다. RAM ≈ page PNG `W×H×4`(game-memory.md SSOT, 압축/화질 무관).
- LRU dispose 는 `clearAtlasPage(sourceKey)` 로 같은 kind 의 *모든 page*(멀티페이지 `<kind>2.png`
  포함)를 함께 해제한다([actor_animation_set.dart:931](../../../../lib/features/game/render/actor_animation_set.dart#L931)) — page1 만 clear 하면 page2 가 RAM 에 남는 누수 방지.
- 진단: `debugAtlasPageBytes()`(page 실측 바이트·장수), `atlasPageBytesForKey(sourceKey)`.

## 11. 핵심 파일·심볼 맵

| 파일 | 심볼 | 역할 |
|---|---|---|
| `lib/features/game/render/actor_animation_set.dart` | `loadActorAtlas` / `_buildAtlasTable` / `getDir16` | atlas 로드·테이블 빌드·방향 조회 |
| " | `_loadAtlasManifest` / `hasActorAtlas` | AssetManifest 스캔 name→cat |
| " | `parseDisplayScales` / `displayScaleFor` | laryen.actionScale 메타 → 배율 |
| " | `loadActor` / `_missingPlaceholderSet` / `missingAtlasKinds` | 누락 placeholder·리포트 |
| " | `_atlasActions` / `kDir16Labels` / `kActorDisplaySize` | 행동/방향/표시크기 SSOT |
| " | `clearAtlasPage` / `atlasPageBytesForKey` | atlas page LRU dispose·RAM 측정 |
| `lib/features/game/render/mob_component.dart` | `MobComponent`(SpriteAnimationComponent) | 몬스터 렌더·상태/방향 애니 교체 |
| `lib/features/game/render/player_component.dart` | `PlayerComponent` | self PC 렌더(동일 패턴) |
| `lib/features/game/render/remote_player_component.dart` | `RemotePlayerComponent` | 타 PC 렌더 |
| `lib/features/game/render/npc_animation_set.dart` | `NpcAnimationSet` | NPC atlas 로드(look/talk/wave) |
| `lib/features/game/render/iso_projection.dart` | `worldToScreen` / `screenToWorld` / `worldToScreenInto` | isometric 투영·역변환 |
