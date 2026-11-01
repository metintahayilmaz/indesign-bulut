#!/usr/bin/env python3
"""InDesign Bulut — masaüstü ajanı (yalnızca Python standart kütüphanesi, kurulum gerektirmez).

Bulut sunucusundaki işleri (PDF dışa aktarma, .indd -> .idml) alır, InDesign'ın izlediği
"sıcak klasöre" bırakır ve InDesign'ın ürettiği çıktıyı sunucuya geri yükler.
InDesign tarafında `indesign/InDesignBulut_startup.jsx` başlangıç script'i kurulu olmalıdır.

Kullanım:
  python3 agent.py run    --server https://sunucu --token GIZLI
  python3 agent.py upload --server https://sunucu --token GIZLI  ~/Arsiv   # klasördeki tüm .idml/.indd'leri yükle

Ortam değişkenleri: BULUT_SERVER, BULUT_TOKEN, BULUT_AGENT_NAME, BULUT_HOTFOLDER
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

DEFAULT_HOT = Path.home() / "Documents" / "InDesignBulut"
JOB_TIMEOUT = 15 * 60


class Client:
    def __init__(self, server: str, token: str | None):
        self.server, self.token = server.rstrip("/"), token

    def _req(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None):
        req = urllib.request.Request(self.server + path, data=body, method=method)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if ctype:
            req.add_header("Content-Type", ctype)
        return urllib.request.urlopen(req, timeout=300)

    def json(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload or {}).encode()
        with self._req(method, path, body, "application/json") as r:
            return None if r.status == 204 else json.loads(r.read() or b"null")

    def download(self, path: str, dest: Path) -> None:
        with self._req("GET", path) as r, open(dest, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)

    def upload(self, path: str, file: Path, fields: dict | None = None):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
                     f'Content-Type: application/octet-stream\r\n\r\n'.encode())
        body = b"".join(parts) + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        with self._req("POST", path, body, f"multipart/form-data; boundary={boundary}") as r:
            return json.loads(r.read())


def process(client: Client, job: dict, hot: Path) -> None:
    inbox, outbox = hot / "inbox", hot / "outbox"
    jid, kind = job["id"], job["kind"]
    if kind == "layout":
        return process_layout(client, job, hot)
    in_ext, out_ext = (".idml", ".pdf") if kind == "pdf" else (".indd", ".idml")
    src = inbox / f"{jid}{in_ext}"
    print(f"[{time.strftime('%H:%M:%S')}] İş {jid[:8]} ({kind}, belge: {job['doc']}) indiriliyor…")
    client.download(f"/api/agent/jobs/{jid}/input", src)
    # Talimat dosyası en son yazılır: InDesign script'i yalnızca .json gördüğünde işe başlar
    tmp = inbox / f"{jid}.json.tmp"
    tmp.write_text(json.dumps({"id": jid, "kind": kind, "input": src.name, "output": f"{jid}{out_ext}",
                               "preset": job["params"].get("preset") or "[High Quality Print]"}), encoding="utf-8")
    tmp.rename(inbox / f"{jid}.json")

    out, err = outbox / f"{jid}{out_ext}", outbox / f"{jid}.error.txt"
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        if out.exists():
            client.upload(f"/api/agent/jobs/{jid}/complete", out)
            print(f"    tamamlandı -> {out.name} yüklendi")
            break
        if err.exists():
            msg = err.read_text(encoding="utf-8", errors="replace")
            client.json("POST", f"/api/agent/jobs/{jid}/fail", {"error": f"InDesign: {msg}"})
            print(f"    HATA: {msg}")
            break
        time.sleep(2)
    else:
        client.json("POST", f"/api/agent/jobs/{jid}/fail",
                    {"error": "InDesign zamanında yanıt vermedi. InDesign açık mı, başlangıç script'i kurulu mu?"})
        print("    zaman aşımı")
    for f in (src, inbox / f"{jid}.json", out, err):
        f.unlink(missing_ok=True)


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name) or "belge"


def process_layout(client: Client, job: dict, hot: Path) -> None:
    """Tasarım işi: paket (şablon + layout.json + görseller) kalıcı bir klasöre açılır; görseller InDesign
    belgesine bağlantı olarak yerleştiği için bu klasör silinmez: Belgeler/InDesignBulut/tasarimlar/<belge>/"""
    jid = job["id"]
    inbox, outbox = hot / "inbox", hot / "outbox"
    work = hot / "tasarimlar" / safe_name(job["doc"])
    (work / "gorseller").mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%H:%M:%S')}] Tasarım işi {jid[:8]} (belge: {job['doc']}) indiriliyor…")
    bundle = inbox / f"{jid}.zip"
    client.download(f"/api/agent/jobs/{jid}/input", bundle)
    for old in ("sablon.indd", "sablon.idml", "layout.json"):
        (work / old).unlink(missing_ok=True)
    with zipfile.ZipFile(bundle) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or ".." in parts or not parts:
                continue
            target = work.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    bundle.unlink(missing_ok=True)
    template = work / ("sablon.indd" if (work / "sablon.indd").exists() else "sablon.idml")
    outdir = outbox / jid
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)
    tmp = inbox / f"{jid}.json.tmp"
    tmp.write_text(json.dumps({"id": jid, "kind": "layout", "template": template.as_posix(),
                               "spec": (work / "layout.json").as_posix(), "assets": (work / "gorseller").as_posix(),
                               "outdir": outdir.as_posix(), "preset": "[High Quality Print]"}), encoding="utf-8")
    tmp.rename(inbox / f"{jid}.json")

    done, err = outbox / f"{jid}.done", outbox / f"{jid}.error.txt"
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        if done.exists():
            result = outbox / f"{jid}-sonuc.zip"
            with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(outdir.iterdir()):
                    z.write(f, f.name)
            client.upload(f"/api/agent/jobs/{jid}/complete", result)
            print(f"    tamamlandı -> {len(list(outdir.iterdir()))} dosya yüklendi")
            result.unlink(missing_ok=True)
            break
        if err.exists():
            msg = err.read_text(encoding="utf-8", errors="replace")
            client.json("POST", f"/api/agent/jobs/{jid}/fail", {"error": f"InDesign: {msg}"})
            print(f"    HATA: {msg}")
            break
        time.sleep(2)
    else:
        client.json("POST", f"/api/agent/jobs/{jid}/fail",
                    {"error": "InDesign zamanında yanıt vermedi. InDesign açık mı, başlangıç script'i güncel mi?"})
        print("    zaman aşımı")
    for f in (inbox / f"{jid}.json", done, err):
        f.unlink(missing_ok=True)
    shutil.rmtree(outdir, ignore_errors=True)


def run(args) -> None:
    hot = Path(args.hotfolder).expanduser()
    for d in ("inbox", "outbox"):
        (hot / d).mkdir(parents=True, exist_ok=True)
    client = Client(args.server, args.token)
    print(f"Ajan '{args.name}' çalışıyor. Sunucu: {args.server}\nSıcak klasör: {hot}\n(Durdurmak için Ctrl+C)")
    while True:
        try:
            res = client.json("POST", "/api/agent/claim", {"agent": args.name})
            if res and res.get("job"):
                process(client, res["job"], hot)
                continue
        except urllib.error.HTTPError as e:
            print(f"Sunucu hatası: {e.code} {e.read()[:200]!r}")
            if e.code == 401:
                sys.exit("Erişim anahtarı geçersiz (--token).")
        except (urllib.error.URLError, OSError) as e:
            print(f"Bağlantı hatası: {e}")
        time.sleep(args.interval)


def upload(args) -> None:
    client = Client(args.server, args.token)
    root = Path(args.folder).expanduser()
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".idml", ".indd") and not p.name.startswith("."))
    # Aynı adlı .idml varsa .indd'yi atla (zaten dönüştürülmüş)
    idml_stems = {p.with_suffix("") for p in files if p.suffix.lower() == ".idml"}
    files = [p for p in files if p.suffix.lower() == ".idml" or p.with_suffix("") not in idml_stems]
    print(f"{len(files)} dosya yüklenecek")
    for p in files:
        try:
            r = client.upload("/api/documents", p)
            print(f"  ✓ {p.name}" + ("  (InDesign dönüşümü bekliyor)" if r.get("pending") else ""))
        except urllib.error.HTTPError as e:
            print(f"  ✗ {p.name}: {e.code} {e.read()[:200].decode(errors='replace')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="InDesign Bulut masaüstü ajanı")
    ap.add_argument("--server", default=os.environ.get("BULUT_SERVER", "http://localhost:8000"))
    ap.add_argument("--token", default=os.environ.get("BULUT_TOKEN"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="İşleri dinle ve InDesign ile işle")
    r.add_argument("--name", default=os.environ.get("BULUT_AGENT_NAME", f"{socket.gethostname()} ({platform.system()})"))
    r.add_argument("--hotfolder", default=os.environ.get("BULUT_HOTFOLDER", str(DEFAULT_HOT)))
    r.add_argument("--interval", type=float, default=5)
    u = sub.add_parser("upload", help="Bir klasördeki .idml/.indd dosyalarını toplu yükle")
    u.add_argument("folder")
    args = ap.parse_args()
    try:
        {"run": run, "upload": upload}[args.cmd](args)
    except KeyboardInterrupt:
        print("\nDurduruldu.")


if __name__ == "__main__":
    main()
