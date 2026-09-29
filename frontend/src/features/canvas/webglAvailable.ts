let probed: boolean | null = null;

/** Cheap WebGL capability probe — deliberately lives outside renderStudio so
 * callers can feature-gate without pulling three.js into the main bundle. */
export function webglAvailable(): boolean {
  if (probed !== null) return probed;
  try {
    const canvas = document.createElement("canvas");
    probed = Boolean(
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl"),
    );
  } catch {
    probed = false;
  }
  return probed;
}
