/** Compact 14px stroke icons for the domain rail — one visual anchor per
 * destination; labels stay textual (icons alone are never the affordance). */

const P = {
  dashboard: (
    <>
      <rect x="1.5" y="1.5" width="4.6" height="4.6" rx="0.6" />
      <rect x="7.9" y="1.5" width="4.6" height="4.6" rx="0.6" />
      <rect x="1.5" y="7.9" width="4.6" height="4.6" rx="0.6" />
      <rect x="7.9" y="7.9" width="4.6" height="4.6" rx="0.6" />
    </>
  ),
  projects: (
    <>
      <rect x="2" y="3" width="10" height="8" rx="0.8" />
      <path d="M7 3v8M2 7h10" />
    </>
  ),
  clients: (
    <>
      <circle cx="7" cy="4.6" r="2.4" />
      <path d="M2.4 12c.6-2.4 2.4-3.6 4.6-3.6S11 9.6 11.6 12" />
    </>
  ),
  sales: (
    <>
      <path d="M2 4h10v7H2z" />
      <path d="M2 6h10M4.5 9h3" />
    </>
  ),
  catalog: (
    <>
      <path d="M2.5 2.5h3.4v9H2.5zM5.9 2.5h4.6l1 9H7z" />
    </>
  ),
  purchasing: (
    <>
      <path d="M1.8 2.6h1.6l1.2 6.2h6.8l1-4.4H4" />
      <circle cx="5.4" cy="11.4" r="1" />
      <circle cx="10.6" cy="11.4" r="1" />
    </>
  ),
  production: (
    <>
      <circle cx="7" cy="7" r="2.4" />
      <path d="M7 1.6v1.8M7 10.6v1.8M1.6 7h1.8M10.6 7h1.8M3.2 3.2l1.3 1.3M9.5 9.5l1.3 1.3M10.8 3.2 9.5 4.5M4.5 9.5 3.2 10.8" />
    </>
  ),
  assistant: (
    <>
      <circle cx="7" cy="7" r="5" />
      <circle cx="5.3" cy="6.6" r="0.75" />
      <circle cx="8.7" cy="6.6" r="0.75" />
    </>
  ),
  jobs: (
    <>
      <path d="M2.5 3.4h9M2.5 7h9M2.5 10.6h5.5" />
    </>
  ),
  quotations: (
    <>
      <path d="M3 1.8h6.4L12 4.4V12H3z" />
      <path d="M9.4 1.8v2.8H12M5.2 7h3.6M5.2 9.6h3.6" />
    </>
  ),
  inventory: (
    <>
      <path d="M2 4.6h10v7H2z" />
      <path d="M2 7.8h10M7 4.6v7" />
    </>
  ),
  deliveries: (
    <>
      <path d="M1.8 8.8h8.4V4.4H1.8z" />
      <path d="M10.2 6.4h1.6l1.4 1.8v0.6h-3" />
      <circle cx="4.4" cy="10.8" r="1.1" />
      <circle cx="9.6" cy="10.8" r="1.1" />
    </>
  ),
  settings: (
    <>
      <circle cx="7" cy="7" r="2" />
      <path d="M7 1.8v1.6M7 10.6v1.6M1.8 7h1.6M10.6 7h1.6M3.3 3.3l1.1 1.1M9.6 9.6l1.1 1.1M10.7 3.3 9.6 4.4M4.4 9.6 3.3 10.7" />
    </>
  ),
};

const routeIcon: Record<string, keyof typeof P> = {
  "/dashboard": "dashboard",
  "/projects": "projects",
  "/clients": "clients",
  "/quotations": "quotations",
  "/pricing/commercial": "sales",
  "/catalogs/systems": "catalog",
  "/purchasing": "purchasing",
  "/inventory": "inventory",
  "/production": "production",
  "/deliveries": "deliveries",
  "/assistant": "assistant",
  "/jobs": "jobs",
  "/settings/general": "settings",
};

export function RailIcon({ to }: { to: string }): JSX.Element | null {
  const key = routeIcon[to];
  if (!key) return null;
  return (
    <svg
      aria-hidden="true"
      className="rail-item__icon"
      fill="none"
      height="14"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.3"
      viewBox="0 0 14 14"
      width="14"
    >
      {P[key]}
    </svg>
  );
}
