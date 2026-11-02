export default async function run(page, ui) {
  const results = {};

  // Clear saved preference -> should boot DARK (default per audit).
  await page.evaluate(() => localStorage.removeItem("aeon.theme"));
  await page.reload();
  await page.waitForTimeout(2500);
  results.defaultThemeNoPref = await page.evaluate(() => ({
    attr: document.documentElement.dataset.theme,
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
    bodyBg: getComputedStyle(document.body).backgroundColor,
  }));
  await page.screenshot({ path: "F:/AEON/audit-default-dark.png" });

  // Login to judge mode.
  await page.getByRole("button", { name: "Enter judge mode" }).click();
  await page.waitForTimeout(3000);

  // --- DARK checks ---
  results.dark = await page.evaluate(() => {
    const cs = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : null;
    };
    return {
      headerText: cs(".ag-theme-quartz .ag-header-cell-text", "color"),
      headerWeight: cs(".ag-theme-quartz .ag-header-cell-text", "fontWeight"),
      logRowPadding: cs(".log-row", "padding"),
      logRowLineHeight: cs(".log-row", "lineHeight"),
      tsColor: cs(".log-row .ts", "color"),
      agentNodeBg: cs(".agent-node", "backgroundColor"),
      agentNodeBorder: cs(".agent-node", "borderColor"),
      agentNodeShadow: cs(".agent-node", "boxShadow"),
      topBarBg: cs(".sys-top-bar", "backgroundColor"),
    };
  });
  await page.screenshot({ path: "F:/AEON/audit-main-dark.png" });

  // Switch to light via toggle button and reload persistence check.
  await page.getByRole("button", { name: /◐|◑/ }).click();
  await page.waitForTimeout(600);
  results.lightAfterToggle = await page.evaluate(() => ({
    attr: document.documentElement.dataset.theme,
    saved: localStorage.getItem("aeon.theme"),
  }));

  // --- LIGHT checks ---
  results.light = await page.evaluate(() => {
    const cs = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : null;
    };
    return {
      bodyBg: cs("body", "backgroundColor"),
      paneBg: cs(".topology-canvas-pane", "backgroundColor"),
      agentNodeBg: cs(".agent-node", "backgroundColor"),
      agentNodeBorder: cs(".agent-node", "borderColor"),
      agentNodeShadow: cs(".agent-node", "boxShadow"),
      headerText: cs(".ag-theme-quartz .ag-header-cell-text", "color"),
      headerWeight: cs(".ag-theme-quartz .ag-header-cell-text", "fontWeight"),
      cellColor: cs(".ag-theme-quartz .ag-cell", "color"),
      tabsBg: cs(".tabs", "backgroundColor"),
    };
  });
  await page.screenshot({ path: "F:/AEON/audit-main-light.png" });

  // Reload: saved preference (light) should persist.
  await page.reload();
  await page.waitForTimeout(2500);
  results.persistAfterReload = await page.evaluate(() => ({
    attr: document.documentElement.dataset.theme,
    saved: localStorage.getItem("aeon.theme"),
  }));

  // Toggle back to dark to confirm the switcher round-trips.
  await page.getByRole("button", { name: /◐|◑/ }).click();
  await page.waitForTimeout(400);
  results.backToDark = await page.evaluate(
    () => document.documentElement.dataset.theme,
  );

  return results;
}
