export type ApiAuthContext = {
  accessToken: string | null;
  organizationId: string | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, payload: unknown) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

let readAuthContext: () => Promise<ApiAuthContext> = async () => ({
  accessToken: null,
  organizationId: null,
});

export function configureApiAuthContext(provider: () => Promise<ApiAuthContext>): () => void {
  readAuthContext = provider;
  return () => {
    readAuthContext = async () => ({ accessToken: null, organizationId: null });
  };
}

export async function apiMutator<T>(url: string, options: RequestInit): Promise<T> {
  const context = await readAuthContext();
  const headers = new Headers(options.headers);
  const requestedOrganization = headers.get("X-Organization-ID");
  if (requestedOrganization !== null && requestedOrganization !== context.organizationId) {
    throw new ApiError(409, { error: { code: "stale_organization" } });
  }
  headers.set("Accept", "application/json");
  if (context.accessToken !== null) {
    headers.set("Authorization", `Bearer ${context.accessToken}`);
  }
  if (context.organizationId !== null) {
    headers.set("X-Organization-ID", context.organizationId);
  }

  const response = await fetch(url, { ...options, headers });
  const text = await response.text();
  const contentType = response.headers.get("Content-Type") ?? "";
  const payload: unknown =
    text.length === 0 ? null : contentType.includes("application/json") ? JSON.parse(text) : text;
  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }
  return { data: payload, status: response.status, headers: response.headers } as T;
}

/** Binary download through the same auth context — the generated client
 * stringifies bodies, so PDF/stream endpoints fetch the Blob directly. */
export async function apiFetchBlob(url: string): Promise<{
  blob: Blob;
  filename: string | null;
}> {
  const context = await readAuthContext();
  const headers = new Headers();
  if (context.accessToken !== null) {
    headers.set("Authorization", `Bearer ${context.accessToken}`);
  }
  if (context.organizationId !== null) {
    headers.set("X-Organization-ID", context.organizationId);
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";\n]+)"?/.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}
