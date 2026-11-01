# InDesign Bulut

InDesign belgelerinizi tarayıcıdan ve Claude Code ile bulutta yönetin: **metin düzenleme ve çeviri**, **sürüm geçmişi** ve **PDF çıktısı**.

```
 ┌──────────── Bulut sunucu ─────────────┐          ┌──── Sizin bilgisayarınız ────┐
 │ Web paneli (FastAPI)                  │  HTTPS   │ agent.py  (iş kuyruğunu       │
 │  • metin düzenleme  • geçmiş/diff     │◄────────►│            dinler)            │
 │  • PDF isteme      • Claude talimatı  │          │     │ sıcak klasör            │
 │ Git deposu: açılmış IDML (her kayıt   │          │     ▼                         │
 │  bir commit)                          │          │ InDesign + başlangıç script'i │
 │ Claude Code (claude -p) + idmlkit     │          │  • .indd → .idml  • PDF       │
 └───────────────────────────────────────┘          └───────────────────────────────┘
```

**Neden böyle?** `.indd` Adobe'nin kapalı ikili formatıdır ve yalnızca InDesign açabilir. Bu yüzden metin işleri bulutta **IDML** (InDesign'ın XML formatı) üzerinde yapılır. PDF üretimi ve `.indd` dönüşümü gibi InDesign gerektiren işler ise sizin masaüstü InDesign'ınıza iş olarak gönderilir. Ek lisans gerekmez.

## Özellikler
- **.idml veya .indd yükleme.** `.indd` dosyaları ajan tarafından otomatik olarak IDML'e çevrilir.
- **Paragraf bazlı metin düzenleme.** Karakter stilleri (`<r1>…</r1>`) ve satır içi nesneler (`<x1/>`: tablo, sayfa no, görsel) korunur. Geçersiz düzenlemeler reddedilir.
- **Sürüm geçmişi.** Her kayıt bir git commit'i olur. Yazar bilgisi tutulur, paragraf düzeyinde fark görülebilir, eski bir sürüm indirilebilir veya geri yüklenebilir.
- **Claude talimatları.** Örnekler: "İngilizceye çevir", "yazım hatalarını düzelt", "fiyatlara %10 zam yap". Claude Code değişiklikleri yeni bir sürüm olarak kaydeder.
- **PDF çıktısı.** InDesign ön ayarlarıyla (High Quality Print, Press Quality, PDF/X-4…) alınır.
- **Arşiv aktarımı.** `Toplu_INDD_to_IDML.jsx` ile klasör klasör dönüştürüp `agent.py upload` ile toplu yükleyebilirsiniz.

## 1. Sunucuyu kurun

### Docker ile
```bash
docker build -t indesign-bulut .
```
```bash
docker run -d -p 8000:8000 -v $PWD/data:/data -e APP_TOKEN=uzun-gizli-anahtar -e ANTHROPIC_API_KEY=sk-ant-... indesign-bulut
```

### Doğrudan
```bash
pip install -r requirements.txt
```
```bash
npm install -g @anthropic-ai/claude-code
```
```bash
DATA_DIR=./data APP_TOKEN=uzun-gizli-anahtar uvicorn server.app:app --host 0.0.0.0 --port 8000
```

`http://sunucu:8000` adresini açın, ⚙ simgesine tıklayın ve erişim anahtarınızı girin. İnternete açacaksanız sunucuyu HTTPS arkasına (Caddy, nginx, Cloudflare Tunnel vb.) koyun.

| Ortam değişkeni | Açıklama |
|---|---|
| `APP_TOKEN` | Panel ve ajan erişim anahtarı (boş bırakılırsa kimlik doğrulama kapalı olur, önerilmez) |
| `DATA_DIR` | Git deposu, PDF'ler ve iş kayıtlarının tutulacağı yer (varsayılan `./data`) |
| `ANTHROPIC_API_KEY` | Claude Code'un kullanacağı anahtar (veya sunucuda `claude login`) |
| `CLAUDE_MODEL`, `CLAUDE_TIMEOUT` | İsteğe bağlı model ve görev zaman aşımı (saniye, varsayılan 1800) |
| `MAX_UPLOAD_MB` | Yükleme sınırı (varsayılan 500) |

## 2. InDesign ajanını kurun (Mac veya Windows)

1. `agent/indesign/InDesignBulut_startup.jsx` dosyasını InDesign'ın **Startup Scripts** klasörüne kopyalayın:
   - macOS: `~/Library/Preferences/Adobe InDesign/<sürüm>/<dil>/Scripts/Startup Scripts/`
   - Windows: `%APPDATA%\Adobe\InDesign\<sürüm>\<dil>\Scripts\Startup Scripts\`

   Klasör yoksa oluşturun. InDesign'ı yeniden başlatın.
2. Ajanı başlatın (Python 3.9+ yeterli, ek paket gerekmez):
   ```bash
   python3 agent/agent.py --server https://sunucu-adresi --token uzun-gizli-anahtar run
   ```
3. Panelin sağ üstünde **InDesign ajanı** yeşil görünmelidir. InDesign açık kaldığı sürece işler otomatik olarak işlenir.

Sıcak klasör varsayılan olarak `Belgeler/InDesignBulut` konumundadır. Fontlar ve bağlı görseller sizin bilgisayarınızda bulunduğu için PDF'ler bire bir doğru çıkar. Eksik font veya bağlantı olsa bile script uyarı penceresinde takılmaz.

### Mevcut arşivi aktarma
InDesign'da *Script'ler* panelinden `Toplu_INDD_to_IDML.jsx` çalıştırıp bir klasör seçin. Ardından:
```bash
python3 agent/agent.py --server https://sunucu-adresi --token uzun-gizli-anahtar upload ~/Arsiv
```

## 3. Claude Code ile doğrudan çalışma
Panel dışında, bu repo üzerinde Claude Code ile de çalışabilirsiniz (ayrıntılar `CLAUDE.md` dosyasında):
```bash
python3 -m idmlkit text katalog.idml
```
```bash
python3 -m idmlkit export katalog.idml -o segments.json
```
Claude'dan `segments.json` içindeki metinleri düzenlemesini isteyin, ardından:
```bash
python3 -m idmlkit import katalog.idml segments.json -o katalog-en.idml
```
Sunucudaki belgeler `DATA_DIR/repo/documents/<belge>/idml/` altında açılmış IDML olarak, sıradan bir git deposunda durur.

## Bilinen sınırlar
- Çeviri sonrası **metin taşması** bulutta hesaplanamaz. Kontrol için PDF isteyin.
- Şu an yalnızca mevcut paragrafların metni düzenlenir. Paragraf ekleme/silme, görsel değiştirme ve stil düzenleme yol haritasındadır.
- Aynı paragrafı iki kişi aynı anda düzenlerse ikinci kayıt reddedilir (çakışma uyarısı) ve sayfayı yenilemeniz gerekir.

## Geliştirme
```bash
python3 -m pytest -q
```
