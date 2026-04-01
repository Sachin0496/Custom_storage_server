import re

with open("static/index.html", "r") as f:
    html = f.read()

# 1. Nav change
html = html.replace(
    '<button class="nav-btn active" id="nav-files" onclick="showPage(\'files\')">Files</button>',
    '<button class="nav-btn active" id="nav-files" onclick="showPage(\'files\')">Files</button>\n    <button class="nav-btn" id="nav-shares" onclick="showPage(\'shares\')">Drives</button>'
)

# 2. Shares page HTML structure
shares_page_html = """
  <!-- ═══ SHARES PAGE ═══ -->
  <div class="page" id="page-shares">
    <div class="card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <div style="font-size:16px;font-weight:600;flex:1" id="shares-title">Shared Drives</div>
        <button class="btn btn-ghost btn-sm" onclick="loadSharesView()">↻ Refresh</button>
      </div>
      
      <!-- Breadcrumb -->
      <div id="shares-breadcrumb" style="font-size:13px; font-family:monospace; color:var(--accent); margin-bottom:16px; display:none; flex-wrap:wrap; gap:6px;">
      </div>

      <div class="file-grid" id="shares-list">
        <!-- populated via js -->
      </div>
    </div>
  </div>

  <!-- ═══ ADMIN PAGE ═══ -->
"""
html = html.replace("  <!-- ═══ ADMIN PAGE ═══ -->", shares_page_html.strip())


# 3. Admin Shares HTML
admin_shares_html = """
    <div class="card">
      <div class="card-title">Shared Drives</div>
      <div class="card-sub">Map local folders on the host machine so users can browse them.</div>
      <div class="form-group">
        <label>Drive Name</label>
        <input type="text" id="admin-share-name" placeholder="e.g. Movies" />
      </div>
      <div class="form-group">
        <label>Absolute Path</label>
        <input type="text" id="admin-share-path" placeholder="e.g. /Users/sachin/Movies or D:\\Movies" />
      </div>
      <button class="btn btn-primary" onclick="addAdminShare()">Add Drive</button>
      
      <div style="margin-top:20px; font-weight:600; font-size:14px; margin-bottom:10px;">Mapped Drives</div>
      <div id="admin-shares-list" class="file-grid">
         <div style="color:var(--muted);font-size:14px">Loading…</div>
      </div>
    </div>

    <!-- QR panel -->
"""
html = html.replace("    <!-- QR panel -->", admin_shares_html.strip())


# 4. JS Global State
js_state = """
let CURRENT_SHARE_ID = null;
let CURRENT_SHARE_PATH = "";
let ALL_SHARES = [];
"""
html = html.replace("const API = '';              // same origin", "const API = '';              // same origin\n" + js_state)


# 5. JS showPage() modify
show_page_old = """  if (name === 'files') loadFiles();
  if (name === 'admin') { loadUsers(); loadAdminQR(); loadStats(); }"""

show_page_new = """  if (name === 'files') loadFiles();
  if (name === 'shares') { CURRENT_SHARE_ID=null; CURRENT_SHARE_PATH=""; loadSharesView(); }
  if (name === 'admin') { loadUsers(); loadAdminQR(); loadStats(); loadAdminShares(); }"""
html = html.replace(show_page_old, show_page_new)


# 6. JS functions (appended at bottom before Init)
shares_js = """
// ── Shares ────────────────────────────────────────────────────────────────────
async function loadSharesView() {
  if (!CURRENT_SHARE_ID) {
    // Load list of shares
    $('shares-breadcrumb').style.display = 'none';
    $('shares-title').textContent = 'Shared Drives';
    try {
      ALL_SHARES = await apiFetch('/api/shares');
      renderSharesList();
    } catch(e) { toast(e.message, 'error'); }
  } else {
    // Load directory
    try {
      const items = await apiFetch(`/api/shares/${CURRENT_SHARE_ID}/browse?path=${encodeURIComponent(CURRENT_SHARE_PATH)}`);
      renderShareDir(items);
      renderBreadcrumb();
    } catch(e) {
      toast(e.message, 'error');
      // fallback
      CURRENT_SHARE_ID = null;
      CURRENT_SHARE_PATH = "";
      loadSharesView();
    }
  }
}

function renderSharesList() {
  const el = $('shares-list');
  if (!ALL_SHARES.length) {
    el.innerHTML = '<div class="empty-state"><p>No shared drives available.</p></div>';
    return;
  }
  el.innerHTML = ALL_SHARES.map(s => `
    <div class="file-row" style="cursor:pointer" onclick="openShare('${s.id}', '${escHtml(s.name).replace(/'/g, "\\'")}')">
      <div class="file-icon">💾</div>
      <div class="file-info">
        <div class="file-name">${escHtml(s.name)}</div>
        <div class="file-meta">Created: ${fmtDate(s.created_at)}</div>
      </div>
    </div>
  `).join('');
}

function openShare(id, name) {
  CURRENT_SHARE_ID = id;
  CURRENT_SHARE_PATH = "";
  $('shares-title').textContent = name;
  loadSharesView();
}

function renderBreadcrumb() {
  const bc = $('shares-breadcrumb');
  bc.style.display = 'flex';
  const parts = CURRENT_SHARE_PATH.split('/').filter(Boolean);
  let html = `<span style="cursor:pointer; text-decoration:underline" onclick="navShareDir(-1)">Home</span>`;
  let accum = "";
  for (let i = 0; i < parts.length; i++) {
    accum += (accum ? "/" : "") + parts[i];
    const pathArg = accum;
    html += ` <span>/</span> <span style="cursor:pointer; text-decoration:underline" onclick="navShareDir('${escHtml(pathArg).replace(/'/g, "\\'")}')">${escHtml(parts[i])}</span>`;
  }
  bc.innerHTML = html;
}

function navShareDir(path) {
  if (path === -1) {
    CURRENT_SHARE_ID = null;
    CURRENT_SHARE_PATH = "";
  } else {
    CURRENT_SHARE_PATH = path;
  }
  loadSharesView();
}

function renderShareDir(items) {
  const el = $('shares-list');
  if (!items.length) {
    el.innerHTML = '<div class="empty-state"><p>Folder is empty</p></div>';
    return;
  }
  el.innerHTML = items.map(item => {
    const isDir = item.type === 'dir';
    const icon = isDir ? '📁' : fileIcon(item.name);
    const sz = isDir ? 'Folder' : fmtSize(item.size);
    const subpath = CURRENT_SHARE_PATH ? CURRENT_SHARE_PATH + '/' + item.name : item.name;
    const pathArg = subpath.replace(/'/g, "\\'");
    
    const onClick = isDir ? `onclick="navShareDir('${escHtml(pathArg)}')" style="cursor:pointer"` : '';
    
    return `
    <div class="file-row" ${onClick}>
      <div class="file-icon">${icon}</div>
      <div class="file-info">
        <div class="file-name">${escHtml(item.name)}</div>
        <div class="file-meta">${sz} &nbsp;·&nbsp; ${fmtDate(item.modified_at)}</div>
      </div>
      <div class="file-actions">
        ${!isDir ? `<button class="btn btn-ghost btn-sm" onclick="downloadShareFile('${CURRENT_SHARE_ID}','${escHtml(pathArg)}','${escHtml(item.name).replace(/'/g, "\\'")}')">⬇ Download</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

function downloadShareFile(shareId, subpath, name) {
  if (window.event) window.event.stopPropagation();
  const url = `/api/shares/${shareId}/download?path=${encodeURIComponent(subpath)}`;
  toast('Downloading ' + name + '...');
  apiFetchBlob(url).then(blob => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }).catch(e => toast('Download failed: ' + e.message, 'error'));
}

async function loadAdminShares() {
  try {
    const shares = await apiFetch('/api/shares');
    const el = $('admin-shares-list');
    if (!shares.length) { el.innerHTML = '<div style="color:var(--muted);font-size:14px">No drives mapped.</div>'; return; }
    el.innerHTML = shares.map(s => `
      <div class="file-row">
        <div class="file-icon">💾</div>
        <div class="file-info">
          <div class="file-name">${escHtml(s.name)}</div>
          <div class="file-meta" style="word-break:break-all">${escHtml(s.path)}</div>
        </div>
        <div class="file-actions">
          <button class="btn btn-danger btn-sm" onclick="removeAdminShare('${s.id}')">✕</button>
        </div>
      </div>
    `).join('');
  } catch(e) { }
}

async function addAdminShare() {
  const name = $('admin-share-name').value.trim();
  const path = $('admin-share-path').value.trim();
  if (!name || !path) return toast('Name and path required', 'error');
  try {
    await apiFetch('/api/admin/shares', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, path })
    });
    $('admin-share-name').value = '';
    $('admin-share-path').value = '';
    toast('Drive added');
    loadAdminShares();
  } catch(e) { toast(e.message, 'error'); }
}

async function removeAdminShare(id) {
  if (!confirm('Remove this mapped drive?')) return;
  try {
    await apiFetch(`/api/admin/shares/${id}`, { method: 'DELETE' });
    toast('Drive removed');
    loadAdminShares();
  } catch(e) { toast(e.message, 'error'); }
}

// ── Init ──────────────────────────────────────────────────────────────────────
"""
html = html.replace("// ── Init ──────────────────────────────────────────────────────────────────────", shares_js.strip())

with open("static/index.html", "w") as f:
    f.write(html)
