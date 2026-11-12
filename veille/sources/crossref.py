"""Vérification des financements dans Crossref (registre officiel des DOI, gratuit, sans clé).

Quand un éditeur enregistre un DOI, il peut déclarer les financeurs de l'article.
Cette déclaration (champ « funder », marqué asserted-by « publisher ») sert de
JUSTIFICATION aux financeurs repérés par OpenAlex, qui ne précise pas d'où il
tient chacun d'eux.

Les réponses sont gardées dans data/local/cache_crossref/ et ne sont pas redemandées.
"""
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

from veille import reseau

API = "https://api.crossref.org/works"
DELAI_MAX = 30
CACHE = Path(__file__).resolve().parents[2] / "data" / "local" / "cache_crossref"
suivi = {"appels_reseau": 0, "depuis_cache": 0}
_dernier_appel = 0.0


def notice(doi):
    """Adresse publique de la notice Crossref d'un DOI (lisible dans un navigateur)."""
    return f"{API}/{quote(doi, safe='/')}"


def financeurs(doi):
    """Financeurs déclarés dans Crossref pour ce DOI (liste vide si aucun, None si DOI inconnu)."""
    global _dernier_appel
    fichier = CACHE / (doi.replace("/", "_") + ".json")
    if fichier.exists():
        suivi["depuis_cache"] += 1
        message = json.loads(fichier.read_text(encoding="utf-8"))
    else:
        attente = _dernier_appel + 0.25 - time.monotonic()  # Crossref : 5 requêtes/s au plus
        if attente > 0:
            time.sleep(attente)
        agent = "veille-glaucome/0.1" + (f" (mailto:{os.getenv('CONTACT_EMAIL')})" if os.getenv("CONTACT_EMAIL") else "")
        suivi["appels_reseau"] += 1
        try:
            reponse = reseau.requete("GET", notice(doi), "Crossref", headers={"User-Agent": agent}, timeout=DELAI_MAX)
        except reseau.ErreurSource as erreur:
            if erreur.statut == 404:
                return None  # DOI inconnu de Crossref : ce n'est pas une panne
            raise
        finally:
            _dernier_appel = time.monotonic()
        message = reseau.lire_json(reponse, "Crossref")["message"]
        CACHE.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(message, ensure_ascii=False), encoding="utf-8")

    return [
        {
            "nom": f.get("name"),
            "identifiant": f.get("DOI"),  # identifiant officiel du financeur (Open Funder Registry)
            "references": f.get("award") or None,
            "declare_par": f.get("doi-asserted-by"),  # « publisher » = déclaré par l'éditeur
        }
        for f in message.get("funder") or []
    ]


def meme_nom(a, b):
    """Compare deux noms d'organisme sans tenir compte de la casse ni des espaces spéciaux."""
    simplifier = lambda s: " ".join((s or "").replace("\xa0", " ").lower().split())
    return simplifier(a) == simplifier(b)
