import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Edges, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { PlanGeometry } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import type { ProductJson } from "./productEditing";
import { useTheme } from "../../theme/ThemeProvider";
import { buildScene3D, type LeafMotion, type Scene3D, type Solid3D } from "./Product3DScene";
import { solidToGeometry } from "./scene3dGeometry";
import { solidMaterial, type MaterialMode } from "./materials3d";
import type { MemberGeometry } from "./members";

const SWING_RAD = (32 * Math.PI) / 180;
const TILT_RAD = (13 * Math.PI) / 180;

/** Wood-grain skin for foil-finished members (§05-C): a generated
 * CanvasTexture, license-free, with streaks running along the member's
 * run axis — never a flat brown fill. One base per orientation; solids
 * clone it with a repeat matched to their run length so grain density
 * stays physical. */
const grainCache = new Map<string, THREE.Texture>();

function drawGrain(axis: "u" | "v"): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "rgb(255,255,255)";
    ctx.fillRect(0, 0, 256, 256);
    // Grain needs real contrast to read at member scale (review M7) —
    // faint 4–11% streaks vanished against the foil base coat.
    for (let index = 0; index < 46; index += 1) {
      const at = Math.random() * 256;
      const wave = 4 + Math.random() * 14;
      const alpha = 0.1 + Math.random() * 0.16;
      ctx.strokeStyle = `rgba(52, 34, 16, ${alpha.toFixed(3)})`;
      ctx.lineWidth = 0.9 + Math.random() * 3.2;
      ctx.beginPath();
      if (axis === "u") {
        ctx.moveTo(-8, at);
        ctx.bezierCurveTo(64, at + wave, 192, at - wave, 264, at + wave * 0.5);
      } else {
        ctx.moveTo(at, -8);
        ctx.bezierCurveTo(at + wave, 64, at - wave, 192, at + wave * 0.5, 264);
      }
      ctx.stroke();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

function runLength(solid: Solid3D): number {
  switch (solid.kind) {
    case "box":
      return Math.max(solid.size[0], solid.size[1]);
    case "profile":
      return Math.max(Math.abs(solid.a1 - solid.a0), 1);
    case "prism":
      return Math.max(Math.abs(solid.y1 - solid.y0), 1);
    default: {
      let extent = 1;
      for (const [x, y] of solid.outline) {
        extent = Math.max(extent, Math.abs(x), Math.abs(y));
      }
      return extent;
    }
  }
}

function foilGrainTexture(axis: "u" | "v", runMm: number): THREE.Texture {
  let base = grainCache.get(axis);
  if (!base) {
    base = drawGrain(axis);
    grainCache.set(axis, base);
  }
  const texture = base.clone();
  const repeat = Math.max(1, Math.round(runMm / 400));
  if (axis === "u") texture.repeat.set(repeat, 1);
  else texture.repeat.set(1, repeat);
  return texture;
}

/** Enables per-material clipping planes once — the Corte toggle then just
 * supplies the plane through the scene center. */
function ClipSetup(): null {
  const gl = useThree((state) => state.gl);
  useEffect(() => {
    gl.localClippingEnabled = true;
    return () => {
      gl.localClippingEnabled = false;
    };
  }, [gl]);
  return null;
}

/** §05-E — a leaf's presentation pose. Wraps the solids carrying its
 * leafId and eases them toward open/closed when the toggle flips — the
 * motion is UI state only and never feeds back into the product model.
 * Swing rotates about the hinge edge (+Y), tilt about the pivot edge (+X),
 * slide translates along X. */
function LeafGroup({
  motion,
  open,
  tiltPose,
  explode,
  depth,
  children,
}: {
  motion: LeafMotion;
  open: boolean;
  /** Abatir pose — tilt_turn leaves tip the top in on their bottom pivot
   * while other leaves keep their open pose. Presentation only. */
  tiltPose: boolean;
  /** Despiece pose: leaves lift toward the room side (+z) — reads the
   * frame↔sash↔glass layering apart without touching geometry. */
  explode: boolean;
  depth: number;
  children: React.ReactNode;
}): JSX.Element {
  const tiltGroup = useRef<THREE.Group>(null);
  const swingGroup = useRef<THREE.Group>(null);
  const inner = useRef<THREE.Group>(null);
  const progress = useRef(0);
  const explodeProgress = useRef(0);
  const invalidate = useThree((state) => state.invalidate);
  // Abatir poses only tilt_turn leaves — other kinds keep obeying Abrir.
  const target = (motion.kind === "tilt_turn" ? open || tiltPose : open) ? 1 : 0;
  const explodeTarget = explode ? 1 : 0;
  useFrame((_, delta) => {
    const moving = progress.current !== target;
    const exploding = explodeProgress.current !== explodeTarget;
    if (!moving && !exploding) return;
    const step = Math.min(1, delta * 5.5);
    if (moving) {
      const next = progress.current + (target - progress.current) * step;
      progress.current = Math.abs(next - target) < 0.004 ? target : next;
    }
    if (exploding) {
      const next = explodeProgress.current + (explodeTarget - explodeProgress.current) * step;
      explodeProgress.current = Math.abs(next - explodeTarget) < 0.004 ? explodeTarget : next;
    }
    const pose = progress.current;
    const lift = explodeProgress.current * Math.max(depth * 1.35, 60);
    const tiltGroupEl = tiltGroup.current;
    const swingGroupEl = swingGroup.current;
    const innerGroup = inner.current;
    if (!tiltGroupEl || !swingGroupEl || !innerGroup) return;
    // Chained pivots: outer rotates about the leaf's tilt edge (Rx, the
    // bottom rail for tilt_turn / top rail for awning), mid about the
    // hinge edge (Ry) — at most one carries an angle per pose. Mid's
    // position re-expresses the hinge pivot inside the tilted frame.
    const tiltPivot = motion.tiltPivot ?? 0;
    if (motion.kind === "swing") {
      tiltGroupEl.position.set(0, 0, 0);
      tiltGroupEl.rotation.x = 0;
      swingGroupEl.position.set(motion.pivot, 0, 0);
      swingGroupEl.rotation.y = motion.dir * pose * SWING_RAD;
      innerGroup.position.set(-motion.pivot, 0, lift);
    } else if (motion.kind === "tilt") {
      tiltGroupEl.position.set(0, motion.pivot, 0);
      tiltGroupEl.rotation.x = motion.dir * pose * TILT_RAD;
      swingGroupEl.position.set(0, -motion.pivot, 0);
      swingGroupEl.rotation.y = 0;
      innerGroup.position.set(0, 0, lift);
    } else if (motion.kind === "tilt_turn") {
      tiltGroupEl.position.set(0, tiltPivot, 0);
      tiltGroupEl.rotation.x = tiltPose ? pose * TILT_RAD : 0;
      swingGroupEl.position.set(motion.pivot, -tiltPivot, 0);
      swingGroupEl.rotation.y = tiltPose ? 0 : motion.dir * pose * SWING_RAD;
      innerGroup.position.set(-motion.pivot, 0, lift);
    } else {
      tiltGroupEl.position.set(motion.dir * pose * motion.travel, 0, 0);
      tiltGroupEl.rotation.x = 0;
      swingGroupEl.position.set(0, 0, 0);
      swingGroupEl.rotation.y = 0;
      innerGroup.position.set(0, 0, lift);
    }
    invalidate();
  });
  return (
    <group ref={tiltGroup}>
      <group ref={swingGroup}>
        <group ref={inner}>{children}</group>
      </group>
    </group>
  );
}

/** §16 synchronized 3D view (§05 physical renderer) — the scene derives
 * from the same product model the editor renders (no separate 3D data).
 * Orbit/pan/zoom via OrbitControls; solids carry the same owner ids the
 * 2D selection uses, so clicking a member, leaf or coupler here selects
 * it everywhere. Declared catalog sections extrude as real profiles;
 * undeclared members stay a visibly schematic box (edge lines), never
 * a fabricated declaration. */

function tokenColor(token: string, fallback: string): string {
  const value =
    typeof window === "undefined"
      ? ""
      : getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return value || fallback;
}

function SolidMesh({
  solid,
  selected,
  theme,
  mode,
  clipPlane,
  onPick,
}: {
  solid: Solid3D;
  selected: boolean;
  /** Re-resolves token colors when the app theme switches — theme changes
   * flip CSS variables without otherwise re-rendering this subtree. */
  theme: string;
  mode: MaterialMode;
  clipPlane: THREE.Plane | null;
  onPick(owner: string): void;
}): JSX.Element {
  const geometry = useMemo(() => solidToGeometry(solid), [solid]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- theme re-resolves
  // the same tokens against the new CSS variable values.
  const material = useMemo(() => solidMaterial(solid, mode), [solid, mode]);
  const color = useMemo(
    () => tokenColor(material.colorToken, material.colorFallback),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [material, theme],
  );
  // Selection glows in the accent hue — warning amber washed side faces
  // brown and read as a material tint (visual QA pass on /benchmark).
  const emissive = useMemo(
    () => (selected ? tokenColor("--theme-accent", "rgb(15,129,122)") : "rgb(0,0,0)"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected, theme],
  );
  const map = useMemo(
    () =>
      material.grain && mode === "commercial"
        ? foilGrainTexture(material.grain, runLength(solid))
        : null,
    [solid, material, mode],
  );
  // Each mesh clones the cached base texture — material disposal does NOT
  // release a texture map, so the clone is disposed when the map is
  // replaced or the mesh unmounts (the shared base lives in grainCache).
  useEffect(() => {
    if (!map) return;
    return () => {
      map.dispose();
    };
  }, [map]);
  // BufferGeometry passed to <mesh geometry> is not auto-disposed by r3f —
  // every edit regenerates solids, so the replaced geometry must be freed
  // or GPU memory grows monotonically through a session.
  useEffect(() => {
    return () => {
      geometry?.dispose();
    };
  }, [geometry]);
  return (
    <mesh
      geometry={geometry ?? undefined}
      position={solid.kind === "box" ? solid.center : undefined}
      onClick={(event) => {
        event.stopPropagation();
        onPick(solid.owner);
      }}
    >
      {solid.kind === "box" && <boxGeometry args={solid.size} />}
      <meshStandardMaterial
        color={color}
        map={map ?? undefined}
        transparent={material.transparent}
        opacity={material.opacity}
        depthWrite={!material.glass}
        roughness={material.roughness}
        metalness={material.metalness}
        emissive={emissive}
        emissiveIntensity={selected ? 0.38 : 0}
        // An empty array — never undefined: r3f applies this prop onto
        // material.clippingPlanes and three's WebGLClipping crashes on a
        // missing .length, leaving the whole canvas blank once Corte was
        // toggled off.
        clippingPlanes={clipPlane ? [clipPlane] : []}
      />
      {/* Approximate member boxes (no declared catalog section) get the
       * schematic edge look — visually distinct from a real extruded
       * profile so convention never masquerades as authority. */}
      {(solid.approximate === true || mode === "technical") &&
        (solid.kind === "box" || solid.kind === "profile") && (
          <Edges scale={1.002} color={tokenColor("--model3d-edge", "rgb(107,112,117)")} />
        )}
    </mesh>
  );
}

/** Keeps the live camera fitted when the scene bounds change — the Canvas
 * `camera` prop only applies at mount, so a growing assembly would leave
 * the original frustum. Refits along the current view direction so the
 * user's orbit angle survives a product edit. */
function CameraRig({ radius }: { radius: number }): null {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as unknown as {
    target?: THREE.Vector3;
    update?: () => void;
  } | null;
  useEffect(() => {
    const distance = radius * 2.4;
    // Refit along the current view direction around the controls' target —
    // panning moves both, so rescaling about the world origin would change
    // the orbit angle and slide the product off-screen.
    const target = controls?.target ?? new THREE.Vector3();
    const dir = camera.position.clone().sub(target);
    if (dir.lengthSq() === 0) dir.set(0.5, 0.55, 1);
    camera.position.copy(target).add(dir.normalize().multiplyScalar(distance));
    camera.near = 1;
    camera.far = distance * 10;
    camera.updateProjectionMatrix();
    controls?.update?.();
  }, [camera, controls, radius]);
  return null;
}

function SceneContent({
  scene,
  selection,
  theme,
  mode,
  inside,
  open,
  clip,
  explode,
  tiltPose,
  onPick,
}: {
  scene: Scene3D;
  selection: string | null;
  theme: string;
  mode: MaterialMode;
  inside: boolean;
  open: boolean;
  clip: boolean;
  explode: boolean;
  tiltPose: boolean;
  onPick(owner: string): void;
}): JSX.Element {
  // Corte: a vertical section through the scene center keeps the left
  // half — exposes frame/sash/glazing layering in cross-section.
  const clipPlane = useMemo(() => new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0), []);
  const renderSolid = (solid: Solid3D, key: string): JSX.Element => (
    <SolidMesh
      key={key}
      solid={solid}
      selected={selection === solid.owner}
      theme={theme}
      mode={mode}
      clipPlane={clip ? clipPlane : null}
      onPick={onPick}
    />
  );
  return (
    <>
      <ClipSetup />
      <ambientLight intensity={mode === "commercial" ? 0.55 : 0.85} />
      {/* Commercial mode gets studio key/fill; technical stays flat-lit. */}
      <directionalLight
        position={[4000, 6000, 5000]}
        intensity={mode === "commercial" ? 1.5 : 1.1}
      />
      <directionalLight
        position={[-3000, 2000, -4000]}
        intensity={mode === "commercial" ? 0.6 : 0.35}
      />
      {mode === "commercial" && <directionalLight position={[0, -2000, 2500]} intensity={0.25} />}
      {/* Inside/outside: the assembly (centered on the scene origin by the
       * inner group) rotates 180° so the room face or the street face
       * points at the default camera. World +z is the room face, so the
       * street view is the rotated one. */}
      <group rotation={[0, inside ? 0 : Math.PI, 0]}>
        <group position={[-scene.center[0], -scene.center[1], -scene.center[2]]}>
          {scene.modules.map((module) => (
            <group
              key={module.moduleId}
              position={module.position}
              rotation={[0, module.rotationY, 0]}
            >
              {/* Leaf solids animate as presentation pose — the leaf group
               * rotates/translates around its declared hinge/pivot; fixed
               * members stay put. */}
              {module.leaves.map((motion) => (
                <LeafGroup
                  key={motion.leafId}
                  motion={motion}
                  open={open}
                  tiltPose={tiltPose}
                  explode={explode}
                  depth={module.depth}
                >
                  {module.solids
                    .filter((solid) => solid.leafId === motion.leafId)
                    .map((solid, index) =>
                      renderSolid(solid, `${module.moduleId}-${motion.leafId}-${index}`),
                    )}
                </LeafGroup>
              ))}
              {module.solids
                .filter((solid) => solid.leafId == null)
                .map((solid, index) => renderSolid(solid, `${module.moduleId}-f-${index}`))}
            </group>
          ))}
          {scene.couplers.map((solid, index) => renderSolid(solid, `coupler-${index}`))}
        </group>
      </group>
      <OrbitControls
        makeDefault
        target={[0, 0, 0]}
        enableDamping={false}
        minDistance={scene.radius * 0.2}
        maxDistance={scene.radius * 8}
      />
      <CameraRig radius={scene.radius} />
    </>
  );
}

export default function Model3DView({
  product,
  members,
  plan,
  selection,
  onSelectModule,
  onSelectBay,
  onSelectCoupling,
}: {
  product: ProductJson;
  members: MemberGeometry;
  plan?: PlanGeometry | null;
  /** The shared selection id — module id, `moduleId/bayId`, or coupling id. */
  selection: string | null;
  onSelectModule(moduleId: string): void;
  onSelectBay(moduleId: string, bayId: string): void;
  onSelectCoupling(couplingId: string): void;
}): JSX.Element {
  const { theme } = useTheme();
  const [mode, setMode] = useState<MaterialMode>("commercial");
  const [inside, setInside] = useState(false);
  const [open, setOpen] = useState(false);
  const [tiltPose, setTiltPose] = useState(false);
  const [clip, setClip] = useState(false);
  const [explode, setExplode] = useState(false);
  const scene = useMemo(() => buildScene3D(product, members, plan), [product, members, plan]);
  const hasLeaves = useMemo(
    () => scene.modules.some((module) => module.leaves.length > 0),
    [scene],
  );
  const hasTiltTurn = useMemo(
    () => scene.modules.some((module) => module.leaves.some((leaf) => leaf.kind === "tilt_turn")),
    [scene],
  );
  const moduleIds = useMemo(
    () => new Set(product.assembly.modules.map((module) => module.id)),
    [product],
  );
  const pick = (owner: string): void => {
    const split = owner.indexOf("/");
    if (split > 0) {
      onSelectBay(owner.slice(0, split), owner.slice(split + 1));
      return;
    }
    if (moduleIds.has(owner)) {
      onSelectModule(owner);
      return;
    }
    onSelectCoupling(owner);
  };
  const cameraDistance = scene.radius * 2.4;
  return (
    <div className="model3d-view">
      <div className="model3d-toolbar" role="toolbar" aria-label={t("assembly.view3d")}>
        <button
          type="button"
          className={mode === "commercial" ? "is-active" : ""}
          onClick={() => setMode("commercial")}
        >
          {t("assembly.view3dCommercial")}
        </button>
        <button
          type="button"
          className={mode === "technical" ? "is-active" : ""}
          onClick={() => setMode("technical")}
        >
          {t("assembly.view3dTechnical")}
        </button>
        <button
          type="button"
          className={inside ? "" : "is-active"}
          onClick={() => setInside(false)}
        >
          {t("assembly.view3dOutside")}
        </button>
        <button type="button" className={inside ? "is-active" : ""} onClick={() => setInside(true)}>
          {t("assembly.view3dInside")}
        </button>
        {hasLeaves && (
          <button
            type="button"
            className={open ? "is-active" : ""}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? t("assembly.view3dClose") : t("assembly.view3dOpen")}
          </button>
        )}
        {hasTiltTurn && (
          <button
            type="button"
            className={tiltPose ? "is-active" : ""}
            onClick={() => setTiltPose((value) => !value)}
          >
            {t("assembly.view3dTilt")}
          </button>
        )}
        <button
          type="button"
          className={clip ? "is-active" : ""}
          onClick={() => setClip((value) => !value)}
        >
          {t("assembly.view3dClip")}
        </button>
        {hasLeaves && (
          <button
            type="button"
            className={explode ? "is-active" : ""}
            onClick={() => setExplode((value) => !value)}
          >
            {t("assembly.view3dExplode")}
          </button>
        )}
      </div>
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{
          position: [cameraDistance * 0.5, scene.radius * 0.55, cameraDistance],
          fov: 42,
          near: 1,
          far: cameraDistance * 10,
        }}
        className="model3d-canvas"
      >
        <SceneContent
          scene={scene}
          selection={selection}
          theme={theme}
          mode={mode}
          inside={inside}
          open={open}
          clip={clip}
          explode={explode}
          tiltPose={tiltPose}
          onPick={pick}
        />
      </Canvas>
    </div>
  );
}
