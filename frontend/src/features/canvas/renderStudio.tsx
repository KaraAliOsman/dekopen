import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";

import type { PlanGeometry } from "../../api/generated/models";
import type { ProductJson } from "./productEditing";
import { buildScene3D, type Scene3D, type Solid3D } from "./Product3DScene";
import { leafPose } from "./leafPose";
import { solidToGeometry } from "./scene3dGeometry";
import { foilGrainTexture, runLength, solidMaterial } from "./materials3d";
import type { MemberGeometry } from "./members";
import { webglAvailable } from "./webglAvailable";

/** §05-F commercial renderer — the same ProductModel scene the orbit view
 * shows, rendered offscreen under studio lighting to a PNG data URL for
 * project cards, quotation positions, portal and AI alternatives. One
 * shared WebGL context serves every thumbnail; the scene disposes its
 * geometries after each render. No geometry is ever synthesized for the
 * render that the editor didn't already declare. */

export type StudioOptions = {
  width?: number;
  height?: number;
  /** Interior/exterior face — matches the orbit view's inside toggle. */
  inside?: boolean;
  /** P19 — the exported render can pose the leaves exactly like the orbit
   * view: the same `leafPose` math drives both, so a render never shows a
   * pose the scene couldn't produce (portal/DOC-01 same camera+material). */
  pose?: "closed" | "open" | "tilt";
};

const RENDER_W = 640;
const RENDER_H = 480;

let renderer: THREE.WebGLRenderer | null | "unavailable" = null;

function getRenderer(): THREE.WebGLRenderer | null {
  if (renderer === "unavailable") return null;
  if (renderer) return renderer;
  if (typeof document === "undefined") return null;
  if (!webglAvailable()) {
    renderer = "unavailable";
    return null;
  }
  try {
    const canvas = document.createElement("canvas");
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
  } catch {
    renderer = "unavailable";
  }
  return renderer instanceof THREE.WebGLRenderer ? renderer : null;
}

function tokenColor(token: string, fallback: string): string {
  const value =
    typeof window === "undefined"
      ? ""
      : getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return value || fallback;
}

function solidMesh(solid: Solid3D, inside: boolean): THREE.Mesh | null {
  const material = solidMaterial(solid, "commercial", inside ? "interior" : "exterior");
  const mat = new THREE.MeshStandardMaterial({
    color: tokenColor(material.colorToken, material.colorFallback),
    roughness: material.roughness,
    metalness: material.metalness,
    transparent: material.transparent,
    opacity: material.opacity,
    depthWrite: !material.glass,
    // Foil members keep their grain in the commercial render too — the
    // same texture map the orbit view applies (§7 of the fidelity pass).
    map: material.grain ? foilGrainTexture(material.grain, runLength(solid)) : null,
  });
  if (solid.kind === "box") {
    const geo = new THREE.BoxGeometry(solid.size[0], solid.size[1], solid.size[2]);
    geo.translate(solid.center[0], solid.center[1], solid.center[2]);
    return new THREE.Mesh(geo, mat);
  }
  const geo = solidToGeometry(solid);
  return geo ? new THREE.Mesh(geo, mat) : null;
}

function buildThreeScene(
  scene: Scene3D,
  inside: boolean,
  pose: "closed" | "open" | "tilt",
): THREE.Group {
  const root = new THREE.Group();
  const inner = new THREE.Group();
  inner.position.set(-scene.center[0], -scene.center[1], -scene.center[2]);
  for (const module of scene.modules) {
    const group = new THREE.Group();
    group.position.set(...module.position);
    group.rotation.y = module.rotationY;
    // Leaf solids render inside the same chained-pivot hierarchy the
    // orbit view animates — the exported PNG shows the pose the scene
    // actually performs.
    const leafSolids = new Map<string, Solid3D[]>();
    for (const solid of module.solids) {
      if (!solid.leafId) continue;
      const list = leafSolids.get(solid.leafId) ?? [];
      list.push(solid);
      leafSolids.set(solid.leafId, list);
    }
    for (const motion of module.leaves) {
      const leaf = leafPose(motion, pose === "closed" ? 0 : 1, pose === "tilt");
      const tiltGroup = new THREE.Group();
      tiltGroup.position.set(...leaf.tiltPos);
      tiltGroup.rotation.x = leaf.tiltRotX;
      const swingGroup = new THREE.Group();
      swingGroup.position.set(...leaf.swingPos);
      swingGroup.rotation.y = leaf.swingRotY;
      const innerGroup = new THREE.Group();
      innerGroup.position.set(...leaf.innerPos);
      for (const solid of leafSolids.get(motion.leafId) ?? []) {
        const mesh = solidMesh(solid, inside);
        if (mesh) innerGroup.add(mesh);
      }
      swingGroup.add(innerGroup);
      tiltGroup.add(swingGroup);
      group.add(tiltGroup);
    }
    for (const solid of module.solids) {
      if (solid.leafId) continue;
      const mesh = solidMesh(solid, inside);
      if (mesh) group.add(mesh);
    }
    inner.add(group);
  }
  for (const solid of scene.couplers) {
    const mesh = solidMesh(solid, inside);
    if (mesh) inner.add(mesh);
  }
  root.add(inner);
  return root;
}

/** One observer serves every StudioImage on the page — a grid of N thumbs
 * used to register N MutationObservers on documentElement. */
const themeSubscribers = new Set<(theme: string | undefined) => void>();
let themeObserver: MutationObserver | null = null;

function subscribeTheme(notify: (theme: string | undefined) => void): () => void {
  themeSubscribers.add(notify);
  if (themeObserver === null && typeof document !== "undefined") {
    themeObserver = new MutationObserver(() => {
      const theme = document.documentElement.dataset.theme;
      themeSubscribers.forEach((subscriber) => subscriber(theme));
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }
  return () => {
    themeSubscribers.delete(notify);
    if (themeSubscribers.size === 0) {
      themeObserver?.disconnect();
      themeObserver = null;
    }
  };
}

/** The PNG bakes resolved CSS tokens — a theme change must re-render. */
function useDocumentTheme(): string | undefined {
  const [theme, setTheme] = useState<string | undefined>(() =>
    typeof document === "undefined" ? undefined : document.documentElement.dataset.theme,
  );
  useEffect(() => subscribeTheme(setTheme), []);
  return theme;
}

const cache = new Map<string, string>();
const CACHE_LIMIT = 60;

function cacheKey(
  product: ProductJson,
  members: MemberGeometry,
  plan: PlanGeometry | null | undefined,
  options: StudioOptions,
): string {
  // The PNG bakes resolved CSS tokens — the active theme must key the
  // cache or a light-theme render would survive a dark-mode switch.
  const theme = typeof document === "undefined" ? null : document.documentElement.dataset.theme;
  return JSON.stringify({ product, members, plan, options, theme });
}

export function renderStudioImage(
  product: ProductJson,
  members: MemberGeometry,
  plan?: PlanGeometry | null,
  options: StudioOptions = {},
): string | null {
  const gl = getRenderer();
  if (!gl) return null;
  const width = options.width ?? RENDER_W;
  const height = options.height ?? RENDER_H;
  const key = cacheKey(product, members, plan, options);
  const hit = cache.get(key);
  if (hit !== undefined) {
    // Refresh recency so a visible card never ages out under the cap.
    cache.delete(key);
    cache.set(key, hit);
    return hit;
  }

  const scene3d = buildScene3D(product, members, plan);
  const scene = new THREE.Scene();
  const radius = scene3d.radius || 1;
  // Studio rig: soft ambient + key/fill so chamfers and glass read.
  scene.add(new THREE.AmbientLight(0xffffff, 0.62));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.55);
  keyLight.position.set(radius * 1.2, radius * 1.8, radius * 1.5);
  scene.add(keyLight);
  const fill = new THREE.DirectionalLight(0xdfe9ee, 0.5);
  fill.position.set(-radius, radius * 0.6, -radius);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffffff, 0.28);
  rim.position.set(0, -radius * 0.5, radius * 0.8);
  scene.add(rim);

  const root = buildThreeScene(scene3d, options.inside === true, options.pose ?? "closed");
  // World +z is the room face; the street view rotates the model 180°.
  if (!options.inside) root.rotation.y = Math.PI;
  scene.add(root);
  scene.background = new THREE.Color(tokenColor("--model3d-backdrop", "rgb(238,241,242)"));

  const distance = radius * 2.35;
  const camera = new THREE.PerspectiveCamera(40, width / height, 1, distance * 10);
  // 3/4 product shot: slightly above, to the right — the commercial view.
  camera.position.set(distance * 0.42, radius * 0.5, distance);
  camera.lookAt(0, 0, 0);

  gl.setSize(width, height, false);
  gl.render(scene, camera);
  const url = gl.domElement.toDataURL("image/png");

  root.traverse((node) => {
    if (node instanceof THREE.Mesh) {
      node.geometry.dispose();
      const mat = node.material as THREE.MeshStandardMaterial;
      // texture.dispose() isn't covered by material.dispose() — cloned
      // grain maps would leak across every render pass.
      mat.map?.dispose();
      mat.dispose();
    }
  });
  // LRU eviction — Map order is insertion order, so the first key is the
  // oldest render; clearing the whole map forces on-screen cards to re-render.
  while (cache.size >= CACHE_LIMIT) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
  cache.set(key, url);
  return url;
}

/** Cached commercial thumbnail — renders lazily on mount so a grid of
 * positions only pays WebGL once per product shape (the cache key is the
 * model itself). Renders a neutral panel until the first frame lands. */
export function StudioImage({
  product,
  members,
  plan,
  options,
  alt,
  className,
}: {
  product: ProductJson;
  members: MemberGeometry;
  plan?: PlanGeometry | null;
  options?: StudioOptions;
  alt: string;
  className?: string;
}): JSX.Element {
  const [url, setUrl] = useState<string | null>(null);
  const memoOptions = useMemo(
    () => options ?? {},
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [options?.inside, options?.width, options?.height, options?.pose],
  );
  const theme = useDocumentTheme();
  useEffect(() => {
    let alive = true;
    // Defer the WebGL pass until the browser is idle — a grid of cards
    // mounts first and renders scene-by-scene off the critical path.
    const schedule = (cb: () => void): (() => void) => {
      const idle = (window as { requestIdleCallback?: (cb: () => void) => number })
        .requestIdleCallback;
      if (idle) {
        const id = idle(cb);
        return () =>
          (window as { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback?.(id);
      }
      const id = window.setTimeout(cb, 0);
      return () => window.clearTimeout(id);
    };
    const cancel = schedule(() => {
      const rendered = renderStudioImage(product, members, plan, memoOptions);
      if (alive) setUrl(rendered);
    });
    return () => {
      alive = false;
      cancel();
    };
  }, [product, members, plan, memoOptions, theme]);
  if (url === null) {
    return <div className={className} aria-label={alt} role="img" />;
  }
  return <img className={className} src={url} alt={alt} />;
}
