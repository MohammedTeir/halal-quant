"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const words = {
    en: {working:"Recording…",controls:"Paper operations",create:"Create simulation account",account:"Account ID",cash:"Initial virtual cash",symbol:"Symbol",sector:"Sector",asset:"Asset class",stock:"Stock",etf:"ETF",mode:"Mode",synthetic:"Synthetic",forward:"Forward with read-only market data",method:"Reviewed methodology ID (forward mode)",disabled:"Paper operations are disabled on this deployment.",operator:"An operator session is required to change simulations.",order:"Submit simulation order",decision:"Stored decision ID",quantity:"Whole-share quantity",stop:"Planned stop price (buy)",side:"Side",buy:"Buy",sell:"Sell",match:"Match against latest quote",quote:"Record synthetic quote",bid:"Bid",ask:"Ask",size:"Available size",cancel:"Cancel remainder",halt:"Halt new entries",resume:"Resume entries",reason:"Reason",liquidate:"Close owned virtual positions",tick:"Process settlement / expiry",runs:"Forward campaigns",none:"No forward protocol has been proposed.",pending:"Forward acceptance requires recorded complete sessions and safe recovery.",review:"Review exact paper protocol",note:"Review note",expiry:"Review expiry",choose:"Select review decision",approve:"Approve for paper research",reject:"Reject",submit:"Record review",finalize:"Verify and finalize campaign",refresh:"Refresh forward evidence",failed:"Operation did not complete. Check permissions, configuration and current data.",success:"Recorded",limit:"Simulations only. Forward quotes and fills are controlled by the server worker.",protocol:"Propose a forward protocol",protocolhelp:"Provide the reviewed provider IDs, source document hashes and evidence references. Pending protocols require a distinct reviewer.",protocolbody:"Protocol JSON",details:"Protocol and account configuration",result:"Forward evidence"},
    ar: {working:"جارٍ التسجيل…",controls:"عمليات المحاكاة",create:"إنشاء حساب محاكاة",account:"معرّف الحساب",cash:"النقد الافتراضي الأولي",symbol:"الرمز",sector:"القطاع",asset:"فئة الأصل",stock:"سهم",etf:"صندوق",mode:"الوضع",synthetic:"اصطناعي",forward:"اختبار مستقبلي ببيانات سوق للقراءة فقط",method:"معرّف المنهجية المراجعة للاختبار المستقبلي",disabled:"عمليات المحاكاة غير مفعلة في هذا النشر.",operator:"تتطلب تغييرات المحاكاة جلسة مشغّل.",order:"إرسال أمر محاكاة",decision:"معرّف القرار المحفوظ",quantity:"عدد الأسهم الكاملة",stop:"سعر الوقف المخطّط للشراء",side:"الجانب",buy:"شراء",sell:"بيع",match:"مطابقة مع أحدث سعر",quote:"تسجيل سعر اصطناعي",bid:"العرض",ask:"الطلب",size:"الكمية المتاحة",cancel:"إلغاء الكمية المتبقية",halt:"إيقاف الدخول الجديد",resume:"استئناف الدخول",reason:"السبب",liquidate:"إغلاق المراكز الافتراضية المملوكة",tick:"معالجة التسوية والانتهاء",runs:"حملات الاختبار المستقبلي",none:"لم يُقترح بروتوكول اختبار مستقبلي بعد.",pending:"يتطلب القبول جلسات كاملة مسجلة وتعافيًا آمنًا.",review:"مراجعة بروتوكول المحاكاة المحدد",note:"ملاحظة المراجعة",expiry:"انتهاء المراجعة",choose:"اختر قرار المراجعة",approve:"موافقة للبحث التجريبي",reject:"رفض",submit:"تسجيل المراجعة",finalize:"التحقق وإنهاء الحملة",refresh:"تحديث أدلة الاختبار",failed:"لم تكتمل العملية. تحقق من الصلاحيات والإعدادات والبيانات الحالية.",success:"تم التسجيل",limit:"محاكاة فقط. يتحكم عامل الخادم في أسعار الاختبار المستقبلي وتنفيذاته.",protocol:"اقتراح بروتوكول اختبار مستقبلي",protocolhelp:"أدخل معرّفات المصادر المراجعة وبصمات وثائقها ومراجع الأدلة. يتطلب البروتوكول مشرف مراجعة مختلفًا.",protocolbody:"بروتوكول JSON",details:"البروتوكول وإعدادات الحساب",result:"أدلة الاختبار المستقبلي"}
  };
  const t = key => words[$("language").value === "ar" ? "ar" : "en"][key] || key;
  const node = (tag,text) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
  let user=null, csrf="", selected=null, flags=null, runList=[], version=0, renderedKey="";
  async function api(path,body) {
    const r=await fetch("/api/v1/"+path,{method:body===undefined?"GET":"POST",credentials:"same-origin",redirect:"error",cache:"no-store",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:body===undefined?undefined:JSON.stringify(body)});
    if(!r.ok)throw new Error("HTTP "+r.status);
    return r.json();
  }
  function input(form,label,type="text",value="",required=true) {
    const host=node("label",t(label)),field=node("input");field.type=type;if(type==="number")field.step=["quantity","size"].includes(label)?"1":"any";field.value=value;field.required=required;host.append(field);form.append(host);return field;
  }
  function select(form,label,options) {
    const host=node("label",t(label)),field=node("select");options.forEach(([value,key])=>{const option=node("option",t(key));option.value=value;field.append(option);});host.append(field);form.append(host);return field;
  }
  async function refreshAccount(){const current=version,id=$("paper-account").value;if(!id)return;const result=await api("paper/accounts/"+encodeURIComponent(id));if(current!==version || id!==$("paper-account").value)return;selected=result;window.dispatchEvent(new CustomEvent("hq-paper-update",{detail:result}));renderControls();}
  function button(host,label,action) {
    const b=node("button",t(label));b.type="button";b.addEventListener("click",async()=>{b.disabled=true;try{const result=await action();if(["match","cancel","tick"].includes(label)){await refreshAccount();tell(["NO_FILL","REJECTED","BLOCKED"].includes(result?.status)?result.status+" · "+(result.reason||""):t("success"));}}catch{tell(t("failed"));}finally{b.disabled=false;}});host.append(b);return b;
  }
  function tell(text){$("paper-operation-message").textContent=text;}
  function form(host,label,build,submit) {
    const f=node("form");f.append(node("h3",t(label)));host.append(f);const fields=build(f),b=node("button",t(label));b.type="submit";f.append(b);f.addEventListener("submit",async event=>{event.preventDefault();b.disabled=true;tell(t("working"));try{const result=await submit(fields);if(label==="create")window.dispatchEvent(new Event("hq-paper-refresh"));else await refreshAccount();tell(["REJECTED","BLOCKED","NO_FILL"].includes(result?.status)?result.status:t("success"));await refreshRuns();}catch{tell(t("failed"));}finally{b.disabled=false;}});
  }
  const base = () => "paper/accounts/"+encodeURIComponent(selected.account_id);
  const command = () => "ui:"+crypto.randomUUID();
  function renderControls() {
    const key=JSON.stringify([$("language").value,user?.role,flags?.enabled,flags?.forward_enabled,Boolean(flags?.items?.length),selected]);if(key===renderedKey)return;renderedKey=key;
    const host=$("paper-controls");host.replaceChildren(node("h2",t("controls")));
    const message=node("p");message.id="paper-operation-message";message.setAttribute("role","status");host.append(message);
    if(!flags?.enabled){host.append(node("p",t("disabled")));if(user?.role==="operator"&&selected){form(host,"halt",f=>({reason:input(f,"reason")}),async x=>api(base()+"/halt",{command_id:command(),engaged:true,reason:x.reason.value}));if(selected.mode==="forward")form(host,"liquidate",f=>({reason:input(f,"reason")}),async x=>api(base()+"/liquidate",{command_id:command(),reason:x.reason.value}));}return;}
    if(user?.role!=="operator"){host.append(node("p",t("operator")));return;}
    if(flags?.items?.length && !selected)return;
    host.append(node("p",t("limit")));
    form(host,"create",f=>({id:input(f,"account"),cash:input(f,"cash","number","100000"),symbol:input(f,"symbol"),sector:input(f,"sector"),asset:select(f,"asset",[["stock","stock"],["etf","etf"]]),mode:select(f,"mode",[["synthetic","synthetic"],...(flags.forward_enabled?[["forward","forward"]]:[])]),method:input(f,"method","text","",false)}),async x=>{
      const symbol=x.symbol.value.trim();const policy={version:"paper-"+crypto.randomUUID(),...(x.method.value.trim()?{methodology:x.method.value.trim()}: {})};
      await api("paper/accounts",{account_id:x.id.value.trim(),initial_cash:x.cash.value,mode:x.mode.value,universe:{[symbol]:x.sector.value.trim()},asset_classes:{[symbol]:x.asset.value},policy});
    });
    if(!selected)return;
    form(host,"order",f=>({symbol:selected.mode==="forward"?null:input(f,"symbol"),side:selected.mode==="forward"?null:select(f,"side",[["BUY","buy"],["SELL","sell"]]),quantity:input(f,"quantity","number","1"),stop:input(f,"stop","number","",false),decision:selected.mode==="forward"?input(f,"decision"):null}),async x=>{
      const body={quantity:Number(x.quantity.value),...(x.stop.value?{stop_price:x.stop.value}:{})};
      await api(base()+(selected.mode==="forward"?"/decision-orders":"/orders"),selected.mode==="forward"?{...body,decision_id:x.decision.value.trim()}:{...body,command_id:command(),symbol:x.symbol.value.trim(),side:x.side.value});
    });
    if(selected.mode==="synthetic")form(host,"quote",f=>({symbol:input(f,"symbol"),bid:input(f,"bid","number"),ask:input(f,"ask","number"),size:input(f,"size","number","100")}),async x=>api(base()+"/quotes",{command_id:command(),symbol:x.symbol.value.trim(),observed_at:new Date().toISOString(),bid:x.bid.value,ask:x.ask.value,bid_size:Number(x.size.value),ask_size:Number(x.size.value)}));
    form(host,selected.state.halted?"resume":"halt",f=>({reason:input(f,"reason")}),async x=>api(base()+"/halt",{command_id:command(),engaged:!selected.state.halted,reason:x.reason.value}));
    if(selected.mode==="forward")form(host,"liquidate",f=>({reason:input(f,"reason")}),async x=>api(base()+"/liquidate",{command_id:command(),reason:x.reason.value}));
    button(host,"tick",()=>api(base()+"/tick",{command_id:command()}));
    if(selected.mode==="synthetic")selected.orders.filter(o=>["ACCEPTED","PARTIALLY_FILLED"].includes(o.state.status)).forEach(o=>{const q=selected.quotes?.find(q=>q.symbol===o.request.symbol);if(q)button(host,"match",()=>api(base()+"/fills",{command_id:command(),order_id:o.id,quote_id:q.quote_id})).append(node("span"," · "+o.request.symbol));});
    selected.orders.filter(o=>["ACCEPTED","PARTIALLY_FILLED"].includes(o.state.status)).forEach(o=>button(host,"cancel",()=>api(base()+"/cancel",{command_id:command(),order_id:o.id})).append(node("span"," · "+o.request.symbol)));
    if(selected.mode==="forward")form(host,"protocol",f=>{f.append(node("p",t("protocolhelp")));const area=node("textarea");area.required=true;area.rows=10;area.setAttribute("aria-label",t("protocolbody"));f.append(area);return area;},async area=>{const body=JSON.parse(area.value);if(body.account_id!==selected.account_id)throw new Error("Account mismatch");await api("paper/runs",body);});
  }
  function renderRuns() {
    const host=$("paper-forward-runs");host.replaceChildren(node("h2",t("runs")),node("p",t("pending")));
    button(host,"refresh",refreshRuns);
    if(!runList.length){host.append(node("p",t("none")));return;}
    runList.forEach(run=>{
      const row=node("section");row.append(node("h3",run.run_id+" · "+run.state.status));host.append(row);
      button(row,"result",async()=>{const result=await api("paper/runs/"+encodeURIComponent(run.run_id));const pre=node("pre",JSON.stringify(result,null,2));row.append(pre);});
      const details=node("details"),summary=node("summary",t("details"));details.append(summary,node("pre",JSON.stringify({protocol:run.protocol,account:run.account_config,protocol_sha256:run.protocol_sha256},null,2)));row.append(details);
      if(user?.role==="reviewer" && ["PENDING_REVIEW","APPROVED","RUNNING","PAUSED"].includes(run.state.status))form(row,"review",f=>({note:input(f,"note"),expiry:input(f,"expiry","date",new Date(Date.now()+60*86400000).toISOString().slice(0,10)),decision:select(f,"choose",[["","choose"],["approve","approve"],["reject","reject"]])}),async x=>{
        if(!x.decision.value)throw new Error("Choose review decision");
        await api("paper/runs/"+encodeURIComponent(run.run_id)+"/review",{protocol_sha256:run.protocol_sha256,approved:x.decision.value==="approve",expires_at:new Date(x.expiry.value+"T23:59:59Z").toISOString(),note:x.note.value});
      });
      if(user?.role==="operator" && flags?.forward_enabled)button(row,"finalize",async()=>{const result=await api("paper/runs/"+encodeURIComponent(run.run_id)+"/finalize",{});row.append(node("pre",JSON.stringify(result,null,2)));});
    });
  }
  async function refreshRuns(){const current=version;try{const r=await api("paper/runs");if(current!==version)return;runList=r.items;renderRuns();}catch{if(current===version){runList=[];renderRuns();}}}
  async function syncSession(){const current=++version;try{const result=await api("auth/me");if(current!==version)return;user=result.user;csrf=result.csrf;flags=await api("paper/accounts");if(current!==version)return;const id=$("paper-account").value;if(id)selected=await api("paper/accounts/"+encodeURIComponent(id));if(current!==version)return;renderControls();await refreshRuns();}catch{}}
  window.addEventListener("hq-authenticated",syncSession);
  syncSession();
  window.addEventListener("hq-paper-list",event=>{flags=event.detail;renderControls();});
  window.addEventListener("hq-paper-account",event=>{const next=event.detail;if(selected?.account_id===next.account_id && (selected.reconciliation.last_sequence||0)>(next.reconciliation.last_sequence||0))return;selected=next;renderControls();});
  window.addEventListener("hq-locked",()=>{version++;user=null;csrf="";selected=null;flags=null;runList=[];renderedKey="";$("paper-controls").replaceChildren();$("paper-forward-runs").replaceChildren();});
  $("paper-account").addEventListener("change",()=>{selected=null;renderControls();});
  $("language").addEventListener("change",()=>{renderControls();renderRuns();});
})();
