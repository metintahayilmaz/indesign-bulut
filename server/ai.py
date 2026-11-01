"""Web panelinden gelen doğal dil talimatlarını Claude Code (headless) ile belge üzerinde çalıştırır.

Claude Code, belgenin açılmış IDML klasöründe çalışır ve yalnızca `idmlkit` CLI'ını
ve dosya okuma/düzenleme araçlarını kullanabilir. Bitince değişiklikler git'e işlenir.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROMPT = """Sen bir InDesign belge editörüsün. Çalışma klasöründeki `idml/` klasörü açılmış bir IDML belgesidir.

Kullanıcının talimatı:
---
{instruction}
---

Çalışma yöntemi:
1. `python3 -m idmlkit info idml` ve `python3 -m idmlkit text idml` ile belgeyi incele.
2. Küçük değişiklikler için: `python3 -m idmlkit set idml <paragraf-id> "<yeni metin>"`
   Toplu değişiklik/çeviri için: `python3 -m idmlkit export idml -o segments.json`, ardından
   segments.json içindeki yalnızca "text" alanlarını Edit/Write araçlarıyla düzenle (Python/shell
   script'i çalıştırma izni yoktur; büyük belgelerde dosyayı parça parça Edit ile düzenle), sonra
   `python3 -m idmlkit import idml segments.json` çalıştır ve segments.json'u sil.
   Basit bul-değiştir için: `python3 -m idmlkit replace idml "<ara>" "<yeni>"`
3. Kurallar: <rN>...</rN> etiketleri karakter stilleridir, korunmalıdır (içerikleri değişebilir).
   <xN/> yer tutucuları satır içi nesnelerdir (tablo, sayfa no, görsel): ASLA silme, sırasını değiştirme.
   idml/ altındaki XML dosyalarını doğrudan düzenleme; daima idmlkit kullan.
4. Sonunda Türkçe, kısa bir özet yaz: neyi değiştirdin, kaç paragraf etkilendi, varsa sorunlar.
"""

DESIGN_PROMPT = """Sen deneyimli bir dergi sayfa tasarımcısısın. Bu klasör bir tasarım belgesidir. Görevin, kullanıcının
yazı ve görsellerinden, şablonun stillerine, ana sayfalarına (vinyetlerine) ve kenar boşluklarına SADIK kalarak
dergi sayfaları kurmak. Sayfaları sen çizmezsin: `layout.json` yerleşim planını yazarsın, InDesign onu kurar.

Kullanıcının isteği:
---
{instruction}
---

Çalışma yöntemi:
1. `python3 -m tasarim kurallar` ile plan biçimini oku (bir kez).
2. `python3 -m tasarim profil` ile şablonu incele: sayfa ölçüsü, ızgara, ana sayfalar, vinyet çerçeve adları, stiller, renkler.
3. `python3 -m tasarim varliklar` ile yazıları/görselleri listele; yazıları `python3 -m tasarim metin <ad>` ile oku.
   Görsellerin içeriğini görmek için Read aracıyla varlık klasöründeki dosyalara bak (kompozisyon, yön, odak noktası).
4. Varsa mevcut `layout.json`'u oku: kullanıcı bir düzeltme istiyorsa planı baştan yazma, yalnızca isteneni değiştir.
5. `layout.json`'u Write/Edit ile yaz. Yalnızca profildeki stil, renk ve ana sayfa adlarını kullan; metni kısaltma
   veya değiştirme (kullanıcı istemedikçe) — başlık, spot, ara başlık ve görsel altı yazılarını yazıdan çıkar.
6. `python3 -m tasarim dogrula` — hataları düzelt, uyarıları değerlendir.
7. `python3 -m tasarim olustur` — InDesign sayfaları kurar ve rapor + önizleme PNG yolları döner.
   Önizlemelere Read ile bak. Taşan metin, boş kalan alan, kötü kırpılmış görsel, dengesiz yerleşim varsa planı
   düzeltip yeniden oluştur (en fazla 4 tur). Taşma varsa sayfa ekle veya görseli küçült; metni silme.
8. Sonunda Türkçe kısa özet: kaç sayfa, hangi ana sayfalar, yerleşim kararların, kalan uyarılar.
InDesign ajanı çevrimdışıysa (olustur hata verirse) planı doğrulanmış halde bırak ve bunu söyle.
"""

ALLOWED_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep",
                 "Bash(python3 -m idmlkit:*)", "Bash(rm segments.json)", "Bash(python3 -m tasarim:*)"]


def claude_available() -> bool:
    return shutil.which(os.environ.get("CLAUDE_BIN", "claude")) is not None


class TaskRunner:
    def __init__(self, storage, root: Path):
        self.storage = storage
        self.dir = Path(root) / "tasks"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._doc_locks: dict[str, threading.Lock] = {}

    def _save(self, task: dict) -> dict:
        (self.dir / f"{task['id']}.json").write_text(json.dumps(task, ensure_ascii=False, indent=2))
        return task

    def get(self, task_id: str) -> dict:
        p = self.dir / f"{task_id}.json"
        if not task_id.isalnum() or not p.exists():
            raise KeyError(task_id)
        return json.loads(p.read_text())

    def list(self, doc: str) -> list[dict]:
        tasks = [json.loads(p.read_text()) for p in self.dir.glob("*.json")]
        return sorted([t for t in tasks if t["doc"] == doc], key=lambda t: t["created"], reverse=True)

    def start(self, slug: str, instruction: str, author: str | None = None) -> dict:
        self.storage.doc_dir(slug)
        task = {"id": uuid.uuid4().hex, "doc": slug, "instruction": instruction, "author": author,
                "status": "running", "created": time.time(), "result": None, "commit": None, "error": None}
        self._save(task)
        threading.Thread(target=self._run, args=(task,), daemon=True).start()
        return task

    def _run(self, task: dict) -> None:
        lock = self._doc_locks.setdefault(task["doc"], threading.Lock())
        with lock:
            try:
                cwd = self.storage.doc_dir(task["doc"])
                env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "DATA_DIR": str(self.storage.root.resolve())}
                design = self.storage.meta(task["doc"]).get("kind") == "design"
                prompt = (DESIGN_PROMPT if design else PROMPT).format(instruction=task["instruction"])
                cmd = [os.environ.get("CLAUDE_BIN", "claude"), "-p", prompt,
                       "--output-format", "json", "--permission-mode", "acceptEdits",
                       "--allowedTools", *ALLOWED_TOOLS]
                if design:
                    files = self.storage.files_dir / task["doc"]
                    files.mkdir(parents=True, exist_ok=True)
                    cmd += ["--add-dir", str(files.resolve())]
                if os.environ.get("CLAUDE_MODEL"):
                    cmd += ["--model", os.environ["CLAUDE_MODEL"]]
                r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                                   timeout=int(os.environ.get("CLAUDE_TIMEOUT", "1800")), stdin=subprocess.DEVNULL)
                try:
                    out = json.loads(r.stdout)
                    task["result"] = out.get("result")
                    task["cost_usd"] = out.get("total_cost_usd")
                    is_error = out.get("is_error") or r.returncode != 0
                except json.JSONDecodeError:
                    task["result"] = r.stdout[-4000:]
                    is_error = r.returncode != 0
                if is_error:
                    task["error"] = (r.stderr or "")[-2000:] or "Claude Code hata ile bitti"
                (cwd / "segments.json").unlink(missing_ok=True)
                self.storage.touch(task["doc"])
                msg = f"Claude: {task['instruction'][:72]}"
                task["commit"] = self.storage.commit(msg, [self.storage.rel(task["doc"])], task.get("author") or "Claude")
                task["status"] = "error" if is_error else "done"
            except Exception as e:  # noqa: BLE001
                task["status"], task["error"] = "error", str(e)
            task["finished"] = time.time()
            self._save(task)
