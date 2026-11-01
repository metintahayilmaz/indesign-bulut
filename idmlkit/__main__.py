"""Komut satırı: python3 -m idmlkit <komut> ...

<belge> bir .idml dosyası veya açılmış IDML klasörü olabilir.

  info    <belge>                         Özet bilgi (JSON)
  text    <belge>                         Tüm paragrafları ID'leriyle listele
  export  <belge> [-o segments.json]      Düzenleme/çeviri için segment dosyası üret
  import  <belge> segments.json [-o çıktı] [--force]   Segment dosyasını uygula
  set     <belge> <paragraf-id> <metin>   Tek paragrafın metnini değiştir
  replace <belge> <ara> <yeni> [--regex] [-i]          Bul-değiştir
  expand  <dosya.idml> <klasör>           IDML'i klasöre aç
  pack    <klasör> <dosya.idml>           Klasörü IDML olarak paketle
"""
from __future__ import annotations

import argparse
import json
import sys

from . import package
from .document import IdmlDocument


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="idmlkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("doc")
    s = sub.add_parser("text"); s.add_argument("doc")
    s = sub.add_parser("export"); s.add_argument("doc"); s.add_argument("-o", "--output")
    s = sub.add_parser("import"); s.add_argument("doc"); s.add_argument("segments"); s.add_argument("-o", "--output"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("set"); s.add_argument("doc"); s.add_argument("id"); s.add_argument("text")
    s = sub.add_parser("replace"); s.add_argument("doc"); s.add_argument("find"); s.add_argument("repl")
    s.add_argument("--regex", action="store_true"); s.add_argument("-i", "--ignore-case", action="store_true")
    s = sub.add_parser("expand"); s.add_argument("idml"); s.add_argument("dir")
    s = sub.add_parser("pack"); s.add_argument("dir"); s.add_argument("idml")
    a = ap.parse_args(argv)

    if a.cmd == "expand":
        package.write_package(package.read_package(a.idml), a.dir)
        return 0
    if a.cmd == "pack":
        package.write_package(package.read_package(a.dir), a.idml)
        return 0

    doc = IdmlDocument.open(a.doc)
    if a.cmd == "info":
        print(json.dumps(doc.info(), ensure_ascii=False, indent=2))
    elif a.cmd == "text":
        sys.stdout.write(doc.to_markdown())
    elif a.cmd == "export":
        out = json.dumps(doc.export_segments(), ensure_ascii=False, indent=2)
        if a.output:
            open(a.output, "w", encoding="utf-8").write(out)
            print(f"{len(doc.paragraphs())} paragraf -> {a.output}", file=sys.stderr)
        else:
            print(out)
    elif a.cmd == "import":
        data = json.load(open(a.segments, encoding="utf-8"))
        report = doc.import_segments(data, force=a.force)
        doc.save(a.output)
        print(json.dumps({"changed": len(report["changed"]), "unchanged": report["unchanged"],
                          "conflicts": report["conflicts"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
        return 1 if report["errors"] or report["conflicts"] else 0
    elif a.cmd == "set":
        try:
            changed = doc.set_text(a.id, a.text)
        except (KeyError, ValueError) as e:
            print(f"HATA: {e}", file=sys.stderr)
            return 1
        doc.save()
        print("değişti" if changed else "aynı, değişiklik yok")
    elif a.cmd == "replace":
        n = doc.replace(a.find, a.repl, regex=a.regex, ignore_case=a.ignore_case)
        doc.save()
        print(f"{n} paragraf değişti")
    return 0


if __name__ == "__main__":
    sys.exit(main())
