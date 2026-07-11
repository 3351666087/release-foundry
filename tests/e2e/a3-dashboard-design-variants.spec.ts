import { expect, type Page, test } from "@playwright/test";

const releaseIntelligencePath = "/apps/dashboard/index.html?source=api-mock";
const signalFormPath = "/apps/dashboard/index.html?source=api-mock&design=signal-form";

test.describe("A3 dashboard design variants", () => {
  test("keeps A and B on the same A1/A2 data and product behavior", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });

    await openDashboard(page, releaseIntelligencePath);
    await expect(page.locator("#design-stylesheet")).toHaveAttribute("href", "./src/styles.css");
    await expect(page.locator("html")).toHaveAttribute("data-design", "release-intelligence");
    await expect(page.locator("html")).toHaveAttribute("data-language", "zh");
    await expectSharedEvidence(page);
    await page.screenshot({
      path: "docs/screenshots/a3-design-a-release-intelligence.png",
      fullPage: false
    });

    await openDashboard(page, signalFormPath);
    await expect(page.locator("#design-stylesheet")).toHaveAttribute("href", "./src/signal-form.css");
    await expect(page.locator("html")).toHaveAttribute("data-design", "signal-form");
    await expect(page.locator("html")).toHaveAttribute("data-language", "zh");
    await expectSharedEvidence(page);
    await expect(page.locator(".brand-mark")).toHaveCSS("background-color", "rgb(240, 77, 47)");

    const signalFormAudit = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      gradients: [...document.querySelectorAll<HTMLElement>("body, body *")]
        .filter((node) => getComputedStyle(node).backgroundImage.includes("gradient(")).length,
      nonZeroLetterSpacing: [...document.querySelectorAll<HTMLElement>("body, body *")]
        .filter((node) => !["0px", "normal"].includes(getComputedStyle(node).letterSpacing)).length,
      oversizedRadii: [...document.querySelectorAll<HTMLElement>("body, body *")]
        .filter((node) => Number.parseFloat(getComputedStyle(node).borderRadius) > 8).length,
      mastheadImage: getComputedStyle(document.querySelector(".topbar")!, "::after").backgroundImage,
      titleHeight: document.querySelector(".topbar h1")!.getBoundingClientRect().height,
      titleLineHeight: Number.parseFloat(getComputedStyle(document.querySelector(".topbar h1")!).lineHeight)
    }));

    expect(signalFormAudit.overflow).toBe(false);
    expect(signalFormAudit.gradients).toBe(0);
    expect(signalFormAudit.nonZeroLetterSpacing).toBe(0);
    expect(signalFormAudit.oversizedRadii).toBe(0);
    expect(signalFormAudit.mastheadImage).toContain("polar.png");
    expect(signalFormAudit.mastheadImage).not.toBe("none");
    expect(signalFormAudit.titleHeight / signalFormAudit.titleLineHeight).toBeLessThan(2.1);

    await page.screenshot({
      path: "docs/screenshots/a3-design-b-signal-form.png",
      fullPage: false
    });
  });

  test("keeps Signal/Form readable and bounded at 390 by 844", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openDashboard(page, signalFormPath);

    const mobileAudit = await page.evaluate(() => {
      const viewportWidth = document.documentElement.clientWidth;
      const boundedSelectors = [
        ".brand",
        ".nav",
        ".topbar",
        ".topbar h1",
        ".actions",
        ".source-picker",
        ".export-cluster",
        ".product-surface-strip",
        ".metrics"
      ];
      const outOfBounds = boundedSelectors.flatMap((selector) => (
        [...document.querySelectorAll<HTMLElement>(selector)]
          .filter((node) => {
            const rect = node.getBoundingClientRect();
            return rect.left < -1 || rect.right > viewportWidth + 1;
          })
          .map((node) => selector + ":" + (node.id || node.className))
      ));

      return {
        viewportWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
        outOfBounds,
        titleFontSize: getComputedStyle(document.querySelector(".topbar h1")!).fontSize,
        navColumns: getComputedStyle(document.querySelector(".nav")!).gridTemplateColumns.split(" ").length
      };
    });

    expect(mobileAudit.documentScrollWidth).toBeLessThanOrEqual(mobileAudit.viewportWidth);
    expect(mobileAudit.bodyScrollWidth).toBeLessThanOrEqual(mobileAudit.viewportWidth);
    expect(mobileAudit.outOfBounds).toEqual([]);
    expect(mobileAudit.titleFontSize).toBe("39px");
    expect(mobileAudit.navColumns).toBe(2);

    await page.screenshot({
      path: "docs/screenshots/a3-design-b-signal-form-mobile.png",
      fullPage: false
    });
  });

  test("defaults to Chinese and switches to English without losing dashboard state", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openDashboard(page, signalFormPath);

    await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
    await expect(page.locator("html")).toHaveAttribute("data-language", "zh");
    await expect(page.locator(".topbar h1")).toContainText("发布");
    await expect(page.locator(".topbar h1")).toContainText("智能");
    await expect(page.locator('[data-nav-parent="overview"]')).toContainText("总览");
    await expect(page.locator('[data-language-choice="zh-CN"]')).toHaveAttribute("aria-pressed", "true");

    await page.locator('[data-language-choice="en"]').click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("data-language", "en");
    await expect(page.locator(".topbar h1")).toContainText("Release");
    await expect(page.locator(".topbar h1")).toContainText("Intelligence");
    await expect(page.locator('[data-nav-parent="overview"]')).toContainText("Overview");
    await expect(page.locator('[data-language-choice="en"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/source=api-mock/);
    await expect(page).toHaveURL(/design=signal-form/);
    await expect(page).toHaveURL(/lang=en/);

    await page.reload();
    await expect(page.locator("#metric-cases")).toHaveText("32");
    await expect(page.locator("html")).toHaveAttribute("data-language", "en");
    await expect(page.locator(".topbar h1")).toContainText("Release");
  });

  test("shows both variants in an interactive comparison surface", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.goto("/apps/dashboard/design-compare.html");

    const frames = page.locator("iframe");
    await expect(frames).toHaveCount(2);
    await expect(page.locator(".compare-grid")).toHaveAttribute("data-view", "split");

    const aFrame = page.frameLocator('iframe[title="方案 A Release Intelligence"]');
    const bFrame = page.frameLocator('iframe[title="方案 B Signal Form"]');
    await expect(aFrame.locator("#metric-cases")).toHaveText("32");
    await expect(bFrame.locator("#metric-cases")).toHaveText("32");
    await expect(aFrame.locator("html")).toHaveAttribute("data-design", "release-intelligence");
    await expect(bFrame.locator("html")).toHaveAttribute("data-design", "signal-form");

    await page.screenshot({
      path: "docs/screenshots/a3-design-compare.png",
      fullPage: false
    });

    await page.locator('[data-compare-view="b"]').click();
    await expect(page.locator(".compare-grid")).toHaveAttribute("data-view", "b");
    await expect(page.locator('[data-variant="a"]')).toBeHidden();
    await expect(page.locator('[data-variant="b"]')).toBeVisible();

    await page.locator('[data-compare-view="split"]').click();
    await expect(page.locator(".compare-grid")).toHaveAttribute("data-view", "split");
    await expect(page.locator('[data-variant="a"]')).toBeVisible();
    await expect(page.locator('[data-variant="b"]')).toBeVisible();
  });
});

async function openDashboard(page: Page, path: string) {
  await page.goto(path);
  await expect(page.locator("#data-source")).toContainText("A1/A2");
  await expect(page.locator("#metric-cases")).toHaveText("32");
}

async function expectSharedEvidence(page: Page) {
  await expect(page.locator("#metric-cases")).toHaveText("32");
  await expect(page.locator("#integration-spine")).toContainText("证据链");
  await expect(page.locator("#integration-spine")).toContainText("A1");
  await expect(page.locator("#integration-spine")).toContainText("A2");
  await expect(page.locator("#integration-spine")).toContainText("A3");
}
