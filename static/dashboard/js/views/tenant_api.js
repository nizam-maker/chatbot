// static/dashboard/js/views/tenant_api.js
(function () {
  let tenantId  = null;
  let fullKey   = null;
  let keyHidden = true;

  function toast(msg, type="ok") {
    const el=document.getElementById("toast"); el.textContent=msg; el.className=`toast ${type} show`;
    setTimeout(()=>{el.className="toast";}, 2500);
  }

  function maskKey(key) {
    if (!key) return "—";
    return key.substring(0, 15) + "••••••••••••" + key.slice(-4);
  }

  async function loadKeyData() {
    const data = await authedFetch(`/api/tenant/${tenantId}/sync-key`).then(r => r.json());
    const statusEl = document.getElementById("key-status");
    const webhookEl = document.getElementById("webhook-status");

    if (data.sync_key) {
      fullKey = data.sync_key;
      document.getElementById("sync-key-display").textContent = maskKey(fullKey);
      statusEl.textContent = "Active";
      statusEl.className   = "badge badge-ok";
      document.getElementById("code-key-1").textContent = fullKey;
      document.getElementById("code-key-2").textContent = fullKey;
    } else {
      document.getElementById("sync-key-display").textContent = "No key generated yet — click Regenerate";
      statusEl.textContent = "Not configured";
      statusEl.className   = "badge badge-warn";
    }

    if (data.webhook_url) {
      document.getElementById("webhook-url").value = data.webhook_url;
      webhookEl.textContent = "Configured";
      webhookEl.className   = "badge badge-ok";
    }

    if (data.last_used_at) {
      document.getElementById("last-used").textContent =
        new Date(data.last_used_at).toLocaleDateString("en-MY");
    }
  }

  function toggleKeyVisibility() {
    keyHidden = !keyHidden;
    document.getElementById("sync-key-display").textContent =
      keyHidden ? maskKey(fullKey) : (fullKey || "—");
  }

  function copyKey() {
    if (!fullKey) { toast("No key to copy", "err"); return; }
    navigator.clipboard.writeText(fullKey).then(() => toast("Key copied!", "ok"));
  }

  async function generateKey() {
    if (!confirm("Regenerate sync key? Your old key will stop working immediately.")) return;
    const webhookUrl = document.getElementById("webhook-url").value.trim();
    const res  = await authedFetch(`/api/tenant/${tenantId}/sync-key/generate`, {
      method:  "POST",
      headers: {"Content-Type":"application/json"},
      body:    JSON.stringify({webhook_url: webhookUrl})
    });
    const data = await res.json();
    if (data.status === "ok") {
      fullKey = data.sync_key;
      keyHidden = false;
      toast("New key generated — copy it now!", "ok");
      await loadKeyData();
    } else { toast("Failed to generate key", "err"); }
  }

  async function saveWebhook() {
    const url = document.getElementById("webhook-url").value.trim();
    if (!url) { toast("Please enter a webhook URL", "err"); return; }

    const res  = await authedFetch(`/api/tenant/${tenantId}/sync-key/generate`, {
      method:  "POST",
      headers: {"Content-Type":"application/json"},
      body:    JSON.stringify({webhook_url: url})
    });
    const data = await res.json();
    if (data.status === "ok") {
      toast("Webhook URL saved ✓", "ok");
      document.getElementById("webhook-status").textContent = "Configured";
      document.getElementById("webhook-status").className   = "badge badge-ok";
    } else { toast("Save failed", "err"); }
  }

  async function loadExternalApi() {
    const data = await authedFetch(`/api/tenant/${tenantId}/external-api`).then(r => r.json());
    const statusEl = document.getElementById("extapi-status");

    document.getElementById("ext-base-url").value    = data.base_url    || "";
    document.getElementById("ext-list-path").value   = data.list_path   || "";
    document.getElementById("ext-detail-path").value = data.detail_path || "";
    document.getElementById("ext-auth-header").value = data.auth_header || "";
    document.getElementById("ext-auth-value").value  = data.auth_value  || "";
    document.getElementById("ext-field-map").value   = data.field_map ? JSON.stringify(data.field_map, null, 2) : "";

    if (data.base_url) {
      statusEl.textContent = "Configured";
      statusEl.className   = "badge badge-ok";
    } else {
      statusEl.textContent = "Not configured";
      statusEl.className   = "badge badge-warn";
    }
  }

  async function saveExternalApi() {
    let fieldMap = null;
    const rawMap = document.getElementById("ext-field-map").value.trim();
    if (rawMap) {
      try { fieldMap = JSON.parse(rawMap); }
      catch (e) { toast("Field mapping must be valid JSON", "err"); return; }
    }

    const body = {
      base_url:    document.getElementById("ext-base-url").value.trim(),
      list_path:   document.getElementById("ext-list-path").value.trim(),
      detail_path: document.getElementById("ext-detail-path").value.trim(),
      auth_header: document.getElementById("ext-auth-header").value.trim(),
      auth_value:  document.getElementById("ext-auth-value").value.trim(),
      field_map:   fieldMap,
    };

    const res = await authedFetch(`/api/tenant/${tenantId}/external-api`, {
      method:  "PUT",
      headers: {"Content-Type":"application/json"},
      body:    JSON.stringify(body)
    });
    const data = await res.json();
    if (res.ok) {
      toast("External API config saved ✓", "ok");
      await loadExternalApi();
    } else {
      toast(data.error || "Save failed", "err");
    }
  }

  async function testExternalApi() {
    const box = document.getElementById("extapi-result");
    box.style.display = "block";
    box.textContent   = "Testing...";

    const res  = await authedFetch(`/api/tenant/${tenantId}/external-api/test`, {method: "POST"});
    const data = await res.json();
    if (res.ok) {
      box.textContent = `OK — ${data.count} car(s) returned.\nSample:\n` + JSON.stringify(data.sample, null, 2);
      toast("Connection test succeeded ✓", "ok");
    } else {
      box.textContent = `Error: ${data.error || "unknown error"}`;
      toast("Connection test failed", "err");
    }
  }

  function copyCode(id) {
    const el = document.getElementById(id);
    navigator.clipboard.writeText(el.innerText).then(() => toast("Code copied!", "ok"));
  }

  window.toggleKeyVisibility = toggleKeyVisibility;
  window.copyKey             = copyKey;
  window.generateKey         = generateKey;
  window.saveWebhook         = saveWebhook;
  window.saveExternalApi     = saveExternalApi;
  window.testExternalApi     = testExternalApi;
  window.copyCode            = copyCode;

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant/api"] = async function initApiView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const t = await fetch(`/api/tenants/${tenantId}`).then(r => r.json());
    document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
    document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
    document.getElementById("s-name").textContent          = t.name || "My Dashboard";
    document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");

    await loadKeyData();
    await loadExternalApi();
  };
})();
