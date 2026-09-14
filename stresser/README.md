# 🚀 Facebook In-App Browser & Real Device Stress Tester

Gerçek Chromium tarayıcısı, Oxylabs Residential Proxy rotasyonu, Facebook In-App Browser (mobil uygulama içi tarayıcı) parmak izi ve dinamik Meta `fbclid` desteği sunan, yüksek performanslı paralel stress test ve simülasyon aracı.

---

## 🌟 Öne Çıkan Özellikler

- **Gerçek Tarayıcı & Bot Koruması Atlama:** `playwright` ve `playwright-stealth` ile `navigator.webdriver`, WebGL, Chrome runtime ve tarayıcı parmak izlerini gerçek kullanıcı gibi gösterir.
- **Her İstekte %100 Farklı IP (Oxylabs Residential):** Oxylabs Türkiye rotasyonlu proxy ağı üzerinden, her tarayıcı oturumuna dinamik `sessid` atanarak her istekte garantili farklı ev interneti (Residential) IP'si kullanılır.
- **Facebook Mobil Uygulama İçi (In-App Browser) Emülasyonu:**
  - Android (Samsung Galaxy, Xiaomi, Pixel vb.) için `[FB_IAB/FB4A]` ve `X-Requested-With: com.facebook.katana`
  - iOS (iPhone 11–15) için `[FBAN/FBIOS]`
  - Mobil çözünürlük (`393x852`), Retina piksel yoğunluğu (`device_scale_factor: 3`) ve dokunmatik ekran (`has_touch: True`).
- **Evrensel Facebook Gönderi & CTA Desteği:**
  - Reels (`/reel/...`), Postlar (`/posts/...`, `/permalink.php`), Videolar (`/watch/...`, `/videos/...`) ve doğrudan linkler.
  - "Şimdi Alışveriş Yap" (`SHOP_NOW`), "Daha Fazla Bilgi Al" (`LEARN_MORE`), "Kaydol" (`SIGN_UP`), "Bize Ulaşın" (`CONTACT_US`) ve gönderi metnindeki harici linkleri otomatik yakalayıp tıklar.
  - Facebook Link Shim ara uyarı ekranlarını (`flx/warn`) otomatik olarak aşar.
- **Meta Reklam Kütüphanesi (Ad Library) Entegrasyonu:**
  - `ads/library/?id=...` bağlantılarını otomatik tespit eder. Reklam kartından veya modalından hedef site linkini ve CTA aksiyonunu doğrudan çözer ve tıklar.
- **Çoklu Hesap / Cookie Havuzu (Session Pool):**
  - Tekil veya çoklu hesap JSON cookie formatını destekler. Her paralel istekte havuzdan otomatik rotasyon yapar.
- **Akıllı Medya & Bant Genişliği Tasarrufu:**
  - Reels ve video akışlarında kotayı korumak için video veri akışını %85-90 oranında sınırlar, ancak Meta'nın 3 saniyelik sürekli izleme telemetrisini korur.
- **Dinamik Meta `fbclid` (Facebook Click Identifier) Enjeksiyonu:**
  - Hedef sitedeki Meta Pixel, CAPI ve analiz panellerinin ziyareti gerçek reklam tıklaması sayması için her istekte dinamik, benzersiz bir `fbclid=IwdGRjcAUU..._aem_...` parametresi üretir ve yönlendirir.
- **Paralel & Dengeli Worker Mimarisi:** Belirtilen toplam istek sayısını paralel çalışan worker'lara dengeli şekilde paylaştırır.
- **Canlı & Kalıcı Loglama:** Hem terminal ekranına anlık renkli çıktılar basar hem de tüm geçmişi `stresser.log` dosyasına kaydeder.

---

## 📂 Proje Mimarisi

```
stresser/
├── config.example.yaml   # Örnek yapılandırma şablonu (GitHub safe)
├── config.yaml           # Yerel yapılandırma dosyası (.gitignore'da)
├── main.py               # Giriş noktası, interaktif wizard & worker yöneticisi
├── browser_worker.py     # Facebook Reels, Post, Video & CTA tıklama motoru
├── ad_library_worker.py  # Meta Reklam Kütüphanesi (Ad Library) tık ve yönlendirme motoru
├── user_agents.py        # Gerçek Facebook Android & iOS User-Agent havuzu
├── reporter.py           # Canlı terminal raporlama & stresser.log yazıcı
├── requirements.txt      # Python bağımlılıkları
└── stresser.log          # İstek logları (otomatik üretilir)
```

---

## 🛠️ Kurulum

### 1. Depoyu İndirin ve Dizine Geçin
```bash
git clone <repo-url>
cd dazzling-salk/stresser
```

### 2. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## ⚙️ Yapılandırma

`config.example.yaml` dosyasını `config.yaml` olarak kopyalayın:

```bash
cp config.example.yaml config.yaml   # Linux/macOS
copy config.example.yaml config.yaml # Windows
```

`config.yaml` dosyasını açıp Oxylabs kimlik bilgilerinizi girin:

```yaml
# Hedef URL (Başlangıçta terminalde de sorulur)
target_url: "https://www.facebook.com/reel/28459649277001883"

# Eş zamanlı çalışacak tarayıcı sayısı
workers: 5

# Worker başına varsayılan istek (toplam = workers * requests_per_worker)
requests_per_worker: 20

# Sayfa yükleme zaman aşımı (saniye)
request_timeout: 30

# Headless mod (true = arka planda, false = ekranda tarayıcı pencereleri açılır)
headless: true

# Oxylabs Residential Proxy
oxylabs_username: "kullanici_adiniz"
oxylabs_password: "sifreniz"
oxylabs_country: "TR"
oxylabs_host: "pr.oxylabs.io"
oxylabs_port: 7777
```

> **İpucu (Ortam Değişkenleri):** İsterseniz kimlik bilgilerinizi `OXYLABS_USERNAME` ve `OXYLABS_PASSWORD` çevre değişkeni olarak da tanımlayabilirsiniz.

---

## ▶️ Çalıştırma

```bash
python main.py
```

Uygulama başladığında sizden interaktif olarak iki parametre isteyecektir:

1. **Hedef URL:** Test edilecek Facebook Reel, Post veya doğrudan web sitesi linki.
2. **Toplam İstek Sayısı:** Gönderilmek istenen toplam istek adedi (örn: `50`, `100`, `500`). Enter'a basarsanız varsayılan kullanılır.

### Örnek Terminal Çıktısı:

```text
  Hedef URL [https://www.facebook.com/reel/...]: 
  Toplam İstek Sayısı [100]: 50

──────────────────────────────────────────────────
  [>>]  Browser Stress Tester
──────────────────────────────────────────────────
  Hedef      : https://www.facebook.com/reel/28459649277001883
  Worker     : 5
  Toplam     : 50
  Proxy      : pr.oxylabs.io:7777
  Headless   : True
  Timeout    : 30s
──────────────────────────────────────────────────

[   1/50] [W01] [OK] 200 | 5.82s | UA: FB/Andr (465.0) | -> https://menoxintr.com/?fbclid=IwdGRjc...
[   2/50] [W03] [OK] 200 | 6.10s | UA: FB/iOS (17.4)  | -> https://menoxintr.com/?fbclid=IwdGRjc...
[   3/50] [W02] [OK] 200 | 6.25s | UA: FB/Andr (450.0) | -> https://menoxintr.com/?fbclid=IwdGRjc...
...
══════════════════════════════════════════════════
  Toplam İstek  : 50
  Başarılı      : 50 (%100)
  Hata          : 0
  Ort. Latency  : 6.04s
  Min Latency   : 4.95s
  Max Latency   : 7.20s
  Toplam Süre   : 62.4s
  İstek/saniye  : 0.80
══════════════════════════════════════════════════
```

---

## 🔒 Güvenlik & Gizlilik

- `config.yaml` ve `stresser.log` dosyaları `.gitignore`'a dahil edilmiştir.
- Hassas proxy şifreleriniz GitHub'a veya harici repolara yüklenmez.
- Repoya yalnızca şablon olan `config.example.yaml` yüklenir.

---

## 📄 Lisans
MIT License.
