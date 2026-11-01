"""IDML hikâyelerindeki (Story) metni paragraf düzeyinde çıkarma ve geri yazma.

İşaretleme (markup) kuralları — Claude ve insanlar bu metni düzenler:
  * Paragrafta tek bir karakter stili varsa metin düz yazılır:      "Merhaba dünya"
  * Birden çok karakter stili varsa her parça numaralı etiketle sarılır:
        "<r1>Normal metin, </r1><r2>kalın kısım</r2><r3> devam.</r3>"
    Etiket içeriği değiştirilebilir, etiket silinirse o parça boşalır.
  * Satır içi nesneler (tablo, dipnot, sayfa numarası, bağlı görsel...) <x1/> gibi
    yer tutucularla gösterilir. Bunlar SİLİNMEMELİ ve sırası DEĞİŞTİRİLMEMELİDİR.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from lxml import etree

# Metni içinde taşıyan, aşağı inilecek sarmalayıcılar
WRAPPERS = {"XMLElement", "HyperlinkTextSource", "CrossReferenceSource", "Change", "ParagraphDestination"}
# Kendi paragraf dizisini başlatan kapsayıcılar (satır içi nesne olarak da yer tutucu alırlar)
CONTAINERS = {"Footnote", "Note"}
# Tamamen yok sayılanlar (konum işaretleri, özellikler)
IGNORED = {"Properties", "HyperlinkTextDestination", "PageReference", "Bookmark", "XMLAttribute",
           "XMLComment", "XMLInstruction", "StoryPreference", "InCopyExportOption", "MetadataPacketPreference"}

TOKEN_RE = re.compile(r"<(/?)r(\d+)>|<x(\d+)/>")


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _style_name(ref: str | None) -> str:
    if not ref:
        return ""
    name = ref.split("/", 1)[1] if "/" in ref else ref
    return name.replace("$ID/", "")


@dataclass
class Item:
    kind: str                      # "run" | "obj"
    contents: list = field(default_factory=list)   # run: düzenlenebilir <Content> öğeleri
    csr: object = None
    label: str = ""                # obj: nesne türü

    def text(self) -> str:
        return "".join(c.text or "" for c in self.contents)


@dataclass
class Paragraph:
    id: str
    story: str
    style: str
    items: list[Item] = field(default_factory=list)

    # --- gruplama: yer tutucular arasındaki boşluklar -----------------
    def _gaps(self) -> list[list[Item]]:
        gaps: list[list[Item]] = [[]]
        for it in self.items:
            if it.kind == "obj":
                gaps.append([])
            else:
                gaps[-1].append(it)
        return gaps

    def markup(self) -> str:
        out, run_no, obj_no = [], 0, 0
        gaps = self._gaps()
        for gi, gap in enumerate(gaps):
            if len(gap) == 1:
                run_no += 1
                out.append(gap[0].text())
            else:
                for it in gap:
                    run_no += 1
                    out.append(f"<r{run_no}>{it.text()}</r{run_no}>")
            if gi < len(gaps) - 1:
                obj_no += 1
                out.append(f"<x{obj_no}/>")
        return "".join(out)

    def plain(self) -> str:
        return "".join(it.text() for it in self.items if it.kind == "run")

    def objects(self) -> list[str]:
        return [it.label for it in self.items if it.kind == "obj"]

    def source_hash(self) -> str:
        return hashlib.sha1(self.markup().encode("utf-8")).hexdigest()[:12]

    # --- geri yazma ----------------------------------------------------
    def apply(self, markup: str) -> None:
        """Yeni işaretlemeyi paragrafa uygular. Hatalıysa ValueError fırlatır, hiçbir şey değişmez."""
        gaps = self._gaps()
        # Yer tutuculara göre böl
        pieces, last, expected_x = [], 0, 1
        for m in TOKEN_RE.finditer(markup):
            if m.group(3) is not None:
                if int(m.group(3)) != expected_x:
                    raise ValueError(f"{self.id}: <x{expected_x}/> bekleniyordu, <x{m.group(3)}/> bulundu "
                                     "(yer tutucular silinemez/yer değiştiremez)")
                pieces.append(markup[last:m.start()])
                last = m.end()
                expected_x += 1
        pieces.append(markup[last:])
        if len(pieces) != len(gaps):
            raise ValueError(f"{self.id}: {len(gaps) - 1} yer tutucu bekleniyordu, {len(pieces) - 1} bulundu")

        new_texts: list[tuple[Item, str]] = []
        run_no = 0
        for gap, piece in zip(gaps, pieces):
            numbers = list(range(run_no + 1, run_no + 1 + len(gap)))
            run_no += len(gap)
            tagged = _parse_runs(piece, self.id)
            if not gap:
                if piece.strip() and TOKEN_RE.sub("", piece).strip():
                    raise ValueError(f"{self.id}: bu konumda metin olamaz (karakter stili yok): {piece!r}")
                continue
            if len(gap) == 1 and tagged is None:
                new_texts.append((gap[0], piece))
                continue
            if tagged is None:
                raise ValueError(f"{self.id}: bu bölümde birden çok stil var; metni <rN>...</rN> etiketleriyle yazın")
            unknown = set(tagged) - set(numbers)
            if unknown:
                raise ValueError(f"{self.id}: bilinmeyen etiket(ler) r{sorted(unknown)} — bu bölümde geçerli: r{numbers}")
            for n, it in zip(numbers, gap):
                new_texts.append((it, tagged.get(n, "")))

        for it, txt in new_texts:
            _set_run_text(it, txt)


def _parse_runs(piece: str, pid: str) -> dict[int, str] | None:
    """`<rN>..</rN>` etiketlerini çözer. Etiket yoksa None döner."""
    if not re.search(r"</?r\d+>", piece):
        return None
    result: dict[int, str] = {}
    pos = 0
    for m in re.finditer(r"<r(\d+)>(.*?)</r\1>", piece, flags=re.S):
        if piece[pos:m.start()].strip():
            raise ValueError(f"{pid}: etiket dışında metin var: {piece[pos:m.start()]!r}")
        n = int(m.group(1))
        if n in result:
            raise ValueError(f"{pid}: <r{n}> birden fazla kez kullanılmış")
        result[n] = m.group(2)
        pos = m.end()
    rest = piece[pos:]
    if rest.strip():
        raise ValueError(f"{pid}: kapanmamış etiket veya etiket dışında metin: {rest!r}")
    for v in result.values():
        if re.search(r"</?r\d+>", v):
            raise ValueError(f"{pid}: iç içe etiket kullanılamaz")
    return result


def _set_run_text(item: Item, text: str) -> None:
    if not item.contents:
        return
    first, *rest = item.contents
    first.text = text
    for c in rest:
        parent = c.getparent()
        if parent is not None:
            # c'nin tail'i (normalde boş) korunur
            if c.tail:
                prev = c.getprevious()
                if prev is not None:
                    prev.tail = (prev.tail or "") + c.tail
                else:
                    parent.text = (parent.text or "") + c.tail
            parent.remove(c)
    item.contents = [first]


class _Walker:
    def __init__(self, story_id: str):
        self.story_id = story_id
        self.paragraphs: list[Paragraph] = []

    def walk_story(self, story_el) -> list[Paragraph]:
        self._walk(story_el, {"psr": None, "csr": None, "para": None})
        return [p for p in self.paragraphs if p.items]

    def _para(self, st) -> Paragraph:
        if st["para"] is None:
            style = _style_name(st["psr"].get("AppliedParagraphStyle")) if st["psr"] is not None else ""
            p = Paragraph(id=f"{self.story_id}/p{len(self.paragraphs)}", story=self.story_id, style=style)
            self.paragraphs.append(p)
            st["para"] = p
        return st["para"]

    def _add_content(self, el, st):
        p = self._para(st)
        if len(el):  # içinde işleme talimatı (ör. <?ACE 18?> sayfa no) olan Content kilitlidir
            p.items.append(Item(kind="obj", label="özel karakter"))
            return
        last = p.items[-1] if p.items else None
        if last is not None and last.kind == "run" and last.csr is st["csr"]:
            last.contents.append(el)
        else:
            p.items.append(Item(kind="run", contents=[el], csr=st["csr"]))

    def _walk(self, node, st):
        for child in node:
            tag = _local(child)
            if not tag or tag in IGNORED:
                continue
            if tag == "ParagraphStyleRange":
                prev = st["psr"]
                st["psr"] = child
                self._walk(child, st)
                st["psr"] = prev
            elif tag == "CharacterStyleRange":
                prev = st["csr"]
                st["csr"] = child
                self._walk(child, st)
                st["csr"] = prev
            elif tag == "Content":
                self._add_content(child, st)
            elif tag == "Br":
                st["para"] = None
            elif tag in WRAPPERS:
                self._walk(child, st)
            elif tag in CONTAINERS or tag == "Table":
                self._para(st).items.append(Item(kind="obj", label={"Footnote": "dipnot", "Note": "not", "Table": "tablo"}[tag]))
                cells = [c for c in child if _local(c) == "Cell"] if tag == "Table" else [child]
                for cell in cells:
                    sub = {"psr": None, "csr": None, "para": None}
                    self._walk(cell, sub)
            elif tag == "Cell":
                sub = {"psr": None, "csr": None, "para": None}
                self._walk(child, sub)
            else:
                # Bağlı görsel, metin çerçevesi, metin değişkeni vb.
                self._para(st).items.append(Item(kind="obj", label=tag))


def extract_paragraphs(story_root, story_id: str) -> list[Paragraph]:
    # Kök genellikle <idPkg:Story> sarmalayıcısıdır; asıl öğe ad alansız <Story>'dir.
    story_el = next((e for e in story_root.iter() if isinstance(e.tag, str) and e.tag == "Story"), None)
    if story_el is None:
        return []
    return _Walker(story_id).walk_story(story_el)
