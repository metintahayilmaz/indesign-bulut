#!/usr/bin/env python3
"""InDesign Bulut — kendi bilgisayarınızda tek komutla çalıştırma.

Web panelini ve InDesign ajanını birlikte başlatır, tarayıcıyı açar.
Gerekirse InDesign başlangıç script'ini otomatik kurar.

  python3 yerel.py              # başlat (yalnızca bu bilgisayardan erişilir)
  python3 yerel.py --paylas     # ağdaki diğer cihazlardan / Tailscale ile erişime aç (erişim anahtarı üretir)
  python3 yerel.py kur          # yalnızca InDesign script'ini kur

Veriler: Belgeler/InDesignBulut/veri  (git deposu, PDF'ler)
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME_DIR = Path.home() / "Documents" / "InDesignBulut"
JSX = ROOT / "agent" / "indesign" / "InDesignBulut_startup.jsx"
EXTRA_JSX = ROOT / "agent" / "indesign" / "Toplu_INDD_to_IDML.jsx"
sys.path.insert(0, str(ROOT))


def indesign_script_dirs() -> list[Path]:
    """Kurulu InDesign sürümlerinin kullanıcı Scripts klasörleri."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Adobe"
    else:
        return []
    found = []
    for app_dir in base.glob("Adobe InDesign" if sys.platform == "darwin" else "InDesign"):
        for scripts in app_dir.glob("Version */*/Scripts"):
            found.append(scripts)
    return sorted(found)


def install_scripts(verbose: bool = True) -> int:
    dirs = indesign_script_dirs()
    if not dirs:
        if verbose:
            print("! InDesign ayar klasörü bulunamadı. InDesign'ı en az bir kez açıp kapatın ya da\n"
                  f"  {JSX.name} dosyasını elle 'Startup Scripts' klasörüne kopyalayın (README).")
        return 0
    changed = 0
    for scripts in dirs:
        startup = scripts / "Startup Scripts"
        panel = scripts / "Scripts Panel"
        startup.mkdir(exist_ok=True)
        panel.mkdir(exist_ok=True)
        target = startup / JSX.name
        if not target.exists() or target.read_bytes() != JSX.read_bytes():
            shutil.copy2(JSX, target)
            changed += 1
            if verbose:
                print(f"✓ InDesign script'i kuruldu: {target}")
        shutil.copy2(EXTRA_JSX, panel / EXTRA_JSX.name)
    if changed and verbose:
        print("  → InDesign açıksa kapatıp yeniden açın (script açılışta yüklenir).")
    return changed


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("Boş port bulunamadı")


def start(args) -> None:
    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
        import lxml  # noqa: F401
    except ImportError as e:
        raise SystemExit(f"Eksik paket: {e.name}. Önce şunu çalıştırın:  {sys.executable} -m pip install -r requirements.txt")
    import uvicorn

    install_scripts()
    data = HOME_DIR / "veri"
    os.environ.setdefault("DATA_DIR", str(data))
    token = None
    if args.paylas:
        token_file = HOME_DIR / "erisim-anahtari.txt"
        if token_file.exists():
            token = token_file.read_text().strip()
        else:
            token = secrets.token_urlsafe(18)
            HOME_DIR.mkdir(parents=True, exist_ok=True)
            token_file.write_text(token)
        os.environ["APP_TOKEN"] = token
    else:
        os.environ.pop("APP_TOKEN", None)

    port = free_port(args.port)
    host = "0.0.0.0" if args.paylas else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"

    from server.app import app
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)

    import shutil as _sh
    print("\n══════════════════════════════════════════════")
    print(f"  InDesign Bulut çalışıyor:  {url}")
    if args.paylas:
        print(f"  Ağdan erişim:              http://{lan_ip()}:{port}")
        print(f"  Erişim anahtarı:           {token}")
        print("  (Panelde ⚙ simgesine tıklayıp bu anahtarı girin.)")
    print(f"  Veriler:                   {data}")
    print(f"  Claude Code:               {'hazır' if _sh.which('claude') else 'kurulu değil — Claude sekmesi kapalı (README)'}")
    print("  Durdurmak için bu pencereyi kapatın veya Ctrl+C")
    print("══════════════════════════════════════════════\n")
    if not args.no_browser:
        webbrowser.open(url)

    from agent import agent as ajan
    ns = argparse.Namespace(server=url, token=token, name=f"{socket.gethostname()} (yerel)",
                            hotfolder=str(HOME_DIR), interval=3)
    try:
        ajan.run(ns)
    except KeyboardInterrupt:
        print("\nKapatılıyor…")
        server.should_exit = True


def main() -> None:
    ap = argparse.ArgumentParser(description="InDesign Bulut'u bu bilgisayarda çalıştır")
    ap.add_argument("komut", nargs="?", choices=["baslat", "kur"], default="baslat")
    ap.add_argument("--paylas", action="store_true", help="Ağdaki diğer cihazlardan erişime aç (anahtar ile)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    args = ap.parse_args()
    if args.komut == "kur":
        install_scripts()
    else:
        start(args)


if __name__ == "__main__":
    main()
