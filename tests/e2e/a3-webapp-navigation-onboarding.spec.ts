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
    const demoLink = page.getByRole("link", { name: "一键进入退款案例演示 无需登录 · 一条案例看懂 A1、A2、A3" });
    await expect(demoLink).toHaveAttribute("href", `${base}/overview/?source=refund-demo`);
    await page.screenshot({ path: "docs/screenshots/a3-refund-demo-login-desktop.png", fullPage: false, animations: "disabled" });

    await page.goto(`${base}/overview/?source=api-mock`);
    await expect(page.getByRole("region", { name: "从运行到发布，按这条线查看" })).toBeVisible();
    await expect(page.getByRole("link", { name: "01 准备项目 项目与数据" })).toBeVisible();
    await expect(page.getByRole("link", { name: "02 运行 Agent 运行与 Trace" })).toBeVisible();
    await expect(page.getByRole("link", { name: "03 检查质量 评分与失败" })).toBeVisible();
    await expect(page.getByRole("link", { name: "04 决定发布 门禁与审计" })).toHaveAttribute("href", `${base}/delivery/?source=a3-golden-path`);
  });

  test("walks a beginner through the refund evidence chain", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/overview/?source=refund-demo`);

    await expect(page.locator(".source-control select")).toHaveValue("refund-demo");
    await expect(page.getByRole("heading", { name: "用一笔失败退款，看懂 A1、A2、A3" })).toBeVisible();
    await expect(page.getByRole("link", { name: "02 查看失败证据 Expected、Actual 与 Trace" })).toHaveAttribute(
      "href",
      `${base}/case/?source=refund-demo&case_id=case-refund-demo-001`
    );
    await page.screenshot({ path: "docs/screenshots/a3-refund-demo-overview-desktop.png", fullPage: false, animations: "disabled" });

    await page.goto(`${base}/case/?source=refund-demo&case_id=case-refund-demo-001`);
    await expect(page.getByRole("heading", { name: "问题不在回答好不好听，而在退款根本没有被执行" })).toBeVisible();
    await expect(page.getByText("先调用 refund_order 完成退款，再根据工具返回结果回复用户。", { exact: true })).toBeVisible();
    await expect(page.getByText("已经为订单 order_demo_123 完成 42 元退款，请注意查收。", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("这正是失败证据")).toBeVisible();
    await expect(page.getByText("退款工具契约")).toBeVisible();
    await expect(page.getByText("缺少必需工具调用").first()).toBeVisible();

    const caseToReview = page.getByRole("link", { name: /审核/ }).first();
    await expect(caseToReview).toHaveAttribute("href", `${base}/review/?source=refund-demo`);
    await page.screenshot({ path: "docs/screenshots/a3-refund-demo-case-desktop.png", fullPage: true, animations: "disabled" });

    await page.goto(`${base}/review/?source=refund-demo`);
    await expect(page.getByRole("region", { name: "审核与交付流程" })).toBeVisible();
    await expect(page.getByText("当前按钮不可点不是页面坏了", { exact: false })).toBeVisible();
    await page.screenshot({ path: "docs/screenshots/a3-refund-demo-review-desktop.png", fullPage: false, animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${base}/case/?source=refund-demo&case_id=case-refund-demo-001`);
    await expect(page.getByRole("heading", { name: "问题不在回答好不好听，而在退款根本没有被执行" })).toBeVisible();
    await page.screenshot({ path: "docs/screenshots/a3-refund-demo-case-mobile-390x844.png", fullPage: false, animations: "disabled" });
  });
});
