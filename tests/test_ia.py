"""IA : validation stricte de la sortie JSON, traçabilité et cache (GitHub Models simulé)."""
import json

import pytest

from conftest import FausseReponse, FausseSession, essai
from veille import base, resumer_ia

VALIDE = {"resume": ["Objectif.", "Méthode.", "Résultat."], "categorie": "traitement_medicamenteux",
          "justification": "Le texte évalue un collyre."}


def reponse_modele(contenu):
    return FausseReponse(200, {"choices": [{"message": {"content": contenu}}]})


def test_sortie_valide():
    assert resumer_ia.valider_sortie(json.dumps(VALIDE))["categorie"] == "traitement_medicamenteux"


def test_sortie_entouree_de_balises_code_acceptee():
    assert resumer_ia.valider_sortie("```json\n" + json.dumps(VALIDE) + "\n```")["resume"][0] == "Objectif."


@pytest.mark.parametrize("modif, message", [
    ({"categorie": "cardiologie"}, "hors liste"),
    ({"resume": ["une", "deux"]}, "3 lignes"),
    ({"resume": ["a", "", "c"]}, "3 lignes"),
    ({"justification": " "}, "justification"),
])
def test_sorties_invalides_rejetees(modif, message):
    with pytest.raises(resumer_ia.SortieInvalide, match=message):
        resumer_ia.valider_sortie(json.dumps({**VALIDE, **modif}))


def test_pas_du_json():
    with pytest.raises(resumer_ia.SortieInvalide, match="pas du JSON"):
        resumer_ia.valider_sortie("Voici le résumé : ...")


def test_cle_manquante():
    with pytest.raises(resumer_ia.SortieInvalide, match="clés manquantes"):
        resumer_ia.valider_sortie(json.dumps({"resume": VALIDE["resume"]}))


def test_traitement_trace_et_jamais_refait(conn):
    base.enregistrer_essai(conn, essai(resume_source="A study of eye drops."), "2026-11-01")
    session = FausseSession(reponse_modele(json.dumps(VALIDE)))
    bilan = resumer_ia.traiter(conn, jeton="jeton-test", session=session, pause=0)
    assert bilan["traites"] == 1
    t = conn.execute("SELECT * FROM traitements_ia").fetchone()
    assert (t["modele"], t["version_prompt"], t["statut_validation"]) == (resumer_ia.fournisseur().modele, resumer_ia.VERSION_PROMPT, "non_verifie")
    assert t["categorie"] == "traitement_medicamenteux" and t["date"]
    # Deuxième passage : déjà traité (même texte source, même prompt) → aucun nouvel appel
    assert resumer_ia.traiter(conn, jeton="jeton-test", session=FausseSession(), pause=0)["traites"] == 0


def test_sortie_invalide_jamais_enregistree(conn):
    base.enregistrer_essai(conn, essai(resume_source="Text."), "2026-11-01")
    session = FausseSession(reponse_modele('{"resume": "pas une liste"}'))
    bilan = resumer_ia.traiter(conn, jeton="jeton-test", session=session, pause=0)
    assert bilan["invalides"] == 1 and conn.execute("SELECT COUNT(*) FROM traitements_ia").fetchone()[0] == 0


def test_sans_jeton_etape_sautee(conn, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert resumer_ia.traiter(conn)["saute"] is True


def test_prompt_versionne_existe():
    assert "categorie" in resumer_ia.prompt() and all(c in resumer_ia.prompt() for c in resumer_ia.CATEGORIES)
