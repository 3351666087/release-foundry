import { expect, test } from "@playwright/test";

const base = "/apps/webapp/out";

test.describe("A3 navigation and onboarding clarity", () => {
  test("groups navigation, preserves the active link, and exposes current location", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/overview/?source=api-mock`);

    await expect(page.getByRole("button", { name: "01 工作区 项目与数据" })).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("link", { name: /总览.*当前/ })).toBeVisible();
    await expect(page.locator(".command-context")).toContainText("工作区");
    await expect(page.locator(".command-context")).toContainText("总览");

    const evaluationGroup = page.getByRole("button", { name: "02 评测 运行与证据" });
    await evaluationGroup.click();
    await expect(evaluationGroup).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#nav-group-evaluate").getByRole("link", { name: "运行" })).toHaveCount(0);

    await page.goto(`${base}/runs/?source=api-mock`);
    await expect(page.getByRole("button", { name: "02 评测 运行与证据" })).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("link", { name: /运行.*当前/ })).toBeVisible();
    await expect(page.locator(".command-context")).toContainText("运行");
  });

  test("puts the read-only demo path in front of first-time users", async ({ page }) => {
    await page.goto(`${base}/login/`);
    const demoLink = page.getByRole("link", { name: "先进入只读演示 不创建账号，不保存邮箱或凭据" });
    await expect(demoLink).toHaveAttribute("href", `${base}/overview/`);

    await page.goto(`${base}/overview/?source=api-mock`);
    await expect(page.getByRole("region", { name: "从运行到发布，按这条线查看" })).toBeVisible();
    await expect(page.getByRole("link", { name: "01 准备项目 项目与数据" })).toBeVisible();
    await expect(page.getByRole("link", { name: "02 运行 Agent 运行与 Trace" })).toBeVisible();
    await expect(page.getByRole("link", { name: "03 检查质量 评分与失败" })).toBeVisible();
    await expect(page.getByRole("link", { name: "04 决定发布 门禁与审计" })).toHaveAttribute("href", `${base}/delivery/?source=a3-golden-path`);
  });
});
