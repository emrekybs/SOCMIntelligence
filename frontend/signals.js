/* SOCMIntelligence — taramalardan zaman / kimlik sinyalleri ve "aynı kişi mi" skoru. */
(function () {
  'use strict';

  // ── Tarih okuma: unix sn/ms, ISO, "dd.mm.yyyy[ HH:MM]", "YYYY-MM-DD HH:MM[:SS] UTC"
  function parseDate(v) {
    if (v == null || v === '' || v === 'N/A') return null;
    if (typeof v === 'number' || /^\d{9,13}$/.test(String(v))) {
      const n = +v; const d = new Date(n < 1e12 ? n * 1000 : n); return isNaN(d) ? null : { t: d, dateOnly: false };
    }
    const s = String(v).trim();
    let m = s.match(/^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
    if (m) return { t: new Date(Date.UTC(+m[3], +m[2] - 1, +m[1], +(m[4] || 12), +(m[5] || 0))), dateOnly: !m[4] };
    m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (m) {
      if (/[+-]\d{2}:?\d{2}$|Z$/.test(s)) { const d = new Date(s); if (!isNaN(d)) return { t: d, dateOnly: false }; }
      return { t: new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 12), +(m[5] || 0), +(m[6] || 0))), dateOnly: !m[4] };
    }
    const d = new Date(s); return isNaN(d) ? null : { t: d, dateOnly: false };
  }
  function ev(list, v, label, url) { const p = parseDate(v); if (p && p.t.getUTCFullYear() > 1995) list.push({ ...p, label, url }); }

  const mastoAcc = d => d.targeted_account || (d.instance_info && d.instance_info.admin) || (d.username_scan || [])[0] || {};

  // ── Etkinlikler ──────────────────────────────────────
  function events(s) {
    const d = s.data || {}, out = [];
    switch (s.platform) {
      case 'github': ev(out, d.created_at, t('Hesap açılışı')); ev(out, d.updated_at, t('Profil güncellemesi')); break;
      case 'mastodon': { const a = mastoAcc(d); ev(out, a.profile_created_at, t('Hesap açılışı'));
        (a.pinned_statuses || []).forEach(p => ev(out, p.created_at, t('Sabit gönderi: {v}', { v: (p.text || '').slice(0, 60) }), p.url));
        const tp = (a.status_analysis || {}).top_post; if (tp) ev(out, tp.created_at, t('En çok etkileşim alan gönderi'), tp.url); break; }
      case 'reddit': { const c = d.content_analysis || {};
        (c.top_posts || []).forEach(p => ev(out, p.date, t('Gönderi: {v}', { v: p.title ?? '' }), p.url)); (c.top_comments || []).forEach(p => ev(out, p.date, t('Yorum: {v}', { v: (p.text || '').slice(0, 60) })));
        ev(out, (d.profile || {}).created_utc, t('Hesap açılışı'));
        ((d.post_analysis || {}).top_posts || []).forEach(p => ev(out, p.date, `${p.author}: ${p.title}`, p.url)); break; }
      case 'snapchat': {
        ((d.stories || {}).snaps || []).forEach(x => ev(out, x.upload_date, t('Hikâye'), x.url));
        ((d.curated_highlights || {}).highlights || []).forEach(h => (h.snaps || []).forEach(x => ev(out, x.upload_date, t('Öne çıkan: {v}', { v: h.title || '' }), x.url)));
        ((d.spotlights || {}).spotlights || []).forEach(h => (h.snaps || []).forEach(x => ev(out, x.upload_date, 'Spotlight', x.url))); break; }
      case 'tiktok': (d.profiles || [d]).forEach(p => { ev(out, p.create_time, t('@{u} hesap açılışı', { u: p.username ?? '' })); (p.videos || []).forEach(v => ev(out, v.date, `@${p.username}: ${(v.title || '').slice(0, 60)}`, v.url)); }); break;
      case 'youtube': (d.profiles || [d]).forEach(p => { const va = p.video_analysis || {}, seen = new Set();
        [...(va.latest_videos || []), ...(va.top_by_views || []), ...(va.viral_videos || [])].forEach(v => { if (!seen.has(v.video_id)) { seen.add(v.video_id); ev(out, v.date, v.title, v.url); } });
        ((p.comment_analysis || {}).top_liked_comments || []).forEach(c => ev(out, c.date, t('Yorum ({v})', { v: c.author ?? '' }))); }); break;
      case 'telegram': (d.posts || []).forEach(p => ev(out, p.date, (p.text || t('(medya)')).slice(0, 70), p.url)); break;
      case 'x': (d.tweets || []).forEach(p => ev(out, p.date, (p.text || '').slice(0, 70), p.url)); ev(out, d.created_at, t('Hesap açılışı')); break;
      case 'keybase': ev(out, d.created, t('Hesap açılışı')); (d.devices || []).forEach(x => ev(out, x.ctime, t('Cihaz eklendi: {v}', { v: x.name || '' }))); (d.pgp_keys || []).forEach(k => ev(out, k.ctime, t('PGP anahtarı'))); break;
      case 'steam': ev(out, d.time_created, t('Hesap açılışı')); (d.friends || []).forEach(f => ev(out, f.since, t('Arkadaş: {v}', { v: f.name || f.steamid || '' }), f.profile_url)); break;
      case 'gravatar': ev(out, d.registration_date, t('Kayıt')); ev(out, d.last_profile_edit, t('Profil düzenleme')); break;
      case 'gitlab': ev(out, d.created_at, t('Hesap açılışı')); (d.projects || []).forEach(p => { ev(out, p.created, t('Proje: {v}', { v: p.path ?? '' }), p.url); });
        (d.commit_emails || []).forEach(c => ev(out, c.last, t('Son commit: {v}', { v: c.email ?? '' }))); break;
      case 'hackernews': ev(out, d.created, t('Hesap açılışı')); (d.stories || []).forEach(x => ev(out, x.date, x.title, x.hn_url)); (d.recent_comments || []).forEach(x => ev(out, x.date, t('Yorum: {v}', { v: (x.text || '').slice(0, 60) }), x.hn_url)); break;
      case 'stackexchange': ev(out, d.created, t('Hesap açılışı')); (d.answers || []).forEach(a => ev(out, a.date, t('Yanıt: {v}', { v: a.title || '' }), a.link)); (d.questions || []).forEach(q => ev(out, q.date, t('Soru: {v}', { v: q.title ?? '' }), q.link)); break;
      case 'twitch': ev(out, d.created_at, t('Hesap açılışı')); (d.videos || []).forEach(v => ev(out, v.date, v.title, v.url)); (d.clips || []).forEach(c => ev(out, c.date, t('Klip: {v}', { v: c.title || '' }), c.url)); break;
      case 'kick': (d.recent_categories || []).forEach(() => {}); if (d.stream) ev(out, d.stream.started_at, t('Canlı: {v}', { v: d.stream.title || '' })); break;
      case 'bluesky': ev(out, d.created_at, t('Hesap açılışı')); (d.posts || []).forEach(p => ev(out, p.created, (p.text || '').slice(0, 70), p.url)); break;
      case 'instagram': { ev(out, (d.about || {}).date_joined, t('Hesap açılışı (yaklaşık)'));
        (d.locations || []).forEach(l => ev(out, l.time, t('Konum: {v}', { v: l.name || '' }))); (d.posts_preview || []).forEach(pp => ev(out, pp.taken_at, (pp.caption || '').slice(0, 60), pp.permalink)); break; }
      case 'linkedin': (d.articles || []).forEach(a => ev(out, a.date, t('Yazı: {v}', { v: (a.title || '').slice(0, 60) }), a.url));
        (d.history || []).filter(h => h.source === 'wayback').forEach(h => ev(out, h.date, t('Arşiv kopyası: {v}', { v: h.headline || '' }), h.url)); break;
      case 'wayback': (d.captures || []).forEach(c => ev(out, c.timestamp && `${c.timestamp.slice(0, 4)}-${c.timestamp.slice(4, 6)}-${c.timestamp.slice(6, 8)} ${c.timestamp.slice(8, 10) || '12'}:${c.timestamp.slice(10, 12) || '00'}`, t('Arşiv kaydı ({v})', { v: c.status ?? '' }), c.archive_url)); break;
    }
    return out.sort((a, b) => a.t - b.t);
  }

  // ── Saat dağılımı (UTC, 24 kova) ─────────────────────
  function hours(s) {
    const d = s.data || {};
    const pick = {
      mastodon: () => (mastoAcc(d).status_analysis || {}).hour_distribution,
      reddit: () => (d.activity_analysis || d.post_analysis || {}).hour_distribution,
      snapchat: () => (d.snap_analytics || {}).hourly_distribution,
      tiktok: () => (d.schedule_analysis || {}).hour_dist,
      youtube: () => (d.video_analysis || {}).hour_distribution,
      telegram: () => (d.analysis || {}).hour_distribution,
      x: () => d.hour_distribution,
      instagram: () => (d.posting_times || {}).by_hour,
      bluesky: () => d.hour_distribution,
      gitlab: () => (d.activity || {}).hour_distribution,
      hackernews: () => (d.activity || {}).hour_distribution,
      stackexchange: () => (d.activity || {}).hour_distribution,
    }[s.platform];
    let obj = pick && pick();
    const arr = new Array(24).fill(0);
    if (obj && Object.keys(obj).length) {
      Object.entries(obj).forEach(([k, v]) => { const h = parseInt(String(k).slice(0, 2), 10); if (h >= 0 && h < 24) arr[h] += +v || 0; });
    } else {
      events(s).filter(e => !e.dateOnly).forEach(e => { arr[e.t.getUTCHours()] += 1; });
    }
    return arr.reduce((a, b) => a + b, 0) ? arr : null;
  }

  // ── Kimlik sinyalleri ────────────────────────────────
  const BIG = new Set(['github.com', 'gitlab.com', 'twitter.com', 'x.com', 'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'facebook.com', 'reddit.com',
    't.me', 'telegram.me', 'linkedin.com', 'google.com', 'discord.gg', 'discord.com', 'twitch.tv', 'patreon.com', 'medium.com', 'keybase.io', 'steamcommunity.com',
    'stackoverflow.com', 'news.ycombinator.com', 'gravatar.com', 'mastodon.social', 'bit.ly', 'linktr.ee', 'web.archive.org', 'i.redd.it', 'v.redd.it', 'imgur.com', 'amazon.com', 'spotify.com', 'apple.com']);
  const dom = u => { try { return new URL(/^https?:/.test(u) ? u : 'https://' + u).hostname.replace(/^www\./, '').toLowerCase(); } catch (e) { return null; } };
  const normH = h => String(h || '').toLowerCase().replace(/^@/, '').replace(/@.*$/, '').replace(/[._\-\s]/g, '');

  function identity(s) {
    const d = s.data || {};
    const I = { handles: [], names: [], emails: [], domains: [], avatar: null };
    const add = (k, v) => { if (v && !I[k].includes(v)) I[k].push(v); };
    switch (s.platform) {
      case 'github': add('handles', d.login); add('names', d.name); (d.emails_all || []).forEach(e => add('emails', e)); if (d.blog) add('domains', dom(d.blog)); I.avatar = d.avatar_url; break;
      case 'mastodon': { const a = mastoAcc(d); add('handles', a.username); add('names', a.display_name); (a.emails || []).forEach(e => add('emails', e)); (a.urls || []).forEach(u => add('domains', dom(u))); I.avatar = a.avatar_link; break; }
      case 'reddit': add('handles', d.username || d.name); I.avatar = (d.profile || {}).avatar_url ? String(d.profile.avatar_url).replace(/&amp;/g, '&') : null; break;
      case 'snapchat': { const i = d.account_information || {}; add('handles', i.username); add('names', i.display_name); if (i.website && i.website !== 'None') add('domains', dom(i.website)); I.avatar = i.profile_picture; break; }
      case 'tiktok': add('handles', d.username); add('names', d.display_name); if ((d.bio_link || {}).domain) add('domains', d.bio_link.domain); I.avatar = d.profile_image; break;
      case 'youtube': { const c = d.channel || {}; add('handles', (c.handle || '').replace(/^@/, '')); add('names', c.title);
        (((d.bio_data || {}).emails) || []).forEach(e => add('emails', e)); ((d.bio_links || {}).links || []).forEach(l => add('domains', l.domain)); break; }
      case 'telegram': add('handles', d.username); add('names', d.title); (d.description_emails || []).forEach(e => add('emails', e)); (d.description_links || []).forEach(u => add('domains', dom(u))); I.avatar = d.photo; break;
      case 'x': add('handles', d.username); add('names', d.name); (d.emails || []).forEach(e => add('emails', e)); if (d.website) add('domains', dom(d.website)); I.avatar = d.profile_image; break;
      case 'keybase': add('handles', d.username); add('names', d.full_name); (d.bio_emails || []).forEach(e => add('emails', e));
        (d.proofs || []).forEach(p => { if (p.type === 'generic_web_site' || p.type === 'dns') add('domains', p.nametag); else add('handles', p.nametag); }); I.avatar = d.picture; break;
      case 'steam': add('handles', d.custom_url); add('names', d.persona); add('names', d.real_name); (d.aliases || []).forEach(a => add('names', a.name)); (d.summary_emails || []).forEach(e => add('emails', e)); I.avatar = d.avatar; break;
      case 'gravatar': add('handles', d.username); add('names', d.display_name); add('names', d.name); if (d.email) add('emails', d.email); (d.emails || []).forEach(e => add('emails', e));
        (d.links || []).forEach(l => add('domains', dom(l.url))); (d.accounts || []).forEach(a => add('handles', a.username)); I.avatar = d.avatar_url; break;
      case 'gitlab': add('handles', d.username); add('names', d.name); if (d.public_email) add('emails', d.public_email);
        (d.commit_emails || []).filter(e => e.likely_self && !e.noreply).forEach(e => add('emails', e.email)); if (d.website_url) add('domains', dom(d.website_url)); I.avatar = d.avatar_url; break;
      case 'hackernews': add('handles', d.username); (d.about_emails || []).forEach(e => add('emails', e)); (d.about_links || []).forEach(u => add('domains', dom(u))); break;
      case 'stackexchange': add('names', d.display_name); (d.about_emails || []).forEach(e => add('emails', e)); if (d.website) add('domains', dom(d.website)); I.avatar = d.profile_image; break;
      case 'twitch': add('handles', d.login); add('names', d.display_name); (d.emails || []).forEach(e => add('emails', e)); (d.domains || []).forEach(x => add('domains', x)); (d.socials || []).forEach(x => add('handles', String(x.handle || '').replace(/^@/, ''))); I.avatar = d.profile_image_url; break;
      case 'kick': add('handles', d.slug); add('names', d.username); (d.emails || []).forEach(e => add('emails', e)); (d.domains || []).forEach(x => add('domains', x)); Object.values(d.declared_socials || {}).forEach(v => add('handles', String(v).replace(/^@/, ''))); I.avatar = d.profile_pic; break;
      case 'bluesky': add('handles', d.handle); add('names', d.display_name); (d.emails || []).forEach(e => add('emails', e)); (d.domains || []).forEach(x => add('domains', x.domain)); I.avatar = d.avatar; break;
      case 'instagram': { const p = d.profile || {}; add('handles', p.username || d.username); add('names', p.full_name); if (p.public_email) add('emails', p.public_email);
        (p.bio_links || []).forEach(l => add('domains', dom(l.url))); if (p.external_url) add('domains', dom(p.external_url)); I.avatar = p.profile_pic_url; break; }
      case 'linkedin': add('handles', d.slug); add('names', d.name); (d.emails || []).forEach(e => add('emails', e)); (d.urls || []).forEach(u => add('domains', dom(u))); I.avatar = d.image; break;
      case 'wayback': if (d.is_domain) add('domains', d.target); (d.emails || []).forEach(e => add('emails', e)); break;
    }
    I.emails = I.emails.map(e => e.toLowerCase());
    I.domains = I.domains.filter(x => x && !BIG.has(x));
    I.handles = I.handles.filter(Boolean);
    I.names = I.names.filter(Boolean);
    return I;
  }

  // Taramanın kendi kimlik düğümleri: kişi düğümü + ondan "owns" ile çıkan kullanıcı adları
  function selfNodes(s) {
    const g = s.graph || { nodes: [], edges: [] };
    const person = g.nodes.find(n => n.type === 'person') || g.nodes[0];
    if (!person) return new Set();
    const ids = new Set([person.id]);
    g.edges.forEach(e => { if (e.source === person.id && e.type === 'owns') { const tn = g.nodes.find(n => n.id === e.target); if (tn && tn.type === 'username') ids.add(tn.id); } });
    return ids;
  }
  const personOf = s => ((s.graph || {}).nodes || []).find(n => n.type === 'person') || null;

  // Jaro-Winkler benzerliği
  function jw(a, b) {
    if (!a || !b) return 0; if (a === b) return 1;
    const md = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
    const am = new Array(a.length).fill(false), bm = new Array(b.length).fill(false);
    let m = 0;
    for (let i = 0; i < a.length; i++) for (let j = Math.max(0, i - md); j < Math.min(b.length, i + md + 1); j++) if (!bm[j] && a[i] === b[j]) { am[i] = bm[j] = true; m++; break; }
    if (!m) return 0;
    let tr = 0, k = 0;
    for (let i = 0; i < a.length; i++) if (am[i]) { while (!bm[k]) k++; if (a[i] !== b[k]) tr++; k++; }
    const j = (m / a.length + m / b.length + (m - tr / 2) / m) / 3;
    let p = 0; while (p < 4 && a[p] === b[p]) p++;
    return j + p * 0.1 * (1 - j);
  }
  function cosine(a, b) {
    if (!a || !b) return null;
    const sa = a.reduce((x, y) => x + y, 0), sb = b.reduce((x, y) => x + y, 0);
    if (sa < 8 || sb < 8) return null;
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < 24; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
    return na && nb ? dot / Math.sqrt(na * nb) : null;
  }
  function hamming(h1, h2) {
    if (!h1 || !h2 || h1.length !== h2.length) return null;
    let d = 0; for (let i = 0; i < h1.length; i++) { let x = parseInt(h1[i], 16) ^ parseInt(h2[i], 16); while (x) { d += x & 1; x >>= 1; } }
    return d;
  }

  // İki tarama arasındaki eşleşme skoru (0-100) + gerekçeler
  function score(A, B, avatarHashes = {}) {
    const reasons = [];
    let sc = 0;
    const add = (pts, txt) => { sc += pts; reasons.push({ pts, txt }); };
    const ia = identity(A), ib = identity(B);
    const selfA = selfNodes(A), selfB = selfNodes(B);
    // 1) Doğrudan bağlantı: bir taramanın grafiği diğerinin kimlik düğümüne işaret ediyor
    const link = (X, selfY) => (X.graph ? X.graph.edges : []).filter(e => selfY.has(e.target) && !selfNodes(X).has(e.target));
    const lab = link(A, selfB), lba = link(B, selfA);
    const verified = [...lab, ...lba].some(e => e.type === 'verified');
    if (verified) add(55, t('Kriptografik / doğrulanmış hesap bağlantısı'));
    else if (lab.length || lba.length) add(45, t('Bir profil diğer hesaba doğrudan bağlantı veriyor'));
    // 2) Ortak e-posta
    const em = ia.emails.filter(e => ib.emails.includes(e));
    if (em.length) add(Math.min(50, 35 * em.length), t('Ortak e-posta: {v}', { v: em.slice(0, 3).join(', ') }));
    // 3) Kullanıcı adı benzerliği
    let best = 0, bp = null;
    ia.handles.forEach(a => ib.handles.forEach(b => { const s = jw(normH(a), normH(b)); if (s > best) { best = s; bp = [a, b]; } }));
    if (best >= 0.999) add(25, t('Aynı kullanıcı adı: {v}', { v: bp[0] }));
    else if (best >= 0.9) add(15, t('Çok benzer kullanıcı adı: {a} ~ {b}', { a: bp[0], b: bp[1] }));
    else if (best >= 0.82) add(7, t('Benzer kullanıcı adı: {a} ~ {b}', { a: bp[0], b: bp[1] }));
    // 4) Görünen ad
    const nn = x => String(x || '').toLocaleLowerCase('tr').replace(/[^\p{L}\p{N} ]/gu, '').trim();
    let nameHit = null;
    ia.names.forEach(a => ib.names.forEach(b => { if (!nameHit && nn(a).length > 3 && nn(a) === nn(b)) nameHit = a; }));
    if (nameHit) add(10, t('Aynı görünen ad: {v}', { v: nameHit }));
    // 5) Ortak kişisel alan adı
    const dm = ia.domains.filter(x => ib.domains.includes(x));
    if (dm.length) add(Math.min(30, 15 * dm.length), t('Ortak alan adı: {v}', { v: dm.slice(0, 3).join(', ') }));
    // 6) Avatar benzerliği (pHash)
    const ha = avatarHashes[ia.avatar], hb = avatarHashes[ib.avatar];
    if (ha && hb) {
      const dist = hamming(ha.phash, hb.phash);
      if (dist != null && dist <= 8) add(30, t('Avatarlar neredeyse aynı (pHash farkı {n})', { n: dist }));
      else if (dist != null && dist <= 14) add(12, t('Avatarlar benzer (pHash farkı {n})', { n: dist }));
    }
    // 7) Etkinlik saatleri
    const cs = cosine(hours(A), hours(B));
    if (cs != null && cs >= 0.85) add(8, t('Etkinlik saatleri çok benzer (%{v})', { v: Math.round(cs * 100) }));
    else if (cs != null && cs >= 0.7) add(4, t('Etkinlik saatleri benzer (%{v})', { v: Math.round(cs * 100) }));
    return { score: Math.min(100, sc), reasons, hourSim: cs };
  }
  const level = sc => sc >= 70 ? [t('Güçlü'), 'good'] : sc >= 40 ? [t('Orta'), 'warn'] : sc >= 20 ? [t('Zayıf'), ''] : [t('Yok||none'), ''];

  window.Signals = { BIG, parseDate, events, hours, identity, selfNodes, personOf, score, level, cosine, hamming };
})();
