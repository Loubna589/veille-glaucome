"""Enrichissement et découverte avec OpenAlex (https://openalex.org).

Budget : sans clé, OpenAlex accorde un budget quotidien (environ 1 000 crédits).
Une recherche par identifiants (PMID, DOI) coûte 1 crédit, une recherche en texte
libre 10 crédits. En période de forte charge, les recherches en texte libre
anonymes peuvent être temporairement refusées (HTTP 429) ; une clé gratuite
(variable OPENALEX_API_KEY dans .env) lève cette restriction.

Pour économiser ce budget :
- chaque réponse est gardée dans un CACHE local (data/local/cache_openalex/) et
  n'est jamais redemandée, sauf si on le demande explicitement (rafraichir=True) ;
- les identifiants sont demandés PAR LOTS (jusqu'à 50 en un seul appel) ;
- un PLAFOND d'appels réseau par exécution protège contre les boucles imprévues.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from veille import reseau

API = "https://api.openalex.org"
DELAI_MAX = 30
CACHE = Path(__file__).resolve().parents[2] / "data" / "local" / "cache_openalex"
ATTENTE_MAX = 60  # on accepte d'attendre au plus 60 s quand OpenAlex le demande

# Suivi de l'exécution en cours (affiché dans le bilan)
suivi = {"appels_reseau": 0, "depuis_cache": 0, "plafond": 10, "budget": {}}


class ErreurOpenAlex(Exception):
    """Erreur expliquée en français."""


def _cle_cache(chemin, params):
    brut = json.dumps([chemin, sorted(params.items())], ensure_ascii=False)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()


def _lire_budget(reponse):
    h = reponse.headers
    suivi["budget"] = {
        "restant": h.get("X-RateLimit-Remaining"),
        "limite": h.get("X-RateLimit-Limit"),
        "cout_credits": h.get("X-RateLimit-Credits-Used"),
        "reinitialisation_s": h.get("X-RateLimit-Reset"),
    }


def expliquer(reponse):
    """Transforme une réponse HTTP en échec en explication lisible."""
    try:
        corps = reponse.json()
    except ValueError:
        corps = {}
    message = corps.get("message") or corps.get("error") or reponse.text[:200]
    code = reponse.status_code
    b = suivi["budget"]
    if code == 429:
        attente = reponse.headers.get("Retry-After") or corps.get("retryAfter")
        return (f"HTTP 429 — trop de requêtes. OpenAlex dit : « {message} ». "
                f"Délai demandé : {attente or 'non précisé'} s. "
                f"Crédits restants aujourd'hui : {b.get('restant') or 'non communiqué'}.")
    if code == 400:
        return f"HTTP 400 — requête refusée car mal formée. OpenAlex dit : « {message} »."
    if code in (401, 403):
        return f"HTTP {code} — accès refusé (clé API absente, invalide ou budget épuisé). OpenAlex dit : « {message} »."
    if code == 404:
        return f"HTTP 404 — élément introuvable dans OpenAlex. « {message} »."
    if code >= 500:
        return f"HTTP {code} — panne passagère du serveur OpenAlex. « {message} »."
    return f"HTTP {code} — « {message} »."


def appeler(chemin, params, rafraichir=False):
    """GET sur l'API, avec cache, plafond d'appels et nouvelles tentatives raisonnables."""
    fichier = CACHE / f"{_cle_cache(chemin, params)}.json"
    if fichier.exists() and not rafraichir:
        suivi["depuis_cache"] += 1
        return json.loads(fichier.read_text(encoding="utf-8"))["reponse"]

    if suivi["appels_reseau"] >= suivi["plafond"]:
        raise ErreurOpenAlex(f"plafond de {suivi['plafond']} appels réseau atteint pour cette exécution "
                             "(sécurité pour préserver le budget quotidien).")

    envoyes = dict(params)
    if os.getenv("CONTACT_EMAIL"):
        envoyes["mailto"] = os.getenv("CONTACT_EMAIL")
    if os.getenv("OPENALEX_API_KEY"):
        envoyes["api_key"] = os.getenv("OPENALEX_API_KEY")

    # Tentatives, backoff exponentiel, 429 + Retry-After : module commun veille/reseau.py
    suivi["appels_reseau"] += 1
    try:
        reponse = reseau.requete("GET", f"{API}/{chemin}", "OpenAlex", params=envoyes, timeout=DELAI_MAX,
                                 tentatives=3, attente_max=ATTENTE_MAX)
    except reseau.ErreurSource as erreur:
        if erreur.reponse is not None:
            _lire_budget(erreur.reponse)
            raise ErreurOpenAlex(expliquer(erreur.reponse)) from erreur
        raise ErreurOpenAlex(str(erreur)) from erreur
    _lire_budget(reponse)
    donnees = reseau.lire_json(reponse, "OpenAlex")
    CACHE.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps({
        "date": time.strftime("%Y-%m-%d %H:%M"), "chemin": chemin, "params": params,
        "cout_credits": suivi["budget"].get("cout_credits"), "reponse": donnees,
    }, ensure_ascii=False), encoding="utf-8")
    return donnees


# ------------------------------------------------------------ requêtes utiles

def par_identifiants(pmids=(), dois=()):
    """Cherche des publications par PMID et/ou DOI, par lots de 50 (1 crédit par lot)."""
    trouvees = []
    for champ, valeurs in (("ids.pmid", list(pmids)), ("doi", list(dois))):
        for i in range(0, len(valeurs), 50):
            lot = "|".join(sorted(valeurs[i:i + 50]))
            reponse = appeler("works", {"filter": f"{champ}:{lot}", "per-page": 50})
            trouvees.extend(reponse["results"])
    return trouvees


def decouvrir(recherche, filtres, nombre=5):
    """Recherche en texte libre (10 crédits) + filtres OpenAlex."""
    filtre = ",".join([f"title_and_abstract.search:{recherche}", *filtres])
    return appeler("works", {"filter": filtre, "per-page": nombre})["results"]


# ------------------------------------------------------------ lecture d'une notice

def _sans_prefixe(url, prefixe):
    return url.replace(prefixe, "") if url else None


def resume(index_inverse):
    """OpenAlex stocke le résumé sous forme {mot: [positions]} : on le reconstitue."""
    if not index_inverse:
        return None
    mots = {pos: mot for mot, positions in index_inverse.items() for pos in positions}
    return " ".join(mots[i] for i in sorted(mots))


def normaliser(w):
    ids = w.get("ids") or {}
    source = (w.get("primary_location") or {}).get("source") or {}
    acces = w.get("open_access") or {}
    meilleur = w.get("best_oa_location") or {}

    institutions = {}
    for auteur in w.get("authorships") or []:
        for inst in auteur.get("institutions") or []:
            institutions.setdefault(inst.get("id"), {
                "nom": inst.get("display_name"),
                "pays": inst.get("country_code"),
                "type": inst.get("type"),  # education, healthcare, company, government…
                "ror": inst.get("ror"),
            })

    return {
        "openalex_id": _sans_prefixe(w.get("id"), "https://openalex.org/"),
        "doi": (_sans_prefixe(w.get("doi"), "https://doi.org/") or "").lower() or None,
        "pmid": _sans_prefixe(ids.get("pmid"), "https://pubmed.ncbi.nlm.nih.gov/"),
        "pmcid": _sans_prefixe(ids.get("pmcid"), "https://www.ncbi.nlm.nih.gov/pmc/articles/"),
        "titre": w.get("title") or w.get("display_name"),
        "lien": w.get("id"),
        "date_publication": w.get("publication_date"),
        "type": w.get("type"),
        "revue": source.get("display_name"),
        "type_source": source.get("type"),  # journal, repository (serveur de preprints)…
        "langue": w.get("language"),
        "indexe_dans": w.get("indexed_in"),
        "financeurs": [{"nom": f.get("display_name"), "ror": f.get("ror")} for f in w.get("funders") or []] or None,
        "subventions": [
            {"financeur": a.get("funder_display_name"), "reference": a.get("funder_award_id")}
            for a in w.get("awards") or []
        ] or None,
        "institutions": list(institutions.values()) or None,
        "acces_ouvert": acces.get("is_oa"),
        "statut_acces": acces.get("oa_status"),  # gold, hybrid, green, bronze, diamond, closed
        "url_texte": acces.get("oa_url"),
        "url_pdf": meilleur.get("pdf_url"),
        "licence": meilleur.get("license"),
        "texte_integral_indexe": w.get("has_fulltext"),
        "retracte": w.get("is_retracted"),
        "citations": w.get("cited_by_count"),
        "sujet_principal": (w.get("primary_topic") or {}).get("display_name"),
        "resume_present": bool(w.get("abstract_inverted_index")),
        "resume": resume(w.get("abstract_inverted_index")),
        # Un même terme MeSH est répété pour chacun de ses qualificatifs : on dédoublonne
        "mesh": list(dict.fromkeys(m.get("descriptor_name") for m in w.get("mesh") or [])) or None,
    }
