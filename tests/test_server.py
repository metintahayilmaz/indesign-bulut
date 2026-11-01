import json
import os
import stat
import sys
import time

import pytest
from fastapi.testclient import TestClient

from tests.sample_idml import sample_bytes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_TOKEN", "gizli")
    from server.app import app
    for attr in ("storage", "jobs", "tasks", "agents"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer gizli", "X-User": "Ay%C5%9Fe"})
    return c


def upload(client, name="Bahar Kataloğu.idml"):
    r = client.post("/api/documents", files={"file": (name, sample_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["document"]["slug"]


def test_auth_required(client):
    assert client.get("/api/documents", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/documents?token=gizli", headers={"Authorization": ""}).status_code == 200


def test_upload_edit_history_restore(client):
    slug = upload(client)
    assert slug == "bahar-katalogu"
    paras = client.get(f"/api/documents/{slug}/paragraphs").json()["paragraphs"]
    first = paras[0]
    assert first["text"] == "Bahar Kataloğu"

    r = client.put(f"/api/documents/{slug}/paragraphs",
                   json={"changes": [{"id": first["id"], "text": "Yaz Kataloğu", "hash": first["hash"]}]})
    assert r.json()["ok"] and r.json()["rev"]

    # Bayat hash -> çakışma
    r = client.put(f"/api/documents/{slug}/paragraphs",
                   json={"changes": [{"id": first["id"], "text": "Kış", "hash": first["hash"]}]})
    assert r.status_code == 409

    # Yer tutucuyu silmek reddedilir
    footer = next(p for p in paras if "<x1/>" in p["text"] and p["text"].startswith("Sayfa"))
    r = client.put(f"/api/documents/{slug}/paragraphs",
                   json={"changes": [{"id": footer["id"], "text": "Sayfa", "hash": footer["hash"]}]})
    assert r.status_code == 409 and r.json()["errors"]

    hist = client.get(f"/api/documents/{slug}/history").json()["history"]
    assert len(hist) == 2 and hist[0]["author"] == "Ayşe"
    diff = client.get(f"/api/documents/{slug}/diff", params={"rev": hist[1]["rev"]}).json()["changes"]
    assert diff == [{"id": first["id"], "old": "Bahar Kataloğu", "new": "Yaz Kataloğu"}]

    old = client.get(f"/api/documents/{slug}/download.idml", params={"rev": hist[1]["rev"]})
    assert old.status_code == 200 and old.content[:2] == b"PK"

    assert client.post(f"/api/documents/{slug}/restore", json={"rev": hist[1]["rev"]}).json()["rev"]
    paras = client.get(f"/api/documents/{slug}/paragraphs").json()["paragraphs"]
    assert paras[0]["text"] == "Bahar Kataloğu"


def test_pdf_job_with_fake_agent(client):
    slug = upload(client)
    job = client.post(f"/api/documents/{slug}/pdf", json={"preset": "[Press Quality]"}).json()["job"]
    claimed = client.post("/api/agent/claim", json={"agent": "test-mac"}).json()["job"]
    assert claimed["id"] == job["id"] and claimed["status"] == "running"
    assert client.post("/api/agent/claim", json={"agent": "test-mac"}).status_code == 204

    idml = client.get(f"/api/agent/jobs/{job['id']}/input")
    assert idml.content[:2] == b"PK"
    r = client.post(f"/api/agent/jobs/{job['id']}/complete", files={"file": ("x.pdf", b"%PDF-1.7 sahte")})
    assert r.json()["job"]["status"] == "done"
    files = client.get(f"/api/documents/{slug}").json()["files"]
    assert {"latest.pdf"} <= {f["name"] for f in files}
    assert client.get(f"/api/documents/{slug}/files/latest.pdf").content.startswith(b"%PDF")
    status = client.get("/api/status").json()
    assert status["agents"][0]["name"] == "test-mac" and status["agents"][0]["online"]


def test_indd_conversion_flow(client):
    r = client.post("/api/documents", files={"file": ("Dergi Sayı 5.indd", b"sahte indd")}).json()
    job = r["pending"]
    assert client.get("/api/documents").json()["pending"][0]["id"] == job["id"]
    client.post("/api/agent/claim", json={"agent": "pc"})
    assert client.get(f"/api/agent/jobs/{job['id']}/input").content == b"sahte indd"
    r = client.post(f"/api/agent/jobs/{job['id']}/complete", files={"file": ("x.idml", sample_bytes())}).json()
    assert r["job"]["status"] == "done"
    docs = client.get("/api/documents").json()
    assert docs["documents"][0]["slug"] == "dergi-sayi-5" and not docs["pending"]


def test_ai_task_with_fake_claude(client, tmp_path, monkeypatch):
    """Sahte `claude`: idmlkit ile bir paragrafı değiştirir ve JSON sonucu basar."""
    fake = tmp_path / "claude"
    fake.write_text(f"""#!{sys.executable}
import json, subprocess, sys
subprocess.run([sys.executable, "-m", "idmlkit", "replace", "idml", "Bahar", "Spring"], check=True, capture_output=True)
print(json.dumps({{"result": "1 paragraf çevrildi", "is_error": False, "total_cost_usd": 0.01}}))
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_BIN", str(fake))
    slug = upload(client)
    task = client.post(f"/api/documents/{slug}/ai", json={"instruction": "Başlığı İngilizceye çevir"}).json()["task"]
    for _ in range(100):
        t = client.get(f"/api/documents/{slug}/ai").json()["tasks"][0]
        if t["status"] != "running":
            break
        time.sleep(0.1)
    assert t["status"] == "done", t
    assert t["commit"] and t["result"] == "1 paragraf çevrildi"
    assert client.get(f"/api/documents/{slug}/paragraphs").json()["paragraphs"][0]["text"] == "Spring Kataloğu"
    assert client.get(f"/api/documents/{slug}/history").json()["history"][0]["message"].startswith("Claude:")


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "InDesign" in r.text
