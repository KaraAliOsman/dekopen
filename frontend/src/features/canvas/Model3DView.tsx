import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Edges, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { PlanGeometry } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import type { ProductJson } from "./productEditing";
import { useTheme } from "../../theme/ThemeProvider";
import {
  buildScene3D,
  wallContext,
  type LeafMotion,
  type Scene3D,
  type Solid3D,
  type Vec3,
} from "./Product3DScene";
import { explodeLifts, leafPart, leafPose } from "./leafPose";
import { solidToGeometry } from "./scene3dGeometry";
import {
  contactShadowTexture,
  foilGrainTexture,
  runLength,
  solidMaterial,
  type MaterialMode,
} from "./materials3d";
import type { MemberGeometry } from "./members";
import { webglAvailable } from "./webglAvailable";
import type { SceneDiagnostic } from "./hardwareVisual";

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

const PART_ORDER = ["sash", "bead", "glazing"] as const;

/** §05-E — a leaf's presentation pose. Wraps the solids carrying its
 * leafId and eases them toward open/closed when the toggle flips — the
 * motion is UI state only and never feeds back into the product model.
 * Swing rotates about the hinge edge (+Y), tilt about the pivot edge (+X),
 * slide translates along X — the real mechanism's single axis, one ease
 * well under the 280 ms motion contract. Despiece pulls the leaf apart in
 * the glazing order (sash → junquillo → vidrio) along +z with thin guide
 * rods back to each part's closed seat — never a floating leaf block. */
function LeafGroup({
  motion,
  open,
  tiltPose,
  explode,
  depth,
  parts,
}: {
  motion: LeafMotion;
  open: boolean;
  /** Abatir pose — tilt_turn leaves tip the top in on their bottom pivot
   * while other leaves keep their open pose. Presentation only. */
  tiltPose: boolean;
  /** Despiece pose: ordered axial separation of the leaf's layers with
   * guide lines back to their closed seat. */
  explode: boolean;
  depth: number;
  parts: Record<(typeof PART_ORDER)[number], React.ReactNode>;
}): JSX.Element {
  const tiltGroup = useRef<THREE.Group>(null);
  const swingGroup = useRef<THREE.Group>(null);
  const inner = useRef<THREE.Group>(null);
  const partRefs = useRef<Record<string, THREE.Group | null>>({});
  const guideRefs = useRef<Record<string, THREE.Mesh | null>>({});
  const progress = useRef(0);
  const explodeProgress = useRef(0);
  const invalidate = useThree((state) => state.invalidate);
  const guideColor = tokenColor("--model3d-edge", "rgb(107,112,117)");
  // A tilt_turn leaf owns two pivots — swing (side hinge) and tilt (bottom
  // rail). `activePivot` records which one `progress` currently expresses;
  // switching poses closes the leaf first, then reopens on the other pivot
  // — a real leaf cannot teleport between the two (review: Abatir dead
  // after Abrir).
  const activePivot = useRef<"swing" | "tilt">("swing");
  // Despiece always poses the leaf closed first — an exploded leaf reading
  // half-open is exactly the floating-leaf slop P19 removes.
  const wantOpen = !explode && (motion.kind === "tilt_turn" ? open || tiltPose : open);
  const target = wantOpen ? 1 : 0;
  const explodeTarget = explode ? 1 : 0;
  useFrame((_, delta) => {
    // §13/§8: pose easing settles inside the 280 ms motion contract —
    // rate 11/s ≈ 95 % travelled at ~270 ms while still visibly eased.
    const step = Math.min(1, delta * 11);
    const wantPivot = tiltPose ? "tilt" : "swing";
    let switched = false;
    let switching = motion.kind === "tilt_turn" && wantPivot !== activePivot.current;
    if (switching && progress.current > 0) {
      // Close on the current pivot before switching to the other.
      const next = progress.current - progress.current * step;
      progress.current = Math.abs(next) < 0.004 ? 0 : Math.max(0, next);
    } else if (switching) {
      // Pivot flip owes one pose write so the groups re-anchor.
      activePivot.current = wantPivot;
      switching = false;
      switched = true;
    }
    const moving = progress.current !== target;
    const exploding = explodeProgress.current !== explodeTarget;
    if (!moving && !exploding && !switching && !switched) {
      // Settled pose — rewriting identical transforms and scheduling another
      // frame only burns GPU under frameloop="demand".
      return;
    }
    if (moving) {
      const next = progress.current + (target - progress.current) * step;
      progress.current = Math.abs(next - target) < 0.004 ? target : next;
    }
    if (exploding) {
      const next = explodeProgress.current + (explodeTarget - explodeProgress.current) * step;
      explodeProgress.current = Math.abs(next - explodeTarget) < 0.004 ? explodeTarget : next;
    }
    const tilted = motion.kind === "tilt_turn" && activePivot.current === "tilt";
    const pose = leafPose(motion, progress.current, tilted);
    const lifts = explodeLifts(depth, explodeProgress.current);
    const tiltGroupEl = tiltGroup.current;
    const swingGroupEl = swingGroup.current;
    const innerGroup = inner.current;
    if (!tiltGroupEl || !swingGroupEl || !innerGroup) return;
    // Chained pivots: outer rotates about the leaf's tilt edge (Rx, the
    // bottom rail for tilt_turn / top rail for awning), mid about the
    // hinge edge (Ry) — at most one carries an angle per pose. Mid's
    // position re-expresses the hinge pivot inside the tilted frame.
    tiltGroupEl.position.set(...pose.tiltPos);
    tiltGroupEl.rotation.x = pose.tiltRotX;
    swingGroupEl.position.set(...pose.swingPos);
    swingGroupEl.rotation.y = pose.swingRotY;
    innerGroup.position.set(...pose.innerPos);
    for (const part of PART_ORDER) {
      const group = partRefs.current[part];
      if (group) group.position.set(0, 0, lifts[part]);
      const guide = guideRefs.current[part];
      if (guide) {
        const lift = lifts[part];
        guide.visible = lift > 0.5;
        guide.position.set(motion.cx, motion.cy, motion.partZ[part] + lift / 2);
        guide.scale.set(1, 1, Math.max(lift, 0.01));
      }
    }
    invalidate();
  });
  return (
    <>
      <group ref={tiltGroup}>
        <group ref={swingGroup}>
          <group ref={inner}>
            <group
              ref={(node) => {
                partRefs.current.sash = node;
              }}
            >
              {parts.sash}
            </group>
            <group
              ref={(node) => {
                partRefs.current.bead = node;
              }}
            >
              {parts.bead}
            </group>
            <group
              ref={(node) => {
                partRefs.current.glazing = node;
              }}
            >
              {parts.glazing}
            </group>
          </group>
        </group>
      </group>
      {/* Despiece guides — thin rods from each separated part back to its
       * closed seat on the leaf's axis. */}
      {PART_ORDER.map((part) => (
        <mesh
          key={part}
          ref={(node) => {
            guideRefs.current[part] = node;
          }}
          visible={false}
          renderOrder={2}
        >
          <boxGeometry args={[2.2, 2.2, 1]} />
          <meshBasicMaterial color={guideColor} transparent opacity={0.85} />
        </mesh>
      ))}
    </>
  );
}

/** Human-readable detail for one scene diagnostic — the values the
 * message key can't interpolate through `t`. */
function diagnosticDetail(item: SceneDiagnostic): string {
  const values = item.values;
  switch (item.code) {
    case "kit_unknown":
      return `${values.sku ?? ""}`;
    case "handle_out_of_range":
      return `${values.declared ?? ""} mm → ${values.min ?? ""}–${values.max ?? ""} mm`;
    case "handle_datum_unsupported":
      return `${values.refs ?? ""}`;
    default:
      return `${values.what ?? ""}`;
  }
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
  face,
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
  /** Which physical face the camera sees — the bicolor pair's exterior or
   * interior swatch (D05). */
  face: "exterior" | "interior";
  clipPlane: THREE.Plane | null;
  onPick(owner: string): void;
}): JSX.Element {
  const geometry = useMemo(() => solidToGeometry(solid), [solid]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- theme re-resolves
  // the same tokens against the new CSS variable values.
  const material = useMemo(() => solidMaterial(solid, mode, face), [solid, mode, face]);
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

/** Procedural studio environment — a bare PBR metal needs reflections to
 * read as metal; without an env map metalness collapses to black. RoomEnvironment
 * is generated code (no HDRI download): softbox walls give handles/hinges the
 * highlights that sell them as satin metal. */
function StudioEnvironment({ commercial }: { commercial: boolean }): null {
  const gl = useThree((state) => state.gl);
  const scene = useThree((state) => state.scene);
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envMap;
    scene.environmentIntensity = commercial ? 0.6 : 0.45;
    return () => {
      scene.environment = null;
      scene.environmentIntensity = 1;
      envMap.dispose();
      pmrem.dispose();
    };
  }, [gl, scene, commercial]);
  return null;
}

/** Keeps the live camera fitted when the scene bounds change — the Canvas
 * `camera` prop only applies at mount, so a growing assembly would leave
 * the original frustum. Refits along the current view direction so the
 * user's orbit angle survives a product edit. `focus` (the Detalle preset)
 * dollies onto the leaf's declared hardware anchor instead. */
function CameraRig({ radius, focus }: { radius: number; focus: Vec3 | null }): null {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as unknown as {
    target?: THREE.Vector3;
    update?: () => void;
  } | null;
  useEffect(() => {
    if (focus) {
      // Detalle: a close orbit off the leaf's handle mount point — the
      // camera drops toward the room face so the hardware reads first.
      const anchor = new THREE.Vector3(focus[0], focus[1], focus[2]);
      if (controls?.target) controls.target.copy(anchor);
      camera.position.copy(anchor).add(new THREE.Vector3(190, 80, 420));
      camera.near = 1;
      camera.far = radius * 12;
      camera.updateProjectionMatrix();
      controls?.update?.();
      return;
    }
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
  }, [camera, controls, radius, focus]);
  return null;
}

/** The stage the product stands on: a neutral ground disc under the
 * assembly's real lowest point plus a soft contact shadow. Keeps the
 * product reading as a physical object in both themes — dark-theme
 * canvases used to lose an anthracite frame against the page chrome. */
function Stage({ scene, theme }: { scene: Scene3D; theme: string }): JSX.Element {
  const ground = useMemo(
    () => tokenColor("--theme-viewport-ground", "rgb(212,214,209)"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  );
  const spanX = Math.max(scene.bounds.max[0] - scene.bounds.min[0], 400);
  const spanZ = Math.max(scene.bounds.max[2] - scene.bounds.min[2], 300);
  const groundY = scene.bounds.min[1] - scene.center[1] - 1.5;
  return (
    <group rotation={[0, 0, 0]}>
      {/* Ground disc — sits below the product, clipped to its footprint +
       * breathing room. Rotates with the face toggle is wrong: the stage
       * belongs to the room, so it lives OUTSIDE the flipping group. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, groundY, 0]} renderOrder={-2}>
        <circleGeometry args={[Math.max(spanX, spanZ) * 0.9, 48]} />
        <meshStandardMaterial color={ground} roughness={0.95} metalness={0} />
      </mesh>
      {/* Soft contact shadow where the product meets the ground. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, groundY + 0.4, 0]} renderOrder={-1}>
        <planeGeometry args={[spanX * 1.5, Math.max(spanZ * 1.5 + 500, 900)]} />
        <meshBasicMaterial
          map={contactShadowTexture()}
          transparent
          opacity={0.9}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
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
  wall,
  focus,
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
  /** Vano toggle — draws the plastered wall opening + sill around the
   * assembly so the product reads seated, not floating. */
  wall: boolean;
  /** Detalle preset — camera anchor (the first leaf's handle mount). */
  focus: Vec3 | null;
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
      face={inside ? "interior" : "exterior"}
      clipPlane={clip ? clipPlane : null}
      onPick={onPick}
    />
  );
  return (
    <>
      <ClipSetup />
      <StudioEnvironment commercial={mode === "commercial"} />
      <Stage scene={scene} theme={theme} />
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
               * members stay put. Solids split into despiece parts so the
               * explode pose reads frame↔sash↔junquillo↔vidrio apart. */}
              {module.leaves.map((motion) => {
                const parts: Record<(typeof PART_ORDER)[number], React.ReactNode[]> = {
                  sash: [],
                  bead: [],
                  glazing: [],
                };
                module.solids.forEach((solid, index) => {
                  if (solid.leafId !== motion.leafId) return;
                  parts[leafPart(solid.surface)].push(
                    renderSolid(solid, `${module.moduleId}-${motion.leafId}-${index}`),
                  );
                });
                return (
                  <LeafGroup
                    key={motion.leafId}
                    motion={motion}
                    open={open}
                    tiltPose={tiltPose}
                    explode={explode}
                    depth={module.depth}
                    parts={parts}
                  />
                );
              })}
              {module.solids
                .filter((solid) => solid.leafId == null)
                .map((solid, index) => renderSolid(solid, `${module.moduleId}-f-${index}`))}
            </group>
          ))}
          {scene.couplers.map((solid, index) => renderSolid(solid, `coupler-${index}`))}
          {/* Vano: the wall opening belongs to the product's world, so it
           * rotates with the face toggle but never joins the model — no
           * selection, no explode parts. */}
          {wall &&
            wallContext(scene.bounds).map((solid, index) => (
              <SolidMesh
                key={`wall-${index}`}
                solid={solid}
                selected={false}
                theme={theme}
                mode={mode}
                face={inside ? "interior" : "exterior"}
                clipPlane={clip ? clipPlane : null}
                onPick={() => {}}
              />
            ))}
        </group>
      </group>
      <OrbitControls
        makeDefault
        target={[0, 0, 0]}
        enableDamping={false}
        minDistance={scene.radius * 0.2}
        maxDistance={scene.radius * 8}
      />
      <CameraRig radius={scene.radius} focus={focus} />
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
  inside: insideProp,
  onInsideChange,
}: {
  product: ProductJson;
  members: MemberGeometry;
  plan?: PlanGeometry | null;
  /** The shared selection id — module id, `moduleId/bayId`, or coupling id. */
  selection: string | null;
  onSelectModule(moduleId: string): void;
  onSelectBay(moduleId: string, bayId: string): void;
  onSelectCoupling(couplingId: string): void;
  /** Controlled inside/outside override — the editor's Interior/Exterior
   * selector drives the same state (uncontrolled falls back to internal). */
  inside?: boolean;
  onInsideChange?(inside: boolean): void;
}): JSX.Element {
  const { theme } = useTheme();
  const [mode, setMode] = useState<MaterialMode>("commercial");
  const [insideState, setInsideState] = useState(false);
  const inside = insideProp ?? insideState;
  const setInside = (value: boolean): void => {
    setInsideState(value);
    onInsideChange?.(value);
  };
  const [open, setOpen] = useState(false);
  const [tiltPose, setTiltPose] = useState(false);
  const [clip, setClip] = useState(false);
  const [explode, setExplode] = useState(false);
  const [wall, setWall] = useState(false);
  const [detail, setDetail] = useState(false);
  const scene = useMemo(() => buildScene3D(product, members, plan), [product, members, plan]);
  // Detalle preset anchor — the first leaf's declared handle mount,
  // lifted from module space into the centered world frame.
  const detailAnchor = useMemo<Vec3 | null>(() => {
    for (const module of scene.modules) {
      for (const motion of module.leaves) {
        if (!motion.detail) continue;
        return [
          module.position[0] + motion.detail[0] - scene.center[0],
          module.position[1] + motion.detail[1] - scene.center[1],
          module.position[2] + motion.detail[2] - scene.center[2],
        ];
      }
    }
    return null;
  }, [scene]);
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
  const illustrating = open || tiltPose || explode;
  const stageColor = useMemo(
    () => tokenColor("--theme-viewport-stage", "rgb(228,230,227)"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  );
  // Diagnostics deduped by (code, owner, values) — a four-panel slider
  // would otherwise print the same convention note per leaf.
  const diagnostics = useMemo(() => {
    const seen = new Set<string>();
    return scene.diagnostics.filter((item) => {
      const key = `${item.code}:${item.owner}:${JSON.stringify(item.values)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [scene]);
  if (!webglAvailable()) {
    return (
      <div className="model3d-view model3d-fallback">
        <p className="model3d-fallback__text">{t("assembly.view3dNoWebgl")}</p>
      </div>
    );
  }
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
        {detailAnchor !== null && (
          <button
            type="button"
            className={detail ? "is-active" : ""}
            onClick={() => {
              setDetail((value) => !value);
              // Hardware anchors live on the room face — the Detalle
              // preset is an interior close-up by definition.
              setInside(true);
            }}
          >
            {t("assembly.view3dDetail")}
          </button>
        )}
        <button
          type="button"
          className={wall ? "is-active" : ""}
          onClick={() => setWall((value) => !value)}
        >
          {t("assembly.view3dWall")}
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
            onClick={() =>
              setExplode((value) => {
                // Parts separate toward the room (+z) — the glazing
                // install direction — so despiece reads as an interior
                // view by definition (same pattern as Detalle).
                if (!value) setInside(true);
                return !value;
              })
            }
          >
            {t("assembly.view3dExplode")}
          </button>
        )}
        {/* Symmetric products look identical flipped, so the face toggle needs
         * a persistent readout of which face is toward the camera — otherwise
         * the control reads as dead on correderas and fixed windows. */}
        <span className="model3d-face" aria-live="polite">
          {inside ? t("assembly.view3dInside") : t("assembly.view3dOutside")}
        </span>
      </div>
      {illustrating && (
        <p className="model3d-illustrative" role="note">
          {t("assembly.view3dIllustrative")}
        </p>
      )}
      {diagnostics.length > 0 && (
        <div className="model3d-diagnostics" role="status">
          {diagnostics.map((item, index) => (
            <span
              key={`${item.code}-${index}`}
              className={`model3d-diag model3d-diag--${item.code}`}
              title={diagnosticDetail(item)}
            >
              {t(
                item.code === "kit_unknown"
                  ? "assembly.diagKitUnknown"
                  : item.code === "handle_out_of_range"
                    ? "assembly.diagHandleOutOfRange"
                    : item.code === "handle_datum_unsupported"
                      ? "assembly.diagHandleDatum"
                      : item.code === "finish_convention"
                        ? "assembly.diagFinishConvention"
                        : "assembly.diagHardwareConvention",
              )}
            </span>
          ))}
        </div>
      )}
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
        {/* Neutral stage backdrop — a product photograph's seamless
         * background, not the app's page color. Physical finishes stay
         * readable in either theme. */}
        <color attach="background" args={[stageColor]} />
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
          wall={wall}
          focus={detail ? detailAnchor : null}
          onPick={pick}
        />
      </Canvas>
    </div>
  );
}
