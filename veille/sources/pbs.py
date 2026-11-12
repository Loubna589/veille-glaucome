"""Australie : PBS (Pharmaceutical Benefits Scheme) — médicaments remboursés, API publique « PBS API PUBLIC v3 ».

Documentation : https://data.pbs.gov.au/api/pbs-api.html · catalogue : https://data-api-portal.health.gov.au/apis
- l'API publique « est librement accessible à tous » ; elle exige un en-tête « Subscription-Key ».
  Le portail du ministère publie une clé partagée pour les utilisateurs publics non inscrits :
  la copier dans .env (PBS_API_KEY=…). Sans clé, cette source est sautée proprement ;
- limite partagée par TOUS les utilisateurs publics : 1 requête toutes les 20 secondes → on fait très peu
  d'appels (1 pour le barème du mois, puis les pages d'items), avec un cache d'une journée ;
- données mises à jour le 1er de chaque mois (« schedule »).

On garde les items à usage oculaire et on rattache par le nom du médicament déclaré
(« latanoprost with timolol » → latanoprost + timolol). Date affichée : 1re inscription au PBS
(« first_listed_date ») quand l'API la fournit ; sinon, pas de date.
À VALIDER au premier appel réel : les noms de champs sont lus avec prudence (plusieurs noms acceptés).
"""
import json
import os
import re
import time

from veille import marche_commun as mc
from veille import reseau

API = "https://data-api.health.gov.au/pbs/api/v3/"
PAUSE = 21          # secondes entre deux appels (limite publique : 1 requête / 20 s, partagée)
PAR_PAGE = 10000
MAX_PAGES = 5
suivi = {"appels_reseau": 0, "depuis_cache": 0}
OCULAIRE = re.compile(r"eye|ophthalm|ocular|intraocular", re.I)


class CleAbsente(Exception):
    """Pas de PBS_API_KEY : la source est sautée (ce n'est pas une panne)."""
    saute = True  # lu par base.Execution : étape notée « saute », l'exécution reste « ok »


_dernier = [0.0]


def appeler(service, cle, **params):
    attente = _dernier[0] + PAUSE - time.monotonic()
    if _dernier[0] and attente > 0:
        time.sleep(attente)
    suivi["appels_reseau"] += 1
    try:
        reponse = reseau.requete("GET", API + service, "PBS (Australie)", params=params, timeout=90, tentatives=2,
                                 headers={"Subscription-Key": cle, "Accept": "application/json"}, attente_max=60)
    finally:
        _dernier[0] = time.monotonic()
    return reseau.lire_json(reponse, "PBS (Australie)")


def lignes(corps):
    """Les réponses de l'API sont du type {"data": [...], "_meta": {...}} ; on accepte aussi une liste directe."""
    if isinstance(corps, list):
        return corps
    return corps.get("data") or corps.get("items") or []


def champ(element, *noms):
    return next((element[n] for n in noms if element.get(n) not in (None, "")), None)


def substances(nom):
    """« latanoprost with timolol » / « dorzolamide + timolol » → liste de substances."""
    return [s for s in re.split(r"\s+with\s+|\s*\+\s*|\s+and\s+|,", nom or "", flags=re.I) if s.strip()]


def collecter(molecules, cle=None):
    cle = cle if cle is not None else os.getenv("PBS_API_KEY", "").strip()
    if not cle:
        raise CleAbsente("PBS_API_KEY absente de .env : Australie non collectée (voir .env.example)")
    fichier = mc.CACHE / "pbs_items.json"
    if fichier.exists() and time.time() - fichier.stat().st_mtime < mc.DUREE_CACHE:
        suivi["depuis_cache"] += 1
        brut = json.loads(fichier.read_text(encoding="utf-8"))
    else:
        schedules = sorted(lignes(appeler("schedules", cle)), key=lambda s: str(champ(s, "effective_date", "schedule_code") or ""))
        if not schedules:
            raise ValueError("PBS : aucun barème (schedule) renvoyé")
        code = champ(schedules[-1], "schedule_code")
        items = []
        for page in range(1, MAX_PAGES + 1):
            lot = lignes(appeler("items", cle, schedule_code=code, limit=PAR_PAGE, page=page))
            items += lot
            if len(lot) < PAR_PAGE:
                break
        brut = {"schedule_code": code, "effective_date": champ(schedules[-1], "effective_date"), "items": items}
        mc.CACHE.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    resultat = {m["nom"]: {} for m in molecules}
    for it in brut["items"]:
        voie = " ".join(str(champ(it, n) or "") for n in ("manner_of_administration", "li_form", "schedule_form", "form"))
        if not OCULAIRE.search(voie):
            continue
        nom_medicament = champ(it, "drug_name", "li_drug_name") or ""
        molecule = mc.rattacher(substances(nom_medicament), molecules)
        if not molecule:
            continue
        code_pbs = champ(it, "pbs_code")
        resultat[molecule["nom"]].setdefault(code_pbs or nom_medicament, {
            "nom": champ(it, "brand_name") or nom_medicament, "pbs_code": code_pbs, "medicament": nom_medicament,
            "programme": champ(it, "program_code"),
            # Fabricant : seulement si l'item le nomme (le code seul n'est pas un nom ; rien n'est déduit d'ailleurs)
            "titulaire": champ(it, "manufacturer_name", "organisation_name", "sponsor_name"),
            "code_fabricant": champ(it, "manufacturer_code", "organisation_id"),"date_inscription": mc.date_iso(str(champ(it, "first_listed_date") or "")),
            "prix": champ(it, "determined_price", "dispensed_price_max_quantity"),
            "lien": f"https://www.pbs.gov.au/medicine/item/{code_pbs}" if code_pbs else None,
        })
    sortie = {nom: sorted(d.values(), key=lambda x: x["date_inscription"] or "9999") for nom, d in resultat.items()}
    source = {"nom": "PBS — Pharmaceutical Benefits Scheme (Australie)", "url": "https://data.pbs.gov.au/api/pbs-api.html",
              "telecharge_le": time.strftime("%Y-%m-%d"), "bareme": brut.get("schedule_code"),
              "bareme_en_vigueur": brut.get("effective_date")}
    return sortie, source
