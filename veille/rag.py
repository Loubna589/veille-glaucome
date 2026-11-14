"""Assistant RAG (Retrieval-Augmented Generation) : recherche sémantique → extraits → IA (Mistral ou Gemini) → réponse citée.

1. la question passe par la recherche hybride (veille/semantique.py) : top k extraits ;
2. les extraits sont envoyés au modèle avec un prompt VERSIONNÉ (config/prompts/rag_v1.md) :
   réponse en français, uniquement à partir des extraits, chaque affirmation citée [PMID:…] / [NCT…],
   « Je ne sais pas » si les extraits ne suffisent pas ;
3. la réponse est VÉRIFIÉE : toute citation doit désigner un extrait réellement fourni, et une réponse
   (hors « je ne sais pas ») sans aucune citation est refusée ;
4. chaque échange est journalisé dans SQLite (table echanges_rag) : question, identifiants retrouvés,
   scores, modèle, version du prompt, réponse, citations, statut, durée.

Sans clé MISTRAL_API_KEY ou GEMINI_API_KEY (lue dans .env), l'assistant renvoie les sources retrouvées SANS synthèse.
"""
import os
import re
import time
from contextlib import closing
from pathlib import Path

from veille import base, fournisseur_ia, reseau, semantique

RACINE = Path(__file__).resolve().parents[1]
VERSION_PROMPT = os.getenv("VERSION_PROMPT_RAG", "rag_v1")
K = 6
MOTIF_CITATION = re.compile(r"\[(PMID:\d+|NCT\d{8}|OpenAlex:W\d+)\]")
JE_NE_SAIS_PAS = "je ne sais pas"

SCHEMA = """
CREATE TABLE IF NOT EXISTS echanges_rag (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, question TEXT NOT NULL, question_etendue TEXT,
    ids_retrouves TEXT NOT NULL, scores TEXT, modele TEXT, version_prompt TEXT NOT NULL,
    reponse TEXT, citations TEXT, statut TEXT NOT NULL, duree_ms INTEGER
);
"""


def prompt(version=VERSION_PROMPT):
    return (RACINE / "config" / "prompts" / f"{version}.md").read_text(encoding="utf-8")


def etiquette(doc_id, doc_type):
    """Identifiant de citation : PMID:123, NCT01234567 ou OpenAlex:W123."""
    if doc_type == "essai":
        return doc_id
    return f"PMID:{doc_id}" if str(doc_id).isdigit() else f"OpenAlex:{doc_id}"


def lien_citation(cite):
    if cite.startswith("PMID:"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{cite[5:]}/"
    if cite.startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{cite}"
    return f"https://openalex.org/{cite.split(':', 1)[1]}"


def extraits_texte(resultats):
    return "\n\n".join(f"[{etiquette(r['id'], r['type'])}] {r.get('texte') or r.get('titre')}" for r in resultats)


def verifier_citations(reponse, resultats):
    """Contrôle les citations. Renvoie (statut, citations trouvées, citations inconnues).

    statut : « ok », « je_ne_sais_pas », « citations_invalides » (identifiant absent des extraits)
    ou « sans_citation » (affirmations non sourcées)."""
    autorisees = {etiquette(r["id"], r["type"]) for r in resultats}
    citees = list(dict.fromkeys(MOTIF_CITATION.findall(reponse or "")))
    inconnues = [c for c in citees if c not in autorisees]
    if JE_NE_SAIS_PAS in (reponse or "").lower() and not citees:
        return "je_ne_sais_pas", citees, inconnues
    if inconnues:
        return "citations_invalides", citees, inconnues
    if not citees:
        return "sans_citation", citees, inconnues
    return "ok", citees, inconnues


def demander(question, resultats, jeton, session=None):
    f = fournisseur_ia.actif("MODELE_RAG")
    corps = {"model": f.modele, "temperature": 0, "max_tokens": 700,
             "messages": [{"role": "system", "content": prompt()},
                          {"role": "user", "content": f"QUESTION : {question}\n\nEXTRAITS :\n{extraits_texte(resultats)}"}]}
    return reseau.appeler_chat(f.url, corps, jeton, f"IA ({f.nom}, assistant)", session=session)["choices"][0]["message"]["content"].strip()


class Assistant:
    def __init__(self, chemin_db=None, index=None, encodeur=None, jeton=None, session=None):
        # Une connexion SQLite PAR requête (un serveur web répond depuis plusieurs fils d'exécution)
        self.chemin_db = chemin_db or base.CHEMIN
        with closing(base.connecter(self.chemin_db)) as conn:
            conn.executescript(SCHEMA)
        self.index = index or semantique.Index.charger()
        self.encodeur = encodeur or semantique.Encodeur()
        self.jeton = jeton if jeton is not None else fournisseur_ia.actif("MODELE_RAG").cle
        self.session = session

    def repondre(self, question, k=K):
        debut = time.monotonic()
        resultats, etendue = semantique.rechercher(self.index, self.encodeur, question, k=k)
        sources = [{"citation": etiquette(r["id"], r["type"]), "id": r["id"], "type": r["type"], "titre": r.get("titre"),
                    "score": r["score"], "lien": lien_citation(etiquette(r["id"], r["type"])), "fiche": r.get("fiche")}
                   for r in resultats]
        sortie = {"question": question, "question_etendue": etendue, "sources": sources, "modele": None,
                  "version_prompt": VERSION_PROMPT, "reponse": None, "citations": [], "statut": "sans_jeton", "erreur": None}
        if self.jeton:
            sortie["modele"] = fournisseur_ia.actif("MODELE_RAG").modele
            try:
                texte = demander(question, resultats, self.jeton, self.session)
                statut, citees, inconnues = verifier_citations(texte, resultats)
                sortie.update(reponse=texte, citations=citees, statut=statut)
                if inconnues:
                    sortie["erreur"] = f"citations absentes des extraits : {', '.join(inconnues)}"
            except reseau.ErreurSource as erreur:
                sortie.update(statut="erreur", erreur=str(erreur))
        sortie["duree_ms"] = int((time.monotonic() - debut) * 1000)
        with closing(base.connecter(self.chemin_db)) as conn:
            conn.execute(
                "INSERT INTO echanges_rag (date, question, question_etendue, ids_retrouves, scores, modele, version_prompt, "
                "reponse, citations, statut, duree_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (base.maintenant(), question, etendue, base.jdump([s["citation"] for s in sources]),
                 base.jdump([s["score"] for s in sources]), sortie["modele"], VERSION_PROMPT, sortie["reponse"],
                 base.jdump(sortie["citations"]), sortie["statut"], sortie["duree_ms"]))
            conn.commit()
        return sortie
