"""Git destekli belge deposu.

DATA_DIR/
  repo/                       git deposu (sürüm geçmişi)
    documents/<slug>/meta.json
    documents/<slug>/idml/... açılmış IDML (XML'ler — satır bazlı diff alınabilir)
  files/<slug>/               git dışı ikili dosyalar (orijinal .indd, PDF çıktıları)
  jobs/<id>.json              masaüstü ajan işleri
  tasks/<id>.json             Claude Code görevleri
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

from idmlkit import IdmlDocument
from idmlkit import package

_lock = threading.RLock()


def slugify(name: str) -> str:
    name = Path(name).stem
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    name = unicodedata.normalize("NFKD", name.translate(tr)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "belge"


class Storage:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir)
        self.repo = self.root / "repo"
        self.files_dir = self.root / "files"
        for d in (self.repo / "documents", self.files_dir, self.root / "jobs", self.root / "tasks"):
            d.mkdir(parents=True, exist_ok=True)
        if not (self.repo / ".git").exists():
            self.git("init", "-q", "-b", "main")
            self.git("config", "user.name", "InDesign Bulut")
            self.git("config", "user.email", "bot@indesign-bulut.local")
            (self.repo / "README.md").write_text("InDesign Bulut belge deposu\n")
            self.commit("Depo oluşturuldu", ["README.md"])

    # --- git ------------------------------------------------------------
    def git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout

    def commit(self, message: str, paths: list[str], author: str | None = None) -> str | None:
        with _lock:
            self.git("add", "-A", "--", *paths)
            if not self.git("status", "--porcelain", "--", *paths).strip():
                return None
            args = ["commit", "-q", "-m", message]
            if author:
                args += ["--author", f"{author} <{slugify(author)}@indesign-bulut.local>"]
            self.git(*args)
            return self.git("rev-parse", "HEAD").strip()

    # --- belgeler -------------------------------------------------------
    def doc_dir(self, slug: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise KeyError(slug)
        d = self.repo / "documents" / slug
        if not (d / "meta.json").exists():
            raise KeyError(slug)
        return d

    def idml_dir(self, slug: str) -> Path:
        return self.doc_dir(slug) / "idml"

    def rel(self, slug: str) -> str:
        return f"documents/{slug}"

    def list_documents(self) -> list[dict]:
        docs = []
        for meta in sorted((self.repo / "documents").glob("*/meta.json")):
            docs.append(json.loads(meta.read_text()))
        return sorted(docs, key=lambda m: m.get("updated", 0), reverse=True)

    def meta(self, slug: str) -> dict:
        return json.loads((self.doc_dir(slug) / "meta.json").read_text())

    def _write_meta(self, slug: str, meta: dict) -> None:
        (self.repo / "documents" / slug / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def add_document(self, filename: str, idml_bytes: bytes, author: str | None = None, slug: str | None = None) -> dict:
        files = package.read_bytes(idml_bytes)  # doğrulama
        with _lock:
            if slug is None:
                base = slugify(filename)
                slug, i = base, 2
                while (self.repo / "documents" / slug).exists():
                    slug, i = f"{base}-{i}", i + 1
            d = self.repo / "documents" / slug
            new = not (d / "meta.json").exists()
            if (d / "idml").exists():
                shutil.rmtree(d / "idml")
            package.write_package(files, d / "idml")
            info = IdmlDocument(files).info()
            now = time.time()
            meta = self.meta(slug) if not new else {"slug": slug, "name": Path(filename).stem, "created": now}
            meta.update({"filename": filename, "updated": now, "info": info})
            self._write_meta(slug, meta)
            self.commit(f"{'Yüklendi' if new else 'Yeni sürüm yüklendi'}: {filename}", [self.rel(slug)], author)
            return meta

    def touch(self, slug: str) -> None:
        meta = self.meta(slug)
        meta["updated"] = time.time()
        meta["info"] = IdmlDocument.open(self.idml_dir(slug)).info()
        self._write_meta(slug, meta)

    def delete_document(self, slug: str, author: str | None = None) -> None:
        with _lock:
            d = self.doc_dir(slug)
            shutil.rmtree(d)
            self.commit(f"Silindi: {slug}", [self.rel(slug)], author)
            shutil.rmtree(self.files_dir / slug, ignore_errors=True)

    def open_doc(self, slug: str) -> IdmlDocument:
        return IdmlDocument.open(self.idml_dir(slug))

    def save_doc(self, slug: str, doc: IdmlDocument, message: str, author: str | None = None) -> str | None:
        with _lock:
            doc.save(self.idml_dir(slug))
            self.touch(slug)
            return self.commit(message, [self.rel(slug)], author)

    # --- geçmiş ---------------------------------------------------------
    def history(self, slug: str, limit: int = 100) -> list[dict]:
        self.doc_dir(slug)
        out = self.git("log", f"-{limit}", "--format=%H%x1f%an%x1f%at%x1f%s", "--", self.rel(slug))
        items = []
        for line in out.splitlines():
            h, an, at, s = line.split("\x1f")
            items.append({"rev": h, "author": an, "time": int(at), "message": s})
        return items

    def doc_at(self, slug: str, rev: str) -> IdmlDocument:
        if not re.fullmatch(r"[0-9a-f]{7,40}", rev):
            raise KeyError(rev)
        prefix = f"{self.rel(slug)}/idml/"
        names = self.git("ls-tree", "-r", "--name-only", rev, "--", prefix).splitlines()
        if not names:
            raise KeyError(rev)
        files = {}
        for n in names:
            r = subprocess.run(["git", "show", f"{rev}:{n}"], cwd=self.repo, capture_output=True, check=True)
            files[n[len(prefix):]] = r.stdout
        return IdmlDocument(files)

    def diff(self, slug: str, rev: str, against: str | None = None) -> list[dict]:
        """Paragraf düzeyinde fark: `rev` sürümü ile `against` (varsayılan: güncel) arasında."""
        old = {p.id: p.markup() for p in self.doc_at(slug, rev).paragraphs()}
        cur_doc = self.doc_at(slug, against) if against else self.open_doc(slug)
        new = {p.id: p.markup() for p in cur_doc.paragraphs()}
        changes = []
        for pid in list(dict.fromkeys([*old, *new])):
            if old.get(pid) != new.get(pid):
                changes.append({"id": pid, "old": old.get(pid), "new": new.get(pid)})
        return changes

    def restore(self, slug: str, rev: str, author: str | None = None) -> str | None:
        with _lock:
            self.doc_dir(slug)
            path = f"{self.rel(slug)}/idml"
            self.git("rm", "-r", "-q", "--", path)
            self.git("checkout", rev, "--", path)
            self.touch(slug)
            return self.commit(f"{rev[:8]} sürümüne geri dönüldü", [self.rel(slug)], author)

    # --- git dışı dosyalar ---------------------------------------------
    SUBDIRS = ("cikti", "varliklar")

    def file_path(self, slug: str, name: str) -> Path:
        """Git dışı dosya yolu. `name` düz bir ad ya da `cikti/ad`, `varliklar/ad` olabilir."""
        parts = name.split("/")
        if len(parts) > 2 or (len(parts) == 2 and parts[0] not in self.SUBDIRS) \
                or any(not p or p.startswith(".") or "\\" in p for p in parts) or not re.fullmatch(r"[a-z0-9-]+", slug):
            raise KeyError(name)
        d = self.files_dir / slug / (parts[0] if len(parts) == 2 else "")
        d.mkdir(parents=True, exist_ok=True)
        return d / parts[-1]

    def list_files(self, slug: str, sub: str | None = None) -> list[dict]:
        d = self.files_dir / slug / (sub or "")
        if not d.exists():
            return []
        return [{"name": f.name, "size": f.stat().st_size, "time": f.stat().st_mtime}
                for f in sorted(d.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True) if f.is_file()]

    # --- tasarımlar -----------------------------------------------------
    def create_design(self, name: str, template: str, author: str | None = None) -> dict:
        """Şablonun kopyası olarak yeni bir tasarım belgesi oluşturur."""
        with _lock:
            tmeta = self.meta(template)
            base = slugify(name)
            slug, i = base, 2
            while (self.repo / "documents" / slug).exists():
                slug, i = f"{base}-{i}", i + 1
            d = self.repo / "documents" / slug
            shutil.copytree(self.idml_dir(template), d / "idml")
            now = time.time()
            meta = {"slug": slug, "name": name.strip() or slug, "kind": "design", "template": template,
                    "template_name": tmeta.get("name"), "filename": f"{slug}.idml", "created": now, "updated": now,
                    "info": IdmlDocument.open(d / "idml").info()}
            self._write_meta(slug, meta)
            self.commit(f"Tasarım oluşturuldu: {meta['name']} (şablon: {tmeta.get('name')})", [self.rel(slug)], author)
            return meta
