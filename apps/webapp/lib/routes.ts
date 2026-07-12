export const productRoutes = [
  { id: "overview", labelKey: "nav.overview", group: "workspace" },
  { id: "projects", labelKey: "nav.projects", group: "workspace" },
  { id: "runs", labelKey: "nav.runs", group: "evaluate" },
  { id: "case", labelKey: "nav.case", group: "evaluate" },
  { id: "review", labelKey: "nav.review", group: "release" },
  { id: "reports", labelKey: "nav.reports", group: "release" },
  { id: "delivery", labelKey: "nav.delivery", group: "release" },
  { id: "api-reference", labelKey: "nav.apiReference", group: "developer" },
  { id: "team", labelKey: "nav.team", group: "manage" },
  { id: "billing", labelKey: "nav.billing", group: "manage" },
  { id: "trust", labelKey: "nav.trust", group: "manage" },
  { id: "login", labelKey: "nav.login", group: "account" }
] as const;

export type ProductRoute = (typeof productRoutes)[number]["id"];

export const generatedRoutes = productRoutes.map((route) => route.id);

export function isProductRoute(value: string): value is ProductRoute {
  return generatedRoutes.includes(value as ProductRoute);
}
