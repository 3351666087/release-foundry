import { expect, test, type Page } from "@playwright/test";

const previewPath = "/apps/wechat-miniprogram/preview/index.html";

test.describe("WeChat enterprise release center preview", () => {
  test("renders all four customer pages without lane labels or mobile overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(previewPath);

    await expect(page.locator('[data-page="workbench"]')).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ashr 发布中心" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/\bA[123]\b/);
    await assertMobileLayout(page);
    await page.screenshot({ path: "docs/screenshots/a3-wechat-workbench-mobile.png", fullPage: false });

    await page.locator('[data-target="approval"]').click();
    await expect(page.getByRole("heading", { name: "发布审批" })).toBeVisible();
    await expect(page.locator('[data-page="approval"]')).toHaveCSS("opacity", "1");
    await expect(page.locator('[data-page="approval"]')).toContainText("当前能力：权限预检");
    await page.screenshot({ path: "docs/screenshots/a3-wechat-approval-mobile.png", fullPage: false });
    await page.getByRole("button", { name: "检查批准权限" }).click();
    await expect(page.locator(".toast")).toContainText("不提交审批结果");
    await expect(page.locator(".toast")).not.toHaveClass(/show/, { timeout: 3_000 });
    await assertMobileLayout(page);

    await page.locator('[data-target="incidents"]').click();
    await expect(page.getByRole("heading", { name: "风险告警" })).toBeVisible();
    await expect(page.locator('[data-page="incidents"]')).toHaveCSS("opacity", "1");
    await page.screenshot({ path: "docs/screenshots/a3-wechat-incidents-mobile.png", fullPage: false });
    await page.locator('[data-incident="tools"]').click();
    await expect(page.locator("#incident-title")).toHaveText("关键工具证据完整性复核");
    await expect(page.locator("#incident-timeline")).toBeHidden();
    await assertMobileLayout(page);

    await page.locator('[data-target="account"]').click();
    await expect(page.getByRole("heading", { name: "账户与连接" })).toBeVisible();
    await expect(page.locator('[data-page="account"]')).toHaveCSS("opacity", "1");
    await expect(page.locator('[data-page="account"]')).toContainText("游客调试 AppID");
    await expect(page.locator('[data-page="account"]')).toContainText("尚未启用");
    await assertMobileLayout(page);
    await page.screenshot({ path: "docs/screenshots/a3-wechat-account-mobile.png", fullPage: false });
  });
});

async function assertMobileLayout(page: Page) {
  const result = await page.evaluate(() => {
    const active = document.querySelector<HTMLElement>(".preview-page.active")!;
    const tabBar = document.querySelector<HTMLElement>(".tab-bar")!;
    const painted = [...active.querySelectorAll<HTMLElement>("*")];
    const boundedCards = [...active.querySelectorAll<HTMLElement>(
      ".release-hero, .decision-panel, .panel, .blocker-list article, .incident-chip, .incident-detail, .identity-panel, .connection-panel, .capability-list article"
    )];
    return {
      documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      activeOverflow: active.scrollWidth > active.clientWidth,
      gradients: painted.filter((node) => getComputedStyle(node).backgroundImage.includes("gradient(")).length,
      nonZeroLetterSpacing: painted.filter((node) => !["0px", "normal"].includes(getComputedStyle(node).letterSpacing)).length,
      radiusOverEight: boundedCards.filter((node) => Number.parseFloat(getComputedStyle(node).borderRadius) > 8).length,
      tabInsideViewport: tabBar.getBoundingClientRect().bottom <= window.innerHeight + 1
        && tabBar.getBoundingClientRect().left >= 0
        && tabBar.getBoundingClientRect().right <= window.innerWidth + 1
    };
  });
  expect(result.documentOverflow).toBe(false);
  expect(result.activeOverflow).toBe(false);
  expect(result.gradients).toBe(0);
  expect(result.nonZeroLetterSpacing).toBe(0);
  expect(result.radiusOverEight).toBe(0);
  expect(result.tabInsideViewport).toBe(true);
}
