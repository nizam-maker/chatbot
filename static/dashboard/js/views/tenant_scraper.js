// static/dashboard/js/views/tenant_scraper.js
(function () {
  let allURLs  = [];
  let tenantId = null;

  function statusBadge(s) {
    if (s==="ok")   return `<span class="badge badge-ok"><span class="dot dot-ok"></span>ok</span>`;
    if (s==="fail") return `<span class="badge badge-fail"><span class="dot dot-fail"></span>fail</span>`;
    return `<span class="badge badge-warn"><span class="dot dot-warn"></span>pending</span>`;
  }

  function toast(msg, type="ok") {
    const el=document.getElementById("toast"); el.textContent=msg; el.className=`toast ${type} show`;
    setTimeout(()=>{el.className="toast";}, 2500);
  }

  async function loadURLs() {
    if (!tenantId) return;
    const res = await authedFetch(`/api/tenant/${tenantId}/scraper/urls`);
    allURLs   = await res.json();
    renderScraperTable();
  }

  function renderScraperTable() {
    const q = document.getElementById("search").value.toLowerCase();
    const rows = allURLs.filter(u =>
      !q || `${u.url} ${u.brand} ${u.model}`.toLowerCase().includes(q)
    );

    document.getElementById("row-count").textContent = `${rows.length} of ${allURLs.length} URLs`;
    document.getElementById("s-total").textContent   = allURLs.length;
    document.getElementById("s-ok").textContent      = allURLs.filter(u=>u.last_status==="ok").length;
    document.getElementById("s-fail").textContent    = allURLs.filter(u=>u.last_status==="fail").length;
    document.getElementById("s-pending").textContent = allURLs.filter(u=>!u.last_status||u.last_status==="pending").length;

    const tbody = document.getElementById("tbody");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No URLs yet — add your first scraper URL above</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(u => `
      <tr>
        <td>
          <label class="toggle">
            <input type="checkbox" ${u.is_enabled?"checked":""}
              onchange="toggleURL('${u.id}', this.checked)">
            <span class="slider"></span>
          </label>
        </td>
        <td style="font-size:12px;color:var(--muted)" title="${u.url}">${u.url}</td>
        <td style="font-weight:500">${u.brand||""} ${u.model||""}</td>
        <td><span style="font-size:11px;font-weight:500;padding:2px 8px;border-radius:20px;background:#e8f4ee;color:#085041">${u.domain}</span></td>
        <td>${statusBadge(u.last_status||"pending")}</td>
        <td style="font-size:12px;color:var(--muted)">${u.last_scraped ? new Date(u.last_scraped).toLocaleDateString("en-MY") : "never"}</td>
        <td>
          <div style="display:flex;gap:4px">
            <button class="btn btn-sm" onclick="runOne('${u.id}')" title="Run">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </button>
            <button class="btn btn-sm btn-danger" onclick="deleteURL('${u.id}')" title="Delete">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
            </button>
          </div>
        </td>
      </tr>`).join("");
  }

  async function addURL() {
    const url    = document.getElementById("f-url").value.trim();
    const brand  = document.getElementById("f-brand").value.trim();
    const model  = document.getElementById("f-model").value.trim();
    const domain = document.getElementById("f-domain").value;
    if (!url) { document.getElementById("f-url").focus(); return; }

    const res  = await authedFetch(`/api/tenant/${tenantId}/scraper/urls`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({url, brand, model, domain})
    });
    const data = await res.json();
    if (data.id) {
      document.getElementById("f-url").value   = "";
      document.getElementById("f-brand").value = "";
      document.getElementById("f-model").value = "";
      toast("URL added ✓", "ok");
      await loadURLs();
    } else { toast("Failed to add URL", "err"); }
  }

  async function deleteURL(id) {
    if (!confirm("Delete this URL?")) return;
    await authedFetch(`/api/tenant/${tenantId}/scraper/urls/${id}`, {method:"DELETE"});
    toast("URL deleted", "ok");
    await loadURLs();
  }

  async function toggleURL(id, enabled) {
    await authedFetch(`/api/tenant/${tenantId}/scraper/urls/${id}`, {
      method:"PATCH", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({is_enabled: enabled})
    });
  }

  async function runOne(id) {
    allURLs = allURLs.map(u => u.id===id ? {...u, last_status:"running"} : u);
    renderScraperTable();
    await authedFetch(`/api/tenant/${tenantId}/scraper/urls/${id}/run`, {method:"POST"});
    setTimeout(loadURLs, 8000);
  }

  async function runAll() {
    toast("Scraper started — check back in a minute", "ok");
    await authedFetch(`/api/tenant/${tenantId}/scraper/run-all`, {method:"POST"});
    setTimeout(loadURLs, 15000);
  }

  window.loadURLs          = loadURLs;
  window.renderScraperTable = renderScraperTable;
  window.addURL            = addURL;
  window.deleteURL         = deleteURL;
  window.toggleURL         = toggleURL;
  window.runOne            = runOne;
  window.runAll            = runAll;

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant/scraper"] = async function initScraperView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const t = await fetch(`/api/tenants/${tenantId}`).then(r => r.json());
    document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
    document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
    document.getElementById("s-name").textContent          = t.name || "My Dashboard";
    document.getElementById("topbar-sub").textContent      = `${t.name} — scraper manager`;
    document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");

    await loadURLs();
  };
})();
