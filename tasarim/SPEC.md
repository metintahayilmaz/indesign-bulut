# Yerleşim planı (`layout.json`) — biçim referansı

Plan, şablonun sayfa geometrisine ve stillerine **bağlı** bir tariftir. InDesign'daki sabit script (`InDesignBulut_startup.jsx`)
şablonu açar ve bu tarife göre sayfaları kurar. Bütün ölçüler **milimetre**dir.

```json
{
  "start_page": 34,
  "pages": [
    {
      "master": "A-Haber",
      "master_text": {"vinyet-bolum": "RÖPORTAJ"},
      "frames": [
        {"type": "image", "image": "kapak.jpg", "col": 1, "span": 3, "top": 0, "height": 150,
         "bleed": ["top", "outside"], "fit": "fill"},
        {"type": "text", "story": "manset", "col": 1, "span": 3, "top": 160, "height": 40},
        {"type": "text", "story": "govde", "col": 1, "span": 1, "top": 205, "bottom": 0},
        {"type": "text", "story": "govde", "col": 2, "span": 1, "top": 205, "bottom": 0},
        {"type": "text", "story": "govde", "col": 3, "span": 1, "top": 205, "bottom": 0}
      ]
    }
  ],
  "stories": {
    "manset": [{"style": "Başlıklar/Manşet", "text": "Başlık metni"}],
    "govde": [
      {"style": "Gövde İlk", "text": "İlk paragraf <c:Vurgu>vurgulu kısım</c> devam."},
      {"style": "Gövde", "text": "İkinci paragraf."}
    ]
  }
}
```

## Sayfalar
| Alan | Açıklama |
|---|---|
| `start_page` | İlk sayfanın dergi sayfa numarası. Karşılıklı sayfalarda **çift = sol**, **tek = sağ** sayfa. |
| `master` | Uygulanacak ana sayfa: tam ad (`A-Haber`) veya ön ek (`A`). Profildeki ana sayfalardan biri olmalıdır. |
| `master_text` | Ana sayfadaki **adlandırılmış** metin çerçevelerinin (vinyetlerin) bu sayfadaki metni: `{"çerçeve-adı": "metin"}`. |
| `frames` | Sayfadaki çerçeveler, alttan üste çizim sırasıyla. |

## Çerçeve konumu — şablon ızgarası
Yatay konum **sütun ızgarasıyla** verilir; kenar boşlukları ve sütun arası ana sayfadan alınır (sol/sağ sayfada iç-dış otomatik yer değiştirir).

| Alan | Açıklama |
|---|---|
| `col` | Başlangıç sütunu (1'den başlar). |
| `span` | Kaç sütun genişliğinde (sütun aralıkları dahil). |
| `top` | Üst kenar boşluğundan aşağı mesafe (mm). `0` = üst kenar boşluğu çizgisi. |
| `height` | Yükseklik (mm). **veya** |
| `bottom` | Alt kenar boşluğuna mesafe (mm). `0` = alt kenar boşluğuna kadar uzan. |
| `bleed` | Taşma payına uzatılacak kenarlar: `top`, `bottom`, `inside`, `outside`. Görsel ve zemin kutuları içindir. |

İstisnai durumlarda mutlak konum: `"x", "y", "w", "h"` (sayfanın sol üst köşesinden, mm). Doğrulayıcı kenar boşluğu dışına
taşan mutlak çerçeveler için uyarır.

## Çerçeve türleri
**`text`** — `story` (zorunlu). Aynı `story`'yi kullanan çerçeveler sayfalar arasında **plan sırasıyla birbirine bağlanır** (metin akar).
İsteğe bağlı: `columns` (çerçeve içi sütun sayısı), `valign` (`top`/`center`/`bottom`), `object_style`.

**`image`** — `image` (varlık dosya adı, zorunlu). `fit`: `fill` (çerçeveyi doldur, kırp — varsayılan) veya `fit` (tamamı görünsün).
`wrap`: `true` ise metin görselin etrafından akar (`wrap_offset` mm, varsayılan 3). İsteğe bağlı `object_style`.
Görsel altı yazısı ayrı bir `text` çerçevesidir (`Görsel Altı` gibi bir stil ile).

**`rect`** — renkli zemin/kutu. `fill`: profildeki renk adı, `tint` (0–100), isteğe bağlı `object_style`.

## Metinler (`stories`)
Her hikâye bir paragraf listesidir: `{"style": "<paragraf stili>", "text": "..."}`.
- Stil adı profildeki **ad** (`Gövde`) veya grup yolu (`Başlıklar/Manşet`) olmalıdır. Şablonda olmayan stil kullanılamaz.
- Satır içi karakter stili: `<c:Vurgu>metin</c>` (iç içe kullanılamaz).
- Satır sonu (paragraf bölmeden): `\n`.

## Tasarım ilkeleri (şablona sadakat)
1. Yalnızca şablon stillerini, renklerini ve ana sayfalarını kullan; yazı tipi/punto belirtme — stiller belirler.
2. Metin çerçevelerini ızgaraya oturt (`col`/`span`); gövde metni sütun genişliğinde akmalı.
3. Vinyetleri (`master_text`) her sayfa için doldur; bölüm adını makalenin türüne göre ver.
4. Görselleri en az 200 ppi'de kullan; doğrulayıcının çözünürlük uyarılarını dikkate al.
5. Taşan metin (overset) bırakma: raporda taşma varsa çerçeve ekle, görseli küçült veya sayfa ekle.
