#!/bin/bash
# InDesign Bulut — macOS başlatıcı. Finder'da çift tıklayın.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import sys; sys.exit(sys.version_info < (3,9))" 2>/dev/null; then
  echo "Python 3.9+ gerekli. https://www.python.org/downloads/ adresinden kurup tekrar deneyin."
  read -n 1 -s -r -p "Kapatmak için bir tuşa basın…"; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "İlk kurulum yapılıyor (bir kez, ~1 dk)…"
  python3 -m venv .venv || { read -n 1 -s -r -p "Sanal ortam oluşturulamadı. Bir tuşa basın…"; exit 1; }
fi
if ! .venv/bin/python -c "import fastapi, uvicorn, lxml, multipart" 2>/dev/null; then
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt || { read -n 1 -s -r -p "Paketler kurulamadı. Bir tuşa basın…"; exit 1; }
fi
exec .venv/bin/python yerel.py "$@"
