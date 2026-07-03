// static/dashboard/js/views/tenant_overview.js
// View logic for /dashboard/tenant — loaded once in the shell, re-run on each
// HTMX navigation to this path via window.dashboardViews dispatch.
(function () {
  let tenantId = null;

  async function loadStats() {
    const [analytics, files, urls] = await Promise.all([
      authedFetch(`/api/tenant/${tenantId}/analytics`).then(r => r.json()),
      authedFetch(`/api/tenant/${tenantId}/files`).then(r => r.json()),
      authedFetch(`/api/tenant/${tenantId}/scraper/urls`).then(r => r.json()),
    ]);

    document.getElementById("s-sessions").textContent   = analytics.total_sessions ?? "—";
    document.getElementById("s-messages").textContent   = analytics.total_messages ?? "—";
    document.getElementById("s-leads").textContent      = analytics.total_leads ?? "—";
    document.getElementById("s-conversion").textContent = (analytics.conversion_rate ?? 0) + "%";
    document.getElementById("s-files").textContent      = (files || []).filter(f => f.is_enabled).length;
    document.getElementById("s-urls").textContent       = (urls || []).length;

    const topCarsEl = document.getElementById("top-cars");
    const topCars   = analytics.top_cars || [];
    if (topCars.length) {
      topCarsEl.innerHTML = topCars.map(c => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">
          <span>${c.name}</span>
          <span style="color:var(--muted)">${c.count} queries</span>
        </div>`).join("");
    } else {
      topCarsEl.innerHTML = '<div style="font-size:13px;color:var(--muted)">No car queries yet</div>';
    }
  }

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant"] = async function initOverviewView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const t = await fetch(`/api/tenants/${tenantId}`).then(r => r.json());
    document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
    document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
    document.getElementById("s-name").textContent          = t.name || "My Dashboard";
    document.getElementById("topbar-sub").textContent      = `${t.name} — chatbot overview`;
    document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");

    await loadStats();
  };
})();
