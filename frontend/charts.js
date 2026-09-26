/* SOCMIntelligence — grafik çizimleri (D3) + PNG dışa aktarma.
   Tüm renkler SVG özniteliği olarak yazılır: PNG çıktısı ekrandakiyle birebir aynı. */
(function () {
  'use strict';
  const DARK = {
    surface: '#111823', grid: '#1b2531', axis: '#2c3846',
    ink1: '#e2e8f0', ink2: '#9aa7b6', ink3: '#6b7889',
    series: '#5f8ac2', seriesHover: '#86a8ce',
    pos: '#54a05f', neu: '#5f6b79', neg: '#c25a5a',
    cat: ['#5f8ac2', '#4ba39d', '#8f83d6', '#c7a24e', '#cf7d8f', '#5fa46b', '#c9805f'],
    seqZero: '#161f2b', seqLo: '#2b4a6f', seqHi: '#a2c1e0',
  };
  // Rapor (HTML/PDF) icin acik tema
  const LIGHT = {
    surface: '#ffffff', grid: '#e6e5df', axis: '#c3c2b7',
    ink1: '#15181c', ink2: '#4d535b', ink3: '#7d828a',
    series: '#3d6ea5', seriesHover: '#3d6ea5',
    pos: '#3d6ea5', neu: '#a9aca8', neg: '#c04848',
    cat: ['#2f6fbd', '#1f9c95', '#6a5cc4', '#d99a2b', '#d4708a', '#2f9a52', '#c56a45'],
    seqZero: '#f0efec', seqLo: '#cde2fb', seqHi: '#184f95',
  };
  const C = { ...DARK };
  function withTheme(name, fn) {
    const saved = { ...C };
    Object.assign(C, name === 'light' ? LIGHT : DARK);
    try { return fn(); } finally { Object.assign(C, saved); }
  }
  const FONT = 'system-ui,-apple-system,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif';
  const MONO = 'ui-monospace,SFMono-Regular,Menlo,Consolas,monospace';
  const nf = new Intl.NumberFormat(I18N.locale);
  const nfc = new Intl.NumberFormat(I18N.locale, { notation: 'compact', maximumFractionDigits: 1 });
  const fmt = v => (v == null || isNaN(v)) ? '—' : (Math.abs(v) >= 10000 ? nfc.format(v) : nf.format(v));

  // ── Tooltip ───────────────────────────────────────────
  let tip;
  function tipEl() {
    if (!tip) { tip = document.createElement('div'); tip.className = 'tooltip'; document.body.appendChild(tip); }
    return tip;
  }
  function showTip(e, html) {
    const tp = tipEl(); tp.innerHTML = html; tp.style.display = 'block';
    const r = tp.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tp.style.left = x + 'px'; tp.style.top = y + 'px';
  }
  function hideTip() { if (tip) tip.style.display = 'none'; }
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function base(el, h) {
    el.innerHTML = '';
    const w = Math.max(260, el.clientWidth || 400);
    const svg = d3.select(el).append('svg')
      .attr('xmlns', 'http://www.w3.org/2000/svg')
      .attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`)
      .attr('font-family', FONT).attr('font-size', 11);
    return { svg, w, h };
  }
  function rounded(x, y, w, h, r, dir) { // dir: 'up' (üstte yuvarlak) | 'right'
    r = Math.max(0, Math.min(r, dir === 'up' ? w / 2 : h / 2, dir === 'up' ? h : w));
    if (dir === 'up') return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }

  // ── Dikey çubuk (saat / gün dağılımı) ──────────────────
  function bar(el, spec) {
    const data = spec.data || [];
    const { svg, w, h } = base(el, spec.height || 190);
    const m = { t: 10, r: 6, b: 24, l: 36 };
    const x = d3.scaleBand().domain(data.map(d => d.label)).range([m.l, w - m.r]).padding(0.18);
    const max = d3.max(data, d => d.value) || 1;
    const y = d3.scaleLinear().domain([0, max]).nice().range([h - m.b, m.t]);
    const g = svg.append('g');
    y.ticks(4).forEach(tk => {
      g.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', y(tk)).attr('y2', y(tk)).attr('stroke', C.grid);
      g.append('text').attr('x', m.l - 6).attr('y', y(tk)).attr('dy', '0.32em').attr('text-anchor', 'end')
        .attr('fill', C.ink3).attr('font-family', MONO).attr('font-size', 10).text(fmt(tk));
    });
    g.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', C.axis);
    const every = Math.ceil(data.length / Math.max(1, Math.floor((w - m.l) / 34)));
    data.forEach((d, i) => {
      if (i % every === 0) g.append('text').attr('x', x(d.label) + x.bandwidth() / 2).attr('y', h - m.b + 15)
        .attr('text-anchor', 'middle').attr('fill', C.ink3).attr('font-size', 10).attr('font-family', MONO).text(d.label);
    });
    const peak = d3.max(data, d => d.value);
    let peakDone = false;
    data.forEach(d => {
      const bh = Math.max(0, y(0) - y(d.value));
      const p = g.append('path').attr('d', d.value > 0 ? rounded(x(d.label), y(d.value), x.bandwidth(), bh, 3, 'up') : '')
        .attr('fill', C.series);
      // Geniş hit alanı
      g.append('rect').attr('x', x(d.label)).attr('y', m.t).attr('width', x.bandwidth()).attr('height', h - m.b - m.t)
        .attr('fill', 'transparent')
        .on('mousemove', e => { p.attr('fill', C.seriesHover); showTip(e, `<div class="tk">${esc(spec.xName || '')} ${esc(d.full || d.label)}</div><b>${nf.format(d.value)}</b> ${esc(spec.unit || '')}`); })
        .on('mouseleave', () => { p.attr('fill', C.series); hideTip(); });
      if (spec.labelPeak !== false && d.value === peak && peak > 0 && !peakDone) {
        peakDone = true;
        g.append('text').attr('x', x(d.label) + x.bandwidth() / 2).attr('y', y(d.value) - 4).attr('text-anchor', 'middle')
          .attr('fill', C.ink2).attr('font-size', 10).attr('font-family', MONO).text(fmt(d.value));
      }
    });
  }

  // ── Yatay çubuk (sıralama: en çok yorum yapanlar vb.) ───
  function hbar(el, spec) {
    let data = (spec.data || []).filter(d => d && d.label != null);
    if (!spec.keepOrder) data = [...data].sort((a, b) => (b.value || 0) - (a.value || 0));
    data = data.slice(0, spec.limit || 12);
    const rowH = 24;
    const h = Math.max(60, data.length * rowH + 16);
    const { svg, w } = base(el, h);
    const labelW = Math.min(spec.labelWidth || 150, w * 0.42);
    const valW = 58;
    const max = d3.max(data, d => d.value) || 1;
    const x = d3.scaleLinear().domain([0, max]).range([0, Math.max(10, w - labelW - valW - 10)]);
    const g = svg.append('g').attr('transform', 'translate(0,8)');
    data.forEach((d, i) => {
      const y = i * rowH;
      const lbl = String(d.label);
      const maxChars = Math.floor(labelW / 6.6);
      g.append('text').attr('x', labelW - 8).attr('y', y + rowH / 2).attr('dy', '0.32em').attr('text-anchor', 'end')
        .attr('fill', C.ink2).attr('font-size', 11.5).text(lbl.length > maxChars ? lbl.slice(0, maxChars - 1) + '…' : lbl);
      const bw = Math.max(d.value > 0 ? 2 : 0, x(d.value));
      const base = d.color || (spec.mono ? C.series : C.cat[i % C.cat.length]);
      let hov; try { hov = d3.color(base).brighter(0.45).formatHex(); } catch (e) { hov = C.seriesHover; }
      const p = g.append('path').attr('d', bw ? rounded(labelW, y + 5, bw, rowH - 10, 3, 'right') : '').attr('fill', base);
      g.append('text').attr('x', labelW + bw + 6).attr('y', y + rowH / 2).attr('dy', '0.32em')
        .attr('fill', C.ink1).attr('font-size', 11).attr('font-family', MONO).text(d.display ?? fmt(d.value));
      g.append('rect').attr('x', 0).attr('y', y).attr('width', w).attr('height', rowH).attr('fill', 'transparent')
        .style('cursor', d.href ? 'pointer' : 'default')
        .on('mousemove', e => { p.attr('fill', hov); showTip(e, `<b>${esc(lbl)}</b><br>${nf.format(d.value)} ${esc(spec.unit || '')}${d.sub ? `<div class="tk">${esc(d.sub)}</div>` : ''}`); })
        .on('mouseleave', () => { p.attr('fill', base); hideTip(); })
        .on('click', () => { if (d.href) window.open(d.href, '_blank', 'noopener'); });
    });
    if (!data.length) el.innerHTML = `<div class="empty">${esc(t('Veri yok'))}</div>`;
  }

  // ── %100 yığılmış yatay çubuk (duygu analizi, medya türü) ─
  function stack(el, spec) {
    const parts = (spec.data || []).filter(d => d.value > 0);
    const total = d3.sum(parts, d => d.value);
    const { svg, w } = base(el, 74);
    if (!total) { el.innerHTML = `<div class="empty">${esc(t('Veri yok'))}</div>`; return; }
    let x = 0; const bw = w;
    parts.forEach((d, i) => {
      const segW = d.value / total * bw;
      const gap = i < parts.length - 1 ? 2 : 0;
      const r = svg.append('rect').attr('x', x).attr('y', 6).attr('width', Math.max(0, segW - gap)).attr('height', 22)
        .attr('rx', 3).attr('fill', d.color);
      r.on('mousemove', e => showTip(e, `<b>${esc(d.label)}</b><br>${nf.format(d.value)} · ${esc(t('%{v}', { v: (d.value / total * 100).toFixed(1) }))}`)).on('mouseleave', hideTip);
      x += segW;
    });
    // Lejant + doğrudan etiketler
    let lx = 0;
    parts.forEach(d => {
      const txt = `${d.label} ${t('%{v}', { v: (d.value / total * 100).toFixed(1) })} (${fmt(d.value)})`;
      svg.append('rect').attr('x', lx).attr('y', 44).attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', d.color);
      const tx = svg.append('text').attr('x', lx + 15).attr('y', 49).attr('dy', '0.32em').attr('fill', C.ink2).attr('font-size', 11.5).text(txt);
      lx += 15 + txt.length * 6.4 + 16;
    });
  }

  // ── Isı haritası (saat × gün) ──────────────────────────
  function heatmap(el, spec) {
    const rows = spec.rows, cols = spec.cols, val = spec.value; // val(r,c)
    const { svg, w } = base(el, 10);
    const m = { t: 18, l: spec.labelW || 40, r: 8, b: 30 };
    const maxc = Math.floor((m.l - 8) / 6.4);
    const cw = Math.max(8, (w - m.l - m.r) / cols.length);
    const ch = spec.rowH || Math.min(26, Math.max(14, cw * 0.62));
    const h = m.t + rows.length * ch + m.b;
    svg.attr('height', h).attr('viewBox', `0 0 ${w} ${h}`);
    let max = 0;
    rows.forEach((r, ri) => cols.forEach((c, ci) => { max = Math.max(max, val(ri, ci) || 0); }));
    const col = d3.scaleLinear().domain([1, Math.max(1, max)]).range([C.seqLo, C.seqHi]).interpolate(d3.interpolateRgb);
    rows.forEach((r, ri) => {
      svg.append('text').attr('x', m.l - 6).attr('y', m.t + ri * ch + ch / 2).attr('dy', '0.32em').attr('text-anchor', 'end')
        .attr('fill', C.ink3).attr('font-size', 10.5).text(String(r).length > maxc ? String(r).slice(0, maxc - 1) + '…' : r);
      cols.forEach((c, ci) => {
        const v = val(ri, ci) || 0;
        svg.append('rect').attr('x', m.l + ci * cw + 1).attr('y', m.t + ri * ch + 1).attr('width', cw - 2).attr('height', ch - 2)
          .attr('rx', 2).attr('fill', v > 0 ? col(v) : C.seqZero)
          .on('mousemove', e => showTip(e, `<div class="tk">${esc((spec.rowFull || rows)[ri])} · ${esc(c)}:00 UTC</div><b>${nf.format(v)}</b> ${esc(spec.unit || '')}`))
          .on('mouseleave', hideTip);
      });
    });
    const every = Math.ceil(cols.length / Math.floor((w - m.l) / 26));
    cols.forEach((c, ci) => {
      if (ci % every === 0) svg.append('text').attr('x', m.l + ci * cw + cw / 2).attr('y', m.t - 6).attr('text-anchor', 'middle')
        .attr('fill', C.ink3).attr('font-size', 10).attr('font-family', MONO).text(c);
    });
    // Ölçek
    const ly = h - 12;
    svg.append('text').attr('x', m.l).attr('y', ly).attr('dy', '0.32em').attr('fill', C.ink3).attr('font-size', 10.5).text('0');
    svg.append('rect').attr('x', m.l + 12).attr('y', ly - 5).attr('width', 16).attr('height', 10).attr('rx', 2).attr('fill', C.seqZero).attr('stroke', C.axis);
    const steps = 6;
    for (let i = 0; i < steps; i++) {
      const v = 1 + (Math.max(1, max) - 1) * i / (steps - 1);
      svg.append('rect').attr('x', m.l + 32 + i * 18).attr('y', ly - 5).attr('width', 16).attr('height', 10).attr('rx', 2).attr('fill', col(v));
    }
    svg.append('text').attr('x', m.l + 32 + steps * 18 + 4).attr('y', ly).attr('dy', '0.32em').attr('fill', C.ink3).attr('font-size', 10.5).text(fmt(max));
  }

  // ── Çizgi (TikTok büyüme — tahmini) ───────────────────
  function line(el, spec) {
    const data = (spec.data || []).filter(d => d.value != null);
    const { svg, w, h } = base(el, spec.height || 210);
    if (data.length < 2) { el.innerHTML = `<div class="empty">${esc(t('Yeterli veri yok'))}</div>`; return; }
    const m = { t: 14, r: 14, b: 26, l: 52 };
    const x = d3.scalePoint().domain(data.map(d => d.label)).range([m.l, w - m.r]);
    const ext = d3.extent(data, d => d.value);
    const pad = (ext[1] - ext[0]) * 0.15 || ext[1] * 0.05 || 1;
    const y = d3.scaleLinear().domain([Math.max(0, ext[0] - pad), ext[1] + pad]).nice().range([h - m.b, m.t]);
    y.ticks(4).forEach(tk => {
      svg.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', y(tk)).attr('y2', y(tk)).attr('stroke', C.grid);
      svg.append('text').attr('x', m.l - 6).attr('y', y(tk)).attr('dy', '0.32em').attr('text-anchor', 'end').attr('fill', C.ink3)
        .attr('font-size', 10).attr('font-family', MONO).text(fmt(tk));
    });
    data.forEach(d => svg.append('text').attr('x', x(d.label)).attr('y', h - 8).attr('text-anchor', 'middle').attr('fill', C.ink3)
      .attr('font-size', 10).attr('font-family', MONO).text(d.label));
    const ln = d3.line().x(d => x(d.label)).y(d => y(d.value));
    svg.append('path').attr('d', ln(data)).attr('fill', 'none').attr('stroke', C.series).attr('stroke-width', 2)
      .attr('stroke-dasharray', spec.dashed ? '6,4' : null);
    const cross = svg.append('line').attr('y1', m.t).attr('y2', h - m.b).attr('stroke', C.axis).style('display', 'none');
    const dot = svg.append('circle').attr('r', 4.5).attr('fill', C.series).attr('stroke', C.surface).attr('stroke-width', 2).style('display', 'none');
    data.forEach(d => svg.append('circle').attr('cx', x(d.label)).attr('cy', y(d.value)).attr('r', 3).attr('fill', C.series));
    const last = data[data.length - 1];
    svg.append('text').attr('x', x(last.label) - 4).attr('y', y(last.value) - 9).attr('text-anchor', 'end').attr('fill', C.ink1)
      .attr('font-size', 11).attr('font-family', MONO).text(fmt(last.value));
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b).attr('fill', 'transparent')
      .on('mousemove', e => {
        const [mx] = d3.pointer(e);
        let best = data[0];
        data.forEach(d => { if (Math.abs(x(d.label) - mx) < Math.abs(x(best.label) - mx)) best = d; });
        cross.style('display', null).attr('x1', x(best.label)).attr('x2', x(best.label));
        dot.style('display', null).attr('cx', x(best.label)).attr('cy', y(best.value));
        showTip(e, `<div class="tk">${esc(best.full || best.label)}</div><b>${nf.format(best.value)}</b> ${esc(spec.unit || '')}`);
      })
      .on('mouseleave', () => { cross.style('display', 'none'); dot.style('display', 'none'); hideTip(); });
  }

  // ── Zaman çizelgesi (satır = tarama, nokta = etkinlik) ─────
  function strip(el, spec) {
    const rows = (spec.rows || []).filter(r => r.events && r.events.length);
    if (!rows.length) { el.innerHTML = `<div class="empty">${esc(t('Tarihli etkinlik yok'))}</div>`; return; }
    const labelW = 170, rowH = 30;
    const { svg, w } = base(el, rows.length * rowH + 40);
    const all = rows.flatMap(r => r.events.map(e => e.t));
    const from = spec.from || d3.min(all), to = spec.to || d3.max(all);
    const pad = Math.max(86400000, (to - from) * 0.02);
    const x = d3.scaleTime().domain([new Date(+from - pad), new Date(+to + pad)]).range([labelW, w - 12]);
    const ticks = x.ticks(Math.max(3, Math.floor((w - labelW) / 90)));
    const fmtT = x.tickFormat();
    ticks.forEach(tk => {
      svg.append('line').attr('x1', x(tk)).attr('x2', x(tk)).attr('y1', 6).attr('y2', rows.length * rowH + 8).attr('stroke', C.grid);
      svg.append('text').attr('x', x(tk)).attr('y', rows.length * rowH + 24).attr('text-anchor', 'middle').attr('fill', C.ink3)
        .attr('font-size', 10).attr('font-family', MONO).text(fmtT(tk));
    });
    rows.forEach((r, i) => {
      const cy = 8 + i * rowH + rowH / 2;
      svg.append('line').attr('x1', labelW).attr('x2', w - 12).attr('y1', cy).attr('y2', cy).attr('stroke', C.axis).attr('stroke-dasharray', '2,3');
      const lbl = String(r.label); const max = Math.floor((labelW - 14) / 7.2);
      svg.append('text').attr('x', labelW - 10).attr('y', cy).attr('dy', '0.32em').attr('text-anchor', 'end').attr('fill', C.ink2).attr('font-size', 11.5)
        .text(lbl.length > max ? lbl.slice(0, max - 1) + '…' : lbl);
      r.events.forEach(ev => {
        if (ev.t < from || ev.t > to) return;
        const c = svg.append('circle').attr('cx', x(ev.t)).attr('cy', cy).attr('r', 4).attr('fill', r.color || C.series)
          .attr('fill-opacity', 0.75).attr('stroke', C.surface).attr('stroke-width', 1);
        c.style('cursor', ev.url ? 'pointer' : 'default')
          .on('mousemove', e => { c.attr('r', 6); showTip(e, `<div class="tk">${esc(r.label)} · ${ev.t.toLocaleString(I18N.locale)}${ev.dateOnly ? ' ' + esc(t('(yalnız tarih)')) : ''}</div>${esc(ev.label || '')}`); })
          .on('mouseleave', () => { c.attr('r', 4); hideTip(); })
          .on('click', () => { if (ev.url) window.open(ev.url, '_blank', 'noopener'); });
      });
    });
  }

  const RENDER = { bar, hbar, stack, heatmap, line, strip };

  function render(el, spec) {
    const fn = RENDER[spec.type];
    if (!fn) return;
    fn(el, spec);
    // Genişlik değişince yeniden çiz
    if (!el._ro) {
      let lastW = el.clientWidth, timer;
      el._ro = new ResizeObserver(() => {
        if (Math.abs(el.clientWidth - lastW) < 4) return;
        lastW = el.clientWidth; clearTimeout(timer);
        timer = setTimeout(() => fn(el, spec), 120);
      });
      el._ro.observe(el);
    }
  }

  // ── PNG dışa aktarma ───────────────────────────────────
  async function svgToPng(svgNode, filename, opts = {}) {
    const bg = opts.background || C.surface;
    const title = opts.title || '';
    const clone = svgNode.cloneNode(true);
    let w = +svgNode.getAttribute('width') || svgNode.clientWidth;
    let h = +svgNode.getAttribute('height') || svgNode.clientHeight;
    if (opts.viewBox) { clone.setAttribute('viewBox', opts.viewBox.join(' ')); w = opts.width; h = opts.height; }
    clone.setAttribute('width', w); clone.setAttribute('height', h);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const xml = new XMLSerializer().serializeToString(clone);
    const img = new Image();
    const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
    const scale = 2, padX = 20, padTop = title ? 44 : 20, padB = 26;
    const cv = document.createElement('canvas');
    cv.width = (w + padX * 2) * scale; cv.height = (h + padTop + padB) * scale;
    const ctx = cv.getContext('2d');
    ctx.scale(scale, scale);
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w + padX * 2, h + padTop + padB);
    if (title) {
      ctx.fillStyle = C.ink1; ctx.font = `600 14px ${FONT}`; ctx.fillText(title, padX, 26);
    }
    ctx.drawImage(img, padX, padTop, w, h);
    ctx.fillStyle = C.ink3; ctx.font = `10px ${FONT}`;
    ctx.fillText(`SOCMIntelligence · ${new Date().toLocaleString(I18N.locale)}`, padX, h + padTop + 17);
    URL.revokeObjectURL(url);
    const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // Rapor icin: DOM disi statik SVG uret
  function staticSvg(spec, width = 680, theme = 'light') {
    const fn = RENDER[spec.type]; if (!fn) return '';
    const host = document.createElement('div');
    host.style.cssText = `position:absolute;left:-10000px;top:0;width:${width}px`;
    document.body.appendChild(host);
    try { withTheme(theme, () => fn(host, spec)); const svg = host.querySelector('svg'); return svg ? svg.outerHTML : host.innerHTML; }
    finally { host.remove(); }
  }

  window.Charts = { render, svgToPng, staticSvg, withTheme, colors: C, fmt, nf, esc, showTip, hideTip, FONT, MONO };
})();
