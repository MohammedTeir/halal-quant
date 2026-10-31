"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  let token = "", busy = false, generation = 0;
  let paperList = null, paperSnapshot = null, paperGeneration = 0;
  let language = "en", snapshot = null, panel = "overview", messageKey = "";
  try { if (localStorage.getItem("halal-quant.language") === "ar") language = "ar"; } catch {}
  const t = (key, values = {}) => (window.DashboardI18n[language][key] || window.DashboardI18n.en[key] || key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
  const message = (key = "") => {messageKey = key; $("message").textContent = key ? t(key) : "";};
  function applyLanguage() {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    document.title = t("page_title");
    document.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
    document.querySelectorAll("[data-i18n-aria]").forEach(el => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
    $("language").value = language;
    $("section-name").textContent = t(panel);
    $("connection").textContent = t(snapshot ? "connected" : "disconnected");
    message(messageKey);
    if (snapshot) render(...snapshot);
    renderPaper();
  }
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = String(text ?? "—"); if (cls) el.className = cls; return el; };
  const empty = (el, text = t("empty")) => el.append(node("div", text, "empty"));
  const date = (value) => { if (!value) return "—"; const d = new Date(value); return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(language, {dateStyle: "short", timeStyle: "short"}); };
  function table(id, headers, rows) { const host = $(id); host.replaceChildren(); if (!rows.length) return empty(host); const t = node("table"); const head = node("thead"), hr = node("tr"); headers.forEach(h => hr.append(node("th", h))); head.append(hr); t.append(head); const body = node("tbody"); rows.forEach(row => {const tr = node("tr"); row.forEach(v => tr.append(node("td", v))); body.append(tr);}); t.append(body); host.append(t); }
  function lock(revoke = true) {generation++; token = ""; snapshot = null; paperList = null; paperSnapshot = null; paperGeneration++; $("paper-account").replaceChildren(); renderPaper(); $("access-key").value = ""; $("workspace").hidden = true; $("account-login").hidden=false; $("legacy-access").hidden=false; window.dispatchEvent(new CustomEvent("hq-locked", {detail: {revoke}})); $("login").hidden = false; $("connection").textContent = t("disconnected"); ["recent-signals","signals-table","decisions-list","portfolio-status","portfolio-summary","positions-table","research-list","alerts-list","audit-table"].forEach(id => $(id).replaceChildren()); ["count-signals","count-decisions","count-audit","updated"].forEach(id=>$(id).textContent="—");}
  async function api(path, credential) {const controller = new AbortController(); const timer = setTimeout(()=>controller.abort(), 15000); try {const r = await fetch(path, {headers: credential === "session" ? {} : {Authorization: `Bearer ${credential}`}, cache: "no-store", signal: controller.signal, redirect: "error", credentials: credential === "session" ? "same-origin" : "omit"}); if (r.status === 401) throw new Error("AUTH"); if (!r.ok) throw new Error("HTTP"); return await r.json();} finally {clearTimeout(timer);} }
  function render(o,s,d,p,r,a,u) {
    $("count-signals").textContent = o.counts.signals; $("count-decisions").textContent = o.counts.decisions; $("count-audit").textContent = o.counts.audit; $("updated").textContent = date(o.as_of);
    const recent = $("recent-signals"); recent.replaceChildren(); s.items.slice(0,5).forEach(item=>{ const row=node("div",undefined,"row"), info=node("div"); info.append(node("strong",item.symbol),node("small",`${item.strategy} · ${item.timeframe}`)); row.append(info,node("span",item.action,"tag")); recent.append(row); }); if (!s.items.length) empty(recent);
    table("signals-table",[t("asset"),t("strategy"),t("timeframe"),t("signal"),t("bar_time")],s.items.map(x=>[x.symbol,x.strategy,x.timeframe,x.action,date(x.bar_time)]));
    const decisions=$("decisions-list"); decisions.replaceChildren(); d.items.forEach(x=>{const row=node("div",undefined,"row"), info=node("div"); info.append(node("strong",x.snapshot?.signal?.symbol || x.signal_id || x.evaluation_id || t("evaluation")),node("small",x.explanation || x.reason || x.reasons?.join(" · ") || t("decision_details"))); row.append(info,node("span",x.status || x.decision || t("recorded"),"tag")); decisions.append(row);}); if(!d.items.length) empty(decisions);
    $("portfolio-status").replaceChildren(node("span",t(p.status),"pill warning"),node("p",t("last_observed", {time: date(p.observed_at)}))); const ps=$("portfolio-summary"); ps.replaceChildren(); if(p.status!=="UNAVAILABLE") [[t("equity"),p.equity],[t("cash"),p.reported_cash],[t("settled"),p.settled_cash]].forEach(([name,value])=>{const box=node("div",undefined,"metric"); box.append(node("small",name),node("strong",value ?? t("unverified"))); ps.append(box);}); table("positions-table",[t("asset"),t("quantity"),t("sellable"),t("value")],p.positions.map(x=>[x.symbol,x.quantity,x.sellable_quantity,x.market_value]));
    const research=$("research-list"); research.replaceChildren(); r.items.forEach(item=>{const card=node("article",undefined,"card"); card.append(node("h3",({portfolio:t("portfolio_report"),validation:t("validation_report"),gold:t("gold_report")})[item.label]),node("span",item.available?t("performance_incomplete"):t("report_unavailable"),"pill warning"),node("p",item.status || t("no_report"), "footnote")); if(item.tests_passed) card.append(node("p",t("tests_snapshot", {count: item.tests_passed}))); if(item.gates?.checks) Object.entries(item.gates.checks).forEach(([key,value])=>{const row=node("div",undefined,"status-row"); row.append(node("span",t(key)),node("strong",value?t("passed"):t("not_passed"))); card.append(row);}); card.append(node("p",item.filename,"footnote")); research.append(card);});
    const alerts=$("alerts-list"); alerts.replaceChildren(); a.items.forEach(item=>{const card=node("article",undefined,"card"); card.append(node("span",t("preview_only"),"tag"),node("pre",item.texts?.[language] || item.text)); alerts.append(card);}); if(!a.items.length) empty(alerts,t("empty_alerts"));
    table("audit-table",[t("event"),t("reference"),t("recorded_at")],u.items.map(x=>[x.action,x.subject,date(x.created_at)]));
  }
  function renderPaper() {
    const host = $("paper-summary"); host.replaceChildren();
    $("paper-positions").replaceChildren(); $("paper-orders").replaceChildren();
    const status = $("paper-status");
    if (!paperList) {status.textContent = t("paper_unavailable"); return;}
    status.textContent = t(paperList.enabled ? "paper_enabled" : "paper_disabled");
    if (!paperList.items.length) {status.append(node("p", t("paper_empty"))); return;}
    if (!paperSnapshot) return;
    status.append(node("p", t(paperSnapshot.reconciliation.status === "MATCH" ? "paper_reconciled" : "paper_drift")));
    [["paper_cash",paperSnapshot.state.cash],["paper_available",paperSnapshot.available_cash],["paper_holds",paperSnapshot.reserved_cash],["paper_equity",paperSnapshot.equity],["paper_realized",paperSnapshot.state.realized],["paper_fees",paperSnapshot.state.fees]].forEach(([label,value])=>{const box=node("div",undefined,"metric");box.append(node("small",t(label)),node("strong",value));host.append(box);});
    table("paper-positions",[t("asset"),t("quantity"),t("paper_cost"),t("paper_stop")],Object.entries(paperSnapshot.state.positions).map(([symbol,p])=>[symbol,p.quantity,p.cost,p.stop]));
    table("paper-orders",[t("asset"),t("paper_status"),t("quantity"),t("paper_filled")],paperSnapshot.orders.map(o=>[o.request.symbol,o.state.status,o.request.quantity,o.state.filled]));
  }
  async function loadPaperAccount() {
    const current = generation, request = ++paperGeneration, credential = token;
    const id = $("paper-account").value;
    paperSnapshot = null; renderPaper();
    if (!id || !credential) return;
    try {
      const result = await api(`/api/v1/paper/accounts/${encodeURIComponent(id)}`,credential);
      if (current !== generation || request !== paperGeneration) return;
      paperSnapshot = result; renderPaper();
    } catch (error) {
      if (current !== generation || request !== paperGeneration) return;
      if (error.message === "AUTH") {lock();message("auth_error");return;}
      $("paper-status").textContent = t("paper_unavailable");
    }
  }
  async function loadPaper() {
    const current = generation, request = ++paperGeneration, credential = token;
    try {
      const result = await api("/api/v1/paper/accounts",credential);
      if (current !== generation || request !== paperGeneration) return;
      paperList = result; paperSnapshot = null;
      const select = $("paper-account"), selected = select.value;
      select.replaceChildren();
      result.items.forEach(account=>{const option=node("option",account.account_id);option.value=account.account_id;select.append(option);});
      if(result.items.some(a=>a.account_id===selected)) select.value=selected;
      renderPaper(); await loadPaperAccount();
    } catch (error) {
      if (current !== generation || request !== paperGeneration) return;
      if (error.message === "AUTH") {lock();message("auth_error");return;}
      paperList = null; paperSnapshot = null; $("paper-account").replaceChildren(); renderPaper();
    }
  }
  $("paper-account").addEventListener("change",loadPaperAccount);
  async function refresh() {if(busy || !token)return; busy=true; $("refresh").disabled=true; const current=generation, credential=token; message("loading"); try {const values=await Promise.all(["/api/v1/dashboard/overview","/api/v1/signals","/api/v1/decisions","/api/v1/portfolio","/api/v1/dashboard/research","/api/v1/notifications/preview","/api/v1/audit"].map(path=>api(path,credential))); if(current!==generation)return; snapshot=values; render(...values); $("login").hidden=true; $("workspace").hidden=false; $("account-login").hidden=true; $("legacy-access").hidden=true; $("connection").textContent=t("connected"); message(); loadPaper();}catch(e){if(current!==generation)return; if(e.message==="AUTH"){lock(); message("auth_error");}else{lock(); message("refresh_error");}}finally{busy=false; $("refresh").disabled=false;}}
  $("connect-form").addEventListener("submit",event=>{event.preventDefault(); if(busy)return; token=$("access-key").value.trim(); $("access-key").value=""; generation++; refresh();}); $("refresh").addEventListener("click",refresh); $("lock").addEventListener("click",()=>{lock();message("locked");});
  document.querySelectorAll("[data-panel]").forEach(button=>button.addEventListener("click",()=>{const name=button.dataset.panel; panel=name; document.querySelectorAll(".panel").forEach(p=>p.hidden=p.id!==`panel-${name}`); document.querySelectorAll("[data-panel]").forEach(b=>{b.classList.toggle("active",b===button);b.setAttribute("aria-pressed",b===button?"true":"false");}); $("section-name").textContent=t(name);}));
  $("language").addEventListener("change", () => {
    language = $("language").value === "ar" ? "ar" : "en";
    try {localStorage.setItem("halal-quant.language", language);} catch {}
    applyLanguage();
  });
  window.addEventListener("hq-authenticated", () => {token="session"; generation++; refresh();});
  applyLanguage();
  window.addEventListener("pagehide",()=>lock(false));
})();
