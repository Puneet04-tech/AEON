export default async function run(page, ui) {
  await page.getByRole("button", { name: "Enter judge mode" }).click();
  await page.waitForTimeout(3000);

  // Dark theme, then open the judge scenario modal.
  await page.evaluate(() => {
    localStorage.setItem("aeon.theme", "dark");
    document.documentElement.dataset.theme = "dark";
  });
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Judge Scenario Controller" }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: "F:/AEON/modal-dark.png" });

  const modal = await page.evaluate(() => {
    const el = document.querySelector(".sandbox-controller");
    return el ? getComputedStyle(el).backgroundColor : null;
  });
  await page.keyboard.press("Escape");
  await page.mouse.click(10, 10);
  await page.waitForTimeout(400);

  // Light theme version.
  await page.evaluate(() => {
    localStorage.setItem("aeon.theme", "light");
    document.documentElement.dataset.theme = "light";
  });
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Judge Scenario Controller" }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: "F:/AEON/modal-light.png" });
  const modalLight = await page.evaluate(() => {
    const el = document.querySelector(".sandbox-controller");
    return el ? getComputedStyle(el).backgroundColor : null;
  });

  return { modalDark: modal, modalLight };
}
