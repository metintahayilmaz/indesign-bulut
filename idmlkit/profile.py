"""Şablon profili: IDML'den sayfa geometrisi, ana sayfalar (vinyetler), stiller ve renkleri çıkarır.

Tasarım planı (layout.json) yalnızca bu profilde olan öğeleri kullanabilir. Ölçüler milimetredir.
"""
from __future__ import annotations

from lxml import etree

from .text import extract_paragraphs

PT_TO_MM = 25.4 / 72


def mm(value) -> float | None:
    try:
        return round(float(value) * PT_TO_MM, 2)
    except (TypeError, ValueError):
        return None


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _prop(el, name: str) -> str | None:
    """Öznitelik ya da <Properties><Name>değer</Name></Properties> olarak saklanan değeri okur."""
    if el.get(name) is not None:
        return el.get(name)
    for props in el:
        if _local(props) == "Properties":
            for p in props:
                if _local(p) == name:
                    return (p.text or "").strip() or None
    return None


def _ref_name(ref: str | None) -> str | None:
    if not ref:
        return None
    name = ref.split("/", 1)[1] if "/" in ref else ref
    name = name.replace("%3a", ":").replace("$ID/", "")
    return name or None


def _margins(el) -> dict | None:
    if el is None:
        return None
    return {
        "top": mm(el.get("Top")), "bottom": mm(el.get("Bottom")),
        "inside": mm(el.get("Left")), "outside": mm(el.get("Right")),
        "columns": int(el.get("ColumnCount", "1")), "gutter": mm(el.get("ColumnGutter")),
    }


def _find(root, name: str):
    return next((e for e in root.iter() if _local(e) == name), None)


def _styles(root, kind: str) -> list[dict]:
    """kind: ParagraphStyle | CharacterStyle | ObjectStyle"""
    out = []

    def walk(node, groups):
        for child in node:
            tag = _local(child)
            if tag == f"{kind}Group":
                walk(child, groups + [child.get("Name", "")])
            elif tag == kind:
                raw = child.get("Name", "")
                if raw.startswith("$ID/") or raw.startswith("["):
                    continue
                leaf = raw.split(":")[-1]
                path = "/".join([g for g in groups if g] + [leaf])
                item = {"name": leaf}
                if path != leaf:
                    item["path"] = path
                if kind != "ObjectStyle":
                    font = _prop(child, "AppliedFont")
                    if font:
                        item["font"] = font
                    for attr, key in (("FontStyle", "style"), ("PointSize", "size")):
                        if child.get(attr):
                            item[key] = child.get(attr) if key == "style" else float(child.get(attr))
                    lead = _prop(child, "Leading")
                    if lead and lead != "Auto":
                        try:
                            item["leading"] = float(lead)
                        except ValueError:
                            pass
                    for attr, key in (("Justification", "align"), ("SpaceBefore", "space_before"),
                                      ("SpaceAfter", "space_after"), ("Capitalization", "caps"),
                                      ("FillColor", "color")):
                        v = child.get(attr)
                        if v and v not in ("0", "Normal"):
                            item[key] = _ref_name(v) if key == "color" else (float(v) if key.startswith("space") else v)
                    based = _ref_name(_prop(child, "BasedOn"))
                    if based and not based.startswith("["):
                        item["based_on"] = based.split(":")[-1]
                    nxt = _ref_name(child.get("NextStyle"))
                    if kind == "ParagraphStyle" and nxt and nxt.split(":")[-1] != leaf and not nxt.startswith("["):
                        item["next"] = nxt.split(":")[-1]
                out.append(item)

    for root_group in root.iter():
        if _local(root_group) == f"Root{kind}Group":
            walk(root_group, [])
    return out


def build_profile(doc) -> dict:
    """`doc`: idmlkit.IdmlDocument"""
    files = doc.files
    prof: dict = {"page": {}, "baseline": None, "masters": [], "paragraph_styles": [],
                  "character_styles": [], "object_styles": [], "swatches": [], "layers": []}

    if "Resources/Preferences.xml" in files:
        pref = etree.fromstring(files["Resources/Preferences.xml"])
        dp = _find(pref, "DocumentPreference")
        if dp is not None:
            prof["page"] = {
                "width": mm(dp.get("PageWidth")), "height": mm(dp.get("PageHeight")),
                "facing": dp.get("FacingPages") == "true",
                "bleed": {"top": mm(dp.get("DocumentBleedTopOffset", 0)),
                          "bottom": mm(dp.get("DocumentBleedBottomOffset", 0)),
                          "inside": mm(dp.get("DocumentBleedInsideOrLeftOffset", 0)),
                          "outside": mm(dp.get("DocumentBleedOutsideOrRightOffset", 0))},
            }
        prof["page"]["margins"] = _margins(_find(pref, "MarginPreference"))
        gp = _find(pref, "GridPreference")
        if gp is not None and gp.get("BaselineDivision"):
            prof["baseline"] = {"start": mm(gp.get("BaselineStart")), "increment_pt": float(gp.get("BaselineDivision")),
                                "increment": mm(gp.get("BaselineDivision"))}

    # Ana sayfa hikâyelerinin metni (vinyet içerikleri)
    story_text: dict[str, str] = {}
    for name in files:
        if name.startswith("Stories/"):
            root = etree.fromstring(files[name])
            el = next((e for e in root.iter() if isinstance(e.tag, str) and e.tag == "Story"), None)
            if el is not None:
                paras = extract_paragraphs(root, el.get("Self"))
                story_text[el.get("Self")] = "\n".join(p.markup() for p in paras)

    dm = etree.fromstring(files["designmap.xml"])
    for el in dm.iter():
        if _local(el) == "Layer" and el.get("Name"):
            prof["layers"].append(el.get("Name"))
    master_srcs = [el.get("src") for el in dm.iter() if _local(el) == "MasterSpread" and el.get("src")]
    for src in master_srcs:
        if src not in files:
            continue
        root = etree.fromstring(files[src])
        ms = next((e for e in root.iter() if _local(e) == "MasterSpread" and e.get("Self")), None)
        if ms is None:
            continue
        pages = [p for p in ms if _local(p) == "Page"]
        info = {"name": ms.get("Name"), "prefix": ms.get("NamePrefix"),
                "based_on": _ref_name(ms.get("BasedOn")) if ms.get("BasedOn") not in (None, "n") else None,
                "pages": [], "items": []}
        for i, p in enumerate(pages):
            side = "single" if len(pages) == 1 else ("left" if i == 0 else "right")
            info["pages"].append({"side": side, "margins": _margins(_find(p, "MarginPreference"))})
        for item in ms.iter():
            tag = _local(item)
            if tag == "TextFrame":
                name = item.get("Name", "$ID/")
                text = story_text.get(item.get("ParentStory"), "")
                entry = {"type": "text", "name": None if name.startswith("$ID/") else name, "text": text[:200]}
                if entry["name"] or entry["text"]:
                    info["items"].append(entry)
        prof["masters"].append(info)

    if "Resources/Styles.xml" in files:
        st = etree.fromstring(files["Resources/Styles.xml"])
        prof["paragraph_styles"] = _styles(st, "ParagraphStyle")
        prof["character_styles"] = _styles(st, "CharacterStyle")
        prof["object_styles"] = _styles(st, "ObjectStyle")

    if "Resources/Graphic.xml" in files:
        gr = etree.fromstring(files["Resources/Graphic.xml"])
        for c in gr.iter():
            if _local(c) in ("Color", "Gradient", "Tint") and c.get("Name") and not c.get("Name").startswith("$ID/") \
                    and c.get("Name") != "Registration":
                sw = {"name": c.get("Name"), "kind": _local(c).lower()}
                if c.get("Space"):
                    sw["space"] = c.get("Space")
                if c.get("ColorValue"):
                    sw["value"] = c.get("ColorValue")
                prof["swatches"].append(sw)
        names = {s["name"] for s in prof["swatches"]}
        for builtin in ("Black", "Paper", "None"):
            if builtin not in names:
                prof["swatches"].append({"name": builtin, "kind": "builtin"})
    return prof


def summarize(prof: dict) -> str:
    """İnsan/Claude için kısa özet."""
    p = prof.get("page", {})
    lines = [f"Sayfa: {p.get('width')}×{p.get('height')} mm, {'karşılıklı' if p.get('facing') else 'tek'} sayfa, "
             f"taşma payı {p.get('bleed', {}).get('top')} mm"]
    if prof.get("baseline"):
        b = prof["baseline"]
        lines.append(f"Taban çizgisi ızgarası: başlangıç {b['start']} mm, aralık {b['increment_pt']} pt")
    for m in prof.get("masters", []):
        lines.append(f"Ana sayfa '{m['name']}':")
        for pg in m["pages"]:
            mg = pg["margins"] or {}
            lines.append(f"  {pg['side']}: üst {mg.get('top')} alt {mg.get('bottom')} iç {mg.get('inside')} dış {mg.get('outside')} mm, "
                         f"{mg.get('columns')} sütun, ara {mg.get('gutter')} mm")
        for it in m["items"]:
            lines.append(f"  vinyet/öğe: ad={it['name']!r} metin={it['text'][:60]!r}")
    lines.append("Paragraf stilleri: " + ", ".join(s.get("path", s["name"]) for s in prof.get("paragraph_styles", [])))
    lines.append("Karakter stilleri: " + ", ".join(s.get("path", s["name"]) for s in prof.get("character_styles", [])))
    lines.append("Nesne stilleri: " + ", ".join(s.get("path", s["name"]) for s in prof.get("object_styles", [])))
    lines.append("Renkler: " + ", ".join(s["name"] for s in prof.get("swatches", [])))
    return "\n".join(lines)
