"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const words = {
    en: {
      sign_in: "Sign in",
      sign_out: "Sign out",
      email: "Email",
      password: "Password",
      save: "Save",
      account: "Account & Telegram",
      legacy: "Service key access",
      recovery_help:
        "Invitation only. Contact your administrator for an invitation or password recovery link.",
      set_password: "Set password (at least 12 characters)",
      sessions: "Sessions",
      revoke: "Revoke",
      password_change: "Change password",
      current_password: "Current password",
      new_password: "New password (12+ characters)",
      link: "Create Telegram linking code",
      link_help:
        "Send /link CODE in your private chat with the bot or in a group where you and the bot are administrators. Codes expire in 10 minutes and work once. Refresh after linking. Enable the verified destination below to start notifications.",
      refresh: "Refresh settings",
      enabled: "Enabled",
      language: "Language",
      signal: "Trading signals",
      decision: "Research decisions",
      risk_stop: "Risk-stop alerts",
      destinations: "Verified destinations",
      deliveries: "Delivery history",
      invite: "Invite user",
      users: "Users & roles",
      recovery: "Recovery link",
      disable: "Disable",
      enable: "Enable",
      revoke_all: "Revoke all sessions",
      unlink: "Unlink",
      success: "Saved",
      failure: "Request failed. Sign in again if your session has expired.",
      sent_link: "Share this link privately. It expires and works once:",
      status: "Status",
      error: "Error",
      UNCERTAIN: "Uncertain — held; never automatically resent",
      FAILED: "Confirmed failure",
      SENT: "Sent",
      QUEUED: "Queued",
      RETRY: "Waiting for safe retry",
      CANCELLED: "Cancelled",
      SENDING: "Sending",
      admin: "Administrator",
      viewer: "Viewer",
      reviewer: "Controls reviewer",
      operator: "Risk operator",
      broker_reader: "Broker reader",
      analyst: "Analyst",
    },
    ar: {
      sign_in: "تسجيل الدخول",
      sign_out: "تسجيل الخروج",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      save: "حفظ",
      account: "الحساب وTelegram",
      legacy: "الدخول بمفتاح الخدمة",
      recovery_help:
        "الدخول بالدعوة فقط. تواصل مع المسؤول للحصول على دعوة أو رابط استعادة كلمة المرور.",
      set_password: "تعيين كلمة المرور (12 حرفًا على الأقل)",
      sessions: "الجلسات",
      revoke: "إلغاء الجلسة",
      password_change: "تغيير كلمة المرور",
      current_password: "كلمة المرور الحالية",
      new_password: "كلمة المرور الجديدة (12 حرفًا على الأقل)",
      link: "إنشاء رمز ربط Telegram",
      link_help:
        "أرسل ‎/link CODE في محادثتك الخاصة مع البوت أو في مجموعة تكون أنت والبوت مسؤولين فيها. تنتهي صلاحية الرمز خلال 10 دقائق ويستخدم مرة واحدة. حدّث بعد الربط ثم فعّل الوجهة الموثقة لبدء التنبيهات.",
      refresh: "تحديث الإعدادات",
      enabled: "مفعّل",
      language: "اللغة",
      signal: "إشارات التداول",
      decision: "القرارات البحثية",
      risk_stop: "تنبيهات إيقاف المخاطر",
      destinations: "الوجهات الموثقة",
      deliveries: "سجل التسليم",
      invite: "دعوة مستخدم",
      users: "المستخدمون والأدوار",
      recovery: "رابط الاستعادة",
      disable: "تعطيل",
      enable: "تفعيل",
      revoke_all: "إلغاء كل الجلسات",
      unlink: "إلغاء الربط",
      success: "تم الحفظ",
      failure: "فشل الطلب. سجّل الدخول مجددًا إذا انتهت الجلسة.",
      sent_link: "شارك هذا الرابط بشكل خاص. تنتهي صلاحيته ويستخدم مرة واحدة:",
      status: "الحالة",
      error: "الخطأ",
      UNCERTAIN: "التسليم غير مؤكد — معلّق دون إعادة تلقائية",
      FAILED: "فشل مؤكد",
      SENT: "تم الإرسال",
      QUEUED: "في الانتظار",
      RETRY: "انتظار إعادة آمنة",
      CANCELLED: "ملغى",
      SENDING: "جارٍ الإرسال",
      admin: "مسؤول",
      viewer: "قارئ",
      reviewer: "مراجع الضوابط",
      operator: "مشغّل المخاطر",
      broker_reader: "قارئ الوسيط",
      analyst: "محلل",
    },
  };
  let csrf = "",
    user = null,
    recoveryToken = "",
    version = 0;
  const t = (key) =>
    words[document.documentElement.lang === "ar" ? "ar" : "en"][key] || key;
  const el = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const tell = (text) => {
    $(user ? "settings-message" : "account-message").textContent = text;
  };
  async function call(path, method = "GET", body) {
    const response = await fetch("/api/v1/" + path, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw new Error("REQUEST");
    return response.json();
  }
  const run = (action) => async (event) => {
    event?.preventDefault();
    const button = event?.currentTarget;
    if (button) button.disabled = true;
    try {
      await action();
    } catch {
      tell(t("failure"));
    } finally {
      if (button) button.disabled = false;
    }
  };
  function button(text, action) {
    const n = el("button", t(text));
    n.type = "button";
    n.addEventListener("click", run(action));
    return n;
  }
  function input(type, label, value = "") {
    const wrap = el("label"),
      n = el("input");
    n.type = type;
    n.value = value;
    if (type === "password") {
      n.minLength = 12;
      n.autocomplete = "new-password";
    }
    wrap.append(el("span", t(label)), n);
    return [wrap, n];
  }
  function select(values, value) {
    const n = el("select");
    values.forEach((v) => {
      const o = el("option", t(v));
      o.value = v;
      n.append(o);
    });
    n.value = value;
    return n;
  }
  function linkOutput(token) {
    tell(
      t("sent_link") + " " + location.origin + "/dashboard#recover=" + token,
    );
  }
  function translate() {
    document
      .querySelectorAll("[data-account-text]")
      .forEach((n) => (n.textContent = t(n.dataset.accountText)));
  }
  async function settings() {
    if (!user) return;
    const currentVersion = version;
    const [sessions, dests, deliveries, users] = await Promise.all([
      call("auth/sessions"),
      call("telegram/destinations"),
      call("telegram/deliveries"),
      user.role === "admin" ? call("admin/users") : Promise.resolve(null),
    ]);
    if (currentVersion !== version || !user) return;
    const host = $("account-content");
    host.replaceChildren(el("p", user.email + " · " + t(user.role)));
    host.append(
      button("refresh", settings),
      button("sign_out", () => $("lock").click()),
      el("h3", t("sessions")),
    );
    sessions.items.forEach((s) => {
      const row = el("div");
      row.append(
        el(
          "span",
          new Date(s.expires * 1000).toLocaleString(
            document.documentElement.lang,
          ),
        ),
        button("revoke", async () => {
          await call("auth/sessions/" + s.id, "DELETE");
          if (s.current) location.reload();
          else await settings();
        }),
      );
      host.append(row);
    });
    host.append(el("h3", t("password_change")));
    const [cw, c] = input("password", "current_password"),
      [nw, n] = input("password", "new_password");
    c.minLength = 0;
    c.autocomplete = "current-password";
    host.append(
      cw,
      nw,
      button("save", async () => {
        await call("auth/password", "POST", {
          current_password: c.value,
          password: n.value,
        });
        location.reload();
      }),
    );
    host.append(
      el("h3", "Telegram"),
      el("p", t("link_help")),
      button("link", async () => {
        const r = await call("telegram/link-code", "POST");
        tell("/link " + r.code);
      }),
      el("h3", t("destinations")),
    );
    dests.items.forEach((d) => {
      const row = el("article");
      row.className = "card spaced";
      row.append(el("p", d.chat_id));
      const enabled = el("input");
      enabled.type = "checkbox";
      enabled.checked = d.enabled;
      const label = el("label", t("enabled"));
      label.append(enabled);
      const lang = select(["en", "ar"], d.language);
      const choices = {};
      row.append(label, lang);
      ["signal", "decision", "risk_stop"].forEach((kind) => {
        const check = el("input");
        check.type = "checkbox";
        check.checked = d.kinds.includes(kind);
        choices[kind] = check;
        const label = el("label", t(kind));
        label.append(check);
        row.append(label);
      });
      row.append(
        button("save", async () => {
          await call("telegram/destinations/" + d.id, "PATCH", {
            enabled: enabled.checked,
            language: lang.value,
            kinds: Object.keys(choices).filter((k) => choices[k].checked),
          });
          tell(t("success"));
          await settings();
        }),
        button("unlink", async () => {
          await call("telegram/destinations/" + d.id, "DELETE");
          await settings();
        }),
      );
      host.append(row);
    });
    host.append(el("h3", t("deliveries")));
    deliveries.items.forEach((d) =>
      host.append(
        el(
          "p",
          t(d.kind) +
            " · " +
            d.event_key +
            " · " +
            t(d.status) +
            (d.error ? " · " + t("error") + ": " + d.error : ""),
        ),
      ),
    );
    if (users) {
      host.append(el("h3", t("users")));
      const [ew, email] = input("email", "email"),
        roles = [
          "viewer",
          "admin",
          "reviewer",
          "operator",
          "broker_reader",
          "analyst",
        ],
        role = select(roles, "viewer");
      host.append(
        ew,
        role,
        button("invite", async () => {
          linkOutput(
            (
              await call("admin/invitations", "POST", {
                email: email.value,
                role: role.value,
              })
            ).token,
          );
          await settings();
        }),
      );
      users.items.forEach((u) => {
        const row = el("div"),
          r = select(roles, u.role);
        row.append(
          el("p", u.email),
          r,
          button("save", async () => {
            await call("admin/users/" + u.id, "PATCH", {
              role: r.value,
              enabled: u.enabled,
            });
            await settings();
          }),
          button(u.enabled ? "disable" : "enable", async () => {
            await call("admin/users/" + u.id, "PATCH", {
              role: u.role,
              enabled: !u.enabled,
            });
            await settings();
          }),
          button("revoke_all", async () => {
            await call("admin/users/" + u.id + "/sessions", "DELETE");
            tell(t("success"));
          }),
          button("recovery", async () =>
            linkOutput(
              (await call("admin/users/" + u.id + "/recovery", "POST")).token,
            ),
          ),
        );
        host.append(row);
      });
    }
    $("account-settings").hidden = false;
  }
  async function signedIn(data) {
    user = data.user;
    csrf = data.csrf;
    version++;
    window.dispatchEvent(new Event("hq-authenticated"));
    await settings();
  }
  $("account-form").addEventListener(
    "submit",
    run(async () => {
      const email = $("account-email").value,
        password = $("account-password").value;
      $("account-password").value = "";
      await signedIn(await call("auth/login", "POST", { email, password }));
    }),
  );
  $("recover-form").addEventListener(
    "submit",
    run(async () => {
      await call("auth/recover", "POST", {
        token: recoveryToken,
        password: $("new-password").value,
      });
      recoveryToken = "";
      $("new-password").value = "";
      $("recover-form").hidden = true;
      tell(t("success"));
    }),
  );
  window.addEventListener("hq-locked", (event) => {
    version++;
    const oldCsrf = csrf;
    user = null;
    csrf = "";
    $("account-content").replaceChildren();
    $("account-settings").hidden = true;
    $("settings-message").textContent = "";
    if (oldCsrf && event.detail?.revoke)
      fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: { "X-CSRF-Token": oldCsrf },
      }).catch(() => {});
  });
  $("language").addEventListener("change", () => {
    translate();
    if (user) settings().catch(() => tell(t("failure")));
  });
  const fragment = new URLSearchParams(location.hash.slice(1));
  recoveryToken = fragment.get("recover") || "";
  if (recoveryToken) {
    history.replaceState(null, "", location.pathname);
    $("recover-form").hidden = false;
  }
  translate();
  if (!recoveryToken)
    call("auth/me")
      .then(signedIn)
      .catch(() => {});
})();
