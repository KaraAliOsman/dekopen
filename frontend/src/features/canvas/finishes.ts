import type { ColorOptionChoice } from "../../api/generated/models";

/** D05: the catalog's declared render record per face — hex swatch + optional
 * grain texture, stamped onto every member spec of a design that picked real
 * finishes. An empty face keeps the material's token colors (binary-era
 * finishes carry no render record). */
export type FinishFace = {
  color?: string | null;
  texture?: string | null;
};

/** The position's two renderable faces — the same option unless bicolor. */
export type MemberFinish = {
  exterior: FinishFace;
  interior: FinishFace;
};

/** Catalog option rows and sealed `color_*_detail` blobs share the same
 * `render_*` keys — the selector, the 2D/3D renders, the portal thumbnail
 * and the PDF all read the face through this one projection. Values arrive
 * typed as the catalog row and untyped as the sealed dict, so the fields
 * are narrowed here, once. */
type FaceSource = { render_color?: unknown; render_texture?: unknown } | null | undefined;

export function finishFace(source: FaceSource): FinishFace {
  if (!source || typeof source !== "object") return {};
  const color = source.render_color;
  const texture = source.render_texture;
  return {
    color: typeof color === "string" && color !== "" ? color : null,
    texture: typeof texture === "string" && texture !== "" ? texture : null,
  };
}

/** A face with a real render record — used to decide whether the picked
 * finish should override the material's token colors at all. */
export function finishFaceReal(face: FinishFace | undefined): face is FinishFace {
  return !!face && (face.color != null || face.texture != null);
}

/** Picked codes → both faces. Returns undefined when the series exposes no
 * finish catalog or neither face resolved a render record — binary-era
 * systems keep their material tokens unchanged. */
export function finishForSelection(
  options: readonly ColorOptionChoice[] | undefined,
  interiorCode: string,
  exteriorCode?: string | null,
): MemberFinish | undefined {
  if (!options || options.length === 0) return undefined;
  const interior = finishFace(options.find((option) => option.code === interiorCode));
  const exterior = finishFace(
    options.find((option) => option.code === (exteriorCode || interiorCode)),
  );
  if (!finishFaceReal(interior) && !finishFaceReal(exterior)) return undefined;
  return { exterior, interior };
}

/** Darken a `#rrggbb` swatch for edge strokes — same formula the PDF uses so
 * the canvas outline reads like the emitted document. */
export function darkenHex(value: string, amount = 0.55): string {
  const match = /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(value.trim());
  if (!match) return value;
  const channel = (index: number) =>
    Math.round(parseInt(match[index]!, 16) * amount)
      .toString(16)
      .padStart(2, "0");
  return `#${channel(1)}${channel(2)}${channel(3)}`;
}

/** Lighten toward white for the inner highlight stroke. */
export function lightenHex(value: string, amount = 0.45): string {
  const match = /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(value.trim());
  if (!match) return value;
  const channel = (index: number) =>
    Math.min(
      255,
      Math.round(parseInt(match[index]!, 16) + (255 - parseInt(match[index]!, 16)) * amount),
    )
      .toString(16)
      .padStart(2, "0");
  return `#${channel(1)}${channel(2)}${channel(3)}`;
}
