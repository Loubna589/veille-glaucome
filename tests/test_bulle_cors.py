"""Bulle d'assistant : l'API locale n'accepte les appels que depuis le site local (CORS limité)."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

flask = pytest.importorskip("flask")
import assistant as module_assistant  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]


class FauxAssistant:
    jeton = None
    index = SimpleNamespace(ids=["a", "b"])

    def repondre(self, question):
        return {"question": question, "statut": "sans_jeton", "reponse": None,
                "sources": [{"citation": "PMID:1", "id": "PMID:1", "titre": "t", "score": 0.9}]}


@pytest.fixture
def client():
    return module_assistant.application(FauxAssistant()).test_client()


def test_origine_locale_autorisee(client):
    r = client.get("/api/etat", headers={"Origin": "http://127.0.0.1:8766"})
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:8766"


def test_preverification_options(client):
    r = client.open("/api/question", method="OPTIONS", headers={
        "Origin": "http://localhost:8766", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:8766"
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in r.headers["Access-Control-Allow-Headers"]


def test_autre_origine_refusee(client):
    r = client.post("/api/question", json={"question": "netarsudil ?"}, headers={"Origin": "https://exemple.com"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_reponse_sans_jeton_renvoie_les_sources(client):
    r = client.post("/api/question", json={"question": "netarsudil ?"}, headers={"Origin": "http://127.0.0.1:8766"})
    d = r.get_json()
    assert d["statut"] == "sans_jeton" and d["sources"][0]["citation"] == "PMID:1"


def test_bulle_reconnait_les_memes_citations_que_le_rag():
    """La bulle transforme en liens exactement les citations que veille/rag.py valide."""
    from veille.rag import MOTIF_CITATION
    js = (RACINE / "site" / "js" / "bulle.js").read_text(encoding="utf-8")
    motif_js = re.search(r"replace\(/(.+?)/g", js).group(1)
    assert motif_js == getattr(MOTIF_CITATION, "pattern", MOTIF_CITATION)
    assert "8770" in js and "Mode sources seulement" in js
