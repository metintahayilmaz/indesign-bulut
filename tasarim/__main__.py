"""Komut satırı: python3 -m tasarim <komut>   (belge klasöründe ya da --doc <belge> ile)

  profil       Şablon profili: sayfa, kenar boşlukları, sütunlar, ana sayfalar/vinyetler, stiller, renkler
  varliklar    Yazılar ve görseller (piksel boyutu, en-boy oranı)
  metin <ad>   Bir yazı dosyasının (docx/txt/md) metnini göster
  kurallar     Yerleşim planı biçim referansı (SPEC.md)
  dogrula      layout.json'u şablona göre doğrula
  olustur      Doğrula ve Mac'teki InDesign'da oluştur; raporu ve önizleme PNG yollarını yazdır
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from idmlkit.profile import summarize

from . import SPEC_DOC, context_from_env
from .assets import read_text

QUEUE_TIMEOUT = 90


def print_validation(res: dict) -> None:
    for e in res["errors"]:
        print(f"HATA: {e}")
    for w in res["warnings"]:
        print(f"uyarı: {w}")
    if not res["errors"]:
        print(f"Plan geçerli: {len(res['pages'])} sayfa" + (f", {len(res['warnings'])} uyarı" if res["warnings"] else ""))


def cmd_olustur(ctx, wait: int) -> int:
    from server.jobs import JobQueue  # sunucu ile aynı kuyruk

    spec = ctx.load_spec()
    res = ctx.validate(spec)
    print_validation(res)
    if res["errors"]:
        return 1
    jobs = JobQueue(ctx.data_dir)
    job = jobs.create("layout", ctx.slug, spec=spec, template=ctx.template_slug(), author="Claude")
    print(f"InDesign işi gönderildi ({job['id'][:8]}), bekleniyor…", flush=True)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(2)
        job = jobs.get(job["id"])
        if job["status"] == "queued" and time.time() - t0 > QUEUE_TIMEOUT:
            jobs.finish(job["id"], error="InDesign ajanı işi almadı (InDesign Bulut başlatıcısı ve InDesign açık mı?)")
            print("HATA: InDesign ajanı çevrimdışı. Kullanıcıdan InDesign'ı ve başlatıcıyı açmasını isteyin.")
            return 2
        if job["status"] == "error":
            print(f"HATA (InDesign): {job['error']}")
            return 1
        if job["status"] == "done":
            result = job.get("result") or {}
            report = result.get("report") or {}
            print(f"Oluşturuldu: {report.get('pages', '?')} sayfa")
            for key, label in (("overset", "TAŞAN METİN (hikâye)"), ("missing", "eksik"), ("low_ppi", "düşük çözünürlük"),
                               ("errors", "hata"), ("warnings", "uyarı")):
                for item in report.get(key) or []:
                    print(f"{label}: {item}")
            if not report.get("overset"):
                print("Taşan metin yok.")
            print("Önizlemeler (Read ile bakın):")
            for name in result.get("previews", []):
                print(f"  {ctx.output_dir / name}")
            return 0
    print("HATA: InDesign zamanında bitiremedi.")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tasarim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", help="Belge kısa adı (belge klasöründe değilseniz)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("profil"); s.add_argument("--json", action="store_true")
    sub.add_parser("varliklar")
    s = sub.add_parser("metin"); s.add_argument("ad")
    sub.add_parser("kurallar")
    sub.add_parser("dogrula")
    s = sub.add_parser("olustur"); s.add_argument("--bekle", type=int, default=600)
    a = ap.parse_args(argv)

    if a.cmd == "kurallar":
        print(SPEC_DOC.read_text(encoding="utf-8"))
        return 0
    ctx = context_from_env(a.doc)
    if a.cmd == "profil":
        prof = ctx.profile()
        print(json.dumps(prof, ensure_ascii=False, indent=1) if a.json else summarize(prof))
    elif a.cmd == "varliklar":
        assets = ctx.assets()
        print(f"Varlık klasörü: {ctx.assets_dir}")
        print("Yazılar:")
        for t in assets["texts"]:
            print(f"  {t['name']} ({t['words']} kelime)")
        print("Görseller:")
        for i in assets["images"]:
            size = f"{i['width_px']}×{i['height_px']} px, oran {i['aspect']}" if i.get("width_px") else "boyut okunamadı"
            print(f"  {i['name']} ({size})")
        if not assets["texts"] and not assets["images"]:
            print("  (boş — kullanıcı henüz yazı/görsel yüklememiş)")
    elif a.cmd == "metin":
        path = (ctx.assets_dir / a.ad).resolve()
        if path.parent != ctx.assets_dir.resolve() or not path.exists():
            print(f"HATA: {a.ad} bulunamadı", file=sys.stderr)
            return 1
        print(read_text(path))
    elif a.cmd == "dogrula":
        if not ctx.layout_path.exists():
            print("HATA: layout.json yok")
            return 1
        res = ctx.validate()
        print_validation(res)
        return 1 if res["errors"] else 0
    elif a.cmd == "olustur":
        if not ctx.layout_path.exists():
            print("HATA: layout.json yok")
            return 1
        return cmd_olustur(ctx, a.bekle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
