"""Şablona sadık dergi sayfası tasarımı: profil, varlıklar, yerleşim planı doğrulama ve InDesign'da oluşturma."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from idmlkit import IdmlDocument
from idmlkit.profile import build_profile

from .assets import list_assets
from .spec import validate

SPEC_DOC = Path(__file__).with_name("SPEC.md")


@dataclass
class DesignContext:
    data_dir: Path
    slug: str

    @property
    def repo(self) -> Path:
        return self.data_dir / "repo"

    @property
    def doc_dir(self) -> Path:
        return self.repo / "documents" / self.slug

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files" / self.slug

    @property
    def assets_dir(self) -> Path:
        return self.files_dir / "varliklar"

    @property
    def output_dir(self) -> Path:
        return self.files_dir / "cikti"

    @property
    def layout_path(self) -> Path:
        return self.doc_dir / "layout.json"

    def meta(self) -> dict:
        return json.loads((self.doc_dir / "meta.json").read_text())

    def template_slug(self) -> str:
        return self.meta().get("template") or self.slug

    def profile(self) -> dict:
        tdir = self.repo / "documents" / self.template_slug() / "idml"
        return build_profile(IdmlDocument.open(tdir))

    def assets(self) -> dict:
        return list_assets(self.assets_dir)

    def load_spec(self) -> dict:
        return json.loads(self.layout_path.read_text(encoding="utf-8"))

    def validate(self, spec: dict | None = None) -> dict:
        return validate(spec if spec is not None else self.load_spec(), self.profile(), self.assets())


def context_from_env(slug: str | None = None) -> DesignContext:
    data = os.environ.get("DATA_DIR")
    cwd = Path.cwd().resolve()
    if slug is None and cwd.parent.name == "documents" and (cwd / "meta.json").exists():
        slug = cwd.name
        if data is None:
            data = str(cwd.parent.parent.parent)
    if not data or not slug:
        raise SystemExit("Belge bulunamadı: belge klasöründe çalıştırın ya da --doc <belge> ve DATA_DIR verin.")
    return DesignContext(Path(data).resolve(), slug)
