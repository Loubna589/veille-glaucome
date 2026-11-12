"""Canada : Base de données sur les produits pharmaceutiques (DPD) de Santé Canada — API JSON publique, sans clé.

Documentation : https://health-products.canada.ca/api/documentation/dpd-documentation-en.html
(données publiées sous la Licence du gouvernement ouvert — Canada).

1. pour chaque substance suivie : liste des produits qui la contiennent (activeingredient) ;
2. pour chaque produit : fiche (marque, titulaire, nombre de substances), statut et date de 1re
   commercialisation, voie d'administration — seuls les produits OPHTALMIQUES sont gardés ;
3. un produit n'est rattaché à une molécule que si TOUTES ses substances sont connues et
   correspondent exactement (number_of_ais) : jamais de rattachement approximatif.

La DPD ne publie pas de « date d'autorisation » : on affiche la date de 1re commercialisation déclarée.
Environ 250 produits × 3 appels : appels en parallèle (4 à la fois) et cache d'une journée.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from veille import marche_commun as mc
from veille import reseau

API = "https://health-products.canada.ca/api/drug/"
FICHE = "https://health-products.canada.ca/dpd-bdpp/info?lang=fre&code={code}"
PARALLELE = 4
suivi = {"appels_reseau": 0, "depuis_cache": 0}


def appeler(service, **params):
    suivi["appels_reseau"] += 1
    reponse = reseau.requete("GET", API + service + "/", "Santé Canada DPD",
                             params={"lang": "fr", "type": "json", **params}, timeout=60, tentatives=3)
    return reseau.lire_json(reponse, "Santé Canada DPD")


def fiche_produit(code):
    produit = appeler("drugproduct", id=code)
    statut = appeler("status", id=code)
    voies = appeler("route", id=code)
    return {"produit": produit, "statut": statut, "voies": voies}


def collecter(molecules):
    fichier = mc.CACHE / "canada_dpd.json"
    if fichier.exists() and time.time() - fichier.stat().st_mtime < mc.DUREE_CACHE:
        suivi["depuis_cache"] += 1
        brut = json.loads(fichier.read_text(encoding="utf-8"))
    else:
        substances = sorted({s for m in molecules for s in m["substances"]})
        ingredients = {}  # code produit → noms des substances suivies qu'il contient
        for s in substances:
            for ligne in appeler("activeingredient", ingredientname=s.upper()):
                ingredients.setdefault(str(ligne["drug_code"]), set()).add(ligne["ingredient_name"])
        with ThreadPoolExecutor(PARALLELE) as pool:
            fiches = dict(zip(ingredients, pool.map(fiche_produit, list(ingredients))))
        brut = {code: {"ingredients": sorted(ingredients[code]), **fiches[code]} for code in ingredients}
        mc.CACHE.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    resultat = {m["nom"]: [] for m in molecules}
    for code, b in brut.items():
        produit = b["produit"][0] if isinstance(b["produit"], list) and b["produit"] else b["produit"] or {}
        statut = b["statut"][0] if isinstance(b["statut"], list) and b["statut"] else b["statut"] or {}
        voies = [v.get("route_of_administration_name", "") for v in (b["voies"] or [])]
        if not any("ophtalm" in v.lower() or "ophthalm" in v.lower() for v in voies):
            continue
        try:
            nb_substances = int(produit.get("number_of_ais") or 0)
        except ValueError:
            nb_substances = 0
        if nb_substances != len(b["ingredients"]):
            continue  # le produit contient une substance non suivie : pas de rattachement approximatif
        molecule = mc.rattacher(b["ingredients"], molecules)
        if not molecule:
            continue
        resultat[molecule["nom"]].append({
            "nom": produit.get("brand_name"), "din": produit.get("drug_identification_number"),
            "titulaire": produit.get("company_name"), "statut": statut.get("status"),
            "date_commercialisation": statut.get("original_market_date"), "date_statut": statut.get("history_date"),
            "substances": b["ingredients"], "lien": FICHE.format(code=code),
        })
    for liste in resultat.values():
        liste.sort(key=lambda x: x["date_commercialisation"] or "9999")
    source = {"nom": "Santé Canada — Base de données sur les produits pharmaceutiques (DPD)",
              "url": "https://www.canada.ca/fr/sante-canada/services/medicaments-produits-sante/medicaments/base-donnees-produits-pharmaceutiques.html",
              "telecharge_le": time.strftime("%Y-%m-%d")}
    return resultat, source
