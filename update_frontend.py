import re

with open("static/index.html", "r") as f:
    html = f.read()

# 1. Update HTML UI
shares_header_old = """      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <div style="font-size:16px;font-weight:600;flex:1" id="shares-title">Shared Drives</div>
        <button class="btn btn-ghost btn-sm" onclick="loadSharesView()">↻ Refresh</button>
      </div>"""

shares_header_new = """      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <div style="font-size:16px;font-weight:600;flex:1" id="shares-title">Shared Drives</div>
        <div id="shares-actions" style="display:none; gap:8px;">
           <button class="btn btn-primary btn-sm" onclick="promptCreateShareDir()">+ Folder</button>
           <button class="btn btn-primary btn-sm" onclick="document.getElementById('share-file-input').click()">↑ Upload</button>
           <input type="file" id="share-file-input" style="display:none" multiple onchange="uploadShareFile(this.files)" />
        </div>
        <button class="btn btn-ghost btn-sm" onclick="loadSharesView()">↻ Refresh</button>
      </div>"""
html = html.replace(shares_header_old, shares_header_new)

# 2. Update loadSharesView
loadSharesView_old = """  if (!CURRENT_SHARE_ID) {
    // Load list of shares
    $('shares-breadcrumb').style.display = 'none';
    $('shares-title').textContent = 'Shared Drives';"""

loadSharesView_new = """  if (!CURRENT_SHARE_ID) {
    // Load list of shares
    $('shares-breadcrumb').style.display = 'none';
    $('shares-actions').style.display = 'none';
    $('shares-title').textContent = 'Shared Drives';"""
html = html.replace(loadSharesView_old, loadSharesView_new)

loadSharesView_else_old = """  } else {
    // Load directory
    try {"""

loadSharesView_else_new = """  } else {
    // Load directory
    $('shares-actions').style.display = (SESSION?.permissions?.upload || SESSION?.role === 'admin') ? 'flex' : 'none';
    try {"""
html = html.replace(loadSharesView_else_old, loadSharesView_else_new)


# 3. Update renderShareDir
renderShareDir_actions_old = """      <div class="file-actions">
        ${!isDir ? `<button class="btn btn-ghost btn-sm" onclick="downloadShareFile('${CURRENT_SHARE_ID}','${escHtml(pathArg)}','${escHtml(item.name).replace(/'/g, "\\\\'")}')">⬇ Download</button>` : ''}
      </div>"""

renderShareDir_actions_new = """      <div class="file-actions">
        ${!isDir ? `<button class="btn btn-ghost btn-sm" onclick="downloadShareFile('${CURRENT_SHARE_ID}','${escHtml(pathArg).replace(/'/g, "\\\\\\'")}','${escHtml(item.name).replace(/'/g, "\\\\'")}')">⬇ Download</button>` : ''}
        ${(SESSION?.permissions?.delete || SESSION?.role === 'admin') ? `<button class="btn btn-danger btn-sm" onclick="deleteShareItem('${CURRENT_SHARE_ID}','${escHtml(pathArg).replace(/'/g, "\\\\'")}')">✕</button>` : ''}
      </div>"""

# Wait, `escHtml(pathArg)` was originally passed in directly without `.replace(/'/g, "\\'")` for pathArg in my previous renderShareDir but wait, let's fix it properly using regex matching if needed. Let's just do a regex replace for the file-actions block.
actions_regex = re.compile(r'<div class="file-actions">\s*\$\{!isDir \? `<button class="btn btn-ghost btn-sm" onclick="downloadShareFile\(\'\$\{CURRENT_SHARE_ID\}\',\'\$\{escHtml\(pathArg\)\}\',\'\$\{escHtml\(item\.name\)\.replace\(/\\\\\\\'/g, "\\\\\\\\\\\\\'"\)\}\'\)">⬇ Download</button>` : \'\'\}\s*</div>')
# Actually regex matching is tricky with these template literals. Let's find the exact string.

if 'downloadShareFile(\'${CURRENT_SHARE_ID}\',\'${escHtml(pathArg)}\',\'' in html:
    html = html.replace(
        "downloadShareFile('${CURRENT_SHARE_ID}','${escHtml(pathArg)}','${escHtml(item.name).replace(/'/g, \"\\\\'\")}')\">⬇ Download</button>` : ''}\n      </div>",
        "downloadShareFile('${CURRENT_SHARE_ID}','${escHtml(pathArg).replace(/'/g, \"\\\\'\")}','${escHtml(item.name).replace(/'/g, \"\\\\'\")}')\">⬇ Download</button>` : ''}\n        ${(SESSION?.permissions?.delete || SESSION?.role === 'admin') ? `<button class=\"btn btn-danger btn-sm\" onclick=\"deleteShareItem('${CURRENT_SHARE_ID}','${escHtml(pathArg).replace(/'/g, \"\\\\'\")}')\">✕</button>` : ''}\n      </div>"
    )

# 4. Add JS functions
new_js = """
async function promptCreateShareDir() {
  const name = prompt("Folder name:");
  if (!name) return;
  try {
    await apiFetch(`/api/shares/${CURRENT_SHARE_ID}/mkdir?path=${encodeURIComponent(CURRENT_SHARE_PATH)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
    toast("Folder created");
    loadSharesView();
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteShareItem(shareId, subpath) {
  if (window.event) window.event.stopPropagation();
  if (!confirm("Delete this item?")) return;
  try {
    await apiFetch(`/api/shares/${shareId}/item?path=${encodeURIComponent(subpath)}`, { method: 'DELETE' });
    toast("Item deleted");
    loadSharesView();
  } catch(e) { toast(e.message, 'error'); }
}

async function uploadShareFile(files, overwrite=false) {
  if (!files.length) return;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    try {
      const fd = new FormData();
      fd.append('file', f);
      const res = await fetch(`${API}/api/shares/${CURRENT_SHARE_ID}/upload?path=${encodeURIComponent(CURRENT_SHARE_PATH)}&overwrite=${overwrite}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${SESSION.bearer}` },
        body: fd,
      });
      if (!res.ok) {
        if (res.status === 409) {
          if (confirm(`File "${f.name}" already exists. Replace it?`)) {
            await uploadShareFile([f], true);
            continue;
          } else {
            continue;
          }
        }
        const e = await res.json().catch(()=>({}));
        toast(`Upload failed: ${e.detail || 'Unknown error'}`, 'error');
        continue;
      }
      toast(`Uploaded ${f.name}`);
    } catch(e) { toast(e.message, 'error'); }
  }
  $('share-file-input').value = '';
  loadSharesView();
}

async function loadAdminShares() {
"""
html = html.replace("async function loadAdminShares() {", new_js.strip())

with open("static/index.html", "w") as f:
    f.write(html)
