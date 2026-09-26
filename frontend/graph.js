/* SOCMIntelligence — İlişki grafiği motoru.
   Kullanıcının graph.html motorundan uyarlandı:
   D3 kuvvet simülasyonu, sürükle/yakınlaştır, komşu vurgulama, detay paneli, bağlam menüsü,
   arama, tür filtresi, fizik aç/kapa. Glow filtreleri kaldırıldı, düz Socmint Mavi stili.
   Sahte "pivot" havuzu yerine gerçek tarama tetiklenir. */
(function () {
  'use strict';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const BG = '#0b1017';

  const NODE = {
    person:    { color: '#5f8ac2', icon: 'P', label: t('Kişi / hesap sahibi'), r: 19 },
    username:  { color: '#c9805f', icon: 'U', label: t('Kullanıcı adı'),       r: 13 },
    email:     { color: '#4ba39d', icon: '@', label: t('E-posta'),             r: 13 },
    domain:    { color: '#c7a24e', icon: 'D', label: t('Alan adı / sunucu'),   r: 14 },
    community: { color: '#8f83d6', icon: 'C', label: t('Topluluk / org'),      r: 15 },
    hashtag:   { color: '#a897dd', icon: '#', label: t('Etiket'),              r: 11 },
    content:   { color: '#7f8ea6', icon: 'V', label: t('İçerik (video/repo)'), r: 11 },
    artifact:  { color: '#5fa46b', icon: '$', label: t('Tanımlayıcı (tel/kripto)'), r: 12 },
    breach:    { color: '#c25a5a', icon: '!', label: t('Sızıntı / risk'),      r: 15 },
    ip:        { color: '#c25a5a', icon: 'I', label: 'IP',                  r: 13 },
  };
  const ID_COL = '#6d97cf', INT_COL = '#d2895a', CNT_COL = '#5fa6a0', MOD_COL = '#9a8bde';
  const EDGE = {
    owns:          { color: ID_COL,  dash: '',     label: t('sahip') },
    linked_to:     { color: ID_COL,  dash: '6,3',  label: t('bağlantılı') },
    registered_to: { color: ID_COL,  dash: '3,3',  label: t('kayıtlı') },
    member_of:     { color: ID_COL,  dash: '1,3',  label: t('üye') },
    commented:     { color: INT_COL, dash: '',     label: t('yorum yaptı') },
    mentioned:     { color: INT_COL, dash: '6,3',  label: t('bahsetti') },
    related:       { color: INT_COL, dash: '3,3',  label: t('ilişkili hesap') },
    posted:        { color: CNT_COL, dash: '',     label: t('paylaştı') },
    appears_in:    { color: CNT_COL, dash: '6,3',  label: t('aktif / geçiyor') },
    tagged:        { color: CNT_COL, dash: '3,3',  label: t('etiket kullandı') },
    interest:      { color: CNT_COL, dash: '1,3',  label: t('ilgi alanı') },
    moderates:     { color: MOD_COL, dash: '',     label: t('moderatör') },
    verified:      { color: '#7fb0e0', dash: '',     label: t('kanıtlı bağ') },
    follows:       { color: ID_COL,  dash: '2,3',  label: t('takip ediyor') },
    friend:        { color: INT_COL, dash: '',     label: t('arkadaş') },
    replied:       { color: INT_COL, dash: '4,2',  label: t('yanıtladı') },
    forwarded:     { color: INT_COL, dash: '8,3',  label: t('iletti') },
    same_person:   { color: '#6fae78', dash: '10,4', label: t('aynı kişi olabilir') },
    manual:        { color: '#c9a24a', dash: '',     label: t('analist bağlantısı') },
  };
  const ANN = {
    verified:  { color: '#6fae78', label: t('Doğrulandı'), dash: null },
    suspect:   { color: '#c9a24a', label: t('Şüpheli'), dash: '4,3' },
    dismissed: { color: '#6c7887', label: t('Elendi'), dash: '2,3' },
  };
  const META_TR = {
    Platform: 'Platform', Platforms: 'Platform', Username: t('Kullanıcı adı'), Login: t('Kullanıcı'), Bio: 'Bio', Subscribers: t('Abone'),
    Verified: t('Doğrulanmış'), Public: t('Herkese açık'), Private: t('Gizli'), Category: t('Kategori'), Followers: t('Takipçi'), Following: t('Takip'),
    Videos: t('Video'), Region: t('Bölge'), Fake_Score: t('Sahte takipçi skoru'), Profile: t('Profil'), Source: t('Kaynak'), Location: t('Konum'),
    Company: t('Şirket'), Repos: t('Repo'), Public_Repos: t('Açık repo'), Created: t('Oluşturma'), Provider: t('Sağlayıcı'), Title: t('Başlık'),
    Members: t('Üye'), Type: t('Tür'), Severity: t('Önem'), Channel_ID: t('Kanal ID'), Handle: 'Handle', Country: t('Ülke'), Description: t('Açıklama'),
    Age: t('Yaş'), Total_views: t('Toplam izlenme'), Total_Karma: t('Toplam karma'), Post_Karma: t('Gönderi karması'), Comment_Karma: t('Yorum karması'),
    Suspended: t('Askıda'), Role: t('Rol'), Instance: t('Sunucu'), Posts: t('Gönderi'), Statuses: t('Gönderi'), Display_Name: t('Görünen ad'),
    Mention_count: t('Bahsetme sayısı'), Posts_in_sub: t('Subreddit’teki gönderi'), User_activity: t('Kullanıcı aktivitesi'), Count: t('Sayı'),
    Active: t('Çevrimiçi'), Admin_Email: t('Yönetici e-postası'), Open_Registration: t('Açık kayıt'), Users: t('Kullanıcı'), Version: t('Sürüm'),
    Label: t('Etiket||label'), Mod_since: t('Moderatörlük başlangıcı'), Snippet: t('Önizleme'), NSFW: 'NSFW', Uzun_video_izni: t('Uzun video izni'),
  };
  // Sunucunun Türkçe ürettiği meta anahtarları / değerleri (Türkçede aynen gösterilir)
  Object.assign(META_TR, {
    Tür: t('Tür'), Adres: t('Adres'), Kaynak: t('Kaynak'), Not: t('Not'), Durum: t('Durum'), Kanıt: t('Kanıt'), 'Parmak izi': t('Parmak izi'),
    Beğeni: t('Beğeni'), İzlenme: t('İzlenme'), Commit_adı: t('Commit adı'), Commit_adları: t('Commit adları'), Commit_sayısı: t('Commit sayısı'),
    En_beğenilen_yorum: t('En beğenilen yorum'), Eski_adlar: t('Eski adlar'), Video_sayısı: t('Video sayısı'), Yorum_sayısı: t('Yorum sayısı'),
    İlk_görülme: t('İlk görülme'),
  });
  const VAL_TR = {
    Var: t('Var'), Yok: t('Yok'), Kanal: t('Kanal'), Grup: t('Grup'), Kullanıcı: t('Kullanıcı'), Telefon: t('Telefon'), Video: t('Video||type'),
    Repo: t('Repo||type'), Moderatör: t('Moderatör'), Geçerli: t('Geçerli'), Açıklama: t('Açıklama'), Analist: t('Analist'),
    'PGP anahtarı': t('PGP anahtarı'), 'Arşivlenmiş sayfa': t('Arşivlenmiş sayfa'), 'Wayback hedefi': t('Wayback hedefi'),
    'Aynı Stack Exchange hesabı (account_id)': t('Aynı Stack Exchange hesabı (account_id)'), 'Commit meta verisi': t('Commit meta verisi'),
    'GitHub (yıldızlı repo konusu)': t('GitHub (yıldızlı repo konusu)'), 'GitHub organizasyonu': t('GitHub organizasyonu'), 'GitHub profili': t('GitHub profili'),
    'GitLab grubu': t('GitLab grubu'), 'Keybase alan adı kanıtı': t('Keybase alan adı kanıtı'), 'Mastodon bio': t('Mastodon bio'),
    "Snapchat 'ilişkili hesaplar'": t("Snapchat 'ilişkili hesaplar'"), 'Sorusuna yanıt verdiği kullanıcı': t('Sorusuna yanıt verdiği kullanıcı'),
    'TikTok bio linki': t('TikTok bio linki'), 'Yorumcu (görünen ad)': t('Yorumcu (görünen ad)'), 'YouTube Hakkında linkleri': t('YouTube Hakkında linkleri'),
    'YouTube açıklaması': t('YouTube açıklaması'),
  };
  const trKey = k => META_TR[k] || k.replace(/_/g, ' ');
  const trVal = v => v === 'Yes' ? t('Evet') : v === 'No' ? t('Hayır')
    : typeof v === 'string' ? (VAL_TR[v] ?? v.replace(/^Kripto \((.+)\)$/, (m, c) => t('Kripto ({c})', { c }))) : v;
  const nodeCfg = ty => NODE[ty] || { color: '#7b8aa0', icon: '?', label: ty, r: 12 };
  const edgeCfg = ty => EDGE[ty] || { color: CNT_COL, dash: '2,2', label: ty };
  const tint = c => d3.interpolateRgb(BG, c)(0.22);
  const eid = x => (typeof x === 'object' ? x.id : x);
  const ICON = {
    fit: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
    png: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M12 3v12M7 10l5 5 5-5M4 21h16"/></svg>',
  };

  class GraphView {
    constructor(root, opts = {}) {
      this.root = root;
      this.opts = opts;
      this.nodes = []; this.edges = [];
      this.hidden = new Set(); this.typeOff = new Set();
      this.physics = true; this.showLabels = true; this.selected = null;
      this._build();
    }

    _build() {
      this.root.innerHTML = `
        <div class="gwrap">
          <div class="gmain">
            <div class="gbar">
              <input class="input" data-r="search" placeholder="${esc(t('Düğüm ara…'))}">
              <div class="stats"><span>${esc(t('Düğüm'))} <b data-r="sn">0</b></span><span>${esc(t('Kenar'))} <b data-r="se">0</b></span><span data-r="shid"></span></div>
              <div class="right">
                <span data-r="extra" style="display:flex;gap:6px"></span>
                <button class="btn sm" data-r="fit" title="${esc(t('Ekrana sığdır'))}">${ICON.fit}${esc(t('Sığdır'))}</button>
                <button class="btn sm" data-r="phys">${esc(t('Fizik: açık'))}</button>
                <button class="btn sm" data-r="lbl">${esc(t('Etiketler: açık'))}</button>
                <button class="btn sm hidden" data-r="unhide">${esc(t('Gizlenenleri göster'))}</button>
                <button class="btn sm" data-r="json">JSON</button>
                <button class="btn sm" data-r="png">${ICON.png}PNG</button>
              </div>
            </div>
            <div class="gcanvas" data-r="canvas"><div class="gempty hidden" data-r="empty"></div></div>
            <div class="glegend" data-r="legend"></div>
          </div>
          <aside class="gpanel closed" data-r="panel">
            <div class="gpanel-h"><span class="badge" data-r="ptype">${esc(t('DÜĞÜM'))}</span><button class="btn sm ghost" style="margin-left:auto" data-r="pclose">${esc(t('Kapat'))}</button></div>
            <div class="gpanel-b" data-r="pbody"></div>
          </aside>
        </div>`;
      const $ = r => this.root.querySelector(`[data-r="${r}"]`);
      this.$ = $;
      this.canvas = $('canvas');
      if (this.opts.height) this.root.querySelector('.gwrap').style.height = this.opts.height + 'px';

      this.svg = d3.select(this.canvas).append('svg').attr('xmlns', 'http://www.w3.org/2000/svg');
      this.defs = this.svg.append('defs');
      Object.entries(EDGE).forEach(([ty, c]) => {
        this.defs.append('marker').attr('id', `arw-${ty}-${this._uid()}`).attr('data-t', ty)
          .attr('viewBox', '0 -4 8 8').attr('refX', 7).attr('refY', 0).attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 8).attr('markerHeight', 8)
          .attr('orient', 'auto').append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', c.color);
      });
      this.gRoot = this.svg.append('g').attr('class', 'graph-root');
      this.gEdges = this.gRoot.append('g');
      this.gNodes = this.gRoot.append('g');
      this.zoom = d3.zoom().scaleExtent([0.08, 4]).on('zoom', e => this.gRoot.attr('transform', e.transform));
      this.svg.call(this.zoom).on('dblclick.zoom', null);
      this.svg.on('click', e => { if (e.target === this.svg.node()) { this._clearFocus(); this.closePanel(); } this._hideCtx(); });
      this.svg.on('contextmenu', e => e.preventDefault());

      this.sim = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(l => 70 + (typeof l.source === 'object' ? nodeCfg(l.source.type).r : 12) + (typeof l.target === 'object' ? nodeCfg(l.target.type).r : 12)).strength(0.55))
        .force('charge', d3.forceManyBody().strength(-330).distanceMax(520))
        .force('collide', d3.forceCollide().radius(d => this._r(d) + 16))
        .force('x', d3.forceX().strength(0.035)).force('y', d3.forceY().strength(0.035))
        .alphaDecay(0.028)
        .on('tick', () => this._tick());

      // Kontroller
      $('search').addEventListener('input', e => this.search(e.target.value));
      $('fit').onclick = () => this.fit();
      $('phys').onclick = () => {
        this.physics = !this.physics;
        $('phys').textContent = this.physics ? t('Fizik: açık') : t('Fizik: kapalı');
        this.physics ? this.sim.alpha(0.4).restart() : this.sim.stop();
      };
      $('lbl').onclick = () => {
        this.showLabels = !this.showLabels;
        $('lbl').textContent = this.showLabels ? t('Etiketler: açık') : t('Etiketler: kapalı');
        this.gNodes.selectAll('text.lbl').attr('display', this.showLabels ? null : 'none');
      };
      $('unhide').onclick = () => { this.hidden.clear(); this.typeOff.clear(); this.render(); };
      $('png').onclick = () => this.exportPng();
      $('json').onclick = () => {
        const data = { nodes: this.nodes.map(n => ({ id: n.id, type: n.type, label: n.label, meta: n.meta, sources: n.sources })),
          edges: this.edges.map(e => ({ source: eid(e.source), target: eid(e.target), type: e.type, weight: e.weight })) };
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
        a.download = (this.opts.filename || t('iliski-grafigi')) + '.json'; a.click();
      };
      $('pclose').onclick = () => { this.closePanel(); this._clearFocus(); };

      this.ctx = document.createElement('div'); this.ctx.className = 'gctx'; document.body.appendChild(this.ctx);
      document.addEventListener('click', () => this._hideCtx());

      new ResizeObserver(() => { const r = this.canvas.getBoundingClientRect(); this.w = r.width; this.h = r.height; }).observe(this.canvas);
    }

    _uid() { if (!this.__uid) this.__uid = Math.random().toString(36).slice(2, 8); return this.__uid; }
    _deg(id) { return this._degMap?.get(id) || 0; }
    _r(d) { return nodeCfg(d.type).r + Math.min(9, Math.sqrt(this._deg(d.id)) * 1.6); }

    setData(graph) {
      const old = new Map(this.nodes.map(n => [n.id, n]));
      this.nodes = (graph.nodes || []).map(n => {
        const o = old.get(n.id);
        return Object.assign({}, n, o ? { x: o.x, y: o.y, vx: o.vx, vy: o.vy } : {});
      });
      const ids = new Set(this.nodes.map(n => n.id));
      this.edges = (graph.edges || []).filter(e => ids.has(eid(e.source)) && ids.has(eid(e.target)))
        .map(e => ({ ...e, source: eid(e.source), target: eid(e.target) }));
      this.render();
      const fresh = this.nodes.some(n => !old.has(n.id));
      if (fresh) setTimeout(() => this.fit(), 900);
    }

    _visible() {
      const vn = this.nodes.filter(n => !this.hidden.has(n.id) && !this.typeOff.has(n.type));
      const ids = new Set(vn.map(n => n.id));
      const ve = this.edges.filter(e => ids.has(eid(e.source)) && ids.has(eid(e.target)));
      return { vn, ve };
    }

    render() {
      const { vn, ve } = this._visible();
      this._degMap = new Map();
      ve.forEach(e => {
        this._degMap.set(eid(e.source), (this._degMap.get(eid(e.source)) || 0) + 1);
        this._degMap.set(eid(e.target), (this._degMap.get(eid(e.target)) || 0) + 1);
      });
      const uid = this._uid();

      this.edgeSel = this.gEdges.selectAll('line.edge').data(ve, d => d.id || `${eid(d.source)}|${eid(d.target)}|${d.type}`)
        .join(enter => enter.append('line').attr('class', 'edge')
          .attr('stroke', d => edgeCfg(d.type).color)
          .attr('stroke-opacity', 0.7)
          .attr('stroke-width', d => Math.min(4.5, 1.1 + (d.weight > 1 ? Math.log2(d.weight) * 0.55 : 0)))
          .attr('stroke-dasharray', d => edgeCfg(d.type).dash || null)
          .attr('marker-end', d => EDGE[d.type] ? `url(#arw-${d.type}-${uid})` : null)
          .on('mousemove', (e, d) => Charts.showTip(e, `<b>${esc(edgeCfg(d.type).label)}</b>${d.weight != null ? (d.type === 'same_person' ? ` · ${esc(t('skor %{v}', { v: d.weight }))}` : ` · ${Charts.nf.format(d.weight)}`) : ''}<div class="tk">${esc(this._label(eid(d.source)))} → ${esc(this._label(eid(d.target)))}</div>`))
          .on('mouseleave', () => Charts.hideTip()));

      const drag = d3.drag()
        .on('start', (e, d) => { this._hideCtx(); if (!e.active && this.physics) this.sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; if (!this.physics) { d.x = e.x; d.y = e.y; this._tick(); } })
        .on('end', (e, d) => { if (!e.active) this.sim.alphaTarget(0); if (this.physics) { d.fx = null; d.fy = null; } });

      this.nodeSel = this.gNodes.selectAll('g.node').data(vn, d => d.id)
        .join(enter => {
          const g = enter.append('g').attr('class', 'node').call(drag);
          g.append('circle').attr('class', 'ring').attr('fill', 'none');
          g.append('circle').attr('class', 'ann').attr('fill', 'none');
          g.append('circle').attr('class', 'body').attr('stroke-width', 1.8);
          g.append('text').attr('class', 'ico').attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
            .attr('font-family', Charts.MONO).attr('font-weight', 700);
          g.append('text').attr('class', 'lbl').attr('text-anchor', 'middle').attr('fill', '#a3b3cb')
            .attr('font-size', 10.5).attr('font-family', Charts.FONT);
          return g;
        });
      this.nodeSel.select('circle.body').attr('r', d => this._r(d)).attr('fill', d => tint(nodeCfg(d.type).color)).attr('stroke', d => nodeCfg(d.type).color);
      // Birden fazla kaynakta görülen düğüm: dış halka (platformlar arası eşleşme)
      this.nodeSel.select('circle.ring').attr('r', d => this._r(d) + 4.5)
        .attr('stroke', d => nodeCfg(d.type).color).attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '3,2').attr('display', d => (d.sources || []).length > 1 ? null : 'none');
      const ann = id => (this.opts.getAnn && this.opts.getAnn(id)) || {};
      this.nodeSel.select('circle.ann').attr('r', d => this._r(d) + 8)
        .attr('stroke', d => (ANN[ann(d.id).status] || {}).color || 'none').attr('stroke-width', 2.5)
        .attr('stroke-dasharray', d => (ANN[ann(d.id).status] || {}).dash || null).attr('display', d => ANN[ann(d.id).status] ? null : 'none');
      this.nodeSel.attr('opacity', d => ann(d.id).status === 'dismissed' ? 0.4 : null);
      this.nodeSel.select('text.ico').attr('fill', d => nodeCfg(d.type).color).attr('font-size', d => this._r(d) > 16 ? 13 : 10.5)
        .text(d => nodeCfg(d.type).icon);
      this.nodeSel.select('text.lbl').attr('y', d => this._r(d) + 13).attr('display', this.showLabels ? null : 'none')
        .text(d => { const l = String(d.label || d.id); return l.length > 24 ? l.slice(0, 22) + '…' : l; });
      this.nodeSel
        .on('mouseover', (e, d) => this._hover(d))
        .on('mouseout', () => this._unhover())
        .on('click', (e, d) => { e.stopPropagation(); this.select(d.id); })
        .on('dblclick', (e, d) => { e.stopPropagation(); this._pivot(d); })
        .on('contextmenu', (e, d) => { e.preventDefault(); e.stopPropagation(); this._showCtx(e, d); });

      this.sim.nodes(vn);
      this.sim.force('link').links(ve);
      if (this.physics) this.sim.alpha(0.7).restart(); else this._tick();

      this.$('sn').textContent = vn.length;
      this.$('se').textContent = ve.length;
      const hid = this.hidden.size + (this.typeOff.size ? this.nodes.filter(n => this.typeOff.has(n.type)).length : 0);
      this.$('shid').textContent = hid ? t('Gizli {n}', { n: hid }) : '';
      this.$('unhide').classList.toggle('hidden', !this.hidden.size);
      const empty = this.$('empty');
      empty.classList.toggle('hidden', this.nodes.length > 0);
      empty.innerHTML = this.opts.emptyText || esc(t('Henüz düğüm yok.'));
      this._legend();
    }

    _label(id) { const n = this.nodes.find(x => x.id === id); return n ? n.label : id; }

    _tick() {
      if (!this.edgeSel) return;
      this.edgeSel.each(function (d) {
        const s = d.source, tg = d.target;
        if (typeof s !== 'object' || typeof tg !== 'object') return;
        const dx = tg.x - s.x, dy = tg.y - s.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
        const rs = (nodeCfg(s.type).r + 3), rt = (nodeCfg(tg.type).r + 8);
        d3.select(this).attr('x1', s.x + dx * rs / len).attr('y1', s.y + dy * rs / len)
          .attr('x2', s.x + dx * (len - rt) / len).attr('y2', s.y + dy * (len - rt) / len);
      });
      this.nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    }

    _neighbors(id) {
      const ns = new Set([id]), es = new Set();
      this.edgeSel.each(e => { const s = eid(e.source), tg = eid(e.target); if (s === id || tg === id) { ns.add(s); ns.add(tg); es.add(e); } });
      return { ns, es };
    }
    _hover(d) {
      if (this.focusId) return;
      const { ns, es } = this._neighbors(d.id);
      this.nodeSel.classed('dim', n => !ns.has(n.id));
      this.edgeSel.classed('dim', e => !es.has(e));
    }
    _unhover() { if (this.focusId) return; this.nodeSel?.classed('dim', false); this.edgeSel?.classed('dim', false); }
    _focus(id) {
      this.focusId = id;
      const { ns, es } = this._neighbors(id);
      this.nodeSel.classed('dim', n => !ns.has(n.id)).classed('hit', n => n.id === id);
      this.edgeSel.classed('dim', e => !es.has(e));
    }
    _clearFocus() { this.focusId = null; this.nodeSel?.classed('dim', false).classed('hit', false); this.edgeSel?.classed('dim', false); }

    select(id) {
      const n = this.nodes.find(x => x.id === id); if (!n) return;
      this.selected = id; this._focus(id); this.openPanel(n);
    }

    openPanel(n) {
      const cfg = nodeCfg(n.type);
      this.$('ptype').innerHTML = `<span class="sq" style="background:${cfg.color}"></span>${esc(cfg.label)}`;
      const meta = Object.entries(n.meta || {}).filter(([, v]) => v !== '' && v != null && v !== '—');
      const isUrl = v => /^https?:\/\//i.test(String(v));
      const rels = [];
      this.edges.forEach(e => {
        const s = eid(e.source), tg = eid(e.target);
        if (s === n.id) rels.push({ id: tg, e, dir: '→' });
        else if (tg === n.id) rels.push({ id: s, e, dir: '←' });
      });
      const profileUrl = meta.find(([k, v]) => /profile|url/i.test(k) && isUrl(v));
      const pvs = this.opts.resolvePivots ? this.opts.resolvePivots(n) : [];
      const an = (this.opts.getAnn && this.opts.getAnn(n.id)) || {};
      this.$('pbody').innerHTML = `
        <div class="val">${esc(n.label)}</div>
        <div class="muted mono" style="font-size:11px;margin-top:3px">${esc(n.id)}</div>
        ${(n.sources || []).length ? `<div class="sec">${esc(t('Kaynak taramalar'))}</div><div class="chips">${n.sources.map(s => `<span class="badge accent">${esc(s)}</span>`).join('')}</div>
          ${n.sources.length > 1 ? `<div class="muted" style="font-size:11.5px;margin-top:6px">${esc(t('Bu düğüm birden fazla platform taramasında ortak çıktı.'))}</div>` : ''}` : ''}
        <div class="acts">
          <button class="btn sm" data-a="center">${esc(t('Merkeze al'))}</button>
          <button class="btn sm" data-a="copy">${esc(t('Değeri kopyala'))}</button>
          ${profileUrl ? `<a class="btn sm" href="${esc(profileUrl[1])}" target="_blank" rel="noopener">${esc(t('Profili aç'))}</a>` : ''}
          ${this.opts.onAddEdge ? `<button class="btn sm" data-a="link">${esc(t('Bağlantı ekle'))}</button>` : ''}
          ${n.manual && this.opts.onDeleteManual ? `<button class="btn sm danger" data-a="delm">${esc(t('Düğümü sil'))}</button>` : ''}
        </div>
        ${pvs.length ? `<div class="sec">${esc(t('Bu değerle tara'))}</div><div class="acts" style="margin-top:0">${pvs.map((p, i) => `<button class="btn sm primary" data-pv="${i}">${esc(p.label)}</button>`).join('')}</div>` : ''}
        ${this.opts.onAnnotate ? `<div class="sec">${esc(t('Analist işareti'))}</div>
        <div class="seg">${Object.entries(ANN).map(([k, v]) => `<button class="${an.status === k ? 'on' : ''}" data-ann="${k}" style="--c:${v.color}">${esc(v.label)}</button>`).join('')}
          <button data-ann="" class="${an.status ? '' : 'on'}">${esc(t('İşaretsiz'))}</button></div>
        <textarea class="input" data-a="note" rows="3" placeholder="${esc(t('Not ekle…'))}" style="width:100%;margin-top:8px">${esc(an.note || '')}</textarea>` : ''}
        <div class="sec">${esc(t('Meta veri'))}</div>
        ${meta.length ? `<div class="kv">${meta.map(([k, v]) => `<div>${esc(trKey(k))}</div><div>${isUrl(v) ? `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>` : esc(trVal(v))}</div>`).join('')}</div>` : `<div class="muted">${esc(t('Meta veri yok'))}</div>`}
        <div class="sec">${esc(t('Bağlantılar ({n})', { n: rels.length }))}</div>
        ${rels.map(r => { const o = this.nodes.find(x => x.id === r.id); if (!o) return ''; return `<div class="rel" data-id="${esc(r.id)}"><span class="glegend" style="position:static;padding:0;border:none;background:none"><span class="dot" style="border-color:${nodeCfg(o.type).color};display:inline-block"></span></span><span>${esc(o.label)}</span><span class="et">${r.dir} ${esc(edgeCfg(r.e.type).label)}${r.e.weight != null ? ' · ' + Charts.nf.format(r.e.weight) : ''}</span></div>`; }).join('')}
      `;
      const pb = this.$('pbody');
      pb.querySelectorAll('.rel').forEach(el => el.onclick = () => { this.select(el.dataset.id); this.center(el.dataset.id); });
      pb.querySelector('[data-a=center]').onclick = () => this.center(n.id);
      pb.querySelector('[data-a=copy]').onclick = () => { navigator.clipboard?.writeText(n.label); this.opts.toast?.(t('Kopyalandı')); };
      pb.querySelectorAll('[data-pv]').forEach(b => b.onclick = () => this.opts.onPivot?.(pvs[+b.dataset.pv]));
      pb.querySelectorAll('[data-ann]').forEach(b => b.onclick = () => { this.opts.onAnnotate(n.id, { status: b.dataset.ann || null }); this.render(); this.openPanel(n); });
      const note = pb.querySelector('[data-a=note]'); if (note) note.onchange = () => this.opts.onAnnotate(n.id, { note: note.value });
      const lk = pb.querySelector('[data-a=link]'); if (lk) lk.onclick = () => this.opts.onAddEdge(n);
      const dm = pb.querySelector('[data-a=delm]'); if (dm) dm.onclick = () => this.opts.onDeleteManual(n);
      this.$('panel').classList.remove('closed');
    }
    closePanel() { this.$('panel').classList.add('closed'); this.selected = null; }

    _pivot(n) {
      const pv = (this.opts.resolvePivots ? this.opts.resolvePivots(n) : [])[0];
      if (pv) this.opts.onPivot?.(pv);
      else this.opts.toast?.(t('Bu düğüm için desteklenen bir tarama modülü yok.'));
    }

    _showCtx(e, n) {
      const pvs = this.opts.resolvePivots ? this.opts.resolvePivots(n) : [];
      const url = Object.entries(n.meta || {}).find(([k, v]) => /profile|url/i.test(k) && /^https?:/i.test(String(v)));
      this.ctx.innerHTML = `
        <div data-a="center">${esc(t('Merkeze al'))}</div>
        <div data-a="focus">${esc(t('Komşuları vurgula'))}</div>
        <div data-a="copy">${esc(t('Değeri kopyala'))}</div>
        ${url ? `<div data-a="open">${esc(t('Profili aç'))}</div>` : ''}
        ${pvs.length ? '<hr>' + pvs.map((p, i) => `<div data-a="pv" data-i="${i}">${esc(t('Tara — {v}', { v: p.label ?? '' }))}</div>`).join('') : ''}
        ${this.opts.onAnnotate ? '<hr>' + Object.entries(ANN).map(([k, v]) => `<div data-a="ann" data-k="${k}">${esc(t('İşaretle: {v}', { v: v.label }))}</div>`).join('') : ''}
        <hr><div data-a="hide">${esc(t('Grafikten gizle'))}</div>`;
      this.ctx.style.display = 'block';
      this.ctx.style.left = Math.min(e.clientX, innerWidth - 210) + 'px';
      this.ctx.style.top = Math.min(e.clientY, innerHeight - 220) + 'px';
      this.ctx.querySelectorAll('div[data-a]').forEach(el => el.onclick = ev => {
        ev.stopPropagation(); this._hideCtx();
        const a = el.dataset.a;
        if (a === 'center') this.center(n.id);
        if (a === 'focus') this._focus(n.id);
        if (a === 'copy') { navigator.clipboard?.writeText(n.label); this.opts.toast?.(t('Kopyalandı')); }
        if (a === 'open') window.open(url[1], '_blank', 'noopener');
        if (a === 'pv') this.opts.onPivot?.(pvs[+el.dataset.i]);
        if (a === 'ann') { this.opts.onAnnotate(n.id, { status: el.dataset.k }); this.render(); }
        if (a === 'hide') { this.hidden.add(n.id); this.closePanel(); this._clearFocus(); this.render(); }
      });
    }
    _hideCtx() { if (this.ctx) this.ctx.style.display = 'none'; }

    _legend() {
      const counts = {}; this.nodes.forEach(n => { counts[n.type] = (counts[n.type] || 0) + 1; });
      const ecount = {}; this.edges.forEach(e => { ecount[e.type] = (ecount[e.type] || 0) + 1; });
      const types = Object.keys(counts).sort((a, b) => Object.keys(NODE).indexOf(a) - Object.keys(NODE).indexOf(b));
      const et = Object.keys(ecount).sort((a, b) => Object.keys(EDGE).indexOf(a) - Object.keys(EDGE).indexOf(b));
      const L = this.$('legend');
      if (!types.length) { L.classList.add('hidden'); return; }
      L.classList.remove('hidden');
      if (this.legendMin) { L.innerHTML = `<div class="row" data-min="1" style="cursor:pointer">${esc(t('Lejantı göster'))}</div>`; L.querySelector('[data-min]').onclick = () => { this.legendMin = false; this._legend(); }; return; }
      L.innerHTML = `<div class="lt" style="display:flex">${esc(t('Düğümler — tıkla: gizle/göster'))}<span data-min="1" style="margin-left:auto;cursor:pointer;text-transform:none;letter-spacing:0">${esc(t('küçült'))}</span></div>` +
        types.map(ty => `<div class="row ${this.typeOff.has(ty) ? 'off' : ''}" data-t="${ty}"><span class="dot" style="border-color:${nodeCfg(ty).color};background:${tint(nodeCfg(ty).color)}"></span>${esc(nodeCfg(ty).label)}<span class="n">${counts[ty]}</span></div>`).join('') +
        `<div class="lt" style="margin-top:8px">${esc(t('İlişkiler'))}</div>` +
        et.map(ty => `<div class="row" style="cursor:default"><span class="ln" style="border-top-color:${edgeCfg(ty).color};border-top-style:${edgeCfg(ty).dash ? 'dashed' : 'solid'}"></span>${esc(edgeCfg(ty).label)}<span class="n">${ecount[ty]}</span></div>`).join('') +
        (this.opts.getAnn ? `<div class="lt" style="margin-top:8px">${esc(t('Analist işaretleri'))}</div>` + Object.values(ANN).map(v => `<div class="row" style="cursor:default"><span class="dot" style="border-color:${v.color};border-style:${v.dash ? 'dashed' : 'solid'}"></span>${esc(v.label)}</div>`).join('') : '') +
        `<div class="muted" style="font-size:10.5px;margin-top:6px">${esc(t('Kesikli dış halka: birden çok platformda eşleşen düğüm. Kalın çizgi: yüksek sayı (yorum, gönderi).'))}</div>`;
      L.querySelector('[data-min]').onclick = () => { this.legendMin = true; this._legend(); };
      L.querySelectorAll('.row[data-t]').forEach(r => r.onclick = () => {
        const ty = r.dataset.t; this.typeOff.has(ty) ? this.typeOff.delete(ty) : this.typeOff.add(ty); this.render();
      });
    }

    search(q) {
      q = (q || '').trim().toLowerCase();
      if (!q) { this._clearFocus(); return; }
      let first = null;
      this.nodeSel.classed('dim', n => {
        const m = String(n.label).toLowerCase().includes(q) || n.id.includes(q);
        if (m && !first) first = n; return !m;
      });
      this.edgeSel.classed('dim', true);
      if (first) this.center(first.id, 1.3);
    }

    center(id, k = 1.4) {
      const n = this.nodes.find(x => x.id === id); if (!n || n.x == null) return;
      this.svg.transition().duration(600).call(this.zoom.transform,
        d3.zoomIdentity.translate(this.w / 2, this.h / 2).scale(k).translate(-n.x, -n.y));
    }

    fit() {
      const { vn } = this._visible();
      if (!vn.length || !this.w) return;
      const xs = vn.map(n => n.x || 0), ys = vn.map(n => n.y || 0);
      const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 60, y0 = Math.min(...ys) - 60, y1 = Math.max(...ys) + 70;
      const k = Math.min(1.6, Math.min(this.w / (x1 - x0), this.h / (y1 - y0)));
      this.svg.transition().duration(650).call(this.zoom.transform,
        d3.zoomIdentity.translate(this.w / 2, this.h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
    }

    exportPng() {
      const bb = this.gRoot.node().getBBox();
      if (!bb.width) { this.opts.toast?.(t('Dışa aktarılacak düğüm yok')); return; }
      const pad = 30;
      const vb = [bb.x - pad, bb.y - pad, bb.width + pad * 2, bb.height + pad * 2];
      const scale = Math.min(1.6, 1800 / vb[2]);
      const clone = this.svg.node().cloneNode(true);
      clone.querySelector('.graph-root').removeAttribute('transform');
      clone.querySelectorAll('.dim').forEach(el => el.classList.remove('dim'));
      Charts.svgToPng(clone, (this.opts.filename || t('iliski-grafigi')) + '.png', {
        viewBox: vb, width: vb[2] * scale, height: vb[3] * scale, background: BG,
        title: this.opts.pngTitle || t('İlişki grafiği'),
      });
    }

    destroy() { this.sim.stop(); this.ctx?.remove(); }
  }

  window.GraphView = GraphView;
  window.GraphMeta = { NODE, EDGE, ANN };
})();
