"use strict";
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const store = {
  get token() { try { return localStorage.getItem("token") || ""; } catch { return ""; } },
  get user() { try { return localStorage.getItem("user") || ""; } catch { return ""; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function when(t) { return new Date(t * 1000).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" }); }
function size(b) { return b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.ceil(b / 1e3) + " KB"; }
function toast(msg, err = false) {
  const d = document.createElement("div"); d.textContent = msg; if (err) d.className = "err";
  $("#toast").append(d); setTimeout(() => d.remove(), err ? 7000 : 3500);
}
function link(path) { return path + (store.token ? (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(store.token) : ""); }
const STATUS_TR = { queued: "kuyrukta", running: "çalışıyor", done: "tamam", error: "hata" };
const badge = s => `<span class="badge ${s}">${STATUS_TR[s] || s}</span>`;

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (store.token) headers.Authorization = "Bearer " + store.token;
  if (store.user) headers["X-User"] = encodeURIComponent(store.user);
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) { openSettings(); throw new Error("Erişim anahtarı gerekli"); }
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.detail || "İstek başarısız (" + r.status + ")"); e.data = data; throw e; }
  return data;
}

// --- ayarlar & durum ---------------------------------------------------------
function openSettings() { $("#tokenInput").value = store.token; $("#userInput").value = store.user; $("#settings").showModal(); }
$("#settingsBtn").onclick = openSettings;
$("#settingsSave").onclick = () => { store.set("token", $("#tokenInput").value.trim()); store.set("user", $("#userInput").value.trim()); setTimeout(route, 0); };

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const online = s.agents.filter(a => a.online);
    $("#status").innerHTML =
      `<span><i class="dot ${s.claude ? "on" : ""}"></i>Claude Code</span>` +
      `<span title="${esc(s.agents.map(a => a.name).join(", "))}"><i class="dot ${online.length ? "on" : ""}"></i>InDesign ajanı${online.length ? " (" + online.length + ")" : ""}</span>`;
  } catch { /* yok say */ }
}

// --- yönlendirme ---------------------------------------------------------------
let cleanup = null;
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  try {
    if (parts[0] === "doc" && parts[1]) await docView(parts[1], parts[2] || "metin");
    else await homeView();
  } catch (e) { view.innerHTML = `<div class="card">${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);

// --- ana sayfa -------------------------------------------------------------------
async function homeView() {
  const { documents, pending } = await api("/api/documents");
  view.innerHTML = `
    <div class="drop" id="drop">
      <b>.idml veya .indd dosyası sürükleyin</b> ya da tıklayıp seçin
      <div class="help">.indd dosyaları masaüstü InDesign ajanı tarafından IDML'e çevrilir.</div>
      <input type="file" id="file" accept=".idml,.indd" multiple hidden>
    </div>
    ${pending.length ? `<h2>Dönüştürülmeyi bekleyenler</h2><ul class="list">${pending.map(j =>
      `<li>${badge(j.status)} ${esc(j.params.filename)} <span class="muted small">${when(j.created)}</span>${j.error ? `<span class="small" style="color:var(--err)">${esc(j.error)}</span>` : ""}</li>`).join("")}</ul>` : ""}
    ${documents.some(d => d.kind !== "design") ? `
    <form class="card newdesign" id="newdesign">
      <b>Yeni dergi sayfası tasarla</b>
      <div class="help">Boş dergi sayfanızı (.indd) şablon olarak yükleyin; Claude yazı ve görsellerinizi bu şablonun stillerine, vinyetlerine ve kenar boşluklarına sadık kalarak yerleştirir.</div>
      <div class="row" style="margin-top:10px">
        <input id="dname" placeholder="Tasarım adı (örn. Sayı 12 — Röportaj)" required style="flex:2;min-width:200px">
        <select id="dtemplate" style="flex:1;min-width:160px">${documents.filter(d => d.kind !== "design").map(d => `<option value="${esc(d.slug)}">Şablon: ${esc(d.name)}</option>`).join("")}</select>
        <button>Oluştur</button>
      </div>
    </form>` : ""}
    <h2>Belgeler</h2>
    ${documents.length ? `<div class="grid">${documents.map(d => `
      <a class="card doc-card" href="#/doc/${encodeURIComponent(d.slug)}">
        <h3>${esc(d.name)} ${d.kind === "design" ? `<span class="badge design">tasarım</span>` : ""}</h3>
        ${d.kind === "design" ? `<div class="muted small">Şablon: ${esc(d.template_name || d.template)}</div>` : ""}
        <div class="muted small">${d.info.paragraphs} paragraf · ${d.info.words} kelime · ${d.info.spreads} yayılım</div>
        <div class="muted small">Güncelleme: ${when(d.updated)}</div>
      </a>`).join("")}</div>` : `<p class="muted">Henüz belge yok. InDesign'da <i>Dosya → Farklı Kaydet → InDesign Markup (IDML)</i> ile bir dosya kaydedip buraya yükleyin.</p>`}`;
  const drop = $("#drop"), input = $("#file");
  drop.onclick = () => input.click();
  input.onchange = () => upload([...input.files]);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); };
  const nd = $("#newdesign");
  if (nd) nd.onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await api("/api/designs", { method: "POST", json: { name: $("#dname").value, template: $("#dtemplate").value } });
      location.hash = `#/doc/${encodeURIComponent(r.document.slug)}/tasarim`;
    } catch (err) { toast(err.message, true); }
  };
  if (pending.some(j => j.status !== "error")) { const t = setTimeout(route, 5000); cleanup = () => clearTimeout(t); }
}

async function upload(files, slug) {
  for (const f of files) {
    const fd = new FormData(); fd.append("file", f); if (slug) fd.append("slug", slug);
    try {
      const r = await api("/api/documents", { method: "POST", body: fd });
      toast(r.pending ? `${f.name}: InDesign ajanının dönüştürmesi bekleniyor` : `${f.name} yüklendi`);
    } catch (e) { toast(`${f.name}: ${e.message}`, true); }
  }
  route();
}

// --- belge sayfası ---------------------------------------------------------------
const TABS = [["metin", "Metin"], ["gecmis", "Geçmiş"], ["ciktilar", "PDF & Dosyalar"], ["claude", "Claude"]];
const DESIGN_TABS = [["tasarim", "Tasarım"], ["metin", "Metin"], ["gecmis", "Geçmiş"]];
async function docView(slug, tab) {
  const { document: d } = await api(`/api/documents/${slug}`);
  const isDesign = d.kind === "design";
  if (!location.hash.split("/")[3]) tab = isDesign ? "tasarim" : "metin";
  view.innerHTML = `
    <div class="row">
      <div><h1>${esc(d.name)}</h1><div class="muted small">${esc(d.filename)} · ${d.info.stories} hikâye · ${d.info.paragraphs} paragraf · ${d.info.words} kelime</div></div>
      <span class="spacer"></span>
      <a class="btn ghost" href="${link(`/api/documents/${slug}/download.idml`)}">IDML indir</a>
      ${isDesign ? "" : `<button class="ghost" id="newver">Yeni sürüm yükle</button>
      <input type="file" id="verfile" accept=".idml,.indd" hidden>`}
    </div>
    <nav class="tabs">${(isDesign ? DESIGN_TABS : TABS).map(([k, l]) => `<a href="#/doc/${slug}/${k}" class="${k === tab ? "active" : ""}">${l}</a>`).join("")}</nav>
    <section id="tab"></section>`;
  if (!isDesign) {
    $("#newver").onclick = () => $("#verfile").click();
    $("#verfile").onchange = e => upload([...e.target.files], slug);
  }
  const el = $("#tab");
  ({ tasarim: designTab, metin: textTab, gecmis: historyTab, ciktilar: outputsTab, claude: claudeTab }[tab] || textTab)(slug, el);
}

// --- tasarım sekmesi ---------------------------------------------------------------
const DESIGN_EXAMPLES = [
  "Röportajı 4 sayfaya yerleştir: açılışta tam sayfa fotoğraf ve büyük manşet, sonra 3 sütun gövde, bir sayfaya alıntı kutusu.",
  "Haberi tek sayfaya sığdır; üstte yatay görsel, altında 3 sütun metin.",
  "Görselleri daha büyük kullan, açılış sayfasında başlığı fotoğrafın üzerine al.",
  "2. sayfada metin taşıyor; düzelt ve görsel altı yazılarını ekle.",
];
let designDraft = "";
async function designTab(slug, el) {
  const [ds, { tasks }, status, files] = await Promise.all([
    api(`/api/documents/${slug}/design`), api(`/api/documents/${slug}/ai`), api("/api/status"), api(`/api/documents/${slug}`)]);
  const prof = await api(`/api/documents/${ds.template}/profile`).catch(() => null);
  const running = tasks.find(t => t.status === "running");
  const layoutJob = files.jobs.find(j => j.kind === "layout" && (j.status === "queued" || j.status === "running"));
  const lastLayout = files.jobs.find(j => j.kind === "layout");
  const agentOn = status.agents.some(a => a.online);
  const rep = ds.report || {};
  const out = (n, bust) => link(`/api/documents/${slug}/files/cikti/${encodeURIComponent(n)}${bust ? "?v=" + bust : ""}`);
  const asset = n => link(`/api/documents/${slug}/files/varliklar/${encodeURIComponent(n)}`);
  const bust = lastLayout ? Math.round(lastLayout.updated) : 0;
  const thumb = n => /\.(jpe?g|png)$/i.test(n) ? `<img src="${asset(n)}" alt="" loading="lazy">` : `<div class="noimg">${esc(n.split(".").pop().toUpperCase())}</div>`;
  const issues = [...(rep.overset || []).map(x => "Taşan metin: " + x), ...(rep.missing || []).map(x => "Eksik " + x),
    ...(rep.low_ppi || []).map(x => "Düşük çözünürlük: " + x), ...(rep.errors || []), ...(rep.warnings || [])];

  el.innerHTML = `
    <div class="design-grid">
      <div>
        <div class="card">
          <b>1. Yazı ve görseller</b>
          <div class="drop small-drop" id="adrop">Yazı (.docx, .txt, .md) ve görselleri (.jpg, .png, .tif, .psd) sürükleyin ya da tıklayın
            <input type="file" id="afile" multiple hidden accept=".docx,.txt,.md,.jpg,.jpeg,.png,.tif,.tiff,.psd,.ai,.eps,.pdf"></div>
          ${ds.assets.texts.length ? `<ul class="list compact">${ds.assets.texts.map(t => `<li>📄 ${esc(t.name)} <span class="muted small">${t.words ?? "?"} kelime</span><span class="spacer"></span><button class="ghost xs" data-del="${esc(t.name)}">Sil</button></li>`).join("")}</ul>` : ""}
          ${ds.assets.images.length ? `<div class="thumbs">${ds.assets.images.map(i => `<figure title="${esc(i.name)}">${thumb(i.name)}<figcaption>${esc(i.name)}<br><span class="muted">${i.width_px ? i.width_px + "×" + i.height_px : ""}</span></figcaption><button class="ghost xs" data-del="${esc(i.name)}">×</button></figure>`).join("")}</div>` : ""}
        </div>
        <div class="card" style="margin-top:12px">
          <b>2. Claude'a isteğinizi yazın</b>
          <textarea id="dinstr" rows="4" placeholder="Örn: ${esc(DESIGN_EXAMPLES[0])}" style="margin-top:8px"></textarea>
          <div class="row" style="margin-top:6px">${DESIGN_EXAMPLES.map(x => `<button class="ghost xs" data-ex="${esc(x)}">${esc(x.slice(0, 30))}…</button>`).join("")}</div>
          <div class="row" style="margin-top:10px">
            <span class="small ${agentOn ? "ok" : "warn"}">${agentOn ? "● InDesign bağlı" : "● InDesign ajanı çevrimdışı — InDesign ve başlatıcı açık olmalı"}</span>
            <span class="spacer"></span>
            <button id="drun" ${status.claude && !running ? "" : "disabled"}>${running ? "Claude çalışıyor…" : ds.layout ? "Claude ile düzelt / yeniden tasarla" : "Claude ile tasarla"}</button>
          </div>
          ${status.claude ? "" : `<p class="small warn">Claude Code kurulu değil (README).</p>`}
        </div>
        ${prof ? `<details class="card" style="margin-top:12px"><summary><b>Şablon profili</b> <span class="muted small">${esc(prof.profile.page.width)}×${esc(prof.profile.page.height)} mm · ${prof.profile.masters.length} ana sayfa · ${prof.profile.paragraph_styles.length} paragraf stili</span></summary><pre class="result">${esc(prof.summary)}</pre></details>` : ""}
      </div>
      <div>
        <div class="card">
          <div class="row"><b>3. Sonuç</b><span class="spacer"></span>
            ${ds.layout ? `<button class="ghost xs" id="rerender" ${layoutJob ? "disabled" : ""}>InDesign'da yeniden oluştur</button>` : ""}</div>
          ${running ? `<div class="result">⏳ Claude tasarlıyor: <i>${esc(running.instruction)}</i><br><span class="muted small">Plan yazılıyor, InDesign'da kuruluyor ve önizlemeler kontrol ediliyor. Birkaç dakika sürebilir.</span></div>` : ""}
          ${layoutJob ? `<div class="result">⏳ InDesign sayfaları kuruyor…</div>` : ""}
          ${lastLayout && lastLayout.status === "error" && !layoutJob ? `<div class="result warn">Son InDesign işi hata verdi: ${esc(lastLayout.error)}</div>` : ""}
          ${ds.validation && ds.validation.errors.length ? `<div class="result warn">Plan hataları:<br>${ds.validation.errors.map(esc).join("<br>")}</div>` : ""}
          ${ds.outputs.length ? `<div class="row" style="margin:10px 0">${ds.outputs.map(f => `<a class="btn ghost xs" href="${out(f.name)}">${esc(f.name.split(".").pop().toUpperCase())} indir</a>`).join("")}</div>` : ""}
          ${issues.length ? `<details class="issues" ${rep.overset && rep.overset.length ? "open" : ""}><summary>${issues.length} uyarı</summary><ul>${issues.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : (ds.previews.length ? `<p class="small ok">Taşan metin ve eksik öğe yok.</p>` : "")}
          ${ds.previews.length ? `<div class="previews">${ds.previews.map((n, i) => `<a href="${out(n)}" target="_blank"><img src="${out(n, bust)}" alt="Sayfa ${i + 1}"><span>${rep.geometry && rep.geometry[i] ? "s. " + esc(rep.geometry[i].page) : "Sayfa " + (i + 1)}</span></a>`).join("")}</div>`
            : (!running && !layoutJob ? `<p class="muted">Henüz sayfa yok. Yazı ve görselleri yükleyip Claude'a isteğinizi yazın.</p>` : "")}
        </div>
        ${tasks.length ? `<h2>Claude geçmişi</h2><ul class="list">${tasks.slice(0, 6).map(t => `<li style="display:block">${badge(t.status)} <b>${esc(t.instruction)}</b> <span class="muted small">${when(t.created)}${t.cost_usd ? " · $" + t.cost_usd.toFixed(2) : ""}</span>${t.result ? `<details><summary class="small">Claude'un özeti</summary><div class="result">${esc(t.result)}</div></details>` : ""}${t.error ? `<div class="result warn">${esc(t.error)}</div>` : ""}</li>`).join("")}</ul>` : ""}
      </div>
    </div>`;

  const drop = $("#adrop"), input = $("#afile");
  const send = async fl => {
    const fd = new FormData(); [...fl].forEach(f => fd.append("files", f));
    try { const r = await api(`/api/documents/${slug}/assets`, { method: "POST", body: fd });
      toast(`${r.saved.length} dosya eklendi` + (r.rejected.length ? `, desteklenmeyen: ${r.rejected.join(", ")}` : "")); }
    catch (e) { toast(e.message, true); }
    route();
  };
  drop.onclick = () => input.click();
  input.onchange = () => send(input.files);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files); };
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (!confirm(b.dataset.del + " silinsin mi?")) return;
    await api(`/api/documents/${slug}/assets/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" }); route();
  });
  $("#dinstr").value = designDraft;
  $("#dinstr").oninput = e => { designDraft = e.target.value; };
  el.querySelectorAll("[data-ex]").forEach(b => b.onclick = () => { $("#dinstr").value = designDraft = b.dataset.ex; });
  $("#drun").onclick = async () => {
    const instruction = $("#dinstr").value.trim();
    if (!instruction) { toast("Önce isteğinizi yazın", true); return; }
    if (!ds.assets.texts.length && !ds.assets.images.length && !confirm("Henüz yazı/görsel yüklenmedi. Yine de devam edilsin mi?")) return;
    try { await api(`/api/documents/${slug}/ai`, { method: "POST", json: { instruction } }); designDraft = ""; toast("Claude tasarlıyor…"); route(); }
    catch (e) { toast(e.message, true); }
  };
  const rr = $("#rerender");
  if (rr) rr.onclick = async () => {
    try { await api(`/api/documents/${slug}/render`, { method: "POST" }); toast("InDesign işi gönderildi"); route(); }
    catch (e) { toast((e.data && e.data.errors ? e.data.errors.join("\n") : e.message), true); }
  };
  if (running || layoutJob) { const t = setTimeout(route, 5000); cleanup = () => clearTimeout(t); }
}

async function textTab(slug, el) {
  const { paragraphs } = await api(`/api/documents/${slug}/paragraphs`);
  const orig = new Map(paragraphs.map(p => [p.id, p]));
  let story = null, html = `
    <div class="row"><input id="filter" placeholder="Paragraflarda ara…" style="max-width:360px"><span class="spacer"></span>
    <span class="help"><code>&lt;r1&gt;…&lt;/r1&gt;</code> karakter stili · <code>&lt;x1/&gt;</code> satır içi nesne (silmeyin)</span></div>`;
  for (const p of paragraphs) {
    if (p.story !== story) { story = p.story; html += `<div class="story-h">Hikâye ${esc(story)}</div>`; }
    html += `<div class="para" data-id="${esc(p.id)}"><div class="meta"><span class="style">${esc(p.style || "—")}</span>${esc(p.id)}${p.objects.length ? "<br>" + esc(p.objects.join(", ")) : ""}</div>
      <textarea rows="1" spellcheck="true">${esc(p.text)}</textarea></div>`;
  }
  el.innerHTML = html + `<div class="savebar" id="savebar" hidden><span id="cnt"></span><input id="msg" placeholder="Değişiklik notu (isteğe bağlı)"><button class="ghost" id="undo">Geri al</button><button id="save">Kaydet</button></div>`;
  const fit = t => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; };
  const changed = () => [...el.querySelectorAll(".para")].filter(d => $("textarea", d).value !== orig.get(d.dataset.id).text);
  const update = () => { const c = changed(); el.querySelectorAll(".para").forEach(d => d.classList.toggle("changed", c.includes(d))); $("#savebar").hidden = !c.length; $("#cnt").textContent = `${c.length} değişiklik`; };
  el.querySelectorAll("textarea").forEach(t => { fit(t); t.oninput = () => { fit(t); update(); }; });
  $("#filter").oninput = e => { const q = e.target.value.toLocaleLowerCase("tr"); el.querySelectorAll(".para").forEach(d => d.hidden = q && !$("textarea", d).value.toLocaleLowerCase("tr").includes(q)); };
  $("#undo").onclick = () => { el.querySelectorAll(".para").forEach(d => { const t = $("textarea", d); t.value = orig.get(d.dataset.id).text; fit(t); }); update(); };
  $("#save").onclick = async () => {
    const changes = changed().map(d => ({ id: d.dataset.id, text: $("textarea", d).value, hash: orig.get(d.dataset.id).hash }));
    $("#save").disabled = true;
    try {
      const r = await api(`/api/documents/${slug}/paragraphs`, { method: "PUT", json: { changes, message: $("#msg").value || null } });
      toast(`${r.changed.length} paragraf kaydedildi`); route();
    } catch (e) {
      const errs = [...(e.data?.errors || []), ...(e.data?.conflicts || [])];
      toast(errs.length ? errs.map(x => x.error).join("\n") : e.message, true);
      $("#save").disabled = false;
    }
  };
  const onLeave = e => { if (changed().length) { e.preventDefault(); e.returnValue = ""; } };
  window.addEventListener("beforeunload", onLeave);
  cleanup = () => window.removeEventListener("beforeunload", onLeave);
}

async function historyTab(slug, el) {
  const { history } = await api(`/api/documents/${slug}/history`);
  el.innerHTML = `<ul class="list">${history.map((h, i) => `
    <li data-rev="${h.rev}"><div style="flex:1;min-width:220px"><b>${esc(h.message)}</b><div class="muted small">${esc(h.author)} · ${when(h.time)} · <code>${h.rev.slice(0, 8)}</code></div><div class="diff"></div></div>
      ${i ? `<button class="ghost" data-act="diff">Güncel ile karşılaştır</button>
      <a class="btn ghost" href="${link(`/api/documents/${slug}/download.idml?rev=${h.rev}`)}">İndir</a>
      <button class="ghost" data-act="restore">Bu sürüme dön</button>` : `<span class="badge done">güncel</span>`}</li>`).join("")}</ul>`;
  el.onclick = async e => {
    const act = e.target.dataset.act; if (!act) return;
    const li = e.target.closest("li"), rev = li.dataset.rev;
    if (act === "diff") {
      const { changes } = await api(`/api/documents/${slug}/diff?rev=${rev}`);
      $(".diff", li).innerHTML = changes.length ? changes.map(c => `<div class="muted small">${esc(c.id)}</div>${c.old != null ? `<div class="old">${esc(c.old)}</div>` : ""}${c.new != null ? `<div class="new">${esc(c.new)}</div>` : ""}`).join("") : `<div class="muted">Metin farkı yok</div>`;
    } else if (act === "restore" && confirm("Belge bu sürüme döndürülsün mü? (Geçmiş korunur, yeni bir sürüm olarak eklenir.)")) {
      await api(`/api/documents/${slug}/restore`, { method: "POST", json: { rev } });
      toast("Geri dönüldü"); route();
    }
  };
}

async function outputsTab(slug, el) {
  const { files, jobs } = await api(`/api/documents/${slug}`);
  el.innerHTML = `
    <div class="card"><div class="row"><div style="flex:1"><b>PDF oluştur</b><div class="help">Masaüstü InDesign ajanı belgenin güncel sürümünü açar, seçilen ön ayarla PDF'e aktarır ve buraya yükler.</div></div>
      <select id="preset" style="width:auto"><option>[High Quality Print]</option><option>[Press Quality]</option><option>[Smallest File Size]</option><option>[PDF/X-4:2008]</option></select>
      <button id="pdf">PDF iste</button></div></div>
    <h2>İşler</h2>
    ${jobs.length ? `<ul class="list">${jobs.map(j => `<li>${badge(j.status)} <b>${j.kind === "pdf" ? "PDF" : "INDD → IDML"}</b> <span class="muted small">${when(j.created)}${j.agent ? " · " + esc(j.agent) : ""}</span>
      ${j.result?.file ? `<a href="${link(`/api/documents/${slug}/files/${encodeURIComponent(j.result.file)}`)}">${esc(j.result.file)}</a>` : ""}
      ${j.error ? `<span class="small" style="color:var(--err)">${esc(j.error)}</span>` : ""}</li>`).join("")}</ul>` : `<p class="muted">Henüz iş yok.</p>`}
    <h2>Dosyalar</h2>
    ${files.length ? `<ul class="list">${files.map(f => `<li><a href="${link(`/api/documents/${slug}/files/${encodeURIComponent(f.name)}`)}">${esc(f.name)}</a><span class="muted small">${size(f.size)} · ${when(f.time)}</span></li>`).join("")}</ul>` : `<p class="muted">Dosya yok.</p>`}`;
  $("#pdf").onclick = async () => { await api(`/api/documents/${slug}/pdf`, { method: "POST", json: { preset: $("#preset").value } }); toast("PDF işi kuyruğa alındı"); route(); };
  if (jobs.some(j => j.status === "queued" || j.status === "running")) { const t = setTimeout(route, 5000); cleanup = () => clearTimeout(t); }
}

const EXAMPLES = [
  "Tüm metni İngilizceye çevir; başlıkları kısa ve vurucu tut.",
  "Yazım ve noktalama hatalarını düzelt, anlamı değiştirme.",
  "Tüm fiyatlara %10 zam yap ve '₺' işaretini sayının sonuna koy.",
  "'Bahar' kelimesini 'Yaz' ile değiştir ve tutarlılığı kontrol et.",
];
let claudeDraft = "";
async function claudeTab(slug, el) {
  const [{ tasks }, status] = await Promise.all([api(`/api/documents/${slug}/ai`), api("/api/status")]);
  el.innerHTML = `
    <div class="card">
      <b>Claude Code'a talimat ver</b>
      <div class="help">Claude belgeyi okur, metni düzenler ve değişiklikleri yeni bir sürüm olarak kaydeder. Beğenmezseniz Geçmiş sekmesinden geri dönebilirsiniz.</div>
      ${status.claude ? "" : `<p style="color:var(--err)">Sunucuda Claude Code kurulu değil. README'deki kurulum adımlarına bakın.</p>`}
      <textarea id="instr" rows="3" placeholder="Örn: ${esc(EXAMPLES[0])}" style="margin-top:10px"></textarea>
      <div class="row" style="margin-top:8px">${EXAMPLES.map(x => `<button class="ghost small" data-ex="${esc(x)}">${esc(x.slice(0, 34))}…</button>`).join("")}<span class="spacer"></span><button id="run" ${status.claude ? "" : "disabled"}>Çalıştır</button></div>
    </div>
    <h2>Görevler</h2>
    ${tasks.length ? `<ul class="list">${tasks.map(t => `<li style="display:block">${badge(t.status)} <b>${esc(t.instruction)}</b>
      <span class="muted small">${esc(t.author || "")} · ${when(t.created)}${t.commit ? " · sürüm <code>" + t.commit.slice(0, 8) + "</code>" : ""}${t.cost_usd ? " · $" + t.cost_usd.toFixed(3) : ""}</span>
      ${t.result ? `<div class="result">${esc(t.result)}</div>` : ""}${t.error ? `<div class="result" style="color:var(--err)">${esc(t.error)}</div>` : ""}</li>`).join("")}</ul>` : `<p class="muted">Henüz görev yok.</p>`}`;
  $("#instr").value = claudeDraft;
  $("#instr").oninput = e => { claudeDraft = e.target.value; };
  el.querySelectorAll("[data-ex]").forEach(b => b.onclick = () => { $("#instr").value = claudeDraft = b.dataset.ex; $("#instr").focus(); });
  $("#run").onclick = async () => {
    const instruction = $("#instr").value.trim(); if (!instruction) return;
    try { await api(`/api/documents/${slug}/ai`, { method: "POST", json: { instruction } }); claudeDraft = ""; toast("Claude çalışıyor…"); route(); }
    catch (e) { toast(e.message, true); }
  };
  if (tasks.some(t => t.status === "running")) { const t = setTimeout(route, 4000); cleanup = () => clearTimeout(t); }
}

refreshStatus(); setInterval(refreshStatus, 30000);
route();
