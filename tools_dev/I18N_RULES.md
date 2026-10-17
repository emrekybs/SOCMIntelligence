# SOCMIntelligence i18n kuralları (TR kaynak → EN)

Altyapı: `frontend/i18n.js` hazır. Global `t(key, vars)` ve `I18N` var (tüm diğer scriptlerden önce yüklenir).
- Anahtar = **birebir Türkçe kaynak metin**. Türkçe modda t() metni aynen döndürür; yani TR arayüz HİÇ değişmemeli.
- `t('{n} başarılı', { n: fmt(x) })` — değişkenler `{ad}` yer tutucusuyla. Cümleyi parçalara bölüp birleştirme; tüm cümle tek anahtar olsun (İngilizcede kelime sırası farklı).
- İngilizce çoğul: sözlük değeri dizi olabilir `['{n} scan', '{n} scans']` (vars.n === 1 ise ilki). Sayıyı `n` adıyla ver.
- t() HTML kaçışı yapmaz ve anahtarlar HTML içermez. HTML'e basarken `esc(t(...))` kullan (vars ham verilebilir, esc sonucu korur). Metin içinde işaretleme (link, <b>) gerekiyorsa işaretlemeyi t() dışında bırak veya yer tutucu kullan: `t('YouTube API anahtarı tanımlı değil. {link}', {link: '__L__'})` gibi değil — daha basit: iki ayrı anahtar (cümle + link metni) kabul edilebilir, sadece dil bilgisi bozulmuyorsa.
- t()'nin İLK ARGÜMANI HER ZAMAN SABİT METİN olmalı (tek/çift tırnak ya da `${}` içermeyen backtick). `t(degisken)` YASAK. Sabit tablolar (ör. STATUS, CONF, NODE etiketleri) tanım anında t() ile sarılır: `ok: ['ok', t('Başarılı')]`. Modül seviyesinde t() çağırmak serbest (dil değişince sayfa yeniden yüklenir).
- **`t` adını gölgeleme!** Dokunduğun dosyalarda `t` adlı yerel değişken/parametre varsa (`forEach(t => ...)`, `const t = ...`, `[k, t]` destructuring, `let t` zamanlayıcı vs.) hepsini başka isimle değiştir (`tb`, `txt`, `tm`...). Aksi halde t() çağrısı patlar.
- Çevirme: araçlardan gelen veri değerleri (bio, başlık, kullanıcı adı), platform/marka adları, kısaltmalar (SHA-256, JSON, PNG, API, UTC, URL, OSINT, SOCMINT, GraphML, GEXF, Maltego CSV, pHash, NSFW, ID), düğüm id'leri, CSS sınıfları, data-* değerleri, mantık karşılaştırmasında kullanılan metinler (kontrol et: bir metin `===` ile karşılaştırılıyorsa veya sözlük anahtarıysa sarmalama).
- Tarih/sayı: `'tr-TR'` sabitlerini `I18N.locale` ile değiştir.
- Sunucudan gelen hata metinlerini gösterirken `I18N.err(msg)` ile sar (kalıp çevirisi ayrıca yazılacak).
- `confirm()`, `alert()`, toast, placeholder, title, aria, indirilen dosya adları, PNG başlıkları, rapor metinleri — hepsi dahil.

## İngilizce sözlük dosyası
Kendi parçanın çevirilerini `frontend/lang/en.<parça>.js` içine yaz:
```js
I18N.add('en', {
  'Genel bakış': 'Overview',
  '{n} başarılı': '{n} successful',
});
```
Kurallar: doğal, kısa, sentence case arayüz İngilizcesi (Title Case değil: "Relationship graph"). Yer tutucular aynen korunmalı. Anahtar tekrarı olmasın. JS geçerli olsun (tırnak kaçışları!).

## Sözlük (tutarlılık için ZORUNLU)
Tarama=Scan · Taramalar=Scans · Tara (düğme)=Scan · Yeniden tara=Rescan · Hedef=Target · Vaka=Case · Vakalar=Cases · Aktif vaka=Active case · Analist=Analyst · Güven=Confidence (Düşük/Orta/Yüksek=Low/Medium/High) · Notlar=Notes · Genel bakış=Overview · İlişki grafiği=Relationship graph · Düğüm=Node · İlişki/Kenar=Relation/Edge · Varlık=Entity · Ortak varlık=Shared entity · Bulgular=Findings · Grafikler=Charts · Ham JSON=Raw JSON · Zaman çizelgesi=Timeline · Kimlik eşleştirme=Identity matching · aynı kişi olabilir=possibly same person · Skor=Score · Gerekçe=Reason · Onayla=Confirm · Reddet=Reject · İzleme=Monitoring · İzle=Watch · Ayarlar=Settings · Dışa aktar=Export · İçe aktar=Import · Rapor=Report · Delil bütünlüğü=Evidence integrity · doğrula=verify · Analist işareti=Analyst mark · Doğrulandı=Verified · Şüpheli=Suspicious · Elendi=Dismissed · İşaretsiz=Unmarked · Bulunan hesaplar=Discovered accounts · Oturum=Session · Oturumu temizle=Clear session · Başarılı=Success · Bulunamadı=Not found · Gizli / erişim yok=Private / no access · Hız sınırı=Rate limited · Hata=Error · Çalışıyor=Running · Kullanıcı adı=Username · Görünen ad=Display name · E-posta=Email · Alan adı=Domain · Topluluk=Community · Etiket (hashtag)=Hashtag · İçerik=Content · Tanımlayıcı=Identifier · Kişi / hesap sahibi=Person / account owner · Abone=Subscribers · Takipçi=Followers · Takip=Following · Gönderi=Post · Yorum=Comment · Yanıt=Answer (Stack Exchange) / Reply · Beğeni=Likes · Görüntülenme=Views · İletilen=Forwarded · Bahsedilen=Mentioned · Tahmini=Estimated · Isı haritası=Heatmap · Saat=Hour · Gün=Day · Hesap açılışı=Account created · Proxy=Proxy · Hız=Speed/Rate · Kaydet=Save · Sil=Delete · İptal=Cancel · Kapat=Close · Ekle=Add · Kopyala=Copy · Kopyalandı=Copied · İndir=Download · Nasıl kullanılır=How to use · Rehberi gizle=Hide guide · Girdi=Input · Çıktı=Output · Not=Note · Sunucuda oluştur=Generate on server · Karşılaştır=Compare · Merkeze al=Center · Sığdır=Fit · Fizik=Physics · Etiketler (graf)=Labels · açık/kapalı=on/off · B (bin, sayı kısaltması)=K · Mn=M.
Gün kısaltmaları: Pzt Sal Çar Per Cum Cmt Paz = Mon Tue Wed Thu Fri Sat Sun; tam: Monday...Sunday.

## Bitince
`node tools_dev/i18n_check.js frontend/<dosyaların>` çalıştır: MISS=0, DYN=0 olmalı; LOOSE satırlarını tek tek incele (kalanlar sadece veri/yorum/mantık metni olmalı — veri anahtarı veya karşılaştırma gibi). `node --check` tüm dokunduğun dosyalarda. TR modunda davranış değişmemeli.
