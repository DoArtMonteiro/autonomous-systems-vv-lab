# Geospatial renderer research for a Tauri 2 / WebView2 replay app

Date of research: 2026-11-04. Every fact has a URL or names a local test I ran. Anything I could not confirm from a primary source is marked **UNVERIFIED**.

Two kinds of local evidence are used:

- **Registry data**: version, publish time, licence and `dist.unpackedSize` came from the npm registry JSON (`https://registry.npmjs.org/<pkg>`).
- **Package inspection**: I ran `npm pack` on the exact versions and inspected the tarballs: file sizes, `grep` for `new Function`, `eval(` and `WebAssembly`, and a Node import test with a frozen prototype. Node v24.18.0 (V8) on Windows 11 was used for the import tests.

---

## 0. Decisive findings (read first)

1. **CesiumJS 1.147 does not load under Tauri `freezePrototype: true`.** Test: in Node v24.18.0, `Object.freeze(Object.prototype)` followed by a dynamic `import()` of `Build/CesiumUnminified/index.js` (copied to `.mjs`) throws during module evaluation:
   `TypeError: Cannot assign to read only property 'toString' of object '#<Quaternion>'` (line 23626 of the unminified bundle).
   Without the freeze, the same import succeeds and exposes 1358 exports. The bundle has 6 `X.prototype.toString = …`, 30 `X.prototype.constructor = …` and 1 `X.prototype.valueOf = …` assignments. In strict-mode ES modules these hit the "override mistake": once `Object.prototype` is frozen, the inherited non-writable property blocks the assignment, and the assignment throws. Tauri documents `freezePrototype` as "Whether `Object.freeze(Object.prototype)` is run as an initialization script on every webview" (https://v2.tauri.app/reference/config/).
   - The WebView2 runtime itself was not tested. I infer the same failure because this is ECMAScript semantics and WebView2 is also V8.
   - `@cesium/engine` is built from the same source, so it is expected to fail the same way (**UNVERIFIED**, not tested separately).
   - The IIFE `Cesium.js` contains `"use strict"` 27 times and was not tested.
   - Workers are not webviews, so the freeze script should not apply inside them (inference).
   - Practical consequence: using Cesium means either `freezePrototype: false` or patching Cesium's source to use `Object.defineProperty` for those assignments.
   - Control results: three@0.187.0 and 3d-tiles-renderer@0.5.4 (core + plugins) imported cleanly under the same freeze. maplibre-gl@6.16.0 also imported cleanly, but that tests module evaluation only, not `new Map()` (map construction needs a DOM and WebGL).
2. **Every candidate needs `connect-src 'self'` (or another local scheme) in the CSP.** The current policy is `connect-src ipc: http://ipc.localhost`. Cesium loads `Assets/approximateTerrainHeights.json` and `Assets/IAU2006_XYS/*.json` through XHR (`buildModuleUrl("Assets/...")`, 2 `new XMLHttpRequest` sites). It also loads imagery through blob + `createImageBitmap`. MapLibre and 3d-tiles-renderer also use `fetch`: grep found `fetch(` in `maplibre-gl.mjs` and `maplibre-gl-worker.mjs`, and `TilesRendererBase.js:1401` in 3d-tiles-renderer has `return fetch( url, options )`. A local tile set served from the app origin therefore needs `connect-src` to allow that origin. On Windows the Tauri origin is `http://tauri.localhost`, which appears in the example response headers at https://v2.tauri.app/reference/config/.
3. **CesiumJS needs no `unsafe-eval` for its core path, but needs `'wasm-unsafe-eval'` for Draco, KTX2/Basis, meshopt, KMZ and the 3D Tiles terrain workers.** The Gaussian-splat SPZ loader would need full `'unsafe-eval'`. Details are in section 1.4.
4. **MapLibre GL JS 6.x**: `maxPitch` is documented as 0–180, and `centerClampedToGround: false` is required above 90°. Since 6.0 it ships as ESM only, and the separate CSP build was removed. With a self-hosted worker, `worker-src 'self'` is enough and `blob:` is not required.
5. **Unreal Engine**: the primary licence and EULA pages returned HTTP 403 to every fetch, so the seat terms below are **UNVERIFIED from primary**. They come from Epic's 2024 blog, seen only through search snippets, plus press coverage. In short: $1,850 per seat per year for non-game companies with more than USD 1M annual gross revenue. An older EULA PDF on Epic's CDN was readable. It confirms the 5% royalty above USD 1M lifetime revenue per product, a royalty exemption for in-house work-for-hire tools, and default anonymous usage-data collection by the engine. Cesium for Unreal itself is Apache-2.0.

---

## 1. CesiumJS

### 1.1 Version
- `cesium` **1.147.0**, published to npm 2026-11-02T20:17Z (npm registry). The GitHub release notes list 1.147 on 2026-11-02, 1.146 on 2026-10-01 and 1.145 on 2026-09-01 (https://github.com/CesiumGS/cesium/releases).
- `@cesium/engine` 26.5.0 (2026-11-02) and `@cesium/widgets` 16.3.1 (npm registry).
- 1.146 added a new `@cesium/core` package holding classes previously in `@cesium/engine` (https://github.com/CesiumGS/cesium/releases).

### 1.2 Licence
- Apache-2.0 (npm registry `license` field). The bundle header says "Licensed under the Apache License, Version 2.0 … Portions licensed separately. See https://github.com/CesiumGS/cesium/blob/main/LICENSE.md". Commercial use is permitted under Apache-2.0.

### 1.3 Offline operation and default network behaviour
Defaults found in the 1.147 bundle (`Build/CesiumUnminified/index.js`):
- `Ion.defaultAccessToken` is a hard-coded JWT, and `Ion.defaultServer = "https://api.cesium.com/"`. Base64-decoding the token's payload segment shows the `aud` claim "1.147 Release - Delete on January 1, 2027", so the default token expires.
- `ArcGisMapService.defaultAccessToken` is also hard-coded.
- `CesiumWidget` default `baseLayer` is `ImageryLayer.fromWorldImagery()`, which is ion and Bing (code at bundle line ~241210). The API reference documents the same default; `false` adds no imagery (https://cesium.com/learn/cesiumjs/ref-doc/CesiumWidget.html).
- Default `terrainProvider` is `new EllipsoidTerrainProvider(...)`, which makes no network calls (https://cesium.com/learn/cesiumjs/ref-doc/CesiumWidget.html).
- The default SkyBox (`Assets/Textures/SkyBox/tycho2t3_80_*.jpg`) and the NaturalEarthII imagery are bundled locally.

The official Offline Guide covers the same points (https://github.com/CesiumGS/cesium/blob/main/Documentation/OfflineGuide/README.md):
- The default imagery reaches `api.cesium.com` and `dev.virtualearth.net`. Use a local provider instead, for example `TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII"))`.
- Disable the geocoder (ion) and the base-layer picker. Both are Viewer widgets, so they do not apply to a `CesiumWidget`-only setup.
- The guide warns that `file://` is treated as cross-origin. That warning does not apply to an app served from `http://tauri.localhost`.

Self-hosted terrain options in the bundle:
- `CesiumTerrainProvider.fromUrl` reads quantized-mesh (`layer.json`).
- `CustomHeightmapTerrainProvider` accepts a heightmap callback.

Required settings for offline use: `baseLayer: false` (or a local TMS/XYZ `ImageryLayer`), a local terrain provider, and no use of `Ion*` classes.

### 1.4 CSP requirements (static analysis of 1.147)

| Feature / module | Mechanism found | CSP needed |
|---|---|---|
| Core engine, CesiumWidget, quantized-mesh and heightmap terrain workers (`createVerticesFromQuantizedTerrainMesh`, `upsampleQuantizedTerrainMesh`) | Plain JS. No `new Function` or `eval` in these workers | `script-src 'self'` |
| Web workers (`TaskProcessor.createWorker`) | Same-origin URL creates a module worker from `Workers/<id>.js` with `type: "module"`. A **blob:** worker (`import "<url>"`) is created only when the worker URL is cross-origin | `worker-src` falls back to `child-src`, then `script-src`, then `default-src` (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/worker-src), so `'self'` is enough when served same-origin |
| Draco (`decodeDraco`, `decodeI3S` workers, `ThirdParty/draco_decoder.wasm`) | `WebAssembly.instantiate`. No JS fallback configured | `'wasm-unsafe-eval'` |
| KTX2/Basis (`transcodeKTX2` worker, `basis_transcoder.wasm`) | wasm. Embind code in this worker has no `new Function` (grep) | `'wasm-unsafe-eval'` |
| EXT_meshopt_compression (main thread, inline wasm bytes) | `WebAssembly.instantiate` on the main thread. Optional blob worker only if `MeshoptDecoder.useWorkers()` is called | `'wasm-unsafe-eval'` (plus `blob:` in worker-src only if useWorkers) |
| Cesium 3D Tiles terrain (`createVerticesFromCesium3DTilesTerrain`, `upsampleVerticesFromCesium3DTilesTerrain`) | Uses the meshoptimizer chunk with wasm | `'wasm-unsafe-eval'` |
| Gaussian splats (`gaussianSplatSorter`, `wasm_splats_bg.wasm`) and the SPZ loader (`@spz-loader/core`, main thread) | wasm. The SPZ embind glue calls `new Function(...)` (2 sites) | `'wasm-unsafe-eval'`, and **`'unsafe-eval'`** for SPZ |
| KMZ (`zip-module.wasm`, `ThirdParty/Workers/zip-web-worker.js`) | wasm | `'wasm-unsafe-eval'` |
| Knockout 3.5.1 (bundled in the combined `index.js` / `Cesium.js` via `packages/widgets`) | `new Function("$context","$element",…)` in `parseBindingsString`, plus a `new Function("return "+…)` JSON fallback used only when `JSON.parse` is missing | Only when Knockout bindings are evaluated (Viewer widgets). Importing `@cesium/engine` drops Knockout altogether |

CSP semantics: without `'wasm-unsafe-eval'` in `script-src`, "WebAssembly is blocked from loading and executing on the page". `'unsafe-eval'` covers both eval and wasm (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src).

History:
- The old RequireJS worker bootstrap `eval` issue, "Replace use of eval()", was closed by PR #11400 on 2023-09-01 (https://github.com/CesiumGS/cesium/issues/9024).
- Older forum reports say Knockout's eval breaks strict CSP even without widgets, and Cesium staff pointed to `@cesium/engine` as the widget-less build (https://community.cesium.com/t/using-cesium-with-csp-settings/12663).
- In 1.147, both Knockout `new Function` sites are inside functions that only binding evaluation calls (static reading). **UNVERIFIED at runtime**: I did not run `CesiumWidget` from the combined bundle under the app CSP. Use `@cesium/engine` to remove the question.

`freezePrototype`: **fails**, see section 0 item 1.

`img-src`: the existing policy allows `'self' data: blob:`, which covers Cesium's blob-based image decode.

### 1.5 Sizes (measured from the `cesium@1.147.0` tarball)
- npm unpacked: **80.2 MB** (`cesium`). `@cesium/engine` 27.3 MB, `@cesium/widgets` 1.17 MB (npm registry).
- `Build/Cesium` (minified, deployable): **23 MB total**.
  - `index.js` (ESM, includes widgets and Knockout): 4.83 MB, **1.34 MB gzip**.
  - `Cesium.js` (IIFE): 6.10 MB.
  - `Workers/`: 1.2 MB.
  - `ThirdParty/`: 1.1 MB. Contains `basis_transcoder.wasm` 492 KB, `draco_decoder.wasm` 280 KB, `zip-module.wasm` 56 KB and `wasm_splats_bg.wasm` 28 KB.
  - `Assets/`: 4.7 MB. Of that, `IAU2006_XYS` is 1.8 MB, `Textures` 2.6 MB (SkyBox 864 KB, NaturalEarthII 540 KB, maki 505 KB, LensFlare 304 KB, waterNormals 288 KB) and `approximateTerrainHeights.json` 296 KB.
  - `Widgets/`: 652 KB.
- `Build/CesiumUnminified`: 47 MB.
- An engine-only bundle size after tree-shaking depends on the bundler: **UNVERIFIED**.
- GPU/RAM footprint: no official figure found (**UNVERIFIED**).

### 1.6 Precision and features
- Precision: Cesium uses relative-to-center (RTC) rendering. The CESIUM_RTC glTF extension describes positions relative to a centre, with a model-view matrix computed in double precision on the CPU (https://github.com/KhronosGroup/glTF/blob/main/extensions/1.0/Vendor/CESIUM_RTC/README.md, path checked with HTTP 200 on raw.githubusercontent.com; it cites the Cesium "Precisions, Precisions" article as the origin). A secondary write-up compares RTC and RTE (https://reearth-engineering.pages.dev/posts/high-precision-rendering-en). Cesium's GPU relative-to-eye emulation is not documented in a primary page I fetched (**UNVERIFIED** detail).
- Camera: Cesium allows free 6-DoF camera movement. I found no pitch cap in the docs, but this was not fetched explicitly (**UNVERIFIED**).
- CesiumWidget options include `shadows` (default `false`), `terrainShadows` (default `ShadowMode.RECEIVE_ONLY`), `skyBox`, `skyAtmosphere` (on with the default ellipsoid) and `requestRenderMode` (https://cesium.com/learn/cesiumjs/ref-doc/CesiumWidget.html). Globe, 3D Tiles, glTF (Model) and quantized-mesh terrain are core engine features (classes present in the bundle).

### 1.7 Three.js integration
- There is no maintained official Cesium + Three.js overlay. Older shared-camera community examples exist, but I did not verify their maturity (**UNVERIFIED**). The practical path is to rebuild the vehicle in Cesium primitives or glTF `Model`. A second WebGL canvas with camera sync is the alternative (**UNVERIFIED** maturity).

---

## 2. MapLibre GL JS (with a Three.js custom layer)

### 2.1 Version
- `maplibre-gl` **6.16.0**, published 2026-10-25 (npm registry; https://github.com/maplibre/maplibre-gl-js/releases lists v6.16.0 on 25 Oct, v6.15.0 on 18 Oct and v6.14.0 on 11 Oct). 6.0.0 was published 2026-07-22 (npm registry).

### 2.2 Licence
- BSD-3-Clause (npm registry). Commercial use is permitted.

### 2.3 Offline operation
- No token is required. Styles and sources are URLs you supply. Examples exist for "Add 3D terrain from quantized-mesh tiles", "3D Terrain", "PMTiles source and protocol" and `addProtocol` (https://maplibre.org/maplibre-gl-js/docs/examples/). `transformRequest` is "A callback run before the Map makes a request for an external URL" (https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapOptions/).
- The worker contains one `globalThis.eval(n)`, reached only when a non-`.mjs`, non-module external script is loaded into the workers (the RTL text plugin path, `fetch` + `eval`). Avoid loading such scripts.

### 2.4 CSP and freezePrototype
- v6 is ESM only: "The UMD bundle, separate CSP build, and CommonJS entry are gone". The worker file is `maplibre-gl-worker.mjs`. Bundlers need `setWorkerUrl()` (https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/).
- CSP: a cross-origin CDN load needs `worker-src 'self' blob:` and `img-src data: blob: 'self'`. With a self-hosted worker, `worker-src 'self'` is enough (same page).
- No `WebAssembly` and no `new Function` in the 6.16.0 bundles (grep of `dist/*.mjs`), so `'wasm-unsafe-eval'` is not needed.
- WebGL2 is required, because WebGL1 support was removed in v6 (migration guide).
- freezePrototype: the module imports cleanly under a frozen `Object.prototype` in Node, but map construction was not tested (**UNVERIFIED**).

### 2.5 Sizes (6.16.0 tarball)
- npm unpacked 29.0 MB, mostly source maps and the dev build. `maplibre-gl.mjs` is 1.11 MB (295 KB gzip), `maplibre-gl-worker.mjs` 519 KB (147 KB gzip) and `maplibre-gl.css` 72 KB.
- GPU/RAM footprint: **UNVERIFIED**.

### 2.6 Camera, precision and features
- `maxPitch`: "The maximum pitch of the map (0-180)", default 60. `minPitch` is also 0–180 (https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapOptions/).
- `centerClampedToGround` defaults to `true`. The docs say it must be `false` to keep the camera above ground when pitch exceeds 90° (same page).
- The initial `pitch` option is documented as 0–85 with "Values greater than 60 degrees are experimental and may result in rendering issues" (same page). The docs contradict each other here, so test it.
- `roll` and `elevation` options exist (same page).
- Looking up at a vehicle from ground level therefore needs a pitch above 90° with `centerClampedToGround: false`. Rendering quality at such pitches: **UNVERIFIED**.
- Globe and atmosphere: examples "Display a globe with an atmosphere", "Sky, Fog, Terrain" and "Add a simple custom layer on a globe" (https://maplibre.org/maplibre-gl-js/docs/examples/).
- Sun lighting and shadows: MapLibre has no shadow-mapped sun or terrain shadows in its docs. Hillshade is a raster layer ("Add a hillshade layer", same index). Real shadows would have to come from Three.js inside the custom layer (**UNVERIFIED** that this works well with terrain).
- 3D Tiles: through Three.js plus 3d-tiles-renderer ("Add 3D Tiles, 3D objects and models using Three.js", "Raycast 3D Tiles using Three.js" in the same index). There is no native 3D Tiles support.
- Precision: custom layers receive a Mercator-space matrix. Float32 jitter at metre or millimetre scale needs a camera-relative or local-origin model matrix. No primary MapLibre page on this was found (**UNVERIFIED**). The specific Three.js example page returned 404 at `/docs/examples/add-a-3d-model-using-threejs/`.

### 2.7 Three.js integration
- Custom layers share the WebGL context, and an official example uses Three.js (examples index). Maturity: official examples, but you own the shared GL state and the depth interplay with terrain ("Add custom layers that follow the terrain" example exists).

---

## 3. NASA-AMMOS `3d-tiles-renderer` (Three.js native)

- Version **0.5.4**, published 2026-11-03 (npm registry; https://github.com/NASA-AMMOS/3DTilesRendererJS/releases). 0.5.3 was released on 18 Sep.
- Licence Apache-2.0 (npm registry).
- Peer dependency `three >=0.167.0`. Optional peers: Babylon.js, PlayCanvas, R3F (package.json in the tarball). Runtime dependencies: `@mapbox/vector-tile`, `pbf`, `pmtiles`.
- Plugins (from `src/three/plugins/API.md` in the 0.5.4 tarball):
  - `QuantizedMeshPlugin`: "adds support for the Cesium quantized-mesh terrain format. Fetches the `layer.json` descriptor from the tileset root and dynamically generates 3D Tiles tile content". It takes a URL, so a local source works without ion (inference from the API; `CesiumIonAuthPlugin` is a separate opt-in plugin).
  - `ImageOverlayPlugin` with `XYZTilesOverlay`, `TMSTilesOverlay`, `WMTSTilesOverlay`, `WMSTilesOverlay`, `PMTilesOverlay`, `GeoJSONOverlay` and `MVTOverlay`.
  - `GLTFExtensionsPlugin`, `GLTFCesiumRTCExtension`, `ReorientationPlugin`, `GeneratedSurfacePlugin` and `TileCompressionPlugin`.
  - The 0.5.3 release notes mention `GlobeControls` and image-overlay draping work (releases page).
- CSP: Draco, KTX2 and meshopt decoding go through Three.js loaders, which you supply through `GLTFExtensionsPlugin`. Each loader needs `'wasm-unsafe-eval'` only if you enable it (Three's standard loaders; not separately verified).
- freezePrototype: `3d-tiles-renderer` and `3d-tiles-renderer/plugins` imported cleanly under a frozen `Object.prototype` (Node test), and so did three@0.187.0.
- Size: unpacked 3.75 MB, `build/` 2.4 MB (tarball).
- Precision: tiles are rendered in the ECEF frame or reoriented. `ReorientationPlugin` re-centres the tileset at the local origin, which suits a local ENU scene (plugin name in API.md; behaviour summary is an inference, **UNVERIFIED** in detail).
- Atmosphere and sun shadows: not built in. They would come from Three.js (for example shadow maps; atmosphere add-ons such as `@takram/three-atmosphere` were not researched, **UNVERIFIED**).
- This is the most direct reuse path for existing Three.js code, because the app keeps its own scene, camera and renderer.

---

## 4. Other options (brief)

| Library | Latest (npm) | Published | Licence | Unpacked | Notes |
|---|---|---|---|---|---|
| deck.gl | 9.4.1 | 2026-10-28 | MIT | 6.5 MB (`@deck.gl/core` 8.5 MB) | Features not researched (**UNVERIFIED**) |
| iTowns | 2.46.0 (`latest` tag) | 2025-10-03 | CECILL-B OR MIT | 28.4 MB | Three.js based. Registry `time.modified` is 2026-11-03, which suggests a newer prerelease tag (**UNVERIFIED**) |
| Babylon.js `@babylonjs/core` | 9.33.2 | 2026-11-02 | Apache-2.0 | 73.4 MB | 3d-tiles-renderer has Babylon bindings (peer dependency `@babylonjs/core >=8.0.0`) |
| three | 0.187.0 | 2026-10-30 | MIT | 21.0 MB | Imports cleanly under freezePrototype |

All rows come from the npm registry JSON.

---

## 5. Cesium for Unreal / Unreal Engine 5

### 5.1 Versions
- Cesium for Unreal **v2.31.0**. The release header says 29 Oct, while the changelog heading says 2026-11-02. It supports UE **5.6, 5.7 and 5.8** on Windows, Linux, macOS, Android and iOS (https://github.com/CesiumGS/cesium-unreal/releases). The current UE version was not fetched directly; 5.8 is the newest the plugin lists (indirect).

### 5.2 Licences
- Cesium for Unreal: Apache License 2.0 (https://github.com/CesiumGS/cesium-unreal/blob/main/LICENSE).
- Unreal Engine: https://www.unrealengine.com/en-US/license and https://www.unrealengine.com/en-US/eula/unreal returned **HTTP 403** to both WebFetch and curl, so the terms below are **UNVERIFIED from primary** (search snippets and press only):
  - $1,850 per seat per year for companies with more than USD 1M annual gross revenue that are not making games. Companies under USD 1M, students, educators and hobbyists are exempt. The model started with UE 5.4. Sources: Epic blog via search snippet (https://www.unrealengine.com/en-US/blog/we-are-updating-unreal-engine-twinmotion-and-realitycapture-pricing-in-late-april) and https://www.engadget.com/epic-will-charge-non-game-developers-1850-per-seat-to-use-unreal-engine-162015997.html.
  - Per the Epic blog snippet, non-game applications licensed to third parties that ship UE runtime code pay royalties like games. A EULA snippet says the seat requirement does not apply if the corporate group earned less than USD 1M over the last 12 months (**UNVERIFIED**, snippet only).
  - Primary text, older EULA: I downloaded and read the PDF at https://cdn1.epicgames.com/eulatracking-download/ue_games/en/v1/r4/cf33c801ba52b566dcf201a862da65a9.pdf ("Unreal® Engine End User License Agreement For Publishing", revision r4). It predates the seat model and contains no seat clause. It states:
    - §5: "a royalty equal to 5% of all worldwide gross revenue actually attributable to each Product", with no royalty on "The first $1,000,000 in lifetime gross revenue for each Product".
    - Also royalty-free: "Consulting fees or work-for-hire fees which are non-recoupable for services performed using the Licensed Technology (e.g., … a contractor-developed in-house training simulator)", and revenue from Location-Based Experiences.
    - §12 requires a credits notice: "[Product name] uses the Unreal® Engine…".
    - §13: by default the engine "will collect and send to Epic anonymous hardware and usage data from end users of Products" unless you modify the engine code to turn it off. This matters for an offline, privacy-strict tool.
    - §1(B)(ii) forbids combining with GPL, LGPL (except dynamic linking) or CC BY-SA content.
    - The current EULA revision may differ (**UNVERIFIED**). A second PDF, v15 at https://cdn2.unrealengine.com/Unreal+Engine/faq/UnrealEngineEULA_for_Publishing_v15-b9955ec2954f0e09fade11b2d9acecfc65cb6ab1.pdf, was downloaded (HTTP 200) but not read.
  - A 2026 Epic blog snippet says that from 2026-05-27 Unreal Subscriptions no longer include Twinmotion and RealityScan (**UNVERIFIED**, snippet only).

### 5.3 Offline
- Cesium for Unreal can load a 3D Tiles tileset "From URL" instead of ion, raster overlays from TMS, and quantized-mesh terrain from a `layer.json` URL (community forum answers, not official docs: https://community.cesium.com/t/using-3d-tiles-besides-cesium-ion/15398, https://community.cesium.com/t/terrain-without-cesium-ion/24263). **UNVERIFIED** against official docs.

### 5.4 Integration with a WebView2 app
- Pixel Streaming streams frames and audio over WebRTC, using a signalling server, matchmaker and SFU that are hosted separately on GitHub (https://dev.epicgames.com/documentation/en-us/unreal-engine/pixel-streaming-in-unreal-engine).
- Encoding requires NVIDIA NVENC, AMD AMF or Apple VideoToolbox. H.264 encoding happens on the GPU, AV1 needs NVIDIA Ada or newer, and VP8/VP9 run on the CPU (https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-pixel-streaming-reference, via search summary).
- Same-machine embedding is not addressed by the docs. The architecture means running a separate UE process plus a signalling server, with WebRTC into the WebView. Alternatively, run a separate native window or process controlled over IPC (**UNVERIFIED** as a supported pattern).
- Packaged size: there is no official figure. Community reports for a blank Shipping Windows build range from about 200 to 320 MB (UE 5.3: ~321 MB default, ~211 MB trimmed; https://cobracode.notion.site/How-to-reduce-Package-Size-for-Unreal-Engine-Game-Builds-7993544e050041f9800512acd3500cfc; https://forums.unrealengine.com/t/1950640). **UNVERIFIED** for UE 5.6–5.8, and Cesium for Unreal adds to this.
- GPU, from Epic's hardware specification page (https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine). These figures are for the editor and development machine; the page gives no runtime minimum.
  - Recommended: a DirectX 12 GPU, 8 GB or more VRAM, 32 GB RAM.
  - Lumen needs DX12 with SM6 on an RTX 2000, RX 6000 or Arc A series GPU or newer.
  - Nanite and Virtual Shadow Maps need DX12 with SM6.6 atomics.

---

## 6. Data sources

### 6.1 Copernicus DEM GLO-30
- Licence: "Licence for the use of the Copernicus WorldDEM-30", free of charge (Art. 5). It grants reproduction, distribution, communication to the public, and adaptation or combination (Art. 4) (https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf).
- Required notices (Art. 6), quoted from the PDF:
  - Unmodified: "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved."
  - Modified: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved".
  - Liability sentence required when redistributing: "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30".
  - You must not imply endorsement (Art. 6(d)), and subsequent users must be bound by the same obligations (Art. 6(e)).
- Datums: vertical "EGM2008 (EPSG 3855)", horizontal "WGS84-G1150 (EPSG 4326)". It is a DSM, not a DTM, so it includes buildings and vegetation. Release 2023_1 opened the previously restricted Armenia, Azerbaijan and Moldova tiles (https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).
- AWS: bucket `copernicus-dem-30m` (GLO-30) and `copernicus-dem-90m`, region `eu-central-1`, Cloud Optimized GeoTIFF (https://registry.opendata.aws/copernicus-dem/, https://copernicus-dem-30m.s3.amazonaws.com/readme.html).
- Tile naming: the readme template is `Copernicus_DSM_COG_[resolution]_[northing]_[easting]_DEM/`. For GLO-30 the resolution token is `10`. I verified this with an anonymous S3 listing and a `HEAD` request (HTTP 200) on `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N38_00_W009_00_DEM/Copernicus_DSM_COG_10_N38_00_W009_00_DEM.tif`. Auxiliary files live under `AUXFILES/` (`_EDM`, `_FLM`, `_HEM`, `_ACM.kml`).

### 6.2 Sentinel-2 L2A
- Legal notice (European Commission), quoted from https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice:
  - Free, full and open access, including reproduction, distribution, communication to the public, and adaptation or combination.
  - Required notice: "'Copernicus Sentinel data [Year]' for Sentinel data". If modified: "'Contains modified Copernicus Sentinel data [Year]' for Sentinel data". Users waive claims for damages.
- Keyless STAC: `https://earth-search.aws.element84.com/v1`, collection `sentinel-2-l2a`. I queried it live on 2026-11-04 and it returned item `S2B_29SMC_20261102_0_L2A`.
  - The collection `license` field is `proprietary`, with a license link to the Sentinel Data Legal Notice. Providers: ESA, Sinergise, AWS, Element 84.
  - COG asset keys: `visual` (`…/TCI.tif`), `red` (`B04.tif`), `green` (`B03.tif`), `blue` (`B02.tif`), `nir`, `nir08`, `nir09`, `rededge1`–`rededge3`, `swir16`, `swir22`, `coastal`, `aot`, `wvp`, `scl` and `thumbnail` (`preview.jpg`), plus `*-jp2` variants.
  - Hrefs point to `https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/...`.

### 6.3 USGS 3DEP and NAIP
- USGS: "USGS-authored or produced data and information are considered to be in the U.S. Public Domain". Suggested credit: "U.S. Geological Survey" (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits).
- 3DEP: "All 3DEP products are available, free of charge and without use restrictions". Products include 1/3 arc-second (~10 m) and 1 m DEMs through The National Map (https://www.usgs.gov/3d-elevation-program/about-3dep-products-services).
- 3DEP lidar on AWS: `usgs-lidar-public` (EPT, us-west-2), licensed "US Government Public Domain" (https://registry.opendata.aws/usgs-lidar/).
- The 3DEP vertical datum (NAVD88) and the DEM S3 bucket were not confirmed (**UNVERIFIED**).
- NAIP on AWS: licence "Public Domain with Attribution". Buckets `naip-analytic`, `naip-source` and `naip-visualization` in us-west-2 are all **Requester Pays**. Resolution 30–100 cm (https://registry.opendata.aws/naip/).
- A USDA hub document says USDA aerial imagery is public domain, but I found no primary statement covering acquisitions after 2019, a period when FSA considered licensing (search summary; **UNVERIFIED** for recent years).
- Coverage is the USA only.

### 6.4 EOX Sentinel-2 cloudless
- Licence summary (https://cloudless.eox.at/documentation/license):
  - Non-commercial use falls under "the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License".
  - Commercial use requires the paid "EOX Commercial Attribution-RestrictedUse 1.2 License". Sub-licensing and resale need a separate agreement.
  - Attribution: "EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data "year")". This unified wording applies from June 2026.
  - **Non-commercial only unless licensed.** A per-year table (for example whether the 2016 release is CC BY 4.0) was not on the page (**UNVERIFIED**).

### 6.5 OpenStreetMap tile servers
- `tile.openstreetmap.org` forbids bulk downloading and prefetching, including "Preloading entire towns/regions or multiple zoom stacks 'just in case'". It states: "Offline use is not permitted on `tile.openstreetmap.org`". Attribution must be clearly visible (https://operations.osmfoundation.org/policies/tiles/).
- For offline use, render your own tiles from OSM data (ODbL) or use PMTiles builds. The terms of those alternatives were not researched.

---

## 7. Summary matrix

| Criterion | CesiumJS 1.147 | MapLibre 6.16 + Three | 3d-tiles-renderer 0.5.4 + Three | UE5 + Cesium for Unreal |
|---|---|---|---|---|
| Licence | Apache-2.0 | BSD-3 | Apache-2.0 (+ three MIT) | UE EULA: 5% royalty over USD 1M per product (older EULA PDF read); seat fee **UNVERIFIED** from primary; plugin Apache-2.0 |
| Offline, no token | Yes, after overriding `baseLayer` and not using Ion | Yes | Yes | Yes per forum (**UNVERIFIED** official) |
| `unsafe-eval` | No (core); yes for SPZ splats | No | No (core) | n/a |
| `wasm-unsafe-eval` | For Draco, KTX2, meshopt, 3D Tiles terrain, KMZ | No | Only if Draco/KTX2/meshopt loaders are enabled | n/a |
| `worker-src` | `'self'` (module workers) | `'self'` (self-hosted worker) | none required by core (**UNVERIFIED**) | n/a |
| `connect-src 'self'` needed | Yes | Yes | Yes | n/a |
| freezePrototype | **Fails at import** (Node test) | Imports OK; map construction untested | Imports OK | n/a |
| Deploy size | 23 MB `Build/Cesium` (4.8 MB JS, 1.34 MB gz) | ~1.7 MB JS + CSS (1.11 + 0.52 + 0.07 MB) | 2.4 MB build + three | ~200–320 MB blank (**UNVERIFIED**) + plugin |
| Camera looking up from ground | Free camera | Pitch up to 180 with `centerClampedToGround:false`; quality at >90° **UNVERIFIED** | Free (Three camera) | Free |
| Sun shadows / terrain shadows | Built in (`shadows`, `terrainShadows`) | No (hillshade only) | Via Three.js | Built in |
| Atmosphere / globe | Built in | Globe + atmosphere + sky | Not built in | Built in |
| 3D Tiles / glTF | Native | Via Three + 3d-tiles-renderer | Native | Native |
| Reuse of existing Three.js scene | Poor (separate engine) | Good (custom layer, shared GL) | Best (same scene) | None |
