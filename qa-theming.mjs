export default async function run(page, ui) {
  const results = {};

  // Judge mode avoids needing operator credentials.
  await page.getByRole('button', { name: 'Enter judge mode' }).click();
  await page.waitForTimeout(3000);

  results.snapshotAfterLogin = (await ui.snapshot()).split("\n").slice(0, 30);

  // Force light theme and capture.
  await page.evaluate(() => {
    localStorage.setItem("aeon.theme", "light");
    document.documentElement.dataset.theme = "light";
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: "F:/AEON/main-light.png" });

  // Collect computed colors of key surfaces in light.
  results.light = await page.evaluate(() => {
    const pick = (sel, prop) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      return getComputedStyle(el)[prop];
    };
    return {
      bodyBg: pick("body", "backgroundColor"),
      topBarBg: pick(".sys-top-bar", "backgroundColor"),
      drawerBg: pick(".right-stream-drawer", "backgroundColor"),
      paneBg: pick(".topology-canvas-pane", "backgroundColor"),
      tabsBg: pick(".tabs", "backgroundColor"),
      agentNodeBg: pick(".agent-node", "backgroundColor"),
      buttonBg: pick("button.nav-rail-button", "backgroundColor"),
    };
  });

  // Switch to dark theme via toggle effect simulation.
  await page.evaluate(() => {
    localStorage.setItem("aeon.theme", "dark");
    document.documentElement.dataset.theme = "dark";
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: "F:/AEON/main-dark.png" });

  results.dark = await page.evaluate(() => {
    const pick = (sel, prop) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      return getComputedStyle(el)[prop];
    };
    return {
      bodyBg: pick("body", "backgroundColor"),
      topBarBg: pick(".sys-top-bar", "backgroundColor"),
      drawerBg: pick(".right-stream-drawer", "backgroundColor"),
      paneBg: pick(".topology-canvas-pane", "backgroundColor"),
      tabsBg: pick(".tabs", "backgroundColor"),
      agentNodeBg: pick(".agent-node", "backgroundColor"),
      buttonBg: pick("button.nav-rail-button", "backgroundColor"),
      agHeader: pick(".ag-theme-quartz .ag-header", "backgroundColor"),
    };
  });

  return results;
}
