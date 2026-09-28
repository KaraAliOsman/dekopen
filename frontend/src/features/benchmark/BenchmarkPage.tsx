import { useMemo, useState } from "react";

import { t, type TranslationKey } from "../../i18n/es-CL";
import { STARTER_DEFINITIONS, starterNominalSize, type StarterKey } from "../canvas/designLibrary";
import { FALLBACK_MEMBERS, type MemberGeometry, type MemberSpec } from "../canvas/members";
import Model3DView from "../canvas/Model3DView";
import { ProductFrontSvg } from "../canvas/ProductFrontSvg";
import type { ProductJson } from "../canvas/productEditing";
import { StudioImage } from "../canvas/renderStudio";
import "./benchmark.css";

/** §05-H visual benchmark — one fixture wall that projects the same
 * ProductModel through every render surface (technical elevation, studio
 * commercial render, interactive 3D) per finish family. A QA surface for
 * inspecting whether output looks like physically convincing fenestration,
 * not a user-facing page; the interactive 3D mounts on demand per card. */

const NOOP = (): void => undefined;

/** A fixture wall of ten interactive canvases would hold ~10 WebGL
 * contexts at once — near the browser ceiling, and mount/unmount churn
 * was visibly hitting context-loss warnings. The 3D capture therefore
 * rests as the shared-context studio still and only upgrades to the live
 * orbit view when a reviewer actually clicks to orbit it. */
function LazyThree({
  product,
  members,
  label,
}: {
  product: ProductJson;
  members: MemberGeometry;
  label: string;
}): JSX.Element {
  const [active, setActive] = useState(false);
  return (
    <div className="benchmark-capture__body benchmark-capture__body--three">
      {active ? (
        <>
          <Model3DView
            product={product}
            members={members}
            selection={null}
            onSelectModule={NOOP}
            onSelectBay={NOOP}
            onSelectCoupling={NOOP}
          />
          <button type="button" className="benchmark-three-freeze" onClick={() => setActive(false)}>
            {t("benchmark.freeze")}
          </button>
        </>
      ) : (
        <button
          type="button"
          className="benchmark-three-activate"
          onClick={() => setActive(true)}
          aria-label={`${t("benchmark.orbit")} — ${label}`}
        >
          <StudioImage
            product={product}
            members={members}
            options={{ width: 380, height: 260 }}
            alt={label}
          />
          <span className="benchmark-three-cta">{t("benchmark.orbit")} ▸</span>
        </button>
      )}
    </div>
  );
}

type BenchMaterialKey = "pvc" | "pvcFoil" | "aluAnthracite";

function spec(material: string, faceWidthMm: number): MemberSpec {
  return { sku: null, material, faceWidthMm };
}

function benchMembers(profile: "pvc" | "alu", material: string): MemberGeometry {
  const frame = profile === "alu" ? 50 : 60;
  const sash = profile === "alu" ? 58 : 72;
  const mullion = profile === "alu" ? 52 : 70;
  const threshold = profile === "alu" ? 24 : 30;
  const coupler = profile === "alu" ? 46 : 64;
  return {
    frame: spec(material, frame),
    sash: spec(material, sash),
    mullionV: spec(material, mullion),
    mullionH: spec(material, mullion),
    threshold: spec(material, threshold),
    beadFor: () => FALLBACK_MEMBERS.bead,
    beadSpecFor: () => null,
    couplerFor: () => spec(material, coupler),
    kitFor: () => null,
    handlePolicy: null,
    rebateMm: FALLBACK_MEMBERS.rebate,
    sashOverlapMm: FALLBACK_MEMBERS.sashOverlap,
  };
}

const MATERIALS: Record<BenchMaterialKey, { labelKey: TranslationKey; members: MemberGeometry }> = {
  pvc: {
    labelKey: "benchmark.material.pvc",
    members: benchMembers("pvc", "PVC"),
  },
  pvcFoil: {
    labelKey: "benchmark.material.foil",
    members: benchMembers("pvc", "PVC_FOIL"),
  },
  aluAnthracite: {
    labelKey: "benchmark.material.anthracite",
    members: benchMembers("alu", "ALUMINIUM_ANTHRACITE"),
  },
};

function starterProduct(key: StarterKey): ProductJson {
  const def = STARTER_DEFINITIONS.find((entry) => entry.key === key);
  const size = starterNominalSize(key);
  return def
    ? def.build(size.widthMm, size.heightMm)
    : { version: "product-v2", assembly: { modules: [], couplings: [] } };
}

/** Two-module 90° corner — the TEE/CORNER joint the starters don't cover. */
function cornerProduct(): ProductJson {
  return {
    version: "product-v2",
    assembly: {
      modules: [
        {
          id: "m1",
          width_mm: "1400.00",
          height_mm: "1600.00",
          tree: { id: "m1", type: "BAY", opening_type: "TILT_TURN_LEFT" },
        },
        {
          id: "m2",
          width_mm: "1100.00",
          height_mm: "1600.00",
          tree: { id: "m2", type: "BAY", opening_type: "FIXED" },
        },
      ],
      couplings: [
        {
          id: "c1",
          angle_deg: "90.0",
          kind: "CORNER",
          modules: ["m1", "m2"],
          edges: ["right", "left"],
          coupler_profile_sku: null,
        },
      ],
    },
  };
}

type Fixture = {
  key: string;
  labelKey: TranslationKey;
  build(): ProductJson;
};

const FIXTURES: Fixture[] = [
  { key: "fixed", labelKey: "benchmark.fixture.fixed", build: () => starterProduct("fixed") },
  { key: "tiltTurn", labelKey: "benchmark.fixture.tiltTurn", build: () => starterProduct("sash") },
  { key: "twoSash", labelKey: "benchmark.fixture.twoSash", build: () => starterProduct("twoSash") },
  {
    key: "sliding",
    labelKey: "benchmark.fixture.sliding",
    build: () => starterProduct("sliding2"),
  },
  { key: "door", labelKey: "benchmark.fixture.door", build: () => starterProduct("doorSide") },
  { key: "corner", labelKey: "benchmark.fixture.corner", build: cornerProduct },
  { key: "bow", labelKey: "benchmark.fixture.bow", build: () => starterProduct("bow3") },
  {
    key: "frameless",
    labelKey: "benchmark.fixture.frameless",
    build: () => starterProduct("frameless"),
  },
  {
    key: "trapezoid",
    labelKey: "benchmark.fixture.trapezoid",
    build: () => starterProduct("trapezoid"),
  },
  { key: "arch", labelKey: "benchmark.fixture.arch", build: () => starterProduct("arch") },
];

const MATERIAL_ORDER: BenchMaterialKey[] = ["pvc", "pvcFoil", "aluAnthracite"];

export function BenchmarkPage(): JSX.Element {
  const [materialKey, setMaterialKey] = useState<BenchMaterialKey>("pvc");
  const members = MATERIALS[materialKey].members;
  const fixtures = useMemo(
    () => FIXTURES.map((fixture) => ({ ...fixture, product: fixture.build() })),
    [],
  );
  return (
    <div className="benchmark-page">
      <header className="benchmark-header">
        <div>
          <h1>{t("benchmark.title")}</h1>
          <p className="benchmark-subtitle">{t("benchmark.subtitle")}</p>
        </div>
        <div className="benchmark-materials" role="tablist">
          {MATERIAL_ORDER.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === materialKey}
              className={`benchmark-chip${key === materialKey ? " is-active" : ""}`}
              onClick={() => setMaterialKey(key)}
            >
              {t(MATERIALS[key].labelKey)}
            </button>
          ))}
        </div>
      </header>
      <section className="benchmark-grid">
        {fixtures.map((fixture) => (
          <article key={fixture.key} className="benchmark-fixture">
            <h2 className="benchmark-fixture__name">{t(fixture.labelKey)}</h2>
            <div className="benchmark-captures">
              <figure className="benchmark-capture">
                <figcaption>{t("benchmark.view2d")}</figcaption>
                <div className="benchmark-capture__body">
                  <ProductFrontSvg
                    product={fixture.product}
                    members={members}
                    selectedId={null}
                    issues={[]}
                    disabled
                    preview
                    dimLevel="technical"
                    onSelectModule={NOOP}
                    onSelectBay={NOOP}
                    onSelectDivision={NOOP}
                    onSelectCoupling={NOOP}
                    onContextMenuModule={NOOP}
                    onAddUnit={NOOP}
                    onCommitModuleWidth={NOOP}
                    onCommitTotalWidth={NOOP}
                    onCommitHeight={NOOP}
                    onCommitDivide={NOOP}
                    onMoveDivision={NOOP}
                    onResizeSeam={NOOP}
                  />
                </div>
              </figure>
              <figure className="benchmark-capture">
                <figcaption>{t("benchmark.commercial")}</figcaption>
                <div className="benchmark-capture__body benchmark-capture__body--studio">
                  <StudioImage
                    product={fixture.product}
                    members={members}
                    options={{ width: 380, height: 280 }}
                    alt={t(fixture.labelKey)}
                  />
                </div>
              </figure>
              <figure className="benchmark-capture benchmark-capture--three">
                <figcaption>{t("benchmark.view3d")}</figcaption>
                <LazyThree
                  product={fixture.product}
                  members={members}
                  label={t(fixture.labelKey)}
                />
              </figure>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
