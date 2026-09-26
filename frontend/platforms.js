/* SOCMIntelligence — platform tanımları: başlık, göstergeler, grafikler, bulgular.
   Her fonksiyon aracın GERÇEK JSON çıktısındaki alan adlarını okur; olmayan alan "—" gösterilir. */
(function () {
  'use strict';
  const { fmt, nf } = Charts;
  const C = Charts.colors;
  const has = v => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length) && !(typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length);
  const num = v => (v == null || v === '' || isNaN(+v)) ? null : +v;
  const pct = v => v == null ? '—' : t('%{n}', { n: (+v).toLocaleString(I18N.locale, { maximumFractionDigits: 2 }) });
  const decSep = (1.5).toLocaleString(I18N.locale).charAt(1);
  const unamp = s => String(s || '').replace(/&amp;/g, '&');
  const clip = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

  const DAYS_TR = [t('Pzt'), t('Sal'), t('Çar'), t('Per'), t('Cum'), t('Cmt'), t('Paz')];
  const DAYS_FULL = [t('Pazartesi'), t('Salı'), t('Çarşamba'), t('Perşembe'), t('Cuma'), t('Cumartesi'), t('Pazar')];
  const DAY_KEYS = [['0', 'mon', 'monday'], ['1', 'tue', 'tuesday'], ['2', 'wed', 'wednesday'], ['3', 'thu', 'thursday'], ['4', 'fri', 'friday'], ['5', 'sat', 'saturday'], ['6', 'sun', 'sunday']];
  const dayIdx = k => DAY_KEYS.findIndex(a => a.includes(String(k).toLowerCase()));
  const dayTr = k => { const i = dayIdx(k); return i >= 0 ? DAYS_FULL[i] : (k || '—'); };

  function hourSeries(obj) {
    if (!has(obj)) return null;
    const out = Array.from({ length: 24 }, (_, h) => ({ label: String(h).padStart(2, '0'), full: `${String(h).padStart(2, '0')}:00 UTC`, value: 0 }));
    Object.entries(obj).forEach(([k, v]) => { const h = parseInt(String(k).slice(0, 2), 10); if (h >= 0 && h < 24) out[h].value += +v || 0; });
    return out;
  }
  function daySeries(obj) {
    if (!has(obj)) return null;
    const out = DAYS_TR.map((d, i) => ({ label: d, full: DAYS_FULL[i], value: 0 }));
    Object.entries(obj).forEach(([k, v]) => { const i = dayIdx(k); if (i >= 0) out[i].value += +v || 0; });
    return out;
  }
  function pairs(obj, keyNames = ['tag', 'name', 'account', 'sub', 'user', 'author', 'username', 'domain', 'flair', 'category'], cnt = ['count', 'posts', 'total_comments', 'value']) {
    if (!obj) return [];
    if (Array.isArray(obj)) return obj.map(it => {
      if (Array.isArray(it)) return { label: String(it[0]), value: +it[1] || 0 };
      if (it && typeof it === 'object') {
        const k = keyNames.find(n => it[n] != null); const c = cnt.find(n => it[n] != null);
        return k ? { label: String(it[k]), value: c ? +it[c] || 0 : 0, raw: it } : null;
      }
      return null;
    }).filter(Boolean);
    return Object.entries(obj).map(([k, v]) => ({ label: k, value: +v || 0 })).sort((a, b) => b.value - a.value);
  }
  const sentiment = s => has(s) ? { type: 'stack', data: [
    { label: t('Olumlu'), value: +s.positive || 0, color: C.pos },
    { label: t('Nötr'), value: +s.neutral || 0, color: C.neu },
    { label: t('Olumsuz'), value: +s.negative || 0, color: C.neg }] } : null;
  const riskCls = l => { l = String(l || '').toUpperCase(); return l.includes('HIGH') ? 'critical' : l.includes('MEDIUM') ? 'serious' : l.includes('LOW') ? 'warn' : l.includes('CLEAN') ? 'good' : ''; };
  const RISK_TR = { 'HIGH RISK': t('Yüksek risk'), 'MEDIUM RISK': t('Orta risk'), 'LOW RISK': t('Düşük risk'), 'CLEAN': t('Temiz') };
  const riskTr = l => (RISK_TR[String(l || '').toUpperCase()] || l || '—');
  const unixDate = ts => { const n = +ts; if (!n) return '—'; return new Date(n * 1000).toLocaleString(I18N.locale); };
  const isoDate = s => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString(I18N.locale); };

  // Bulgu yardımcıları
  const kv = (title, rows) => ({ title, kind: 'kv', rows: rows.filter(r => has(r[1]) && r[1] !== '—') });
  const list = (title, items, note) => ({ title, kind: 'list', items: items.filter(Boolean), note });
  const table = (title, cols, rows, note) => ({ title, kind: 'table', cols, rows, note });
  const L = (text, href, tag) => ({ text, href, tag });
  // platform adı -> ikonlu rozet (bulgular tablosunda güzel görünüm için)
  const PLAT_ICON = { 'Instagram': 'instagram', 'TikTok': 'tiktok', 'X (Twitter)': 'x', 'LinkedIn': 'linkedin', 'YouTube': 'youtube', 'Reddit': 'reddit', 'Telegram': 'telegram', 'Bluesky': 'bluesky', 'Mastodon': 'mastodon', 'Twitch': 'twitch', 'Kick': 'kick', 'Hacker News': 'hackernews' };
  const platBadge = name => ({ badge: name || '—', icon: PLAT_ICON[name] || null });

  // ═══════════════════ GitHub ═══════════════════
  const github = {
    id: 'github', name: 'GitHub', mark: 'GH',
    desc: t('Profil, e-postalar (commit meta verisi dahil), sosyal hesaplar, organizasyonlar, sızıntı taraması.'),
    examples: ['torvalds', '@torvalds', 'github.com/torvalds', t('kisi@ornek.com')],
    placeholder: t('kullanıcı adı, profil URL’si veya e-posta'), max: 10,
    header: d => ({
      avatar: d.avatar_url, title: d.name || d.login, handle: '@' + d.login, url: `https://github.com/${d.login}`, bio: d.bio,
      badges: [d.location && { t: d.location }, d.company && { t: d.company },
        (d.secrets_found || []).length && { t: t('{n} sızıntı bulgusu', { n: d.secrets_found.length }), c: 'critical' }].filter(Boolean),
    }),
    kpis: d => [
      { k: t('Açık repo'), v: fmt(d.public_repos) }, { k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Takip edilen'), v: fmt(d.following) },
      { k: 'Gist', v: fmt(d.gist_count) }, { k: t('E-posta'), v: fmt((d.emails_all || []).length) },
      { k: t('Organizasyon'), v: fmt((d.organizations || []).length) }, { k: t('Hesap oluşturma'), v: isoDate(d.created_at) },
    ],
    charts: d => [
      { title: t('Yıldızlı repoların dilleri'), sub: t('Hedefin yıldızladığı repolardaki dil dağılımı'), type: 'hbar', data: pairs(d.starred_top_languages), unit: t('repo') },
      { title: t('Yıldızlı repo konuları'), sub: t('İlgi alanı sinyali'), type: 'hbar', data: pairs(d.starred_top_topics), unit: t('repo') },
      { title: t('Organizasyon üye sayıları'), sub: t('Herkese açık üyeler (hedef hariç)'), type: 'hbar', data: (d.organizations || []).map(o => ({ label: o.org, value: (o.members || []).length })), unit: t('üye||unit') },
    ],
    findings: d => [
      kv(t('Kimlik'), [[t('Kullanıcı'), d.login], [t('Ad'), d.name], ['ID', d.id], [t('Konum'), d.location], [t('Şirket'), d.company], ['Blog', d.blog],
        [t('Profil e-postası'), d.email], ['Twitter/X', d.twitter_username], [t('Oluşturma'), isoDate(d.created_at)], [t('Son güncelleme'), isoDate(d.updated_at)],
        [t('Profil README'), d.profile_readme], [t('GPG anahtarları'), d.GPG_keys], ['GPG ID', (d.GPG_ids || []).join(', ')]]),
      list(t('E-posta adresleri'), (d.emails_all || []).map(e => L(e, 'mailto:' + e, t('e-posta')))),
      table(t('Commit meta verisindeki e-postalar'), [t('E-posta'), t('Ad'), t('Rol'), 'Repo'], (d.commit_search_emails || []).map(c => [c.email, c.name, c.role, c.repo])),
      list(t('Sosyal hesaplar'), [
        ...(d.social_accounts || []).map(s => L(s.url, s.url, s.provider)),
        ...Object.entries(d.social_media || {}).flatMap(([p, hs]) => (hs || []).map(h => L(h, null, p))),
      ]),
      table(t('Organizasyonlar'), [t('Organizasyon'), t('Herkese açık üyeler')], (d.organizations || []).map(o => [o.org, (o.members || []).join(', ') || '—'])),
      table(t('Sızıntı bulguları'), [t('Tür'), t('Kaynak'), t('Önizleme (maskeli)')], (d.secrets_found || []).map(s => [s.type, s.source, s.snippet])),
      table(t('Hassas dosyalar'), [t('Dosya'), t('Detay')], (d.sensitive_files || []).map(f => [f.path || f.file || f.name || JSON.stringify(f), f.repo || f.url || ''])),
      list(t('Genel olaylardaki e-postalar'), (d.public_events_emails || []).map(e => L(e, 'mailto:' + e))),
    ],
  };

  // ═══════════════════ Mastodon ═══════════════════
  const mastoAcc = d => d.targeted_account || (d.instance_info && d.instance_info.admin) || (d.username_scan || [])[0] || null;
  const MASTO_KIND = { qualified: t('Tam adres'), username: t('Kullanıcı adı taraması') };
  const mastodon = {
    id: 'mastodon', name: 'Mastodon', mark: 'MA',
    desc: t('Kullanıcı adını yüzlerce sunucuda arar; hesap, gönderi alışkanlığı ve bahsedilen hesaplar.'),
    examples: ['gargron', '@gargron@mastodon.social', 'https://mastodon.social/@gargron', 'mastodon.social'],
    placeholder: t('kullanıcı adı, @kullanıcı@sunucu, profil URL’si veya sunucu'), max: 5,
    header: d => {
      const inst = d.instance_info;
      if (d.kind === 'instance' && inst) return {
        avatar: inst.thumbnail_link, title: inst.title || inst.instance, handle: inst.instance, url: `https://${inst.instance}`,
        bio: inst.short_description || inst.detailed_description,
        badges: [{ t: t('Sunucu') }, inst.version && { t: 'v' + inst.version }, { t: inst.registrations_open ? t('Kayıt açık') : t('Kayıt kapalı'), c: inst.registrations_open ? 'good' : '' }].filter(Boolean),
      };
      const a = mastoAcc(d) || {};
      return {
        avatar: a.avatar_link, title: a.display_name || a.username || d.input, handle: a.account || (a.username ? `@${a.username}@${a.instance}` : d.input),
        url: a.profile_url, bio: a.bio,
        badges: [{ t: MASTO_KIND[d.kind] || d.kind },
          (d.username_scan || []).length && { t: t('{n} sunucuda bulundu', { n: d.username_scan.length }), c: 'accent' },
          a.bot && { t: 'Bot', c: 'warn' }, a.profile_locked && { t: t('Kilitli') }, a.suspended && { t: t('Askıya alınmış'), c: 'critical' }].filter(Boolean),
      };
    },
    kpis: d => {
      if (d.kind === 'instance' && d.instance_info) {
        const i = d.instance_info;
        return [{ k: t('Kullanıcı'), v: fmt(i.user_count) }, { k: t('Gönderi'), v: fmt(i.status_count) }, { k: t('Bağlı alan adı'), v: fmt(i.domain_count) }, { k: t('Sürüm'), v: i.version || '—' }, { k: t('İletişim'), v: i.email || '—' }];
      }
      const a = mastoAcc(d) || {}; const sa = a.status_analysis || {};
      return [{ k: t('Takipçi'), v: fmt(a.followers_count) }, { k: t('Takip'), v: fmt(a.following_count) }, { k: t('Gönderi'), v: fmt(a.statuses_count) },
        { k: t('Analiz edilen'), v: fmt(sa.statuses_analyzed), s: t('son gönderiler') }, { k: t('Günlük ort.'), v: sa.posts_per_day_avg != null ? String(sa.posts_per_day_avg) : '—' },
        { k: t('Bulunan sunucu'), v: fmt((d.username_scan || []).length) }, { k: t('Oluşturma'), v: isoDate(a.profile_created_at) }];
    },
    charts: d => {
      const a = mastoAcc(d) || {}; const sa = a.status_analysis || {};
      return [
        { title: t('Gönderi saatleri'), sub: t('UTC · son gönderiler'), type: 'bar', data: hourSeries(sa.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
        { title: t('Gönderi günleri'), type: 'bar', data: daySeries(sa.day_distribution), unit: t('gönderi') },
        { title: t('En çok bahsedilen hesaplar'), sub: t('İlişki grafiğinde "bahsetti" kenarı'), type: 'hbar', data: pairs(sa.top_mentions), unit: t('bahsetme'), labelWidth: 190 },
        { title: t('Etiketler'), type: 'hbar', data: pairs(sa.top_hashtags).map(x => ({ ...x, label: '#' + x.label })), unit: t('kullanım') },
        { title: t('Diller'), type: 'hbar', data: pairs(sa.languages), unit: t('gönderi') },
        { title: t('Görünürlük'), type: 'hbar', data: pairs(sa.visibility_breakdown), unit: t('gönderi') },
        { title: t('Bulunduğu sunucular — takipçi'), type: 'hbar', data: (d.username_scan || []).map(h => ({ label: h.instance, value: +h.followers_count || 0, href: h.profile_url })), unit: t('takipçi'), labelWidth: 180 },
      ];
    },
    findings: d => {
      const a = mastoAcc(d) || {}; const inst = d.instance_info || {}; const av = a.avatar_analysis || {}; const sa = a.status_analysis || {};
      return [
        d.kind === 'instance' ? kv(t('Sunucu'), [[t('Alan adı'), inst.instance], [t('Başlık'), inst.title], [t('Sürüm'), inst.version], [t('İletişim e-postası'), inst.email],
          [t('Diller'), (inst.languages || []).join(', ')], [t('Kayıt||reg'), inst.registrations_open ? t('Açık||reg') : t('Kapalı||reg')], [t('Onay gerekli'), inst.registration_approval_required ? t('Evet') : t('Hayır')],
          [t('Kullanıcı'), fmt(inst.user_count)], [t('Gönderi'), fmt(inst.status_count)]]) : null,
        kv(d.kind === 'instance' ? t('Yönetici hesabı') : t('Hesap'), [[t('Hesap'), a.account], [t('Görünen ad'), a.display_name], [t('Kullanıcı ID'), a.user_id], [t('Profil'), a.profile_url],
          [t('Oluşturma'), isoDate(a.profile_created_at)], [t('Son gönderi'), a.last_status_at], [t('Keşfedilebilir'), a.discoverable == null ? null : (a.discoverable ? t('Evet') : t('Hayır'))],
          ['Bot', a.bot ? t('Evet') : null], [t('Grup'), a.group ? t('Evet') : null], [t('Arama motoru kapalı (noindex)'), a.noindex ? t('Evet') : null], [t('Sınırlı'), a.limited ? t('Evet') : null]]),
        list(t('İletişim ve tanımlayıcılar'), [
          ...(a.emails || a.emails_in_bio || []).map(e => L(e, 'mailto:' + e, t('e-posta'))),
          ...(a.phone_numbers || []).map(p => L(p, null, t('telefon'))),
          ...Object.entries(a.crypto_addresses || {}).flatMap(([c, xs]) => (xs || []).map(x => L(x, null, c.toUpperCase()))),
        ]),
        list(t('Bio ve alanlardaki linkler'), (a.urls || a.urls_in_bio || []).map(u => L(u, u, 'url'))),
        list(t('Sosyal hesaplar (bio)'), Object.entries(a.social_handles || {}).flatMap(([p, hs]) => (hs || []).map(h => L(h, null, p)))),
        table(t('Profil alanları'), [t('Ad'), t('Değer'), t('Doğrulandı')], (a.custom_fields || []).map(f => [f.name, f.value, f.verified_at ? isoDate(f.verified_at) : '—'])),
        table(t('Kullanıcı adı taraması — bulunan sunucular'), [t('Sunucu'), t('Kullanıcı'), t('Takipçi'), t('Gönderi'), t('Profil')],
          (d.username_scan || []).map(h => [h.instance, h.username || h.acct, fmt(h.followers_count), fmt(h.statuses_count), { href: h.profile_url, text: t('Aç') }])),
        list(t('Sabitlenmiş gönderiler'), (a.pinned_statuses || []).map(p => L(clip(p.text, 140), p.url, isoDate(p.created_at)))),
        sa.top_post ? kv(t('En çok etkileşim alan gönderi'), [[t('Metin'), sa.top_post.text], [t('Favori'), fmt(sa.top_post.favourites_count ?? sa.top_post.favourites)], ['Boost', fmt(sa.top_post.reblogs_count)], [t('Tarih'), isoDate(sa.top_post.created_at)], ['URL', sa.top_post.url]]) : null,
        list(t('Paylaşılan URL’ler'), (sa.urls_shared || []).slice(0, 30).map(u => L(u, u))),
        kv(t('Avatar analizi'), [['URL', av.url], [t('Boyut'), av.size_bytes ? t('{n} bayt', { n: nf.format(av.size_bytes) }) : null], [t('Çözünürlük'), (av.dimensions || []).join('×')], [t('Biçim'), av.format],
          ['MD5', av.md5], ['SHA-256', av.sha256], ['pHash', av.phash], ['dHash', av.dhash], ['EXIF', has(av.exif) ? JSON.stringify(av.exif) : null]]),
      ].filter(Boolean);
    },
  };

  // ═══════════════════ Reddit ═══════════════════
  const reddit = {
    id: 'reddit', name: 'Reddit', mark: 'RD',
    desc: t('Kullanıcı veya subreddit: aktivite, ilgi alanları, tahmini saat dilimi, bot skoru, moderatörler.'),
    examples: ['spez', 'u/spez', 'https://reddit.com/user/spez', 'r/OSINT'],
    placeholder: t('kullanıcı adı, u/kullanıcı, r/subreddit veya URL'), max: 10,
    header: d => {
      if (d.type === 'subreddit') {
        const a = d.about || {};
        return { title: 'r/' + d.name, handle: a.title, url: d.url, bio: a.description, mono: 'r/',
          badges: [{ t: 'Subreddit' }, a.type && { t: a.type }, a.nsfw && { t: 'NSFW', c: 'warn' }, a.lang && { t: a.lang }].filter(Boolean) };
      }
      const p = d.profile || {}; const b = d.bot_score || {};
      return { avatar: unamp(p.avatar_url), title: 'u/' + d.username, handle: p.account_age ? t('Hesap yaşı: {age}', { age: p.account_age }) : '', url: d.profile_url, bio: p.description,
        badges: [p.verified && { t: t('E-posta doğrulanmış'), c: 'good' }, p.employee && { t: t('Reddit çalışanı'), c: 'accent' }, p.nsfw && { t: 'NSFW', c: 'warn' },
          p.is_suspended && { t: t('Askıya alınmış'), c: 'critical' }, b.label && { t: t('Bot skoru: {label}', { label: riskTr(b.label) }), c: riskCls(b.label) }].filter(Boolean) };
    },
    kpis: d => {
      if (d.type === 'subreddit') {
        const a = d.about || {}, pa = d.post_analysis || {}, e = d.engagement || {};
        return [{ k: t('Abone'), v: fmt(a.subscribers) }, { k: t('Çevrimiçi'), v: fmt(a.active_users) }, { k: t('Aktiflik oranı'), v: pct(e.active_ratio_pct), s: e.label },
          { k: t('Analiz edilen gönderi'), v: fmt(pa.total_analyzed) }, { k: t('Ort. skor'), v: fmt(pa.avg_score) }, { k: t('Ort. yorum'), v: fmt(pa.avg_comments) },
          { k: t('Moderatör'), v: fmt((d.moderators || []).length) }, { k: t('Kuruluş'), v: a.created_date || '—', s: a.age }];
      }
      const p = d.profile || {}, s = d.stats || {}, sa = d.subreddit_analysis || {}, aa = d.activity_analysis || {}, b = d.bot_score || {};
      return [{ k: t('Toplam karma'), v: fmt(p.total_karma) }, { k: t('Gönderi karması'), v: fmt(p.post_karma) }, { k: t('Yorum karması'), v: fmt(p.comment_karma) },
        { k: t('Hesap oluşturma'), v: p.created_date || '—', s: p.account_age }, { k: t('Çekilen yorum / gönderi'), v: `${fmt(s.comments_fetched)} / ${fmt(s.posts_fetched)}` },
        { k: t('Farklı subreddit'), v: fmt(sa.unique_subs) }, { k: t('Aktivite skoru'), v: aa.activity_score != null ? `${aa.activity_score}/100` : '—' },
        { k: t('Bot skoru'), v: b.score != null ? `${b.score}/100` : '—', s: riskTr(b.label) }];
    },
    charts: d => {
      if (d.type === 'subreddit') {
        const pa = d.post_analysis || {};
        return [
          { title: t('En aktif yazarlar'), sub: t('hot + top gönderilerde · ilişki grafiğinde yazar → subreddit'), type: 'hbar', data: pairs(pa.top_authors).map(x => ({ ...x, href: `https://www.reddit.com/user/${x.label}` })), unit: t('gönderi') },
          { title: t('Gönderi saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(pa.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
          { title: t('Gönderi günleri'), type: 'bar', data: daySeries(pa.day_distribution), unit: t('gönderi') },
          { title: t('Paylaşılan alan adları'), type: 'hbar', data: pairs(pa.top_domains), unit: t('gönderi') },
          { title: t('Etiketler (flair)'), type: 'hbar', data: pairs(pa.top_flairs), unit: t('gönderi') },
        ];
      }
      const sa = d.subreddit_analysis || {}, aa = d.activity_analysis || {}, ca = d.content_analysis || {};
      return [
        { title: t('En aktif olduğu subreddit’ler'), sub: t('yorum + gönderi sayısı'), type: 'hbar', data: pairs(sa.top_subreddits).map(x => ({ ...x, label: 'r/' + x.label, href: `https://www.reddit.com/r/${x.label}` })), unit: t('öğe'), limit: 15 },
        { title: t('Aktivite saatleri'), sub: t('UTC · tahmini saat dilimi: {tz}', { tz: aa.timezone_est || '—' }), type: 'bar', data: hourSeries(aa.hour_distribution), xName: t('Saat||hour'), unit: t('öğe') },
        { title: t('Aktivite günleri'), type: 'bar', data: daySeries(aa.day_distribution), unit: t('öğe') },
        sentiment(ca.sentiment) && { title: t('Yorum duygu dağılımı'), sub: t('Sözlük tabanlı basit sınıflandırma'), ...sentiment(ca.sentiment) },
      ].filter(Boolean);
    },
    findings: d => {
      if (d.type === 'subreddit') {
        const a = d.about || {}, pa = d.post_analysis || {};
        return [
          kv('Subreddit', [[t('Ad'), a.display_name], [t('Başlık'), a.title], [t('Açıklama'), a.description], [t('Kuruluş'), a.created_date], [t('Yaş'), a.age], [t('Tür'), a.type],
            [t('Dil'), a.lang], ['NSFW', a.nsfw ? t('Evet') : t('Hayır')], [t('En iyi saat'), pa.best_hour], [t('En iyi gün'), dayTr(pa.best_day)]]),
          table(t('Moderatörler'), [t('Kullanıcı'), t('Moderatörlük başlangıcı'), t('Yetkiler')], (d.moderators || []).map(m => [{ href: `https://www.reddit.com/user/${m.username || m.name}`, text: m.username || m.name }, m.mod_since, (m.permissions || []).join(', ')])),
          table(t('Öne çıkan gönderiler'), [t('Başlık'), t('Yazar'), t('Skor'), t('Yorum'), t('Tarih')], (pa.top_posts || []).map(p => [{ href: p.url, text: p.title }, p.author, fmt(p.score), fmt(p.comments), p.date])),
        ];
      }
      const p = d.profile || {}, aa = d.activity_analysis || {}, sa = d.subreddit_analysis || {}, ca = d.content_analysis || {}, b = d.bot_score || {};
      return [
        kv(t('Profil'), [[t('Kullanıcı'), p.display_name], ['ID', p.id], [t('Oluşturma'), p.created_date], [t('Hesap yaşı'), p.account_age], [t('Açıklama'), p.description],
          ['Avatar', p.has_avatar ? t('Var') : t('Yok')], [t('Profil'), d.profile_url]]),
        kv(t('Aktivite'), [[t('İlk aktivite'), aa.first_activity], [t('Son aktivite'), aa.last_activity], [t('En aktif saat'), aa.best_hour ? aa.best_hour + ' UTC' : null],
          [t('En aktif gün'), dayTr(aa.best_day)], [t('Tahmini saat dilimi'), aa.timezone_est], [t('Son 30 gün'), fmt(aa.last_30d_posts)], [t('Son 90 gün'), fmt(aa.last_90d_posts)],
          [t('Ort. yorum uzunluğu'), ca.avg_comment_len ? t('{n} karakter', { n: ca.avg_comment_len }) : null], [t('Silinmiş yorum'), fmt(ca.deleted_comments)]]),
        list(t('İlgi alanları (genel subreddit’ler hariç)'), (sa.interests || []).map(i => L('r/' + i, `https://www.reddit.com/r/${i}`))),
        list(t('Bot / şüpheli davranış sinyalleri'), (b.flags || []).map(f => L(f, null, t('sinyal'))), b.flags && !b.flags.length ? t('Sinyal yok') : null),
        table(t('En yüksek skorlu yorumlar'), [t('Yorum'), 'Subreddit', t('Skor'), t('Tarih')], (ca.top_comments || []).map(c => [c.text, 'r/' + c.subreddit, fmt(c.score), c.date])),
        table(t('En yüksek skorlu gönderiler'), [t('Başlık'), 'Subreddit', t('Skor'), t('Tarih')], (ca.top_posts || []).map(c => [{ href: c.url, text: c.title }, 'r/' + c.subreddit, fmt(c.score), c.date])),
      ];
    },
  };

  // ═══════════════════ Snapchat ═══════════════════
  const snapBadge = b => b && !['none', 'null', ''].includes(String(b).toLowerCase());
  const snapchat = {
    id: 'snapchat', name: 'Snapchat', mark: 'SC',
    desc: t('Herkese açık profil, hikâyeler, spotlight’lar, ilişkili hesaplar, yükleme ısı haritası.'),
    examples: ['djkhaled305', '@djkhaled305', 'snapchat.com/add/djkhaled305', 'https://www.snapchat.com/@djkhaled305'],
    placeholder: t('kullanıcı adı veya profil URL’si'), max: 10,
    header: d => {
      const i = d.account_information || {};
      return { avatar: i.profile_picture, title: i.display_name || i.username, handle: '@' + i.username, url: `https://www.snapchat.com/add/${i.username}`, bio: i.bio,
        badges: [snapBadge(i.badge) && { t: t('Rozetli hesap'), c: 'accent' }, { t: i.is_public ? t('Herkese açık') : t('Gizli / sınırlı'), c: i.is_public ? '' : 'warn' },
          (i.subcategory || i.category) && { t: String(i.subcategory || i.category).replace('public-profile-', '').replace('-v3', '') }].filter(Boolean) };
    },
    kpis: d => {
      const i = d.account_information || {}, a = d.account_analysis || {}, s = d.snap_analytics || {};
      return [{ k: t('Abone'), v: fmt(i.subscriber_count) }, { k: t('Toplam snap'), v: fmt(s.total_snaps) }, { k: t('Hikâye||count'), v: fmt((d.stories || {}).count) },
        { k: t('Öne çıkan'), v: fmt((d.curated_highlights || {}).count), s: t('{n} snap', { n: fmt((d.curated_highlights || {}).total_snaps) }) },
        { k: 'Spotlight', v: fmt((d.spotlights || {}).count) }, { k: t('Günlük ort.'), v: s.avg_per_day != null ? String(s.avg_per_day).replace('snaps/day', t('snap/gün')) : '—' },
        { k: t('Hesap yaşı'), v: a.account_age || '—' }, { k: t('Son aktif'), v: a.last_active || '—' }];
    },
    charts: d => {
      const hm = d.heatmap || {}, s = d.snap_analytics || {};
      const days = hm.days || ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
      const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
      const grid = hm.grid || {};
      const gridSum = Object.values(grid).reduce((a, r) => a + Object.values(r || {}).reduce((x, y) => x + (+y || 0), 0), 0);
      return [
        gridSum ? { title: t('Yükleme ısı haritası'), sub: t('Gün × saat (UTC) · hikâye + öne çıkan + spotlight'), type: 'heatmap', wide: true, unit: t('snap'),
          rows: days.map(d => { const i = dayIdx(d); return i >= 0 ? DAYS_TR[i] : d; }), rowFull: days.map(dayTr), cols: hours, value: (ri, ci) => +((grid[`${hours[ci]}:00`] || {})[days[ri]] || 0) } : { title: t('Yükleme ısı haritası'), type: 'heatmap', empty: true },
        { title: t('Günlere göre'), type: 'bar', data: daySeries(s.daily_distribution), unit: t('snap') },
        { title: t('Saatlere göre'), sub: 'UTC', type: 'bar', data: hourSeries(s.hourly_distribution), xName: t('Saat||hour'), unit: t('snap') },
        (s.video_count || s.image_count) ? { title: t('Medya türü'), type: 'stack', data: [{ label: 'Video', value: +s.video_count || 0, color: C.cat[0] }, { label: t('Fotoğraf'), value: +s.image_count || 0, color: C.cat[1] }] } : null,
        { title: t('İlişkili hesaplar — abone'), sub: t('Snapchat’in önerdiği benzer hesaplar'), type: 'hbar', data: (d.related_accounts || []).map(r => ({ label: '@' + r.username, value: +r.subscribers || 0, sub: r.title, href: `https://www.snapchat.com/add/${r.username}` })), unit: t('abone') },
      ].filter(Boolean);
    },
    media: d => { const u = (d.account_information || {}).username; return u ? [{ title: t('Isı haritası (sunucu PNG)'), endpoint: `/api/socmint/snapchat/heatmap/${encodeURIComponent(u)}`, file: `snapchat_heatmap_${u}.png`, note: t('Araç sunucuda yeniden çalıştırılır ve matplotlib ile PNG üretir (24 saat önbellek).') }] : []; },
    findings: d => {
      const i = d.account_information || {}, a = d.account_analysis || {}, s = d.snap_analytics || {};
      const allSnaps = [...((d.stories || {}).snaps || []).map(x => ({ ...x, src: t('Hikâye') })),
        ...((d.curated_highlights || {}).highlights || []).flatMap(h => (h.snaps || []).map(x => ({ ...x, src: t('Öne çıkan: {title}', { title: h.title || '' }) }))),
        ...((d.spotlights || {}).spotlights || []).flatMap(h => (h.snaps || []).map(x => ({ ...x, src: 'Spotlight' })))];
      return [
        kv(t('Hesap'), [[t('Kullanıcı'), i.username], [t('Görünen ad'), i.display_name], ['Bio', i.bio], [t('Web sitesi'), i.website], [t('Kategori'), i.category], [t('Alt kategori'), i.subcategory],
          [t('Rozet'), snapBadge(i.badge) ? i.badge : t('Yok||none')], [t('Oluşturma'), a.created_at], [t('Son güncelleme'), a.last_updated], ['Snapcode', i.snapcode_url]]),
        kv(t('Aktivite'), [[t('Son aktif'), a.last_active], [t('En aktif gün'), dayTr(a.most_active_day || s.most_active_day)], [t('En aktif saat'), a.most_active_hour || s.most_active_hour],
          [t('İlk snap'), s.first_snap], [t('Son snap'), s.last_snap], [t('Video / foto'), `${fmt(s.video_count)} / ${fmt(s.image_count)}`], [t('Ort. spotlight süresi'), s.avg_spotlight_duration]]),
        table(t('İlişkili hesaplar'), [t('Kullanıcı'), t('Ad'), t('Abone')], (d.related_accounts || []).map(r => [{ href: `https://www.snapchat.com/add/${r.username}`, text: '@' + r.username }, r.title, fmt(r.subscribers)])),
        table(t('Öne çıkanlar'), [t('Başlık'), t('Snap sayısı')], ((d.curated_highlights || {}).highlights || []).map(h => [h.title, fmt(h.snap_count)])),
        table(t('Spotlight’lar'), [t('Ad'), t('Etiketler'), 'Snap'], ((d.spotlights || {}).spotlights || []).map(h => [h.name, (h.hashtags || []).join(' '), fmt((h.snaps || []).length)])),
        table(t('Snap’ler'), [t('Kaynak'), t('Tür'), t('Yükleme'), t('Bağlantı')], allSnaps.slice(0, 80).map(x => [x.src, x.type, x.upload_date, x.url ? { href: x.url, text: t('Aç') } : '—'])),
      ];
    },
  };

  // ═══════════════════ TikTok ═══════════════════
  const tiktokSingle = {
    kpis: d => {
      const pf = d.posting_frequency || {};
      return [{ k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Takip'), v: fmt(d.following) }, { k: t('Toplam beğeni'), v: fmt(d.likes) }, { k: t('Video'), v: fmt(d.video_count) },
        { k: t('Etkileşim oranı'), v: pct(d.engagement_rate) }, { k: t('Günlük takipçi'), v: fmt(d.followers_per_day), s: t('hesap ömrü ortalaması') },
        { k: t('Hesap yaşı'), v: d.account_age_days != null ? t('{n} gün', { n: fmt(d.account_age_days) }) : '—' }, { k: t('Paylaşım'), v: pf.activity_label || '—', s: pf.per_week != null ? t('haftada {n}', { n: pf.per_week }) : '' }];
    },
    charts: d => {
      const ca = d.comment_analysis || {}, ha = d.hashtag_analysis || {}, sc = d.schedule_analysis || {};
      const gh = (d.growth_history || []).map(p => ({ label: String(p.date || '').slice(5, 10), full: p.date, value: num(p.followers) }));
      return [
        gh.length ? { title: t('Takipçi büyümesi'), sub: t('TAHMİNİ — araç geçmiş veri tutmaz; mevcut günlük ortalamadan geriye doğrusal projeksiyon'), type: 'line', data: gh, dashed: (d.growth_history || []).some(p => p.estimated), unit: t('takipçi'), wide: true } : null,
        { title: t('En çok yorum yapanlar'), sub: t('İlk {n} video · ilişki grafiğinde yorumcu → hesap', { n: ca.videos_scanned || '—' }), type: 'hbar', data: (ca.top_commenters || []).map(c => ({ label: '@' + c.username, value: +c.total_comments || 0, sub: t('{n} farklı videoda', { n: c.video_count }), href: `https://www.tiktok.com/@${c.username}` })), unit: t('yorum'), limit: 15 },
        { title: t('Etiketler'), type: 'hbar', data: pairs(ha.top_tags).map(x => ({ ...x, label: '#' + x.label })), unit: t('kullanım') },
        { title: t('Bahsedilen hesaplar'), sub: t('Video açıklamalarında @'), type: 'hbar', data: pairs((d.mention_network || {}).top).map(x => ({ ...x, label: '@' + x.label })), unit: t('bahsetme') },
        { title: t('Paylaşım saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(sc.hour_dist), xName: t('Saat||hour'), unit: t('video') },
        { title: t('Paylaşım günleri'), type: 'bar', data: daySeries(sc.day_dist), unit: t('video') },
        { title: t('En çok izlenen videolar'), type: 'hbar', data: [...(d.videos || [])].sort((a, b) => b.views - a.views).map(v => ({ label: v.title, value: +v.views || 0, href: v.url, sub: t('{likes} beğeni · {comments} yorum', { likes: fmt(v.likes), comments: fmt(v.comments) }) })), unit: t('izlenme'), limit: 10, labelWidth: 220 },
        sentiment(ca.sentiment) && { title: t('Yorum duygu dağılımı'), sub: t('Sözlük tabanlı basit sınıflandırma'), ...sentiment(ca.sentiment) },
        { title: t('Niş puanları'), type: 'hbar', data: pairs(ha.niche_scores), unit: t('puan') },
      ].filter(Boolean);
    },
    findings: d => {
      const bl = d.bio_link || {}, pf = d.posting_frequency || {}, ca = d.comment_analysis || {}, w = bl.whois || {};
      return [
        kv(t('Kimlik'), [[t('Kullanıcı'), d.username], [t('Görünen ad'), d.display_name], [t('Kullanıcı ID'), d.user_id], [t('Bölge'), d.region], [t('Dil'), d.language],
          [t('Oluşturma'), unixDate(d.create_time)], [t('Doğrulanmış'), d.verified ? t('Evet') : t('Hayır')], [t('Gizli hesap'), d.private ? t('Evet') : t('Hayır')],
          [t('Sahte takipçi skoru'), d.fake_score != null ? `${d.fake_score}/100 · ${riskTr(d.fake_label)}` : null], [t('Profil'), d.profile_url]]),
        has(bl) ? kv(t('Bio linki'), [[t('Orijinal'), bl.original_url], [t('Son adres'), bl.final_url], [t('Alan adı'), bl.domain], ['HTTP', bl.http_code],
          [t('Yönlendirme zinciri'), (bl.redirect_chain || []).join(' → ')], [t('WHOIS kayıt eden'), w.registrar], [t('WHOIS oluşturma'), w.created], [t('WHOIS ülke'), w.country], [t('WHOIS kurum'), w.org], [t('Hata'), bl.error]]) : null,
        kv(t('Paylaşım sıklığı'), [[t('Son paylaşım'), pf.last_post_date], [t('Kaç gün önce'), pf.last_post_days_ago], [t('Son 30 gün'), pf.videos_last_30d], [t('Son 90 gün'), pf.videos_last_90d],
          [t('Ortalama aralık'), pf.avg_gap_days != null ? t('{n} gün', { n: pf.avg_gap_days }) : null], [t('Aktivite skoru'), pf.activity_score], [t('Hayalet hesap'), pf.ghost_account ? t('Evet') : null]]),
        table(t('Videolar'), [t('Tarih'), t('Başlık'), t('İzlenme'), t('Beğeni'), t('Yorum'), t('Paylaşım')], (d.videos || []).map(v => [unixDate(v.date), { href: v.url, text: clip(v.title, 90) }, fmt(v.views), fmt(v.likes), fmt(v.comments), fmt(v.shares)])),
        table(t('En çok beğenilen yorumlar'), [t('Yazar'), t('Yorum'), t('Beğeni'), t('Duygu')], (ca.top_liked || []).map(c => [{ href: `https://www.tiktok.com/@${c.author}`, text: '@' + c.author }, c.text, fmt(c.likes), c.sentiment])),
      ].filter(Boolean);
    },
  };
  const tiktok = {
    id: 'tiktok', name: 'TikTok', mark: 'TT',
    desc: t('Profil, videolar, yorumcular, etiket ve bahsetme ağı, bio linki. Birden fazla hesap karşılaştırılabilir.'),
    examples: ['charlidamelio', '@khaby.lame', 'https://www.tiktok.com/@zachking'],
    placeholder: t('kullanıcı adı veya profil URL’si'), max: 5, videoOpt: { min: 5, max: 35, def: 20 }, compare: true,
    header: d => d.compare_mode ? { title: t('Karşılaştırma · {n} profil', { n: d.compared_count }), handle: (d.profiles || []).map(p => '@' + p.username).join('  '), badges: [{ t: t('Karşılaştırma modu'), c: 'accent' }], mono: 'VS' }
      : { avatar: d.profile_image, title: d.display_name || d.username, handle: '@' + d.username, url: d.profile_url, bio: d.bio === '(empty)' ? '' : d.bio,
        badges: [d.verified && { t: t('Doğrulanmış'), c: 'accent' }, d.private && { t: t('Gizli hesap'), c: 'warn' }, d.region && d.region !== 'N/A' && { t: d.region },
          d.fake_label && { t: t('Sahte takipçi: {label}', { label: riskTr(d.fake_label) }), c: riskCls(d.fake_label) }].filter(Boolean) },
    kpis: d => d.compare_mode ? [] : tiktokSingle.kpis(d),
    charts: d => d.compare_mode ? [
      { title: t('Takipçi'), type: 'hbar', data: d.profiles.map(p => ({ label: '@' + p.username, value: +p.followers || 0 })), unit: t('takipçi') },
      { title: t('Toplam beğeni'), type: 'hbar', data: d.profiles.map(p => ({ label: '@' + p.username, value: +p.likes || 0 })), unit: t('beğeni') },
      { title: t('Etkileşim oranı'), type: 'hbar', data: d.profiles.map(p => ({ label: '@' + p.username, value: +p.engagement_rate || 0, display: pct(p.engagement_rate) })), unit: '%' },
      { title: t('Sahte takipçi skoru'), type: 'hbar', data: d.profiles.map(p => ({ label: '@' + p.username, value: +p.fake_score || 0 })), unit: '/100' },
    ] : tiktokSingle.charts(d),
    media: d => { const u = d.compare_mode ? null : d.username; return u ? [{ title: t('Büyüme grafiği (sunucu PNG)'), endpoint: `/api/socmint/tiktok/growth/${encodeURIComponent(u)}`, file: `tiktok_growth_${u}.png`, note: t('Aracın kendi ürettiği grafik. Değerler TAHMİNİDİR (geriye doğrusal projeksiyon). Araç sunucuda yeniden çalışır.') }] : []; },
    findings: d => d.compare_mode ? [
      table(t('Karşılaştırma'), [t('Hesap'), t('Takipçi'), t('Beğeni'), t('Video'), t('Etkileşim'), t('Günlük takipçi'), t('Sahte skor'), t('Bölge')],
        d.profiles.map(p => [{ href: p.profile_url, text: '@' + p.username }, fmt(p.followers), fmt(p.likes), fmt(p.video_count), pct(p.engagement_rate), fmt(p.followers_per_day), `${p.fake_score ?? '—'} · ${riskTr(p.fake_label)}`, p.region])),
      ...d.profiles.flatMap(p => tiktokSingle.findings(p).slice(0, 1).map(s => ({ ...s, title: `@${p.username} — ${s.title}` }))),
    ] : tiktokSingle.findings(d),
  };

  // ═══════════════════ YouTube ═══════════════════
  const YT_DURATION = { 'short(<4min)': t('Kısa (<4 dk)'), 'medium(4-20min)': t('Orta (4–20 dk)'), 'long(20min+)': t('Uzun (20+ dk)') };
  const ytSingle = {
    kpis: d => {
      const c = d.channel || {}, va = d.video_analysis || {};
      return [{ k: t('Abone'), v: fmt(c.subscribers) }, { k: t('Toplam izlenme'), v: fmt(c.total_views) }, { k: t('Video'), v: fmt(c.video_count) },
        { k: t('Video başı izlenme'), v: fmt(c.avg_views_per_video) }, { k: t('Günlük abone'), v: fmt(c.subs_per_day), s: t('kanal ömrü ortalaması') },
        { k: t('Etkileşim (son videolar)'), v: pct(va.avg_engagement_pct) }, { k: t('Kanal yaşı'), v: c.account_age || '—', s: c.created_date }, { k: t('Ülke'), v: c.country || '—' }];
    },
    charts: d => {
      const va = d.video_analysis || {}, ca = d.comment_analysis || {};
      return [
        { title: t('En çok yorum yapanlar'), sub: t('Son {n} video, video başına ilk 50 yorum · görünen ad', { n: ca.videos_scanned || '—' }), type: 'hbar', data: (ca.top_commenters || []).map(c => ({ label: c.author, value: +c.count || 0 })), unit: t('yorum'), labelWidth: 180 },
        { title: t('Yükleme saatleri'), sub: t('UTC · tahmini saat dilimi: {tz}', { tz: va.timezone_est || '—' }), type: 'bar', data: hourSeries(va.hour_distribution), xName: t('Saat||hour'), unit: t('video') },
        { title: t('Yükleme günleri'), type: 'bar', data: daySeries(va.day_distribution), unit: t('video') },
        { title: t('En çok izlenen videolar'), type: 'hbar', data: (va.top_by_views || []).map(v => ({ label: v.title, value: +v.views || 0, href: v.url, sub: t('{likes} beğeni · {date}', { likes: fmt(v.likes), date: v.date }) })), unit: t('izlenme'), labelWidth: 220 },
        { title: t('Etiketler'), type: 'hbar', data: pairs(va.top_tags).map(x => ({ ...x, label: '#' + x.label })), unit: t('video') },
        { title: t('Video süreleri'), type: 'hbar', data: pairs(va.duration_buckets).map(x => ({ ...x, label: YT_DURATION[x.label] || x.label })), unit: t('video') },
        sentiment(ca.sentiment) && { title: t('Yorum duygu dağılımı'), sub: t('Sözlük tabanlı basit sınıflandırma'), ...sentiment(ca.sentiment) },
        { title: t('Kategoriler'), type: 'hbar', data: pairs(va.top_categories), unit: t('video') },
      ].filter(Boolean);
    },
    findings: d => {
      const c = d.channel || {}, bl = d.bio_links || {}, bd = d.bio_data || {}, va = d.video_analysis || {}, ca = d.comment_analysis || {}, fs = d.fake_score || {};
      const socials = [...(bl.social_accounts || []), ...(bd.social_accounts || [])];
      return [
        kv(t('Kanal'), [[t('Başlık'), c.title], ['Handle', c.handle], [t('Kanal ID'), d.channel_id], ['URL', c.channel_url || d.channel_url], [t('Ülke'), c.country], [t('Oluşturma'), c.created_date],
          [t('Uzun video izni'), c.verified == null ? null : (c.verified ? t('Var') : t('Yok'))], [t('Çocuklara yönelik'), c.made_for_kids ? t('Evet') : t('Hayır')], [t('Anahtar kelimeler'), c.keywords],
          [t('Wayback kayıt sayısı'), (d.wayback || {}).snapshots], [t('Tarama||at'), d.scanned_at]]),
        list(t('Sosyal hesaplar'), socials.map(s => L(s.handle || s.url, s.url, [s.platform || '', s.verified ? t('Hakkında linki') : t('açıklama')].join(' · ')))),
        table(t('Açıklamadaki linkler'), [t('Orijinal'), t('Son adres'), 'HTTP'], (bl.links || []).map(l => [{ href: l.original, text: l.original }, l.final || (l.error ? t('erişilemedi') : '—'), l.http_code || '—'])),
        list(t('E-postalar'), (bd.emails || []).map(e => L(e, 'mailto:' + e))),
        list(t('Sahte abone sinyalleri'), (fs.flags || []).map(f => L(f, null, t('sinyal'))), fs.label ? t('Skor: {score}/100 · {label}', { score: fs.score, label: riskTr(fs.label) }) : null),
        table(t('En çok beğenilen yorumlar'), [t('Yazar'), t('Yorum'), t('Beğeni'), t('Tarih')], (ca.top_liked_comments || []).map(x => [x.author, x.text, fmt(x.likes), x.date])),
        table(t('Son videolar'), [t('Tarih'), t('Başlık'), t('İzlenme'), t('Beğeni'), t('Yorum'), t('Süre')], (va.latest_videos || []).map(v => [v.date, { href: v.url, text: v.title }, fmt(v.views), fmt(v.likes), fmt(v.comments), v.duration])),
        table(t('Viral videolar (medyanın 5 katı)'), [t('Tarih'), t('Başlık'), t('İzlenme')], (va.viral_videos || []).map(v => [v.date, { href: v.url, text: v.title }, fmt(v.views)])),
        table(t('Oynatma listeleri'), [t('Başlık'), t('Video'), t('Bağlantı')], (d.playlists || []).map(p => [p.title, fmt(p.video_count), { href: p.url, text: t('Aç') }])),
        kv(t('Açıklama'), [[t('Metin'), c.description]]),
      ];
    },
  };
  const youtube = {
    id: 'youtube', name: 'YouTube', mark: 'YT',
    desc: t('Kanal, video analizi, en çok yorum yapanlar, Hakkında sayfasındaki sosyal hesaplar. API anahtarı gerekir.'),
    examples: ['@MrBeast', 'https://youtube.com/@Veritasium', 'UCX6OQ3DkcsbYNE6H8uQQuVA'],
    placeholder: t('@handle, kanal URL’si veya kanal ID (UC…)'), max: 5, videoOpt: { min: 5, max: 50, def: 20 }, compare: true, needsKey: true,
    header: d => {
      if (d.compare_mode) return { title: t('Karşılaştırma · {n} kanal', { n: d.compared_count }), handle: (d.profiles || []).map(p => (p.channel || {}).handle || p.target).join('  '), badges: [{ t: t('Karşılaştırma modu'), c: 'accent' }], mono: 'VS' };
      const c = d.channel || {}, fs = d.fake_score || {};
      return { title: c.title, handle: c.handle, url: c.channel_url || d.channel_url, bio: clip(c.description, 420),
        badges: [c.country && { t: c.country }, c.made_for_kids && { t: t('Çocuklara yönelik'), c: 'warn' }, fs.label && { t: t('Sahte abone: {label}', { label: riskTr(fs.label) }), c: riskCls(fs.label) }].filter(Boolean) };
    },
    kpis: d => d.compare_mode ? [] : ytSingle.kpis(d),
    charts: d => d.compare_mode ? [
      { title: t('Abone'), type: 'hbar', data: d.profiles.map(p => ({ label: (p.channel || {}).title || p.target, value: +(p.channel || {}).subscribers || 0 })), unit: t('abone') },
      { title: t('Toplam izlenme'), type: 'hbar', data: d.profiles.map(p => ({ label: (p.channel || {}).title || p.target, value: +(p.channel || {}).total_views || 0 })), unit: t('izlenme') },
      { title: t('Ortalama izlenme (son videolar)'), type: 'hbar', data: d.profiles.map(p => ({ label: (p.channel || {}).title || p.target, value: +(p.video_analysis || {}).avg_views || 0 })), unit: t('izlenme') },
      { title: t('Etkileşim oranı'), type: 'hbar', data: d.profiles.map(p => ({ label: (p.channel || {}).title || p.target, value: +(p.video_analysis || {}).avg_engagement_pct || 0, display: pct((p.video_analysis || {}).avg_engagement_pct) })), unit: '%' },
    ] : ytSingle.charts(d),
    findings: d => d.compare_mode ? [
      table(t('Karşılaştırma'), [t('Kanal'), t('Abone'), t('İzlenme'), t('Video'), t('Ort. izlenme'), t('Etkileşim'), t('Sahte skor'), t('Ülke')],
        d.profiles.map(p => { const c = p.channel || {}, va = p.video_analysis || {}, fs = p.fake_score || {};
          return [{ href: c.channel_url, text: c.title || p.target }, fmt(c.subscribers), fmt(c.total_views), fmt(c.video_count), fmt(va.avg_views), pct(va.avg_engagement_pct), `${fs.score ?? '—'} · ${riskTr(fs.label)}`, c.country]; })),
    ] : ytSingle.findings(d),
  };


  // ═══════════════════ Telegram ═══════════════════
  const TG_KIND = { channel: t('Kanal'), group: t('Grup'), user: t('Kullanıcı'), bot: 'Bot' };
  const TG_MEDIA = { text: t('Metin'), photo: t('Fotoğraf'), video: 'Video', document: t('Dosya'), poll: t('Anket') };
  const telegram = {
    id: 'telegram', name: 'Telegram', mark: 'TG',
    desc: t('Herkese açık kanal, grup ve kullanıcı sayfaları; kanal gönderileri, iletilen kaynaklar, bahsedilen hesaplar.'),
    examples: ['durov', '@telegram', 'https://t.me/s/telegram'],
    placeholder: t('kullanıcı adı veya t.me bağlantısı'), max: 10,
    header: d => ({ avatar: d.photo, title: d.title || d.username, handle: '@' + d.username, url: d.url, bio: d.description,
      badges: [{ t: TG_KIND[d.kind] || d.kind }, d.verified && { t: t('Doğrulanmış'), c: 'accent' }, d.kind === 'channel' && !d.public_preview && { t: t('Önizleme kapalı'), c: 'warn' }].filter(Boolean) }),
    kpis: d => { const a = d.analysis || {}, c = d.counters || {};
      return [{ k: d.kind === 'group' ? t('Üye') : t('Abone'), v: fmt(d.subscribers), s: d.online ? t('{n} çevrimiçi', { n: fmt(d.online) }) : '' },
        { k: t('İncelenen gönderi'), v: fmt(a.posts_analyzed) }, { k: t('Ort. görüntülenme'), v: fmt(a.avg_views) }, { k: t('En yüksek'), v: fmt(a.max_views) },
        { k: t('Günlük gönderi'), v: a.posts_per_day != null ? String(a.posts_per_day).replace('.', decSep) : '—' },
        { k: t('Fotoğraf / link'), v: `${fmt(c.photos)} / ${fmt(c.links)}` }, { k: t('İlk incelenen'), v: isoDate(a.first_post) }, { k: t('Son gönderi'), v: isoDate(a.last_post) }]; },
    charts: d => { const a = d.analysis || {};
      return [
        { title: t('Gönderi saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(a.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
        { title: t('Gönderi günleri'), type: 'bar', data: daySeries(a.day_distribution), unit: t('gönderi') },
        { title: t('İletilen kaynaklar'), sub: t('Başka kanallardan iletilen gönderiler'), type: 'hbar', data: pairs(a.top_forward_sources).map(x => ({ ...x, label: '@' + x.label, href: `https://t.me/${x.label}` })), unit: t('gönderi') },
        { title: t('Bahsedilen hesaplar'), type: 'hbar', data: pairs(a.top_mentions).map(x => ({ ...x, label: '@' + x.label, href: `https://t.me/${x.label}` })), unit: t('bahsetme') },
        { title: t('Etiketler'), type: 'hbar', data: pairs(a.top_hashtags).map(x => ({ ...x, label: '#' + x.label })), unit: t('gönderi') },
        { title: t('Paylaşılan alan adları'), type: 'hbar', data: pairs(a.top_domains), unit: t('link') },
        { title: t('İçerik türü'), type: 'hbar', data: pairs(a.media).map(x => ({ ...x, label: TG_MEDIA[x.label] || x.label })), unit: t('gönderi') },
      ]; },
    findings: d => [
      kv(t('Hesap'), [[t('Kullanıcı adı'), '@' + d.username], [t('Başlık'), d.title], [t('Tür'), TG_KIND[d.kind] || d.kind], [t('Sayfa bilgisi'), d.extra], [t('Bağlantı'), d.url]]),
      list(t('Açıklamadaki bağlantılar'), [...(d.description_emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))),
        ...(d.description_socials || []).map(s => L(s.handle, s.url, s.platform)), ...(d.description_links || []).map(u => L(u, u, 'url')),
        ...(d.description_mentions || []).map(m => L('@' + m, `https://t.me/${m}`, 'telegram'))]),
      table(t('Gönderiler'), [t('Tarih'), t('Metin'), t('Görüntülenme'), t('İletilen'), t('Bağlantı')], (d.posts || []).map(p => [isoDate(p.date), clip(p.text, 140) || t('(medya)'), fmt(p.views),
        p.forwarded_from ? (p.forwarded_from.username ? '@' + p.forwarded_from.username : p.forwarded_from.name) : '', { href: p.url, text: t('Aç') }])),
    ],
  };

  // ═══════════════════ Keybase ═══════════════════
  const PROOF_TR = { twitter: 'Twitter/X', github: 'GitHub', reddit: 'Reddit', hackernews: 'Hacker News', facebook: 'Facebook', generic_web_site: t('Web sitesi'), dns: 'DNS' };
  const keybase = {
    id: 'keybase', name: 'Keybase', mark: 'KB',
    desc: t('Kriptografik kanıtla doğrulanmış hesaplar, PGP anahtarı, kripto adresleri, takip ağı.'),
    examples: ['chris', 'github:torvalds', 'twitter:jack'],
    placeholder: t('kullanıcı adı veya github:, twitter:, reddit:, hackernews:, domain:'), max: 10,
    header: d => ({ avatar: d.picture, title: d.full_name || d.username, handle: '@' + d.username, url: d.profile_url, bio: d.bio,
      badges: [{ t: t('{n} kanıt', { n: (d.proofs || []).length }), c: 'accent' }, d.location && { t: d.location }, d.lookup && d.lookup.field !== 'usernames' && { t: `${d.lookup.field}: ${d.lookup.value}` }].filter(Boolean) }),
    kpis: d => [{ k: t('Kanıtlı hesap'), v: fmt((d.proofs || []).length) }, { k: t('PGP anahtarı||count'), v: fmt((d.pgp_keys || []).length) },
      { k: t('Kripto adres'), v: fmt(Object.values(d.crypto || {}).flat().length) }, { k: t('Cihaz'), v: fmt((d.devices || []).length) },
      { k: t('Takipçi'), v: fmt((d.followers || []).length) }, { k: t('Takip'), v: fmt((d.following || []).length) }, { k: t('Oluşturma'), v: isoDate(d.created) }],
    charts: d => [{ title: t('Kanıt türleri'), type: 'hbar', data: pairs((d.proofs || []).reduce((m, p) => { const k = PROOF_TR[p.type] || p.type; m[k] = (m[k] || 0) + 1; return m; }, {})), unit: t('kanıt') }],
    findings: d => [
      table(t('Doğrulanmış hesaplar'), [t('Tür'), t('Hesap'), t('Durum'), t('Kanıt')], (d.proofs || []).map(p => [PROOF_TR[p.type] || p.type, p.service_url ? { href: p.service_url, text: p.nametag } : p.nametag,
        p.state === 1 ? t('Geçerli') : `state=${p.state}`, p.proof_url || p.human_url ? { href: p.proof_url || p.human_url, text: t('Kanıt') } : '—'])),
      table(t('PGP anahtarları'), [t('Parmak izi'), t('Oluşturma'), 'Bit'], (d.pgp_keys || []).map(k => [String(k.fingerprint || '').toUpperCase(), isoDate(k.ctime), k.bits || '—'])),
      list(t('Kripto adresleri'), Object.entries(d.crypto || {}).flatMap(([c, xs]) => xs.map(x => L(x, null, c)))),
      list('Bio', [...(d.bio_emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))), ...(d.bio_socials || []).map(s => L(s.handle, s.url, s.platform))]),
      table(t('Cihazlar'), [t('Ad'), t('Tür'), t('Eklenme')], (d.devices || []).map(x => [x.name, x.type, isoDate(x.ctime)])),
      table(t('Takipçiler'), [t('Kullanıcı'), t('Ad')], (d.followers || []).map(f => [{ href: `https://keybase.io/${f.username}`, text: '@' + f.username }, f.full_name])),
      table(t('Takip ettikleri'), [t('Kullanıcı'), t('Ad')], (d.following || []).map(f => [{ href: `https://keybase.io/${f.username}`, text: '@' + f.username }, f.full_name])),
    ],
  };

  // ═══════════════════ Steam ═══════════════════
  const STEAM_PRIVACY = { public: t('Herkese açık'), private: t('Gizli'), friendsonly: t('Yalnızca arkadaşlar') };
  const steam = {
    id: 'steam', name: 'Steam', mark: 'ST',
    desc: t('Profil, eski kullanıcı adları, gruplar, arkadaş listesi ve oyunlar. API anahtarı ile daha fazla veri.'),
    examples: ['gabelogannewell', '76561197960287930', 'https://steamcommunity.com/id/gabelogannewell'],
    placeholder: t('özel URL adı, SteamID64 veya profil bağlantısı'), max: 10,
    header: d => ({ avatar: d.avatar, title: d.persona || d.custom_url || d.steamid, handle: d.custom_url ? '@' + d.custom_url : d.steamid, url: d.profile_url, bio: d.summary,
      badges: [d.privacy && { t: STEAM_PRIVACY[d.privacy] || d.privacy },
        (d.vac_banned || ((d.bans || {}).vac > 0)) && { t: t('VAC yasağı'), c: 'critical' }, d.limited && { t: t('Sınırlı hesap'), c: 'warn' },
        { t: d.source === 'api' ? 'Web API' : t('Herkese açık profil') }].filter(Boolean) }),
    kpis: d => [{ k: t('Seviye'), v: d.level != null ? String(d.level) : '—' }, { k: t('Arkadaş'), v: fmt((d.friends || []).length) }, { k: t('Grup'), v: fmt((d.groups || []).length) },
      { k: t('Oyun'), v: fmt((d.games || {}).count) }, { k: t('Son 2 hafta'), v: d.hours_2w != null ? t('{n} sa', { n: d.hours_2w }) : '—' },
      { k: t('Üyelik'), v: d.member_since || isoDate(d.time_created) }, { k: t('Konum'), v: d.location || d.country || '—' }, { k: t('Eski ad'), v: fmt((d.aliases || []).length) }],
    charts: d => [
      { title: t('En çok oynanan oyunlar'), type: 'hbar', data: ((d.games || {}).top || d.most_played || []).map(g => ({ label: g.name, value: +g.hours || 0, display: t('{n} sa', { n: fmt(g.hours) }) })), unit: t('saat'), labelWidth: 200 },
      { title: t('Arkadaşların ülkeleri'), type: 'hbar', data: pairs((d.friends || []).reduce((m, f) => { if (f.country) m[f.country] = (m[f.country] || 0) + 1; return m; }, {})), unit: t('arkadaş||unit') },
      { title: t('Grupların üye sayısı'), type: 'hbar', data: (d.groups || []).map(g => ({ label: g.name, value: +g.members || 0 })), unit: t('üye||unit'), labelWidth: 200 },
    ],
    findings: d => [
      kv(t('Profil'), [['SteamID64', d.steamid], [t('Görünen ad'), d.persona], [t('Özel URL'), d.custom_url], [t('Gerçek ad'), d.real_name], [t('Konum'), d.location],
        [t('Ülke'), d.country], [t('Üyelik'), d.member_since || isoDate(d.time_created)], [t('Son çıkış'), isoDate(d.last_logoff)], [t('Durum'), d.persona_state || d.online_state],
        [t('Oynuyor'), d.playing], [t('Takas yasağı'), d.trade_ban && d.trade_ban !== 'None' ? d.trade_ban : null], [t('Profil'), d.profile_url]]),
      d.bans ? kv(t('Yasaklar'), [['VAC', fmt(d.bans.vac)], [t('Oyun'), fmt(d.bans.game)], [t('Topluluk'), d.bans.community ? t('Evet') : t('Hayır')], [t('Ekonomi'), d.bans.economy], [t('Son yasaktan beri'), d.bans.days_since_last ? t('{n} gün', { n: d.bans.days_since_last }) : null]]) : null,
      table(t('Eski kullanıcı adları'), [t('Ad'), t('Değişiklik||date')], (d.aliases || []).map(a => [a.name, a.changed])),
      list(t('Profil özetindeki hesaplar'), [...(d.summary_socials || []).map(s => L(s.handle, s.url, s.platform)), ...(d.summary_emails || []).map(e => L(e, 'mailto:' + e, t('e-posta')))]),
      table(t('Arkadaşlar'), [t('Ad'), 'SteamID64', t('Arkadaşlık'), t('Ülke')], (d.friends || []).map(f => [{ href: f.profile_url, text: f.name || f.steamid }, f.steamid, isoDate(f.since), f.country || '—'])),
      table(t('Gruplar'), [t('Grup'), t('Üye'), t('Birincil')], (d.groups || []).map(g => [g.url ? { href: `https://steamcommunity.com/groups/${g.url}`, text: g.name } : g.name, fmt(g.members), g.primary ? t('Evet') : ''])),
    ].filter(Boolean),
  };

  // ═══════════════════ Gravatar ═══════════════════
  const GRAV_SOURCE = { v3: 'v3 API', legacy: t('Eski JSON'), avatar: 'Avatar' };
  const gravatar = {
    id: 'gravatar', name: 'Gravatar', mark: 'GR',
    desc: t('E-postadan profil, avatar ve bağlı hesaplar. E-posta düğümlerinden doğrudan buraya geçilebilir.'),
    examples: [t('kisi@ornek.com'), 'beau', '205e460b479e2e5b48aec07710c08d50'],
    placeholder: t('e-posta, MD5/SHA-256 hash veya kullanıcı adı'), max: 10,
    header: d => ({ avatar: d.avatar_url, title: d.display_name || d.name || d.username || d.input, handle: d.email || (d.username ? '@' + d.username : d.md5), url: d.profile_url, bio: d.about,
      badges: [{ t: d.profile_found ? t('Profil var') : t('Yalnızca avatar'), c: d.profile_found ? 'accent' : 'warn' }, d.location && { t: d.location }, d.company && { t: d.company }].filter(Boolean) }),
    kpis: d => [{ k: t('Bağlı hesap'), v: fmt((d.accounts || []).length) }, { k: t('Bağlantı'), v: fmt((d.links || []).length) }, { k: t('Kripto'), v: fmt((d.crypto || []).length) },
      { k: 'Avatar', v: d.has_avatar ? t('Var') : t('Yok') }, { k: t('Kaynak'), v: GRAV_SOURCE[d.source] || '—' }],
    charts: () => [],
    findings: d => [
      kv(t('Kimlik'), [[t('Girdi'), d.input], [t('E-posta'), d.email], ['MD5', d.md5], ['SHA-256', d.sha256], [t('Ad'), d.name], [t('Görünen ad'), d.display_name], [t('Kullanıcı adı'), d.username],
        [t('Konum'), d.location], [t('Unvan'), d.job_title], [t('Şirket'), d.company], [t('Zaman dilimi'), d.timezone], [t('Kayıt'), isoDate(d.registration_date)], [t('Profil'), d.profile_url]]),
      table(t('Bağlı hesaplar'), [t('Servis'), t('Hesap'), t('Doğrulanmış')], (d.accounts || []).map(a => [a.service, a.url ? { href: a.url, text: a.username || a.url } : a.username, a.verified ? t('Evet') : ''])),
      list(t('Bağlantılar'), (d.links || []).map(l => L(l.url, l.url, l.title))),
      list(t('Diğer tanımlayıcılar'), [...(d.emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))), ...(d.phones || []).map(p => L(p, null, t('telefon'))), ...(d.crypto || []).map(c => L(c.address, null, c.label))]),
    ],
  };

  // ═══════════════════ GitLab ═══════════════════
  const gitlab = {
    id: 'gitlab', name: 'GitLab', mark: 'GL',
    desc: t('Profil, projeler, commit e-postaları, gruplar ve takip ağı. Kurum içi GitLab adresi de verilebilir.'),
    examples: ['gitlab-bot', 'https://gitlab.com/gitlab-bot'],
    placeholder: t('kullanıcı adı veya profil bağlantısı'), max: 10,
    header: d => ({ avatar: d.avatar_url, title: d.name || d.username, handle: '@' + d.username, url: d.web_url, bio: d.bio,
      badges: [d.organization && { t: d.organization }, d.location && { t: d.location }, d.bot && { t: 'Bot', c: 'warn' },
        d.base_url && !/gitlab\.com$/.test(d.base_url) && { t: d.base_url.replace(/^https?:\/\//, ''), c: 'accent' }].filter(Boolean) }),
    kpis: d => [{ k: t('Proje'), v: fmt((d.projects || []).length) }, { k: t('Toplam yıldız'), v: fmt((d.projects || []).reduce((s, p) => s + (p.stars || 0), 0)) },
      { k: t('Takipçi'), v: fmt(d.followers_count ?? (d.followers || []).length) }, { k: t('Takip'), v: fmt(d.following_count ?? (d.following || []).length) },
      { k: t('Commit e-postası'), v: fmt((d.commit_emails || []).filter(e => !e.noreply).length) }, { k: t('Etkinlik'), v: fmt((d.activity || {}).events) }, { k: t('Oluşturma'), v: isoDate(d.created_at) }],
    charts: d => { const a = d.activity || {};
      return [
        { title: t('Etkinlik saatleri'), sub: t('UTC · son 100 etkinlik'), type: 'bar', data: hourSeries(a.hour_distribution), xName: t('Saat||hour'), unit: t('etkinlik') },
        { title: t('Etkinlik günleri'), type: 'bar', data: daySeries(a.day_distribution), unit: t('etkinlik') },
        { title: t('Commit e-postaları'), sub: t('Kendi projelerindeki son commitler'), type: 'hbar', data: (d.commit_emails || []).map(e => ({ label: e.email, value: e.count, sub: (e.names || []).join(', ') })), unit: t('commit'), labelWidth: 220 },
        { title: t('Projeler — yıldız'), type: 'hbar', data: (d.projects || []).map(p => ({ label: p.path, value: +p.stars || 0, href: p.url })), unit: t('yıldız'), labelWidth: 200 },
        { title: t('Etkinlik türleri'), type: 'hbar', data: pairs(a.actions), unit: t('etkinlik') },
      ]; },
    findings: d => [
      kv(t('Profil'), [[t('Kullanıcı'), d.username], [t('Ad'), d.name], ['ID', d.id], [t('Durum'), d.state], [t('Profil e-postası'), d.public_email], [t('Web sitesi'), d.website_url],
        [t('Kurum'), d.organization], [t('Unvan'), d.job_title], [t('Konum'), d.location], ['Twitter', d.twitter], ['LinkedIn', d.linkedin], ['Discord', d.discord], ['Skype', d.skype],
        [t('Yerel saat'), d.local_time], [t('Oluşturma'), isoDate(d.created_at)], [t('Sunucu||server'), d.base_url]]),
      table(t('Commit e-postaları'), [t('E-posta'), t('Commit adları'), t('Commit'), t('Repolar'), t('Hedefe ait olabilir')], (d.commit_emails || []).map(e => [e.email, (e.names || []).join(', '), fmt(e.count), (e.repos || []).join(', '), e.noreply ? 'noreply' : (e.likely_self ? t('Evet') : '')])),
      table(t('Projeler'), [t('Proje'), t('Yıldız'), 'Fork', t('Son etkinlik'), t('Konular')], (d.projects || []).map(p => [{ href: p.url, text: p.path + (p.fork ? ' (fork)' : '') }, fmt(p.stars), fmt(p.forks), isoDate(p.last_activity), (p.topics || []).join(', ')])),
      table(t('Gruplar'), [t('Grup'), t('Proje')], (d.groups || []).map(g => [{ href: `${d.base_url}/${g.path}`, text: g.path }, fmt(g.projects)])),
      list(t('Sosyal hesaplar'), (d.socials || []).map(s => L(s.handle, s.url, s.platform))),
      table(t('Takipçiler'), [t('Kullanıcı'), t('Ad')], (d.followers || []).map(f => [{ href: f.url, text: '@' + f.username }, f.name])),
      table(t('Takip ettikleri'), [t('Kullanıcı'), t('Ad')], (d.following || []).map(f => [{ href: f.url, text: '@' + f.username }, f.name])),
      table(t('Yıldızladığı projeler'), [t('Proje'), t('Yıldız')], (d.starred || []).map(p => [{ href: p.url, text: p.path }, fmt(p.stars)])),
    ],
  };

  // ═══════════════════ Hacker News ═══════════════════
  const hackernews = {
    id: 'hackernews', name: 'Hacker News', mark: 'HN',
    desc: t('Profil, gönderi ve yorum geçmişi, yanıt verdiği kullanıcılar, paylaştığı alan adları.'),
    examples: ['pg', 'dang', 'https://news.ycombinator.com/user?id=pg'],
    placeholder: t('kullanıcı adı veya profil bağlantısı'), max: 10,
    header: d => ({ title: d.username, handle: `karma ${fmt(d.karma)}`, url: d.profile_url, bio: d.about, mono: 'HN',
      badges: [(d.kinds || {}).show_hn && { t: `${d.kinds.show_hn} Show HN` }].filter(Boolean) }),
    kpis: d => [{ k: 'Karma', v: fmt(d.karma) }, { k: t('Hesap açılışı'), v: isoDate(d.created) }, { k: t('Toplam öğe'), v: fmt(d.submitted_total) },
      { k: t('İncelenen'), v: fmt(d.items_analyzed) }, { k: t('Hikâye||count'), v: fmt((d.kinds || {}).story) }, { k: t('Yorum'), v: fmt((d.kinds || {}).comment) },
      { k: t('Son etkinlik'), v: isoDate((d.activity || {}).last) }],
    charts: d => [
      { title: t('En çok yanıt verdiği kullanıcılar'), sub: t('Yorumun üst öğesinin yazarı'), type: 'hbar', data: pairs(d.replied_to).map(x => ({ ...x, href: `https://news.ycombinator.com/user?id=${x.label}` })), unit: t('yanıt') },
      { title: t('Etkinlik saatleri'), sub: 'UTC', type: 'bar', data: hourSeries((d.activity || {}).hour_distribution), xName: t('Saat||hour'), unit: t('öğe') },
      { title: t('Etkinlik günleri'), type: 'bar', data: daySeries((d.activity || {}).day_distribution), unit: t('öğe') },
      { title: t('Paylaştığı alan adları'), type: 'hbar', data: pairs(d.top_domains), unit: t('hikâye') },
    ],
    findings: d => [
      list(t('About bölümü'), [...(d.about_emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))), ...(d.about_socials || []).map(s => L(s.handle, s.url, s.platform)), ...(d.about_links || []).map(u => L(u, u, 'url'))]),
      table(t('Hikâyeler'), [t('Tarih'), t('Başlık'), t('Puan'), t('Yorum'), 'HN'], (d.stories || []).map(s => [isoDate(s.date), s.url ? { href: s.url, text: s.title } : s.title, fmt(s.points), fmt(s.comments), { href: s.hn_url, text: t('Aç') }])),
      table(t('Son yorumlar'), [t('Tarih'), t('Hikâye'), t('Yanıtladığı'), t('Yorum')], (d.recent_comments || []).map(c => [isoDate(c.date), c.story, c.parent_author || '—', { href: c.hn_url, text: clip(c.text, 120) }])),
    ],
  };

  // ═══════════════════ Stack Exchange ═══════════════════
  const stackexchange = {
    id: 'stackexchange', name: 'Stack Exchange', mark: 'SE',
    desc: t('Profil, ağdaki diğer sitelerdeki hesaplar, etiketler, yanıt verdiği kullanıcılar.'),
    examples: ['https://stackoverflow.com/users/22656/jon-skeet', '22656', 'superuser:12345'],
    placeholder: t('profil bağlantısı, site:id, sayısal id veya ad'), max: 10,
    header: d => ({ avatar: d.profile_image, title: d.display_name, handle: `${d.site} · #${d.user_id}`, url: d.link, bio: d.about,
      badges: [{ t: t('{n} itibar', { n: fmt(d.reputation) }), c: 'accent' }, d.location && { t: d.location }, d.is_employee && { t: t('Stack Exchange çalışanı') }].filter(Boolean) }),
    kpis: d => { const b = d.badges || {};
      return [{ k: t('İtibar'), v: fmt(d.reputation) }, { k: t('Rozet'), v: `${fmt(b.gold)} / ${fmt(b.silver)} / ${fmt(b.bronze)}`, s: t('altın / gümüş / bronz') },
        { k: t('Ağdaki hesap'), v: fmt((d.network || []).length) }, { k: t('İncelenen yanıt'), v: fmt((d.answers || []).length) }, { k: t('Soru'), v: fmt((d.questions || []).length) },
        { k: t('Üyelik'), v: isoDate(d.created) }, { k: t('Son erişim'), v: isoDate(d.last_access) }]; },
    charts: d => [
      { title: t('Etiketler'), sub: t('Yanıt sayısı'), type: 'hbar', data: (d.top_tags || []).map(tg => ({ label: tg.tag, value: +tg.answers || 0 })), unit: t('yanıt') },
      { title: t('Yanıt verdiği kullanıcılar'), sub: t('Soruları yanıtlanan kişiler'), type: 'hbar', data: (d.answered_users || []).map(a => ({ label: a.name, value: a.count, href: a.link })), unit: t('yanıt') },
      { title: t('Ağdaki hesaplar — itibar'), type: 'hbar', data: (d.network || []).map(n => ({ label: n.site, value: +n.reputation || 0, href: n.link })), unit: t('itibar'), labelWidth: 190 },
      { title: t('Etkinlik saatleri'), sub: t('UTC · yanıt ve sorular'), type: 'bar', data: hourSeries((d.activity || {}).hour_distribution), xName: t('Saat||hour'), unit: t('öğe') },
    ],
    findings: d => [
      kv(t('Profil'), [[t('Ad'), d.display_name], ['Site', d.site], [t('Kullanıcı ID'), d.user_id], [t('Hesap ID'), d.account_id], [t('Konum'), d.location], [t('Web sitesi'), d.website],
        [t('Üyelik'), isoDate(d.created)], [t('Son erişim'), isoDate(d.last_access)], [t('Kalan API kotası'), d.quota_remaining], [t('Profil'), d.link]]),
      (d.candidates || []).length > 1 ? table(t('Ada göre arama sonuçları (ilki seçildi)'), [t('Ad'), t('İtibar'), t('Profil')], d.candidates.map(c => [c.display_name, fmt(c.reputation), { href: c.link, text: t('Aç') }])) : null,
      list(t('About bölümü'), [...(d.about_emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))), ...(d.socials || []).map(s => L(s.handle, s.url, s.platform)), ...(d.about_links || []).map(u => L(u, u, 'url'))]),
      table(t('Ağdaki hesaplar'), ['Site', t('İtibar'), t('Yanıt'), t('Soru'), t('Açılış')], (d.network || []).map(n => [{ href: n.link, text: n.site }, fmt(n.reputation), fmt(n.answers), fmt(n.questions), isoDate(n.created)])),
      table(t('Son yanıtlar'), [t('Tarih'), t('Soru'), t('Skor'), t('Kabul')], (d.answers || []).map(a => [isoDate(a.date), a.link ? { href: a.link, text: a.title || a.question_id } : a.title, fmt(a.score), a.accepted ? t('Evet') : ''])),
      table(t('Sorular'), [t('Tarih'), t('Başlık'), t('Skor'), t('Etiketler')], (d.questions || []).map(q => [isoDate(q.date), { href: q.link, text: q.title }, fmt(q.score), (q.tags || []).join(', ')])),
    ].filter(Boolean),
  };

  // ═══════════════════ Wayback Machine ═══════════════════
  const wayback = {
    id: 'wayback', name: 'Wayback Machine', mark: 'WB',
    desc: t('Bir alan adının veya sayfanın arşiv geçmişi; eski kopyalardaki e-posta ve sosyal hesaplar.'),
    examples: ['example.com', 'https://example.com/about', 'https://twitter.com/jack'],
    placeholder: t('alan adı veya URL (silinmiş profil sayfaları dahil)'), max: 5,
    header: d => ({ title: d.target, handle: t('{n} kayıt · {first} → {last}', { n: fmt(d.total_captures), first: d.first_capture || '—', last: d.last_capture || '—' }), url: d.last_capture_url, mono: 'WB',
      badges: [{ t: d.is_domain ? t('Alan adı') : t('Sayfa') }, d.last_status && { t: t('Son durum {status}', { status: d.last_status }), c: String(d.last_status).startsWith('2') ? '' : 'warn' }].filter(Boolean) }),
    kpis: d => [{ k: t('Arşiv kaydı'), v: fmt(d.total_captures), s: t('günlük tekilleştirilmiş') }, { k: t('Farklı sürüm'), v: fmt(d.unique_versions) },
      { k: t('İlk kayıt'), v: d.first_capture || '—' }, { k: t('Son kayıt'), v: d.last_capture || '—' }, { k: t('Arşivli URL'), v: fmt((d.urls || []).length) },
      { k: t('E-posta'), v: fmt((d.emails || []).length) }, { k: t('Sosyal hesap'), v: fmt((d.socials || []).length) }],
    charts: d => [
      { title: t('Yıllara göre arşiv kaydı'), type: 'bar', data: Object.entries(d.years || {}).map(([y, c]) => ({ label: y.slice(2), full: y, value: +c || 0 })), unit: t('kayıt'), xName: t('Yıl') },
      { title: t('HTTP durum kodları'), type: 'hbar', data: pairs(d.status_codes), unit: t('kayıt') },
      { title: t('İçerik türleri'), type: 'hbar', data: pairs(d.mime_types), unit: t('kayıt') },
    ],
    findings: d => [
      kv(t('Özet'), [[t('Hedef'), d.target], [t('İlk kayıt'), d.first_capture_url], [t('Son kayıt'), d.last_capture_url]]),
      table(t('Arşiv kopyalarında bulunanlar'), [t('Tarih'), t('Başlık'), t('Açıklama'), t('E-posta'), t('Sosyal'), t('Arşiv')], (d.snapshots || []).map(s => [s.date, s.title || (s.error ? `(${s.error})` : '—'), clip(s.description, 120),
        (s.emails || []).join(', '), (s.socials || []).map(x => `${x.platform}:${x.handle}`).join(', '), { href: s.archive_url, text: t('Aç') }])),
      table(t('Sosyal hesaplar'), ['Platform', t('Hesap'), t('İlk görüldüğü kopya')], (d.socials || []).map(s => [s.platform, { href: s.url, text: s.handle }, s.first_seen])),
      list(t('E-postalar'), (d.emails || []).map(e => L(e, 'mailto:' + e))),
      table(t('Arşivlenmiş URL’ler'), ['URL', t('İlk kayıt'), t('Durum')], (d.urls || []).map(u => [{ href: `https://web.archive.org/web/*/${u.url}`, text: u.url }, u.first, u.status])),
      table(t('Son kayıtlar'), [t('Tarih'), t('Durum'), t('Tür'), t('Arşiv')], (d.captures || []).map(c => [c.date, c.status, c.mime, { href: c.archive_url, text: t('Aç') }])),
    ],
  };

  // ═══════════════════ X (Twitter) ═══════════════════
  const xMockBadge = d => d.mock ? [{ t: t('ÖRNEK VERİ'), c: 'warn' }] : [];
  const x = {
    id: 'x', name: 'X (Twitter)', mark: 'X',
    desc: t('Resmi X API v2 ile profil, gönderiler, bahsedilen hesaplar, etiketler ve alan adları. Token yoksa örnek veri.'),
    examples: ['nasa', '@github', 'https://x.com/jack'],
    placeholder: t('kullanıcı adı veya profil bağlantısı'), max: 10,
    header: d => ({ avatar: d.profile_image, title: d.name || d.username, handle: '@' + d.username, url: d.url, bio: d.bio,
      badges: [...xMockBadge(d), d.verified && { t: t('Doğrulanmış'), c: 'accent' }, d.protected && { t: t('Gizli hesap') }, d.location && { t: d.location }].filter(Boolean) }),
    kpis: d => [{ k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Takip'), v: fmt(d.following) }, { k: t('Gönderi'), v: fmt(d.tweet_count) },
      { k: t('Listelenme'), v: fmt(d.listed) }, { k: t('Oluşturma'), v: isoDate(d.created_at) }, { k: t('Konum'), v: d.location || '—' }],
    charts: d => [
      { title: t('Etiketler'), type: 'hbar', data: (d.hashtags || []).map(h => ({ label: '#' + h.tag, value: h.count })), unit: t('kullanım') },
      { title: t('Bahsedilen hesaplar'), type: 'hbar', data: (d.mentions || []).map(m => ({ label: '@' + m.handle, value: m.count, href: `https://x.com/${m.handle}` })), unit: t('bahsetme') },
      { title: t('Gönderi saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(d.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
      { title: t('Gönderi günleri'), type: 'bar', data: daySeries(d.day_distribution), unit: t('gönderi') },
      { title: t('Paylaşılan alan adları'), type: 'hbar', data: (d.domains || []).map(x => ({ label: x.domain, value: x.count })), unit: t('gönderi') },
    ],
    findings: d => [
      d.mock ? list(t('Bilgi'), [{ text: t('Bu sonuç örnek veridir. Gerçek veri için Ayarlar’dan X_BEARER_TOKEN girin.') }]) : null,
      kv(t('Kimlik'), [[t('Kullanıcı adı'), '@' + d.username], [t('Ad'), d.name], [t('Kullanıcı ID'), d.user_id], [t('Konum'), d.location],
        [t('Web sitesi'), d.website], [t('Doğrulanmış'), d.verified ? t('Evet') : t('Hayır')], [t('Oluşturma'), isoDate(d.created_at)], [t('Profil'), d.url]]),
      d.tweets_error ? list(t('Not'), [{ text: t('Gönderiler alınamadı (API planı izin vermiyor olabilir): {v}', { v: d.tweets_error }) }]) : null,
      table(t('Son gönderiler'), [t('Tarih'), t('Gönderi'), t('Beğeni'), 'RT', t('Yanıt')], (d.tweets || []).map(w => [isoDate(w.date), w.url ? { href: w.url, text: clip(w.text, 110) } : clip(w.text, 110), fmt(w.likes), fmt(w.retweets), fmt(w.replies)])),
      list(t('E-postalar'), (d.emails || []).map(e => L(e, 'mailto:' + e))),
    ].filter(Boolean),
  };

  // ═══════════════════ LinkedIn ═══════════════════
  const liSrc = d => d.source_used === 'live' ? t('Canlı sayfa') : t('Arşiv kopyası {date}', { date: d.source_date || '' });
  const liPeriod = o => [o.start, o.end].filter(Boolean).join(' – ') || '—';
  const LI_FIELD = { Unvan: t('Unvan'), Şirket: t('Şirket'), Konum: t('Konum'), Ad: t('Ad') };
  const LI_LIVE = { ok: t('Açık'), blocked: t('Giriş duvarı'), not_found: t('Bulunamadı'), empty: t('Boş sayfa'), error: t('Hata'), skipped: t('Atlandı') };
  const linkedin = {
    id: 'linkedin', name: 'LinkedIn', mark: 'IN',
    desc: t('Herkese açık profil sayfası ve arşiv kopyalarından unvan, şirket, eğitim, konum ve zaman içindeki değişiklikler.'),
    examples: ['https://www.linkedin.com/in/williamhgates', 'linkedin.com/in/satyanadella', 'williamhgates'],
    placeholder: t('profil bağlantısı veya profil kısa adı'), max: 5,
    header: d => ({ avatar: d.image, title: d.name || d.slug, handle: 'in/' + d.slug, url: d.url, bio: d.headline,
      badges: [{ t: liSrc(d), c: d.source_used === 'live' ? 'accent' : 'warn' }, d.location && { t: d.location },
        (d.changes || []).length && { t: t('{n} değişiklik', { n: d.changes.length }) }].filter(Boolean) }),
    kpis: d => [{ k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Bağlantı||connections'), v: d.connections || '—' },
      { k: t('Deneyim'), v: fmt((d.current || []).length + (d.experience || []).length) }, { k: t('Eğitim'), v: fmt((d.education || []).length) },
      { k: t('Arşiv sürümü'), v: fmt((d.archive || {}).total_versions), s: (d.archive || {}).first ? `${d.archive.first} → ${d.archive.last}` : '' },
      { k: t('Canlı sayfa'), v: LI_LIVE[d.live_status] || d.live_status || '—' }],
    charts: d => [
      { title: t('Yıllara göre arşiv sürümü'), sub: t('Wayback Machine · farklı içerikli kopyalar'), type: 'bar', data: Object.entries((d.archive || {}).years || {}).map(([y, c]) => ({ label: y.slice(2), full: y, value: +c || 0 })), unit: t('sürüm'), xName: t('Yıl') },
      { title: t('Takipçi — kopyalara göre'), type: 'bar', data: (d.history || []).filter(h => num(h.followers) != null).map(h => ({ label: h.date, full: h.date, value: +h.followers })), unit: t('takipçi') },
    ],
    findings: d => [
      kv(t('Profil'), [[t('Ad'), d.name], [t('Unvan'), d.headline], [t('Konum'), [d.location, d.country].filter(Boolean).join(' · ')], [t('Takipçi'), fmt(d.followers)],
        [t('Bağlantı||connections'), d.connections], [t('Kaynak'), liSrc(d)], [t('Canlı sayfa'), LI_LIVE[d.live_status] || d.live_status], [t('Profil'), d.url]]),
      d.about ? list(t('Hakkında'), [{ text: d.about }]) : null,
      table(t('Deneyim'), [t('Şirket'), t('Dönem'), t('Açıklama'), t('Durum')],
        [...(d.current || []).map(o => [o.url ? { href: o.url, text: o.name } : o.name, liPeriod(o), clip(o.description, 120), t('Güncel')]),
         ...(d.experience || []).map(o => [o.url ? { href: o.url, text: o.name } : o.name, liPeriod(o), clip(o.description, 120), t('Geçmiş')])]),
      table(t('Eğitim'), [t('Okul'), t('Dönem'), t('Açıklama')], (d.education || []).map(o => [o.url ? { href: o.url, text: o.name } : o.name, liPeriod(o), clip(o.description, 120)])),
      table(t('Profil değişiklikleri'), [t('Alan'), t('Önce'), t('Sonra'), t('Dönem')], (d.changes || []).map(c => [LI_FIELD[c.field] || c.field, c.from, c.to, `${c.from_date} → ${c.to_date}`]),
        t('Arşiv kopyaları ile canlı sayfa karşılaştırılır.')),
      table(t('Kopyalara göre profil'), [t('Tarih'), t('Unvan'), t('Şirket'), t('Konum'), t('Takipçi'), t('Kaynak')], (d.history || []).map(h => [h.date, h.headline || '—', h.company || '—', h.location || '—', fmt(h.followers), h.url ? { href: h.url, text: t('Aç') } : '—'])),
      list(t('Hakkında bölümündekiler'), [...(d.emails || []).map(e => L(e, 'mailto:' + e, t('e-posta'))), ...(d.socials || []).map(s => L(s.handle, s.url, s.platform)), ...(d.urls || []).map(u => L(u, u, 'url'))]),
      list(t('Diller ve ödüller'), [...(d.languages || []).map(x => L(x, null, t('dil'))), ...(d.awards || []).map(x => L(x, null, t('ödül')))]),
      table(t('Yazılar ve paylaşımlar'), [t('Tarih'), t('Başlık')], (d.articles || []).map(a => [isoDate(a.date), a.url ? { href: a.url, text: a.title } : a.title])),
      table(t('İncelenen arşiv kopyaları'), [t('Tarih'), t('Okundu'), t('Arşiv')], ((d.archive || {}).snapshots || []).map(s => [s.date, s.parsed ? t('Evet') : t('Giriş duvarı / boş'), { href: s.archive_url, text: t('Aç') }])),
    ].filter(Boolean),
  };

  // ═══════════════════ Instagram ═══════════════════
  const igMock = d => d.mock ? [{ t: t('ÖRNEK VERİ'), c: 'warn' }] : [];
  const instagram = {
    id: 'instagram', name: 'Instagram', mark: 'IG',
    desc: t('HikerAPI ile herkese açık profil, içerik istatistikleri, gönderi konumları, etkileşen hesaplar ve önerilen ilişkili hesaplar. Oturum açılmaz.'),
    examples: ['nasa', '@natgeo', 'https://www.instagram.com/instagram/'],
    placeholder: t('kullanıcı adı veya profil bağlantısı'), max: 10,
    header: d => { const p = d.profile || {}; return { avatar: p.profile_pic_url, title: p.full_name || p.username, handle: '@' + (p.username || d.username), url: `https://www.instagram.com/${p.username || d.username}/`, bio: p.biography,
      badges: [...igMock(d), p.is_verified && { t: t('Doğrulanmış'), c: 'accent' }, d.is_private && { t: t('Gizli hesap') }, p.is_business && { t: t('İşletme / içerik üretici') }, p.category_name && { t: p.category_name }].filter(Boolean) }; },
    kpis: d => { const p = d.profile || {}, st = d.stats || {}; return [
      { k: t('Takipçi'), v: fmt(p.follower_count) }, { k: t('Takip'), v: fmt(p.following_count) }, { k: t('Gönderi'), v: fmt(p.media_count) },
      { k: t('Etkileşim oranı'), v: st.engagement_rate != null ? pct(st.engagement_rate) : '—', s: t('son {n} gönderi', { n: fmt(d.scanned_posts) }) },
      { k: t('Ortalama beğeni'), v: fmt(st.likes_avg) }, { k: t('Ortalama yorum'), v: fmt(st.comments_avg) },
      { k: t('Ülke (kayıt)'), v: (d.about || {}).country || '—' }, { k: t('Oluşturma'), v: (d.about || {}).date_joined || '—' }]; },
    charts: d => [
      { title: t('Gönderi türleri'), type: 'hbar', data: [{ label: t('Fotoğraf'), value: (d.stats || {}).photos || 0 }, { label: t('Video'), value: (d.stats || {}).videos || 0 }, { label: t('Galeri'), value: (d.stats || {}).carousels || 0 }], unit: t('gönderi') },
      { title: t('Etiketler'), sub: t('Açıklamalarda en çok geçen'), type: 'hbar', data: (d.hashtags || []).map(h => ({ label: h.hashtag, value: h.count })), unit: t('kullanım') },
      { title: t('En çok yorum yapanlar'), type: 'hbar', data: (d.top_commenters || []).map(c => ({ label: '@' + c.username, value: c.count, href: `https://www.instagram.com/${c.username}/` })), unit: t('yorum') },
      { title: t('Paylaşım saatleri'), sub: 'UTC', type: 'bar', data: hourSeries((d.posting_times || {}).by_hour), xName: t('Saat||hour'), unit: t('gönderi') },
      { title: t('Paylaşım günleri'), type: 'bar', data: daySeries((d.posting_times || {}).by_weekday), unit: t('gönderi') },
    ],
    media: d => { const u = (d.profile || {}).username || d.username; return u ? [{ title: t('Profil kanıt kartı (PNG)'), endpoint: `/api/socmint/instagram/card/${encodeURIComponent(u)}`, file: `instagram_card_${u}.png`, note: t('Dış araç/tarayıcı gerektirmez; araç sunucuda kartı çizer (zaman damgası + SHA-256).') }] : []; },
    findings: d => { const p = d.profile || {}, st = d.stats || {}, pt = d.posting_times || {}; return [
      d.mock ? list(t('Bilgi'), [{ text: t('Bu sonuç örnek veridir. Gerçek veri için Ayarlar’dan HIKERAPI_TOKEN girin.') }]) : null,
      kv(t('Profil'), [[t('Kullanıcı adı'), '@' + (p.username || d.username)], [t('Ad'), p.full_name], [t('Kullanıcı ID'), p.id], [t('Kategori'), p.category_name || p.category],
        [t('Ülke (kayıt)'), (d.about || {}).country], [t('Oluşturma'), (d.about || {}).date_joined], [t('Kullanıcı adı değişimi'), (d.about || {}).former_usernames_count],
        [t('Zamir'), p.pronouns], [t('Bağlı Facebook ID'), p.fbid_v2], [t('Profil'), `https://www.instagram.com/${p.username || d.username}/`]]),
      kv(t('İşletme iletişimi (hesabın kendi yayınladığı)'), [[t('E-posta'), p.public_email], [t('Telefon'), p.public_phone_number || p.contact_phone_number], ['WhatsApp', p.whatsapp_number],
        [t('Adres'), [p.address_street, p.city_name, p.zip].filter(Boolean).join(', ')], [t('Konum (koordinat)'), p.latitude && p.longitude ? `${p.latitude}, ${p.longitude}` : null]]),
      p.biography ? list(t('Bio'), [{ text: p.biography }]) : null,
      list(t('Bio bağlantıları'), (p.bio_links || []).map(l => L(l.title || l.url, l.url, 'url')).concat(p.external_url ? [L(p.external_url, p.external_url, 'url')] : [])),
      kv(t('İçerik istatistikleri'), [[t('Taranan gönderi'), fmt(d.scanned_posts)], [t('Fotoğraf / Video / Galeri'), `${fmt(st.photos)} / ${fmt(st.videos)} / ${fmt(st.carousels)}`],
        [t('Toplam / ort. beğeni'), `${fmt(st.likes_total)} / ${fmt(st.likes_avg)}`], [t('Toplam / ort. yorum'), `${fmt(st.comments_total)} / ${fmt(st.comments_avg)}`],
        [t('Video izlenme (ort.)'), fmt(st.video_plays_avg)], [t('İş birliği'), fmt(st.collaborations)], [t('Ücretli iş birliği'), fmt(st.paid_partnerships)],
        [t('En aktif gün'), pt.most_active_day], [t('En aktif saat'), pt.most_active_hour], [t('İlk / son gönderi'), [pt.first_post, pt.last_post].filter(Boolean).join(' → ')], [t('Ortalama gün aralığı'), pt.avg_days_between_posts]]),
      table(t('Gönderi konumları'), [t('Yer'), t('Koordinat'), t('Tarih')], (d.locations || []).map(l => [l.name || '—', `${l.lat}, ${l.lng}`, l.time]), t('Haritada da gösterilir.')),
      table(t('En çok yorum yapanlar'), [t('Hesap'), t('Ad'), t('Yorum')], (d.top_commenters || []).map(c => [{ href: `https://www.instagram.com/${c.username}/`, text: '@' + c.username }, c.full_name || '—', fmt(c.count)])),
      table(t('Etiketleyenler'), [t('Hesap'), t('Ad'), t('Etiket')], (d.tagged_by || []).map(c => [{ href: `https://www.instagram.com/${c.username}/`, text: '@' + c.username }, c.full_name || '—', fmt(c.count)])),
      table(t('Hedefin etiketledikleri'), [t('Hesap'), t('Ad'), t('Etiket')], (d.tagged_users || []).map(c => [{ href: `https://www.instagram.com/${c.username}/`, text: '@' + c.username }, c.full_name || '—', fmt(c.count)])),
      table(t('Önerilen ilişkili hesaplar'), [t('Hesap'), t('Ad'), t('Doğrulanmış')], (d.suggested_profiles || []).map(s => [{ href: `https://www.instagram.com/${s.username}/`, text: '@' + s.username }, s.full_name || '—', s.is_verified ? t('Evet') : ''])),
      table(t('Öne çıkanlar'), [t('Kapak'), t('Başlık'), t('İçerik sayısı')], (d.highlights || []).map(h => [h.thumbnail_url ? { href: h.thumbnail_url, text: t('Aç') } : '—', h.title || '—', fmt(h.media_count)])),
      table(t('Hikâyeler (anonim — oturumsuz)'), [t('Tür'), t('Medya'), t('Tarih')], (d.stories || []).map(st => [st.media_type === 'video' ? t('Video') : t('Fotoğraf'), { href: st.url, text: t('Aç / indir') }, isoDate(st.taken_at ? st.taken_at * 1000 : null)]), d.active_stories ? t('{n} aktif hikâye — hedefin görenler listesinde görünmezsiniz.', { n: fmt(d.active_stories) }) : t('Aktif hikâye yok.')),
      table(t('Takipçiler'), [t('Hesap'), t('Ad'), t('Gizli'), t('Doğrulanmış')], (d.followers || []).map(u => [{ href: `https://www.instagram.com/${u.username}/`, text: '@' + u.username }, u.full_name || '—', u.is_private ? t('Evet') : '', u.is_verified ? t('Evet') : '']), (d.followers || []).length ? t('İlk {n} takipçi (herkese açık).', { n: fmt((d.followers || []).length) }) : ''),
      table(t('Takip edilenler'), [t('Hesap'), t('Ad'), t('Gizli'), t('Doğrulanmış')], (d.followings || []).map(u => [{ href: `https://www.instagram.com/${u.username}/`, text: '@' + u.username }, u.full_name || '—', u.is_private ? t('Evet') : '', u.is_verified ? t('Evet') : ''])),
      table(t('Yorumlar (ham)'), [t('Hesap'), t('Yorum'), t('Beğeni'), t('Gönderi')], (d.comments || []).map(c => [c.username ? { href: `https://www.instagram.com/${c.username}/`, text: '@' + c.username } : '—', clip(c.text, 140), fmt(c.likes), c.post_url ? { href: c.post_url, text: t('Aç') } : '—'])),
      table(t('Fotoğraflar (toplu URL)'), [t('Tarih'), t('Fotoğraf'), t('Gönderi')], (d.photos || []).map(ph => [isoDate(ph.taken_at ? ph.taken_at * 1000 : null), { href: ph.url, text: t('Aç / indir') }, ph.permalink ? { href: ph.permalink, text: t('Gönderi') } : '—'])),
      list(t('Fotoğraf alt metinleri'), (d.photo_alt_text || []).map(x => ({ text: x }))),
    ].filter(Boolean); },
  };

  // ═══════════════════ Bluesky ═══════════════════
  const bluesky = {
    id: 'bluesky', name: 'Bluesky', mark: 'BS',
    desc: t('AT Protocol açık API’si ile profil, gönderiler, bahsedilen hesaplar, etiketler, paylaşılan alan adları ve paylaşım saatleri. Anahtar gerekmez.'),
    examples: ['nasa.gov', '@jay.bsky.team', 'https://bsky.app/profile/bsky.app'],
    placeholder: t('handle (ör. nasa.gov), @handle veya DID'), max: 10,
    header: d => ({ avatar: d.avatar, title: d.display_name || d.handle, handle: '@' + d.handle, url: d.url, bio: d.description,
      badges: [(d.labels || []).length && { t: (d.labels || []).join(', '), c: 'warn' }, d.pds && { t: t('Kendi sunucusu') }].filter(Boolean) }),
    kpis: d => [{ k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Takip'), v: fmt(d.following) }, { k: t('Gönderi'), v: fmt(d.posts_count) },
      { k: t('Taranan gönderi'), v: fmt(d.scanned_posts), s: t('{r} repost, {y} yanıt', { r: fmt(d.reposts), y: fmt(d.replies_count) }) },
      { k: t('İlk / son gönderi'), v: [d.first_post, d.last_post].filter(Boolean).join(' → ') || '—' }, { k: t('Oluşturma'), v: isoDate(d.created_at) }],
    charts: d => [
      { title: t('Etiketler'), type: 'hbar', data: (d.hashtags || []).map(h => ({ label: h.hashtag, value: h.count })), unit: t('kullanım') },
      { title: t('Bahsedilen hesaplar'), type: 'hbar', data: (d.mentions || []).map(m => ({ label: '@' + (m.handle || m.did), value: m.count, href: m.handle ? `https://bsky.app/profile/${m.handle}` : null })), unit: t('bahsetme') },
      { title: t('Paylaşılan alan adları'), type: 'hbar', data: (d.domains || []).map(x => ({ label: x.domain, value: x.count })), unit: t('gönderi') },
      { title: t('Paylaşım saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(d.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
      { title: t('Paylaşım günleri'), type: 'bar', data: daySeries(d.day_distribution), unit: t('gönderi') },
      { title: t('Diller'), type: 'hbar', data: (d.languages || []).map(l => ({ label: l.lang, value: l.count })), unit: t('gönderi') },
    ],
    findings: d => [
      kv(t('Profil'), [[t('Handle'), '@' + d.handle], ['DID', d.did], [t('Ad'), d.display_name], [t('Takipçi'), fmt(d.followers)], [t('Takip'), fmt(d.following)],
        [t('Gönderi'), fmt(d.posts_count)], [t('Liste'), d.lists], [t('Besleme üreteci'), d.feedgens], [t('Oluşturma'), isoDate(d.created_at)], [t('Profil'), d.url]]),
      d.description ? list(t('Bio'), [{ text: d.description }]) : null,
      (d.labels || []).length ? list(t('Etiketler (moderasyon)'), (d.labels || []).map(l => ({ text: l }))) : null,
      list(t('E-postalar'), (d.emails || []).map(e => L(e, 'mailto:' + e))),
      table(t('Bahsedilen hesaplar'), [t('Hesap'), t('Ad'), t('Bahsetme')], (d.mentions || []).map(m => [m.handle ? { href: `https://bsky.app/profile/${m.handle}`, text: '@' + m.handle } : m.did, m.display_name || '—', fmt(m.count)])),
      table(t('Son gönderiler'), [t('Tarih'), t('Gönderi'), t('Beğeni'), t('Repost'), t('Yanıt')], (d.posts || []).map(p => [isoDate(p.created), p.url ? { href: p.url, text: clip(p.text, 110) } : clip(p.text, 110), fmt(p.likes), fmt(p.reposts), fmt(p.replies)])),
    ].filter(Boolean),
  };

  // ═══════════════════ Twitch ═══════════════════
  const twMock = d => d.mock ? [{ t: t('ÖRNEK VERİ'), c: 'warn' }] : [];
  const TW_TYPE = { partner: t('Partner'), affiliate: t('Affiliate') };
  const twitch = {
    id: 'twitch', name: 'Twitch', mark: 'TW',
    desc: t('Resmi Helix API ile kanal, canlı yayın durumu, videolar, klipler ve bio’daki sosyal hesaplar. Token yoksa örnek veri.'),
    examples: ['ninja', '@pokimane', 'https://twitch.tv/xqc'],
    placeholder: t('kullanıcı adı veya kanal bağlantısı'), max: 10,
    header: d => { const ch = d.channel || {}; return { avatar: d.profile_image_url, title: d.display_name || d.login, handle: '@' + d.login, url: d.url, bio: d.description,
      badges: [...twMock(d), d.live && { t: t('CANLI'), c: 'critical' }, d.type && { t: TW_TYPE[d.type] || d.type, c: 'accent' }, ch.game && { t: ch.game }].filter(Boolean) }; },
    kpis: d => { const ch = d.channel || {}; return [
      { k: t('Takipçi'), v: d.followers != null ? fmt(d.followers) : '—' }, { k: t('Toplam izlenme'), v: fmt(d.view_count) },
      { k: t('Tür'), v: TW_TYPE[d.type] || d.type || '—' }, { k: t('Ana oyun'), v: ch.game || '—' }, { k: t('Dil'), v: ch.language || '—' },
      { k: t('Hesap yaşı'), v: d.account_age_days != null ? t('{n} gün', { n: fmt(d.account_age_days) }) : '—' }, { k: t('Oluşturma'), v: isoDate(d.created_at) }]; },
    charts: d => [
      { title: t('En çok izlenen videolar'), type: 'hbar', data: (d.videos || []).map(v => ({ label: clip(v.title, 40), value: +v.views || 0 })), unit: t('izlenme') },
      { title: t('En çok izlenen klipler'), type: 'hbar', data: (d.clips || []).map(c => ({ label: clip(c.title, 40), value: +c.views || 0 })), unit: t('izlenme') },
    ],
    findings: d => { const ch = d.channel || {}; return [
      d.mock ? list(t('Bilgi'), [{ text: t('Bu sonuç örnek veridir. Gerçek veri için Ayarlar’dan TWITCH_CLIENT_ID ve secret girin.') }]) : null,
      kv(t('Kanal'), [[t('Kullanıcı adı'), '@' + d.login], [t('Ad'), d.display_name], [t('Kullanıcı ID'), d.id], [t('Tür'), TW_TYPE[d.type] || d.type],
        [t('Ana oyun'), ch.game], [t('Yayın başlığı'), ch.title], [t('Dil'), ch.language], [t('Etiketler'), (ch.tags || []).join(', ')], [t('Oluşturma'), isoDate(d.created_at)], [t('Profil'), d.url]]),
      d.description ? list(t('Bio'), [{ text: d.description }]) : null,
      d.live && d.stream ? kv(t('Canlı yayın'), [[t('Başlık'), d.stream.title], [t('Oyun'), d.stream.game], [t('İzleyici'), fmt(d.stream.viewers)], [t('Başlangıç'), isoDate(d.stream.started_at)]]) : null,
      table(t('Videolar'), [t('Tarih'), t('Başlık'), t('Tür'), t('İzlenme'), t('Süre')], (d.videos || []).map(v => [v.date, v.url ? { href: v.url, text: v.title } : v.title, v.type, fmt(v.views), v.duration])),
      table(t('Klipler'), [t('Tarih'), t('Başlık'), t('Oluşturan'), t('İzlenme')], (d.clips || []).map(c => [c.date, c.url ? { href: c.url, text: c.title } : c.title, c.creator, fmt(c.views)])),
      list(t('Bio bağlantıları'), [...(d.socials || []).map(x => L(x.handle, x.url, x.platform)), ...(d.emails || []).map(e => L(e, 'mailto:' + e, t('e-posta')))]),
    ].filter(Boolean); },
  };

  // ═══════════════════ Discord ═══════════════════
  const discord = {
    id: 'discord', name: 'Discord', mark: 'DC',
    desc: t('Herkese açık davet ve widget bilgisi: sunucu adı, yaklaşık üye / çevrimiçi sayısı, kanallar ve davet eden. Anahtar gerekmez.'),
    examples: ['discord.gg/python', 'https://discord.com/invite/openai', '267624335836053506'],
    placeholder: t('davet linki/kodu veya sunucu ID’si'), max: 10,
    header: d => ({ avatar: d.icon, title: d.guild_name || d.code || d.guild_id, handle: d.vanity ? 'discord.gg/' + d.vanity : (d.code ? 'discord.gg/' + d.code : d.guild_id), url: d.url, bio: d.description, mono: 'DC',
      badges: [d.member_count != null && { t: t('{n} üye', { n: fmt(d.member_count) }) }, d.online_count != null && { t: t('{n} çevrimiçi', { n: fmt(d.online_count) }), c: 'accent' }, d.verification_level && { t: t('Doğrulama: {v}', { v: d.verification_level }) }].filter(Boolean) }),
    kpis: d => { const w = d.widget || {}; return [
      { k: t('Üye (yaklaşık)'), v: fmt(d.member_count) }, { k: t('Çevrimiçi'), v: fmt(d.online_count) }, { k: t('Boost'), v: fmt(d.boosts) },
      { k: t('Doğrulama'), v: d.verification_level || '—' }, { k: t('Widget'), v: w.enabled ? t('Açık') : t('Kapalı') }, { k: t('Kanal (widget)'), v: fmt((w.channels || []).length) }]; },
    charts: d => [
      { title: t('Üye / çevrimiçi'), type: 'bar', data: [{ label: t('Üye'), value: +d.member_count || 0 }, { label: t('Çevrimiçi'), value: +d.online_count || 0 }], unit: t('kişi') },
    ],
    findings: d => { const w = d.widget || {}; return [
      kv(t('Sunucu'), [[t('Ad'), d.guild_name], [t('Sunucu ID'), d.guild_id], [t('Davet kodu'), d.code], [t('Vanity'), d.vanity], [t('Doğrulama düzeyi'), d.verification_level],
        [t('Üye (yaklaşık)'), fmt(d.member_count)], [t('Çevrimiçi'), fmt(d.online_count)], [t('Boost'), fmt(d.boosts)], [t('Davet URL’si'), d.url], [t('Davet süresi'), d.expires_at ? isoDate(d.expires_at) : t('Süresiz')]]),
      d.description ? list(t('Açıklama'), [{ text: d.description }]) : null,
      d.inviter ? kv(t('Davet eden'), [[t('Kullanıcı adı'), d.inviter.username], [t('Görünen ad'), d.inviter.global_name], [t('Kullanıcı ID'), d.inviter.id]]) : null,
      (d.features || []).length ? list(t('Sunucu özellikleri'), (d.features || []).map(f => ({ text: f }))) : null,
      d.channel && d.channel.name ? kv(t('Davet kanalı'), [[t('Ad'), '#' + d.channel.name], [t('Kanal ID'), d.channel.id]]) : null,
      w.channels && w.channels.length ? table(t('Kanallar (widget)'), [t('Ad'), t('Kanal ID')], w.channels.map(c => ['#' + c.name, c.id])) : null,
      w.members_sample && w.members_sample.length ? table(t('Çevrimiçi üyeler (widget)'), [t('Kullanıcı adı'), t('Durum'), t('Oyun')], w.members_sample.map(m => [m.username, m.status, m.game || '—'])) : null,
    ].filter(Boolean); },
  };

  // ═══════════════════ Kick ═══════════════════
  const kick = {
    id: 'kick', name: 'Kick', mark: 'KK',
    desc: t('Herkese açık kanal bilgisi: takipçi, doğrulama, yayın kategorileri ve bio’daki sosyal hesaplar. Cloudflare nedeniyle bazen engellenir.'),
    examples: ['xqc', '@trainwreckstv', 'https://kick.com/adin'],
    placeholder: t('kullanıcı adı veya kanal bağlantısı'), max: 10,
    header: d => ({ avatar: d.profile_pic, title: d.username || d.slug, handle: '@' + d.slug, url: d.url, bio: d.bio,
      badges: [d.live && { t: t('CANLI'), c: 'critical' }, d.verified && { t: t('Doğrulanmış'), c: 'accent' }, d.is_banned && { t: t('Yasaklı'), c: 'critical' }].filter(Boolean) }),
    kpis: d => [{ k: t('Takipçi'), v: fmt(d.followers) }, { k: t('Doğrulanmış'), v: d.verified ? t('Evet') : t('Hayır') },
      { k: t('Canlı'), v: d.live ? t('Evet') : t('Hayır') }, { k: 'VOD', v: d.vod_enabled ? t('Açık') : t('Kapalı') }, { k: t('Abonelik'), v: d.subscription_enabled ? t('Açık') : t('Kapalı') }],
    charts: d => [],
    findings: d => [
      kv(t('Kanal'), [[t('Kullanıcı adı'), '@' + d.slug], [t('Ad'), d.username], [t('Kullanıcı ID'), d.user_id], [t('Takipçi'), fmt(d.followers)], [t('Doğrulanmış'), d.verified ? t('Evet') : t('Hayır')], [t('Profil'), d.url]]),
      d.bio ? list(t('Bio'), [{ text: d.bio }]) : null,
      d.live && d.stream ? kv(t('Canlı yayın'), [[t('Başlık'), d.stream.title], [t('İzleyici'), fmt(d.stream.viewers)], [t('Kategori'), (d.stream.categories || []).join(', ')], [t('Başlangıç'), isoDate(d.stream.started_at)]]) : null,
      (d.recent_categories || []).length ? list(t('Son kategoriler'), (d.recent_categories || []).map(c => ({ text: c }))) : null,
      list(t('Sosyal hesaplar'), [...Object.entries(d.declared_socials || {}).map(([k, v]) => L(v, null, k)), ...(d.socials || []).map(x => L(x.handle, x.url, x.platform)), ...(d.emails || []).map(e => L(e, 'mailto:' + e, t('e-posta')))]),
    ].filter(Boolean),
  };

  // ═══════════════════ Hashtag → harita ═══════════════════
  const hashtagmap = {
    id: 'hashtagmap', name: t('Hashtag haritası'), mark: '#',
    desc: t('Bir hashtag’in nerede ve kimlerce atıldığı: konum etiketli gönderiler haritada, birlikte geçen etiketler, en aktif hesaplar ve saatler. Hedef hesap gerekmez.'),
    examples: ['osint', '#İstanbul', 'siber'],
    placeholder: t('hashtag (# olmadan da olur)'), max: 5,
    header: d => ({ title: '#' + d.hashtag, handle: t('{w} web · {m} Mastodon · {f} Flickr', { w: fmt(d.web_total), m: fmt(d.mastodon_posts), f: fmt(d.flickr_posts) }), url: null, mono: '#',
      badges: [d.sources && d.sources.instagram && { t: 'Instagram', c: 'accent' }, d.sources && d.sources.bluesky && { t: 'Bluesky', c: 'accent' }, d.sources && d.sources.mastodon && { t: 'Mastodon', c: 'accent' }, d.sources && d.sources.flickr && { t: 'Flickr', c: 'teal' },
        { t: t('{n} konum etiketli', { n: fmt(d.geotagged_posts) }) }].filter(Boolean) }),
    kpis: d => [{ k: t('Web sonucu'), v: fmt(d.web_total), s: t('tüm platformlar') }, { k: t('Konum etiketli'), v: fmt(d.geotagged_posts), s: 'Flickr' }, { k: 'Mastodon', v: fmt(d.mastodon_posts) },
      { k: 'Flickr', v: fmt(d.flickr_posts) }, { k: 'Bluesky', v: fmt(d.bluesky_posts) }, { k: 'Instagram', v: fmt(d.instagram_posts) }, { k: t('Birlikte geçen etiket'), v: fmt((d.co_hashtags || []).length) }],
    map: d => ({ title: t('Hashtag konum haritası'), note: t('Harita yalnızca konum etiketli gönderileri gösterir; çoğu gönderide konum yoktur, yani örneklemdir.'),
      points: (d.geo_points || []).map(g => ({ lat: g.lat, lng: g.lng, count: g.count, label: g.place || g.city || `${g.lat}, ${g.lng}` })) }),
    charts: d => [
      { title: t('En çok hangi ülkede'), type: 'hbar', data: (d.countries || []).map(c => ({ label: c.country, value: c.count })), unit: t('gönderi'), labelWidth: 160 },
      { title: t('En çok hangi yerde'), sub: t('Konum etiketine göre'), type: 'hbar', data: (d.places || []).map(pl => ({ label: pl.place, value: pl.count })), unit: t('gönderi'), labelWidth: 180 },
      { title: t('Birlikte geçen etiketler'), type: 'hbar', data: (d.co_hashtags || []).map(h => ({ label: h.hashtag, value: h.count })), unit: t('gönderi') },
      { title: t('Web sonuçları — platforma göre'), sub: t('Anahtarsız · arama motorunun açık sayfaları (Instagram dahil)'), type: 'hbar', data: Object.entries(d.web_by_platform || {}).map(([k, v]) => ({ label: k, value: v })), unit: t('sonuç'), labelWidth: 150 },
      { title: t('En aktif hesaplar'), type: 'hbar', data: (d.top_authors || []).map(a => ({ label: '@' + a.username, value: a.count })), unit: t('gönderi'), labelWidth: 160 },
      { title: t('Paylaşım saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(d.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
      { title: t('Diller'), type: 'hbar', data: (d.languages || []).map(l => ({ label: l.lang, value: l.count })), unit: t('gönderi') },
    ],
    findings: d => [
      table(t('Web sonuçları'), [t('Platform'), t('Başlık'), t('Bağlantı')], (d.web_results || []).map(w => [platBadge(w.platform), clip(w.title || '—', 70), { href: w.url, text: w.domain || w.url }])),
      list(t('Bilgi'), [{ text: t('Harita yalnızca konum etiketli gönderileri gösterir; çoğu gönderide konum yoktur, yani örneklemdir.') }].concat(d.instagram_error ? [{ text: t('Instagram: {v}', { v: d.instagram_error }) }] : [])),
      table(t('En çok hangi yerde'), [t('Yer'), t('Gönderi')], (d.places || []).map(pl => [pl.place, fmt(pl.count)])),
      table(t('Ülkeler'), [t('Ülke'), t('Gönderi')], (d.countries || []).map(c => [c.country, fmt(c.count)])),
      table(t('Konum noktaları'), [t('Yer'), t('Koordinat'), t('Gönderi')], (d.geo_points || []).map(g => [g.place || g.city || '—', `${g.lat}, ${g.lng}`, fmt(g.count)])),
      table(t('En aktif hesaplar'), [t('Hesap'), t('Platform'), t('Gönderi')], (d.top_authors || []).map(a => [{ href: a.platform === 'bluesky' ? `https://bsky.app/profile/${a.username}` : (a.platform === 'mastodon' ? `https://mastodon.social/@${a.username}` : (a.platform === 'flickr' ? null : `https://www.instagram.com/${a.username}/`)), text: '@' + a.username }, platBadge((a.platform||'').charAt(0).toUpperCase()+(a.platform||'').slice(1)), fmt(a.count)])),
      table(t('Örnek gönderiler (Bluesky)'), [t('Hesap'), t('Gönderi'), t('Beğeni')], (d.sample_posts || []).map(pp => [pp.handle ? { href: `https://bsky.app/profile/${pp.handle}`, text: '@' + pp.handle } : '—', pp.url ? { href: pp.url, text: clip(pp.text, 100) } : clip(pp.text, 100), fmt(pp.likes)])),
    ],
  };

  // ═══════════════════ Kelime araması ═══════════════════
  const PLAT_LABEL = { bluesky: 'Bluesky', reddit: 'Reddit', mastodon: 'Mastodon', hackernews: 'Hacker News', flickr: 'Flickr', instagram: 'Instagram' };
  const keyword = {
    id: 'keyword', name: t('Kelime araması'), mark: 'Q',
    desc: t('Bir kelimeyi Bluesky, Reddit ve Mastodon’da herkese açık aratır: gönderiler, en aktif hesaplar, etiketler, topluluklar ve saatler. Anahtar gerekmez.'),
    examples: ['ransomware', 'veri sızıntısı', '#osint'],
    placeholder: t('kelime veya kısa ifade'), max: 3,
    header: d => ({ title: '“' + d.query + '”', handle: t('{n} gönderi', { n: fmt(d.total) }), url: null, mono: 'Q',
      badges: Object.entries(d.by_platform || {}).map(([k, v]) => ({ t: `${PLAT_LABEL[k] || k}: ${fmt(v)}`, c: 'accent' })) }),
    kpis: d => [{ k: t('Toplam gönderi'), v: fmt(d.total) }, { k: t('Web sonucu'), v: fmt(d.web_total), s: d.web_engine === 'google' ? 'Google' : (d.web_engine === 'duckduckgo' ? 'DuckDuckGo' : '') },
      { k: 'Bluesky', v: fmt((d.by_platform || {}).bluesky) }, { k: 'Reddit', v: fmt((d.by_platform || {}).reddit) }, { k: 'Mastodon', v: fmt((d.by_platform || {}).mastodon) },
      { k: t('Farklı hesap'), v: fmt((d.top_accounts || []).length) }],
    charts: d => [
      { title: t('Platform kırılımı'), type: 'hbar', data: Object.entries(d.by_platform || {}).map(([k, v]) => ({ label: PLAT_LABEL[k] || k, value: v })), unit: t('gönderi') },
      { title: t('Web sonuçları — platforma göre'), sub: t('Arama motorunun indekslediği açık sayfalar'), type: 'hbar', data: Object.entries(d.web_by_platform || {}).map(([k, v]) => ({ label: k, value: v })), unit: t('sonuç'), labelWidth: 150 },
      { title: t('En aktif hesaplar'), type: 'hbar', data: (d.top_accounts || []).map(a => ({ label: '@' + a.author, value: a.count })), unit: t('gönderi'), labelWidth: 160 },
      { title: t('Etiketler'), type: 'hbar', data: (d.hashtags || []).map(h => ({ label: h.hashtag, value: h.count })), unit: t('gönderi') },
      { title: t('Paylaşım saatleri'), sub: 'UTC', type: 'bar', data: hourSeries(d.hour_distribution), xName: t('Saat||hour'), unit: t('gönderi') },
      { title: t('Diller'), type: 'hbar', data: (d.languages || []).map(l => ({ label: l.lang, value: l.count })), unit: t('gönderi') },
    ],
    findings: d => [
      table(t('Web sonuçları'), [t('Platform'), t('Başlık'), t('Bağlantı')], (d.web_results || []).map(w => [platBadge(w.platform), clip(w.title || '—', 70), { href: w.url, text: w.domain || w.url }])),
      table(t('Gönderiler'), ['Platform', t('Hesap'), t('Gönderi'), t('Tarih'), t('Skor')], (d.posts || []).map(p => [
        platBadge(PLAT_LABEL[p.platform] || p.platform), p.author ? '@' + p.author + (p.subreddit ? ` · r/${p.subreddit}` : '') : '—',
        p.url ? { href: p.url, text: clip(p.text, 120) } : clip(p.text, 120), isoDate(p.date), fmt(p.score)])),
      table(t('En aktif hesaplar'), [t('Platform'), t('Hesap'), t('Gönderi')], (d.top_accounts || []).map(a => [platBadge(PLAT_LABEL[a.platform] || a.platform), '@' + a.author, fmt(a.count)])),
    ],
  };

  const PLATFORMS_TMP = { github, mastodon, reddit, snapchat, tiktok, youtube, telegram, keybase, steam, gravatar, gitlab, hackernews, stackexchange, wayback, x, linkedin, instagram, bluesky, twitch, discord, kick, hashtagmap, keyword };

  // ═══════════════════ Kullanım rehberleri ═══════════════════
  // accepts: [biçim, açıklama] — app.js biçimin iki boşluktan önceki kısmını tıklanabilir örnek olarak kullanır.
  const CMP = 'a b c  + ' + t('Karşılaştırma modu');
  const GUIDES = {
    github: {
      accepts: [['torvalds', t('Kullanıcı adı')], ['@torvalds', t('Başında @ olabilir')], ['github.com/torvalds', t('Profil ya da repo URL’si; repo sahibi alınır')],
        [t('kisi@ornek.com'), t('E-posta — commit aramasıyla ait olduğu hesaba çözülür')]],
      outputs: [t('Profil bilgileri, konum, şirket, blog'), t('Profil, genel olaylar ve commit meta verisinden çıkan e-postalar'), t('Bağlı sosyal hesaplar'), t('Organizasyonlar ve herkese açık üyeleri'), t('Repolarda açık kalmış anahtar/token taraması'), t('Yıldızladığı repoların dil ve konu dağılımı')],
      notes: [t('Token kullanmaz; GitHub saatte 60 istek sınırı uygular. Sonuç 5 dakika önbellekte tutulur.')],
    },
    mastodon: {
      accepts: [['gargron', t('Sadece kullanıcı adı — yüzlerce sunucuda aynı ad aranır')], ['@gargron@mastodon.social', t('Tam adres — hesap analizi + diğer sunucularda arama')],
        ['https://mastodon.social/@gargron', t('Profil URL’si (tam adresle aynı)')], ['mastodon.social', t('Sunucu — sunucu bilgisi ve yönetici hesabı')]],
      outputs: [t('Hesap bilgileri, profil alanları, bio’daki e-posta / telefon / kripto adresleri'), t('Son gönderilerin saat, gün, dil, görünürlük dağılımı'), t('En çok bahsettiği hesaplar ve etiketler'), t('Avatar hash’leri (MD5, SHA-256, pHash) ve EXIF'), t('Aynı kullanıcı adının bulunduğu sunucular')],
      notes: [t('Kullanıcı adı taraması 30–90 saniye sürebilir.')],
    },
    reddit: {
      accepts: [['spez', t('Kullanıcı adı')], ['u/spez  ·  @spez', t('Kullanıcı')], ['https://reddit.com/user/spez', t('Profil URL’si')], ['r/OSINT', 'Subreddit'], ['https://reddit.com/r/OSINT', t('Subreddit URL’si')]],
      outputs: [t('Kullanıcı: karma, hesap yaşı, aktif olduğu subreddit’ler, aktivite saatleri ve tahmini saat dilimi, yorum duygu dağılımı, bot skoru'), t('Subreddit: abone / çevrimiçi sayısı, en aktif yazarlar, moderatörler, paylaşılan alan adları, öne çıkan gönderiler')],
      notes: [t('Oturumsuz uç noktalar kullanılır (dakikada ~60 istek). Kullanıcı için son 100 yorum ve 50 gönderi incelenir.')],
    },
    snapchat: {
      accepts: [['djkhaled305', t('Kullanıcı adı')], ['@djkhaled305', t('Başında @ olabilir')], ['snapchat.com/add/djkhaled305', t('Profil URL’si')], ['https://www.snapchat.com/@djkhaled305', t('Yeni profil URL’si')]],
      outputs: [t('Herkese açık profil, abone sayısı, bio, web sitesi'), t('Hikâyeler, öne çıkanlar, spotlight’lar'), t('Snapchat’in önerdiği ilişkili hesaplar'), t('Yükleme ısı haritası (gün × saat) — ayrıca sunucuda PNG olarak üretilebilir')],
      notes: [t('Yalnızca herkese açık profiller okunabilir.')],
    },
    tiktok: {
      accepts: [['charlidamelio', t('Kullanıcı adı')], ['@khaby.lame', t('Başında @ olabilir')], ['https://www.tiktok.com/@zachking', t('Profil URL’si')], [CMP, t('En fazla 5 hesap tek işte yan yana')]],
      outputs: [t('Profil, takipçi / beğeni / video sayıları, etkileşim oranı, sahte takipçi skoru'), t('Videolar, etiketler, açıklamalarda bahsedilen hesaplar'), t('Yorumcular ve hangi videolara yorum yaptıkları (ilişki grafiği)'), t('Bio linki, yönlendirme zinciri ve WHOIS'), t('Paylaşım saatleri ve sıklığı'), t('Büyüme grafiği — tahmini')],
      notes: [t('Yorum analizi video başına ~1,5 sn ekler. “Bulunamadı” çoğu zaman hız sınırı veya captcha demektir; birkaç dakika sonra tekrar deneyin.'), t('Büyüme grafiği gerçek geçmiş değildir, mevcut ortalamadan geriye doğru tahmindir.')],
    },
    youtube: {
      accepts: [['@MrBeast', 'Handle'], ['https://youtube.com/@Veritasium', t('Kanal URL’si')], ['UCX6OQ3DkcsbYNE6H8uQQuVA', t('Kanal ID')], [CMP, t('En fazla 5 kanal yan yana')]],
      outputs: [t('Kanal istatistikleri ve büyüme ortalamaları'), t('Son videoların izlenme, beğeni, süre, etiket analizi'), t('Yükleme saatleri ve tahmini saat dilimi'), t('En çok yorum yapanlar ve en beğenilen yorumlar (son 5 video)'), t('Hakkında sayfası ve açıklamadaki sosyal hesaplar — diğer platform taramalarıyla eşleşir'), t('Sahte abone skoru')],
      notes: [t('YOUTUBE_API_KEY gerekir (Ayarlar). Günlük kota 10.000 birim; bir tarama yaklaşık 20–60 birim harcar.')],
    },
    telegram: {
      accepts: [['durov', t('Kullanıcı adı')], ['@telegram', t('Başında @ olabilir')], [t('https://t.me/s/kanal'), t('t.me bağlantısı')]],
      outputs: [t('Başlık, açıklama, abone / üye sayısı'), t('Son gönderiler: metin, tarih, görüntülenme, medya'), t('İletilen kaynak kanallar ve bahsedilen hesaplar'), t('Etiketler ve paylaşılan alan adları')],
      notes: [t('Yalnızca herkese açık içerik okunur. Kanal önizlemesi kapalıysa gönderiler gelmez.')],
    },
    keybase: {
      accepts: [['chris', t('Keybase kullanıcı adı')], [t('github:kullanici'), t('GitHub hesabından Keybase kimliğine')], [t('twitter:kullanici'), t('Twitter/X hesabından')], [t('domain:ornek.com'), t('Alan adından')]],
      outputs: [t('İmzalı kanıtla bağlanmış hesaplar (en güvenilir kimlik eşleştirmesi)'), t('PGP anahtarı ve kripto adresleri'), t('Cihazlar, takipçiler, takip edilenler')],
      notes: [t('API anahtarı gerekmez.')],
    },
    steam: {
      accepts: [['gabelogannewell', t('Özel URL adı')], ['76561197960287930', 'SteamID64'], ['steamcommunity.com/id/…', t('Profil bağlantısı')]],
      outputs: [t('Profil, konum, üyelik tarihi'), t('Eski kullanıcı adları'), t('Gruplar ve arkadaş listesi'), t('Oyunlar ve oynama süreleri, yasaklar (API anahtarıyla)')],
      notes: [t('STEAM_API_KEY isteğe bağlı (Ayarlar). Anahtarsız herkese açık profil okunur.')],
    },
    gravatar: {
      accepts: [[t('kisi@ornek.com'), t('E-posta (hash’i hesaplanır, e-posta dışarı gönderilmez)')], ['beau', t('Gravatar kullanıcı adı')], [t('32/64 hane hash'), t('MD5 veya SHA-256')]],
      outputs: [t('Profil, avatar, konum, şirket'), t('Doğrulanmış sosyal hesaplar'), t('Bağlantılar ve kripto adresleri')],
      notes: [t('Gravatar’a yalnızca e-postanın hash’i gider.')],
    },
    gitlab: {
      accepts: [['gitlab-bot', t('gitlab.com kullanıcı adı')], [t('https://gitlab.com/kullanici'), t('Profil bağlantısı')], [t('https://git.kurum.local/kullanici'), t('Kurum içi GitLab')]],
      outputs: [t('Profil, profil e-postası, sosyal hesaplar'), t('Kendi projelerindeki commit e-postaları'), t('Gruplar, takipçiler, takip edilenler'), t('Etkinlik saatleri')],
      notes: [t('GITLAB_TOKEN isteğe bağlı (Ayarlar).')],
    },
    hackernews: {
      accepts: [['pg', t('Kullanıcı adı')], ['news.ycombinator.com/user?id=…', t('Profil bağlantısı')]],
      outputs: [t('Karma, hesap yaşı, about bölümündeki bağlantılar'), t('Hikâye ve yorum geçmişi (son 300 öğe)'), t('Yanıt verdiği kullanıcılar'), t('Paylaştığı alan adları')],
      notes: [t('API anahtarı gerekmez.')],
    },
    stackexchange: {
      accepts: [['stackoverflow.com/users/22656/…', t('Profil bağlantısı (herhangi bir SE sitesi)')], ['superuser:12345', 'site:id'], ['22656', t('Stack Overflow kullanıcı ID')], ['Jon Skeet', t('Ada göre arama')]],
      outputs: [t('Profil ve itibar'), t('Aynı kişinin diğer SE sitelerindeki hesapları'), t('Etiketler, yanıtlar, sorular'), t('Yanıt verdiği kullanıcılar')],
      notes: [t('Anahtarsız günlük 300 istek. STACKEXCHANGE_KEY ile 10.000 (Ayarlar).')],
    },
    wayback: {
      accepts: [['example.com', t('Alan adı (alt sayfalar da listelenir)')], ['https://example.com/about', t('Sayfa')], [t('https://twitter.com/kullanici'), t('Silinmiş / değişmiş profil sayfası')]],
      outputs: [t('Arşiv kayıt sayısı, ilk / son kayıt, yıllara göre dağılım'), t('İlk, orta ve son kopyadaki başlık, e-posta, sosyal hesaplar'), t('Arşivlenmiş URL listesi')],
      notes: [t('Büyük sitelerde 1–2 dakika sürebilir.')],
    },
    keyword: {
      accepts: [['ransomware', t('Tek kelime')], ['veri sızıntısı', t('Kısa ifade (Bluesky ve Reddit)')], ['#osint', t('Etiket de olur')]],
      outputs: [t('Bluesky, Reddit ve Mastodon’dan birleşik gönderi listesi'), t('En aktif hesaplar ve platform kırılımı'), t('Öne çıkan etiketler ve topluluklar (subreddit)'), t('Paylaşım saatleri ve dil dağılımı')],
      notes: [t('Anahtar gerekmez. Mastodon yalnızca tek kelimelik sorguyu etiket olarak okur; çok kelimeli aramalar Bluesky ve Reddit’ten gelir.')],
    },
    hashtagmap: {
      accepts: [['osint', t('Sadece etiket (# olmadan)')], ['#İstanbul', t('Başında # olabilir')], ['siber', t('Türkçe/Unicode etiketler de olur')]],
      outputs: [t('Konum etiketli gönderilerin haritası (nokta = koordinat, büyüklük = gönderi sayısı)'), t('En çok hangi ülke / yerde atıldığı'), t('Birlikte geçen etiketler ve anahtar kelimeler'), t('En aktif hesaplar ve paylaşım saatleri')],
      notes: [t('Harita YALNIZCA konum etiketli gönderileri gösterir; çoğu gönderide konum yoktur, yani örneklemdir, toplam değildir.'), t('Harita ücretsiz OpenStreetMap ile çizilir, anahtar gerekmez. Web + Mastodon kısmı da anahtarsızdır; koordinat noktaları için (opsiyonel) Flickr veya HikerAPI kullanılır.')],
    },
    twitch: {
      accepts: [['ninja', t('Kullanıcı adı')], ['@pokimane', t('Başında @ olabilir')], ['https://twitch.tv/xqc', t('Kanal URL’si')]],
      outputs: [t('Kanal profili, tür (partner/affiliate), ana oyun, dil'), t('Canlı yayın durumu ve izleyici sayısı'), t('Son videolar ve klipler (izlenme sayılarıyla)'), t('Bio’daki sosyal hesaplar ve bağlantılar')],
      notes: [t('TWITCH_CLIENT_ID ve TWITCH_CLIENT_SECRET gerekir (Ayarlar). Girilmezse açıkça “örnek veri” gösterilir.'), t('Takipçi sayısı Twitch tarafında bazen kapalıdır; o durumda boş gelir.')],
    },
    discord: {
      accepts: [['discord.gg/python', t('Davet linki')], ['https://discord.com/invite/openai', t('Davet linki')], ['267624335836053506', t('Sunucu ID’si (widget açıksa)')]],
      outputs: [t('Sunucu adı, açıklama, yaklaşık üye ve çevrimiçi sayısı'), t('Doğrulama düzeyi, boost sayısı, özellikler, vanity URL'), t('Davet eden hesap ve davet kanalı'), t('Widget açıksa: kanallar ve çevrimiçi üyeler')],
      notes: [t('Anahtar gerekmez. Kanal/üye listesi yalnızca sunucu widget’ını açık bıraktıysa gelir; aksi halde sadece davet bilgisi okunur.')],
    },
    kick: {
      accepts: [['xqc', t('Kullanıcı adı')], ['@trainwreckstv', t('Başında @ olabilir')], ['https://kick.com/adin', t('Kanal URL’si')]],
      outputs: [t('Kanal profili, takipçi sayısı, doğrulama'), t('Canlı yayın durumu ve kategori'), t('Son yayın kategorileri'), t('Beyan edilen ve bio’daki sosyal hesaplar')],
      notes: [t('Anahtar gerekmez ama Kick Cloudflare arkasındadır; oturumsuz istek engellenirse “engellendi” döner, birkaç dakika sonra tekrar deneyin.')],
    },
    bluesky: {
      accepts: [['nasa.gov', t('Handle (kullanıcı adı = alan adı)')], ['@jay.bsky.team', t('Başında @ olabilir')], ['did:plc:...', 'DID'], ['https://bsky.app/profile/bsky.app', t('Profil URL’si')]],
      outputs: [t('Profil, takipçi / takip / gönderi sayıları, hesap oluşturma'), t('Son gönderiler, beğeni / repost / yanıt sayıları'), t('Bahsedilen hesaplar, etiketler, paylaşılan alan adları'), t('Paylaşım saatleri (UTC) ve dil dağılımı'), t('Moderasyon etiketleri ve kendi sunucusu (PDS) bilgisi')],
      notes: [t('Tamamen açık AT Protocol API’si; anahtar veya oturum gerekmez.')],
    },
    instagram: {
      accepts: [['nasa', t('Kullanıcı adı')], ['@natgeo', t('Başında @ olabilir')], ['https://www.instagram.com/instagram/', t('Profil URL’si')]],
      outputs: [t('Profil, kategori, doğrulama, takipçi / takip / gönderi sayıları'), t('“About this account”: kayıt ülkesi, oluşturma tarihi, kullanıcı adı değişim sayısı'), t('Hesabın kendi yayınladığı işletme e-postası / telefonu / adresi ve bio bağlantıları'), t('İçerik istatistikleri, etiketler, gönderi türleri, paylaşım saatleri ısı haritası'), t('Gönderi konumları harita üzerinde'), t('En çok yorum yapanlar, etiketleyenler, hedefin etiketledikleri, Instagram’ın önerdiği ilişkili hesaplar'), t('Takipçi ve takip listeleri, ham yorum dökümü, toplu fotoğraf URL’leri'), t('Hikâye ve öne çıkanların medya bağlantıları (anonim — oturumsuz izleme)'), t('Profil kanıt kartı PNG (zaman damgası + SHA-256, dış araç gerektirmez)')],
      notes: [t('HIKERAPI_TOKEN gerekir (Ayarlar). Instagram’a oturum açılmaz; veri HikerAPI üzerinden gelir. Anahtar yoksa açıkça “örnek veri” gösterilir.'), t('Tümü anonimdir: oturum açılmadığı için hikâye/profil görüntüleme hedefin “görenler” listesinde iz bırakmaz.'), t('Yalnızca herkese açık hesaplar okunur; gizli hesap gizli kalır, aşılmaz.'), t('Takipçi/takip listeleri herkese açık veridir; ancak o listelerdeki kişilerin e-posta ve telefon numaraları toplanmaz.')],
    },
    linkedin: {
      accepts: [['https://www.linkedin.com/in/williamhgates', t('Profil bağlantısı (tr.linkedin.com da olur)')], ['williamhgates', t('Profil kısa adı (in/ sonrası)')]],
      outputs: [t('Ad, unvan, konum, takipçi / bağlantı sayısı'), t('Güncel ve geçmiş şirketler, eğitim, diller'), t('Hakkında bölümündeki e-posta, sosyal hesap ve bağlantılar'), t('Arşiv kopyalarına göre unvan / şirket / konum değişiklikleri')],
      notes: [t('Oturum açılmaz, şifre veya çerez istenmez; yalnızca herkese açık sayfa ve Wayback Machine kopyaları okunur.'), t('LinkedIn oturumsuz isteklerin çoğunu giriş duvarına yönlendirir; o durumda veri yalnızca arşivden gelir ve kopya tarihi gösterilir.'), t('Bağlantı listesi ve gizli alanlar alınmaz.')],
    },
    x: {
      accepts: [['nasa', t('Kullanıcı adı')], ['@github', t('Başında @ olabilir')], ['https://x.com/jack', t('Profil URL’si')]],
      outputs: [t('Profil: ad, bio, konum, web sitesi, doğrulama, sayılar'), t('Son gönderiler (API planına göre): tarih, beğeni, RT'), t('Bahsedilen hesaplar, etiketler, alan adları'), t('Gönderi saatleri (UTC)')],
      notes: [t('Ayarlar’dan X_BEARER_TOKEN girilirse gerçek veri çekilir; girilmezse açıkça “örnek veri” gösterilir.'), t('Ücretsiz X planı çok kısıtlıdır; gönderi geçmişi bazı planlarda boş dönebilir.')],
    },
  };
  const B = s => '<b>' + s + '</b>';
  const STEPS = [
    t('Hedefi yazın. Birden fazla hedef için boşluk ya da virgülle ayırın.'),
    t('{scan}’ya basın. Sonuç hazır olunca bildirim gelir; bu sırada başka modüle geçebilirsiniz.', { scan: B(t('Tara')) }),
    t('Sonuçta dört sekme var: {charts} (her biri PNG indirilebilir), {graph}, {findings}, {json}.', { charts: B(t('Grafikler')), graph: B(t('İlişki grafiği')), findings: B(t('Bulgular')), json: B(t('Ham JSON')) }),
    t('İlişki grafiğinde bir kullanıcı adına çift tıklayın: o hesap ilgili modülde taranır.'),
    t('Aktif bir vaka seçiliyse sonuçlar vakaya otomatik kaydedilir. Rapor menüsünden HTML veya PDF alabilirsiniz.'),
  ];
  Object.entries(GUIDES).forEach(([k, g]) => { PLATFORMS_TMP[k].guide = g; });
  const PLATFORMS = PLATFORMS_TMP;
  const GROUPS = [
    [t('Sosyal ağlar'), ['x', 'instagram', 'bluesky', 'linkedin', 'youtube', 'tiktok', 'twitch', 'kick', 'snapchat', 'reddit', 'mastodon', 'telegram', 'discord', 'steam']],
    [t('Geliştirici'), ['github', 'gitlab', 'stackexchange', 'hackernews']],
    [t('Kimlik ve arşiv'), ['keybase', 'gravatar', 'wayback']],
    [t('Arama ve harita'), ['keyword', 'hashtagmap']],
  ];
  const ORDER = GROUPS.flatMap(g => g[1]);

  // İlişki grafiğindeki düğümden gerçek taramalar (pivot) — birden fazla seçenek olabilir
  function resolvePivots(n) {
    const id = n.id || '', lbl = String(n.label || ''), meta = n.meta || {};
    const strip = s => s.replace(/^@/, '');
    const out = [];
    const add = (p, raw) => { if (raw && PLATFORMS[p] && !out.some(o => o.platform === p && o.raw === raw)) out.push({ platform: p, raw, label: `${PLATFORMS[p].name}: ${raw}` }); };
    const tail = pfx => id.slice(pfx.length);
    if (/^u_gh_|^u_org_/.test(id)) { add('github', strip(lbl)); add('keybase', 'github:' + strip(lbl)); }
    else if (/^p_gh_/.test(id)) add('github', tail('p_gh_'));
    else if (/^u_twitter_/.test(id)) { add('x', strip(lbl)); add('keybase', 'twitter:' + strip(lbl)); }
    else if (/^p_twitter_/.test(id)) add('x', tail('p_twitter_'));
    else if (/^u_tiktok_/.test(id)) add('tiktok', strip(lbl));
    else if (/^u_snap_/.test(id)) add('snapchat', strip(lbl));
    else if (/^u_reddit_/.test(id)) { add('reddit', lbl.startsWith('u/') ? lbl : 'u/' + strip(lbl)); add('keybase', 'reddit:' + strip(lbl).replace(/^u\//, '')); }
    else if (/^d_reddit_sub_/.test(id)) add('reddit', lbl.startsWith('r/') ? lbl : 'r/' + lbl);
    else if (/^u_youtube_/.test(id)) add('youtube', lbl.startsWith('@') ? lbl : '@' + lbl);
    else if (/^u_masto_/.test(id)) add('mastodon', lbl.startsWith('@') ? lbl : '@' + lbl);
    else if (/^d_masto_/.test(id)) add('mastodon', lbl);
    else if (/^u_telegram_/.test(id)) add('telegram', strip(lbl));
    else if (/^u_keybase_/.test(id)) add('keybase', strip(lbl));
    else if (/^u_steam_/.test(id)) add('steam', meta.SteamID64 || strip(lbl));
    else if (/^u_gitlab_/.test(id)) add('gitlab', meta.Profile || strip(lbl));
    else if (/^u_hackernews_/.test(id)) { add('hackernews', strip(lbl)); add('keybase', 'hackernews:' + strip(lbl)); }
    else if (/^u_se_/.test(id)) { const m = id.match(/^u_se_(.+)_(\d+)$/); add('stackexchange', meta.Profile || (m ? `${m[1]}:${m[2]}` : '')); }
    else if (/^e_/.test(id)) add('gravatar', lbl);
    else if (/^d_ext_/.test(id)) { add('wayback', lbl); add('keybase', 'domain:' + lbl); }
    else if (/^c_wb_/.test(id)) add('wayback', lbl);
    else if (/^p_telegram_/.test(id)) add('telegram', tail('p_telegram_'));
    else if (/^u_linkedin_|^p_linkedin_/.test(id)) add('linkedin', /^p_/.test(id) ? (meta.Profil || meta.Profile || '') : lbl);
    else if (/^u_instagram_|^p_instagram_/.test(id)) add('instagram', strip(lbl));
    else if (/^u_bluesky_|^p_bluesky_/.test(id)) add('bluesky', strip(lbl));
    else if (/^u_twitch_|^p_twitch_/.test(id)) add('twitch', strip(lbl));
    else if (/^u_kick_|^p_kick_/.test(id)) add('kick', strip(lbl));
    else if (/^u_discord_/.test(id)) { /* Discord kullanıcı adı taranamaz (davet/ID gerekir) */ }
    return out;
  }
  const resolvePivot = n => resolvePivots(n)[0] || null;

  window.SOC = { PLATFORMS, ORDER, GROUPS, resolvePivot, resolvePivots, has, dayTr, STEPS, hourSeries, daySeries, pairs };
})();
