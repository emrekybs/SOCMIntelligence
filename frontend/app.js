/* SOCMIntelligence — uygulama: durum, yönlendirme, görünümler. */
(function () {
  'use strict';
  const { PLATFORMS, ORDER, GROUPS, resolvePivots } = window.SOC;
  const { esc, fmt, nf } = Charts;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const svgI = p => `<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8">${p}</svg>`;
  const IC = {
    grid: svgI('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
    graph: svgI('<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7.2 7.2l3.6 8.6M16.8 7.2l-3.6 8.6M7.5 6h9"/>'),
    time: svgI('<path d="M3 12h18M7 8v8M12 5v14M17 9v6"/>'),
    match: svgI('<circle cx="8" cy="9" r="3.5"/><circle cx="16" cy="9" r="3.5"/><path d="M3 20c.8-3 3-4.5 5-4.5s3.2.8 4 2c.8-1.2 2-2 4-2s4.2 1.5 5 4.5"/>'),
    compare: svgI('<path d="M12 3v18M6 8H3v9h3zM6 8l-1.5-2M18 6h3v11h-3zM18 6l1.5-2"/>'),
    folder: svgI('<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>'),
    eye: svgI('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
    gear: svgI('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>'),
    dl: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M12 3v12M7 10l5 5 5-5M4 21h16"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>',
    open: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
  };
  const STATUS = {
    running: ['run', t('Çalışıyor')], ok: ['ok', t('Başarılı')], not_found: ['nf', t('Bulunamadı')], private: ['err', t('Gizli / erişim yok')],
    rate_limited: ['err', t('Hız sınırı')], error: ['err', t('Hata')],
  };
  const safe = v => String(v || '').replace(/[^\w.-]+/g, '_').slice(0, 60);

  // ───────────────── Durum ─────────────────
  const STORE_KEY = 'socmint.session.v1';
  const S = { scans: [], sel: {}, tab: {}, status: {}, graphIncl: null, activeCase: null, ann: {}, manual: { nodes: [], edges: [] },
    pairs: {}, avatars: {}, showMatches: true, tlIncl: null, tlRange: 'all' };
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null') || {};
    ['scans', 'activeCase', 'ann', 'manual', 'pairs', 'avatars'].forEach(k => { if (saved[k]) S[k] = saved[k]; });
  } catch (e) { /* depolama yok */ }
  let saveT;
  function save() {
    clearTimeout(saveT);
    saveT = setTimeout(() => {
      try { localStorage.setItem(STORE_KEY, JSON.stringify({ scans: S.scans, activeCase: S.activeCase, ann: S.ann, manual: S.manual, pairs: S.pairs, avatars: S.avatars })); } catch (e) { /* kota */ }
    }, 300);
  }
  let syncT;
  function syncCase() {
    if (!S.activeCase) return;
    clearTimeout(syncT);
    syncT = setTimeout(async () => {
      const scans = S.scans.filter(s => s.status === 'ok').map(s => ({ ...s, jobId: null }));
      try {
        await api('/api/cases/' + encodeURIComponent(S.activeCase.case_id), { method: 'PATCH', body: JSON.stringify({
          scan_results: { scans, ann: S.ann, manual: S.manual, pairs: S.pairs }, graph: mergedGraph(scans),
          platforms: [...new Set(scans.map(s => s.platform))],
          scan_history: S.scans.map(s => ({ platform: s.platform, input: s.raw, status: s.status, at: new Date(s.at).toISOString() })) }) });
      } catch (e) { toast(t('Vaka kaydedilemedi: {err}', { err: I18N.err(e.message) }), 'err'); }
    }, 800);
  }
  const persist = () => { save(); syncCase(); };
  const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  const scanLabel = s => `${PLATFORMS[s.platform].name}: ${s.value || s.raw}`;

  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}, ...opts });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j); } catch (e) { /* */ }
      throw new Error(msg);
    }
    return r.headers.get('content-type')?.includes('json') ? r.json() : r;
  }
  function toast(msg, kind = '') {
    const box = $('#toasts'); const tel = document.createElement('div');
    tel.className = 'toast ' + kind; tel.textContent = msg; box.appendChild(tel);
    setTimeout(() => tel.remove(), 3800);
  }
  function download(name, data, type = 'application/json') {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], { type }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }
  // Basit form penceresi
  function dialog(title, bodyHtml, onOk, okText = t('Kaydet')) {
    const d = document.createElement('div');
    d.className = 'dlg-back';
    d.innerHTML = `<div class="dlg"><div class="card-h"><h3>${esc(title)}</h3></div><div class="card-b dlg-b">${bodyHtml}</div>
      <div class="dlg-f"><button class="btn sm ghost" data-x>${esc(t('İptal'))}</button><button class="btn sm primary" data-ok>${esc(okText)}</button></div></div>`;
    document.body.appendChild(d);
    const close = () => d.remove();
    d.querySelector('[data-x]').onclick = close;
    d.onclick = e => { if (e.target === d) close(); };
    d.querySelector('[data-ok]').onclick = async () => { if ((await onOk(d)) !== false) close(); };
    setTimeout(() => d.querySelector('input,select,textarea')?.focus(), 20);
    return d;
  }

  // ───────────────── Tarama ─────────────────
  async function startScan(platform, raws, opts = {}) {
    const P = PLATFORMS[platform];
    raws = raws.map(r => r.trim()).filter(Boolean);
    if (!raws.length) { toast(t('Hedef girin'), 'err'); return; }
    let targets;
    if (P.compare && opts.compare && raws.length > 1) targets = [{ raw: raws[0], compare_with: raws.slice(1, 5) }];
    else {
      targets = raws.slice(0, P.max).map(raw => ({ raw }));
      if (raws.length > P.max) toast(t('{p} için en fazla {n} hedef; fazlası atlandı', { p: P.name, n: P.max }));
    }
    if (P.videoOpt && opts.videos) targets.forEach(tg => { tg.video_count = opts.videos; });
    let job;
    try { job = await api(`/api/socmint/${platform}/scan`, { method: 'POST', body: JSON.stringify({ targets }) }); }
    catch (e) { toast(`${P.name}: ${I18N.err(e.message)}`, 'err'); return; }
    const created = targets.map((tg, i) => ({
      id: uid(), platform, raw: tg.compare_with ? [tg.raw, ...tg.compare_with].join(' ') : tg.raw, value: tg.raw,
      status: 'running', jobId: job.job_id, idx: i, at: Date.now(), opts: { compare: !!tg.compare_with, videos: tg.video_count },
    }));
    S.scans.push(...created);
    if (!opts.background) S.sel[platform] = created[0].id;
    save(); poll(job.job_id); render({ keepGraph: true });
  }

  const polling = new Set();
  async function poll(jobId) {
    if (polling.has(jobId)) return; polling.add(jobId);
    try {
      for (;;) {
        let j;
        try { j = await api(`/api/socmint/jobs/${jobId}`); } catch (e) {
          S.scans.filter(s => s.jobId === jobId && s.status === 'running').forEach(s => { s.status = 'error'; s.error = t('İş bulunamadı (sunucu yeniden başlatılmış olabilir). Tekrar tarayın.'); });
          break;
        }
        let changed = false;
        S.scans.filter(s => s.jobId === jobId).forEach(s => {
          const r = j.results[s.idx];
          if (r && s.status === 'running') {
            Object.assign(s, { status: r.status, value: r.value, type: r.type, data: r.data, graph: r.graph, error: r.error, duration: r.duration_ms, evidence: r.evidence });
            changed = true;
            toast(r.status === 'ok' ? t('{target} tamamlandı', { target: scanLabel(s) }) : `${scanLabel(s)}: ${STATUS[r.status]?.[1] || r.status}`, r.status === 'ok' ? 'ok' : 'err');
          }
        });
        if (j.status === 'failure') {
          S.scans.filter(s => s.jobId === jobId && s.status === 'running').forEach(s => { s.status = 'error'; s.error = j.error || t('İş başarısız'); });
          changed = true;
        }
        if (changed) {
          persist();
          const rt = route(), plat = S.scans.find(s => s.jobId === jobId)?.platform;
          if ((rt.view === 'module' && rt.platform !== plat) || ['settings', 'watch', 'case', 'cases'].includes(rt.view)) renderNav(); else render({ keepGraph: true });
        }
        if (j.status === 'success' || j.status === 'failure') break;
        await new Promise(r => setTimeout(r, 1500));
      }
    } finally { polling.delete(jobId); save(); renderNav(); }
  }

  // ───────────────── Birleşik grafik + eşleşmeler ─────────────────
  const okScans = () => S.scans.filter(s => s.status === 'ok' && s.graph);
  const pairKey = (a, b) => [a.id, b.id].sort().join('|');
  function matchPairs(scans) {
    const out = [];
    for (let i = 0; i < scans.length; i++) for (let j = i + 1; j < scans.length; j++) {
      const A = scans[i], B = scans[j];
      const r = Signals.score(A, B, S.avatars);
      out.push({ A, B, key: pairKey(A, B), ...r, decision: S.pairs[pairKey(A, B)] || null });
    }
    return out.sort((a, b) => b.score - a.score);
  }
  function mergedGraph(scans, opts = {}) {
    const nodes = new Map(), edges = new Map();
    scans.forEach(s => {
      const g = s.graph; if (!g) return; const lbl = scanLabel(s);
      (g.nodes || []).forEach(n => {
        const cur = nodes.get(n.id);
        if (cur) {
          Object.entries(n.meta || {}).forEach(([k, v]) => { if (!(k in cur.meta)) cur.meta[k] = v; });
          if (!cur.sources.includes(lbl)) cur.sources.push(lbl);
        } else nodes.set(n.id, { ...n, meta: { ...(n.meta || {}) }, sources: [lbl] });
      });
      (g.edges || []).forEach(e => {
        const k = `${e.source}|${e.target}|${e.type}`;
        const cur = edges.get(k);
        if (cur) { if (e.weight != null) cur.weight = Math.max(cur.weight || 0, e.weight); } else edges.set(k, { ...e, id: k });
      });
    });
    if (opts.manual !== false) {
      (S.manual.nodes || []).forEach(n => { if (!nodes.has(n.id)) nodes.set(n.id, { ...n, sources: [t('Analist')] }); });
      (S.manual.edges || []).forEach(e => { if (nodes.has(e.source) && nodes.has(e.target)) edges.set(e.id, { ...e }); });
    }
    if (opts.matches && scans.length > 1) {
      matchPairs(scans).forEach(p => {
        if (p.decision === 'rejected') return;
        if (p.decision !== 'confirmed' && p.score < 40) return;
        const a = Signals.personOf(p.A), b = Signals.personOf(p.B);
        if (!a || !b || a.id === b.id) return;
        const id = `sp|${p.key}`;
        edges.set(id, { id, source: a.id, target: b.id, type: 'same_person', weight: p.decision === 'confirmed' ? 100 : p.score });
      });
    }
    return { nodes: [...nodes.values()], edges: [...edges.values()] };
  }
  const annFns = () => ({
    getAnn: id => S.ann[id],
    onAnnotate: (id, patch) => {
      const cur = { ...(S.ann[id] || {}), ...patch };
      if (!cur.status) delete cur.status;
      if (!cur.note) delete cur.note;
      if (Object.keys(cur).length) S.ann[id] = cur; else delete S.ann[id];
      persist();
    },
  });

  // ───────────────── Kabuk ─────────────────
  const VIEWS = ['overview', 'graph', 'timeline', 'match', 'compare', 'cases', 'watch', 'settings'];
  function route() {
    const h = location.hash.replace(/^#\/?/, '') || 'overview';
    const [a, b] = h.split('/');
    if (a === 'm' && PLATFORMS[b]) return { view: 'module', platform: b };
    if (a === 'case' && b) return { view: 'case', id: decodeURIComponent(b) };
    if (VIEWS.includes(a)) return { view: a };
    return { view: 'overview' };
  }

  function renderNav() {
    const r = route();
    const count = p => S.scans.filter(s => s.platform === p).length;
    const running = p => S.scans.some(s => s.platform === p && s.status === 'running');
    const item = (href, icon, label, active, right = '') => `<a class="nav-item ${active ? 'active' : ''}" href="#/${href}">${icon}<span>${label}</span>${right}</a>`;
    const cnt = n => `<span class="count">${n || ''}</span>`;
    $('#nav').innerHTML = `
      ${item('overview', IC.grid, esc(t('Genel bakış')), r.view === 'overview', cnt(S.scans.length))}
      ${item('graph', IC.graph, esc(t('İlişki grafiği')), r.view === 'graph', cnt(okScans().length))}
      ${item('timeline', IC.time, esc(t('Zaman çizelgesi')), r.view === 'timeline')}
      ${item('match', IC.match, esc(t('Kimlik eşleştirme')), r.view === 'match')}
      ${item('compare', IC.compare, esc(t('Karşılaştırma')), r.view === 'compare')}
      ${item('cases', IC.folder, esc(t('Vakalar')), r.view === 'cases' || r.view === 'case')}
      ${item('watch', IC.eye, esc(t('İzleme')), r.view === 'watch')}
      ${GROUPS.map(([title, ps]) => `<div class="nav-group">${title}</div>` + ps.map(p => item('m/' + p, picon(p), PLATFORMS[p].name, r.view === 'module' && r.platform === p,
        running(p) ? `<span class="run-dot" title="${esc(t('Tarama sürüyor'))}"></span>` : cnt(count(p)))).join('')).join('')}`;
    $('#nav-foot').innerHTML = item('settings', IC.gear, esc(t('Ayarlar')), r.view === 'settings',
      `<span class="lang-sw">${Object.keys(I18N.LANGS).map(k => `<button data-lang="${k}" class="${I18N.lang === k ? 'on' : ''}" title="${esc(I18N.LANGS[k].name)}">${k.toUpperCase()}</button>`).join('')}</span>`);
    $$('#nav-foot [data-lang]').forEach(b => b.onclick = e => { e.preventDefault(); e.stopPropagation(); I18N.set(b.dataset.lang); });
  }

  let activeGraph = null, scanGraph = null;
  function render(o = {}) {
    Charts.hideTip();
    renderNav();
    const r = route();
    const view = $('#view');
    if (o.keepGraph && r.view === 'graph' && activeGraph) { refreshMerged(); return; }
    if (activeGraph) { activeGraph.destroy(); activeGraph = null; }
    if (scanGraph && !(o.keepGraph && r.view === 'module')) { scanGraph.destroy(); scanGraph = null; }
    view.className = 'view' + (r.view === 'graph' ? ' full' : '');
    const ac = S.activeCase;
    $('#top-actions').innerHTML = `
      <a class="btn sm" href="${ac ? '#/case/' + encodeURIComponent(ac.case_id) : '#/cases'}" title="${esc(ac ? t('Aktif vaka — taramalar buraya kaydediliyor') : t('Vaka seçilmedi'))}">${IC.folder}${ac ? `<span class="mono">${esc(ac.case_id)}</span> ${esc(ac.title)}` : esc(t('Vaka seçilmedi'))}</a>
      <button class="btn sm" id="btn-report">${IC.dl}${esc(t('Dışa aktar'))}</button>
      <button class="btn sm ghost danger" id="btn-clear">${IC.trash}${esc(t('Oturumu temizle'))}</button>`;
    $('#btn-report').onclick = e => { e.stopPropagation(); exportMenu(e.currentTarget); };
    $('#btn-clear').onclick = () => {
      if (!S.scans.length && !S.activeCase) return;
      if (!confirm(t('Oturumdaki taramalar ve analist işaretleri temizlensin mi? Aktif vaka kapatılır; kayıtlı vakalar silinmez.'))) return;
      Object.assign(S, { activeCase: null, scans: [], sel: {}, ann: {}, manual: { nodes: [], edges: [] }, pairs: {} }); save(); render();
    };
    ({ overview: viewOverview, graph: viewGraph, timeline: viewTimeline, match: viewMatch, compare: viewCompare, cases: viewCases, watch: viewWatch, settings: viewSettings }[r.view]
      || (r.view === 'case' ? v => viewCase(v, r.id) : v => viewModule(v, r.platform)))(view);
  }
  function setTitle(ttl, crumb = '') { $('#title').textContent = ttl; $('#crumb').textContent = crumb; document.title = `${ttl} · SOCMIntelligence`; }

  // ───────────────── Dışa aktarma menüsü ─────────────────
  let menuEl;
  function exportMenu(anchor) {
    if (!menuEl) { menuEl = document.createElement('div'); menuEl.className = 'gctx'; document.body.appendChild(menuEl); document.addEventListener('click', () => { menuEl.style.display = 'none'; }); }
    menuEl.innerHTML = `<div class="muted" style="cursor:default;font-size:11px">${esc(S.activeCase ? t('Aktif vaka: {id}', { id: S.activeCase.case_id }) : t('Mevcut oturum'))}</div><hr>
      <div data-r="html">${esc(t('HTML rapor'))}</div><div data-r="pdf">${esc(t('PDF rapor'))}</div><div data-r="xlsx">Excel (.xlsx)</div><hr>
      <div data-r="graphml">GraphML (Gephi, yEd)</div><div data-r="gexf">GEXF (Gephi)</div><div data-r="maltego">Maltego CSV</div><hr>
      <div data-r="json">${esc(t('JSON (ham veri)'))}</div>`;
    const r = anchor.getBoundingClientRect();
    menuEl.style.display = 'block'; menuEl.style.left = Math.min(r.left, innerWidth - 240) + 'px'; menuEl.style.top = (r.bottom + 4) + 'px';
    menuEl.querySelectorAll('[data-r]').forEach(el => el.onclick = async ev => {
      ev.stopPropagation(); menuEl.style.display = 'none';
      const k = el.dataset.r;
      if (k === 'json') return exportJson();
      const ok = S.scans.filter(s => s.status === 'ok');
      if (!ok.length) { toast(t('Dışa aktarılacak başarılı tarama yok'), 'err'); return; }
      const g = mergedGraph(ok, { matches: true });
      const name = S.activeCase ? S.activeCase.case_id : `socmintelligence_${new Date().toISOString().slice(0, 10)}`;
      if (k === 'graphml') return Exporter.graphml(g, S.ann, name);
      if (k === 'gexf') return Exporter.gexf(g, S.ann, name);
      if (k === 'maltego') return Exporter.maltego(g, name);
      if (k === 'xlsx') {
        try { await Exporter.xlsx({ title: name, scans: ok.map(s => ({ platform: s.platform, raw: s.raw, value: s.value, status: s.status, at: s.at, data: s.data, evidence: s.evidence })), graph: g, annotations: S.ann }, name); }
        catch (e) { toast(I18N.err(e.message), 'err'); }
        return;
      }
      let caseInfo = null, notes = '';
      if (S.activeCase) { try { caseInfo = await api('/api/cases/' + encodeURIComponent(S.activeCase.case_id)); notes = caseInfo.notes || ''; } catch (e) { /* oturumla devam */ } }
      Report[k](reportOpts(caseInfo, notes, S.scans));
    });
  }
  const reportOpts = (caseInfo, notes, scans) => ({ caseInfo, notes, scans, ann: S.ann, manual: S.manual,
    matches: matchPairs(scans.filter(s => s.status === 'ok' && s.graph)).filter(p => p.decision === 'confirmed' || (p.decision !== 'rejected' && p.score >= 40)) });
  function exportJson() {
    const ok = S.scans.filter(s => s.status === 'ok');
    download(`socmintelligence_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`, JSON.stringify({
      tool: 'SOCMIntelligence', case: S.activeCase, generated_at: new Date().toISOString(), annotations: S.ann, manual: S.manual,
      scans: S.scans.map(s => ({ platform: s.platform, input: s.raw, value: s.value, type: s.type, status: s.status, error: s.error, scanned_at: new Date(s.at).toISOString(), evidence: s.evidence, data: s.data })),
      merged_graph: mergedGraph(ok, { matches: true }),
    }, null, 2));
  }

  // ───────────────── Genel bakış ─────────────────
  function viewOverview(v) {
    setTitle(t('Genel bakış'));
    const ok = okScans();
    const mg = mergedGraph(ok);
    const matches = mg.nodes.filter(n => n.sources.length > 1).sort((a, b) => b.sources.length - a.sources.length);
    const strong = ok.length > 1 ? matchPairs(ok).filter(p => p.score >= 40 && p.decision !== 'rejected') : [];
    const kstat = (k, val, s = '') => `<div class="kpi"><div class="k">${k}</div><div class="v">${val}</div><div class="s">${s}</div></div>`;
    v.innerHTML = `
      <div class="kpis">
        ${kstat(esc(t('Tarama')), fmt(S.scans.length), esc(t('{n} başarılı', { n: fmt(ok.length) })))}
        ${kstat(esc(t('Platform')), fmt(new Set(ok.map(s => s.platform)).size))}
        ${kstat(esc(t('Varlık')), fmt(mg.nodes.length), esc(t('{n} ilişki', { n: fmt(mg.edges.length) })))}
        ${kstat(esc(t('Ortak varlık')), fmt(matches.length))}
        ${kstat(esc(t('Olası aynı kişi')), fmt(strong.length), esc(t('skor ≥ 40')))}
        ${kstat(esc(t('İşaretli düğüm')), fmt(Object.keys(S.ann).length))}
      </div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card"><div class="card-h"><h3>${esc(t('Ortak varlıklar'))}</h3><span class="sub">${esc(t('birden çok taramada görülen'))}</span></div>
          <div class="card-b" style="padding:0 4px">${matches.length ? `<table class="t"><tr><th>${esc(t('Varlık'))}</th><th>${esc(t('Tür'))}</th><th>${esc(t('Taramalar'))}</th></tr>
            ${matches.slice(0, 20).map(n => `<tr style="cursor:pointer" data-node="${esc(n.id)}"><td>${esc(n.label)}</td><td class="dim">${esc((GraphMeta.NODE[n.type] || {}).label || n.type)}</td><td class="dim">${n.sources.map(esc).join('<br>')}</td></tr>`).join('')}</table>`
            : `<div class="empty">${esc(t('Henüz yok'))}</div>`}</div></div>
        <div class="card"><div class="card-h"><h3>${esc(t('Son taramalar'))}</h3></div>
          <div class="card-b" style="padding:0 4px">${S.scans.length ? `<table class="t"><tr><th></th><th>${esc(t('Hedef'))}</th><th>${esc(t('Durum'))}</th><th class="num">${esc(t('Süre'))}</th><th>${esc(t('Saat'))}</th></tr>
            ${[...S.scans].reverse().slice(0, 14).map(s => `<tr style="cursor:pointer" data-scan="${s.id}"><td>${picon(s.platform)}</td><td class="mono ell" title="${esc(s.raw)}">${esc(s.raw)}</td><td class="nw">${STATUS[s.status][1]}</td><td class="num nw">${s.duration ? esc(t('{n} sn', { n: (s.duration / 1000).toFixed(1) })) : '—'}</td><td class="dim nw">${new Date(s.at).toLocaleTimeString(I18N.locale, { hour: '2-digit', minute: '2-digit' })}</td></tr>`).join('')}</table>`
            : `<div class="empty">${esc(t('Soldan bir modül seçip tarama başlatın'))}</div>`}</div></div>
      </div>
      <div class="card plist" style="margin-top:14px">
        <div class="row hd"><span></span><span>${esc(t('Modül'))}</span><span>${esc(t('Tarama'))}</span><span>${esc(t('Son durum'))}</span><span>${esc(t('Son hedef'))}</span></div>
        ${ORDER.map(p => {
          const ss = S.scans.filter(s => s.platform === p); const last = ss[ss.length - 1];
          return `<div class="row" data-go="#/m/${p}">${picon(p)}<span>${PLATFORMS[p].name}</span><span class="mono">${ss.length || '—'}</span>
            <span>${last ? `<span class="badge"><span class="st ${STATUS[last.status][0]}"></span>${STATUS[last.status][1]}</span>` : '<span class="muted">—</span>'}</span>
            <span class="mono dim">${last ? esc(last.raw) : ''}</span></div>`;
        }).join('')}
      </div>`;
    $$('[data-go]', v).forEach(el => el.onclick = () => { location.hash = el.dataset.go; });
    $$('[data-scan]', v).forEach(el => el.onclick = () => { const s = S.scans.find(x => x.id === el.dataset.scan); if (s) { S.sel[s.platform] = s.id; location.hash = '#/m/' + s.platform; } });
    $$('[data-node]', v).forEach(el => el.onclick = () => { S.focusNode = el.dataset.node; location.hash = '#/graph'; });
  }

  // ───────────────── Birleşik grafik ─────────────────
  function viewGraph(v) {
    setTitle(t('İlişki grafiği'), t('tüm başarılı taramalar'));
    const ok = okScans();
    if (!S.graphIncl) S.graphIncl = new Set();
    v.innerHTML = `<div style="display:flex;flex-direction:column;flex:1;min-width:0">
      <div class="gbar" style="border-bottom:1px solid var(--border)">
        <div class="chips" id="incl">${ok.length ? ok.map(s => `<label class="chip" style="gap:6px"><input type="checkbox" data-id="${s.id}" ${S.graphIncl.has(s.id) ? '' : 'checked'}>${picon(s.platform)} ${esc(s.value || s.raw)}</label>`).join('') : `<span class="muted">${esc(t('Henüz başarılı tarama yok'))}</span>`}</div></div>
      <div id="gholder" style="flex:1;min-height:0;display:flex"></div></div>`;
    activeGraph = new GraphView($('#gholder', v), {
      resolvePivots, onPivot: pivot, toast, filename: t('socmintelligence_iliski_grafigi'), pngTitle: 'SOCMIntelligence · ' + t('İlişki grafiği'),
      emptyText: t('Başarılı tarama olduğunda kimlikler, e-postalar, alan adları ve etkileşimler burada birleşir.'),
      ...annFns(), onAddEdge: n => addEdgeDialog(n), onDeleteManual: n => {
        S.manual.nodes = S.manual.nodes.filter(x => x.id !== n.id);
        S.manual.edges = S.manual.edges.filter(e => e.source !== n.id && e.target !== n.id);
        persist(); activeGraph.closePanel(); refreshMerged();
      },
    });
    const gw = $('#gholder .gwrap'); gw.style.height = '100%'; gw.style.flex = '1';
    activeGraph.$('extra').innerHTML = `<label class="btn sm" title="${esc(t('Aynı kişi olabilecek hesaplar arasında bağ'))}"><input type="checkbox" id="showm" ${S.showMatches ? 'checked' : ''}> ${esc(t('Eşleşme bağları'))}</label>
      <button class="btn sm" id="addn">${esc(t('Düğüm ekle'))}</button>`;
    $('#showm', v).onchange = e => { S.showMatches = e.target.checked; refreshMerged(); };
    $('#addn', v).onclick = () => addNodeDialog();
    $$('#incl input', v).forEach(cb => cb.onchange = () => { cb.checked ? S.graphIncl.delete(cb.dataset.id) : S.graphIncl.add(cb.dataset.id); refreshMerged(); });
    refreshMerged();
    if (S.focusNode) { const id = S.focusNode; S.focusNode = null; setTimeout(() => { activeGraph?.select(id); activeGraph?.center(id); }, 1300); }
  }
  function refreshMerged() {
    if (!activeGraph) return;
    activeGraph.setData(mergedGraph(okScans().filter(s => !S.graphIncl?.has(s.id)), { matches: S.showMatches }));
  }
  const NTYPES = ['person', 'username', 'email', 'domain', 'community', 'artifact', 'content', 'hashtag'];
  function addNodeDialog() {
    const sel = activeGraph?.selected;
    dialog(t('Düğüm ekle'), `
      <label class="field">${esc(t('Tür'))}<select class="input" name="t">${NTYPES.map(nt => `<option value="${nt}">${esc(GraphMeta.NODE[nt].label)}</option>`).join('')}</select></label>
      <label class="field">${esc(t('Değer'))}<input class="input" name="l" placeholder="${esc(t('ör. ad soyad, e-posta, telefon'))}"></label>
      <label class="field">${esc(t('Not'))}<input class="input" name="n" placeholder="${esc(t('kaynak, bağlam'))}"></label>
      ${sel ? `<label class="field">${esc(t('Seçili düğüme bağla'))}<select class="input" name="r"><option value="">${esc(t('Bağlama'))}</option>${['linked_to', 'owns', 'same_person', 'related', 'manual'].map(et => `<option value="${et}">${esc(GraphMeta.EDGE[et].label)}</option>`).join('')}</select></label>` : ''}`,
      d => {
        const label = d.querySelector('[name=l]').value.trim();
        if (!label) { toast(t('Değer girin'), 'err'); return false; }
        const id = 'm_' + uid();
        S.manual.nodes.push({ id, type: d.querySelector('[name=t]').value, label, manual: true, meta: { Kaynak: t('Analist'), Not: d.querySelector('[name=n]').value.trim() || undefined } });
        const rel = d.querySelector('[name=r]')?.value;
        if (sel && rel) S.manual.edges.push({ id: 'me_' + uid(), source: sel, target: id, type: rel, manual: true });
        persist(); refreshMerged();
      }, t('Ekle'));
  }
  function addEdgeDialog(n) {
    const g = mergedGraph(okScans(), { matches: false });
    const others = g.nodes.filter(x => x.id !== n.id);
    dialog(t('Bağlantı ekle — {label}', { label: n.label }), `
      <label class="field">${esc(t('Hedef düğüm'))}<input class="input" name="q" list="nlist" placeholder="${esc(t('yazmaya başlayın'))}"><datalist id="nlist">${others.map(x => `<option value="${esc(x.label)} · ${esc(x.id)}">`).join('')}</datalist></label>
      <label class="field">${esc(t('İlişki'))}<select class="input" name="r">${['linked_to', 'same_person', 'related', 'owns', 'manual'].map(et => `<option value="${et}">${esc(GraphMeta.EDGE[et].label)}</option>`).join('')}</select></label>`,
      d => {
        const q = d.querySelector('[name=q]').value;
        const id = (q.split(' · ').pop() || '').trim();
        if (!g.nodes.some(x => x.id === id)) { toast(t('Listeden bir düğüm seçin'), 'err'); return false; }
        S.manual.edges.push({ id: 'me_' + uid(), source: n.id, target: id, type: d.querySelector('[name=r]').value, manual: true });
        persist(); refreshMerged();
      }, t('Ekle'));
  }
  function pivot(pv) {
    toast(t('{p} taraması başlatılıyor: {raw}', { p: PLATFORMS[pv.platform].name, raw: pv.raw }));
    location.hash = '#/m/' + pv.platform;
    startScan(pv.platform, [pv.raw], { videos: PLATFORMS[pv.platform].videoOpt?.def });
  }

  // ───────────────── Zaman çizelgesi ─────────────────
  function viewTimeline(v) {
    setTitle(t('Zaman çizelgesi'), 'UTC');
    const ok = okScans();
    if (!S.tlIncl) S.tlIncl = new Set();
    const use = ok.filter(s => !S.tlIncl.has(s.id));
    const rows = use.map(s => ({ s, label: `${PLATFORMS[s.platform].name}: ${s.value}`, events: Signals.events(s), hours: Signals.hours(s) }));
    const now = Date.now(), R = { all: null, y: 365, q: 90, m: 30 }[S.tlRange];
    const from = R ? new Date(now - R * 86400000) : null;
    const hrRows = rows.filter(r => r.hours);
    const pairs = [];
    for (let i = 0; i < hrRows.length; i++) for (let j = i + 1; j < hrRows.length; j++) {
      const c = Signals.cosine(hrRows[i].hours, hrRows[j].hours);
      if (c != null) pairs.push({ a: hrRows[i].label, b: hrRows[j].label, c });
    }
    pairs.sort((a, b) => b.c - a.c);
    const allEv = rows.flatMap(r => r.events.map(e => ({ ...e, who: r.label, platform: r.s.platform }))).filter(e => !from || e.t >= from).sort((a, b) => b.t - a.t);
    v.innerHTML = `
      <div class="toolbar">
        <div class="chips">${ok.map(s => `<label class="chip" style="gap:6px"><input type="checkbox" data-id="${s.id}" ${S.tlIncl.has(s.id) ? '' : 'checked'}>${picon(s.platform)} ${esc(s.value)}</label>`).join('') || `<span class="muted">${esc(t('Başarılı tarama yok'))}</span>`}</div>
        <select class="input" id="rng" style="margin-left:auto;width:140px">${[['all', t('Tümü')], ['y', t('Son 1 yıl')], ['q', t('Son 90 gün')], ['m', t('Son 30 gün')]].map(([k, lb]) => `<option value="${k}" ${S.tlRange === k ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select>
      </div>
      <div class="card"><div class="card-h"><h3>${esc(t('Etkinlikler'))}</h3><span class="sub">${esc(t('gönderi, yorum, yükleme, hesap açılışı · {n} olay', { n: fmt(allEv.length) }))}</span><div class="right"><button class="btn sm" data-png="tl">${IC.dl}PNG</button></div></div>
        <div class="card-b"><div class="chart" id="tl"></div></div></div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card"><div class="card-h"><h3>${esc(t('Saat örtüşmesi'))}</h3><span class="sub">${esc(t('her satırda etkinliğin saatlere dağılımı (%)'))}</span><div class="right"><button class="btn sm" data-png="hm">${IC.dl}PNG</button></div></div>
          <div class="card-b"><div class="chart" id="hm"></div></div></div>
        <div class="card"><div class="card-h"><h3>${esc(t('Saat benzerliği'))}</h3><span class="sub">${esc(t('aynı saatlerde aktif hesaplar'))}</span></div>
          <div class="card-b" style="padding:0 4px">${pairs.length ? `<table class="t"><tr><th>${esc(t('Hesap'))}</th><th>${esc(t('Hesap'))}</th><th class="num">${esc(t('Benzerlik'))}</th></tr>
            ${pairs.slice(0, 15).map(p => `<tr><td>${esc(p.a)}</td><td>${esc(p.b)}</td><td class="num">${esc(t('%{n}', { n: Math.round(p.c * 100) }))}</td></tr>`).join('')}</table>` : `<div class="empty">${esc(t('En az iki hesapta saat verisi gerekli'))}</div>`}</div></div>
      </div>
      <div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Olay listesi'))}</h3><span class="sub">${esc(t('en yeni önce'))}</span></div>
        <div class="card-b" style="padding:0 4px;max-height:420px;overflow:auto">${allEv.length ? `<table class="t"><tr><th>${esc(t('Tarih (UTC)'))}</th><th></th><th>${esc(t('Hesap'))}</th><th>${esc(t('Olay'))}</th></tr>
          ${allEv.slice(0, 400).map(e => `<tr><td class="mono" style="white-space:nowrap">${e.t.toISOString().slice(0, e.dateOnly ? 10 : 16).replace('T', ' ')}</td><td>${picon(e.platform)}</td><td>${esc(e.who)}</td>
            <td>${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.label || '—')}</a>` : esc(e.label || '—')}</td></tr>`).join('')}</table>` : `<div class="empty">${esc(t('Tarihli olay yok'))}</div>`}</div></div>`;
    Charts.render($('#tl', v), { type: 'strip', rows: rows.map(r => ({ label: r.label, events: r.events })), from: from || undefined, to: R ? new Date(now) : undefined });
    const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
    if (hrRows.length) {
      const pct = hrRows.map(r => { const tot = r.hours.reduce((a, b) => a + b, 0); return r.hours.map(x => Math.round(x / tot * 1000) / 10); });
      Charts.render($('#hm', v), { type: 'heatmap', rows: hrRows.map(r => r.label), cols: hours, value: (ri, ci) => pct[ri][ci], unit: '%', labelW: 170, rowH: 20 });
    } else $('#hm', v).innerHTML = `<div class="empty">${esc(t('Saat verisi yok'))}</div>`;
    $$('.toolbar input[data-id]', v).forEach(cb => cb.onchange = () => { cb.checked ? S.tlIncl.delete(cb.dataset.id) : S.tlIncl.add(cb.dataset.id); render(); });
    $('#rng', v).onchange = e => { S.tlRange = e.target.value; render(); };
    $$('[data-png]', v).forEach(b => b.onclick = () => { const svg = $(`#${b.dataset.png} svg`, v); if (svg) Charts.svgToPng(svg, t('zaman_cizelgesi_{id}.png', { id: b.dataset.png }), { title: b.dataset.png === 'tl' ? t('Etkinlik zaman çizelgesi (UTC)') : t('Saat örtüşmesi (UTC)') }); });
  }

  // ───────────────── Kimlik eşleştirme ─────────────────
  const avTried = new Set();
  const needAvatar = u => u && /^https?:/.test(u) && !S.avatars[u] && !avTried.has(u);
  async function ensureAvatars(scans, onProgress) {
    const urls = [...new Set(scans.map(s => Signals.identity(s).avatar).filter(needAvatar))];
    urls.forEach(u => avTried.add(u));
    let done = 0;
    const worker = async () => {
      while (urls.length) {
        const u = urls.shift();
        try { const r = await api('/api/socmint/avatar-hash?url=' + encodeURIComponent(u)); if (r.phash) S.avatars[u] = r; } catch (e) { /* ağ hatası */ }
        onProgress?.(++done);
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    save();
  }
  function viewMatch(v) {
    setTitle(t('Kimlik eşleştirme'));
    const ok = okScans();
    const draw = () => {
      const all = ok.length > 1 ? matchPairs(ok) : [];
      const min = +(S.matchMin ?? 20);
      const list = all.filter(p => p.score >= min || p.decision);
      v.innerHTML = `
        <div class="toolbar"><span class="muted" id="avst"></span>
          <select class="input" id="min" style="margin-left:auto;width:170px">${[[20, t('Skor ≥ 20')], [40, t('Skor ≥ 40')], [70, t('Skor ≥ 70')], [0, t('Tüm çiftler')]].map(([k, lb]) => `<option value="${k}" ${min === k ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select></div>
        <div class="card"><div class="card-b" style="padding:0 4px">${list.length ? `<table class="t"><tr><th>${esc(t('Hesap'))}</th><th>${esc(t('Hesap'))}</th><th style="width:160px">${esc(t('Skor'))}</th><th>${esc(t('Gerekçe'))}</th><th></th></tr>
          ${list.map(p => { const [lv, cls] = Signals.level(p.decision === 'confirmed' ? 100 : p.score);
            return `<tr><td>${picon(p.A.platform)} ${esc(p.A.value)}</td><td>${picon(p.B.platform)} ${esc(p.B.value)}</td>
              <td><div class="meter"><i style="width:${p.score}%"></i></div><span class="mono">${p.score}</span> <span class="badge ${cls}">${esc(p.decision === 'confirmed' ? t('Onaylandı') : p.decision === 'rejected' ? t('Reddedildi') : lv)}</span></td>
              <td class="dim">${p.reasons.map(r => `<div>+${r.pts} ${esc(r.txt)}</div>`).join('') || '—'}</td>
              <td style="white-space:nowrap"><button class="btn sm" data-dec="confirmed" data-k="${p.key}">${esc(t('Onayla'))}</button> <button class="btn sm ghost" data-dec="rejected" data-k="${p.key}">${esc(t('Reddet'))}</button>
                ${p.decision ? `<button class="btn sm ghost" data-dec="" data-k="${p.key}">${esc(t('Sıfırla'))}</button>` : ''}</td></tr>`; }).join('')}</table>`
          : `<div class="empty">${esc(ok.length < 2 ? t('En az iki başarılı tarama gerekli') : t('Bu eşiğin üstünde eşleşme yok'))}</div>`}</div></div>
        <div class="chart-note">${esc(t('Sinyaller: doğrudan / kanıtlı hesap bağlantısı, ortak e-posta, kullanıcı adı ve görünen ad benzerliği, ortak kişisel alan adı, avatar pHash benzerliği, etkinlik saatleri. Skor ≥ 40 olan çiftler ilişki grafiğinde “aynı kişi olabilir” bağıyla gösterilir.'))}</div>`;
      $('#min', v).onchange = e => { S.matchMin = +e.target.value; draw(); };
      $$('[data-dec]', v).forEach(b => b.onclick = () => { if (b.dataset.dec) S.pairs[b.dataset.k] = b.dataset.dec; else delete S.pairs[b.dataset.k]; persist(); draw(); });
    };
    draw();
    const need = [...new Set(ok.map(s => Signals.identity(s).avatar).filter(needAvatar))];
    if (need.length) {
      $('#avst', v).textContent = t('Avatarlar karşılaştırılıyor… {done}/{total}', { done: 0, total: need.length });
      ensureAvatars(ok, n => { const el = $('#avst', v); if (el) el.textContent = t('Avatarlar karşılaştırılıyor… {done}/{total}', { done: n, total: need.length }); })
        .then(() => { if (route().view === 'match') draw(); });
    }
  }

  // ───────────────── Karşılaştırma ─────────────────
  // Arayüzde biçimlenmiş sayıyı (12,3 B / 12.3k / 1,2 Mn) tekrar sayıya çevirir.
  function pnum(v) {
    if (typeof v === 'number') return v;
    if (v == null) return null;
    const s = String(v).replace(/\s+/g, '');
    const m = s.match(/^(-?[0-9.,]+)(bn|mr|mn|bin|b|k|m)?$/i);
    if (!m) return null;
    let num = m[1]; const suf = (m[2] || '').toLowerCase();
    if (suf) num = I18N.lang === 'tr' ? num.replace(/\./g, '').replace(',', '.') : num.replace(/,/g, '');
    else num = num.replace(/[.,]/g, '');
    const n = parseFloat(num);
    if (isNaN(n)) return null;
    return n * ({ k: 1e3, b: 1e3, bin: 1e3, m: 1e6, mn: 1e6, bn: 1e9, mr: 1e9 }[suf] || 1);
  }
  function viewCompare(v) {
    setTitle(t('Karşılaştırma'));
    const byPlat = {};
    okScans().forEach(s => { (byPlat[s.platform] = byPlat[s.platform] || []).push(s); });
    const plats = ORDER.filter(p => (byPlat[p] || []).length >= 2);
    if (!plats.length) { v.innerHTML = `<div class="empty" style="padding:60px 0">${esc(t('Karşılaştırma için aynı modülde en az iki başarılı tarama gerekli.'))}</div>`; return; }
    if (!plats.includes(S.cmpPlatform)) { S.cmpPlatform = plats[0]; S.cmpPick = null; S.cmpMetric = null; }
    const P = PLATFORMS[S.cmpPlatform];
    const list = byPlat[S.cmpPlatform];
    if (!S.cmpPick || !S.cmpPick.some(id => list.some(s => s.id === id))) S.cmpPick = list.slice(0, 6).map(s => s.id);
    const chosen = list.filter(s => S.cmpPick.includes(s.id)).slice(0, 6);
    const kpiByScan = chosen.map(s => ({ s, k: (P.kpis(s.data) || []).filter(Boolean) }));
    const labels = []; kpiByScan.forEach(x => x.k.forEach(k => { if (!labels.includes(k.k)) labels.push(k.k); }));
    const cell = (x, lb) => x.k.find(k => k.k === lb) || null;
    const numericLabels = labels.filter(lb => kpiByScan.some(x => { const c = cell(x, lb); return c && pnum(c.v) != null; }));
    if (!numericLabels.includes(S.cmpMetric)) S.cmpMetric = numericLabels[0] || null;
    v.innerHTML = `
      <div class="toolbar">
        <label class="field" style="flex-direction:row;align-items:center;gap:8px">${esc(t('Modül'))}
          <select class="input" id="cp" style="height:30px;width:auto">${plats.map(p => `<option value="${p}" ${p === S.cmpPlatform ? 'selected' : ''}>${esc(PLATFORMS[p].name)}</option>`).join('')}</select></label>
        <div class="chips">${list.map(s => `<label class="chip" style="gap:6px"><input type="checkbox" data-id="${s.id}" ${S.cmpPick.includes(s.id) ? 'checked' : ''}>${picon(s.platform)} ${esc(s.value || s.raw)}</label>`).join('')}</div>
      </div>
      ${chosen.length < 2 ? `<div class="notice">${esc(t('Karşılaştırmak için en az iki hesap seçin.'))}</div>` : ''}
      <div class="card"><div class="card-b" style="padding:0 4px;overflow:auto">
        <table class="t cmp"><tr><th>${esc(t('Ölçüt'))}</th>${kpiByScan.map(x => `<th class="nw">${picon(x.s.platform)} <span class="mono">${esc(x.s.value || x.s.raw)}</span></th>`).join('')}</tr>
        ${labels.map(lb => {
          const vals = kpiByScan.map(x => { const c = cell(x, lb); return { c, n: c ? pnum(c.v) : null }; });
          const nums = vals.map(o => o.n).filter(n => n != null);
          const max = nums.length ? Math.max(...nums) : null;
          return `<tr><td class="dim nw">${esc(lb)}</td>${vals.map(o => `<td class="nw ${o.n != null && o.n === max && nums.length > 1 && new Set(nums).size > 1 ? 'win' : ''}">${o.c ? esc(o.c.v ?? '—') : '—'}${o.c && o.c.s ? ` <span class="muted" style="font-size:10.5px">${esc(o.c.s)}</span>` : ''}</td>`).join('')}</tr>`;
        }).join('')}
        </table></div></div>
      ${numericLabels.length && chosen.length >= 2 ? `<div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Ölçüt karşılaştırması'))}</h3>
        <div class="right"><select class="input" id="cm" style="height:28px;width:auto">${numericLabels.map(lb => `<option ${lb === S.cmpMetric ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select><button class="btn sm" id="cpng">${IC.dl}PNG</button></div></div>
        <div class="card-b"><div class="chart" id="cch"></div></div></div>` : ''}
      <div class="chart-note">${esc(t('Değerler modül sonuçlarındaki göstergelerden alınır. Yeşil hücre o satırdaki en yüksek değer.'))}</div>`;
    $('#cp', v).onchange = e => { S.cmpPlatform = e.target.value; S.cmpPick = null; S.cmpMetric = null; render(); };
    $$('.toolbar input[data-id]', v).forEach(cb => cb.onchange = () => { const set = new Set(S.cmpPick); cb.checked ? set.add(cb.dataset.id) : set.delete(cb.dataset.id); S.cmpPick = [...set]; render(); });
    if (numericLabels.length && chosen.length >= 2) {
      const draw = () => Charts.render($('#cch', v), { type: 'hbar', keepOrder: true, data: kpiByScan.map(x => { const c = cell(x, S.cmpMetric); return { label: x.s.value || x.s.raw, value: pnum(c && c.v) || 0 }; }) });
      $('#cm', v).onchange = e => { S.cmpMetric = e.target.value; draw(); };
      draw();
      $('#cpng', v).onclick = () => { const svg = $('#cch svg', v); if (svg) Charts.svgToPng(svg, `karsilastirma_${S.cmpPlatform}.png`, { title: `${PLATFORMS[S.cmpPlatform].name} — ${S.cmpMetric}` }); };
    }
  }

  // ───────────────── Modül sayfası ─────────────────
  function viewModule(v, p) {
    const P = PLATFORMS[p];
    setTitle(P.name);
    const scans = S.scans.filter(s => s.platform === p);
    if (!scans.find(s => s.id === S.sel[p])) S.sel[p] = scans.length ? scans[scans.length - 1].id : null;
    const cur = scans.find(s => s.id === S.sel[p]);
    const keyMissing = p === 'youtube' && S.status.youtube_api_key === false;
    const mockMode = p === 'x' && S.status.x_bearer_token === false;
    const open = !!(S.guideOpen || {})[p];
    v.innerHTML = `
      <div class="scan-head">${picon(p, 'lg')}<div><h2>${P.name}</h2><p>${esc(P.desc)}</p></div>
        <button class="btn sm" id="guide-t" style="margin-left:auto">${esc(open ? t('Rehberi gizle') : t('Nasıl kullanılır'))}</button></div>
      <div class="card guide ${open ? '' : 'hidden'}" id="guide" style="margin-bottom:12px">
        <div class="grid g3" style="padding:14px;gap:22px">
          <div><div class="gh">${esc(t('Girdi'))}</div>${P.guide.accepts.map(([f, e]) => `<div class="acc"><span class="chip" data-ex="${esc(f.split('  ')[0])}">${esc(f)}</span><span class="dim">${esc(e)}</span></div>`).join('')}</div>
          <div><div class="gh">${esc(t('Çıktı'))}</div><ul>${P.guide.outputs.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div>
          <div><div class="gh">${esc(t('Not'))}</div>${P.guide.notes.map(n => `<p class="dim" style="margin-bottom:6px">${esc(n)}</p>`).join('')}
            <p class="dim">${esc(t('Sonuçta grafikler, ilişki grafiği, bulgular ve ham JSON sekmeleri var. Grafikte bir kullanıcı adına çift tıklamak o hesabı ilgili modülde tarar.'))}</p></div>
        </div></div>
      <div class="card card-b">
        <div class="scan-form">
          <label class="field grow">${esc(t('Hedef'))}
            <input class="input" id="q" placeholder="${esc(P.placeholder)}${P.max > 1 ? ' · ' + esc(t('birden fazla: boşlukla ayırın')) : ''}" autocomplete="off" spellcheck="false"></label>
          ${P.videoOpt ? `<label class="field">${esc(t('Video'))}<input class="input" id="vc" type="number" min="${P.videoOpt.min}" max="${P.videoOpt.max}" value="${P.videoOpt.def}" style="width:84px;height:36px"></label>` : ''}
          ${P.compare ? `<label class="field" style="flex-direction:row;align-items:center;gap:7px;height:36px"><input type="checkbox" id="cmp"> ${esc(t('Karşılaştır'))}</label>` : ''}
          <button class="btn primary" id="go">${esc(t('Tara'))}</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap">
          <div class="chips">${P.examples.map(x => `<span class="chip" data-ex="${esc(x)}">${esc(x)}</span>`).join('')}</div>
          ${S.activeCase ? `<span class="muted" style="margin-left:auto;font-size:11.5px">→ ${esc(S.activeCase.case_id)}</span>` : ''}</div>
        ${keyMissing ? `<div class="notice" style="margin-top:12px">${esc(t('YouTube API anahtarı tanımlı değil.'))} <a href="#/settings">${esc(t('Ayarlar'))}</a></div>` : ''}
        ${mockMode ? `<div class="notice info" style="margin-top:12px">${esc(t('X API anahtarı (Bearer Token) girilmedi — örnek veri gösteriliyor.'))} <a href="#/settings">${esc(t('Ayarlar'))}</a></div>` : ''}
      </div>
      ${scans.length ? `<div class="scan-tabs">${scans.map(s => `<div class="scan-tab ${cur && s.id === cur.id ? 'active' : ''}" data-id="${s.id}" title="${esc(STATUS[s.status][1])}">
        <span class="st ${STATUS[s.status][0]}"></span><span class="mono">${esc(s.raw)}</span><span class="muted" style="font-size:11px">${new Date(s.at).toLocaleTimeString(I18N.locale, { hour: '2-digit', minute: '2-digit' })}</span>
        <span class="x" data-del="${s.id}" title="${esc(t('Kaldır'))}">×</span></div>`).join('')}</div>` : ''}
      <div id="result"></div>`;
    const go = () => {
      const raws = $('#q', v).value.split(/[\s,]+/).filter(Boolean);
      startScan(p, p === 'stackexchange' && !/^https?:|^\d+$|^[a-z.\-]+:\d+$/i.test($('#q', v).value.trim()) ? [$('#q', v).value.trim()] : raws,
        { videos: $('#vc', v) ? Math.max(P.videoOpt.min, Math.min(P.videoOpt.max, +$('#vc', v).value || P.videoOpt.def)) : null, compare: $('#cmp', v)?.checked });
    };
    $('#go', v).onclick = go;
    $('#guide-t', v).onclick = () => { S.guideOpen = S.guideOpen || {}; S.guideOpen[p] = !S.guideOpen[p]; $('#guide', v).classList.toggle('hidden', !S.guideOpen[p]); $('#guide-t', v).textContent = S.guideOpen[p] ? t('Rehberi gizle') : t('Nasıl kullanılır'); };
    $('#q', v).onkeydown = e => { if (e.key === 'Enter') go(); };
    $$('[data-ex]', v).forEach(c => c.onclick = () => { $('#q', v).value = c.dataset.ex; $('#q', v).focus(); });
    $$('.scan-tab', v).forEach(tb => tb.onclick = e => {
      if (e.target.dataset.del) { S.scans = S.scans.filter(s => s.id !== e.target.dataset.del); persist(); render(); return; }
      S.sel[p] = tb.dataset.id; render();
    });
    if (!scans.length) { $('#result', v).innerHTML = `<div class="empty" style="padding:60px 0">${esc(t('Henüz tarama yok'))}</div>`; setTimeout(() => $('#q', v)?.focus(), 30); return; }
    if (cur) renderResult($('#result', v), cur);
  }

  function discovered(s) {
    const self = Signals.selfNodes(s);
    const have = new Set(S.scans.map(x => `${x.platform}|${String(x.value || x.raw).toLowerCase().replace(/^@/, '')}`));
    const out = [], seen = new Set();
    ((s.graph || {}).nodes || []).forEach(n => {
      if (self.has(n.id)) return;
      if (n.type === 'domain' && Signals.BIG.has(String(n.label).toLowerCase().replace(/^www\./, ''))) return;
      resolvePivots(n).slice(0, 1).forEach(pv => {
        const k = `${pv.platform}|${pv.raw.toLowerCase().replace(/^@/, '')}`;
        if (seen.has(k) || have.has(k) || (pv.platform === s.platform && String(pv.raw).toLowerCase().replace(/^@/, '') === String(s.value).toLowerCase().replace(/^@/, ''))) return;
        seen.add(k); out.push({ ...pv, node: n });
      });
    });
    return out;
  }

  function renderResult(el, s) {
    const P = PLATFORMS[s.platform];
    if (s.status === 'running') {
      el.innerHTML = `<div class="card card-b">${t('{target} taranıyor…', { target: `<b>${esc(s.raw)}</b>` })}<div class="progress"><i></i></div></div>`;
      return;
    }
    if (s.status !== 'ok') {
      el.innerHTML = `<div class="notice err"><b>${esc(STATUS[s.status][1])}</b> — ${esc(I18N.err(s.error || ''))}</div>
        <div style="margin-top:10px"><button class="btn sm" id="retry">${IC.refresh}${esc(t('Tekrar dene'))}</button></div>`;
      $('#retry', el).onclick = () => startScan(s.platform, s.opts?.compare ? s.raw.split(' ') : [s.raw], s.opts || {});
      return;
    }
    const d = s.data || {};
    const h = P.header(d) || {};
    const kpis = (P.kpis(d) || []).filter(Boolean);
    const tab = S.tab[s.id] || 'ozet';
    const initials = (h.mono || String(h.title || '?').replace(/^[@ur]\//, '').slice(0, 2)).toUpperCase();
    const disc = discovered(s);
    const ev = s.evidence;
    el.innerHTML = `
      <div class="card"><div class="profile">
        <div class="avatar">${h.avatar ? `<img src="${esc(h.avatar)}" referrerpolicy="no-referrer" alt="" style="width:100%;height:100%;object-fit:cover" onerror="this.replaceWith(document.createTextNode('${esc(initials)}'))">` : esc(initials)}</div>
        <div style="min-width:0">
          <h2>${esc(h.title || s.value)} ${(h.badges || []).map(b => `<span class="badge ${b.c || ''}">${esc(b.t)}</span>`).join('')}</h2>
          <div class="handle">${h.url ? `<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.handle || h.url)}</a>` : esc(h.handle || '')}
            <span class="muted"> · ${new Date(s.at).toLocaleString(I18N.locale)}${s.duration ? ` · ${esc(t('{n} sn', { n: (s.duration / 1000).toFixed(1) }))}` : ''}</span></div>
          ${h.bio ? `<div class="bio">${esc(h.bio)}</div>` : ''}
          ${ev ? `<div class="evid mono" title="${esc(t('SHA-256 · kanonik JSON (anahtarlar sıralı, UTF-8)'))}">SHA-256 ${esc(ev.sha256.slice(0, 16))}… · ${esc(String(ev.collected_at).replace('T', ' ').replace(/(\.\d+)?\+00:00$/, ' UTC'))} <button class="linkbtn" id="verify">${esc(t('doğrula'))}</button></div>` : ''}
        </div>
        <div class="right">
          <button class="btn sm" id="rescan">${IC.refresh}${esc(t('Yeniden tara'))}</button>
          ${s.opts?.compare ? '' : `<button class="btn sm" id="watch">${IC.eye}${esc(t('İzle'))}</button>`}
          <button class="btn sm" id="dljson">${IC.dl}JSON</button>
        </div></div></div>
      ${kpis.length ? `<div class="kpis" style="margin-top:12px">${kpis.map(k => `<div class="kpi"><div class="k">${esc(k.k)}</div><div class="v">${esc(k.v ?? '—')}</div>${k.s ? `<div class="s">${esc(k.s)}</div>` : ''}</div>`).join('')}</div>` : ''}
      ${disc.length ? `<details class="card disc" style="margin-top:12px" ${S.discOpen?.[s.id] ? 'open' : ''}><summary class="card-h"><h3>${esc(t('Bulunan hesaplar'))}</h3><span class="sub">${esc(t('{n} · seçip tarayın', { n: disc.length }))}</span></summary>
        <div class="card-b"><div class="disc-list">${disc.map((x, i) => `<label class="chip" style="gap:6px" title="${esc(PLATFORMS[x.platform].name)}"><input type="checkbox" data-d="${i}">${picon(x.platform)} ${esc(x.raw)}</label>`).join('')}</div>
        <div style="display:flex;gap:8px;margin-top:10px"><button class="btn sm" id="dall">${esc(t('Tümünü seç'))}</button><button class="btn sm primary" id="dgo">${esc(t('Seçilenleri tara'))}</button></div></div></details>` : ''}
      <div class="tabs">
        ${[['ozet', esc(t('Grafikler'))], ['graf', `${esc(t('İlişki grafiği'))} <span class="muted mono">${(s.graph?.nodes || []).length}</span>`], ['bulgu', esc(t('Bulgular'))], ['json', esc(t('Ham JSON'))]].map(([k, lb]) => `<div class="tab ${tab === k ? 'active' : ''}" data-tab="${k}">${lb}</div>`).join('')}
      </div>
      <div id="tabbody"></div>`;
    $('#rescan', el).onclick = () => startScan(s.platform, s.opts?.compare ? s.raw.split(' ') : [s.raw], s.opts || {});
    $('#dljson', el).onclick = () => download(`${s.platform}_${safe(s.value)}.json`, JSON.stringify({ evidence: s.evidence, data: s.data }, null, 2));
    const w = $('#watch', el);
    if (w) w.onclick = () => dialog(t('İzlemeye al'), `<p class="dim" style="margin-bottom:10px">${esc(t('{target} belirli aralıklarla yeniden taranır; değişiklikler İzleme sayfasında görünür.', { target: scanLabel(s) }))}</p>
      <label class="field">${esc(t('Aralık'))}<select class="input" name="h">${[[1, t('Saatte bir')], [6, t('6 saatte bir')], [12, t('12 saatte bir')], [24, t('Günde bir')], [72, t('3 günde bir')], [168, t('Haftada bir')]].map(([k, lb]) => `<option value="${k}" ${k === 24 ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select></label>`,
      async dd => {
        try { await api('/api/watches', { method: 'POST', body: JSON.stringify({ platform: s.platform, raw: s.raw, interval_hours: +dd.querySelector('[name=h]').value }) }); toast(t('İzlemeye alındı'), 'ok'); }
        catch (e) { toast(I18N.err(e.message), 'err'); return false; }
      }, t('İzle'));
    const vb = $('#verify', el);
    if (vb) vb.onclick = async () => {
      try { const r = await api('/api/evidence/verify', { method: 'POST', body: JSON.stringify({ data: s.data, sha256: ev.sha256 }) });
        toast(r.match ? t('Veri toplandığı andan beri değişmemiş') : t('Hash uyuşmuyor: veri değiştirilmiş'), r.match ? 'ok' : 'err'); }
      catch (e) { toast(I18N.err(e.message), 'err'); }
    };
    const dz = $('details.disc', el);
    if (dz) {
      dz.addEventListener('toggle', () => { S.discOpen = S.discOpen || {}; S.discOpen[s.id] = dz.open; });
      $('#dall', el).onclick = () => $$('[data-d]', el).forEach(c => { c.checked = true; });
      $('#dgo', el).onclick = () => {
        const pick = $$('[data-d]:checked', el).map(c => disc[+c.dataset.d]);
        if (!pick.length) { toast(t('Hesap seçin'), 'err'); return; }
        const by = {};
        pick.forEach(x => { (by[x.platform] = by[x.platform] || []).push(x.raw); });
        Object.entries(by).forEach(([pl, raws]) => {
          for (let i = 0; i < raws.length; i += PLATFORMS[pl].max) startScan(pl, raws.slice(i, i + PLATFORMS[pl].max), { background: true, videos: PLATFORMS[pl].videoOpt?.def });
        });
        toast(t('{n} hesap taranıyor', { n: pick.length }), 'ok');
      };
    }
    $$('.tab', el).forEach(tb => tb.onclick = () => { S.tab[s.id] = tb.dataset.tab; renderResult(el, s); });
    const body = $('#tabbody', el);
    if (tab === 'ozet') renderCharts(body, s, P, d);
    else if (tab === 'graf') renderScanGraph(body, s);
    else if (tab === 'bulgu') renderFindings(body, P.findings(d) || []);
    else renderJson(body, s);
  }

  let _leafletP = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (_leafletP) return _leafletP;
    _leafletP = new Promise((res, rej) => {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
      document.head.appendChild(css);
      const sc = document.createElement('script');
      sc.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
      sc.onload = () => res(window.L); sc.onerror = () => rej(new Error('load'));
      document.head.appendChild(sc);
    });
    return _leafletP;
  }
  // Anahtarsız harita: Leaflet + CARTO dark (OpenStreetMap verisi) — token GEREKMEZ.
  async function renderHashMap(el, msg, points) {
    const pts = (points || []).filter(p => p.lat != null && p.lng != null);
    let L;
    try { L = await loadLeaflet(); } catch (e) { el.style.display = 'none'; msg.textContent = t('Harita kütüphanesi yüklenemedi (internet erişimi gerekir).'); return; }
    try {
      // Nokta olmasa bile haritayı AÇ (OpenStreetMap anahtarsız çalışır — dünya görünümü).
      const map = L.map(el, { scrollWheelZoom: false, attributionControl: true })
        .setView(pts.length ? [+pts[0].lat, +pts[0].lng] : [30, 15], pts.length ? 3 : 2);
      // Tamamen anahtarsız OpenStreetMap standart tile'ları (koyu görünüm CSS filtresiyle).
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '© OpenStreetMap katkıda bulunanlar',
      }).addTo(map);
      if (!pts.length) {
        msg.innerHTML = esc(t('Konum etiketli gönderi bulunamadı — harita boş. Koordinat noktaları için (ücretsiz) FLICKR_API_KEY veya HikerAPI gerekir; harita motorunun kendisi anahtarsızdır.')) + ` <a href="#/settings">${esc(t('Ayarlar'))}</a>`;
        setTimeout(() => { try { map.invalidateSize(); } catch (e) { /* */ } }, 80);
        return;
      }
      const max = Math.max(1, ...pts.map(p => +p.count || 1));
      const latlngs = [];
      pts.forEach(p => {
        const r = 6 + 18 * Math.sqrt((+p.count || 1) / max);
        L.circleMarker([+p.lat, +p.lng], { radius: r, color: '#93c5fd', weight: 1, fillColor: '#5f8ac2', fillOpacity: 0.55 })
          .addTo(map).bindPopup(`<b>${esc(p.label || '')}</b>: ${+p.count || 1}`);
        latlngs.push([+p.lat, +p.lng]);
      });
      setTimeout(() => { try { map.invalidateSize(); if (latlngs.length > 1) map.fitBounds(latlngs, { padding: [30, 30], maxZoom: 9 }); else map.setView(latlngs[0], 8); } catch (e) { /* */ } }, 80);
    } catch (e) { el.style.display = 'none'; msg.textContent = t('Harita oluşturulamadı: {v}', { v: e.message }); }
  }

  function renderCharts(body, s, P, d) {
    const specs = (P.charts(d) || []).filter(c => c && (c.type === 'heatmap' ? !c.empty : (c.data && c.data.length && c.data.some(x => x.value > 0))));
    const media = P.media ? P.media(d) : [];
    const mapData = P.map ? P.map(d) : null;
    const hasMap = !!(mapData && mapData.points);
    if (!specs.length && !media.length && !hasMap) { body.innerHTML = `<div class="empty">${esc(t('Bu sonuçta grafik verisi yok — Bulgular sekmesine bakın'))}</div>`; return; }
    const mapCard = hasMap ? `<div class="card" style="margin-bottom:14px">
      <div class="card-h"><div><h3>${esc(mapData.title || t('Konum haritası'))}</h3>${mapData.note ? `<div class="sub">${esc(mapData.note)}</div>` : ''}</div></div>
      <div class="card-b"><div id="hxmap" style="height:440px;border-radius:8px;overflow:hidden;background:#0b1017"></div><div id="hxmsg" class="muted" style="font-size:12.5px;margin-top:8px"></div></div></div>` : '';
    body.innerHTML = mapCard + `<div class="grid gauto">
      ${specs.map((c, i) => `<div class="card" style="${c.wide ? 'grid-column:1/-1' : ''}"><div class="card-h"><div><h3>${esc(c.title)}</h3>${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ''}</div>
        <div class="right"><button class="btn sm" data-png="${i}" title="${esc(t('PNG olarak indir'))}">${IC.dl}PNG</button></div></div>
        <div class="card-b"><div class="chart" id="ch${i}"></div></div></div>`).join('')}
      ${media.map((m, i) => `<div class="card" style="grid-column:1/-1"><div class="card-h"><div><h3>${esc(m.title)}</h3><div class="sub">${esc(m.note)}</div></div>
        <div class="right"><button class="btn sm" data-media="${i}">${esc(t('Sunucuda oluştur'))}</button><a class="btn sm hidden" data-mdl="${i}">${IC.dl}${esc(t('PNG indir'))}</a></div></div>
        <div class="card-b"><div data-mimg="${i}" class="muted" style="font-size:12.5px">${esc(t('Henüz oluşturulmadı'))}</div></div></div>`).join('')}
    </div>`;
    if (hasMap) renderHashMap($('#hxmap', body), $('#hxmsg', body), mapData.points);
    specs.forEach((c, i) => Charts.render($('#ch' + i, body), c));
    $$('[data-png]', body).forEach(b => b.onclick = () => {
      const c = specs[+b.dataset.png]; const svg = $('#ch' + b.dataset.png + ' svg', body);
      if (svg) Charts.svgToPng(svg, `${s.platform}_${safe(s.value)}_${c.title.toLowerCase().replace(/[^a-z0-9ğüşıöç]+/gi, '_')}.png`, { title: `${c.title} — ${s.value}` });
    });
    $$('[data-media]', body).forEach(b => b.onclick = async () => {
      const m = media[+b.dataset.media]; const box = $(`[data-mimg="${b.dataset.media}"]`, body);
      b.disabled = true; box.innerHTML = `${esc(t('PNG üretiliyor…'))}<div class="progress"><i></i></div>`;
      try {
        const r = await fetch(m.endpoint);
        if (!r.ok) { let msg = `HTTP ${r.status}`; try { msg = (await r.json()).detail || msg; } catch (e) { /* */ } throw new Error(msg); }
        const url = URL.createObjectURL(await r.blob());
        box.innerHTML = `<img class="media-img" src="${url}" alt="${esc(m.title)}">`;
        const a = $(`[data-mdl="${b.dataset.media}"]`, body); a.href = url; a.download = m.file; a.classList.remove('hidden');
        b.textContent = t('Yeniden oluştur');
      } catch (e) { box.innerHTML = `<div class="notice err">${esc(I18N.err(e.message))}</div>`; }
      b.disabled = false;
    });
  }

  function renderScanGraph(body, s) {
    if (scanGraph) { scanGraph.destroy(); scanGraph = null; }
    body.innerHTML = `<div id="sg"></div><div class="chart-note">${esc(t('Çift tıklama: ilgili modülde tara · sağ tık: menü ve analist işaretleri'))}</div>`;
    scanGraph = new GraphView($('#sg', body), {
      height: 640, resolvePivots, onPivot: pivot, toast, ...annFns(),
      filename: t('{name}_iliski', { name: `${s.platform}_${safe(s.value)}` }), pngTitle: t('İlişki grafiği — {target}', { target: `${PLATFORMS[s.platform].name}: ${s.value}` }),
      emptyText: t('Bu tarama için grafik düğümü üretilmedi.'),
    });
    scanGraph.setData(s.graph || { nodes: [], edges: [] });
  }

  function cell(c) {
    if (c && typeof c === 'object') {
      if (c.html != null) return c.html;  // güvenilir (picon SVG'si + kaçışlı metin)
      if (c.badge != null) { const cls = c.cls ? ' ' + c.cls : ''; return `<span class="badge${cls}">${c.icon ? picon(c.icon) : ''}${esc(c.badge)}</span>`; }
      return c.href ? `<a href="${esc(c.href)}" target="_blank" rel="noopener">${esc(c.text ?? c.href)}</a>` : esc(c.text);
    }
    return esc(c ?? '—');
  }
  function renderFindings(body, sections) {
    const html = sections.filter(Boolean).map(sec => {
      if (sec.kind === 'kv') {
        if (!sec.rows.length) return '';
        return `<div class="card"><div class="card-h"><h3>${esc(sec.title)}</h3></div><div class="card-b"><div class="kv">${sec.rows.map(([k, v]) =>
          `<div>${esc(k)}</div><div>${/^https?:\/\//.test(String(v)) ? `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>` : esc(v)}</div>`).join('')}</div></div></div>`;
      }
      if (sec.kind === 'list') {
        if (!sec.items.length && !sec.note) return '';
        return `<div class="card"><div class="card-h"><h3>${esc(sec.title)}</h3><span class="sub">${sec.items.length || ''}</span></div><div class="card-b">
          ${sec.note ? `<div class="dim" style="margin-bottom:6px">${esc(sec.note)}</div>` : ''}
          <div class="list">${sec.items.map(it => `<div class="li"><span class="grow" title="${esc(it.text)}">${esc(it.text)}</span>${it.tag ? `<span class="tag">${esc(it.tag)}</span>` : ''}
            <button class="icon-btn" data-copy="${esc(it.text)}" title="${esc(t('Kopyala'))}">${IC.copy}</button>
            ${it.href ? `<a class="icon-btn" href="${esc(it.href)}" target="_blank" rel="noopener" title="${esc(t('Aç'))}">${IC.open}</a>` : ''}</div>`).join('')}</div></div></div>`;
      }
      if (sec.kind === 'table') {
        if (!sec.rows.length) return '';
        return `<div class="card" style="grid-column:1/-1"><div class="card-h"><h3>${esc(sec.title)}</h3><span class="sub">${sec.rows.length}</span></div>
          <div class="card-b" style="padding:0 4px;overflow:auto;max-height:520px"><table class="t"><tr>${sec.cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr>
          ${sec.rows.map(r => `<tr>${r.map(c => `<td>${cell(c)}</td>`).join('')}</tr>`).join('')}</table></div></div>`;
      }
      return '';
    }).join('');
    body.innerHTML = html ? `<div class="grid g2">${html}</div>` : `<div class="empty">${esc(t('Bulgu yok'))}</div>`;
    $$('[data-copy]', body).forEach(b => b.onclick = () => { navigator.clipboard?.writeText(b.dataset.copy); toast(t('Kopyalandı')); });
  }

  function renderJson(body, s) {
    const txt = JSON.stringify(s.data, null, 2);
    const hl = esc(txt).replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
      (m, str, colon, bool, n) => str ? (colon ? `<span class="k">${str}</span>${colon}` : `<span class="s">${str}</span>`) : bool ? `<span class="b">${bool}</span>` : `<span class="n">${n}</span>`);
    body.innerHTML = `<div style="display:flex;gap:8px;margin-bottom:8px"><button class="btn sm" id="cj">${IC.copy}${esc(t('Kopyala'))}</button><button class="btn sm" id="dj">${IC.dl}${esc(t('İndir'))}</button>
      <span class="muted" style="font-size:11.5px;align-self:center">${esc(t('{n} karakter', { n: nf.format(txt.length) }))}</span></div><pre class="json">${hl}</pre>`;
    $('#cj', body).onclick = () => { navigator.clipboard?.writeText(txt); toast(t('Kopyalandı')); };
    $('#dj', body).onclick = () => download(`${s.platform}_${safe(s.value)}.json`, txt);
  }

  // ───────────────── Vaka yönetimi ─────────────────
  const CONF = { low: t('Düşük'), medium: t('Orta'), high: t('Yüksek') };
  function activateCase(c, sr) {
    S.activeCase = { case_id: c.case_id, title: c.title };
    if (sr) {
      S.scans = sr.scans || []; S.sel = {};
      S.ann = sr.ann || {}; S.manual = sr.manual || { nodes: [], edges: [] }; S.pairs = sr.pairs || {};
    }
    persist();
  }

  async function viewCases(v) {
    setTitle(t('Vakalar'));
    const ok = okScans();
    v.innerHTML = `
      <div class="split">
        <div class="card"><div class="card-h"><h3>${esc(t('Vakalar'))}</h3><div class="right">
            <input class="input" id="cs" placeholder="${esc(t('Ara'))}" style="height:28px;width:200px">
            <label class="btn sm">${esc(t('İçe aktar'))}<input type="file" id="imp" accept=".socmint,.zip" class="hidden"></label></div></div>
            <div class="card-b" style="padding:0 4px" id="clist"><div class="empty">${esc(t('Yükleniyor…'))}</div></div></div>
        <div class="card"><div class="card-h"><h3>${esc(t('Yeni vaka'))}</h3></div><div class="card-b" style="display:flex;flex-direction:column;gap:10px">
          <label class="field">${esc(t('Başlık'))}<input class="input" id="ct"></label>
          <label class="field">${esc(t('Hedef'))}<input class="input" id="ctg" value="${esc(ok[0]?.value || '')}"></label>
          <label class="field">${esc(t('Analist'))}<input class="input" id="ca" value="${esc(localStorage.getItem('socmint.analyst') || '')}"></label>
          <label class="field">${esc(t('Güven'))}<select class="input" id="cc"><option value="low">${esc(CONF.low)}</option><option value="medium" selected>${esc(CONF.medium)}</option><option value="high">${esc(CONF.high)}</option></select></label>
          ${ok.length ? `<label class="field" style="flex-direction:row;gap:8px;align-items:center"><input type="checkbox" id="cinc" checked> ${esc(t('Oturumdaki {n} taramayı ekle', { n: ok.length }))}</label>` : ''}
          <button class="btn primary" id="cnew">${esc(t('Oluştur ve aktif yap'))}</button>
          <p class="muted" style="font-size:11.5px">${esc(t('Aktif vakaya taramalar, analist işaretleri ve notlar otomatik kaydedilir.'))}</p>
        </div></div>
      </div>`;
    const load = async () => {
      try {
        const q = $('#cs', v).value.trim();
        const r = await api('/api/cases' + (q ? `?search=${encodeURIComponent(q)}` : ''));
        $('#clist', v).innerHTML = r.cases.length ? `<table class="t"><tr><th>${esc(t('Vaka'))}</th><th>${esc(t('Başlık'))}</th><th>${esc(t('Hedef'))}</th><th>${esc(t('Analist'))}</th><th>${esc(t('Güven'))}</th><th>${esc(t('Platformlar'))}</th><th>${esc(t('Güncelleme'))}</th></tr>
          ${r.cases.map(c => `<tr style="cursor:pointer" data-open="${esc(c.case_id)}"><td class="mono">${esc(c.case_id)}${S.activeCase?.case_id === c.case_id ? ` <span class="badge accent">${esc(t('aktif'))}</span>` : ''}</td>
            <td>${esc(c.title)}</td><td class="mono">${esc(c.target || '')}</td><td>${esc(c.analyst || '')}</td><td>${esc(CONF[c.confidence] || c.confidence)}</td>
            <td>${(c.platforms_csv || '').split(',').filter(Boolean).map(p => picon(p)).join(' ')}</td>
            <td class="dim">${new Date(c.updated_at).toLocaleString(I18N.locale)}</td></tr>`).join('')}</table>`
          : `<div class="empty">${esc(t('Henüz vaka yok'))}</div>`;
        $$('[data-open]', v).forEach(row => row.onclick = () => { location.hash = '#/case/' + encodeURIComponent(row.dataset.open); });
      } catch (e) { $('#clist', v).innerHTML = `<div class="notice err">${esc(I18N.err(e.message))}</div>`; }
    };
    $('#cs', v).oninput = () => { clearTimeout(v._t); v._t = setTimeout(load, 250); };
    $('#imp', v).onchange = async e => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append('file', f);
      try { const r = await api('/api/cases/import', { method: 'POST', body: fd }); toast(t('İçe aktarıldı: {id}', { id: r.new_case_id }), 'ok'); load(); } catch (err) { toast(I18N.err(err.message), 'err'); }
    };
    $('#cnew', v).onclick = async () => {
      const analyst = $('#ca', v).value.trim() || t('Analist');
      try { localStorage.setItem('socmint.analyst', analyst); } catch (e) { /* */ }
      const include = $('#cinc', v)?.checked;
      if (!include && S.scans.length && !confirm(t('Oturumdaki taramalar vakaya eklenmeyecek ve oturum temizlenecek. Devam edilsin mi?'))) return;
      try {
        const c = await api('/api/cases', { method: 'POST', body: JSON.stringify({
          title: $('#ct', v).value.trim() || t('Vaka {date}', { date: new Date().toLocaleDateString(I18N.locale) }), target: $('#ctg', v).value.trim(), analyst, confidence: $('#cc', v).value }) });
        activateCase(c, include ? { scans: S.scans, ann: S.ann, manual: S.manual, pairs: S.pairs } : { scans: [] });
        toast(t('{id} oluşturuldu', { id: c.case_id }), 'ok');
        location.hash = '#/case/' + encodeURIComponent(c.case_id);
      } catch (e) { toast(I18N.err(e.message), 'err'); }
    };
    load();
  }

  async function viewCase(v, id) {
    setTitle(t('Vaka'), id);
    v.innerHTML = `<div class="empty">${esc(t('Yükleniyor…'))}</div>`;
    let c;
    try { c = await api('/api/cases/' + encodeURIComponent(id)); } catch (e) { v.innerHTML = `<div class="notice err">${esc(I18N.err(e.message))}</div>`; return; }
    const isActive = S.activeCase?.case_id === c.case_id;
    const sr = c.scan_results || {};
    const scans = isActive ? S.scans.filter(s => s.status === 'ok') : (sr.scans || []);
    const ann = isActive ? S.ann : (sr.ann || {});
    setTitle(c.title, c.case_id);
    v.innerHTML = `
      <div class="split">
        <div>
          <div class="card"><div class="card-h"><h3 class="mono">${esc(c.case_id)}</h3>${isActive ? `<span class="badge accent">${esc(t('Aktif'))}</span>` : ''}
            <span class="sub" id="savest">${new Date(c.created_at).toLocaleString(I18N.locale)}</span>
            <div class="right">${isActive ? '' : `<button class="btn sm primary" id="act">${esc(t('Aktif yap'))}</button>`}</div></div>
            <div class="card-b" style="display:grid;grid-template-columns:2fr 1.4fr 1fr 1fr;gap:10px">
              <label class="field">${esc(t('Başlık'))}<input class="input" data-f="title" value="${esc(c.title)}"></label>
              <label class="field">${esc(t('Hedef'))}<input class="input" data-f="target" value="${esc(c.target || '')}"></label>
              <label class="field">${esc(t('Analist'))}<input class="input" data-f="analyst" value="${esc(c.analyst || '')}"></label>
              <label class="field">${esc(t('Güven'))}<select class="input" data-f="confidence">${Object.entries(CONF).map(([k, lb]) => `<option value="${k}" ${c.confidence === k ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select></label>
            </div>
            <div class="card-b" style="padding-top:0"><label class="field">${esc(t('Notlar'))}
              <textarea class="input" data-f="notes" rows="11" style="font-family:var(--font);line-height:1.6">${esc(c.notes || '')}</textarea></label></div>
          </div>
          <div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Taramalar'))}</h3><span class="sub">${scans.length}</span></div>
            <div class="card-b" style="padding:0 4px">${scans.length ? `<table class="t"><tr><th></th><th>${esc(t('Girdi'))}</th><th>${esc(t('Tarih'))}</th><th>SHA-256</th><th class="num">${esc(t('Düğüm'))}</th></tr>
              ${scans.map(s => `<tr ${isActive ? `style="cursor:pointer" data-scan="${s.id}"` : ''}><td>${picon(s.platform)}</td><td class="mono">${esc(s.raw)}</td>
                <td class="dim">${new Date(s.at).toLocaleString(I18N.locale)}</td><td class="mono dim">${esc((s.evidence?.sha256 || '').slice(0, 12))}</td><td class="num">${(s.graph?.nodes || []).length}</td></tr>`).join('')}</table>`
              : `<div class="empty">${esc(isActive ? t('Modüllerden yapılan taramalar buraya eklenecek') : t('Tarama yok'))}</div>`}</div></div>
          ${Object.keys(ann).length ? `<div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Analist işaretleri'))}</h3><span class="sub">${Object.keys(ann).length}</span></div>
            <div class="card-b" style="padding:0 4px"><table class="t"><tr><th>${esc(t('Düğüm||one'))}</th><th>${esc(t('İşaret'))}</th><th>${esc(t('Not'))}</th></tr>
            ${Object.entries(ann).map(([k, a]) => `<tr><td class="mono">${esc(k)}</td><td>${esc((GraphMeta.ANN[a.status] || {}).label || '—')}</td><td>${esc(a.note || '')}</td></tr>`).join('')}</table></div></div>` : ''}
        </div>
        <div>
          <div class="card"><div class="card-h"><h3>${esc(t('Dışa aktar'))}</h3></div><div class="card-b" style="display:flex;flex-direction:column;gap:8px">
            <button class="btn" id="xhtml">${IC.dl}${esc(t('HTML rapor'))}</button>
            <button class="btn" id="xpdf">${IC.dl}${esc(t('PDF rapor'))}</button>
            <button class="btn" id="xxlsx">${IC.dl}Excel</button>
            <a class="btn" href="/api/cases/${encodeURIComponent(c.case_id)}/export">${IC.dl}${esc(t('Vaka paketi (.socmint)'))}</a>
            <button class="btn" id="xjson">${IC.dl}JSON</button>
          </div></div>
          <div class="card" style="margin-top:14px"><div class="card-b" style="display:flex;flex-direction:column;gap:8px">
            ${isActive ? `<button class="btn" id="deact">${esc(t('Aktif vakayı kapat'))}</button>` : ''}
            <button class="btn danger" id="del">${IC.trash}${esc(t('Vakayı sil'))}</button></div></div>
        </div>
      </div>`;
    let tm;
    $$('[data-f]', v).forEach(el => el.addEventListener('input', () => {
      clearTimeout(tm); $('#savest', v).textContent = t('Kaydediliyor…');
      tm = setTimeout(async () => {
        const body = {}; $$('[data-f]', v).forEach(x => { body[x.dataset.f] = x.value; });
        try {
          c = await api('/api/cases/' + encodeURIComponent(c.case_id), { method: 'PATCH', body: JSON.stringify(body) });
          if (S.activeCase?.case_id === c.case_id) { S.activeCase.title = c.title; save(); }
          $('#savest', v).textContent = t('Kaydedildi {time}', { time: new Date().toLocaleTimeString(I18N.locale) });
        } catch (e) { $('#savest', v).textContent = t('Kaydedilemedi: {err}', { err: I18N.err(e.message) }); }
      }, 700);
    }));
    const act = $('#act', v);
    if (act) act.onclick = () => {
      if (S.scans.length && !confirm(t('Oturumdaki mevcut taramalar bu vakanınkilerle değiştirilsin mi?'))) return;
      activateCase(c, sr); toast(t('{id} aktif', { id: c.case_id }), 'ok'); render();
    };
    const deact = $('#deact', v);
    if (deact) deact.onclick = () => { S.activeCase = null; save(); render(); };
    $('#del', v).onclick = async () => {
      if (!confirm(t('{id} kalıcı olarak silinsin mi?', { id: c.case_id }))) return;
      await api('/api/cases/' + encodeURIComponent(c.case_id), { method: 'DELETE' });
      if (S.activeCase?.case_id === c.case_id) { S.activeCase = null; save(); }
      toast(t('Vaka silindi')); location.hash = '#/cases';
    };
    const notesNow = () => $('[data-f=notes]', v).value;
    const opts = () => ({ ...reportOpts(c, notesNow(), scans), ann, manual: isActive ? S.manual : (sr.manual || { nodes: [], edges: [] }) });
    $('#xhtml', v).onclick = () => Report.html(opts());
    $('#xpdf', v).onclick = () => Report.pdf(opts());
    $('#xxlsx', v).onclick = () => Exporter.xlsx({ title: c.case_id, scans: scans.map(s => ({ platform: s.platform, raw: s.raw, value: s.value, status: s.status, at: s.at, data: s.data, evidence: s.evidence })),
      graph: mergedGraph(scans, { matches: true }), annotations: ann }, c.case_id).catch(e => toast(I18N.err(e.message), 'err'));
    $('#xjson', v).onclick = () => download(`${c.case_id}.json`, JSON.stringify({ ...c, scan_results: { ...sr, scans } }, null, 2));
    $$('[data-scan]', v).forEach(row => row.onclick = () => { const s = S.scans.find(x => x.id === row.dataset.scan); if (s) { S.sel[s.platform] = s.id; location.hash = '#/m/' + s.platform; } });
  }

  // ───────────────── İzleme ─────────────────
  async function viewWatch(v) {
    setTitle(t('İzleme'), t('değişiklik takibi'));
    v.innerHTML = `
      <div class="card card-b"><div class="scan-form">
        <label class="field">${esc(t('Modül'))}<select class="input" id="wp" style="height:36px">${ORDER.map(p => `<option value="${p}">${PLATFORMS[p].name}</option>`).join('')}</select></label>
        <label class="field grow">${esc(t('Hedef'))}<input class="input" id="wq" placeholder="${esc(t('modülün kabul ettiği biçimde'))}"></label>
        <label class="field">${esc(t('Aralık'))}<select class="input" id="wh" style="height:36px">${[[1, t('Saatte bir')], [6, t('6 saat')], [12, t('12 saat')], [24, t('Günde bir')], [72, t('3 gün')], [168, t('Haftada bir')]].map(([k, lb]) => `<option value="${k}" ${k === 24 ? 'selected' : ''}>${esc(lb)}</option>`).join('')}</select></label>
        <button class="btn primary" id="wadd">${esc(t('Ekle'))}</button></div>
        <p class="muted" style="font-size:11.5px;margin-top:8px">${esc(t('Taramalar sunucu çalıştığı sürece arka planda yapılır; tarayıcının açık olması gerekmez.'))}</p></div>
      <div class="card" style="margin-top:14px"><div class="card-b" style="padding:0 4px" id="wlist"><div class="empty">${esc(t('Yükleniyor…'))}</div></div></div>
      <div id="whist"></div>`;
    const hLabel = h => ({ 1: t('Saatte bir'), 6: t('6 saat'), 12: t('12 saat'), 24: t('Günde bir'), 72: t('3 gün'), 168: t('Haftada bir') }[h] || t('{n} sa', { n: h }));
    const load = async () => {
      let r;
      try { r = await api('/api/watches'); } catch (e) { $('#wlist', v).innerHTML = `<div class="notice err">${esc(I18N.err(e.message))}</div>`; return; }
      $('#wlist', v).innerHTML = r.watches.length ? `<table class="t"><tr><th></th><th>${esc(t('Hedef'))}</th><th>${esc(t('Aralık'))}</th><th>${esc(t('Son çalışma'))}</th><th>${esc(t('Sonraki'))}</th><th>${esc(t('Durum'))}</th><th class="num">${esc(t('Değişiklik'))}</th><th></th></tr>
        ${r.watches.map(w => `<tr><td>${picon(w.platform)}</td><td class="mono">${esc(w.raw)}</td><td>${esc(hLabel(w.interval_hours))}</td>
          <td class="dim">${w.last_run ? new Date(w.last_run).toLocaleString(I18N.locale) : '—'}</td><td class="dim">${w.enabled && w.next_run ? new Date(w.next_run).toLocaleString(I18N.locale) : '—'}</td>
          <td>${w.last_status ? `<span class="badge ${w.last_status === 'ok' ? '' : 'critical'}">${esc((STATUS[w.last_status] || [0, w.last_status])[1])}</span>` : '—'}</td>
          <td class="num">${w.change_count ? `<b>${w.change_count}</b>` : '0'}</td>
          <td style="white-space:nowrap"><button class="btn sm" data-h="${w.id}">${esc(t('Geçmiş'))}</button> <button class="btn sm" data-run="${w.id}">${esc(t('Şimdi'))}</button>
            <button class="btn sm ghost" data-tog="${w.id}" data-en="${w.enabled ? 1 : 0}">${esc(w.enabled ? t('Duraklat') : t('Sürdür'))}</button> <button class="btn sm ghost danger" data-delw="${w.id}">${esc(t('Sil'))}</button></td></tr>`).join('')}</table>`
        : `<div class="empty">${esc(t('İzlenen hedef yok. Bir tarama sonucundaki “İzle” düğmesiyle ya da yukarıdan ekleyin.'))}</div>`;
      $$('[data-run]', v).forEach(b => b.onclick = async () => { b.disabled = true; b.textContent = '…'; try { await api(`/api/watches/${b.dataset.run}/run`, { method: 'POST' }); toast(t('Tarandı'), 'ok'); } catch (e) { toast(I18N.err(e.message), 'err'); } load(); if (v._hist == b.dataset.run) hist(b.dataset.run); });
      $$('[data-tog]', v).forEach(b => b.onclick = async () => { await api(`/api/watches/${b.dataset.tog}`, { method: 'PATCH', body: JSON.stringify({ enabled: b.dataset.en !== '1' }) }); load(); });
      $$('[data-delw]', v).forEach(b => b.onclick = async () => { if (!confirm(t('İzleme ve geçmişi silinsin mi?'))) return; await api(`/api/watches/${b.dataset.delw}`, { method: 'DELETE' }); $('#whist', v).innerHTML = ''; load(); });
      $$('[data-h]', v).forEach(b => b.onclick = () => hist(b.dataset.h));
    };
    const show = x => x == null ? '—' : (Array.isArray(x) ? x.join(', ') : String(x));
    const hist = async wid => {
      v._hist = wid;
      const r = await api(`/api/watches/${wid}/snapshots`);
      $('#whist', v).innerHTML = `<div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Geçmiş'))}</h3><span class="sub">${esc(t('izleme #{id}', { id: wid }))}</span></div><div class="card-b">
        ${r.snapshots.length ? r.snapshots.map(sn => {
          const d = sn.diff;
          const body = !d ? `<span class="muted">${esc(t('İlk kayıt (karşılaştırma tabanı)'))}</span>`
            : (!d.change_total && !d.nodes_added.length && !d.nodes_removed.length) ? `<span class="muted">${esc(t('Değişiklik yok'))}</span>`
            : `${d.changes.length ? `<table class="t"><tr><th>${esc(t('Alan'))}</th><th>${esc(t('Önceki'))}</th><th>${esc(t('Yeni'))}</th></tr>${d.changes.slice(0, 60).map(c => `<tr><td class="mono">${esc(c.path)}</td><td class="dim">${esc(show(c.old)).slice(0, 200)}</td><td>${esc(show(c.new)).slice(0, 200)}</td></tr>`).join('')}</table>` : ''}
              ${d.nodes_added.length ? `<div style="margin-top:6px"><span class="badge good">${esc(t('Yeni bağlantılar'))}</span> ${d.nodes_added.map(esc).join(', ')}</div>` : ''}
              ${d.nodes_removed.length ? `<div style="margin-top:6px"><span class="badge critical">${esc(t('Kaybolan bağlantılar'))}</span> ${d.nodes_removed.map(esc).join(', ')}</div>` : ''}`;
          return `<div class="snap"><div class="snap-h"><span class="mono">${new Date(sn.at).toLocaleString(I18N.locale)}</span> <span class="badge ${sn.status === 'ok' ? '' : 'critical'}">${esc((STATUS[sn.status] || [0, sn.status])[1])}</span>
            ${d && d.change_total ? `<span class="badge warn">${esc(t('{n} alan değişti', { n: d.change_total }))}</span>` : ''} <span class="muted mono">${esc((sn.sha256 || '').slice(0, 12))}</span></div>${sn.error ? `<div class="notice err">${esc(I18N.err(sn.error))}</div>` : body}</div>`;
        }).join('') : `<div class="empty">${esc(t('Henüz çalışmadı (ilk tarama bir dakika içinde yapılır)'))}</div>`}</div></div>`;
    };
    $('#wadd', v).onclick = async () => {
      const raw = $('#wq', v).value.trim(); if (!raw) { toast(t('Hedef girin'), 'err'); return; }
      try { await api('/api/watches', { method: 'POST', body: JSON.stringify({ platform: $('#wp', v).value, raw, interval_hours: +$('#wh', v).value }) }); $('#wq', v).value = ''; toast(t('Eklendi'), 'ok'); load(); }
      catch (e) { toast(I18N.err(e.message), 'err'); }
    };
    load();
  }

  // ───────────────── Ayarlar ─────────────────
  async function viewSettings(v) {
    setTitle(t('Ayarlar'));
    let st;
    try { st = await api('/api/settings'); } catch (e) { v.innerHTML = `<div class="notice err">${esc(I18N.err(e.message))}</div>`; return; }
    v.innerHTML = `
      <div class="grid g2">
        <div>
        <div class="card" style="margin-bottom:14px"><div class="card-h"><h3>${esc(t('Dil'))}</h3><span class="sub">${I18N.lang === 'tr' ? 'Language' : 'Dil'}</span></div><div class="card-b">
          <div class="seg">${Object.entries(I18N.LANGS).map(([k, x]) => `<button data-lang="${k}" class="${I18N.lang === k ? 'on' : ''}">${esc(x.name)}</button>`).join('')}</div>
        </div></div>
        <div class="card"><div class="card-h"><h3>${esc(t('API anahtarları'))}</h3><span class="sub">${esc(t('sunucuda saklanır, tarayıcıya geri gönderilmez'))}</span></div><div class="card-b">
          ${Object.entries(st.keys).map(([k, x]) => `<div class="keyrow"><div><div>${esc(x.label)}</div><div class="muted mono" style="font-size:11px">${k} · ${x.set ? `${esc(t('ayarlı {hint}', { hint: x.hint }))}${x.source === '.env' ? ' (.env)' : ''}` : esc(t('yok'))}</div></div>
            <input class="input" type="password" data-k="${k}" placeholder="${esc(x.set ? t('değiştirmek için yeni değer') : t('değer'))}" autocomplete="off">
            <button class="btn sm" data-save="${k}">${esc(t('Kaydet'))}</button>${x.source === 'ayarlar' ? `<button class="btn sm ghost danger" data-clr="${k}">${esc(t('Sil'))}</button>` : '<span></span>'}</div>`).join('')}
        </div></div>
        </div>
        <div>
          <div class="card"><div class="card-h"><h3>Proxy / Tor</h3></div><div class="card-b" style="display:flex;flex-direction:column;gap:10px">
            <div class="seg">${[['none', t('Kapalı')], ['tor', 'Tor'], ['custom', t('Özel proxy')], ['list', t('Proxy listesi')]].map(([k, lb]) => `<button data-pm="${k}" class="${st.proxy.mode === k ? 'on' : ''}">${esc(lb)}</button>`).join('')}</div>
            <label class="field" id="purl-row" style="${st.proxy.mode === 'list' ? 'display:none' : ''}">${esc(t('Adres'))}<input class="input" id="purl" value="${esc(st.proxy.url || '')}" placeholder="${esc(st.proxy.mode === 'tor' ? t('socks5h://127.0.0.1:9050 (varsayılan)') : t('http://127.0.0.1:8080 veya socks5h://…'))}"></label>
            <label class="field" id="plist-row" style="${st.proxy.mode === 'list' ? '' : 'display:none'}">${esc(t('Proxy listesi (her satıra bir tane)'))}
              <textarea class="input" id="plist" rows="5" spellcheck="false" placeholder="http://kullanici:parola@1.2.3.4:8080&#10;socks5h://5.6.7.8:1080">${esc((st.proxies || []).join('\n'))}</textarea></label>
            <div style="display:flex;gap:8px"><button class="btn sm primary" id="psave">${esc(t('Kaydet'))}</button><button class="btn sm" id="ptest">${esc(t('Bağlantıyı test et'))}</button><span class="muted" id="pres" style="align-self:center;font-size:12px"></span></div>
            <p class="muted" style="font-size:11.5px">${esc(t('Tüm araçların istekleri bu adres üzerinden gider. Tor için Tor servisinin çalışıyor olması gerekir.'))}</p>
            <p class="muted" style="font-size:11.5px" id="plist-note" style="${st.proxy.mode === 'list' ? '' : 'display:none'}">${esc(t('Liste modunda her tarama sırayla farklı bir proxy kullanır (round-robin) — rate-limit’i dağıtır. Test ilk proxy’yi dener.'))}</p>
          </div></div>
          <div class="card" style="margin-top:14px"><div class="card-h"><h3>${esc(t('Hız'))}</h3></div><div class="card-b" style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
            <label class="field">${esc(t('Paralel tarama'))}<input class="input" id="wk" type="number" min="1" max="16" value="${st.workers}" style="width:100px"></label>
            <label class="field">${esc(t('İstek arası bekleme (sn)'))}<input class="input" id="rd" type="number" min="0" max="10" step="0.5" value="${st.request_delay}" style="width:120px"></label>
            <button class="btn primary" id="rsave">${esc(t('Kaydet'))}</button>
            <p class="muted" style="font-size:11.5px;width:100%">${esc(t('Bekleme süresi yeni modüllerde (Telegram, Keybase, Steam, Gravatar, GitLab, HN, Stack Exchange, Wayback) uygulanır.'))}</p>
          </div></div>
        </div>
      </div>`;
    let mode = st.proxy.mode;
    $$('[data-lang]', v).forEach(b => b.onclick = () => I18N.set(b.dataset.lang));
    const put = async body => { try { await api('/api/settings', { method: 'PUT', body: JSON.stringify(body) }); toast(t('Kaydedildi'), 'ok'); S.status = await api('/api/socmint/status').catch(() => S.status); return true; } catch (e) { toast(I18N.err(e.message), 'err'); return false; } };
    $$('[data-save]', v).forEach(b => b.onclick = async () => { const k = b.dataset.save; const val = $(`[data-k="${k}"]`, v).value.trim(); if (!val) { toast(t('Değer girin'), 'err'); return; } if (await put({ keys: { [k]: val } })) viewSettings(v); });
    $$('[data-clr]', v).forEach(b => b.onclick = async () => { if (await put({ keys: { [b.dataset.clr]: '' } })) viewSettings(v); });
    $$('[data-pm]', v).forEach(b => b.onclick = () => {
      mode = b.dataset.pm; $$('[data-pm]', v).forEach(x => x.classList.toggle('on', x === b));
      const isList = mode === 'list';
      $('#purl-row', v).style.display = isList ? 'none' : '';
      $('#plist-row', v).style.display = isList ? '' : 'none';
      const note = $('#plist-note', v); if (note) note.style.display = isList ? '' : 'none';
    });
    $('#psave', v).onclick = async () => {
      const body = mode === 'list'
        ? { proxies: $('#plist', v).value, proxy: { mode: 'list' } }
        : { proxy: { mode, url: $('#purl', v).value.trim() } };
      if (await put(body)) viewSettings(v);
    };
    $('#ptest', v).onclick = async () => {
      $('#pres', v).textContent = t('Test ediliyor…');
      try { const r = await api('/api/settings/test-proxy', { method: 'POST' }); const er = String(r.error || ''); $('#pres', v).title = er;
        $('#pres', v).textContent = r.ok ? t('Çıkış IP: {ip}', { ip: r.ip }) + (r.tor ? ' · ' + t('Tor üzerinden') : '')
          : /refused|Failed to establish|SOCKS|ProxyError/i.test(er) ? t('Proxy adresine bağlanılamadı — servis çalışıyor mu?') : /timed? ?out/i.test(er) ? t('Zaman aşımı') : t('Başarısız: {err}', { err: I18N.err(er.slice(0, 100)) }); }
      catch (e) { $('#pres', v).textContent = I18N.err(e.message); }
    };
    $('#rsave', v).onclick = () => put({ workers: +$('#wk', v).value, request_delay: +$('#rd', v).value });
  }

  // ───────────────── Başlangıç ─────────────────
  window.addEventListener('hashchange', () => render());
  async function boot() {
    render();
    try { S.status = await api('/api/socmint/status'); } catch (e) { toast(t('Sunucuya ulaşılamıyor'), 'err'); }
    new Set(S.scans.filter(s => s.status === 'running' && s.jobId).map(s => s.jobId)).forEach(poll);
    render();
  }
  window.SOCMINT = { S, startScan, mergedGraph, matchPairs };
  boot();
})();
