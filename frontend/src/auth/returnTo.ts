// Return-to-destination: a guarded deep link (/projects/…/edit) must survive
// the magic-link round trip through email. The guard hands `from` via router
// state; LoginPage stashes it in sessionStorage (router state dies when the
// mail client opens the link); the post-auth pages consume it. Validation
// keeps it an in-app path — never an open redirect.

const KEY = "dk:returnTo";

function isSafeInternalPath(path: string): boolean {
  return (
    path.startsWith("/") &&
    !path.startsWith("//") &&
    !path.includes("\\") &&
    !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path) &&
    path !== "/login" &&
    !path.startsWith("/auth/") // /auth/callback would loop
  );
}

export function stashReturnTo(path: string | undefined | null): void {
  try {
    if (path && isSafeInternalPath(path)) sessionStorage.setItem(KEY, path);
  } catch {
    /* storage unavailable — fall back to the default home */
  }
}

export function consumeReturnTo(fallback = "/dashboard"): string {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return raw && isSafeInternalPath(raw) ? raw : fallback;
  } catch {
    return fallback;
  }
}
