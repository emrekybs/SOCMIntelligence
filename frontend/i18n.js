/* SOCMIntelligence — dil desteği.
   Anahtar = Türkçe kaynak metin. Türkçe seçiliyken metin aynen döner; diğer dillerde sözlükten gelir.
   t('{n} tarama', { n: 3 })  →  "3 tarama" / "3 scans"
   Sözlük değeri dizi olabilir: ['1 scan', '{n} scans'] → n === 1 ise ilki. */
(function () {
  'use strict';
  const KEY = 'socmint.lang';
  const LANGS = { tr: { name: 'Türkçe', locale: 'tr-TR' }, en: { name: 'English', locale: 'en-GB' } };
  let lang = null;
  try { lang = localStorage.getItem(KEY); } catch (e) { /* depolama yok */ }
  if (!LANGS[lang]) lang = 'tr';
  const dict = {};
  const errRules = {};
  const missing = new Set();

  function fill(s, vars) {
    if (!vars) return s;
    return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars && vars[k] != null ? String(vars[k]) : m));
  }
  // 'Metin||bağlam': aynı Türkçe metnin farklı yerlerde farklı çevirisi için. Türkçede bağlam atılır.
  function t(key, vars) {
    let s = key.split('||')[0];
    if (lang !== 'tr') {
      const v = dict[lang] && dict[lang][key];
      if (v == null) missing.add(key);
      else s = Array.isArray(v) ? (vars && Number(vars.n) === 1 ? v[0] : v[1]) : v;
    }
    return fill(s, vars);
  }
  // Sunucudan gelen Türkçe hata mesajlarını çevirir: kurallar sırayla, iç içe mesajlarda da uygulanır.
  function err(msg) {
    msg = String(msg == null ? '' : msg);
    if (lang === 'tr') return msg;
    for (const [re, out] of errRules[lang] || []) msg = msg.replace(re, (...m) => out.replace(/\$(\d)/g, (x, i) => m[+i] ?? ''));
    return msg;
  }
  window.I18N = {
    get lang() { return lang; },
    get locale() { return LANGS[lang].locale; },
    LANGS, t, err, missing,
    add(l, obj) { dict[l] = Object.assign(dict[l] || {}, obj); },
    addErrors(l, rules) { errRules[l] = (errRules[l] || []).concat(rules); },
    has(l, key) { return !!(dict[l] && key in dict[l]); },
    dict,
    set(l) {
      if (!LANGS[l] || l === lang) return;
      try { localStorage.setItem(KEY, l); } catch (e) { /* */ }
      location.reload();
    },
  };
  window.t = t;
  document.documentElement.lang = lang;
})();
