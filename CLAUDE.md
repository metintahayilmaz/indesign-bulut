# InDesign Bulut — Claude Code rehberi

Bu repo, InDesign belgelerini bulutta yönetmek için bir web paneli, `idmlkit` kütüphanesi ve masaüstü InDesign ajanı içerir.

## Mimari
- `idmlkit/` — IDML (InDesign Markup, ZIP içinde XML) okuma/yazma. `.indd` ikili formatı Linux'ta açılamaz; tüm metin işlemleri IDML üzerinde yapılır.
- `server/` — FastAPI. `storage.py` belgeleri git deposunda *açılmış IDML* olarak tutar (her kayıt bir commit). `jobs.py` masaüstü ajan kuyruğu, `ai.py` panelden gelen talimatları `claude -p` ile çalıştırır.
- `yerel.py` + `Baslat (Mac).command` / `Baslat (Windows).bat` — paneli ve ajanı aynı bilgisayarda tek süreçte başlatır, InDesign script'ini kurar (önerilen kurulum).
- `agent/` — Kullanıcının bilgisayarında çalışır: `agent.py` (Python stdlib) işleri sıcak klasöre bırakır, `indesign/InDesignBulut_startup.jsx` InDesign içinde PDF/IDML dışa aktarır.

## IDML belgeleri üzerinde çalışırken
Daima `python3 -m idmlkit` kullan; `Stories/*.xml` dosyalarını elle düzenleme.

```bash
python3 -m idmlkit info  <belge>             # <belge>: .idml dosyası veya açılmış klasör
python3 -m idmlkit text  <belge>             # [paragraf-id] (stil) metin
python3 -m idmlkit set   <belge> u200/p3 "Yeni metin"
python3 -m idmlkit export <belge> -o segments.json   # toplu düzenleme/çeviri
python3 -m idmlkit import <belge> segments.json      # yalnızca "text" alanları değişmiş olmalı
python3 -m idmlkit replace <belge> "eski" "yeni" [--regex] [-i]
```

İşaretleme kuralları:
- `<r1>…</r1><r2>…</r2>` — paragraftaki karakter stili parçaları. İçerik değişebilir, etiketler korunmalı (silinen etiketin parçası boşalır).
- `<x1/>` — satır içi nesne (tablo, dipnot, sayfa numarası, bağlı görsel). **Silinemez, sırası değiştirilemez.**
- Paragraf kimlikleri (`<StorySelf>/p<n>`) belgenin yapısı değişmedikçe sabittir.

## Geliştirme
```bash
pip install -r requirements-dev.txt
python3 -m pytest -q
DATA_DIR=./data uvicorn server.app:app --reload
```
- Testler örnek IDML'i `tests/sample_idml.py` ile üretir (`python3 -m tests.sample_idml ornek.idml`).
- Arayüz metinleri Türkçedir. Ön yüz bağımlılıksızdır (`server/static/`).
- ExtendScript (`.jsx`) ES3'tür: `let/const`, ok fonksiyonları ve `JSON` yoktur.

## Bilinen sınırlar
- Metin taşması/yerleşim IDML'de hesaplanamaz; çeviri sonrası taşmaları görmek için PDF iste (ajan gerekir).
- Değişiklik izleme (track changes) ve koşullu metin ayrıştırılır ama ayrıca işaretlenmez.
- Paragraf ekleme/silme henüz yok (yalnızca mevcut paragrafların metni düzenlenir).
