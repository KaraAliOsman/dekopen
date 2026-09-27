import * as client from "../../api/generated/dekopen";
import type {
  ErrorResponse,
  SectionImportResponse,
  SystemWriteRequest,
  SystemWorkspace,
  ProcessProfileOption,
  WorkCenter,
  WorkCenterRequestRequest,
  ArticleWriteRequest,
  BeadWriteRequest,
  KitWriteRequest,
  CatalogHardwareComponentRequest,
  ProfileSection,
  ProfileSectionRequest,
  SystemResponse,
  ArticleResponse,
  BeadResponse,
  KitResponse,
} from "../../api/generated/models";

export type SystemWrite = SystemWriteRequest;
export type ArticleWrite = ArticleWriteRequest;
export type BeadWrite = BeadWriteRequest;
export type KitWrite = KitWriteRequest;
export type HardwareComponent = CatalogHardwareComponentRequest;

/** §9 component-kind vocabulary — mirrors the engine enum. */
export const HARDWARE_COMPONENT_CATEGORIES = [
  "HANDLE",
  "HINGE",
  "LOCK",
  "ROLLER",
  "CONNECTOR",
  "DRAINAGE",
  "GASKET",
  "SEAL",
  "SCREW",
  "CONSUMABLE",
  "FITTING",
  "SUPPORT",
  "CHANNEL",
  "OTHER",
] as const;
export type Writes = {
  systems: SystemWrite;
  articles: ArticleWrite;
  glazing: BeadWrite;
  "hardware-kits": KitWrite;
};
export type Resource = keyof Writes;
type Responses = {
  systems: SystemResponse;
  articles: ArticleResponse;
  glazing: BeadResponse;
  "hardware-kits": KitResponse;
};
export type Row<R extends Resource> = Responses[R];
export type CatalogData = { [R in Resource]: Row<R>[] };

export type Field = {
  name: string;
  kind:
    | "text"
    | "decimal"
    | "integer"
    | "boolean"
    | "select"
    | "system"
    | "bead"
    | "csv"
    | "processProfile";
  optional?: boolean;
  places?: number;
  maxLength?: number;
  options?: readonly string[];
};

type Group = { title: string; fields: Field[] };

const text = (name: string, maxLength?: number, optional = false): Field => ({
  name,
  kind: "text",
  maxLength,
  optional,
});

const decimal = (name: string, places = 2, optional = false): Field => ({
  name,
  kind: "decimal",
  places,
  optional,
});

const measures = (...names: string[]): Field[] => names.map((name) => decimal(name));
const integer = (name: string): Field => ({ name, kind: "integer" });
const active: Field = { name: "is_active", kind: "boolean" };
const material: Field = {
  name: "material",
  kind: "select",
  options: ["PVC", "ALUMINIUM"],
};
const rail: Field = {
  name: "rail_type",
  kind: "select",
  options: ["dual", "mono"],
};
const system: Field = { name: "system_id", kind: "system" };

export const schemas: Record<Resource, Group[]> = {
  systems: [
    {
      title: "identity",
      fields: [
        text("name", 150),
        text("code", 50),
        material,
        // §06 system identity — who makes it, which family, what it covers.
        text("manufacturer", 255, true),
        text("family", 150, true),
        { name: "applications", kind: "csv", optional: true, maxLength: 60 },
        // Finishes the series sells — feeds the estimator's Acabado picker.
        { name: "finishes", kind: "csv", optional: true, maxLength: 50 },
        { name: "process_profile_id", kind: "processProfile", optional: true },
        decimal("depth_mm"),
        integer("chamber_count"),
        integer("version"),
        active,
      ],
    },
    {
      title: "glazingGeometry",
      fields: [
        ...measures("sash_overlap_mm", "glass_clearance_white_mm", "glass_clearance_foil_mm"),
        decimal("chamber_clearance_mm", 2, true),
      ],
    },
    {
      title: "fabricationGeometry",
      fields: [
        // UNKNOWN is a legitimate state — an empty value writes null and the
        // engine refuses rather than compute on an invented constant.
        decimal("rebate_depth_mm", 2, true),
        decimal("end_milling_overlap_mm", 2, true),
      ],
    },
    {
      title: "slidingGeometry",
      fields: [
        rail,
        ...measures(
          "pulley_height_mm",
          "central_overlap_mm",
          "sliding_lateral_clearance_mm",
          "sliding_end_add_mm",
          "corner_bracket_loss_mm",
          "hook_depth_mm",
          "sliding_glazing_deduction_width_mm",
          "sliding_glazing_deduction_height_mm",
        ),
      ],
    },
    {
      title: "doorGeometry",
      fields: measures(
        "door_threshold_mm",
        "door_bottom_clearance_mm",
        "door_leaf_side_clearance_mm",
      ),
    },
  ],
  articles: [
    {
      title: "identity",
      fields: [
        system,
        text("sku", 100),
        text("name", 255),
        material,
        {
          name: "role",
          kind: "select",
          options: [
            "FRAME",
            "SASH",
            "MULLION_V",
            "MULLION_H",
            "INVERSOR",
            "GLAZING_BEAD",
            "COUPLER",
            "ADDITIONAL",
            "THRESHOLD",
          ],
        },
      ],
    },
    {
      title: "profileGeometry",
      fields: [
        ...measures("face_width_mm"),
        // Fabrication fields accept UNKNOWN — an empty value writes null and
        // downstream consumers refuse or flag rather than compute on a guess.
        decimal("commercial_length_mm", 2, true),
        decimal("welding_loss_mm", 2, true),
      ],
    },
    {
      title: "reinforcement",
      fields: [
        text("reinforcement_sku", 100, true),
        decimal("reinforcement_gap_mm", 2, true),
        decimal("weight_kg_m", 4, true),
        decimal("steel_weight_kg_m", 4, true),
      ],
    },
  ],
  glazing: [
    {
      title: "compatibility",
      fields: [
        system,
        { name: "bead_article_id", kind: "bead" },
        ...measures(
          "glass_thickness_mm",
          "bead_width_mm",
          "gasket_interior_mm",
          "gasket_exterior_mm",
          "cut_add_mm",
        ),
        active,
      ],
    },
  ],
  "hardware-kits": [
    {
      title: "identity",
      fields: [
        { ...system, optional: true },
        text("sku", 100),
        text("name", 255),
        {
          name: "opening_type",
          kind: "select",
          options: ["TURN", "TILT_TURN", "SLIDING", "DOOR", "AWNING"],
        },
        rail,
        active,
      ],
    },
    {
      title: "leafLimits",
      fields: measures(
        "min_leaf_width_mm",
        "max_leaf_width_mm",
        "min_leaf_height_mm",
        "max_leaf_height_mm",
        "max_leaf_weight_kg",
      ),
    },
    {
      title: "hardware",
      fields: [
        integer("carriages_qty"),
        integer("stay_arms_qty"),
        decimal("weight_kg", 2, true),
        decimal("carriage_capacity_kg", 2, true),
      ],
    },
  ],
};

// Decimal strings remain strings throughout form state and transport —
// precision is the contract ("0.1000000000000000001" reaches the engine
// untouched). Only the es-CL thousands-dot pattern normalizes: "1.500" is
// fifteen hundred, never 1.5.
export const exact = (value: string): string => {
  const text = value.trim();
  if (/^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$/.test(text)) {
    return text.replaceAll(".", "").replace(",", ".");
  }
  return text.replace(",", ".");
};

/** §15 section authoring state — structured like the kit `contents` list:
 * vertices/axes carry stable keys for the editable tables; string decimals
 * stay strings until the request is built. */
export interface SectionVertexDraft {
  key: string;
  x_mm: string;
  y_mm: string;
}

export interface SectionAxisDraft {
  key: string;
  name: string;
  y_mm: string;
}

export type SectionOrientation =
  "EXTERIOR_DOWN" | "EXTERIOR_UP" | "EXTERIOR_LEFT" | "EXTERIOR_RIGHT";
export type SectionLocalOrigin =
  "TOP_LEFT" | "TOP_RIGHT" | "BOTTOM_LEFT" | "BOTTOM_RIGHT" | "CENTROID";

export interface SectionDraft {
  enabled: boolean;
  source: "POLYGON" | "DXF_REFERENCE";
  depth_mm: string;
  drawing_ref: string;
  orientation: SectionOrientation;
  local_origin: SectionLocalOrigin;
  vertices: SectionVertexDraft[];
  axes: SectionAxisDraft[];
}

export function initialSectionDraft(section: ProfileSection | null | undefined): SectionDraft {
  return {
    enabled: section != null,
    source: section?.source === "DXF_REFERENCE" ? "DXF_REFERENCE" : "POLYGON",
    depth_mm: section?.depth_mm ?? "",
    drawing_ref: section?.drawing_ref ?? "",
    orientation: section?.orientation ?? "EXTERIOR_DOWN",
    local_origin: section?.local_origin ?? "TOP_LEFT",
    vertices: (section?.polygon ?? []).map((point) => ({
      key: crypto.randomUUID(),
      x_mm: point.x_mm,
      y_mm: point.y_mm,
    })),
    axes: (section?.axes ?? []).map((axis) => ({
      key: crypto.randomUUID(),
      name: axis.name,
      y_mm: axis.y_mm,
    })),
  };
}

export function sectionFromDraft(draft: SectionDraft | undefined): ProfileSectionRequest | null {
  if (!draft?.enabled) return null;
  const polygon = draft.vertices.map((vertex) => ({
    x_mm: exact(vertex.x_mm),
    y_mm: exact(vertex.y_mm),
  }));
  const depth = exact(draft.depth_mm);
  const drawingRef = draft.drawing_ref.trim();
  if (
    polygon.length < 3 ||
    polygon.some((point) => point.x_mm === "" || point.y_mm === "") ||
    depth === "" ||
    (draft.source === "DXF_REFERENCE" && drawingRef === "")
  ) {
    throw new Error("Invalid section");
  }
  return {
    source: draft.source,
    polygon,
    depth_mm: depth,
    orientation: draft.orientation,
    local_origin: draft.local_origin,
    axes: draft.axes
      .filter((axis) => axis.name.trim() !== "" || axis.y_mm.trim() !== "")
      .map((axis) => ({ name: axis.name.trim(), y_mm: exact(axis.y_mm) })),
    drawing_ref: drawingRef === "" ? null : drawingRef,
  };
}

/** Loose preview of the in-progress draft — tolerates empty cells so the
 * editor shows the shape while the user is still typing it. */
export function sectionPreviewFromDraft(draft: SectionDraft): ProfileSection | null {
  if (!draft.enabled || draft.vertices.length < 3) return null;
  return {
    source: draft.source,
    polygon: draft.vertices.map((vertex) => ({
      x_mm: vertex.x_mm || "0",
      y_mm: vertex.y_mm || "0",
    })),
    depth_mm: draft.depth_mm || "0",
    orientation: draft.orientation,
    local_origin: draft.local_origin,
    axes: draft.axes
      .filter((axis) => axis.name.trim() !== "")
      .map((axis) => ({ name: axis.name.trim(), y_mm: axis.y_mm || "0" })),
    drawing_ref: draft.drawing_ref.trim() || null,
  };
}

export function fieldsFor(resource: Resource): Field[] {
  return schemas[resource].flatMap((group) => group.fields);
}

export function initialDraft(
  resource: Resource,
  row: object | undefined,
  systemId: string | null,
): Record<string, string> {
  const source = (row ?? {}) as Record<string, unknown>;
  return Object.fromEntries(
    fieldsFor(resource).map((field) => [
      field.name,
      source[field.name] == null
        ? field.name === "system_id"
          ? (systemId ?? "")
          : // A required select renders its first option visually; the draft
            // must start there too or it would silently submit "".
            row === undefined && field.kind === "select" && !field.optional
            ? (field.options?.[0] ?? "")
            : row === undefined && field.kind === "boolean"
              ? "true"
              : ""
        : Array.isArray(source[field.name])
          ? (source[field.name] as string[]).join(", ")
          : String(source[field.name]),
    ]),
  );
}

export function writeFromDraft<R extends Resource>(
  resource: R,
  draft: Record<string, string>,
  contents: HardwareComponent[],
  section?: SectionDraft,
): Writes[R] {
  const values: Record<
    string,
    string | number | boolean | null | string[] | HardwareComponent[] | ProfileSectionRequest
  > = {};
  for (const field of fieldsFor(resource)) {
    const value = draft[field.name]?.trim() ?? "";
    if (field.kind === "csv") {
      values[field.name] = value
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item !== "");
    } else if (value === "" && field.optional) {
      values[field.name] = null;
    } else if (field.kind === "integer") {
      // Integer counters only; never dimensions, weights, quantities or money.
      const count = Number(value);
      if (
        !/^-?\d+$/.test(value) ||
        !Number.isSafeInteger(count) ||
        count < -2147483648 ||
        count > 2147483647
      )
        throw new Error(`Invalid integer: ${field.name}`);
      values[field.name] = count;
    } else if (field.kind === "boolean") {
      if (value !== "true" && value !== "false") throw new Error(`Missing boolean: ${field.name}`);
      values[field.name] = value === "true";
    } else if (field.kind === "processProfile") {
      values[field.name] = value === "" ? null : value;
    } else {
      values[field.name] = field.kind === "decimal" ? exact(value) : value;
    }
  }
  if (resource === "hardware-kits") {
    values.contents = contents.map((item) => ({
      sku: item.sku.trim(),
      name: item.name.trim(),
      qty: exact(item.qty),
      unit: item.unit.trim(),
      category: item.category ?? "OTHER",
    }));
  }
  if (resource === "articles") {
    values.section = sectionFromDraft(section);
  }
  // Only schema-declared writable fields enter the request.
  return values as unknown as Writes[R];
}

export function catalogApi(orgId: string) {
  const options = { headers: { "X-Organization-ID": orgId } };
  return {
    async list<R extends Resource>(resource: R, signal?: AbortSignal): Promise<Row<R>[]> {
      const request = { ...options, signal };
      const response =
        resource === "systems"
          ? await client.catalogSystemList(request)
          : resource === "articles"
            ? await client.catalogArticleList(undefined, request)
            : resource === "glazing"
              ? await client.catalogBeadList(undefined, request)
              : await client.catalogKitList(undefined, request);
      if (response.status !== 200) throw new Error("catalog_read_failed");
      return response.data.items as Row<R>[];
    },
    async save<R extends Resource>(
      resource: R,
      body: Writes[R],
      id?: string,
      revision?: string,
    ): Promise<Row<R>> {
      const options = {
        headers: { "X-Organization-ID": orgId, ...(id ? { "If-Match": `"${revision}"` } : {}) },
      };
      const response =
        resource === "systems"
          ? id
            ? await client.catalogSystemUpdate(id, body as SystemWrite, options)
            : await client.catalogSystemCreate(body as SystemWrite, options)
          : resource === "articles"
            ? id
              ? await client.catalogArticleUpdate(id, body as ArticleWrite, options)
              : await client.catalogArticleCreate(body as ArticleWrite, options)
            : resource === "glazing"
              ? id
                ? await client.catalogBeadUpdate(id, body as BeadWrite, options)
                : await client.catalogBeadCreate(body as BeadWrite, options)
              : id
                ? await client.catalogKitUpdate(id, body as KitWrite, options)
                : await client.catalogKitCreate(body as KitWrite, options);
      if (response.status !== 200 && response.status !== 201)
        throw new Error("catalog_write_failed");
      return response.data as Row<R>;
    },
    async workspace(systemId: string, signal?: AbortSignal): Promise<SystemWorkspace> {
      const response = await client.catalogSystemWorkspace(systemId, {
        ...options,
        signal,
      });
      if (response.status !== 200) throw new Error("catalog_read_failed");
      return response.data;
    },
    async sectionImport(file: File): Promise<SectionImportResponse> {
      const response = await client.catalogSectionImportCreate({ file }, options);
      if (response.status !== 200) {
        const detail = (response.data as ErrorResponse).error;
        throw new Error(detail?.code ?? "section_import_failed");
      }
      return response.data;
    },
    async processProfiles(signal?: AbortSignal): Promise<ProcessProfileOption[]> {
      const response = await client.catalogProcessProfileList({ ...options, signal });
      if (response.status !== 200) throw new Error("catalog_read_failed");
      return response.data.items;
    },
    async workCenters(signal?: AbortSignal): Promise<WorkCenter[]> {
      const response = await client.productionWorkCenters({ ...options, signal });
      if (response.status !== 200) throw new Error("work_centers_read_failed");
      return response.data.centers;
    },
    async upsertWorkCenter(body: WorkCenterRequestRequest): Promise<WorkCenter> {
      const response = await client.productionWorkCentersCreate(body, options);
      if (response.status !== 200 && response.status !== 201) {
        const detail = (response.data as ErrorResponse).error;
        throw new Error(detail?.code ?? "work_center_write_failed");
      }
      return response.data;
    },
    async seedWorkCenters(): Promise<WorkCenter[]> {
      const response = await client.productionWorkCentersSeedDefaults(options);
      if (response.status !== 200) throw new Error("work_centers_seed_failed");
      return response.data.centers;
    },
    async review<R extends Resource>(resource: R, row: Row<R>): Promise<Row<R>> {
      // If-Match is required by the API: a review must approve the revision
      // the reviewer actually read, not a later edit (409 on drift).
      const headers = {
        headers: {
          ...options.headers,
          "If-Match": `"${(row as { revision?: string }).revision ?? ""}"`,
        },
      };
      const response =
        resource === "systems"
          ? await client.catalogSystemReview(row.id, headers)
          : resource === "articles"
            ? await client.catalogArticleReview(row.id, headers)
            : resource === "glazing"
              ? await client.catalogBeadReview(row.id, headers)
              : await client.catalogKitReview(row.id, headers);
      if (response.status !== 200) throw new Error("catalog_review_failed");
      return response.data as Row<R>;
    },
    async remove(resource: Resource, id: string, revision: string): Promise<void> {
      const options = { headers: { "X-Organization-ID": orgId, "If-Match": `"${revision}"` } };
      const response =
        resource === "systems"
          ? await client.catalogSystemDelete(id, options)
          : resource === "articles"
            ? await client.catalogArticleDelete(id, options)
            : resource === "glazing"
              ? await client.catalogBeadDelete(id, options)
              : await client.catalogKitDelete(id, options);
      if (response.status !== 204) throw new Error("catalog_delete_failed");
    },
  };
}
