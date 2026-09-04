import { expect, test } from "@playwright/test";

const VIEWPORTS = [
  { width: 320, height: 900 },
  { width: 390, height: 900 },
  { width: 768, height: 960 },
  { width: 909, height: 960 },
  { width: 1280, height: 900 },
  { width: 1440, height: 900 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`terminal controls satisfy layout contract at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.route("**/api/**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ message: "UI contract test" }),
      });
    });
    await page.goto("/funds/510310");

    const toolbar = page.locator(".etf-command-row");
    await expect(toolbar).toBeVisible();
    await expect(page.locator("[data-terminal-control]")).toHaveCount(9);

    const metrics = await page.evaluate(() => {
      const box = (element: Element) => {
        const rect = element.getBoundingClientRect();
        return {
          bottom: rect.bottom,
          height: rect.height,
          left: rect.left,
          right: rect.right,
          top: rect.top,
          width: rect.width,
          xCenter: rect.left + rect.width / 2,
          yCenter: rect.top + rect.height / 2,
        };
      };
      const controls = Array.from(
        document.querySelectorAll<HTMLElement>("[data-terminal-control]"),
      );
      const buttons = Array.from(
        document.querySelectorAll<HTMLElement>(".terminal-control"),
      );
      const selectIcons = Array.from(
        document.querySelectorAll<HTMLElement>(".terminal-select-icon"),
      );
      const command = document.querySelector<HTMLElement>(".etf-command-row");
      const selectors = document.querySelector<HTMLElement>(
        ".etf-selector-toolbar",
      );
      const actions = document.querySelector<HTMLElement>(
        ".etf-global-controls",
      );

      if (!command || !selectors || !actions) {
        throw new Error("ETF terminal toolbar is incomplete");
      }

      return {
        actionBox: box(actions),
        commandBox: box(command),
        controlHeights: controls.map((control) => box(control).height),
        hiddenControls: controls
          .filter((control) => getComputedStyle(control).display === "none")
          .map((control) => control.textContent?.trim() ?? ""),
        overflowingButtonLabels: buttons
          .filter((button) => {
            const content = button.querySelector<HTMLElement>(
              ".terminal-control-content",
            );
            return content ? content.scrollWidth > content.clientWidth : true;
          })
          .map((button) => button.textContent?.trim() ?? ""),
        pageOverflow:
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
        selectIconCenterOffsets: selectIcons.map((icon) => {
          const select = icon
            .closest(".terminal-select")
            ?.querySelector<HTMLElement>(".terminal-select-input");
          return select
            ? Math.abs(box(icon).yCenter - box(select).yCenter)
            : Number.POSITIVE_INFINITY;
        }),
        selectorBox: box(selectors),
        textCenterOffsets: buttons.map((button) => {
          const content = button.querySelector<HTMLElement>(
            ".terminal-control-content",
          );
          return content
            ? Math.abs(box(content).yCenter - box(button).yCenter)
            : Number.POSITIVE_INFINITY;
        }),
      };
    });

    const expectedHeight = viewport.width <= 760 ? 34 : 38;
    expect(metrics.hiddenControls).toEqual([]);
    expect(metrics.controlHeights).toHaveLength(9);
    for (const height of metrics.controlHeights) {
      expect(height).toBe(expectedHeight);
    }
    for (const offset of metrics.textCenterOffsets) {
      expect(offset).toBeLessThanOrEqual(1);
    }
    for (const offset of metrics.selectIconCenterOffsets) {
      expect(offset).toBeLessThanOrEqual(1);
    }
    expect(metrics.overflowingButtonLabels).toEqual([]);
    expect(metrics.pageOverflow).toBeLessThanOrEqual(0);
    expect(metrics.commandBox.left).toBeGreaterThanOrEqual(0);
    expect(metrics.commandBox.right).toBeLessThanOrEqual(viewport.width);

    if (viewport.width >= 1200) {
      const selectorCenter =
        metrics.selectorBox.top + metrics.selectorBox.height / 2;
      const actionCenter =
        metrics.actionBox.top + metrics.actionBox.height / 2;
      expect(Math.abs(selectorCenter - actionCenter)).toBeLessThanOrEqual(1);
    } else {
      expect(
        Math.abs(metrics.selectorBox.left - metrics.actionBox.left),
      ).toBeLessThanOrEqual(1);
      expect(metrics.selectorBox.top).toBeGreaterThan(
        metrics.actionBox.bottom,
      );
    }
  });
}

test("dark mode preserves the terminal control contract", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.route("**/api/**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ message: "UI contract test" }),
    });
  });
  await page.goto("/funds/510310");

  await page.getByRole("button", { name: "夜间" }).click();
  await expect(page.locator(".etf-dashboard-page")).toHaveClass(/theme-dark/u);

  const heights = await page
    .locator("[data-terminal-control]")
    .evaluateAll((controls) =>
      controls.map((control) => control.getBoundingClientRect().height),
    );
  expect(heights).toEqual(Array(9).fill(34));
});
