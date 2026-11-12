"""Outils communs aux tests : base SQLite temporaire et fausses réponses HTTP (aucun appel réseau réel)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille import base, reseau  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    """Base SQLite neuve, dans un dossier temporaire (la vraie base n'est jamais touchée)."""
    c = base.connecter(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    """Les tentatives avec backoff n'attendent pas réellement : on enregistre les pauses demandées."""
    pauses = []
    monkeypatch.setattr(reseau, "_dormir", pauses.append)
    return pauses


class FausseReponse:
    def __init__(self, statut=200, corps=None, entetes=None, texte=None):
        self.status_code = statut
        self.headers = entetes or {}
        self.text = texte if texte is not None else json.dumps(corps if corps is not None else {})

    def json(self):
        return json.loads(self.text)


class FausseSession:
    """Rejoue une suite de réponses (ou d'exceptions) et compte les appels."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    def request(self, methode, url, **kwargs):
        self.appels.append((methode, url, kwargs))
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def essai(nct="NCT00000001", **champs):
    """Essai normalisé minimal, au format de veille.sources.clinicaltrials.normaliser."""
    d = {"nct": nct, "titre": "Essai de test", "statut": "RECRUITING", "phases_declarees": ["PHASE2"],
         "date_fin_principale": "2027-01", "participants_nombre": 100, "resultats_deposes": False,
         "promoteur": "Labo Test", "date_derniere_mise_a_jour": "2026-11-01"}
    d.update(champs)
    return d
