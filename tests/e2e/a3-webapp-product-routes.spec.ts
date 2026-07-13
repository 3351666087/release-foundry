import { expect, test, type Page } from "@playwright/test";

const base = "/apps/webapp/out";
const dataRoutes = [
  ["overview", "发布总览"],
  ["projects", "项目工作区"],
  ["runs", "运行与案例"],
  ["review", "人工审核"],
  ["reports", "报告中心"],
  ["delivery", "交付闭环"],
  ["api-reference", "API 文档与参考"],
  ["team", "团队与权限"],
  ["billing", "用量与计费"],
  ["trust", "信任与审计"]
] as const;

test.describe("A3 Next.js product console", () => {
  test("renders the route-level workflow on the same A1/A2 evidence", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 1000 });

    for (const [route, title] of dataRoutes) {
      await page.goto(`${base}/${route}/`);
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
      await expect(page.locator(".sidebar-contract")).toContainText("32 个案例");
      await expect(page.locator(".source-control select")).toHaveValue("api-mock");
    }

    await page.goto(`${base}/case/`);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.locator(".comparison-panel.expected-panel")).toContainText("预期结果");
    await expect(page.locator(".comparison-panel.actual-panel")).toContainText("实际结果");
    await expect(page.locator(".trace-list")).toBeVisible();
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-case-detail-desktop.png", fullPage: false });

    await page.goto(`${base}/login/`);
    await expect(page.getByRole("heading", { name: "进入工作区" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Google 登录待接入/ })).toBeDisabled();
    await expect(page.getByRole("button", { name: /GitHub 登录待接入/ })).toBeDisabled();
    await expect(page.locator(".auth-roadmap")).toContainText("身份服务未连接");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-login-desktop.png", fullPage: false });

    expect(consoleErrors).toEqual([]);
  });

  test("keeps the overview visually bounded and navigates through real routes", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/overview/`);
    await expect(page.getByRole("heading", { name: "发布总览" })).toBeVisible();
    await expect(page.locator(".release-signal .status-badge")).toHaveText("integrity_invalid");
    await expect(page.locator(".release-signal .status-badge")).toHaveClass(/status-fail/);
    await expect(page.locator(".release-signal")).toContainText("当前不得发布");
    await expect(page.locator(".release-signal")).toContainText("evidence_scope_mismatch");
    await expect(page.locator(".partial-data-state")).toHaveCount(0);

    const visual = await page.evaluate(() => {
      const painted = [...document.querySelectorAll<HTMLElement>("body, body *")];
      const command = document.querySelector<HTMLElement>(".command-bar")!;
      const header = document.querySelector<HTMLElement>(".page-header")!;
      return {
        documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        gradients: painted.filter((node) => getComputedStyle(node).backgroundImage.includes("gradient(")).length,
        nonZeroLetterSpacing: painted.filter((node) => !["0px", "normal"].includes(getComputedStyle(node).letterSpacing)).length,
        radiiOverEight: painted.filter((node) => Number.parseFloat(getComputedStyle(node).borderRadius) > 8).length,
        headerBelowCommand: header.getBoundingClientRect().top >= command.getBoundingClientRect().bottom,
        sectionTitleSize: getComputedStyle(document.querySelector(".section-heading h2")!).fontSize
      };
    });

    expect(visual.documentOverflow).toBe(false);
    expect(visual.gradients).toBe(0);
    expect(visual.nonZeroLetterSpacing).toBe(0);
    expect(visual.radiiOverEight).toBe(0);
    expect(visual.headerBelowCommand).toBe(true);
    expect(Number.parseFloat(visual.sectionTitleSize)).toBeGreaterThanOrEqual(27);
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-overview-desktop.png", fullPage: false });

    const runsLink = page.locator('aside.app-sidebar a[href="/apps/webapp/out/runs/"]');
    await expect(runsLink).toHaveCount(1);
    await runsLink.click();
    await expect(page).toHaveURL(new RegExp(`${base}/runs/?$`));
    await expect(page.getByRole("heading", { name: "运行与案例" })).toBeVisible();
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");

    await page.screenshot({ path: "docs/screenshots/a3-webapp-runs-desktop.png", fullPage: false });
  });

  test("paginates the case queue instead of producing a text wall", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/runs/`);
    await expect(page.getByRole("heading", { name: "运行与案例" })).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(10);
    await expect(page.locator(".table-pagination")).toContainText("第 1 / 4 页");

    const nextPage = page.getByRole("button", { name: "下一页" });
    await expect(nextPage).toBeEnabled();
    await nextPage.click();
    await expect(page.locator(".table-pagination")).toContainText("第 2 / 4 页");

    await page.getByPlaceholder("搜索案例、场景或失败分类").fill("hallucinated_tool_result");
    await expect(page.locator(".table-pagination")).toContainText("第 1 / 1 页");
  });

  test("shows the new-run delivery golden path without overstating production readiness", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=a3-golden-path`);
    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("a3-golden-path");
    await expect(page.locator(".delivery-signal")).toContainText("候选证据绑定无效");
    await expect(page.locator(".delivery-signal")).toContainText("integrity_invalid");
    await expect(page.locator(".delivery-stage-list article")).toHaveCount(11);
    await expect(page.locator('.delivery-stage-list article[data-status="passed"]')).toHaveCount(7);
    await expect(page.getByText("权威决策账本允许发布", { exact: true })).toBeVisible();
    await expect(page.getByText("Tenant-bound GitHub App installation", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Required Check enforced on main", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("GitHub Actions artifact live readback", { exact: true }).first()).toBeVisible();
    const bounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      routeRight: document.querySelector(".route-content")!.getBoundingClientRect().right
    }));
    expect(bounds.documentScrollWidth).toBeLessThanOrEqual(bounds.viewport);
    expect(bounds.routeRight).toBeLessThanOrEqual(bounds.viewport);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-golden-path-desktop.png", fullPage: false });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await expect(page.locator(".delivery-signal")).toContainText("Golden Path 通过 7/11");
    await page.waitForTimeout(500);
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    const mobileBounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      signalRight: document.querySelector(".delivery-signal")!.getBoundingClientRect().right,
      mobileNavDisplay: getComputedStyle(document.querySelector(".mobile-route-nav")!).display
    }));
    expect(mobileBounds.documentScrollWidth).toBeLessThanOrEqual(mobileBounds.viewport);
    expect(mobileBounds.bodyScrollWidth).toBeLessThanOrEqual(mobileBounds.viewport);
    expect(mobileBounds.signalRight).toBeLessThanOrEqual(mobileBounds.viewport);
    expect(mobileBounds.mobileNavDisplay).toBe("grid");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-golden-path-mobile-390x844.png", fullPage: false });
  });

  test("shows rc.2 repair while sealed A2 block and current candidate integrity stay separate", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=a3-golden-path-rc2`);

    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("a3-golden-path-rc2");
    await expect(page.locator(".metric-strip")).toContainText("7/11");
    await expect(page.locator(".page-header")).toContainText("0.2.0-rc.2");
    await expect(page.locator(".delivery-signal")).toContainText("候选证据绑定无效");
    await expect(page.locator(".delivery-signal")).toContainText("evidence_scope_mismatch");
    await expect(page.locator('.delivery-stage-list article[data-status="passed"]')).toHaveCount(7);
    const newRunEvidence = page.locator("section").filter({ has: page.getByRole("heading", { name: "新 Run 证据" }) });
    await expect(newRunEvidence).toContainText("执行结果");
    await expect(newRunEvidence).toContainText("案例评分");
    await expect(newRunEvidence).toContainText("3/3");
    await expect(newRunEvidence).toContainText("4");
    await expect(newRunEvidence).toContainText("unknown");
    const candidateBinding = page.locator("section").filter({ has: page.getByRole("heading", { name: "同一候选绑定校验" }) });
    await expect(candidateBinding).toContainText("a3-golden-20260712-002");
    await expect(candidateBinding).toContainText("a2_trusted_spine_demo");
    await expect(candidateBinding).toContainText("integrity_invalid");
    await expect(candidateBinding).toContainText("历史封存包");
    await expect(candidateBinding).toContainText("block");
    await expect(candidateBinding.locator('.candidate-binding-checks article[data-status="passed"]')).toHaveCount(2);
    await expect(candidateBinding.locator('.candidate-binding-checks article[data-status="failed"]')).toHaveCount(3);
    await candidateBinding.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-candidate-binding-rc2-desktop.png", fullPage: false, animations: "disabled" });
    const releaseComparison = page.locator("section").filter({ has: page.getByRole("heading", { name: "版本对比：rc.1 → rc.2" }) });
    await expect(releaseComparison).toContainText("案例质量已修复，当前候选绑定无效");
    await expect(releaseComparison).toContainText("1/3");
    await expect(releaseComparison).toContainText("3/3");
    await expect(releaseComparison).toContainText("missing_required_tool");
    await expect(releaseComparison).toContainText("0");
    await expect(releaseComparison).toContainText("4");
    await expect(releaseComparison).toContainText("block");
    await expect(releaseComparison).toContainText("integrity_invalid");
    await expect(releaseComparison).toContainText("质量提升不等于发布批准");
    await releaseComparison.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-release-comparison-rc1-rc2-desktop.png", fullPage: false, animations: "disabled" });
    const deploymentHandoff = page.locator("section").filter({ has: page.getByRole("heading", { name: "部署交接：按负责人拆分" }) });
    await expect(deploymentHandoff.locator(".deployment-owner-grid article")).toHaveCount(5);
    await expect(deploymentHandoff.locator("tbody tr")).toHaveCount(9);
    await expect(deploymentHandoff).toContainText("产品工作流");
    await expect(deploymentHandoff).toContainText("6/6");
    await expect(deploymentHandoff).toContainText("Tenant-bound GitHub App installation");
    await expect(deploymentHandoff).toContainText("Required Check enforced on main");
    await expect(deploymentHandoff.locator("details")).not.toHaveAttribute("open", "");
    await deploymentHandoff.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-deployment-handoff-rc2-desktop.png", fullPage: false, animations: "disabled" });
    await expect(page.getByText("权威决策账本允许发布", { exact: true }).first()).toBeVisible();
    const githubReadback = page.locator("section").filter({ has: page.getByRole("heading", { name: "GitHub 真实回读" }) });
    await expect(githubReadback).toContainText("github-actions");
    await expect(githubReadback).toContainText("86656698704");
    await expect(githubReadback).toContainText("4951428174");
    await expect(githubReadback).toContainText("8260724828");
    await expect(githubReadback).toContainText("main 返回 404");
    await expect(githubReadback).toContainText("不是发布批准");
    const githubLinks = await githubReadback.locator("a").evaluateAll((links) => links.map((link) => ({
      href: (link as HTMLAnchorElement).href,
      target: (link as HTMLAnchorElement).target,
      rel: (link as HTMLAnchorElement).rel
    })));
    expect(githubLinks.length).toBe(3);
    expect(githubLinks.every((link) => link.href.startsWith("https://github.com/"))).toBe(true);
    expect(githubLinks.every((link) => link.target === "_blank" && link.rel.includes("noreferrer"))).toBe(true);
    await githubReadback.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-github-readback-rc2-desktop.png", fullPage: false, animations: "disabled" });
    await page.getByRole("button", { name: "EN", exact: true }).click();
    const englishReadback = page.locator("section").filter({ has: page.getByRole("heading", { name: "Live GitHub readback" }) });
    await expect(englishReadback).toContainText("not enforced");
    await expect(englishReadback).toContainText("release approval");
    await expect(page.getByRole("heading", { name: "Release comparison: rc.1 → rc.2" })).toBeVisible();
    await expect(page.getByText("Case quality repaired; current candidate binding invalid")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Same-candidate binding" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Deployment handoff by owner" })).toBeVisible();
    await page.getByRole("button", { name: "中", exact: true }).click();
    await expect(page.getByRole("heading", { name: "GitHub 真实回读" })).toBeVisible();
    const releaseArtifact = page.locator("section").filter({ has: page.getByRole("heading", { name: "版本化 Release Artifact" }) });
    await expect(releaseArtifact).toContainText("c8420813ed6cb94535bd108b30bd97663b906bdb");
    await expect(releaseArtifact).toContainText("746ecbe959a9c8781e8e1fc7d2520a50fd92785b");
    await expect(releaseArtifact).toContainText("no");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-golden-path-rc2-desktop.png", fullPage: false, animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    const mobileReleaseComparison = page.locator("section").filter({ has: page.getByRole("heading", { name: "版本对比：rc.1 → rc.2" }) });
    await expect(mobileReleaseComparison).toBeVisible();
    await mobileReleaseComparison.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 64);
    });
    await page.screenshot({ path: "docs/screenshots/a3-webapp-release-comparison-rc1-rc2-mobile-390x844.png", fullPage: false, animations: "disabled" });
    const mobileCandidateBinding = page.locator("section").filter({ has: page.getByRole("heading", { name: "同一候选绑定校验" }) });
    await mobileCandidateBinding.scrollIntoViewIfNeeded();
    await expect(mobileCandidateBinding).toContainText("a2_trusted_spine_demo");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-candidate-binding-rc2-mobile-390x844.png", fullPage: false, animations: "disabled" });
    const mobileDeploymentHandoff = page.locator("section").filter({ has: page.getByRole("heading", { name: "部署交接：按负责人拆分" }) });
    await mobileDeploymentHandoff.scrollIntoViewIfNeeded();
    await expect(mobileDeploymentHandoff.locator(".deployment-owner-grid article")).toHaveCount(5);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-deployment-handoff-rc2-mobile-390x844.png", fullPage: false, animations: "disabled" });
    const mobileGithubReadback = page.locator("section").filter({ has: page.getByRole("heading", { name: "GitHub 真实回读" }) });
    await mobileGithubReadback.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 70);
    });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(300);
    await expect(mobileGithubReadback).toContainText("8260724828");
    const mobileBounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      signalRight: document.querySelector(".delivery-signal")!.getBoundingClientRect().right
    }));
    expect(mobileBounds.documentScrollWidth).toBeLessThanOrEqual(mobileBounds.viewport);
    expect(mobileBounds.bodyScrollWidth).toBeLessThanOrEqual(mobileBounds.viewport);
    expect(mobileBounds.signalRight).toBeLessThanOrEqual(mobileBounds.viewport);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-github-readback-rc2-mobile-390x844.png", fullPage: false, animations: "disabled" });
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-delivery-golden-path-rc2-mobile-390x844.png", fullPage: false, animations: "disabled" });
  });

  test("renders A1 self-host sandbox evidence separately from production deployment", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=a3-golden-path-rc2`);
    const section = page.locator("section.self-host-sandbox-section");
    await expect(section.getByRole("heading", { name: "自托管沙箱校准" })).toBeVisible();
    await expect(section.locator('.self-host-sandbox[data-sandbox-state="ready"]')).toBeVisible();
    await expect(section.locator(".sandbox-verdict-score")).toContainText("4/4");
    await expect(section.locator(".sandbox-production-boundary")).toContainText("这不是生产部署证明");
    await expect(section.locator(".sandbox-production-boundary")).toContainText("部署验收 8/17");
    await expect(section.locator(".sandbox-production-boundary")).toContainText("生产验证 0");
    await expect(section.locator('.sandbox-postgres-qualification[data-postgres-state="postgres_rls_verified"]')).toBeVisible();
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("PostgreSQL 五层租户隔离已验证");
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("PostgreSQL 17.9");
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("019_to_020_self_host_sandbox_rls");
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("ENABLED + FORCED");
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("写入已拒绝");
    await expect(section.locator(".sandbox-postgres-qualification")).toContainText("部署验收仍为 8/17");
    await expect(section.locator(".sandbox-check-grid article")).toHaveCount(4);
    await expect(section.locator(".sandbox-check-grid article[data-status='passed']")).toHaveCount(4);
    await expect(section.locator("tbody tr")).toHaveCount(5);
    await expect(section).toContainText("PostgreSQL / RLS 租户隔离");
    await expect(section).toContainText("升级、回滚与恢复");
    await expect(section).toContainText("deployment:read");
    await expect(section).toContainText("sandbox_verified");
    await section.scrollIntoViewIfNeeded();
    const desktop = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(".self-host-sandbox-section")!;
      const cards = document.querySelector<HTMLElement>(".sandbox-check-grid")!;
      return {
        viewport: document.documentElement.clientWidth,
        documentWidth: document.documentElement.scrollWidth,
        panelOverflow: panel.scrollWidth > panel.clientWidth,
        cardColumns: getComputedStyle(cards).gridTemplateColumns.split(" ").length
      };
    });
    expect(desktop.documentWidth).toBeLessThanOrEqual(desktop.viewport);
    expect(desktop.panelOverflow).toBe(false);
    expect(desktop.cardColumns).toBe(4);
    await page.screenshot({ path: "docs/screenshots/a3-self-host-sandbox-calibration-desktop-20260713.png", fullPage: false, animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const mobileSection = page.locator("section.self-host-sandbox-section");
    await expect(mobileSection.locator('.self-host-sandbox[data-sandbox-state="ready"]')).toBeVisible();
    await mobileSection.locator(".sandbox-verdict").evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 64);
    });
    const mobile = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(".self-host-sandbox-section")!;
      const cards = document.querySelector<HTMLElement>(".sandbox-check-grid")!;
      return {
        viewport: document.documentElement.clientWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        panelRight: panel.getBoundingClientRect().right,
        panelOverflow: panel.scrollWidth > panel.clientWidth,
        cardColumns: getComputedStyle(cards).gridTemplateColumns.split(" ").length
      };
    });
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.bodyWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.panelRight).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.panelOverflow).toBe(false);
    expect(mobile.cardColumns).toBe(1);
    await expect(mobileSection.locator(".sandbox-postgres-metrics article")).toHaveCount(4);
    await page.screenshot({ path: "docs/screenshots/a3-self-host-sandbox-calibration-mobile-390x844-20260713.png", fullPage: false, animations: "disabled" });
    await mobileSection.locator(".sandbox-postgres-qualification").evaluate((node) => {
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 64);
    });
    await page.screenshot({ path: "docs/screenshots/a3-postgres-rls-qualification-mobile-390x844-20260713.png", fullPage: false, animations: "disabled" });
  });

  test("self-host sandbox panel handles partial, denied, empty, failed, and retry states", async ({ page }) => {
    const routePattern = /\/api\/a3\/deployment\/sandbox-calibration/;
    await page.route(routePattern, async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.status = "sandbox_failed";
      payload.summary.passed = 3;
      payload.summary.failed = 1;
      payload.checks[0].status = "failed";
      payload.checks[0].evidence_level = "sandbox_failed";
      payload.authority_boundary.evidence_level = "sandbox_failed";
      await route.fulfill({ response, json: payload });
    });
    await page.goto(`${base}/delivery/?source=a3-golden-path-rc2`);
    let section = page.locator("section.self-host-sandbox-section");
    await expect(section.locator('[data-sandbox-state="partial"]')).toBeVisible();
    await expect(section.locator(".sandbox-verdict-score")).toContainText("3/4");
    await expect(section.locator(".sandbox-production-boundary")).toContainText("部署验收 8/17");
    await page.unroute(routePattern);

    await page.route(routePattern, (route) => route.fulfill({ status: 403, contentType: "application/json", body: '{"error":"access_denied"}' }));
    await page.reload();
    section = page.locator("section.self-host-sandbox-section");
    await expect(section.locator('[data-sandbox-state="denied"]')).toContainText("无权查看部署校准");
    await expect(section.getByRole("button", { name: "重试" })).toHaveCount(0);
    await page.unroute(routePattern);

    await page.route(routePattern, (route) => route.fulfill({ status: 404, contentType: "application/json", body: '{"error":"not_found"}' }));
    await page.reload();
    section = page.locator("section.self-host-sandbox-section");
    await expect(section.locator('[data-sandbox-state="empty"]')).toContainText("暂无沙箱校准回执");
    await expect(section.getByRole("button", { name: "重试" })).toBeVisible();
    await page.unroute(routePattern);

    await page.route(routePattern, (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"unavailable"}' }));
    await page.reload();
    section = page.locator("section.self-host-sandbox-section");
    await expect(section.locator('[data-sandbox-state="failed"]')).toContainText("沙箱校准读取失败");
    await page.unroute(routePattern);
    await section.getByRole("button", { name: "重试" }).click();
    await expect(section.locator('.self-host-sandbox[data-sandbox-state="ready"]')).toBeVisible();
    await expect(section.locator(".sandbox-production-boundary")).toContainText("生产验证 0");
  });

  test("submits and reviews deployment receipt metadata without promoting delivery", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=a3-golden-path-rc2`);
    const section = page.locator("section.deployment-receipt-section");
    await expect(section.getByRole("heading", { name: "部署回执收件箱" })).toBeVisible();
    await expect(section.locator("tbody tr")).toHaveCount(9);
    await expect(section).toContainText("生产已验证");
    await expect(section.locator('.receipt-inbox-summary [data-state="not-authoritative"]')).toContainText("0");
    const projection = section.getByTestId("deployment-acceptance-projection");
    await expect(projection).toContainText("原始正式验收");
    await expect(projection).toContainText("只读投影");
    await expect(projection.locator(".receipt-projection-metrics > div").nth(0)).toContainText("8/17");
    await expect(projection.locator(".receipt-projection-metrics > div").nth(1)).toContainText("8/17");
    await expect(section.getByRole("button", { name: /权威验证|生产验证/ })).toHaveCount(0);

    await section.getByLabel("阻塞项").selectOption("deployment_health");
    await section.getByLabel("证据引用").fill(`receipt:deployment-health:e2e-${Date.now()}`);
    await section.getByLabel("SHA-256").fill("c".repeat(64));
    await section.getByLabel("采集时间").fill("2026-07-13T14:30");
    await section.getByRole("button", { name: "提交元数据" }).click();
    await expect(section.locator('.receipt-action-state[data-state="acknowledged"]')).toContainText("已进入待复核队列");

    const deploymentRow = section.locator("tbody tr").filter({ hasText: "deployment_health" });
    await expect(deploymentRow).toHaveAttribute("data-intake-status", "submitted", { timeout: 10_000 });
    const inboxResponse = await page.request.get("/api/a3/deployment/receipts?source=a3-golden-path-rc2", {
      headers: receiptApiHeaders("auditor")
    });
    expect(inboxResponse.ok()).toBe(true);
    const inbox = await inboxResponse.json();
    const receipt = inbox.slots.find((item: { blocker_id: string }) => item.blocker_id === "deployment_health").latest_receipt;

    await page.route(/\/api\/a3\/deployment\/receipts\/[^/]+\/review/, async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ schema_version: "a3.api_validation_error.v1", error: "version_conflict", details: [] })
      });
    });
    await deploymentRow.getByRole("button", { name: `确认 ${receipt.receipt_id}` }).click();
    await expect(section.locator('.receipt-action-state[data-state="conflict"]')).toContainText("请刷新后重试");
    await page.unroute(/\/api\/a3\/deployment\/receipts\/[^/]+\/review/);

    await deploymentRow.getByRole("button", { name: `确认 ${receipt.receipt_id}` }).click();
    await expect(section.locator('.receipt-action-state[data-state="denied"]')).toContainText("没有执行此操作的权限");

    const reviewResponse = await page.request.post(`/api/a3/deployment/receipts/${receipt.receipt_id}/review?source=a3-golden-path-rc2`, {
      headers: { ...receiptApiHeaders("reviewer"), "idempotency-key": `e2e-review-${Date.now()}` },
      data: {
        source: "a3-golden-path-rc2",
        organization_id: "org-local",
        tenant_id: "tenant-local",
        workspace_id: "workspace-local",
        project_id: "project-local",
        environment_id: "staging",
        review: { action: "acknowledge", reason_code: "metadata_complete", expected_version: receipt.version }
      }
    });
    expect(reviewResponse.status()).toBe(200);
    expect((await reviewResponse.json()).authority_validation.production_verified).toBe(false);

    await page.reload();
    const refreshed = page.locator("section.deployment-receipt-section");
    const refreshedRow = refreshed.locator("tbody tr").filter({ hasText: "deployment_health" });
    await expect(refreshedRow).toHaveAttribute("data-intake-status", "acknowledged");
    await expect(refreshed.locator('.receipt-inbox-summary [data-state="not-authoritative"]')).toContainText("0");
    await expect(refreshedRow).toContainText("等待服务器回读");
    await expect(page.locator(".metric-strip")).toContainText("8/17");
    await refreshed.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-deployment-receipt-inbox-desktop.png", fullPage: false, animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const mobileSection = page.locator("section.deployment-receipt-section");
    await mobileSection.scrollIntoViewIfNeeded();
    const bounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      sectionRight: document.querySelector(".deployment-receipt-section")!.getBoundingClientRect().right
    }));
    expect(bounds.documentScrollWidth).toBeLessThanOrEqual(bounds.viewport);
    expect(bounds.sectionRight).toBeLessThanOrEqual(bounds.viewport);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-deployment-receipt-inbox-mobile-390x844.png", fullPage: false, animations: "disabled" });
  });

  test("switches Chinese and English without losing the selected evidence source", async ({ page }) => {
    await page.goto(`${base}/overview/?source=api-mock`);
    await expect(page.getByRole("heading", { name: "发布总览" })).toBeVisible();
    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.getByRole("heading", { name: "Release overview" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("api-mock");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });

  test("renders searchable API reference and a fail-closed email registration flow", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/api-reference/`);
    await expect(page.getByRole("heading", { name: "API 文档与参考" })).toBeVisible();
    await expect(page.getByText(/身份会话与可信判定链已进入 main/)).toBeVisible();
    await expect(page.getByText("organization_id", { exact: true })).toBeVisible();
    await expect(page.getByText("可信证据与决策账本", { exact: true })).toBeVisible();
    await expect(page.getByText("请求邮箱验证码", { exact: true })).toBeVisible();
    await page.getByLabel("搜索 API").fill("missing_required_tool");
    await expect(page.getByRole("heading", { name: "评判单个案例" })).toBeVisible();
    await page.getByLabel("搜索 API").fill("verification");
    await expect(page.getByText("完成邮箱验证", { exact: true })).toBeVisible();
    await page.getByLabel("搜索 API").fill("browser-sessions/refresh");
    await expect(page.getByRole("heading", { name: "轮换浏览器会话", level: 2 })).toBeVisible();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-api-reference-desktop.png", fullPage: false });

    await page.goto(`${base}/login/`);
    await page.getByRole("tab", { name: "邮箱注册" }).click();
    await expect(page.getByRole("button", { name: /发送验证码/ })).toBeDisabled();
    await page.getByText("查看验证邮件设计稿").click();
    await expect(page.getByLabel("验证码邮件设计预览")).toBeVisible();
    await expect(page.getByText(/当前身份服务的 SMTP 仍发送纯文本/)).toBeVisible();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-email-signup-preview-desktop.png", fullPage: false });
  });

  test("stays readable at 390 by 844 with mobile navigation", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${base}/overview/`);
    await expect(page.getByRole("heading", { name: "发布总览" })).toBeVisible();

    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      sidebarDisplay: getComputedStyle(document.querySelector(".app-sidebar")!).display,
      mobileNavDisplay: getComputedStyle(document.querySelector(".mobile-route-nav")!).display,
      routeRight: document.querySelector(".route-content")!.getBoundingClientRect().right
    }));

    expect(mobile.documentScrollWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.bodyScrollWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.routeRight).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.sidebarDisplay).toBe("none");
    expect(mobile.mobileNavDisplay).toBe("grid");
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-overview-mobile-390x844.png", fullPage: false });

    await page.goto(`${base}/login/`);
    await expect(page.getByRole("heading", { name: "进入工作区" })).toBeVisible();
    expect(await page.locator(".login-page").evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);

    await page.goto(`${base}/api-reference/`);
    await expect(page.getByRole("heading", { name: "API 文档与参考" })).toBeVisible();
    const apiReferenceBounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      routeRight: document.querySelector(".route-content")!.getBoundingClientRect().right
    }));
    expect(apiReferenceBounds.documentScrollWidth).toBeLessThanOrEqual(apiReferenceBounds.viewport);
    expect(apiReferenceBounds.bodyScrollWidth).toBeLessThanOrEqual(apiReferenceBounds.viewport);
    expect(apiReferenceBounds.routeRight).toBeLessThanOrEqual(apiReferenceBounds.viewport);
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-api-reference-mobile-390x844.png", fullPage: false });
    expect(consoleErrors).toEqual([]);
  });

  test("renders distinct hosted authentication and permission denial states", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route("**/api/a3/dashboard**", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "a3.route_access_error.v1",
          error: "unauthorized",
          message: "Authentication is required."
        })
      });
    });
    await page.goto(`${base}/overview/`);
    const unauthenticated = page.locator('[data-boundary-state="unauthenticated"]');
    await expect(unauthenticated).toContainText("请先登录");
    await expect(unauthenticated.getByRole("link", { name: "前往登录" })).toHaveAttribute("href", `${base}/login/`);
    await expect(unauthenticated.getByRole("button", { name: "重试" })).toHaveCount(0);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-auth-required-desktop.png", fullPage: false });

    await page.unroute("**/api/a3/dashboard**");
    await page.route("**/api/a3/dashboard**", async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "a3.route_access_error.v1",
          error: "forbidden",
          message: "The request is not allowed."
        })
      });
    });
    await page.goto(`${base}/reports/`);
    const denied = page.locator('[data-boundary-state="denied"]');
    await expect(denied).toContainText("无权访问");
    await expect(denied).toContainText("重新加载不会改变权限");
    await expect(denied.getByRole("link")).toHaveCount(0);
    await expect(denied.getByRole("button")).toHaveCount(0);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-access-denied-desktop.png", fullPage: false });
  });

  test("renders a bounded partial-data state when unsafe aggregate records are excluded", async ({ page }) => {
    await page.route("**/api/a3/dashboard**", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.aggregate_scope_status = {
        schema_version: "a3.aggregate_scope_status.v1",
        strict_scope_enforced: true,
        status: "partial",
        excluded_record_count: 2,
        excluded_counts: { auditEvents: 1, reviewWorkflowRecords: 1 },
        reason: "Unsafe records were excluded.",
        retry: "Re-ingest records with exact scope.",
        safety: {
          unscoped_records_included: false,
          cross_tenant_fallback_allowed: false,
          foreign_record_counts_exposed: false
        }
      };
      await route.fulfill({ response, json: payload });
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${base}/overview/`);
    const desktopState = page.locator(".partial-data-state");
    await expect(desktopState).toBeVisible();
    await expect(desktopState).toContainText("2");
    await expect(desktopState).toContainText("Re-ingest records with exact scope.");
    await expect(desktopState.getByRole("button")).toHaveCount(0);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-partial-data-desktop.png", fullPage: false });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const mobileState = page.locator(".partial-data-state");
    await expect(mobileState).toBeVisible();
    const bounds = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bannerRight: document.querySelector(".partial-data-state")!.getBoundingClientRect().right
    }));
    expect(bounds.documentScrollWidth).toBeLessThanOrEqual(bounds.viewport);
    expect(bounds.bannerRight).toBeLessThanOrEqual(bounds.viewport);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-partial-data-mobile-390x844.png", fullPage: false });
  });
});

test("A3 malformed JSON is a fixed 400 and never becomes an internal error", async ({ request }) => {
  const response = await request.fetch("/api/a3/reports/share?source=mock", {
    method: "POST",
    headers: { "content-type": "application/json" },
    data: Buffer.from("{\"title\":\"unfinished request\"", "utf8")
  });

  expect(response.status()).toBe(400);
  expect(await response.json()).toEqual({
    schema_version: "a3.sanitized_bad_request.v1",
    error: "invalid_json"
  });
  expect(await response.text()).not.toContain("unfinished request");
});

test("A3 OPTIONS resolves the requested route instead of bypassing access control", async ({ request }) => {
  const protectedPreflight = await request.fetch("/api/a3/reports/share", {
    method: "OPTIONS",
    headers: { "access-control-request-method": "POST" }
  });
  expect(protectedPreflight.status()).toBe(204);
  expect(await protectedPreflight.text()).toBe("");

  const unsupportedPreflight = await request.fetch("/api/a3/reports/share", {
    method: "OPTIONS",
    headers: { "access-control-request-method": "TRACE" }
  });
  expect(unsupportedPreflight.status()).toBe(403);
  expect(await unsupportedPreflight.json()).toEqual({
    schema_version: "a3.sanitized_forbidden.v1",
    error: "access_denied"
  });
});

function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      errors.push(message.text());
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      const detail = `${response.status()} ${response.url()}`;
      if (!errors.includes(detail)) errors.push(detail);
    }
  });
  return errors;
}

function receiptApiHeaders(role: string) {
  return {
    "content-type": "application/json",
    "x-a3-role": role,
    "x-a3-organization-id": "org-local",
    "x-a3-tenant-id": "tenant-local",
    "x-a3-workspace-id": "workspace-local",
    "x-a3-project-id": "project-local",
    "x-a3-environment-id": "staging"
  };
}
