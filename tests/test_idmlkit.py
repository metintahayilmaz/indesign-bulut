import json
import zipfile

import pytest

from idmlkit import IdmlDocument
from idmlkit.__main__ import main as cli
from tests.sample_idml import sample_bytes


@pytest.fixture
def idml(tmp_path):
    p = tmp_path / "ornek.idml"
    p.write_bytes(sample_bytes())
    return p


def texts(doc):
    return {p.id: p.markup() for p in doc.paragraphs()}


def test_extract_paragraphs(idml):
    doc = IdmlDocument.open(idml)
    t = texts(doc)
    assert t["u200/p0"] == "Bahar Kataloğu"
    assert t["u200/p1"] == "<r1>Yeni sezon ürünleri </r1><r2>şimdi</r2><r3> mağazalarda.</r3>"
    assert t["u200/p2"] == "Fiyatlar & kampanyalar için tabloya bakın:<x1/>"
    assert "Ürün" in t.values() and "Fiyat" in t.values()
    assert t["u200/p5"] == "Sayfa <x1/> / katalog"
    assert t["u300/p0"] == "www.ornek.com adresini ziyaret edin."
    assert doc.paragraph("u200/p0").style == "Başlık"


def test_roundtrip_edit_preserves_structure(idml, tmp_path):
    doc = IdmlDocument.open(idml)
    doc.set_text("u200/p0", "Spring Catalogue")
    doc.set_text("u200/p1", "<r1>New season products are </r1><r2>now</r2><r3> in stores.</r3>")
    doc.set_text("u200/p5", "Page <x1/> / catalogue")
    out = tmp_path / "out.idml"
    doc.save(out)

    with zipfile.ZipFile(out) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        story = z.read("Stories/Story_u200.xml").decode()
    assert "<?ACE 18?>" in story and 'CharacterStyle/Kalın' in story and "<Table" in story

    t = texts(IdmlDocument.open(out))
    assert t["u200/p0"] == "Spring Catalogue"
    assert t["u200/p1"] == "<r1>New season products are </r1><r2>now</r2><r3> in stores.</r3>"
    assert t["u200/p5"] == "Page <x1/> / catalogue"
    assert t["u300/p0"] == "www.ornek.com adresini ziyaret edin."


def test_multi_content_run_is_merged(idml):
    doc = IdmlDocument.open(idml)
    doc.set_text("u300/p0", "Visit www.example.com today.")
    doc2 = IdmlDocument.from_bytes(doc.to_bytes())
    assert doc2.paragraph("u300/p0").markup() == "Visit www.example.com today."


@pytest.mark.parametrize("bad", [
    "Sayfa / katalog",                 # yer tutucu silinmiş
    "Sayfa <x2/> katalog",             # yanlış yer tutucu
])
def test_placeholders_are_protected(idml, bad):
    doc = IdmlDocument.open(idml)
    with pytest.raises(ValueError):
        doc.set_text("u200/p5", bad)


def test_multi_style_requires_tags(idml):
    doc = IdmlDocument.open(idml)
    with pytest.raises(ValueError):
        doc.set_text("u200/p1", "etiketsiz metin")
    # Etiket atlanırsa o parça boşalır
    doc.set_text("u200/p1", "<r1>Sadece bu</r1>")
    assert doc.paragraph("u200/p1").plain() == "Sadece bu"


def test_segments_roundtrip_and_conflict(idml):
    doc = IdmlDocument.open(idml)
    seg = doc.export_segments()
    seg["paragraphs"][0]["text"] = "Spring Catalogue"
    seg["paragraphs"][1]["text"] = "bozuk"
    report = doc.import_segments(seg)
    assert report["changed"] == ["u200/p0"]
    assert report["errors"][0]["id"] == "u200/p1"

    # Belge değiştikten sonra eski segment -> çakışma
    stale = IdmlDocument.open(idml).export_segments()
    doc2 = IdmlDocument.open(idml)
    doc2.set_text("u200/p0", "Başka")
    stale["paragraphs"][0]["text"] = "Spring"
    assert doc2.import_segments(stale)["conflicts"]


def test_replace_skips_tags(idml):
    doc = IdmlDocument.open(idml)
    n = doc.replace("katalog", "broşür")
    assert n == 1
    assert doc.paragraph("u200/p0").markup() == "Bahar Kataloğu"
    assert doc.paragraph("u200/p5").markup() == "Sayfa <x1/> / broşür"


def test_cli_expand_edit_pack(idml, tmp_path, capsys):
    d = tmp_path / "acik"
    assert cli(["expand", str(idml), str(d)]) == 0
    assert cli(["set", str(d), "u200/p0", "Yaz Kataloğu"]) == 0
    seg = tmp_path / "s.json"
    assert cli(["export", str(d), "-o", str(seg)]) == 0
    data = json.loads(seg.read_text())
    assert data["paragraphs"][0]["text"] == "Yaz Kataloğu"
    out = tmp_path / "geri.idml"
    assert cli(["pack", str(d), str(out)]) == 0
    assert IdmlDocument.open(out).paragraph("u200/p0").markup() == "Yaz Kataloğu"
