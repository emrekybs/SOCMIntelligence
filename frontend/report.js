/* SOCMIntelligence — HTML / PDF rapor üretimi.
   Tek dosyalık, dış bağımlılığı olmayan HTML üretir (grafikler ve ilişki grafiği gömülü SVG).
   PDF: aynı rapor yazdırma penceresinde açılır, "PDF olarak kaydet" seçilir. */
(function () {
  'use strict';
  const esc = Charts.esc, fmt = Charts.fmt;

  const LIGHT_NODE = {
    person: '#2f6fbd', username: '#c56a45', email: '#1f9c95', domain: '#d99a2b', community: '#6a5cc4',
    hashtag: '#8a72d0', content: '#7d828a', artifact: '#2f9a52', breach: '#d14b4b', ip: '#d14b4b',
  };
  const EDGE_COL = { identity: '#6b8fbe', interaction: '#c56a45', content: '#9aa0a8', mod: '#6a5cc4', same: '#2f9a52', manual: '#b8862b' };
  const edgeFamily = ty => ['owns', 'linked_to', 'registered_to', 'member_of', 'verified', 'follows'].includes(ty) ? 'identity'
    : ['commented', 'mentioned', 'related', 'friend', 'replied', 'forwarded'].includes(ty) ? 'interaction' : ty === 'moderates' ? 'mod'
    : ty === 'same_person' ? 'same' : ty === 'manual' ? 'manual' : 'content';
  const ANN_COL = { verified: '#3d9150', suspect: '#b8862b', dismissed: '#8a9099' };

  // İlişki grafiği: kuvvet yerleşimini önceden hesaplayıp statik SVG çiz
  function graphSvg(graph, width = 900, height = 560, ann = {}) {
    const nodes = (graph.nodes || []).map(n => ({ ...n }));
    if (!nodes.length) return `<div class="empty">${esc(t('Düğüm yok'))}</div>`;
    const ids = new Set(nodes.map(n => n.id));
    const links = (graph.edges || []).filter(e => ids.has(e.source?.id || e.source) && ids.has(e.target?.id || e.target))
      .map(e => ({ source: e.source?.id || e.source, target: e.target?.id || e.target, type: e.type, weight: e.weight }));
    const R = ty => ({ person: 16, community: 13, domain: 12, breach: 13 }[ty] || 10);
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(70).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-260).distanceMax(420))
      .force('collide', d3.forceCollide().radius(d => R(d.type) + 14))
      .force('x', d3.forceX().strength(0.05)).force('y', d3.forceY().strength(0.05)).stop();
    for (let i = 0; i < 320; i++) sim.tick();
    const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
    const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 60, y0 = Math.min(...ys) - 40, y1 = Math.max(...ys) + 50;
    const vb = `${x0} ${y0} ${x1 - x0} ${y1 - y0}`;
    const h = Math.min(height, Math.max(260, width * (y1 - y0) / (x1 - x0)));
    let out = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}" width="100%" height="${Math.round(h)}" font-family="${Charts.FONT}">`;
    links.forEach(l => {
      const s = l.source, tg = l.target;
      const w = Math.min(4, 1 + (l.weight > 1 ? Math.log2(l.weight) * 0.5 : 0));
      const fam = edgeFamily(l.type);
      out += `<line x1="${s.x.toFixed(1)}" y1="${s.y.toFixed(1)}" x2="${tg.x.toFixed(1)}" y2="${tg.y.toFixed(1)}" stroke="${EDGE_COL[fam]}" stroke-width="${w}" ${fam === 'content' ? 'stroke-dasharray="4,3"' : fam === 'same' ? 'stroke-dasharray="8,4"' : ''} stroke-opacity="0.85"/>`;
    });
    const labelAll = nodes.length <= 70;
    nodes.forEach(n => {
      const c = LIGHT_NODE[n.type] || '#7d828a', r = R(n.type);
      const icon = (GraphMeta.NODE[n.type] || {}).icon || '?';
      out += `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r}" fill="${d3.interpolateRgb('#ffffff', c)(0.16)}" stroke="${c}" stroke-width="1.6"/>`;
      if ((n.sources || []).length > 1) out += `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r + 4}" fill="none" stroke="${c}" stroke-dasharray="3,2"/>`;
      const a = (ann[n.id] || {}).status;
      if (a) out += `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r + 8}" fill="none" stroke="${ANN_COL[a]}" stroke-width="2.2" ${a === 'dismissed' ? 'stroke-dasharray="2,3"' : a === 'suspect' ? 'stroke-dasharray="4,3"' : ''}/>`;
      out += `<text x="${n.x.toFixed(1)}" y="${n.y.toFixed(1)}" dy="0.35em" text-anchor="middle" font-size="${r > 13 ? 11 : 9}" font-weight="700" fill="${c}" font-family="${Charts.MONO}">${esc(icon)}</text>`;
      if (labelAll || n.type === 'person' || (n.sources || []).length > 1) {
        const l = String(n.label || ''); out += `<text x="${n.x.toFixed(1)}" y="${(n.y + r + 11).toFixed(1)}" text-anchor="middle" font-size="9" fill="#4d535b">${esc(l.length > 26 ? l.slice(0, 24) + '…' : l)}</text>`;
      }
    });
    return out + '</svg>';
  }

  function graphLegend(graph) {
    const types = [...new Set((graph.nodes || []).map(n => n.type))];
    return `<div class="legend">${types.map(ty => `<span><i style="background:${LIGHT_NODE[ty] || '#7d828a'}"></i>${esc((GraphMeta.NODE[ty] || {}).label || ty)}</span>`).join('')}
      <span><i style="background:${EDGE_COL.identity}"></i>${esc(t('kimlik bağı'))}</span><span><i style="background:${EDGE_COL.interaction}"></i>${esc(t('etkileşim (yorum, bahsetme)'))}</span>
      <span><i style="background:${EDGE_COL.content}"></i>${esc(t('içerik / etiket / aktivite'))}</span>
      ${(graph.edges || []).some(e => e.type === 'same_person') ? `<span><i style="background:${EDGE_COL.same}"></i>${esc(t('aynı kişi olabilir'))}</span>` : ''}
      ${(graph.edges || []).some(e => e.type === 'manual' || e.manual) ? `<span><i style="background:${EDGE_COL.manual}"></i>${esc(t('analist bağlantısı'))}</span>` : ''}</div>`;
  }

  function cell(c) {
    if (c && typeof c === 'object') return c.href ? `<a href="${esc(c.href)}">${esc(c.text ?? c.href)}</a>` : esc(c.text);
    return esc(c ?? '—');
  }
  function findingsHtml(sections) {
    return sections.filter(Boolean).map(sec => {
      if (sec.kind === 'kv' && sec.rows.length) return `<h4>${esc(sec.title)}</h4><table class="kv">${sec.rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</table>`;
      if (sec.kind === 'list' && (sec.items.length || sec.note)) return `<h4>${esc(sec.title)}</h4>${sec.note ? `<p class="muted">${esc(sec.note)}</p>` : ''}<ul>${sec.items.map(i => `<li>${i.href ? `<a href="${esc(i.href)}">${esc(i.text)}</a>` : esc(i.text)}${i.tag ? ` <span class="muted">· ${esc(i.tag)}</span>` : ''}</li>`).join('')}</ul>`;
      if (sec.kind === 'table' && sec.rows.length) {
        const rows = sec.rows.slice(0, 60);
        return `<h4>${esc(sec.title)} <span class="muted">(${sec.rows.length})</span></h4><table class="t"><tr>${sec.cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${cell(c)}</td>`).join('')}</tr>`).join('')}</table>${sec.rows.length > 60 ? `<p class="muted">${esc(t('İlk {n} kayıt gösterildi.', { n: 60 }))}</p>` : ''}`;
      }
      return '';
    }).join('');
  }

  function scanSection(s, i, ann = {}) {
    const P = SOC.PLATFORMS[s.platform];
    const d = s.data || {};
    const h = P.header(d) || {};
    const kpis = (P.kpis(d) || []).filter(Boolean);
    const specs = Charts.withTheme('light', () => (P.charts(d) || []))
      .filter(c => c && (c.type === 'heatmap' ? !c.empty : (c.data && c.data.length && c.data.some(x => x.value > 0))));
    const charts = specs.map(c => `<figure class="${c.wide || c.type === 'heatmap' ? 'wide' : ''}"><figcaption><b>${esc(c.title)}</b>${c.sub ? `<br><span class="muted">${esc(c.sub)}</span>` : ''}</figcaption>
      ${Charts.staticSvg(c, c.wide || c.type === 'heatmap' ? 720 : 340)}</figure>`).join('');
    return `<section class="scan">
      <div class="scan-h"><span class="plat">${esc(P.name)}</span><h2>${i + 1}. ${esc(h.title || s.value)}</h2>
        <div class="muted">${h.url ? `<a href="${esc(h.url)}">${esc(h.handle || h.url)}</a>` : esc(h.handle || '')} · ${esc(t('Girdi'))}: <code>${esc(s.raw)}</code> · ${new Date(s.at).toLocaleString(I18N.locale)}</div>
        ${(h.badges || []).length ? `<div class="badges">${h.badges.map(b => `<span>${esc(b.t)}</span>`).join('')}</div>` : ''}
        ${h.bio ? `<p class="bio">${esc(h.bio)}</p>` : ''}</div>
      ${kpis.length ? `<table class="kpi"><tr>${kpis.map(k => `<td><div class="k">${esc(k.k)}</div><div class="v">${esc(k.v ?? '—')}</div>${k.s ? `<div class="s">${esc(k.s)}</div>` : ''}</td>`).join('')}</tr></table>` : ''}
      ${charts ? `<h3>${esc(t('Grafikler'))}</h3><div class="charts">${charts}</div>` : ''}
      ${s.evidence ? `<p class="muted ev">SHA-256 <code>${esc(s.evidence.sha256)}</code> · ${esc(t('toplandı {v}', { v: s.evidence.collected_at ?? '' }))}</p>` : ''}
      ${s.graph && s.graph.nodes && s.graph.nodes.length ? `<h3>${esc(t('İlişki grafiği'))} <span class="muted">(${esc(t('{n} düğüm', { n: s.graph.nodes.length }))}, ${esc(t('{n} ilişki', { n: s.graph.edges.length }))})</span></h3>${graphSvg(s.graph, 720, 460, ann)}${graphLegend(s.graph)}` : ''}
      <h3>${esc(t('Bulgular'))}</h3>${findingsHtml(P.findings(d) || [])}
    </section>`;
  }

  const CSS = `
    @page{size:A4;margin:14mm}
    *{box-sizing:border-box}
    html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
    svg{break-inside:avoid}
    body{font:12px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#15181c;background:#fff;margin:0;padding:28px 36px;max-width:1000px}
    a{color:#2a5d94;text-decoration:none;word-break:break-all}
    h1{font-size:22px;margin:0 0 2px}h2{font-size:17px;margin:4px 0}h3{font-size:13.5px;margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid #e6e5df}
    h4{font-size:12px;margin:14px 0 6px}
    .muted{color:#7d828a}code{font:11px ui-monospace,Menlo,Consolas,monospace;background:#f3f3f0;padding:1px 4px;border-radius:3px}
    .head{border-bottom:2px solid #15181c;padding-bottom:12px;margin-bottom:18px}
    .brand{font-weight:600;color:#4d535b;font-size:12px}
    table{border-collapse:collapse;width:100%}
    table.meta td{padding:3px 12px 3px 0;vertical-align:top}table.meta td:first-child{color:#7d828a;width:130px}
    table.t th,table.t td{border-bottom:1px solid #e6e5df;padding:4px 6px;text-align:left;vertical-align:top;font-size:11px;word-break:break-word}
    table.t th{color:#7d828a;font-weight:500}
    table.kv th{color:#7d828a;font-weight:400;text-align:left;width:32%;padding:3px 8px 3px 0;vertical-align:top}table.kv td{padding:3px 0;word-break:break-word}
    table.kv tr{border-bottom:1px solid #f0efec}
    table.kpi{table-layout:fixed;margin:10px 0}table.kpi td{border:1px solid #e6e5df;padding:6px 8px;vertical-align:top}
    table.kpi .k{color:#7d828a;font-size:10.5px}table.kpi .v{font-size:15px;font-weight:600}table.kpi .s{color:#7d828a;font-size:10px}
    .scan{page-break-before:always;padding-top:6px}
    .scan-h .plat{font-size:11px;color:#7d828a}
    code.hash{font-size:9.5px;word-break:break-all}.ev{font-size:10.5px;word-break:break-all}
    .badges span{display:inline-block;border:1px solid #d6d5cf;border-radius:3px;padding:0 6px;margin:4px 4px 0 0;font-size:10.5px}
    .bio{white-space:pre-line;color:#4d535b}
    .charts{display:flex;flex-wrap:wrap;gap:14px}
    figure{margin:0;width:calc(50% - 7px);break-inside:avoid;border:1px solid #eeede8;border-radius:4px;padding:8px}
    figure.wide{width:100%}figcaption{margin-bottom:6px}
    figure svg{max-width:100%;height:auto}
    ul{margin:0;padding-left:18px}li{margin:2px 0}
    .legend{display:flex;flex-wrap:wrap;gap:12px;font-size:10.5px;color:#4d535b;margin:6px 0}.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
    .notes{white-space:pre-wrap;border-left:3px solid #3d6ea5;padding:6px 12px;background:#f7f7f5}
    .empty{color:#7d828a}
    .foot{margin-top:30px;color:#7d828a;font-size:10.5px;border-top:1px solid #e6e5df;padding-top:8px}
    @media print{body{padding:0}a{color:#15181c}}
  `;

  function build({ caseInfo = null, scans = [], notes = '', ann = {}, manual = { nodes: [], edges: [] }, matches: pairs = [] }) {
    const ok = scans.filter(s => s.status === 'ok' && s.data);
    const merged = window.SOCMINT.mergedGraph(ok, { manual: false });
    const ids = new Set(merged.nodes.map(n => n.id));
    (manual.nodes || []).forEach(n => { if (!ids.has(n.id)) { merged.nodes.push({ ...n, sources: [t('Analist')] }); ids.add(n.id); } });
    (manual.edges || []).forEach(e => { if (ids.has(e.source) && ids.has(e.target)) merged.edges.push({ ...e }); });
    pairs.forEach(p => {
      const a = Signals.personOf(p.A), b = Signals.personOf(p.B);
      if (a && b && a.id !== b.id && ids.has(a.id) && ids.has(b.id)) merged.edges.push({ source: a.id, target: b.id, type: 'same_person', weight: p.score });
    });
    const annRows = Object.entries(ann).filter(([, a]) => a.status || a.note);
    const nodeLabel = id => (merged.nodes.find(n => n.id === id) || {}).label || id;
    const ANN_TR = { verified: t('Doğrulandı'), suspect: t('Şüpheli'), dismissed: t('Elendi') };
    const matches = merged.nodes.filter(n => n.sources.length > 1);
    const title = caseInfo ? caseInfo.title : t('Oturum raporu');
    const conf = { low: t('Düşük'), medium: t('Orta'), high: t('Yüksek') };
    const STATUS = { ok: t('Başarılı'), not_found: t('Bulunamadı'), private: t('Gizli'), rate_limited: t('Hız sınırı'), error: t('Hata'), running: t('Sürüyor') };
    const dt = v => new Date(v).toLocaleString(I18N.locale);
    const now = new Date();
    return `<!DOCTYPE html><html lang="${I18N.lang}"><head><meta charset="utf-8"><title>${esc(title)} — SOCMIntelligence</title><style>${CSS}</style></head><body>
      <div class="head"><div class="brand">SOCMIntelligence · ${esc(t('Soruşturma raporu'))}</div><h1>${esc(title)}</h1>
        <table class="meta">
          ${caseInfo ? `<tr><td>${esc(t('Vaka no'))}</td><td><code>${esc(caseInfo.case_id)}</code></td></tr>
          ${caseInfo.target ? `<tr><td>${esc(t('Hedef'))}</td><td>${esc(caseInfo.target)}</td></tr>` : ''}
          <tr><td>${esc(t('Analist'))}</td><td>${esc(caseInfo.analyst || '—')}</td></tr><tr><td>${esc(t('Güven düzeyi'))}</td><td>${esc(conf[caseInfo.confidence] || caseInfo.confidence || '—')}</td></tr>
          <tr><td>${esc(t('Vaka açılışı'))}</td><td>${caseInfo.created_at ? dt(caseInfo.created_at) : '—'}</td></tr>` : ''}
          <tr><td>${esc(t('Rapor tarihi'))}</td><td>${dt(now)}</td></tr>
          <tr><td>${esc(t('Platformlar'))}</td><td>${esc([...new Set(ok.map(s => SOC.PLATFORMS[s.platform].name))].join(', ') || '—')}</td></tr>
        </table></div>
      <h3>${esc(t('Özet'))}</h3>
      <table class="t"><tr><th>#</th><th>Platform</th><th>${esc(t('Girdi'))}</th><th>${esc(t('Durum'))}</th><th>${esc(t('Tarih'))}</th></tr>
        ${scans.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(SOC.PLATFORMS[s.platform].name)}</td><td><code>${esc(s.raw)}</code></td><td>${esc(STATUS[s.status] || s.status)}${s.error ? ` <span class="muted">— ${esc(String(s.error).slice(0, 120))}</span>` : ''}</td><td>${dt(s.at)}</td></tr>`).join('')}
      </table>
      <p class="muted">${esc([t('{n} başarılı tarama', { n: ok.length }), t('{n} varlık', { n: merged.nodes.length }), t('{n} ilişki', { n: merged.edges.length }), t('{n} taramalar arası ortak varlık', { n: matches.length })].join(' · '))}</p>
      ${notes ? `<h3>${esc(t('Analist notları'))}</h3><div class="notes">${esc(notes)}</div>` : ''}
      ${matches.length ? `<h3>${esc(t('Taramalar arası ortak varlıklar'))}</h3><table class="t"><tr><th>${esc(t('Varlık'))}</th><th>${esc(t('Tür'))}</th><th>${esc(t('Görüldüğü taramalar'))}</th></tr>
        ${matches.map(n => `<tr><td>${esc(n.label)}</td><td>${esc((GraphMeta.NODE[n.type] || {}).label || n.type)}</td><td>${n.sources.map(esc).join('<br>')}</td></tr>`).join('')}</table>` : ''}
      ${pairs.length ? `<h3>${esc(t('Kimlik eşleştirme'))}</h3><table class="t"><tr><th>${esc(t('Hesap'))}</th><th>${esc(t('Hesap'))}</th><th>${esc(t('Skor'))}</th><th>${esc(t('Karar'))}</th><th>${esc(t('Gerekçe'))}</th></tr>
        ${pairs.map(p => `<tr><td>${esc(SOC.PLATFORMS[p.A.platform].name)}: ${esc(p.A.value)}</td><td>${esc(SOC.PLATFORMS[p.B.platform].name)}: ${esc(p.B.value)}</td><td>${p.score}</td>
          <td>${esc(p.decision === 'confirmed' ? t('Analist onayladı') : t('Otomatik'))}</td><td>${p.reasons.map(r => esc(r.txt)).join('<br>')}</td></tr>`).join('')}</table>` : ''}
      ${annRows.length ? `<h3>${esc(t('Analist işaretleri'))}</h3><table class="t"><tr><th>${esc(t('Varlık'))}</th><th>${esc(t('İşaret'))}</th><th>${esc(t('Not'))}</th></tr>
        ${annRows.map(([id, a]) => `<tr><td>${esc(nodeLabel(id))}</td><td>${esc(ANN_TR[a.status] || '—')}</td><td>${esc(a.note || '')}</td></tr>`).join('')}</table>` : ''}
      ${(manual.nodes || []).length ? `<h3>${esc(t('Analistin eklediği varlıklar'))}</h3><table class="t"><tr><th>${esc(t('Varlık'))}</th><th>${esc(t('Tür'))}</th><th>${esc(t('Not'))}</th></tr>
        ${manual.nodes.map(n => `<tr><td>${esc(n.label)}</td><td>${esc((GraphMeta.NODE[n.type] || {}).label || n.type)}</td><td>${esc((n.meta || {}).Not || '')}</td></tr>`).join('')}</table>` : ''}
      ${ok.some(s => s.evidence) ? `<h3>${esc(t('Delil bütünlüğü'))}</h3><p class="muted">${esc(t('Her taramanın ham verisi, toplandığı anda kanonik JSON olarak SHA-256 ile özetlenmiştir. Veri değiştirilirse özet tutmaz.'))}</p>
        <table class="t"><tr><th>#</th><th>Platform</th><th>${esc(t('Girdi'))}</th><th>${esc(t('Toplanma (UTC)'))}</th><th>SHA-256</th></tr>
        ${ok.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(SOC.PLATFORMS[s.platform].name)}</td><td><code>${esc(s.raw)}</code></td><td style="white-space:nowrap">${esc(s.evidence ? String(s.evidence.collected_at).replace('T', ' ').replace(/(\.\d+)?\+00:00$/, '') : '—')}</td><td><code class="hash">${esc(s.evidence ? s.evidence.sha256 : '—')}</code></td></tr>`).join('')}</table>` : ''}
      ${merged.nodes.length ? `<h3>${esc(t('Birleşik ilişki grafiği'))}</h3>${graphSvg(merged, 900, 620, ann)}${graphLegend(merged)}
        <p class="muted">${esc(t('Kesikli dış halka: birden fazla taramada görülen varlık. Kalın çizgi: yüksek sayı (yorum, gönderi, bahsetme).'))}</p>` : ''}
      ${ok.map((s, i) => scanSection(s, i, ann)).join('')}
      <div class="foot">${esc(t('SOCMIntelligence tarafından {date} tarihinde oluşturuldu. Saatler UTC’dir. “Tahmini” olarak işaretlenen değerler (ör. TikTok büyüme grafiği) gerçek geçmiş veri değildir.', { date: dt(now) }))}</div>
    </body></html>`;
  }

  function fileBase(caseInfo) {
    const d = new Date().toISOString().slice(0, 10);
    return caseInfo ? t('{id}_rapor_{d}', { id: caseInfo.case_id, d }) : t('socmintelligence_rapor_{d}', { d });
  }
  function html(opts) {
    const doc = build(opts);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([doc], { type: 'text/html;charset=utf-8' }));
    a.download = fileBase(opts.caseInfo) + '.html'; document.body.appendChild(a); a.click(); a.remove();
  }
  function pdf(opts) {
    const doc = build(opts);
    const w = window.open('', '_blank');
    if (!w) { alert(t('Açılır pencere engellendi. Tarayıcıda bu site için açılır pencerelere izin verin.')); return; }
    w.document.open(); w.document.write(doc.replace('</body>', `<script>document.title=${JSON.stringify(fileBase(opts.caseInfo))};window.onload=()=>setTimeout(()=>window.print(),300)<\/script></body>`)); w.document.close();
  }

  window.Report = { build, html, pdf, graphSvg };
})();
