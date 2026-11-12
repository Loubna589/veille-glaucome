"""Espagne : CIMA, le centre d'information des médicaments de l'AEMPS — API REST publique, sans clé.

Documentation : https://cima.aemps.es/cima/publico/home.html (rubrique « REST API »).

Pour chaque substance suivie, recherche par principe actif (nom espagnol) ; on garde les
médicaments à voie ophtalmique et on rattache par la composition déclarée (champ « vtm »,
ex. « latanoprost + timolol »). La date d'autorisation (estado.aut) est fournie en millisecondes.
"""
import json
import time
from datetime import datetime, timezone

from veille import marche_commun as mc
from veille import reseau

API = "https://cima.aemps.es/cima/rest/medicamentos"
FICHE = "https://cima.aemps.es/cima/publico/detalle.html?nregistro={n}"
NOMS_ESPAGNOLS = {"dorzolamide": "dorzolamida", "brinzolamide": "brinzolamida", "brimonidine": "brimonidina",
                  "latanoprostene bunod": "latanoprosteno"}
suivi = {"appels_reseau": 0, "depuis_cache": 0}


def date_ms(valeur):
    if not valeur:
        return None
    return datetime.fromtimestamp(valeur / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def rechercher(substance):
    fichier = mc.CACHE / f"cima_{substance.replace(' ', '_')}.json"
    if fichier.exists() and time.time() - fichier.stat().st_mtime < mc.DUREE_CACHE:
        suivi["depuis_cache"] += 1
        return json.loads(fichier.read_text(encoding="utf-8"))
    resultats, page = [], 1
    while True:
        suivi["appels_reseau"] += 1
        corps = reseau.lire_json(reseau.requete("GET", API, "AEMPS CIMA", timeout=60, tentatives=3, params={
            "practiv1": NOMS_ESPAGNOLS.get(substance, substance), "pagina": page}), "AEMPS CIMA")
        resultats += corps.get("resultados") or []
        if len(resultats) >= corps.get("totalFilas", 0) or not corps.get("resultados") or page >= 20:
            break
        page += 1
    mc.CACHE.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(resultats, ensure_ascii=False), encoding="utf-8")
    return resultats


def collecter(molecules):
    resultat = {m["nom"]: {} for m in molecules}
    for substance in sorted({s for m in molecules for s in m["substances"]}):
        for med in rechercher(substance):
            voies = " ".join(v.get("nombre", "") for v in med.get("viasAdministracion") or [])
            if "OFT" not in mc.sans_accents(voies).upper():
                continue
            vtm = (med.get("vtm") or {}).get("nombre") or ""
            molecule = mc.rattacher(vtm.split("+"), molecules)
            if not molecule:
                continue
            etat = med.get("estado") or {}
            resultat[molecule["nom"]][med["nregistro"]] = {
                "nom": med.get("nombre"), "numero": med.get("nregistro"), "titulaire": med.get("labtitular"),
                "date_autorisation": date_ms(etat.get("aut")), "date_suspension": date_ms(etat.get("susp")),
                "date_revocation": date_ms(etat.get("rev")), "commercialise": bool(med.get("comerc")),
                "generique": bool(med.get("generico")), "procedure_ue": bool(med.get("ema")),
                "substances": vtm, "lien": FICHE.format(n=med["nregistro"]),
            }
    sortie = {nom: sorted(d.values(), key=lambda x: x["date_autorisation"] or "9999") for nom, d in resultat.items()}
    source = {"nom": "AEMPS — CIMA (Espagne)", "url": "https://cima.aemps.es/cima/publico/home.html",
              "telecharge_le": time.strftime("%Y-%m-%d")}
    return sortie, source
