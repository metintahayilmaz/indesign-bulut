"""IDML paketini (ZIP) okuma/yazma. Hem .idml dosyası hem de açılmış klasör desteklenir."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

MIMETYPE = b"application/vnd.adobe.indesign-idml-package"


def read_package(path: str | os.PathLike) -> dict[str, bytes]:
    """`.idml` dosyasını veya açılmış IDML klasörünü {iç_yol: bayt} sözlüğüne okur."""
    p = Path(path)
    if p.is_dir():
        files = {}
        for f in sorted(p.rglob("*")):
            if f.is_file():
                files[f.relative_to(p).as_posix()] = f.read_bytes()
        if "designmap.xml" not in files:
            raise ValueError(f"{p} geçerli bir IDML klasörü değil (designmap.xml yok)")
        return files
    return read_bytes(p.read_bytes())


def read_bytes(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    if "designmap.xml" not in files:
        raise ValueError("Geçerli bir IDML paketi değil (designmap.xml yok)")
    return files


def to_bytes(files: dict[str, bytes]) -> bytes:
    """IDML ZIP'i üretir. `mimetype` ilk girdi ve sıkıştırmasız olmalıdır."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), files.get("mimetype", MIMETYPE), compress_type=zipfile.ZIP_STORED)
        for name in sorted(files):
            if name == "mimetype":
                continue
            z.writestr(name, files[name], compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def write_package(files: dict[str, bytes], path: str | os.PathLike, only: set[str] | None = None) -> None:
    """Paketi yazar. Hedef bir klasörse (veya uzantısız ise) açılmış olarak yazar.

    `only` verilirse klasör modunda yalnızca bu dosyalar yeniden yazılır (git diff'leri küçük kalır).
    """
    p = Path(path)
    if p.is_dir() or (not p.exists() and p.suffix.lower() != ".idml"):
        p.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            if only is not None and name not in only:
                continue
            target = p / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return
    p.write_bytes(to_bytes(files))
