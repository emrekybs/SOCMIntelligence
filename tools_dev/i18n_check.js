// Kullanım: node tools_dev/i18n_check.js [dosya...]
// 1) t('...') anahtarlarının hepsinin İngilizce karşılığı var mı
// 2) t() dışında kalmış Türkçe karakterli metin var mı (satır listesi)
// 3) t() ilk argümanı sabit metin değilse uyarı
const fs = require('fs'), path = require('path'), vm = require('vm');
const FE = path.join(__dirname, '..', 'frontend');
const files = process.argv.slice(2).length ? process.argv.slice(2) : ['app.js', 'platforms.js', 'graph.js', 'charts.js', 'signals.js', 'report.js', 'export.js'].map(f => path.join(FE, f));
const dict = {};
const ctx = { I18N: { add: (l, o) => { dict[l] = Object.assign(dict[l] || {}, o); }, addErrors() {} } };
vm.createContext(ctx);
for (const f of fs.readdirSync(path.join(FE, 'lang')).filter(f => f.endsWith('.js'))) vm.runInContext(fs.readFileSync(path.join(FE, 'lang', f), 'utf8'), ctx, { filename: f });
const en = dict.en || {};
const TR = /[ğüşıöçĞÜŞİÖÇ]/;
const keyRe = /(?<![\w.$])t\(\s*(['"`])((?:\\.|(?!\1)[^\\])*)\1/g;
let missing = 0, loose = 0, dyn = 0; const used = new Set();
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  let m;
  while ((m = keyRe.exec(src))) {
    const key = m[1] === '`' ? m[2] : m[2].replace(/\\(['"\\])/g, '$1');
    if (m[1] === '`' && key.includes('${')) { console.log(`DYN   ${path.basename(f)}: t(\`${key.slice(0, 60)}\`)`); dyn++; continue; }
    used.add(key);
    if (!(key in en)) { console.log(`MISS  ${path.basename(f)}: ${key}`); missing++; }
  }
  const dynRe = /(?<![\w.$])t\(\s*(?!['"`])([^)]{0,50})/g;
  while ((m = dynRe.exec(src))) { console.log(`DYN   ${path.basename(f)}: t(${m[1]}`); dyn++; }
  const stripped = src.replace(keyRe, 't(K').replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' ')).replace(/(^|[^:'"`])\/\/.*$/gm, '$1');
  stripped.split('\n').forEach((line, i) => { if (TR.test(line)) { console.log(`LOOSE ${path.basename(f)}:${i + 1}: ${line.trim().slice(0, 140)}`); loose++; } });
}
const unused = Object.keys(en).filter(k => !used.has(k));
console.log(`\nkeys=${used.size} missing=${missing} loose=${loose} dynamic=${dyn} unused_en=${unused.length}`);
if (process.env.SHOW_UNUSED) unused.forEach(k => console.log('UNUSED', k));
