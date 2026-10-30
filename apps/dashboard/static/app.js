"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  let token = "", busy = false, generation = 0;
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
  }
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = String(text ?? "—"); if (cls) el.className = cls; return el; };
  const empty = (el, text = t("empty")) => el.append(node("div", text, "empty"));
  const date = (value) => { if (!value) return "—"; const d = new Date(value); return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(language, {dateStyle: "short", timeStyle: "short"}); };
  function table(id, headers, rows) { const host = $(id); host.replaceChildren(); if (!rows.length) return empty(host); const t = node("table"); const head = node("thead"), hr = node("tr"); headers.forEach(h => hr.append(node("th", h))); head.append(hr); t.append(head); const body = node("tbody"); rows.forEach(row => {const tr = node("tr"); row.forEach(v => tr.append(node("td", v))); body.append(tr);}); t.append(body); host.append(t); }
  function lock() {generation++; token = ""; snapshot = null; $("access-key").value = ""; $("workspace").hidden = true; $("login").hidden = false; $("connection").textContent = t("disconnected"); ["recent-signals","signals-table","decisions-list","portfolio-status","portfolio-summary","positions-table","research-list","alerts-list","audit-table"].forEach(id => $(id).replaceChildren()); ["count-signals","count-decisions","count-audit","updated"].forEach(id=>$(id).textContent="—");}
  async function api(path, credential) {const controller = new AbortController(); const timer = setTimeout(()=>controller.abort(), 15000); try {const r = await fetch(path, {headers: {Authorization: `Bearer ${credential}`}, cache: "no-store", signal: controller.signal, redirect: "error", credentials: "omit"}); if (r.status === 401) throw new Error("AUTH"); if (!r.ok) throw new Error("HTTP"); return await r.json();} finally {clearTimeout(timer);} }
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
  async function refresh() {if(busy || !token)return; busy=true; $("refresh").disabled=true; const current=generation, credential=token; message("loading"); try {const values=await Promise.all(["/api/v1/dashboard/overview","/api/v1/signals","/api/v1/decisions","/api/v1/portfolio","/api/v1/dashboard/research","/api/v1/notifications/preview","/api/v1/audit"].map(path=>api(path,credential))); if(current!==generation)return; snapshot=values; render(...values); $("login").hidden=true; $("workspace").hidden=false; $("connection").textContent=t("connected"); message();}catch(e){if(current!==generation)return; if(e.message==="AUTH"){lock(); message("auth_error");}else{lock(); message("refresh_error");}}finally{busy=false; $("refresh").disabled=false;}}
  $("connect-form").addEventListener("submit",event=>{event.preventDefault(); if(busy)return; token=$("access-key").value.trim(); $("access-key").value=""; generation++; refresh();}); $("refresh").addEventListener("click",refresh); $("lock").addEventListener("click",()=>{lock();message("locked");});
  document.querySelectorAll("[data-panel]").forEach(button=>button.addEventListener("click",()=>{const name=button.dataset.panel; panel=name; document.querySelectorAll(".panel").forEach(p=>p.hidden=p.id!==`panel-${name}`); document.querySelectorAll("[data-panel]").forEach(b=>{b.classList.toggle("active",b===button);b.setAttribute("aria-pressed",b===button?"true":"false");}); $("section-name").textContent=t(name);}));
  $("language").addEventListener("change", () => {
    language = $("language").value === "ar" ? "ar" : "en";
    try {localStorage.setItem("halal-quant.language", language);} catch {}
    applyLanguage();
  });
  applyLanguage();
  window.addEventListener("pagehide",lock);
})();
