// static/dashboard/js/views/tenant_inventory.js
(function () {
  let tenantId     = null;
  let allItems     = [];
  let editingCarId = null;

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-MY", {day:"2-digit",month:"short",year:"numeric"}) +
      " " + d.toLocaleTimeString("en-MY", {hour:"2-digit",minute:"2-digit"});
  }

  function fmtPrice(n) {
    if (n === null || n === undefined) return "—";
    return "RM" + Number(n).toLocaleString("en-MY", {maximumFractionDigits: 0});
  }

  function numOrNull(v) {
    if (v === "" || v === null || v === undefined) return null;
    const n = Number(v);
    return isNaN(n) ? null : n;
  }

  async function loadInventory() {
    if (!tenantId) return;
    const res = await authedFetch(`/api/tenant/${tenantId}/inventory`);
    allItems  = await res.json();
    renderInventoryTable();
  }

  async function checkLiveApi() {
    try {
      const res  = await authedFetch(`/api/tenant/${tenantId}/external-api`);
      const data = await res.json();
      const hasApi = !!data.base_url;
      document.getElementById("live-badge").style.display    = hasApi ? "inline-block" : "none";
      document.getElementById("sync-api-btn").style.display  = hasApi ? "inline-flex"  : "none";
    } catch (e) { /* ignore */ }
  }

  async function syncFromApi() {
    const btn = document.getElementById("sync-api-btn");
    btn.disabled = true;
    btn.textContent = "Syncing…";
    const resetBtn = () => {
      btn.innerHTML = `<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/><path d="M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15"/></svg> Sync from API`;
      btn.disabled = false;
    };
    try {
      const res  = await authedFetch(`/api/tenant/${tenantId}/inventory/sync`, {method: "POST"});
      const data = await res.json();
      if (res.ok) {
        await loadInventory();
        btn.textContent = `Synced ${data.synced} cars`;
        setTimeout(resetBtn, 3000);
      } else {
        alert(data.error || "Sync failed");
        resetBtn();
      }
    } catch (e) {
      alert("Network error");
      resetBtn();
    }
  }

  function renderInventoryTable() {
    const q  = document.getElementById("search").value.toLowerCase();
    const fs = document.getElementById("filter-status").value;

    const rows = allItems.filter(c => {
      if (fs && c.status !== fs) return false;
      if (!q) return true;
      return (c.brand || "").toLowerCase().includes(q)
          || (c.model || "").toLowerCase().includes(q)
          || (c.variant || "").toLowerCase().includes(q);
    });

    document.getElementById("row-count").textContent = `${rows.length} of ${allItems.length} items`;

    const available = allItems.filter(c => c.status === "available");
    const oos        = allItems.filter(c => !c.stock || c.stock <= 0);
    const lastUpdate = allItems.reduce((latest, c) =>
      (!latest || (c.updated_at && c.updated_at > latest)) ? c.updated_at : latest, null);

    document.getElementById("s-total").textContent     = allItems.length;
    document.getElementById("s-available").textContent = available.length;
    document.getElementById("s-oos").textContent       = oos.length;
    document.getElementById("s-updated").textContent   = lastUpdate ? fmtDate(lastUpdate) : "—";

    const tbody = document.getElementById("tbody");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="empty-state">
        No inventory data yet — sync your stock via API Manager, or click "Add item"</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(c => `
      <tr>
        <td style="font-weight:500">${c.brand || "—"}</td>
        <td>${c.model || "—"}</td>
        <td>${c.variant || "—"}</td>
        <td>${c.year || "—"}</td>
        <td>${fmtPrice(c.price_otr)}</td>
        <td>${c.stock ?? "—"}</td>
        <td><span class="badge ${c.status === "available" ? "badge-ok" : "badge-off"}">${c.status || "—"}</span></td>
        <td>${c.colour || "—"}</td>
        <td style="font-size:12px;color:var(--muted)">${fmtDate(c.updated_at)}</td>
        <td>
          <div class="row-actions">
            <button class="btn btn-sm" onclick='openModal(${JSON.stringify(c).replace(/'/g, "&apos;")})'>Edit</button>
            <button class="btn btn-sm btn-danger" onclick="deleteItem('${c.car_id}')">Delete</button>
          </div>
        </td>
      </tr>`).join("");
  }

  function openModal(car) {
    editingCarId = car ? car.car_id : null;
    document.getElementById("modal-title").textContent = car ? "Edit inventory item" : "Add inventory item";

    document.getElementById("m-car-id").value       = car?.car_id || "";
    document.getElementById("m-car-id").disabled    = !!car;
    document.getElementById("m-status").value       = car?.status || "available";
    document.getElementById("m-brand").value        = car?.brand || "";
    document.getElementById("m-model").value        = car?.model || "";
    document.getElementById("m-variant").value      = car?.variant || "";
    document.getElementById("m-year").value         = car?.year || "";
    document.getElementById("m-price").value        = car?.price_otr ?? "";
    document.getElementById("m-stock").value        = car?.stock ?? "";
    document.getElementById("m-colour").value       = car?.colour || "";
    document.getElementById("m-transmission").value = car?.transmission || "";
    document.getElementById("m-engine").value       = car?.engine_cc ?? "";
    document.getElementById("m-fuel").value         = car?.fuel_cons ?? "";

    document.getElementById("modal-overlay").classList.add("open");
  }

  function closeModal() {
    document.getElementById("modal-overlay").classList.remove("open");
    editingCarId = null;
  }

  async function saveItem() {
    const carId = document.getElementById("m-car-id").value.trim();
    if (!editingCarId && !carId) { alert("Item ID is required"); return; }

    const body = {
      status:       document.getElementById("m-status").value,
      brand:        document.getElementById("m-brand").value.trim(),
      model:        document.getElementById("m-model").value.trim(),
      variant:      document.getElementById("m-variant").value.trim(),
      year:         numOrNull(document.getElementById("m-year").value),
      price_otr:    numOrNull(document.getElementById("m-price").value),
      stock:        numOrNull(document.getElementById("m-stock").value),
      colour:       document.getElementById("m-colour").value.trim(),
      transmission: document.getElementById("m-transmission").value.trim(),
      engine_cc:    numOrNull(document.getElementById("m-engine").value),
      fuel_cons:    numOrNull(document.getElementById("m-fuel").value),
    };

    let res;
    if (editingCarId) {
      res = await authedFetch(`/api/tenant/${tenantId}/inventory/${editingCarId}`, {
        method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
      });
    } else {
      body.car_id = carId;
      res = await authedFetch(`/api/tenant/${tenantId}/inventory`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
      });
    }

    if (res.ok) {
      closeModal();
      await loadInventory();
    } else {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Save failed");
    }
  }

  async function deleteItem(carId) {
    if (!confirm(`Delete "${carId}"? This cannot be undone.`)) return;
    await authedFetch(`/api/tenant/${tenantId}/inventory/${carId}`, {method: "DELETE"});
    await loadInventory();
  }

  window.loadInventory       = loadInventory;
  window.syncFromApi         = syncFromApi;
  window.renderInventoryTable = renderInventoryTable;
  window.openModal           = openModal;
  window.closeModal          = closeModal;
  window.saveItem            = saveItem;
  window.deleteItem          = deleteItem;

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant/inventory"] = async function initInventoryView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const tenantPromise = fetch(`/api/tenants/${tenantId}`).then(r => r.json());

    await Promise.all([
      tenantPromise.then(t => {
        document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
        document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
        document.getElementById("s-name").textContent          = t.name || "My Dashboard";
        document.getElementById("topbar-sub").textContent      = `${t.name} — items synced from your website`;
        document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");
      }),
      loadInventory(),
      checkLiveApi(),
    ]);
  };
})();
