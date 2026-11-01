"""Tasarım varlıkları: görsel boyutları ve metin belgelerinden (docx/txt/md) yazı çıkarma."""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path

from lxml import etree

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".psd", ".ai", ".eps", ".pdf"}
TEXT_EXT = {".docx", ".txt", ".md"}


def image_size(path: Path) -> tuple[int, int] | None:
    """(genişlik, yükseklik) piksel. Bilinmeyen biçimler için None."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return w, h
            if head[:4] == b"8BPS":  # Photoshop
                h, w = struct.unpack(">II", head[14:22])
                return w, h
            if head[:2] == b"\xff\xd8":  # JPEG: SOFn işaretini ara
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                        continue
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(1)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    f.seek(seg_len - 2, 1)
            if head[:4] in (b"II*\x00", b"MM\x00*"):  # TIFF
                end = "<" if head[:2] == b"II" else ">"
                f.seek(struct.unpack(end + "I", head[4:8])[0])
                count = struct.unpack(end + "H", f.read(2))[0]
                w = h = None
                for _ in range(count):
                    tag, typ, _n, val = struct.unpack(end + "HHI4s", f.read(12))
                    v = struct.unpack(end + ("H" if typ == 3 else "I"), val[:2] if typ == 3 else val)[0]
                    if tag == 256:
                        w = v
                    elif tag == 257:
                        h = v
                return (w, h) if w and h else None
    except (OSError, struct.error):
        return None
    return None


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text(path: Path) -> str:
    """Word belgesinden düz metin. Başlıklar '# ', kalın/italik parçalar '**…**' olarak işaretlenir."""
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        sname = (style.get(W + "val") if style is not None else "") or ""
        parts = []
        for r in p.iter(W + "r"):
            txt = "".join((t.text or "") if t.tag == W + "t" else ("\t" if t.tag == W + "tab" else "\n")
                          for t in r if t.tag in (W + "t", W + "tab", W + "br"))
            if not txt:
                continue
            rpr = r.find(W + "rPr")
            bold = rpr is not None and (rpr.find(W + "b") is not None or rpr.find(W + "i") is not None)
            parts.append(f"**{txt}**" if bold and txt.strip() else txt)
        line = re.sub(r"\*\*\*\*", "", "".join(parts)).strip()
        if not line:
            continue
        m = re.match(r"(?i)(heading|başlık|baslik)\s*(\d)", sname)
        if m:
            line = "#" * int(m.group(2)) + " " + line.replace("**", "")
        elif sname.lower() in ("title", "konubaşlığı", "konubasligi"):
            line = "# " + line.replace("**", "")
        out.append(line)
    return "\n\n".join(out) + "\n"


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def list_assets(folder: Path) -> dict:
    images, texts, other = [], [], []
    if folder.exists():
        for f in sorted(folder.iterdir()):
            if f.name.startswith(".") or not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext in IMAGE_EXT:
                size = image_size(f)
                item = {"name": f.name, "bytes": f.stat().st_size}
                if size:
                    item.update(width_px=size[0], height_px=size[1], aspect=round(size[0] / size[1], 3))
                images.append(item)
            elif ext in TEXT_EXT:
                try:
                    words = len(read_text(f).split())
                except Exception:  # noqa: BLE001
                    words = None
                texts.append({"name": f.name, "bytes": f.stat().st_size, "words": words})
            else:
                other.append({"name": f.name})
    return {"images": images, "texts": texts, "other": other}
