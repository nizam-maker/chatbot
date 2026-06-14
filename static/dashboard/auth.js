// static/dashboard/auth.js
// ─────────────────────────────────────────────────────────────
//  Role-based auth guard for all dashboard pages
//  Include as FIRST script on every dashboard page
//
//  Usage:
//    Add data attribute to <body> to specify which roles can access:
//    <body data-roles="admin">          — admin only
//    <body data-roles="admin,tenant">   — both roles
//    <body data-roles="tenant">         — tenant only
//
//    Default (no data-roles): admin only
// ─────────────────────────────────────────────────────────────

(async function() {
  // Load Supabase JS SDK
  if (!window.supabase) {
    await new Promise((resolve, reject) => {
      const s   = document.createElement("script");
      s.src     = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js";
      s.onload  = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // Get public config
  let cfg;
  try {
    const res = await fetch("/api/public-config");
    cfg = await res.json();
  } catch(e) {
    console.error("[auth] Could not load config:", e);
    return;
  }

  if (!cfg.supabase_url || !cfg.supabase_anon_key) {
    console.warn("[auth] Supabase config missing — auth disabled");
    return;
  }

  const sb = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
  window._sb = sb;

  // Fetch wrapper that attaches the current Supabase access token
  window.authedFetch = async function(url, options = {}) {
    const { data: { session: currentSession } } = await sb.auth.getSession();
    const headers = new Headers(options.headers || {});
    if (currentSession) {
      headers.set("Authorization", `Bearer ${currentSession.access_token}`);
    }
    return fetch(url, { ...options, headers });
  };

  // Check session
  const { data: { session } } = await sb.auth.getSession();
  if (!session) {
    window.location.href = "/dashboard/login";
    return;
  }

  // Get profile
  const { data: profile } = await sb
    .from("profiles")
    .select("role, is_approved, tenant_id, full_name, email")
    .eq("id", session.user.id)
    .single();

  if (!profile || !profile.is_approved) {
    await sb.auth.signOut();
    window.location.href = "/dashboard/login";
    return;
  }

  // Check page role requirements
  const allowedRoles = (document.body.dataset.roles || "admin").split(",");
  if (!allowedRoles.includes(profile.role)) {
    // Redirect to correct dashboard
    window.location.href = profile.role === "admin"
      ? "/dashboard"
      : "/dashboard/tenant";
    return;
  }

  // Store profile globally for page scripts to use
  window._profile = profile;

  // Inject sidebar footer
  const footer = document.querySelector(".sidebar-footer");
  if (footer) {
    const tenantLabel = profile.role === "admin"
      ? `<div class="tenant-badge" style="display:inline-flex;align-items:center;gap:5px;
           background:#faeeda;color:#633806;padding:3px 8px;border-radius:20px;
           font-size:11px;font-weight:500;margin-top:6px">
           <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
             <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
             <circle cx="9" cy="7" r="4"/>
             <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
           </svg>
           Admin
         </div>`
      : `<div class="tenant-badge" style="display:inline-flex;align-items:center;gap:5px;
           background:#e8f4ee;color:#1a6f4a;padding:3px 8px;border-radius:20px;
           font-size:11px;font-weight:500;margin-top:6px">
           <div style="width:6px;height:6px;border-radius:50%;background:#1D9E75;
                animation:pulse 2s infinite"></div>
           Tenant
         </div>`;

    footer.innerHTML = `
      <div style="font-size:12px;color:var(--muted)">Signed in as</div>
      <div style="font-weight:500;margin-top:2px;font-size:13px;
                  overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
           title="${profile.email}">${profile.full_name || profile.email}</div>
      ${tenantLabel}
      <div style="display:flex;align-items:center;justify-content:flex-end;margin-top:8px">
        <button onclick="logout()"
          style="font-size:11px;color:var(--muted);background:none;border:none;
                 cursor:pointer;padding:2px 6px;border-radius:5px;transition:background .15s"
          onmouseover="this.style.background='var(--bg)'"
          onmouseout="this.style.background='none'">
          Sign out
        </button>
      </div>`;
  }

  window.logout = async function() {
    await window._sb.auth.signOut();
    window.location.href = "/dashboard/login";
  };

  // Expose helper: is current user admin?
  window.isAdmin  = () => profile.role === "admin";
  window.isTenant = () => profile.role === "tenant";
  window.myTenantId = () => profile.tenant_id;

})();