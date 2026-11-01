"""Masaüstü InDesign ajanı için basit dosya tabanlı iş kuyruğu.

İş türleri:
  pdf          : belgenin güncel IDML'ini InDesign'da açıp PDF dışa aktar
  indd_to_idml : yüklenen .indd dosyasını InDesign'da açıp IDML olarak kaydet
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

_lock = threading.Lock()
STALE_SECONDS = 15 * 60   # bu süre içinde bitmeyen iş yeniden kuyruğa alınır


class JobQueue:
    def __init__(self, root: Path):
        self.dir = Path(root) / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        if not all(c in "0123456789abcdef" for c in job_id):
            raise KeyError(job_id)
        return self.dir / f"{job_id}.json"

    def _save(self, job: dict) -> dict:
        job["updated"] = time.time()
        self._path(job["id"]).write_text(json.dumps(job, ensure_ascii=False, indent=2))
        return job

    def create(self, kind: str, doc: str, **params) -> dict:
        job = {"id": uuid.uuid4().hex, "kind": kind, "doc": doc, "status": "queued",
               "created": time.time(), "params": params, "result": None, "error": None}
        return self._save(job)

    def get(self, job_id: str) -> dict:
        p = self._path(job_id)
        if not p.exists():
            raise KeyError(job_id)
        return json.loads(p.read_text())

    def list(self, doc: str | None = None) -> list[dict]:
        jobs = [json.loads(p.read_text()) for p in self.dir.glob("*.json")]
        if doc:
            jobs = [j for j in jobs if j["doc"] == doc]
        return sorted(jobs, key=lambda j: j["created"], reverse=True)

    def claim(self, agent: str) -> dict | None:
        with _lock:
            now = time.time()
            for job in sorted(self.list(), key=lambda j: j["created"]):
                stale = job["status"] == "running" and now - job.get("updated", 0) > STALE_SECONDS
                if job["status"] == "queued" or stale:
                    job.update(status="running", agent=agent, started=now)
                    return self._save(job)
        return None

    def finish(self, job_id: str, result: dict | None = None, error: str | None = None) -> dict:
        with _lock:
            job = self.get(job_id)
            job.update(status="error" if error else "done", result=result, error=error, finished=time.time())
            return self._save(job)
