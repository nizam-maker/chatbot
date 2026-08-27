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

  let externalApis  = [];
  const TYPE_LABEL   = {stock: "Stock & price", spec: "Car spec", rebate: "Rebate & discount", news: "News & updates"};

  async function loadExternalApis() {
    externalApis = await authedFetch(`/api/tenant/${tenantId}/external-apis`).then(r => r.json());
    const list = document.getElementById("extapi-list");

    if (!externalApis.length) {
      list.innerHTML = `<div style="font-size:13px;color:var(--muted)">No external APIs configured yet.</div>`;
      return;
    }

    list.innerHTML = externalApis.map(api => `
      <div class="key-box" style="align-items:flex-start">
        <div class="key-val">
          <strong>${api.name}</strong>
          <span class="badge ${api.is_active ? 'badge-ok' : 'badge-warn'}" style="margin-left:6px">${TYPE_LABEL[api.api_type] || api.api_type}</span>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">${api.base_url}</div>
        </div>
        <button class="btn btn-sm" onclick="openApiForm('${api.id}')">Edit</button>
        <button class="btn btn-sm" onclick="deleteApi('${api.id}')">Delete</button>
      </div>
    `).join("");
  }

  function openApiForm(id) {
    const form = document.getElementById("extapi-form");
    form.style.display = "block";
    document.getElementById("extapi-result").style.display = "none";

    const api = id ? externalApis.find(a => a.id === id) : null;
    document.getElementById("ext-id").value          = api ? api.id : "";
    document.getElementById("ext-name").value        = api ? api.name : "";
    document.getElementById("ext-type").value        = api ? api.api_type : "stock";
    document.getElementById("ext-base-url").value    = api ? api.base_url    || "" : "";
    document.getElementById("ext-list-path").value   = api ? api.list_path   || "" : "";
    document.getElementById("ext-detail-path").value = api ? api.detail_path || "" : "";
    document.getElementById("ext-auth-header").value = api ? api.auth_header || "" : "";
    document.getElementById("ext-auth-value").value  = api ? api.auth_value  || "" : "";
    document.getElementById("ext-field-map").value   = api && api.field_map ? JSON.stringify(api.field_map, null, 2) : "";
  }

  function closeApiForm() {
    document.getElementById("extapi-form").style.display = "none";
  }

  async function saveExternalApi() {
    let fieldMap = {};
    const rawMap = document.getElementById("ext-field-map").value.trim();
    if (rawMap) {
      try { fieldMap = JSON.parse(rawMap); }
      catch (e) { toast("Field mapping must be valid JSON", "err"); return; }
    }

    const id   = document.getElementById("ext-id").value;
    const body = {
      name:        document.getElementById("ext-name").value.trim(),
      api_type:    document.getElementById("ext-type").value,
      base_url:    document.getElementById("ext-base-url").value.trim(),
      list_path:   document.getElementById("ext-list-path").value.trim(),
      detail_path: document.getElementById("ext-detail-path").value.trim(),
      auth_header: document.getElementById("ext-auth-header").value.trim(),
      auth_value:  document.getElementById("ext-auth-value").value.trim(),
      field_map:   fieldMap,
    };

    if (!body.name || !body.base_url) { toast("Name and base URL are required", "err"); return; }

    const res = await authedFetch(
      id ? `/api/tenant/${tenantId}/external-apis/${id}` : `/api/tenant/${tenantId}/external-apis`,
      {
        method:  id ? "PUT" : "POST",
        headers: {"Content-Type":"application/json"},
        body:    JSON.stringify(body)
      }
    );
    const data = await res.json();
    if (res.ok) {
      toast("External API saved ✓", "ok");
      closeApiForm();
      await loadExternalApis();
    } else {
      toast(data.error || "Save failed", "err");
    }
  }

  async function deleteApi(id) {
    if (!confirm("Delete this external API? This cannot be undone.")) return;
    const res = await authedFetch(`/api/tenant/${tenantId}/external-apis/${id}`, {method: "DELETE"});
    if (res.ok) {
      toast("API deleted", "ok");
      await loadExternalApis();
    } else {
      toast("Delete failed", "err");
    }
  }

  async function testExternalApi() {
    const id = document.getElementById("ext-id").value;
    const box = document.getElementById("extapi-result");
    box.style.display = "block";

    if (!id) {
      box.textContent = "Save the API first, then test the connection.";
      return;
    }

    box.textContent = "Testing...";
    const res  = await authedFetch(`/api/tenant/${tenantId}/external-apis/${id}/test`, {method: "POST"});
    const data = await res.json();
    if (res.ok) {
      box.textContent = `OK — ${data.count} item(s) returned.\nSample:\n` + JSON.stringify(data.sample, null, 2);
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
  window.openApiForm         = openApiForm;
  window.closeApiForm        = closeApiForm;
  window.saveExternalApi     = saveExternalApi;
  window.deleteApi           = deleteApi;
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
    await loadExternalApis();
  };
})();
