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
  await page.locator('[data-panel="paper"]').click();
  await page.waitForFunction(() => document.querySelector("#paper-status").textContent.includes("Ledger matches"));
  if ((await page.locator("#paper-account").inputValue()) !== "browser-paper")
    throw new Error("Paper account missing");
  if (!(await page.locator("#paper-summary").textContent()).includes("100000"))
    throw new Error("Paper cash missing");
  await page.locator("#language").selectOption("ar");
  await page.waitForFunction(() => document.querySelector("#paper-status").textContent.includes("السجل متطابق"));
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
  await page.locator("#account-email").fill("operator@example.test");
  await page.locator("#account-password").fill("Browser-Test-Password-123");
  await page.locator("#account-form button").click();
  await page.locator("#workspace").waitFor({state:"visible"});
  await page.locator('[data-panel="paper"]').click();
  const controls=page.locator("#paper-controls");
  const create=controls.locator("form").filter({has:page.getByRole("heading",{name:"Create simulation account",exact:true})});
  await create.getByLabel("Account ID",{exact:true}).fill("browser-created");
  await create.getByLabel("Symbol",{exact:true}).fill("SYNTH");
  await create.getByLabel("Sector",{exact:true}).fill("technology");
  await create.getByRole("button",{name:"Create simulation account",exact:true}).click();
  await page.waitForFunction(()=>Array.from(document.querySelector("#paper-account").options).some(o=>o.value==="browser-created"));
  await page.locator("#paper-account").selectOption("browser-created");
  await page.waitForFunction(()=>document.querySelector("#paper-status").textContent.includes("Ledger matches"));
  const quoteForm=controls.locator("form").filter({has:page.getByRole("heading",{name:"Record synthetic quote",exact:true})});
  async function enterQuote(){
    await quoteForm.getByLabel("Symbol",{exact:true}).fill("SYNTH");
    await quoteForm.getByLabel("Bid",{exact:true}).fill("99.50");
    await quoteForm.getByLabel("Ask",{exact:true}).fill("100.25");
    await quoteForm.getByRole("button",{name:"Record synthetic quote",exact:true}).click();
    await page.waitForFunction(()=>document.querySelector("#paper-operation-message").textContent==="Recorded");
  }
  await enterQuote();
  const orderForm=controls.locator("form").filter({has:page.getByRole("heading",{name:"Submit simulation order",exact:true})});
  await orderForm.getByLabel("Symbol",{exact:true}).fill("SYNTH");
  await orderForm.getByLabel("Planned stop price (buy)",{exact:true}).fill("95");
  await orderForm.getByRole("button",{name:"Submit simulation order",exact:true}).click();
  await page.waitForFunction(()=>document.querySelector("#paper-orders").textContent.includes("ACCEPTED"));
  await enterQuote();
  await controls.getByRole("button",{name:/Match against latest quote/}).click();
  await page.waitForFunction(()=>document.querySelector("#paper-orders").textContent.includes("FILLED"));
  await page.waitForFunction(()=>document.querySelector("#paper-positions").textContent.includes("SYNTH"));
  await page.locator("#language").selectOption("ar");
  await controls.getByRole("heading",{name:"عمليات المحاكاة",exact:true}).waitFor();
  const paperOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(paperOverflow)throw new Error("Paper controls mobile overflow");
  await page.locator("#language").selectOption("en");
  await page.getByRole("button",{name:"Sign out",exact:true}).click();
  await page.locator("#account-login").waitFor({state:"visible"});
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
      paper_account_english_arabic: true,
      paper_operator_create_quote_order_fill: true,
      paper_controls_mobile_arabic: true,
      js_errors: errors.length,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
