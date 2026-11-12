"""Assistant RAG : validation des citations (modèle simulé), journalisation, mode sans jeton."""
import json

import numpy as np

from conftest import FausseReponse, FausseSession
from veille import rag, semantique

RESULTATS = [{"id": "NCT07845357", "type": "essai", "titre": "Preservative-free", "texte": "x"},
             {"id": "42133103", "type": "article", "titre": "Netarsudil", "texte": "y"}]


def test_citations_valides():
    statut, citees, inconnues = rag.verifier_citations("Un essai compare… [NCT07845357]. Une méta-analyse… [PMID:42133103].", RESULTATS)
    assert statut == "ok" and citees == ["NCT07845357", "PMID:42133103"] and inconnues == []


def test_citation_inventee_refusee():
    statut, _, inconnues = rag.verifier_citations("Affirmation [PMID:99999999].", RESULTATS)
    assert statut == "citations_invalides" and inconnues == ["PMID:99999999"]


def test_reponse_sans_citation_refusee():
    assert rag.verifier_citations("Les collyres sans conservateur sont meilleurs.", RESULTATS)[0] == "sans_citation"


def test_je_ne_sais_pas_accepte():
    texte = "Je ne sais pas : les extraits retrouvés ne permettent pas de répondre à cette question."
    assert rag.verifier_citations(texte, RESULTATS)[0] == "je_ne_sais_pas"


def test_etiquettes_et_liens():
    assert rag.etiquette("123", "article") == "PMID:123" and rag.etiquette("W9", "publication") == "OpenAlex:W9"
    assert rag.lien_citation("NCT07845357") == "https://clinicaltrials.gov/study/NCT07845357"
    assert rag.lien_citation("PMID:123") == "https://pubmed.ncbi.nlm.nih.gov/123/"


class FauxEncodeur:
    modele = "faux"

    def question(self, texte):
        return np.array([1, 0], dtype=np.float32)


def assistant(tmp_path, jeton, session=None):
    index = semantique.Index(np.array([[1, 0], [0, 1]], dtype=np.float32), [r["id"] for r in RESULTATS],
                             [{k: r[k] for k in ("type", "titre", "texte")} for r in RESULTATS])
    return rag.Assistant(chemin_db=tmp_path / "rag.db", index=index, encodeur=FauxEncodeur(), jeton=jeton, session=session)


def reponse_modele(texte):
    return FausseReponse(200, {"choices": [{"message": {"content": texte}}]})


def test_sans_jeton_sources_seules_et_journal(tmp_path):
    a = assistant(tmp_path, jeton="")
    sortie = a.repondre("question ?")
    assert sortie["statut"] == "sans_jeton" and sortie["reponse"] is None and len(sortie["sources"]) == 2
    import sqlite3
    ligne = sqlite3.connect(tmp_path / "rag.db").execute("SELECT question, ids_retrouves, version_prompt, statut FROM echanges_rag").fetchone()
    assert ligne[0] == "question ?" and json.loads(ligne[1]) == ["NCT07845357", "PMID:42133103"]
    assert ligne[2] == rag.VERSION_PROMPT and ligne[3] == "sans_jeton"


def test_reponse_du_modele_verifiee(tmp_path):
    session = FausseSession(reponse_modele("Un essai évalue ZOLYMBUS sans conservateur [NCT07845357]."))
    sortie = assistant(tmp_path, jeton="jeton-test", session=session).repondre("sans conservateur ?")
    assert sortie["statut"] == "ok" and sortie["citations"] == ["NCT07845357"] and sortie["modele"] == rag.MODELE
    envoye = session.appels[0][2]["json"]["messages"][1]["content"]
    assert "[NCT07845357]" in envoye and "[PMID:42133103]" in envoye   # les extraits sont bien transmis


def test_modele_qui_invente_une_source(tmp_path):
    session = FausseSession(reponse_modele("Selon une étude [PMID:12345678], c'est efficace."))
    sortie = assistant(tmp_path, jeton="jeton-test", session=session).repondre("q")
    assert sortie["statut"] == "citations_invalides" and "PMID:12345678" in sortie["erreur"]


def test_prompt_rag_versionne():
    assert "Je ne sais pas" in rag.prompt() and "[NCT" in rag.prompt()
