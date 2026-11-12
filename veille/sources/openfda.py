"""Accès au marché aux États-Unis : openFDA, base « Drugs@FDA » (API gratuite, sans clé).

Documentation : https://open.fda.gov/apis/drug/drugsfda/
Sans clé, openFDA accepte 240 requêtes par minute et 1 000 par jour et par adresse IP :
on fait une recherche par substance (une douzaine d'appels), avec un cache d'une journée.

Vocabulaire de la FDA :
- NDA (New Drug Application) : demande pour un médicament de marque (princeps ou nouvelle formulation) ;
- ANDA (Abbreviated NDA) : demande pour un GÉNÉRIQUE ;
- statut « AP » = approuvé ; « TA » = approbation provisoire (pas encore commercialisable).
On ne retient comme date d'approbation que la soumission ORIGINALE au statut AP.
"""
import json
import time

from veille import marche_commun as mc
from veille import reseau

API = "https://api.fda.gov/drug/drugsfda.json"
FICHE = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={numero}"
PAR_PAGE = 100
MAX_PAGES = 10
suivi = {"appels_reseau": 0, "depuis_cache": 0}
_dernier_appel = 0.0


def rechercher(substance):
    """Toutes les demandes (NDA/ANDA) d'au moins un produit ophtalmique contenant cette substance."""
    global _dernier_appel
    fichier = mc.CACHE / f"openfda_{substance.replace(' ', '_')}.json"
    if fichier.exists() and time.time() - fichier.stat().st_mtime < mc.DUREE_CACHE:
        suivi["depuis_cache"] += 1
        return json.loads(fichier.read_text(encoding="utf-8"))
    requete = f'products.active_ingredients.name:"{substance}" AND products.route:"OPHTHALMIC"'
    resultats = []
    for page in range(MAX_PAGES):
        attente = _dernier_appel + 0.3 - time.monotonic()  # rester loin de 240 requêtes / minute
        if attente > 0:
            time.sleep(attente)
        suivi["appels_reseau"] += 1
        try:
            reponse = reseau.requete("GET", API, "openFDA", params={"search": requete, "limit": PAR_PAGE,
                                                                    "skip": page * PAR_PAGE},
                                     headers={"User-Agent": mc.AGENT}, timeout=mc.DELAI_MAX)
        except reseau.ErreurSource as erreur:
            if erreur.statut == 404:  # openFDA répond 404 quand rien ne correspond
                break
            raise
        finally:
            _dernier_appel = time.monotonic()
        corps = reseau.lire_json(reponse, "openFDA")
        resultats += corps.get("results", [])
        if len(resultats) >= corps.get("meta", {}).get("results", {}).get("total", 0):
            break
    mc.CACHE.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(resultats, ensure_ascii=False), encoding="utf-8")
    return resultats


def approbation_originale(demande):
    """Date de la soumission originale approuvée (AP), ou None."""
    for s in demande.get("submissions") or []:
        if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP":
            return mc.date_iso(s.get("submission_status_date"))
    return None


def collecter(molecules):
    """Demandes FDA rattachées aux molécules suivies (produits ophtalmiques seulement)."""
    resultat = {m["nom"]: {} for m in molecules}
    substances = sorted({s for m in molecules for s in m["substances"]})
    for substance in substances:
        for d in rechercher(substance):
            numero = d.get("application_number")
            for p in d.get("products") or []:
                if (p.get("route") or "").upper() != "OPHTHALMIC":
                    continue
                noms = [i.get("name") for i in p.get("active_ingredients") or []]
                molecule = mc.rattacher(noms, molecules)
                if not molecule or numero in resultat[molecule["nom"]]:
                    continue
                produits = [x for x in d.get("products") or []
                            if mc.rattacher([i.get("name") for i in x.get("active_ingredients") or []], molecules) is molecule]
                resultat[molecule["nom"]][numero] = {
                    "numero": numero, "type": "générique (ANDA)" if numero.startswith("ANDA") else "marque (NDA)",
                    "sponsor": d.get("sponsor_name"), "marques": sorted({x.get("brand_name") for x in produits if x.get("brand_name")}),
                    "substances": noms, "date_approbation": approbation_originale(d),
                    "statuts_commerciaux": sorted({x.get("marketing_status") for x in produits if x.get("marketing_status")}),
                    "lien": FICHE.format(numero=numero.replace("ANDA", "").replace("NDA", "").replace("BLA", "")),
                }
    sortie = {nom: sorted(d.values(), key=lambda x: x["date_approbation"] or "9999") for nom, d in resultat.items()}
    source = {"nom": "openFDA — Drugs@FDA", "url": "https://open.fda.gov/apis/drug/drugsfda/",
              "telecharge_le": time.strftime("%Y-%m-%d")}
    return sortie, source
