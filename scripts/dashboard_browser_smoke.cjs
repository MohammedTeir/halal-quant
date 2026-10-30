const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.HQ_CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(
    process.env.HQ_BROWSER_URL +
      "/dashboard#recover=" +
      process.env.HQ_BROWSER_TOKEN,
  );
  await page.locator("#new-password").fill("Browser-Test-Password-123");
  await page.locator("#recover-form button").click();
  await page.waitForFunction(
    () => document.querySelector("#recover-form").hidden,
  );
  await page.locator("#account-email").fill("browser@example.test");
  await page.locator("#account-password").fill("Browser-Test-Password-123");
  await page.locator("#account-form button").click();
  await page.locator("#account-settings").waitFor({ state: "visible" });
  await page.locator("#workspace").waitFor({ state: "visible" });
  if ((await page.locator("html").getAttribute("lang")) !== "en")
    throw new Error("English default");
  await page.locator("#language").selectOption("ar");
  await page.waitForFunction(() => document.documentElement.dir === "rtl");
  await page
    .getByRole("button", { name: "إنشاء رمز ربط Telegram", exact: true })
    .click();
  await page.waitForFunction(() =>
    document
      .querySelector("#settings-message")
      .textContent.startsWith("/link "),
  );
  await page.locator("#language").selectOption("en");
  await page
    .getByRole("button", { name: "Invite user", exact: true })
    .waitFor();
  const settings = page.locator("#account-content");
  await settings.locator("input[type=email]").fill("invited@example.test");
  await page.getByRole("button", { name: "Invite user", exact: true }).click();
  await page.waitForFunction(() =>
    document
      .querySelector("#settings-message")
      .textContent.includes("#recover="),
  );
  await page.reload();
  await page.locator("#account-settings").waitFor({ state: "visible" });
  await page.locator("#workspace").waitFor({ state: "visible" });
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.locator("#account-login").waitFor({ state: "visible" });
  await page.waitForTimeout(300);
  if (
    (
      await page.request.get(process.env.HQ_BROWSER_URL + "/api/v1/auth/me")
    ).status() !== 401
  )
    throw new Error("Lock failed to revoke");
  if (errors.length) throw new Error(errors.join(";"));
  if (overflow) throw new Error("Mobile overflow");
  console.log(
    JSON.stringify({
      english: true,
      arabic_rtl: true,
      invitation: true,
      link_code: true,
      session_reload: true,
      logout_revocation: true,
      mobile_no_overflow: true,
      js_errors: errors.length,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
