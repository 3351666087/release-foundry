import { expect, test, type Page } from "@playwright/test";

const base = "/apps/webapp/out";
const dataRoutes = [
  ["overview", "发布总览"],
  ["projects", "项目工作区"],
  ["runs", "运行与案例"],
  ["review", "人工审核"],
  ["reports", "报告中心"],
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
      await expect(page.locator(".sidebar-contract")).toContainText("32 cases");
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
    await expect(page.locator(".auth-roadmap")).toContainText("A1 身份服务未连接");
    await page.screenshot({ path: "docs/screenshots/a3-webapp-login-desktop.png", fullPage: false });

    expect(consoleErrors).toEqual([]);
  });

  test("keeps the overview visually bounded and navigates through real routes", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/overview/`);
    await expect(page.getByRole("heading", { name: "发布总览" })).toBeVisible();

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
    await expect(page.getByText(/A1 身份会话与 A2 可信判定链已进入 main/)).toBeVisible();
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
    await expect(page.getByText(/当前 A1 SMTP 仍发送纯文本/)).toBeVisible();
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
