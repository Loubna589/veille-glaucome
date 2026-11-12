"""Robustesse des appels API : 429 + Retry-After, erreurs passagères, réponses invalides (tout est simulé)."""
import pytest
import requests

from conftest import FausseReponse, FausseSession
from veille import reseau


def test_429_puis_succes_respecte_retry_after(sans_attente):
    session = FausseSession(FausseReponse(429, entetes={"Retry-After": "3"}), FausseReponse(200, {"ok": True}))
    reponse = reseau.requete("GET", "https://exemple.test", "Test", session=session)
    assert reponse.status_code == 200 and len(session.appels) == 2
    assert sans_attente == [4]  # Retry-After (3 s) + 1 s de marge


def test_429_avec_attente_trop_longue_abandonne_sans_bloquer(sans_attente):
    session = FausseSession(FausseReponse(429, entetes={"Retry-After": "86400"}))
    with pytest.raises(reseau.ErreurSource) as erreur:
        reseau.requete("GET", "https://exemple.test", "Test", session=session, attente_max=60)
    assert erreur.value.statut == 429 and len(session.appels) == 1 and sans_attente == []


def test_erreurs_passageres_backoff_exponentiel_puis_echec(sans_attente):
    session = FausseSession(*[FausseReponse(503) for _ in range(4)])
    with pytest.raises(reseau.ErreurSource):
        reseau.requete("GET", "https://exemple.test", "Test", session=session, tentatives=4, backoff=2)
    assert len(session.appels) == 4
    assert sans_attente == [2, 4, 8]  # attente exponentielle entre les tentatives


def test_erreur_definitive_404_sans_nouvelle_tentative():
    session = FausseSession(FausseReponse(404, texte="introuvable"))
    with pytest.raises(reseau.ErreurSource) as erreur:
        reseau.requete("GET", "https://exemple.test", "Test", session=session)
    assert erreur.value.statut == 404 and len(session.appels) == 1


def test_coupure_reseau_puis_succes():
    session = FausseSession(requests.exceptions.ConnectionError("coupé"), FausseReponse(200, {"ok": 1}))
    assert reseau.requete("GET", "https://exemple.test", "Test", session=session).status_code == 200


def test_reponse_qui_nest_pas_du_json():
    reponse = FausseReponse(200, texte="<html>Service indisponible</html>")
    with pytest.raises(reseau.ErreurSource, match="JSON attendu"):
        reseau.lire_json(reponse, "Test")


def test_erreur_source_reste_une_erreur_requests():
    """Le code existant qui rattrape RequestException rattrape aussi nos erreurs."""
    assert issubclass(reseau.ErreurSource, requests.exceptions.RequestException)


def test_retry_after_au_format_date_http():
    assert reseau.attente_retry_after("Wed, 11 Nov 2026 12:00:30 GMT", maintenant=1794398400.0) == 30
    assert reseau.attente_retry_after("n'importe quoi") is None


def test_les_cles_ne_sont_jamais_journalisees():
    assert reseau._masquer({"api_key": "secret", "search": "glaucoma"}) == {"api_key": "***", "search": "glaucoma"}
