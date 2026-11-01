import io
import json
import stat
import struct
import sys
import threading
import time
import zipfile
import zlib

import pytest
from fastapi.testclient import TestClient

from idmlkit import IdmlDocument
from idmlkit.profile import build_profile
from tasarim.assets import docx_text, image_size
from tasarim.spec import validate
from tests.sample_idml import template_bytes


def png_bytes(w, h):
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg_header(w, h):
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + \
        b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x00" * 9


def docx_bytes():
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    xml = f'''<w:document {W}><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Usta ile Söyleşi</w:t></w:r></w:p>
      <w:p><w:r><w:t xml:space="preserve">Kırk yıldır </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>seramik</w:t></w:r><w:r><w:t> yapıyor.</w:t></w:r></w:p>
    </w:body></w:document>'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


@pytest.fixture
def profile():
    return build_profile(IdmlDocument.from_bytes(template_bytes()))


SPEC = {
    "start_page": 34,
    "pages": [
        {"master": "A-Haber", "master_text": {"vinyet-bolum": "RÖPORTAJ"}, "frames": [
            {"type": "image", "image": "foto.png", "col": 1, "span": 3, "top": 0, "height": 120, "bleed": ["top", "outside"]},
            {"type": "text", "story": "manset", "col": 1, "span": 3, "top": 125, "height": 30},
            {"type": "text", "story": "govde", "col": 1, "span": 1, "top": 160, "bottom": 0},
            {"type": "text", "story": "govde", "col": 2, "span": 1, "top": 160, "bottom": 0},
        ]},
        {"master": "A", "frames": [
            {"type": "text", "story": "govde", "col": 1, "span": 2, "top": 0, "bottom": 0, "columns": 2},
            {"type": "rect", "fill": "Dergi Kırmızı", "tint": 20, "col": 3, "span": 1, "top": 0, "height": 60},
        ]},
    ],
    "stories": {
        "manset": [{"style": "Başlıklar/Manşet", "text": "Usta ile Söyleşi"}],
        "govde": [{"style": "Gövde İlk", "text": "Kırk yıldır <c:Vurgu>seramik</c> yapıyor."},
                  {"style": "Gövde", "text": "İkinci paragraf."}],
    },
}


def test_profile(profile):
    assert profile["page"]["width"] == 210.0 and profile["page"]["height"] == 280.0 and profile["page"]["facing"]
    m = profile["masters"][0]
    assert m["name"] == "A-Haber" and m["pages"][0]["margins"]["columns"] == 3
    assert m["pages"][0]["margins"]["outside"] == 20.0 and m["pages"][0]["margins"]["inside"] == 15.0
    assert {"type": "text", "name": "vinyet-bolum", "text": "BÖLÜM ADI"} in m["items"]
    names = {s.get("path", s["name"]) for s in profile["paragraph_styles"]}
    assert {"Başlıklar/Manşet", "Gövde", "Görsel Altı"} <= names
    assert "Registration" not in {s["name"] for s in profile["swatches"]}


def test_validate_ok_and_geometry(profile):
    res = validate(SPEC, profile, {"images": [{"name": "foto.png", "width_px": 3000, "height_px": 2000}]})
    assert res["errors"] == [], res["errors"]
    p1, p2 = res["pages"]
    assert (p1["side"], p1["number"], p2["side"]) == ("left", 34, "right")
    # Sol sayfa: dış kenar (20 mm) solda; görsel üst ve dış kenardan taşma payına (5 mm) uzanır
    assert p1["frames"][0]["box"] == (-5.0, -5.0, 195.0, 140.0)
    # Sağ sayfa: iç kenar (15 mm) solda
    assert p2["frames"][0]["box"][0] == 15.0


@pytest.mark.parametrize("mutate,needle", [
    (lambda s: s["pages"][0].update(master="Z"), "ana sayfa 'Z'"),
    (lambda s: s["pages"][0]["frames"][1].update(col=3), "ızgarayı aşıyor"),
    (lambda s: s["stories"]["manset"][0].update(style="Arial 40"), "paragraf stili 'Arial 40'"),
    (lambda s: s["stories"]["govde"][0].update(text="<c:Kalın>x</c>"), "karakter stili 'Kalın'"),
    (lambda s: s["pages"][1]["frames"][1].update(fill="Mor"), "renk 'Mor'"),
    (lambda s: s["pages"][0]["frames"][0].update(image="yok.jpg"), "görsel 'yok.jpg'"),
    (lambda s: s["pages"][0]["frames"][1].update(top=250), "kenar boşluklarının dışına"),
])
def test_validate_rejects_off_template(profile, mutate, needle):
    spec = json.loads(json.dumps(SPEC))
    mutate(spec)
    res = validate(spec, profile, {"images": [{"name": "foto.png", "width_px": 3000, "height_px": 2000}]})
    assert any(needle in e for e in res["errors"]), res["errors"]


def test_low_resolution_warning(profile):
    res = validate(SPEC, profile, {"images": [{"name": "foto.png", "width_px": 600, "height_px": 400}]})
    assert any("çok düşük çözünürlük" in w for w in res["warnings"])


def test_asset_readers(tmp_path):
    (tmp_path / "a.png").write_bytes(png_bytes(40, 30))
    (tmp_path / "b.jpg").write_bytes(jpeg_header(1200, 800))
    (tmp_path / "c.docx").write_bytes(docx_bytes())
    assert image_size(tmp_path / "a.png") == (40, 30)
    assert image_size(tmp_path / "b.jpg") == (1200, 800)
    assert docx_text(tmp_path / "c.docx") == "# Usta ile Söyleşi\n\nKırk yıldır **seramik** yapıyor.\n"


# --- sunucu akışı ---------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_TOKEN", raising=False)
    from server.app import app
    for attr in ("storage", "jobs", "tasks", "agents"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    return TestClient(app)


def make_design(client):
    r = client.post("/api/documents", files={"file": ("Dergi Şablonu.idml", template_bytes())})
    template = r.json()["document"]["slug"]
    d = client.post("/api/designs", json={"name": "Sayı 12 Röportaj", "template": template}).json()["document"]
    assert d["kind"] == "design" and d["template"] == template
    r = client.post(f"/api/documents/{d['slug']}/assets", files=[
        ("files", ("foto.png", png_bytes(3000, 2000))), ("files", ("roportaj.docx", docx_bytes())),
        ("files", ("virus.exe", b"x"))]).json()
    assert sorted(r["saved"]) == ["foto.png", "roportaj.docx"] and r["rejected"] == ["virus.exe"]
    return template, d["slug"]


def fake_indesign_result(pages=2, overset=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("tasarim.idml", template_bytes())
        z.writestr("tasarim.indd", b"indd")
        z.writestr("tasarim.pdf", b"%PDF")
        z.writestr("rapor.json", json.dumps({"pages": pages, "overset": list(overset), "missing": [], "low_ppi": [],
                                             "errors": [], "warnings": [], "geometry": [{"page": "34"}, {"page": "35"}]}))
        for i in range(1, pages + 1):
            z.writestr(f"sayfa-{i}.png", png_bytes(10, 14))
    return buf.getvalue()


def test_design_render_roundtrip(client):
    template, slug = make_design(client)
    st = client.get(f"/api/documents/{slug}/design").json()
    assert st["layout"] is None and st["template"] == template and len(st["assets"]["images"]) == 1
    assert "Sayfa: 210.0×280.0" in client.get(f"/api/documents/{template}/profile").json()["summary"]

    assert client.post(f"/api/documents/{slug}/render").status_code == 400  # plan yok
    from server.app import app
    layout = app.state.storage.doc_dir(slug) / "layout.json"
    bad = json.loads(json.dumps(SPEC)); bad["pages"][0]["master"] = "Z"
    layout.write_text(json.dumps(bad, ensure_ascii=False))
    assert client.post(f"/api/documents/{slug}/render").status_code == 409
    layout.write_text(json.dumps(SPEC, ensure_ascii=False))
    job = client.post(f"/api/documents/{slug}/render").json()["job"]

    claimed = client.post("/api/agent/claim", json={"agent": "mac"}).json()["job"]
    assert claimed["id"] == job["id"] and claimed["kind"] == "layout"
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/agent/jobs/{job['id']}/input").content)) as z:
        assert sorted(z.namelist()) == ["gorseller/foto.png", "layout.json", "sablon.idml"]
        assert json.loads(z.read("layout.json"))["start_page"] == 34

    r = client.post(f"/api/agent/jobs/{job['id']}/complete", files={"file": ("s.zip", fake_indesign_result(overset=["govde"]))})
    res = r.json()["job"]
    assert res["status"] == "done" and res["result"]["previews"] == ["sayfa-1.png", "sayfa-2.png"]

    st = client.get(f"/api/documents/{slug}/design").json()
    assert st["previews"] == ["sayfa-1.png", "sayfa-2.png"] and st["report"]["overset"] == ["govde"]
    assert {f["name"] for f in st["outputs"]} == {"tasarim.indd", "tasarim.idml", "tasarim.pdf"}
    assert client.get(f"/api/documents/{slug}/files/cikti/sayfa-1.png").content.startswith(b"\x89PNG")
    assert client.get(f"/api/documents/{slug}/files/varliklar/foto.png").status_code == 200
    assert client.get(f"/api/documents/{slug}/files/../../etc/passwd").status_code == 404
    hist = client.get(f"/api/documents/{slug}/history").json()["history"]
    assert hist[0]["author"] == "InDesign"


def test_cli_olustur_waits_for_indesign(client, monkeypatch, capsys):
    from server.app import app
    from tasarim.__main__ import main as tasarim_cli
    _, slug = make_design(client)
    (app.state.storage.doc_dir(slug) / "layout.json").write_text(json.dumps(SPEC, ensure_ascii=False))

    def fake_agent():
        for _ in range(100):
            r = client.post("/api/agent/claim", json={"agent": "mac"})
            if r.status_code == 200:
                jid = r.json()["job"]["id"]
                client.post(f"/api/agent/jobs/{jid}/complete", files={"file": ("s.zip", fake_indesign_result())})
                return
            time.sleep(0.2)

    t = threading.Thread(target=fake_agent)
    t.start()
    code = tasarim_cli(["--doc", slug, "olustur", "--bekle", "30"])
    t.join()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Plan geçerli: 2 sayfa" in out and "Taşan metin yok." in out
    assert f"files/{slug}/cikti/sayfa-2.png" in out


def test_ai_design_mode(client, tmp_path, monkeypatch):
    """Tasarım belgelerinde Claude tasarım komutuyla, DATA_DIR ve varlık klasörü erişimiyle çalışır."""
    from server.app import app
    _, slug = make_design(client)
    fake = tmp_path / "claude"
    fake.write_text(f"""#!{sys.executable}
import json, subprocess, sys, pathlib
args = sys.argv[1:]
pathlib.Path("layout.json").write_text(json.dumps({json.dumps(SPEC, ensure_ascii=False)!r} and {SPEC!r}, ensure_ascii=False))
r = subprocess.run([sys.executable, "-m", "tasarim", "dogrula"], capture_output=True, text=True)
info = {{"tasarim_prompt": "dergi sayfa tasarımcısı" in args[1], "add_dir": args[args.index("--add-dir") + 1],
        "dogrula": r.stdout.strip()}}
print(json.dumps({{"result": json.dumps(info, ensure_ascii=False), "is_error": False}}))
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_BIN", str(fake))
    client.post(f"/api/documents/{slug}/ai", json={"instruction": "Röportajı 2 sayfaya yerleştir"})
    for _ in range(100):
        t = client.get(f"/api/documents/{slug}/ai").json()["tasks"][0]
        if t["status"] != "running":
            break
        time.sleep(0.1)
    assert t["status"] == "done", t
    info = json.loads(t["result"])
    assert info["tasarim_prompt"] is True
    assert info["add_dir"].endswith(f"files/{slug}")
    assert info["dogrula"] == "Plan geçerli: 2 sayfa"
    assert (app.state.storage.doc_dir(slug) / "layout.json").exists()
    assert client.get(f"/api/documents/{slug}/history").json()["history"][0]["message"].startswith("Claude:")
