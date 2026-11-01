"""Yerleşim planının (layout.json) şablon profiline göre doğrulanması ve geometri hesabı.

Geometri kuralları InDesign tarafındaki script ile birebir aynıdır (bkz. agent/indesign/InDesignBulut_startup.jsx).
"""
from __future__ import annotations

import re

CHAR_TAG = re.compile(r"<c:([^>]+)>(.*?)</c>", re.S)
SIDES = {"top", "bottom", "inside", "outside"}
MIN_PPI, LOW_PPI = 200, 120


def find_master(profile: dict, name: str) -> dict | None:
    for m in profile.get("masters", []):
        if name in (m.get("name"), m.get("prefix")):
            return m
    return None


def style_names(styles: list[dict]) -> set[str]:
    out = set()
    for s in styles:
        out.add(s["name"])
        if s.get("path"):
            out.add(s["path"])
    return out


def page_side(profile: dict, start_page: int, index: int) -> str:
    if not profile.get("page", {}).get("facing"):
        return "single"
    return "left" if (start_page + index) % 2 == 0 else "right"


def master_margins(profile: dict, master: dict | None, side: str) -> dict:
    if master and master.get("pages"):
        pages = master["pages"]
        pg = pages[0] if side in ("left", "single") or len(pages) == 1 else pages[-1]
        if pg.get("margins"):
            return pg["margins"]
    return profile.get("page", {}).get("margins") or {"top": 15, "bottom": 15, "inside": 15, "outside": 15,
                                                      "columns": 1, "gutter": 5}


def frame_box(profile: dict, margins: dict, side: str, fr: dict) -> tuple[float, float, float, float]:
    """(x1, y1, x2, y2) mm, sayfanın sol üst köşesine göre."""
    page = profile.get("page", {})
    W, H = page.get("width") or 210, page.get("height") or 297
    bleed = page.get("bleed") or {}
    if side == "left":
        ml, mr = margins["outside"], margins["inside"]
    else:  # sağ veya tek sayfa: sol = iç
        ml, mr = margins["inside"], margins["outside"]
    if all(k in fr for k in ("x", "y", "w", "h")):
        x1, y1 = float(fr["x"]), float(fr["y"])
        x2, y2 = x1 + float(fr["w"]), y1 + float(fr["h"])
    else:
        n, g = int(margins.get("columns") or 1), float(margins.get("gutter") or 0)
        live = W - ml - mr
        cw = (live - (n - 1) * g) / n
        col, span = int(fr.get("col", 1)), int(fr.get("span", 1))
        x1 = ml + (col - 1) * (cw + g)
        x2 = x1 + span * cw + (span - 1) * g
        y1 = margins["top"] + float(fr.get("top", 0))
        if "height" in fr:
            y2 = y1 + float(fr["height"])
        else:
            y2 = H - margins["bottom"] - float(fr.get("bottom", 0))
    # Fiziksel sol/sağ kenar hangi mantıksal kenara (iç/dış) denk geliyor?
    left_is = "outside" if side == "left" else "inside"
    right_is = "inside" if side == "left" else "outside"
    for s in fr.get("bleed", []) or []:
        if s == "top":
            y1 = -(bleed.get("top") or 0)
        elif s == "bottom":
            y2 = H + (bleed.get("bottom") or 0)
        elif s == left_is:
            x1 = -(bleed.get(left_is) or 0)
        elif s == right_is:
            x2 = W + (bleed.get(right_is) or 0)
    return round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)


def validate(spec: dict, profile: dict, assets: dict | None = None) -> dict:
    """{"errors": [...], "warnings": [...], "pages": [{side, frames:[{box,...}]}]}"""
    errors, warnings, pages_out = [], [], []
    assets = assets or {"images": [], "texts": []}
    images = {i["name"]: i for i in assets.get("images", [])}
    pstyles = style_names(profile.get("paragraph_styles", []))
    cstyles = style_names(profile.get("character_styles", []))
    ostyles = style_names(profile.get("object_styles", []))
    swatches = {s["name"] for s in profile.get("swatches", [])}
    page = profile.get("page", {})
    W, H = page.get("width") or 210, page.get("height") or 297

    if not isinstance(spec, dict) or not isinstance(spec.get("pages"), list) or not spec["pages"]:
        return {"errors": ["Plan en az bir sayfa içeren 'pages' listesi olmalı"], "warnings": [], "pages": []}
    stories = spec.get("stories") or {}
    if not isinstance(stories, dict):
        errors.append("'stories' bir nesne olmalı: {\"hikaye-adi\": [paragraflar]}")
        stories = {}
    start = int(spec.get("start_page", 1))
    used_stories: set[str] = set()

    for pi, pg in enumerate(spec["pages"], 1):
        where = f"sayfa {pi}"
        side = page_side(profile, start, pi - 1)
        mname = pg.get("master")
        master = find_master(profile, mname) if mname else None
        if mname and master is None:
            errors.append(f"{where}: ana sayfa '{mname}' şablonda yok. Mevcut: "
                          + ", ".join(m["name"] for m in profile.get("masters", [])))
        if master:
            names = {it["name"] for it in master.get("items", []) if it.get("name")}
            for key in (pg.get("master_text") or {}):
                if key not in names:
                    warnings.append(f"{where}: '{key}' adlı vinyet çerçevesi '{master['name']}' ana sayfasında yok "
                                    f"(mevcut: {', '.join(sorted(names)) or 'adlandırılmış çerçeve yok'})")
        margins = master_margins(profile, master, side)
        n_cols = int(margins.get("columns") or 1)
        boxes = []
        for fi, fr in enumerate(pg.get("frames") or [], 1):
            fw = f"{where}, çerçeve {fi}"
            ftype = fr.get("type")
            if ftype not in ("text", "image", "rect"):
                errors.append(f"{fw}: 'type' text/image/rect olmalı")
                continue
            absolute = all(k in fr for k in ("x", "y", "w", "h"))
            if not absolute:
                col, span = fr.get("col"), fr.get("span", 1)
                if not isinstance(col, int) or not isinstance(span, int) or col < 1 or span < 1:
                    errors.append(f"{fw}: 'col' ve 'span' pozitif tam sayı olmalı (veya x/y/w/h verin)")
                    continue
                if col + span - 1 > n_cols:
                    errors.append(f"{fw}: sütun {col}+{span} ızgarayı aşıyor (şablonda {n_cols} sütun var)")
                    continue
                if "height" not in fr and "bottom" not in fr:
                    errors.append(f"{fw}: 'height' veya 'bottom' gerekli")
                    continue
            bad_bleed = set(fr.get("bleed") or []) - SIDES
            if bad_bleed:
                errors.append(f"{fw}: geçersiz bleed kenarı {sorted(bad_bleed)} (top/bottom/inside/outside)")
                continue
            x1, y1, x2, y2 = frame_box(profile, margins, side, fr)
            if x2 - x1 < 2 or y2 - y1 < 2:
                errors.append(f"{fw}: çerçeve çok küçük veya ters ({x2 - x1:.1f}×{y2 - y1:.1f} mm)")
                continue
            ml = margins["outside"] if side == "left" else margins["inside"]
            mr = margins["inside"] if side == "left" else margins["outside"]
            live = (ml - 0.5, margins["top"] - 0.5, W - mr + 0.5, H - margins["bottom"] + 0.5)
            if not fr.get("bleed") and (x1 < live[0] or y1 < live[1] or x2 > live[2] or y2 > live[3]):
                msg = f"{fw}: kenar boşluklarının dışına taşıyor ({x1:.1f},{y1:.1f})–({x2:.1f},{y2:.1f}) mm"
                (warnings if ftype != "text" else errors).append(msg + ("" if ftype != "text" else " — metin çerçeveleri yazı alanında kalmalı"))
            if fr.get("object_style") and fr["object_style"] not in ostyles:
                errors.append(f"{fw}: nesne stili '{fr['object_style']}' şablonda yok")
            if ftype == "text":
                sid = fr.get("story")
                if sid not in stories:
                    errors.append(f"{fw}: hikâye '{sid}' 'stories' içinde yok")
                used_stories.add(sid)
                if fr.get("valign") and fr["valign"] not in ("top", "center", "bottom"):
                    errors.append(f"{fw}: valign top/center/bottom olmalı")
            elif ftype == "image":
                name = fr.get("image")
                if name not in images:
                    errors.append(f"{fw}: görsel '{name}' varlıklarda yok")
                elif images[name].get("width_px"):
                    im = images[name]
                    w_in, h_in = (x2 - x1) / 25.4, (y2 - y1) / 25.4
                    sx, sy = w_in / im["width_px"], h_in / im["height_px"]
                    scale = max(sx, sy) if fr.get("fit", "fill") == "fill" else min(sx, sy)
                    ppi = round(1 / scale)
                    if ppi < LOW_PPI:
                        warnings.append(f"{fw}: '{name}' çok düşük çözünürlükte basılır (~{ppi} ppi) — görseli küçültün")
                    elif ppi < MIN_PPI:
                        warnings.append(f"{fw}: '{name}' ~{ppi} ppi (önerilen ≥{MIN_PPI})")
                if fr.get("fit", "fill") not in ("fill", "fit"):
                    errors.append(f"{fw}: fit 'fill' veya 'fit' olmalı")
            elif ftype == "rect":
                if fr.get("fill") and fr["fill"] not in swatches:
                    errors.append(f"{fw}: renk '{fr['fill']}' şablonda yok (mevcut: {', '.join(sorted(swatches))})")
            for other_type, ob in boxes:
                if ftype == "text" and other_type == "text":
                    ox = min(x2, ob[2]) - max(x1, ob[0])
                    oy = min(y2, ob[3]) - max(y1, ob[1])
                    if ox > 1 and oy > 1:
                        warnings.append(f"{fw}: başka bir metin çerçevesiyle çakışıyor")
                        break
            boxes.append((ftype, (x1, y1, x2, y2)))
        pages_out.append({"side": side, "number": start + pi - 1, "margins": margins,
                          "frames": [{"type": t, "box": b} for t, b in boxes]})

    for sid, paras in stories.items():
        if sid not in used_stories:
            warnings.append(f"hikâye '{sid}' hiçbir çerçevede kullanılmıyor (metin sayfaya girmeyecek)")
        if not isinstance(paras, list):
            errors.append(f"hikâye '{sid}': paragraf listesi olmalı")
            continue
        for i, para in enumerate(paras, 1):
            if not isinstance(para, dict) or "text" not in para:
                errors.append(f"hikâye '{sid}' paragraf {i}: {{\"style\", \"text\"}} olmalı")
                continue
            st = para.get("style")
            if st and st not in pstyles:
                errors.append(f"hikâye '{sid}' paragraf {i}: paragraf stili '{st}' şablonda yok")
            for m in CHAR_TAG.finditer(para["text"]):
                if m.group(1) not in cstyles:
                    errors.append(f"hikâye '{sid}' paragraf {i}: karakter stili '{m.group(1)}' şablonda yok")
                if "<c:" in m.group(2):
                    errors.append(f"hikâye '{sid}' paragraf {i}: iç içe <c:> kullanılamaz")
            leftover = CHAR_TAG.sub("", para["text"])
            if "<c:" in leftover or "</c>" in leftover:
                errors.append(f"hikâye '{sid}' paragraf {i}: kapanmamış <c:...> etiketi")
    return {"errors": errors, "warnings": warnings, "pages": pages_out}
