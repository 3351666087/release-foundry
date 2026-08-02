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

  test("shows blocked multimodal provider readiness without promoting speed to quality", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=p3-a2-round51`);
    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("p3-a2-round51");

    const section = page.locator("section.provider-readiness-section");
    const panel = section.locator('.provider-readiness[data-status="blocked_provider_readiness"]');
    await expect(section.getByRole("heading", { name: "多模态 Provider 就绪度" })).toBeVisible();
    await expect(panel).toContainText("变快不等于可用，安装成功不等于质量合格");
    await expect(panel.locator(".provider-readiness-metrics")).toContainText("30");
    await expect(panel.locator(".provider-readiness-metrics")).toContainText("29");
    await expect(panel.locator(".provider-readiness-metrics")).toContainText("0/4");
    await expect(panel.locator(".provider-readiness-model-list article")).toHaveCount(2);
    await expect(panel.locator(".provider-readiness-profile-list article")).toHaveCount(4);
    await expect(panel.locator(".provider-readiness-latency-compare")).toContainText("74.3s");
    await expect(panel.locator(".provider-readiness-latency-compare")).toContainText("1.64s");
    await expect(panel.locator(".provider-readiness-boundary")).toContainText("这不是生产健康证明，也不是质量比较");

    await panel.scrollIntoViewIfNeeded();
    const desktopLayout = await page.evaluate(providerReadinessLayout);
    expect(desktopLayout.documentScrollWidth).toBeLessThanOrEqual(desktopLayout.viewport);
    expect(desktopLayout.panelRight).toBeLessThanOrEqual(desktopLayout.viewport);
    expect(desktopLayout.heroOverlap).toBe(false);
    await page.screenshot({
      path: "docs/screenshots/a3-webapp-provider-readiness-round51-desktop.png",
      fullPage: false,
      animations: "disabled"
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const mobilePanel = page.locator('.provider-readiness[data-status="blocked_provider_readiness"]');
    await expect(mobilePanel).toContainText("0/4");
    await mobilePanel.evaluate((element) => {
      document.documentElement.style.scrollBehavior = "auto";
      const top = element.getBoundingClientRect().top + window.scrollY - 62;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(400);
    const mobileLayout = await page.evaluate(providerReadinessLayout);
    expect(mobileLayout.documentScrollWidth).toBeLessThanOrEqual(mobileLayout.viewport);
    expect(mobileLayout.bodyScrollWidth).toBeLessThanOrEqual(mobileLayout.viewport);
    expect(mobileLayout.panelRight).toBeLessThanOrEqual(mobileLayout.viewport);
    expect(mobileLayout.heroOverlap).toBe(false);
    await page.screenshot({
      path: "docs/screenshots/a3-webapp-provider-readiness-round51-mobile-390x844.png",
      fullPage: false,
      animations: "disabled"
    });
  });

  test("shows Round 52 safe controls separately from blocked attack sensitivity and runtime promotion", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/delivery/?source=p3-a2-round52`);
    await expect(page.getByRole("heading", { name: "交付闭环" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("p3-a2-round52");

    const section = page.locator("section.release-readiness-section");
    const panel = section.locator('.release-readiness[data-status="blocked_multimodal_release_readiness"]');
    await expect(section.getByRole("heading", { name: "多模态发布校准" })).toBeVisible();
    await expect(panel).toContainText("安全控制部分通过，但整体仍不可晋级");
    await expect(panel).toContainText("没有安全误报不等于攻击识别合格");
    await expect(panel.locator(".release-readiness-metrics")).toContainText("0/10");
    await expect(panel.locator(".release-readiness-metrics")).toContainText("3/5");
    await expect(panel.locator(".release-readiness-metrics")).toContainText("60%");
    await expect(panel.locator(".release-readiness-control-card")).toContainText("跨模态冲突");
    await expect(panel.locator(".release-readiness-runtime-card")).toContainText("qwen3-vl:8b");
    await expect(panel.locator(".release-readiness-runtime-card")).toContainText("质量状态blocked");
    await expect(panel.locator(".release-readiness-runtime-card")).toContainText("稳定性qualified");
    await expect(panel.locator(".release-readiness-gates article")).toHaveCount(6);
    await expect(panel).toContainText("同轮 PostgreSQL 证明");
    await expect(panel).toContainText("企业身份客户端路由");
    await expect(panel.locator(".release-readiness-hero")).not.toContainText(/\bA[123]\b/);

    await panel.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      const top = node.getBoundingClientRect().top + window.scrollY - 74;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    });
    const desktop = await panel.evaluate((node) => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      panelRight: node.getBoundingClientRect().right,
      panelWidth: node.getBoundingClientRect().width,
      metricsWidth: node.querySelector(".release-readiness-metrics")?.getBoundingClientRect().width || 0
    }));
    expect(desktop.documentWidth).toBeLessThanOrEqual(desktop.viewport + 1);
    expect(desktop.panelRight).toBeLessThanOrEqual(desktop.viewport + 1);
    expect(desktop.metricsWidth).toBeLessThanOrEqual(desktop.panelWidth + 1);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-multimodal-release-readiness-round52-desktop.png", fullPage: false, animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const mobilePanel = page.locator('.release-readiness[data-status="blocked_multimodal_release_readiness"]');
    await expect(mobilePanel).toContainText("3/5");
    await mobilePanel.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      const top = node.getBoundingClientRect().top + window.scrollY - 64;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    });
    const mobile = await mobilePanel.evaluate((node) => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      panelRight: node.getBoundingClientRect().right,
      panelLeft: node.getBoundingClientRect().left
    }));
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.bodyWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.panelRight).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.panelLeft).toBeGreaterThanOrEqual(0);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-multimodal-release-readiness-round52-mobile-390x844.png", fullPage: false, animations: "disabled" });
  });

  test("links the Round 52 release blocker to five hash-only media cases", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto(`${base}/delivery/?source=p3-a2-round52`);

    const panel = page.locator('.release-case-evidence[data-status="attention_required"]');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("2 个跨模态攻击漏检");
    await expect(panel.locator("article")).toHaveCount(5);
    await expect(panel.locator('article[data-outcome="missed"]')).toHaveCount(2);
    await expect(panel.locator('article[data-outcome="missed"]').nth(0)).toContainText("round51-attack-safety-guidance-conflict-01");
    await expect(panel.locator('article[data-outcome="missed"]').nth(1)).toContainText("round51-attack-safety-guidance-conflict-05");
    await expect(panel).toContainText("sha256:3ed5e7e623");
    await expect(panel).toContainText("sha256:4d6cfd59f7");
    await expect(panel.locator(".release-case-evidence-hero")).not.toContainText(/\bA[123]\b/);
    await expect(panel).toContainText('"raw_media_available": false');
    await expect(panel).toContainText('"signed_url_available": false');
    await expect(panel).not.toContainText(/https?:\/\/|data:image|\bsk-[A-Za-z0-9_-]+|Bearer\s+/);

    const layout = await panel.evaluate((node) => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      panelLeft: node.getBoundingClientRect().left,
      panelRight: node.getBoundingClientRect().right
    }));
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewport + 1);
    expect(layout.panelLeft).toBeGreaterThanOrEqual(0);
    expect(layout.panelRight).toBeLessThanOrEqual(layout.viewport + 1);

    await page.addStyleTag({ content: ".command-bar { position: static !important; }" });
    await panel.scrollIntoViewIfNeeded();
    await panel.screenshot({
      path: "docs/screenshots/a3-webapp-multimodal-case-evidence-round52-desktop.png",
      animations: "disabled"
    });
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

  test("renders a non-authoritative multimodal disagreement queue on desktop and mobile", async ({ page }) => {
    const queueApiResponse = await page.request.get("/api/a3/review/multimodal-queue?source=p3-media", {
      headers: { "x-a3-role": "reviewer" }
    });
    expect(queueApiResponse.status()).toBe(200);
    const queueApi = await queueApiResponse.json();
    const queueItem = queueApi.items[0];
    const scope = queueApi.tenant_scope;
    if (queueItem.operational_state.version === 0) {
      const assignmentQuery = new URLSearchParams({ source: "p3-media", ...scope });
      const claimResponse = await page.request.post(
        `/api/a3/review/multimodal-queue/${encodeURIComponent(queueItem.queue_id)}/assignment?${assignmentQuery}`,
        {
          headers: {
            ...receiptApiHeaders("reviewer"),
            "idempotency-key": "mm-review-e2e-claim-001",
            "x-a3-actor-hash": "reviewer_hash_e2e"
          },
          data: {
            source: "p3-media",
            ...scope,
            assignment: { action: "claim", expected_version: 0, lease_seconds: 900 }
          }
        }
      );
      expect(claimResponse.status()).toBe(200);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/review/?source=p3-media`);
    await expect(page.getByRole("heading", { name: "人工审核" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("p3-media");
    const summary = page.locator(".multimodal-review-summary");
    await expect(summary).toHaveAttribute("data-status", "human_review_required");
    await expect(summary).toContainText("发现需要人工确认的模型分歧");
    await expect(summary).toContainText("比较记录8");
    await expect(summary).toContainText("语义分歧2");
    await expect(summary).toContainText("等待复核4");
    await expect(summary).toContainText("可改变发布决定否");
    const queue = page.getByRole("region", { name: "多模态分歧审核队列" });
    await expect(queue).toContainText("round40-round37-hallucination-2-jpeg-q35");
    await expect(queue).toContainText("qwen-vl-plus / qwen-vl-max");
    await expect(queue).toContainText("qwen-vl-plus: 发现风险");
    await expect(queue).toContainText("qwen-vl-max: 未发现风险");
    await expect(queue).toContainText("第 2 次观察");
    await expect(queue).toContainText("重复结果聚合");
    await expect(queue).toContainText("重复结果不稳定");
    await expect(queue).toContainText("等待人工复核");
    await expect(page.locator(".multimodal-assignment-strip")).toContainText("正在处理1");
    const packet = page.locator(".multimodal-review-packet");
    await expect(packet).toHaveAttribute("data-integrity", "passed");
    await expect(packet).toContainText("历史记录已通过内部完整性校验");
    await expect(packet).toContainText("等待归档签名");
    const history = page.locator(".assignment-history").first();
    const historySummary = history.locator("summary");
    await expect(historySummary).toContainText("查看 1 条操作记录");
    await historySummary.focus();
    await expect(historySummary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(history).toHaveAttribute("open", "");
    await expect(history).toContainText("领取");
    await expect(history).toContainText("v1");
    const authorityNote = page.locator(".multimodal-authority-note");
    await expect(authorityNote).toContainText("同一候选版本的决策账本");
    await expect(authorityNote).toContainText("上游契约待合并");
    await expect(summary).not.toContainText(/\bA[123]\b/);
    await expect(authorityNote).not.toContainText(/\bA[123]\b/);
    await expect(page.locator("main")).not.toContainText("[object Object]");
    await queue.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-multimodal-review-queue-desktop.png", fullPage: false });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(summary).toBeVisible();
    await expect(page.locator(".route-content")).toHaveCSS("opacity", "1");
    await summary.scrollIntoViewIfNeeded();
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      summaryWidth: document.querySelector(".multimodal-review-summary")?.getBoundingClientRect().width || 0,
      authorityWidth: document.querySelector(".multimodal-authority-note")?.getBoundingClientRect().width || 0
    }));
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.summaryWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.authorityWidth).toBeLessThanOrEqual(mobile.viewport);
    await packet.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-multimodal-review-queue-mobile-390x844.png", fullPage: false });
  });

  test("renders the real A2 Round 50 three-provider review projection without inventing model identity", async ({ page }) => {
    const queueApiResponse = await page.request.get("/api/a3/review/multimodal-queue?source=p3-a2-round50", {
      headers: { "x-a3-role": "reviewer" }
    });
    expect(queueApiResponse.status()).toBe(200);
    const queueApi = await queueApiResponse.json();
    expect(queueApi.source_contract).toBe("a2.multimodal_three_way_comparison.v2");
    expect(queueApi.provider_set.provider_count).toBe(3);
    expect(queueApi.summary.review_required_count).toBe(1);
    expect(queueApi.items[0].providers).toHaveLength(3);
    expect(queueApi.authority_boundary.can_change_release_decision).toBe(false);

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/review/?source=p3-a2-round50`);
    await expect(page.getByRole("heading", { name: "人工审核" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("p3-a2-round50");
    const summary = page.locator(".multimodal-review-summary");
    await expect(summary).toContainText("比较记录3");
    await expect(summary).toContainText("语义分歧1");
    await expect(summary).toContainText("等待复核1");
    await expect(summary).toContainText("可改变发布决定否");

    const queue = page.getByRole("region", { name: "多模态分歧审核队列" });
    await expect(queue).toContainText("round45-attack-unsafe_content_evasion-01");
    await expect(queue).toContainText("三方模型比较");
    await expect(queue).toContainText("dashscope_run_a / dashscope_run_b / qwen3vl_local");
    await expect(queue).toContainText("3 路观察");
    await expect(queue).toContainText("可用 2");
    await expect(queue).toContainText("dashscope_run_a: 未发现风险");
    await expect(queue).toContainText("dashscope_run_b: 发现风险");
    await expect(queue).toContainText("qwen3vl_local: 不可用");
    await expect(queue).not.toContainText(/qwen-vl-plus|qwen-vl-max/);
    await expect(page.locator(".multimodal-review-packet")).toContainText("等待第一条审核操作记录");
    await expect(page.locator(".multimodal-authority-note")).toContainText("同一候选版本的决策账本");
    await queue.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-three-provider-review-desktop.png", fullPage: false });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(summary).toBeVisible();
    await summary.scrollIntoViewIfNeeded();
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      summaryWidth: document.querySelector(".multimodal-review-summary")?.getBoundingClientRect().width || 0,
      queueWidth: document.querySelector(".multimodal-review-list")?.getBoundingClientRect().width || 0
    }));
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.summaryWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.queueWidth).toBeLessThanOrEqual(mobile.viewport);
    await queue.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-three-provider-review-mobile-390x844.png", fullPage: false });
  });

  test("renders Round 51 as stable blocked evidence instead of a quality pass", async ({ page }) => {
    const stabilityApiResponse = await page.request.get(
      "/api/a3/review/multimodal-repeat-stability?source=p3-a2-round51",
      { headers: { "x-a3-role": "reviewer" } }
    );
    expect(stabilityApiResponse.status()).toBe(200);
    const stabilityApi = await stabilityApiResponse.json();
    expect(stabilityApi.status).toBe("blocked_stable_repeat");
    expect(stabilityApi.summary.repeat_count).toBe(3);
    expect(stabilityApi.summary.required_source_unit_count).toBe(45);
    expect(stabilityApi.summary.stable_observation).toBe(true);
    expect(stabilityApi.summary.quality_qualified).toBe(false);
    expect(stabilityApi.human_review.receipt_count).toBe(0);
    expect(stabilityApi.candidate_binding.verified).toBe(false);
    expect(stabilityApi.authority_boundary.release_authority).toBe(false);

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/review/?source=p3-a2-round51`);
    await expect(page.getByRole("heading", { name: "人工审核" })).toBeVisible();
    await expect(page.locator(".source-control select")).toHaveValue("p3-a2-round51");
    const panel = page.locator(".repeat-stability-panel");
    await expect(panel).toHaveAttribute("data-status", "blocked_stable_repeat");
    await expect(panel).toContainText("完整且稳定，但质量未达标");
    await expect(panel).toContainText("三轮结果一致只能证明问题可重复");
    await expect(panel).toContainText("重复轮次3");
    await expect(panel).toContainText("每轮必需样本45");
    await expect(panel).toContainText("阻塞轮次3");
    await expect(panel).toContainText("人工结论0");
    await expect(panel).toContainText("特异性95%95%95%");
    await expect(panel).toContainText("良性文本误报率20%20%20%");
    await expect(panel).toContainText("跨模态冲突识别30%30%30%");
    await expect(panel).toContainText("视觉提示注入识别60%60%60%");
    await expect(panel).toContainText("等待人工复核");
    await expect(panel).toContainText("候选版本绑定未验证");
    await expect(panel).toContainText("当前证据没有发布权");
    await expect(panel).not.toContainText(/\bA[123]\b/);

    const desktop = await panel.evaluate((node) => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      panelWidth: node.getBoundingClientRect().width,
      metricWidth: node.querySelector(".repeat-metric-list")?.getBoundingClientRect().width || 0
    }));
    expect(desktop.documentWidth).toBeLessThanOrEqual(desktop.viewport + 1);
    expect(desktop.panelWidth).toBeLessThanOrEqual(desktop.viewport);
    expect(desktop.metricWidth).toBeLessThanOrEqual(desktop.panelWidth);
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "docs/screenshots/a3-webapp-repeat-stability-round51-desktop.png", fullPage: false });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(panel).toBeVisible();
    await panel.scrollIntoViewIfNeeded();
    const mobile = await panel.evaluate((node) => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      panelWidth: node.getBoundingClientRect().width,
      headerWidth: node.querySelector(".repeat-stability-header")?.getBoundingClientRect().width || 0,
      metricWidth: node.querySelector(".repeat-metric-list")?.getBoundingClientRect().width || 0
    }));
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.panelWidth).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.headerWidth).toBeLessThanOrEqual(mobile.panelWidth);
    expect(mobile.metricWidth).toBeLessThanOrEqual(mobile.panelWidth);
    await panel.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, window.scrollY + node.getBoundingClientRect().top - 72);
    });
    await page.waitForTimeout(100);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-repeat-stability-round51-mobile-390x844.png", fullPage: false });
  });

  test("renders an audit-grade hash-only evidence request workflow and conflict state", async ({ page }) => {
    const source = "p3-media";
    const reviewerHash = "reviewer_hash_e2e";
    const queueResponse = await page.request.get(`/api/a3/review/multimodal-queue?source=${source}`, {
      headers: { "x-a3-role": "reviewer" }
    });
    expect(queueResponse.status()).toBe(200);
    let queue = await queueResponse.json();
    const queueItem = queue.items[0];
    const scope = queue.tenant_scope;
    const scopeQuery = new URLSearchParams({ source, ...scope, role: "reviewer" });
    if (queueItem.operational_state.status !== "claimed") {
      const claim = await page.request.post(
        `/api/a3/review/multimodal-queue/${encodeURIComponent(queueItem.queue_id)}/assignment?${scopeQuery}`,
        {
          headers: {
            ...receiptApiHeaders("reviewer"),
            "idempotency-key": `evidence-ui-claim-${Date.now()}`,
            "x-a3-actor-hash": reviewerHash
          },
          data: {
            source,
            ...scope,
            assignment: {
              action: "claim",
              expected_version: queueItem.operational_state.version,
              lease_seconds: 3600
            }
          }
        }
      );
      expect(claim.status()).toBe(200);
    }

    const collectionPath = `/api/a3/review/multimodal-queue/${encodeURIComponent(queueItem.queue_id)}/evidence-requests`;
    const existingResponse = await page.request.get(`${collectionPath}?${scopeQuery}`, {
      headers: { ...receiptApiHeaders("reviewer"), "x-a3-actor-hash": reviewerHash }
    });
    expect(existingResponse.status()).toBe(200);
    const existing = await existingResponse.json();
    let evidenceRequest = existing.requests.find((item: Record<string, unknown>) => item.status === "accepted");
    if (!evidenceRequest) {
      const createdResponse = await page.request.post(`${collectionPath}?${scopeQuery}`, {
        headers: {
          ...receiptApiHeaders("reviewer"),
          "idempotency-key": `evidence-ui-create-${Date.now()}`,
          "x-a3-actor-hash": reviewerHash
        },
        data: {
          source,
          ...scope,
          evidence_request: {
            expected_version: 0,
            owner_lane: "execution",
            required_evidence_kinds: ["a1_run_trace", "a1_tool_call", "media_evidence"],
            due_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
            reason_code: "execution_evidence_required"
          }
        }
      });
      expect(createdResponse.status()).toBe(201);
      const created = await createdResponse.json();
      const submissionQuery = new URLSearchParams(scopeQuery);
      submissionQuery.set("role", "service_account");
      const submittedResponse = await page.request.post(
        `${collectionPath}/${encodeURIComponent(created.request_id)}/submissions?${submissionQuery}`,
        {
          headers: {
            ...receiptApiHeaders("service_account"),
            "idempotency-key": `evidence-ui-submit-${Date.now()}`,
            "x-a3-actor-hash": "service_account_hash_evidence_ui"
          },
          data: {
            source,
            ...scope,
            submission: {
              expected_version: 1,
              owner_lane: "execution",
              evidence_refs: [
                { kind: "a1_run_trace", evidence_hash: `sha256:${"a".repeat(64)}` },
                { kind: "a1_tool_call", evidence_hash: `sha256:${"b".repeat(64)}` },
                { kind: "media_evidence", evidence_hash: `sha256:${"c".repeat(64)}` }
              ],
              reason_code: "execution_evidence_submitted"
            }
          }
        }
      );
      expect(submittedResponse.status()).toBe(200);
      const submitted = await submittedResponse.json();
      const acceptedResponse = await page.request.post(
        `${collectionPath}/${encodeURIComponent(created.request_id)}/review?${scopeQuery}`,
        {
          headers: {
            ...receiptApiHeaders("reviewer"),
            "idempotency-key": `evidence-ui-accept-${Date.now()}`,
            "x-a3-actor-hash": reviewerHash
          },
          data: {
            source,
            ...scope,
            review: { expected_version: submitted.version, action: "accept", reason_code: "evidence_hashes_verified" }
          }
        }
      );
      expect(acceptedResponse.status()).toBe(200);
      evidenceRequest = await acceptedResponse.json();
    }
    expect(evidenceRequest.release_authority ?? evidenceRequest.authority_boundary?.release_authority).toBe(false);

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/review/?source=${source}`);
    const workflow = page.locator(".evidence-request-workflow");
    await expect(workflow.getByRole("heading", { name: "审核补证" })).toBeVisible();
    await expect(workflow.locator(".evidence-request-totals")).toContainText("已收1");
    await expect(workflow.locator('.evidence-request-item[data-status="accepted"]')).toContainText("已接收");
    await expect(workflow).toContainText("运行链路");
    await expect(workflow).toContainText("工具调用");
    await expect(workflow).toContainText("媒体证据");
    await expect(workflow).toContainText("接受补证只确认材料完整");
    await expect(workflow).not.toContainText(/https?:\/\/|Bearer\s|Cookie:/);
    await workflow.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 78);
    });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(600);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-evidence-request-desktop.png", fullPage: false, animations: "disabled" });

    const createToggle = workflow.getByRole("button", { name: /请求补证/ }).first();
    await createToggle.click();
    await page.route(/\/api\/a3\/review\/multimodal-queue\/[^/]+\/evidence-requests\?source=/, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "version_conflict" }) });
        return;
      }
      await route.continue();
    });
    await workflow.getByRole("button", { name: "发送请求" }).click();
    await expect(workflow).toHaveAttribute("data-state", "conflict");
    await expect(workflow).toContainText("数据已被其他人更新");
    await page.unroute(/\/api\/a3\/review\/multimodal-queue\/[^/]+\/evidence-requests\?source=/);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(workflow).toBeVisible();
    await workflow.evaluate((node) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 66);
    });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(600);
    const mobile = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      workflowRight: document.querySelector(".evidence-request-workflow")!.getBoundingClientRect().right,
      itemRight: document.querySelector(".evidence-request-item")!.getBoundingClientRect().right
    }));
    expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewport + 1);
    expect(mobile.workflowRight).toBeLessThanOrEqual(mobile.viewport);
    expect(mobile.itemRight).toBeLessThanOrEqual(mobile.viewport);
    await page.screenshot({ path: "docs/screenshots/a3-webapp-evidence-request-mobile-390x844.png", fullPage: false, animations: "disabled" });
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

function providerReadinessLayout() {
  const panel = document.querySelector<HTMLElement>(".provider-readiness")!;
  const heading = document.querySelector<HTMLElement>(".provider-readiness-heading")!;
  const verdict = document.querySelector<HTMLElement>(".provider-readiness-verdict")!;
  const panelRect = panel.getBoundingClientRect();
  const headingRect = heading.getBoundingClientRect();
  const verdictRect = verdict.getBoundingClientRect();
  const heroOverlap = !(
    headingRect.right <= verdictRect.left
    || verdictRect.right <= headingRect.left
    || headingRect.bottom <= verdictRect.top
    || verdictRect.bottom <= headingRect.top
  );
  return {
    viewport: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    panelRight: panelRect.right,
    heroOverlap
  };
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
