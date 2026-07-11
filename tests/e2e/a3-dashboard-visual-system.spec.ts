import { expect, type Page, test } from "@playwright/test";

const apiBackedPath = "/apps/dashboard/index.html?source=api-mock";

test.describe("A3 commercial dashboard visual system", () => {
  test("establishes desktop hierarchy, readable data, and interaction states", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openApiDashboard(page);

    const visual = await page.evaluate(() => {
      const sidebar = document.querySelector<HTMLElement>(".sidebar")!;
      const topbar = document.querySelector<HTMLElement>(".topbar")!;
      const firstPanel = document.querySelector<HTMLElement>("#console .panel")!;
      const cards = [...document.querySelectorAll<HTMLElement>(
        ".panel, .metric, .product-surface, .workspace-shell, .sidebar-card"
      )];
      const painted = [...document.querySelectorAll<HTMLElement>("body, body *")];
      return {
        bodyOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        gradientCount: painted.filter((node) => getComputedStyle(node).backgroundImage !== "none").length,
        nonZeroLetterSpacing: painted.filter((node) => !["0px", "normal"].includes(getComputedStyle(node).letterSpacing)).length,
        radiusOverEight: cards.filter((node) => Number.parseFloat(getComputedStyle(node).borderRadius) > 8).length,
        sidebarRight: sidebar.getBoundingClientRect().right,
        topbarLeft: topbar.getBoundingClientRect().left,
        topbarBottom: topbar.getBoundingClientRect().bottom,
        firstPanelTop: firstPanel.getBoundingClientRect().top,
        tableHeaderBackground: getComputedStyle(document.querySelector("th")!).backgroundColor,
        tableHeaderPosition: getComputedStyle(document.querySelector("th")!).position
      };
    });

    expect(visual.bodyOverflow).toBe(false);
    expect(visual.gradientCount).toBe(0);
    expect(visual.nonZeroLetterSpacing).toBe(0);
    expect(visual.radiusOverEight).toBe(0);
    expect(visual.topbarLeft).toBeGreaterThanOrEqual(visual.sidebarRight);
    expect(visual.firstPanelTop).toBeGreaterThan(visual.topbarBottom);
    expect(visual.tableHeaderBackground).not.toBe("rgba(0, 0, 0, 0)");
    expect(visual.tableHeaderPosition).toBe("sticky");

    const evaluateNav = page.locator("[data-nav-parent='evaluate']");
    await evaluateNav.click();
    await expect(evaluateNav).toHaveClass(/active/);
    await expect(evaluateNav.locator("xpath=..")).toHaveClass(/expanded/);

    const focusTarget = page.locator("#export-json");
    await focusTarget.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    const focusStyle = await focusTarget.evaluate((node) => ({
      outline: getComputedStyle(node).outlineStyle,
      outlineWidth: getComputedStyle(node).outlineWidth,
      shadow: getComputedStyle(node).boxShadow
    }));
    expect(focusStyle.outline).toBe("solid");
    expect(focusStyle.outlineWidth).toBe("2px");
    expect(focusStyle.shadow).not.toBe("none");

    const hoverCases = page.locator(".case-row:not(.active)");
    expect(await hoverCases.count()).toBeGreaterThan(0);
    const hoverCase = hoverCases.first();
    await hoverCase.hover();
    await expect(hoverCase).toHaveCSS("background-color", "rgb(246, 249, 250)");

    const overviewNav = page.locator("[data-nav-parent='overview']");
    await overviewNav.click();
    await expect(overviewNav).toHaveClass(/active/);
    await page.evaluate(() => {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    });
    await expect.poll(async () => page.locator("#summary").evaluate((node) => (
      Math.round(node.getBoundingClientRect().top)
    ))).toBeGreaterThanOrEqual(0);

    await page.screenshot({
      path: "docs/screenshots/a3-visual-system-desktop.png",
      fullPage: false
    });

    expect(consoleErrors).toEqual([]);
  });

  test("gives loading, empty, and error states distinct visual treatment", async ({ page }) => {
    await page.route("**/api/a3/dashboard**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.continue();
    });

    const navigation = page.goto(apiBackedPath);
    const loading = page.locator("#saas-runtime-body > .caption:only-child");
    await expect(loading).toBeVisible();
    await expect(loading).toHaveCSS("border-left-width", "3px");
    await navigation;
    await waitForApiDashboard(page);

    await page.locator("#filter-status").selectOption("passed");
    const empty = page.locator("#triage-queue > .muted:only-child");
    await expect(empty).toBeVisible();
    await expect(empty).toHaveCSS("border-left-style", "dashed");
    await expect(empty).toHaveCSS("min-height", "48px");

    const errorBadge = page.locator(".badge.fail").first();
    await expect(errorBadge).toBeVisible();
    await expect(errorBadge).toHaveCSS("background-color", "rgb(255, 240, 238)");
  });

  test("respects reduced motion and remains bounded at 390 by 844", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 390, height: 844 });
    await openApiDashboard(page);

    const mobile = await page.evaluate(() => {
      const body = document.body;
      const viewportWidth = document.documentElement.clientWidth;
      const overview = document.querySelector<HTMLElement>("#summary")!;
      const surfaces = document.querySelector<HTMLElement>("#product-surfaces")!;
      const nav = document.querySelector<HTMLElement>(".nav")!;
      const animated = document.querySelector<HTMLElement>(".product-surface")!;
      return {
        viewportWidth,
        bodyScrollWidth: body.scrollWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        overviewRight: overview.getBoundingClientRect().right,
        surfacesTop: surfaces.getBoundingClientRect().top,
        overviewBottom: overview.getBoundingClientRect().bottom,
        navColumns: getComputedStyle(nav).gridTemplateColumns.split(" ").length,
        transitionDuration: getComputedStyle(animated).transitionDuration,
        animationDuration: getComputedStyle(document.querySelector<HTMLElement>("#console")!).animationDuration,
        internalOverflow: [...document.querySelectorAll<HTMLElement>("main section")]
          .filter((node) => node.scrollWidth > node.clientWidth + 1)
          .map((node) => node.id || node.className)
      };
    });

    expect(mobile.bodyScrollWidth).toBeLessThanOrEqual(mobile.viewportWidth);
    expect(mobile.documentScrollWidth).toBeLessThanOrEqual(mobile.viewportWidth);
    expect(mobile.overviewRight).toBeLessThanOrEqual(mobile.viewportWidth);
    expect(mobile.surfacesTop).toBeGreaterThanOrEqual(mobile.overviewBottom);
    expect(mobile.navColumns).toBe(2);
    expect(cssDurationMs(mobile.transitionDuration)).toBeLessThanOrEqual(0.001);
    expect(cssDurationMs(mobile.animationDuration)).toBeLessThanOrEqual(0.001);
    expect(mobile.internalOverflow).toEqual([]);

    await page.screenshot({
      path: "docs/screenshots/a3-visual-system-mobile-390x844.png",
      fullPage: false
    });

    expect(consoleErrors).toEqual([]);
  });
});

async function openApiDashboard(page: Page) {
  await page.goto(apiBackedPath);
  await waitForApiDashboard(page);
}

async function waitForApiDashboard(page: Page) {
  await expect(page.locator("#data-source")).toContainText("API-backed A1/A2 mock fixture");
  await expect(page.locator("#metric-cases")).toHaveText("32");
}

function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

function cssDurationMs(value: string) {
  return value.endsWith("ms")
    ? Number.parseFloat(value)
    : Number.parseFloat(value) * 1000;
}
