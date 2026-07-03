// static/dashboard/js/views/tenant_files.js
(function () {
  let tenantId    = null;
  let allFiles    = [];
  let pendingFile = null;

  const domainClass = {
    car_specs:      "d-car",
    rebates_promos: "d-rebate",
    faq_support:    "d-faq",
    surat_khabar:   "d-news",
  };

  function fmtSize(bytes) {
    if (!bytes) return "—";
    if (bytes < 1024)       return bytes + " B";
    if (bytes < 1024*1024)  return (bytes/1024).toFixed(1) + " KB";
    return (bytes/1024/1024).toFixed(1) + " MB";
  }

  function fmtDate(ts) {
    if (!ts) return "—";
    return new Date(ts).toLocaleDateString("en-MY");
  }

  function toast(msg, type="ok") {
    const el=document.getElementById("toast"); el.textContent=msg; el.className=`toast ${type} show`;
    setTimeout(()=>{el.className="toast";}, 2500);
  }

  async function loadFiles() {
    if (!tenantId) return;
    const res = await authedFetch(`/api/tenant/${tenantId}/files`);
    allFiles  = await res.json();
    renderFilesTable();
  }

  function renderFilesTable() {
    const q  = document.getElementById("search").value.toLowerCase();
    const fd = document.getElementById("filter-domain").value;
    const fs = document.getElementById("filter-status").value;

    let rows = allFiles.filter(f => {
      if (q  && !f.file_name.toLowerCase().includes(q)) return false;
      if (fd && f.domain !== fd)       return false;
      if (fs === "1" && !f.is_enabled) return false;
      if (fs === "0" &&  f.is_enabled) return false;
      return true;
    });

    document.getElementById("row-count").textContent =
      `${rows.length} of ${allFiles.length} files`;

    const active   = allFiles.filter(f => f.is_enabled);
    const chunks   = active.reduce((a, f) => a + (f.chunk_count || 0), 0);
    const totalSize= allFiles.reduce((a, f) => a + (f.file_size  || 0), 0);
    document.getElementById("s-total").textContent  = allFiles.length;
    document.getElementById("s-active").textContent = active.length;
    document.getElementById("s-chunks").textContent = chunks;
    document.getElementById("s-size").textContent   = fmtSize(totalSize);

    const tbody = document.getElementById("tbody");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state">
        No files yet — upload a PDF to get started</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(f => `
      <tr>
        <td style="font-weight:500" title="${f.file_name}">
          <svg width="13" height="13" fill="none" stroke="var(--muted)"
               stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-2px;margin-right:5px">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>${f.file_name}
        </td>
        <td><span class="d-badge ${domainClass[f.domain]||"d-car"}">${f.domain}</span></td>
        <td style="text-transform:uppercase;font-size:12px;color:var(--muted)">${f.file_type||"pdf"}</td>
        <td style="font-size:13px">${f.chunk_count || "—"}</td>
        <td style="font-size:12px;color:var(--muted)">${fmtSize(f.file_size)}</td>
        <td style="font-size:12px;color:var(--muted)">${fmtDate(f.created_at)}</td>
        <td>
          <label class="toggle" aria-label="Enable ${f.file_name}">
            <input type="checkbox" ${f.is_enabled ? "checked" : ""}
              onchange="toggleFile('${f.id}', this.checked)">
            <span class="slider"></span>
          </label>
        </td>
        <td>
          <button class="btn btn-sm btn-danger" title="Delete file"
            onclick="deleteFile('${f.id}', '${f.file_name}')">
            <svg width="12" height="12" fill="none" stroke="currentColor"
                 stroke-width="2" viewBox="0 0 24 24">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
            </svg>
          </button>
        </td>
      </tr>`).join("");
  }

  function handleDrop(e) {
    e.preventDefault();
    document.getElementById("drop-zone").classList.remove("drag");
    const files = e.dataTransfer.files;
    if (files.length) showUploadConfig(files[0]);
  }

  function handleFileSelect(files) {
    if (files.length) showUploadConfig(files[0]);
  }

  function showUploadConfig(file) {
    pendingFile = file;
    document.getElementById("f-filename").value = file.name;
    document.getElementById("upload-config").style.display = "flex";
    document.getElementById("upload-progress").style.display = "none";
  }

  function cancelUpload() {
    pendingFile = null;
    document.getElementById("upload-config").style.display = "none";
    document.getElementById("file-input").value = "";
  }

  async function uploadFile() {
    if (!pendingFile || !tenantId) return;

    const domain = document.getElementById("f-domain").value;
    const brand  = document.getElementById("f-brand").value;
    const model  = document.getElementById("f-model").value;

    document.getElementById("upload-config").style.display = "none";
    const prog = document.getElementById("upload-progress");
    const fill = document.getElementById("progress-fill");
    const lbl  = document.getElementById("progress-label");
    prog.style.display = "block";

    lbl.textContent = `Uploading ${pendingFile.name}...`;
    fill.style.width = "30%";
    setTimeout(() => { fill.style.width = "60%"; lbl.textContent = "Ingesting into knowledge base..."; }, 800);
    setTimeout(() => { fill.style.width = "85%"; lbl.textContent = "Creating embeddings..."; }, 2000);

    const fd = new FormData();
    fd.append("file",   pendingFile);
    fd.append("domain", domain);
    fd.append("brand",  brand);
    fd.append("model",  model);

    try {
      const res  = await authedFetch(`/api/tenant/${tenantId}/files/upload`, {method:"POST", body:fd});
      const data = await res.json();

      fill.style.width = "100%";
      if (data.status === "ok") {
        lbl.textContent = `✓ ${data.file} ingested — ${data.chunks} chunks created`;
        setTimeout(() => {
          prog.style.display = "none";
          fill.style.width   = "0%";
          document.getElementById("file-input").value = "";
          pendingFile = null;
          loadFiles();
        }, 1500);
      } else {
        lbl.textContent = "Error: " + JSON.stringify(data);
      }
    } catch(e) {
      lbl.textContent = "Upload failed: " + e.message;
    }
  }

  async function toggleFile(id, enabled) {
    await authedFetch(`/api/tenant/${tenantId}/files/${id}`, {
      method:  "PATCH",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({is_enabled: enabled})
    });
    allFiles = allFiles.map(f => f.id === id ? {...f, is_enabled: enabled} : f);
    renderFilesTable();
  }

  async function deleteFile(id, name) {
    if (!confirm(`Delete "${name}"?\n\nThis removes it from the knowledge base permanently.`))
      return;
    await authedFetch(`/api/tenant/${tenantId}/files/${id}`, {method: "DELETE"});
    await loadFiles();
    toast("File deleted", "ok");
  }

  window.loadFiles         = loadFiles;
  window.renderFilesTable  = renderFilesTable;
  window.handleDrop        = handleDrop;
  window.handleFileSelect  = handleFileSelect;
  window.uploadFile        = uploadFile;
  window.cancelUpload      = cancelUpload;
  window.toggleFile        = toggleFile;
  window.deleteFile        = deleteFile;

  window.dashboardViews = window.dashboardViews || {};
  window.dashboardViews["/dashboard/tenant/files"] = async function initFilesView() {
    const profile = await window._profileReady;
    if (!profile?.tenant_id) return;
    tenantId = profile.tenant_id;

    const t = await fetch(`/api/tenants/${tenantId}`).then(r => r.json());
    document.getElementById("s-initials").textContent      = t.brand_initials || "CP";
    document.getElementById("s-initials").style.background = t.brand_color || "#1a6f4a";
    document.getElementById("s-name").textContent          = t.name || "My Dashboard";
    document.getElementById("topbar-sub").textContent      = `${t.name} — knowledge base documents`;
    document.documentElement.style.setProperty("--primary", t.brand_color || "#1a6f4a");

    await loadFiles();
  };
})();
