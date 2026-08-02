"use client";

import type { ProductRoute } from "@/lib/routes";
import { DashboardProvider } from "./dashboard-provider";
import { I18nProvider } from "@/lib/i18n";
import { AppShell } from "./app-shell";
import { LoginPage } from "./pages/login-page";
import { OverviewPage } from "./pages/overview-page";
import { ProjectsPage } from "./pages/projects-page";
import { RunsPage } from "./pages/runs-page";
import { CasePage } from "./pages/case-page";
import { ReviewPage } from "./pages/review-page";
import { ReportsPage } from "./pages/reports-page";
import { DeliveryPage } from "./pages/delivery-page";
import { ApiReferencePage } from "./pages/api-reference-page";
import { TeamPage } from "./pages/team-page";
import { BillingPage } from "./pages/billing-page";
import { TrustPage } from "./pages/trust-page";

const pages = {
  overview: OverviewPage,
  projects: ProjectsPage,
  runs: RunsPage,
  case: CasePage,
  review: ReviewPage,
  reports: ReportsPage,
  delivery: DeliveryPage,
  "api-reference": ApiReferencePage,
  team: TeamPage,
  billing: BillingPage,
  trust: TrustPage
} satisfies Record<Exclude<ProductRoute, "login">, React.ComponentType>;

export function ProductApp({ route }: { route: ProductRoute }) {
  return (
    <I18nProvider>
      <DashboardProvider>
        {route === "login" ? <LoginPage /> : (
          <AppShell route={route}>
            {(() => {
              const Page = pages[route];
              return <Page />;
            })()}
          </AppShell>
        )}
      </DashboardProvider>
    </I18nProvider>
  );
}
