// static/dashboard/js/views/tenant_leads.js
(function () {
  let tenantId = null;
  let allLeads = [];

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-MY", {day:"2-digit",month:"short",year:"numeric"}) +
      " " + d.toLocaleTimeString("en-MY", {hour:"2-digit",minute:"2-digit"});
  }

  async function loadLeads() {
    if (!tenantId) return;
    const res = await authedFetch(`/api/tenant/${tenantId}/leads`);
    allLeads  = await res.json();
    renderLeadsTable();
  }

  function renderLeadsTable() {
    const q = document.getElementById("search").value.toLowerCase();

    const rows = allLeads.filter(l => {
      if (!q) return true;
      return (l.name || "").toLowerCase().includes(q)
          || (l.phone || "").toLowerCase().includes(q)
          || (l.interest || "").toLowerCase().includes(q);
    });

    document.getElementById("row-count").textContent = `${rows.length} of ${allLeads.length} leads`;

    const notified = allLeads.filter(l => l.notified);
    document.getElementById("s-total").textContent    = allLeads.length;
    document.getElementById("s-notified").textContent = notified.length;
    document.getElementById("s-pending").textContent  = allLeads.length - notified.length;
    document.getElementById("s-last").textContent     = allLeads.length ? fmtDate(allLeads[0].created_at) : "—";

    const tbody = document.getElementById("tbody");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No leads captured yet</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(l => `
      <tr>
        <td style="font-weight:500">${l.name || "—"}</td>
        <td><a class="phone-link" href="tel:${l.phone}">${l.phone || "—"}</a></td>
        <td>${l.interest || "—"}</td>
        <td style="color:var(--muted);font-size:12px">${l.source || "chatbot"}</td>
        <td style="font-size:12px;color:var(--muted)">${fmtDate(l.created_at)}</td>
        <td><span class="badge ${l.notified ? "badge-ok" : "badge-off"}">${l.notified ? "Notified" : "Pending"}</span></td>
      </tr>`).join("");
  }

  window.loadLeads        = loadLeads;
  window.renderLeadsTable = renderLeadsTable;

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant/leads"] = async function initLeadsView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const t = await fetch(`/api/tenants/${tenantId}`).then(r => r.json());
    document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
    document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
    document.getElementById("s-name").textContent          = t.name || "My Dashboard";
    document.getElementById("topbar-sub").textContent      = `${t.name} — contacts captured by your chatbot`;
    document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");

    await loadLeads();
  };
})();
