"""IDML belgesi: hikâyeleri yükler, paragrafları listeler, değişiklikleri kaydeder."""
from __future__ import annotations

import os
import re
from pathlib import Path

from lxml import etree

from . import package
from .text import Paragraph, extract_paragraphs

SEGMENTS_FORMAT = "idmlkit-segments/1"


class IdmlDocument:
    def __init__(self, files: dict[str, bytes], source: str | None = None):
        self.files = files
        self.source = source
        self._trees: dict[str, etree._ElementTree] = {}
        self._paras: list[Paragraph] | None = None
        self._dirty: set[str] = set()

    # --- yükleme / kaydetme -------------------------------------------
    @classmethod
    def open(cls, path: str | os.PathLike) -> "IdmlDocument":
        return cls(package.read_package(path), source=str(path))

    @classmethod
    def from_bytes(cls, data: bytes) -> "IdmlDocument":
        return cls(package.read_bytes(data))

    def _serialize_dirty(self) -> None:
        for name in self._dirty:
            self.files[name] = etree.tostring(self._trees[name], xml_declaration=True,
                                              encoding="UTF-8", standalone=True)

    def save(self, path: str | os.PathLike | None = None) -> set[str]:
        """Kaydeder; değişen iç dosyaların adlarını döndürür."""
        target = path or self.source
        if target is None:
            raise ValueError("Kaydetme yolu belirtilmedi")
        self._serialize_dirty()
        changed = set(self._dirty)
        in_place = self.source is not None and Path(target).resolve() == Path(self.source).resolve()
        package.write_package(self.files, target, only=changed if in_place and Path(target).is_dir() else None)
        self._dirty.clear()
        return changed

    def to_bytes(self) -> bytes:
        self._serialize_dirty()
        return package.to_bytes(self.files)

    # --- yapı ----------------------------------------------------------
    def story_files(self) -> list[str]:
        """designmap.xml'deki sırayla hikâye dosyaları."""
        dm = etree.fromstring(self.files["designmap.xml"])
        srcs = [el.get("src") for el in dm.iter() if isinstance(el.tag, str)
                and etree.QName(el).localname == "Story" and el.get("src")]
        if not srcs:
            srcs = sorted(n for n in self.files if n.startswith("Stories/"))
        return [s for s in srcs if s in self.files]

    def _tree(self, name: str):
        if name not in self._trees:
            parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, huge_tree=True)
            self._trees[name] = etree.ElementTree(etree.fromstring(self.files[name], parser))
        return self._trees[name]

    def paragraphs(self) -> list[Paragraph]:
        if self._paras is None:
            self._paras, self._para_file = [], {}
            for name in self.story_files():
                root = self._tree(name).getroot()
                story_el = next((e for e in root.iter() if isinstance(e.tag, str) and e.tag == "Story"), None)
                sid = story_el.get("Self") if story_el is not None else Path(name).stem
                for p in extract_paragraphs(root, sid):
                    self._paras.append(p)
                    self._para_file[p.id] = name
        return self._paras

    def paragraph(self, pid: str) -> Paragraph:
        for p in self.paragraphs():
            if p.id == pid:
                return p
        raise KeyError(f"Paragraf bulunamadı: {pid}")

    def info(self) -> dict:
        paras = self.paragraphs()
        spreads = [n for n in self.files if n.startswith("Spreads/")]
        return {
            "stories": len(self.story_files()),
            "spreads": len(spreads),
            "paragraphs": len(paras),
            "words": sum(len(p.plain().split()) for p in paras),
            "paragraph_styles": sorted({p.style for p in paras if p.style}),
        }

    # --- düzenleme -----------------------------------------------------
    def set_text(self, pid: str, markup: str) -> bool:
        p = self.paragraph(pid)
        if p.markup() == markup:
            return False
        p.apply(markup)
        self._dirty.add(self._para_file[pid])
        return True

    def replace(self, pattern: str, repl: str, regex: bool = False, ignore_case: bool = False) -> int:
        """Tüm paragraflarda bul-değiştir (yer tutucu ve etiketlere dokunmaz). Değişen paragraf sayısını döndürür."""
        flags = re.I if ignore_case else 0
        rx = re.compile(pattern if regex else re.escape(pattern), flags)
        count = 0
        token = re.compile(r"(</?r\d+>|<x\d+/>)")
        for p in self.paragraphs():
            parts = token.split(p.markup())
            new = "".join(part if token.fullmatch(part) else rx.sub(repl, part) for part in parts)
            if self.set_text(p.id, new):
                count += 1
        return count

    # --- segment (çeviri/düzenleme) dosyaları ------------------------
    def export_segments(self) -> dict:
        return {
            "format": SEGMENTS_FORMAT,
            "document": Path(self.source).name if self.source else None,
            "instructions": ("Sadece 'text' alanlarını düzenleyin. <rN>...</rN> etiketleri karakter stillerini, "
                             "<xN/> satır içi nesneleri gösterir; <xN/> silinmemeli ve sırası değişmemelidir."),
            "paragraphs": [
                {"id": p.id, "style": p.style, "hash": p.source_hash(), "source": p.markup(), "text": p.markup()}
                for p in self.paragraphs()
            ],
        }

    def import_segments(self, data: dict, force: bool = False) -> dict:
        """Segment dosyasındaki değişiklikleri uygular. Rapor döndürür."""
        report = {"changed": [], "unchanged": 0, "conflicts": [], "errors": []}
        by_id = {p.id: p for p in self.paragraphs()}
        for seg in data.get("paragraphs", []):
            pid, text = seg.get("id"), seg.get("text")
            if pid not in by_id:
                report["errors"].append({"id": pid, "error": "paragraf bulunamadı"})
                continue
            if text is None or text == seg.get("source", by_id[pid].markup()):
                report["unchanged"] += 1
                continue
            if not force and seg.get("hash") and seg["hash"] != by_id[pid].source_hash():
                report["conflicts"].append({"id": pid, "error": "belge, segment dışa aktarıldıktan sonra değişmiş"})
                continue
            try:
                if self.set_text(pid, text):
                    report["changed"].append(pid)
                else:
                    report["unchanged"] += 1
            except ValueError as e:
                report["errors"].append({"id": pid, "error": str(e)})
        return report

    def to_markdown(self) -> str:
        lines, story = [], None
        for p in self.paragraphs():
            if p.story != story:
                story = p.story
                lines.append(f"\n## Hikâye {story}\n")
            lines.append(f"[{p.id}] ({p.style}) {p.markup()}")
        return "\n".join(lines).strip() + "\n"
