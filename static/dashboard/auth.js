// static/dashboard/auth.js
// ─────────────────────────────────────────────────────────────
//  Shared auth guard for all dashboard pages
//  Include this as the FIRST script on every dashboard page
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

  // Init client
  const sb = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
  window._sb = sb; // make available globally for logout

  // Check session
  const { data: { session } } = await sb.auth.getSession();

  if (!session) {
    // Not logged in — redirect to login
    window.location.href = "/dashboard/login";
    return;
  }

  // Inject logout button into sidebar footer if present
  const footer = document.querySelector(".sidebar-footer");
  if (footer) {
    const email = session.user?.email || "";
    footer.innerHTML = `
      <div>Signed in as</div>
      <div style="font-weight:500;margin-top:2px;font-size:13px;
                  overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
           title="${email}">${email}</div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
        <div class="tenant-badge" style="display:inline-flex;align-items:center;gap:5px;
             background:#e8f4ee;color:#1a6f4a;padding:3px 8px;border-radius:20px;
             font-size:11px;font-weight:500">
          <div style="width:6px;height:6px;border-radius:50%;background:#1D9E75;
               animation:pulse 2s infinite"></div>
          Laman Auto
        </div>
        <button onclick="logout()"
          style="font-size:11px;color:#7a7870;background:none;border:none;
                 cursor:pointer;padding:2px 6px;border-radius:5px;
                 transition:background .15s"
          onmouseover="this.style.background='#f4f3ef'"
          onmouseout="this.style.background='none'">
          Sign out
        </button>
      </div>`;
  }

  // Global logout function
  window.logout = async function() {
    await window._sb.auth.signOut();
    window.location.href = "/dashboard/login";
  };

})();