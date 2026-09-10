import { expect, test, type Page } from "@playwright/test";

const VIEWPORTS = [
  { width: 320, height: 900 },
  { width: 390, height: 900 },
  { width: 768, height: 960 },
  { width: 909, height: 960 },
  { width: 1280, height: 900 },
  { width: 1440, height: 900 },
] as const;

const MARKET_TOPICS = [
  {
    key: "sector_20260910_111111111111",
    question: "元件板块今日能否延续强势？",
    sector_name: "元件",
  },
  {
    key: "sector_20260910_222222222222",
    question: "银行板块今日能否延续强势？",
    sector_name: "银行",
  },
  {
    key: "sector_20260910_333333333333",
    question: "证券板块今日能否延续强势？",
    sector_name: "证券",
  },
  {
    key: "sector_20260910_444444444444",
    question: "通信设备板块今日能否延续强势？",
    sector_name: "通信设备",
  },
] as const;

for (const viewport of VIEWPORTS) {
  test(`terminal controls satisfy layout contract at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await installApiRoutes(page);
    await page.goto("/funds/510310");

    const toolbar = page.locator(".etf-command-row");
    await expect(toolbar).toBeVisible();
    await expect(page.locator(".market-pulse-panel")).toBeVisible();
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
      const hotPolls =
        document.querySelector<HTMLElement>(".etf-hot-polls");
      const marketPulse =
        document.querySelector<HTMLElement>(".market-pulse-panel");

      if (!command || !selectors || !actions || !hotPolls || !marketPulse) {
        throw new Error("ETF terminal toolbar is incomplete");
      }

      const hotPollBox = box(hotPolls);
      const marketPulseBox = box(marketPulse);
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
        topLineOverlap:
          Math.max(
            0,
            Math.min(hotPollBox.right, marketPulseBox.right) -
              Math.max(hotPollBox.left, marketPulseBox.left),
          ) *
          Math.max(
            0,
            Math.min(hotPollBox.bottom, marketPulseBox.bottom) -
              Math.max(hotPollBox.top, marketPulseBox.top),
          ),
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
    expect(metrics.topLineOverlap).toBe(0);
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
  await installApiRoutes(page);
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

test("market pulse drives switchable poll topics", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await installApiRoutes(page);
  await page.goto("/funds/510310");

  await expect(page.locator(".market-pulse-list li")).toHaveCount(4);
  await expect(page.locator(".etf-poll-topic")).toHaveCount(1);
  await expect(page.locator(".etf-poll-topic").first()).toContainText("元件");

  await page.getByRole("button", { name: "更换投票话题" }).click();

  await expect(page.locator(".etf-poll-topic").first()).toContainText("银行");
});

test("anonymous comment dialog lists and submits comments", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await installApiRoutes(page);
  await page.goto("/funds/510310");

  await page.getByRole("button", { name: "反馈", exact: true }).click();
  await page.getByRole("button", { name: "交流区" }).click();
  const dialog = page.getByRole("dialog", { name: "ETF 交流区" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("现有评论");

  await page.getByRole("textbox", { name: "评论内容" }).fill("希望增加板块历史走势");
  await page.getByRole("button", { name: "发表" }).click();

  await expect(dialog).toContainText("希望增加板块历史走势");
  await expect(dialog).toContainText("我的评论");
});

async function installApiRoutes(page: Page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/dashboard/market-pulse") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          board: "market-pulse",
          meta: {
            as_of: "2026-09-10T09:35:00+08:00",
            queried_at: "2026-09-10T09:35:00+08:00",
            status: "available",
            source_tools: ["market_pulse"],
            audit_refs: ["market-pulse-hash"],
          },
          envelope: {
            schema_version: "1.0",
            request_id: "market-pulse-request",
            tool: "market_pulse",
            ok: true,
            data: {
              market: "A股",
              snapshot_at: "2026-09-10T09:35:00+08:00",
              ranking_basis: "同花顺行业板块实时涨跌幅降序",
              sectors: [
                sector(1, "元件", 2.16, "逸豪新材"),
                sector(2, "银行", 1.38, "宁波银行"),
                sector(3, "证券", 1.12, "华林证券"),
                sector(4, "通信设备", 0.98, "示例公司"),
              ],
              poll_topics: MARKET_TOPICS,
              notes: [],
            },
            sources: [],
            data_audit: [],
            data_warnings: [],
            data_policy: { ai_may_generate_market_data: false },
            queried_at: "2026-09-10T09:35:00+08:00",
            error: null,
          },
        }),
      });
      return;
    }
    if (
      url.pathname === "/api/panel/interactions" &&
      request.method() === "GET"
    ) {
      const hotPolls = Object.fromEntries(
        url.searchParams.getAll("hot_poll_topic").map((topic) => [
          topic,
          { counts: { yes: 0, no: 0 }, selected_option: null },
        ]),
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          fund: "510310",
          hot_polls: hotPolls,
          feedback: { counts: {}, selected_option: null },
          feature_vote: { counts: {}, selected_option: null },
        }),
      });
      return;
    }
    if (url.pathname === "/api/panel/comments") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON() as { content: string };
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: "comment-new",
            content: payload.content,
            visitor_label: "访客-TEST",
            mine: true,
            created_at: "2026-09-10T09:40:00+08:00",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          fund: "510310",
          count: 1,
          comments: [
            {
              id: "comment-existing",
              content: "现有评论",
              visitor_label: "访客-A1B2",
              mine: false,
              created_at: "2026-09-10T09:35:00+08:00",
            },
          ],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ message: "UI contract test" }),
    });
  });
}

function sector(rank: number, name: string, changePct: number, leader: string) {
  return {
    rank,
    name,
    change_pct: changePct,
    rising_count: 10,
    falling_count: 2,
    leading_stock: leader,
    leading_stock_change_pct: 5.2,
  };
}
