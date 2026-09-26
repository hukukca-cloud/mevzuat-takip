# Mevzuat Takip – Günlük Toplayıcı

Bu depo her sabah 05:00'te (TSİ) Resmî Gazete'nin günlük fihristini ve tanımlanan kurum duyuru sayfalarını toplar. Sonuçları `data/` klasörüne yazar. Hukuki değerlendirme ve özetleme bu depoda yapılmaz; 06:00'da çalışan Claude zamanlanmış görevi bu dosyayı okuyarak bülteni hazırlar.

## Çıktılar

| Dosya | İçerik |
|---|---|
| `data/latest.md` | Son toplamanın okunabilir hali (Claude görevi bunu okur) |
| `data/latest.json` | Aynı verinin yapılandırılmış hali |
| `data/archive/YYYY-MM-DD.json` | Günlük arşiv |
| `state/` | Son başarılı Resmî Gazete tarihi ve kurum sayfalarında görülen bağlantılar |

Resmî Gazete için durum değerleri şunlardır:

- `ok`: Fihrist alındı.
- `henuz_yayimlanmadi`: Sayı henüz yayımlanmamış; ertesi çalıştırmada tekrar denenir.
- `erisilemedi`: Siteye erişilemedi.
- `bos_veya_ayristirilamadi`: Sayfa yapısı değişmiş olabilir.

Bir gün kaçırılırsa, sonraki çalıştırma en fazla 7 gün geriye giderek eksik sayıları tamamlar.

## Kurulum

1. GitHub'da yeni bir depo oluşturun (ör. `mevzuat-takip`). Claude görevinin dosyayı okuyabilmesi için depo **herkese açık (public)** olmalıdır. Depoda yalnızca kamuya açık mevzuat bilgisi ve anahtar kelimeler bulunur.
2. **Add file → Upload files** ile `scripts/`, `config/`, `data/`, `state/` klasörlerini ve `requirements.txt`, `README.md` dosyalarını yükleyin.
3. Workflow dosyasını ayrıca ekleyin: **Actions → New workflow → set up a workflow yourself** yolunu izleyin, dosya adını `collect.yml` yapın ve `.github/workflows/collect.yml` içeriğini yapıştırın. Nokta ile başlayan klasörler sürükle-bırak sırasında gizli kalabildiği için bu adım ayrıca gereklidir.
4. **Settings → Actions → General → Workflow permissions** altında "Read and write permissions" seçeneğini işaretleyin.
5. **Actions → Mevzuat toplama → Run workflow** ile ilk denemeyi yapın ve `data/latest.md` dosyasını kontrol edin.

## Bilinen riskler

- **Erişim kısıtı:** GitHub sunucuları yurt dışındadır. Bir kamu sitesi yurt dışı erişimini kısıtlarsa ilgili kaynak `erisilemedi` olarak görünür.
- **Zamanlama sapması:** GitHub zamanlanmış çalıştırmaları yoğun saatlerde birkaç dakika ile daha uzun süreler arasında gecikebilir; 05:00 seçimi bu nedenle bir tampon içerir.
- **Pasif depolar:** Uzun süre hareketsiz kalan depolarda GitHub zamanlanmış görevleri durdurabilir. Günlük commit bunu büyük ölçüde önler; yine de Actions sekmesini ara ara kontrol edin.

## Kurum sayfalarını etkinleştirme

`config/sources.yml` dosyasında her kaynağın `url` alanını ilgili **duyuru listesi sayfasının** tam adresiyle değiştirin ve `enabled: true` yapın. Gerekirse `selector` alanına bağlantıların bulunduğu bölümün CSS seçicisini ekleyin. İlk çalıştırma mevcut bağlantıları referans olarak kaydeder; sonraki çalıştırmalar yalnızca yeni eklenenleri raporlar.

## Claude zamanlanmış görev talimatı (06:00)

`hukukca-cloud` kısmını kendi GitHub kullanıcı adınızla değiştirin.

```
Görev: Günlük Mevzuat Takip Bülteni

1) Şu dosyayı oku: https://raw.githubusercontent.com/hukukca-cloud/mevzuat-takip/main/data/latest.md
   Dosyadaki "Oluşturulma" tarihi bugün değilse bunu bültenin başında açıkça belirt.
2) Resmî Gazete kayıtlarından yalnızca şu alanları etkileyenleri seç: kripto varlıklar ve KVHS,
   sermaye piyasası (SPK), SGA/TF (MASAK), TCMB ödeme düzenlemeleri, KVKK, anonim şirketleri
   etkileyen ticari/vergisel düzenlemeler ile HMK, TBK, TTK, CMK ve iş hukuku değişiklikleri.
   Atama, üniversite yönetmelikleri gibi kapsam dışı kayıtları ele.
3) Kurum sayfalarındaki yeni kayıtları aynı ölçütle değerlendir.
4) Web aramasıyla son 24 saati tara: ESMA, EBA, Avrupa Komisyonu, EUR-Lex (MiCA, AMLR/TFR, AMLA);
   SEC, CFTC, Congress.gov, Hazine/OCC/FinCEN, Federal Register ve Beyaz Saray'ın dijital varlık
   çalışmaları. Yalnızca kripto varlık ve stablecoin ile ilgili içeriği al; her kayda kaynak bağlantısı ver.
5) Her kaydı Kritik / Önemli / Bilgi olarak sınıflandır; Stablex (KVHS, Akbank iştiraki) bakımından
   olası etkisini, yürürlük veya uyum tarihini ve önerilen aksiyonu kısaca yaz.
6) Bültenin sonunda kaynak durum tablosu ver ("yeni kayıt", "değişiklik yok", "erişilemedi").
   Emin olmadığın bilgiyi özetleme, bağlantısını ver.
7) Bülteni resmî ve ölçülü hukuk Türkçesiyle hazırla.
```
