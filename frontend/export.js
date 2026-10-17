/* SOCMIntelligence — grafik dışa aktarma: GraphML (Gephi/yEd), GEXF (Gephi), Maltego CSV, Excel. */
(function () {
  'use strict';
  const x = s => String(s ?? '').replace(/[<>&'"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c]));
  const eid = v => (typeof v === 'object' ? v.id : v);
  const meta = n => Object.entries(n.meta || {}).map(([k, v]) => `${k}=${v}`).join('; ');

  function save(name, text, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }

  function graphml(g, ann = {}) {
    const n = g.nodes.map(v => `    <node id="${x(v.id)}"><data key="label">${x(v.label)}</data><data key="type">${x(v.type)}</data><data key="sources">${x((v.sources || []).join(', '))}</data><data key="status">${x((ann[v.id] || {}).status || '')}</data><data key="note">${x((ann[v.id] || {}).note || '')}</data><data key="meta">${x(meta(v))}</data></node>`).join('\n');
    const e = g.edges.map((v, i) => `    <edge id="e${i}" source="${x(eid(v.source))}" target="${x(eid(v.target))}"><data key="etype">${x(v.type)}</data><data key="weight">${v.weight ?? 1}</data></edge>`).join('\n');
    return `<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="type" for="node" attr.name="type" attr.type="string"/>
  <key id="sources" for="node" attr.name="sources" attr.type="string"/>
  <key id="status" for="node" attr.name="analyst_status" attr.type="string"/>
  <key id="note" for="node" attr.name="analyst_note" attr.type="string"/>
  <key id="meta" for="node" attr.name="meta" attr.type="string"/>
  <key id="etype" for="edge" attr.name="relation" attr.type="string"/>
  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>
  <graph id="G" edgedefault="directed">
${n}
${e}
  </graph>
</graphml>`;
  }

  function gexf(g, ann = {}) {
    const n = g.nodes.map(v => `      <node id="${x(v.id)}" label="${x(v.label)}"><attvalues><attvalue for="0" value="${x(v.type)}"/><attvalue for="1" value="${x((v.sources || []).join(', '))}"/><attvalue for="2" value="${x((ann[v.id] || {}).status || '')}"/><attvalue for="3" value="${x(meta(v))}"/></attvalues></node>`).join('\n');
    const e = g.edges.map((v, i) => `      <edge id="${i}" source="${x(eid(v.source))}" target="${x(eid(v.target))}" label="${x(v.type)}" weight="${v.weight ?? 1}"/>`).join('\n');
    return `<?xml version="1.0" encoding="UTF-8"?>
<gexf xmlns="http://gexf.net/1.3" version="1.3">
  <meta lastmodifieddate="${new Date().toISOString().slice(0, 10)}"><creator>SOCMIntelligence</creator></meta>
  <graph defaultedgetype="directed">
    <attributes class="node">
      <attribute id="0" title="type" type="string"/><attribute id="1" title="sources" type="string"/>
      <attribute id="2" title="analyst_status" type="string"/><attribute id="3" title="meta" type="string"/>
    </attributes>
    <nodes>
${n}
    </nodes>
    <edges>
${e}
    </edges>
  </graph>
</gexf>`;
  }

  // Maltego: Import Graph from Table ile içe aktarılır (her satır bir bağlantı).
  const MALTEGO = { person: 'maltego.Person', username: 'maltego.Alias', email: 'maltego.EmailAddress', domain: 'maltego.Domain',
    community: 'maltego.Organization', hashtag: 'maltego.Phrase', content: 'maltego.URL', artifact: 'maltego.Phrase', breach: 'maltego.Phrase', ip: 'maltego.IPv4Address' };
  function maltegoCsv(g) {
    const byId = new Map(g.nodes.map(n => [n.id, n]));
    const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = [[t('Kaynak varlık türü'), t('Kaynak'), t('İlişki'), t('Hedef varlık türü'), t('Hedef')].map(q).join(',')];
    g.edges.forEach(e => {
      const s = byId.get(eid(e.source)), tg = byId.get(eid(e.target));
      if (s && tg) rows.push([MALTEGO[s.type] || 'maltego.Phrase', s.label, e.type, MALTEGO[tg.type] || 'maltego.Phrase', tg.label].map(q).join(','));
    });
    g.nodes.forEach(n => { if (!g.edges.some(e => eid(e.source) === n.id || eid(e.target) === n.id)) rows.push([MALTEGO[n.type] || 'maltego.Phrase', n.label, '', '', ''].map(q).join(',')); });
    return '﻿' + rows.join('\r\n');
  }

  async function xlsx(payload, name) {
    const r = await fetch('/api/export/xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, lang: I18N.lang }) });
    if (!r.ok) throw new Error(t('Excel oluşturulamadı: HTTP {n}', { n: r.status }));
    const blob = await r.blob();
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name + '.xlsx'; document.body.appendChild(a); a.click(); a.remove();
  }

  window.Exporter = {
    graphml: (g, ann, name) => save(name + '.graphml', graphml(g, ann), 'application/xml'),
    gexf: (g, ann, name) => save(name + '.gexf', gexf(g, ann), 'application/xml'),
    maltego: (g, name) => save(name + '_maltego.csv', maltegoCsv(g), 'text/csv;charset=utf-8'),
    xlsx,
  };
})();
