"""InDesign Bulut — web paneli ve API.

Çalıştırma:  DATA_DIR=./data APP_TOKEN=gizli uvicorn server.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from urllib.parse import unquote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import TaskRunner, claude_available
from .jobs import JobQueue
from .storage import Storage, slugify

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024

app = FastAPI(title="InDesign Bulut")


def get_state(request: Request):
    st = request.app.state
    if not hasattr(st, "storage"):
        data = Path(os.environ.get("DATA_DIR", str(DATA_DIR)))
        st.storage = Storage(data)
        st.jobs = JobQueue(data)
        st.tasks = TaskRunner(st.storage, data)
        st.agents = {}
    return st


def auth(request: Request, authorization: str | None = Header(None), token: str | None = Query(None)):
    expected = os.environ.get("APP_TOKEN")
    if expected:
        given = (authorization or "").removeprefix("Bearer ").strip() or token or ""
        if not secrets.compare_digest(given, expected):
            raise HTTPException(401, "Geçersiz veya eksik erişim anahtarı")
    user = request.headers.get("x-user")
    return unquote(user)[:80] if user else None


def nf(fn, *a, **k):
    try:
        return fn(*a, **k)
    except KeyError as e:
        raise HTTPException(404, f"Bulunamadı: {e}")


# --- genel -----------------------------------------------------------------
@app.get("/api/status")
def status(request: Request, user=Depends(auth)):
    st = get_state(request)
    now = time.time()
    agents = [{"name": n, "last_seen": t, "online": now - t < 120} for n, t in st.agents.items()]
    return {"claude": claude_available(), "agents": agents}


@app.get("/api/documents")
def list_documents(request: Request, user=Depends(auth)):
    st = get_state(request)
    pending = [j for j in st.jobs.list() if j["kind"] == "indd_to_idml" and j["status"] in ("queued", "running", "error")]
    return {"documents": st.storage.list_documents(), "pending": pending}


@app.post("/api/documents")
async def upload(request: Request, file: UploadFile = File(...), slug: str | None = Form(None), user=Depends(auth)):
    st = get_state(request)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Dosya çok büyük")
    name = file.filename or "belge.idml"
    ext = Path(name).suffix.lower()
    if slug:
        nf(st.storage.doc_dir, slug)
    if ext == ".idml":
        try:
            meta = st.storage.add_document(name, data, author=user, slug=slug)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"IDML okunamadı: {e}")
        return {"document": meta}
    if ext == ".indd":
        target = slug or slugify(name)
        if not slug:
            base, i = target, 2
            while (st.storage.repo / "documents" / target).exists():
                target, i = f"{base}-{i}", i + 1
        st.storage.file_path(target, "original.indd").write_bytes(data)
        job = st.jobs.create("indd_to_idml", target, filename=name, author=user)
        return {"pending": job}
    raise HTTPException(400, "Yalnızca .idml veya .indd dosyaları yüklenebilir")


@app.get("/api/documents/{slug}")
def get_document(slug: str, request: Request, user=Depends(auth)):
    st = get_state(request)
    meta = nf(st.storage.meta, slug)
    return {"document": meta, "files": st.storage.list_files(slug), "jobs": st.jobs.list(slug)}


@app.delete("/api/documents/{slug}")
def delete_document(slug: str, request: Request, user=Depends(auth)):
    nf(get_state(request).storage.delete_document, slug, author=user)
    return {"ok": True}


@app.get("/api/documents/{slug}/paragraphs")
def paragraphs(slug: str, request: Request, user=Depends(auth)):
    doc = nf(get_state(request).storage.open_doc, slug)
    return {"paragraphs": [{"id": p.id, "story": p.story, "style": p.style, "text": p.markup(),
                            "hash": p.source_hash(), "objects": p.objects()} for p in doc.paragraphs()]}


class Change(BaseModel):
    id: str
    text: str
    hash: str | None = None


class SaveBody(BaseModel):
    changes: list[Change]
    message: str | None = None


@app.put("/api/documents/{slug}/paragraphs")
def save_paragraphs(slug: str, body: SaveBody, request: Request, user=Depends(auth)):
    st = get_state(request)
    doc = nf(st.storage.open_doc, slug)
    report = doc.import_segments({"paragraphs": [
        {"id": c.id, "text": c.text, "hash": c.hash, "source": None} for c in body.changes]})
    if report["errors"] or report["conflicts"]:
        return JSONResponse({"ok": False, **report}, status_code=409)
    rev = None
    if report["changed"]:
        msg = body.message or f"{len(report['changed'])} paragraf düzenlendi"
        rev = st.storage.save_doc(slug, doc, msg, author=user)
    return {"ok": True, "changed": report["changed"], "rev": rev}


@app.get("/api/documents/{slug}/download.idml")
def download_idml(slug: str, request: Request, rev: str | None = None, user=Depends(auth)):
    st = get_state(request)
    doc = nf(st.storage.doc_at, slug, rev) if rev else nf(st.storage.open_doc, slug)
    fname = f"{slug}{'-' + rev[:8] if rev else ''}.idml"
    return Response(doc.to_bytes(), media_type="application/vnd.adobe.indesign-idml-package",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/documents/{slug}/history")
def history(slug: str, request: Request, user=Depends(auth)):
    return {"history": nf(get_state(request).storage.history, slug)}


@app.get("/api/documents/{slug}/diff")
def diff(slug: str, rev: str, request: Request, against: str | None = None, user=Depends(auth)):
    return {"changes": nf(get_state(request).storage.diff, slug, rev, against)}


class RevBody(BaseModel):
    rev: str


@app.post("/api/documents/{slug}/restore")
def restore(slug: str, body: RevBody, request: Request, user=Depends(auth)):
    st = get_state(request)
    nf(st.storage.doc_at, slug, body.rev)  # doğrulama
    return {"rev": st.storage.restore(slug, body.rev, author=user)}


class PdfBody(BaseModel):
    preset: str | None = None


@app.post("/api/documents/{slug}/pdf")
def request_pdf(slug: str, request: Request, body: PdfBody | None = None, user=Depends(auth)):
    st = get_state(request)
    nf(st.storage.doc_dir, slug)
    rev = st.storage.git("rev-parse", "HEAD").strip()
    job = st.jobs.create("pdf", slug, rev=rev, preset=(body.preset if body else None) or "[High Quality Print]", author=user)
    return {"job": job}


@app.get("/api/documents/{slug}/files/{name}")
def get_file(slug: str, name: str, request: Request, user=Depends(auth)):
    p = nf(get_state(request).storage.file_path, slug, name)
    if not p.exists():
        raise HTTPException(404, "Dosya yok")
    return FileResponse(p, filename=name)


# --- Claude Code görevleri ------------------------------------------------
class AiBody(BaseModel):
    instruction: str


@app.post("/api/documents/{slug}/ai")
def ai_start(slug: str, body: AiBody, request: Request, user=Depends(auth)):
    if not claude_available():
        raise HTTPException(503, "Sunucuda Claude Code (claude) kurulu değil")
    if not body.instruction.strip():
        raise HTTPException(400, "Talimat boş")
    return {"task": nf(get_state(request).tasks.start, slug, body.instruction.strip(), author=user)}


@app.get("/api/documents/{slug}/ai")
def ai_list(slug: str, request: Request, user=Depends(auth)):
    return {"tasks": get_state(request).tasks.list(slug)}


# --- masaüstü ajan API'si -------------------------------------------------
class ClaimBody(BaseModel):
    agent: str = "ajan"


@app.post("/api/agent/claim")
def agent_claim(body: ClaimBody, request: Request, user=Depends(auth)):
    st = get_state(request)
    st.agents[body.agent] = time.time()
    job = st.jobs.claim(body.agent)
    if job is None:
        return Response(status_code=204)
    return {"job": job}


@app.get("/api/agent/jobs/{job_id}/input")
def agent_input(job_id: str, request: Request, user=Depends(auth)):
    st = get_state(request)
    job = nf(st.jobs.get, job_id)
    if job["kind"] == "pdf":
        doc = nf(st.storage.doc_at, job["doc"], job["params"]["rev"])
        return Response(doc.to_bytes(), media_type="application/vnd.adobe.indesign-idml-package",
                        headers={"Content-Disposition": f'attachment; filename="{job["doc"]}.idml"'})
    if job["kind"] == "indd_to_idml":
        return FileResponse(st.storage.file_path(job["doc"], "original.indd"), filename=f'{job["doc"]}.indd')
    raise HTTPException(400, "Bilinmeyen iş türü")


@app.post("/api/agent/jobs/{job_id}/complete")
async def agent_complete(job_id: str, request: Request, file: UploadFile = File(...), user=Depends(auth)):
    st = get_state(request)
    job = nf(st.jobs.get, job_id)
    data = await file.read()
    if job["kind"] == "pdf":
        name = f'{job["doc"]}-{job["params"]["rev"][:8]}.pdf'
        st.storage.file_path(job["doc"], name).write_bytes(data)
        st.storage.file_path(job["doc"], "latest.pdf").write_bytes(data)
        return {"job": st.jobs.finish(job_id, result={"file": name})}
    if job["kind"] == "indd_to_idml":
        exists = (st.storage.repo / "documents" / job["doc"] / "meta.json").exists()
        try:
            meta = st.storage.add_document(job["params"]["filename"].rsplit(".", 1)[0] + ".idml", data,
                                           author=job["params"].get("author"), slug=job["doc"])
        except Exception as e:  # noqa: BLE001
            return {"job": st.jobs.finish(job_id, error=f"Ajanın gönderdiği IDML okunamadı: {e}")}
        return {"job": st.jobs.finish(job_id, result={"document": meta["slug"], "new": not exists})}
    raise HTTPException(400, "Bilinmeyen iş türü")


class FailBody(BaseModel):
    error: str


@app.post("/api/agent/jobs/{job_id}/fail")
def agent_fail(job_id: str, body: FailBody, request: Request, user=Depends(auth)):
    st = get_state(request)
    nf(st.jobs.get, job_id)
    return {"job": st.jobs.finish(job_id, error=body.error[:2000])}


# --- arayüz -----------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
