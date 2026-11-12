"""Classement automatique en rubriques, selon config/rubriques.ini.

Chaque rubrique retenue est accompagnée des RAISONS qui l'ont déclenchée
(type d'intervention déclaré, mot du titre, étiquette), pour que le classement
soit toujours identifiable et corrigeable.
"""
import configparser
import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config" / "rubriques.ini"
NOM_AUTRES = "Autres sujets (clinique, épidémiologie…)"
LIBELLES_ETIQUETTES = {
    "produit_suivi_etudie_suggere": "produit suivi étudié (rôle suggéré, à vérifier)",
    "molecule_hors_liste": "molécule hors liste repérée dans le titre (à vérifier)",
    "stade_preclinique": "stade préclinique (indexation PubMed)",
}


def _liste(texte):
    morceaux = re.split(r"[,\n]", texte or "")
    return [m.strip() for m in morceaux if m.strip() and not m.strip().startswith("#")]


def charger(chemin=CONFIG):
    config = configparser.ConfigParser(interpolation=None)
    config.read(chemin, encoding="utf-8")
    regles = {"ordre": _liste(config["ordre"]["priorite"]), "rubriques": {}}
    for cle in regles["ordre"] + ["veterinaire"]:
        s = config[cle]
        regles["rubriques"][cle] = {
            "nom": s.get("nom", cle),
            "types_registre": set(_liste(s.get("types_registre", ""))),
            "buts_registre": set(_liste(s.get("buts_registre", ""))),
            "termes_titre": _liste(s.get("termes_titre", "")),
            "etiquettes": _liste(s.get("etiquettes", "")),
        }
    return regles


def _motif(terme):
    return re.compile(r"\b" + re.escape(terme).replace(r"\*", r"\w*").replace(r"\ ", r"[\s-]+") + r"\b",
                      re.IGNORECASE)


def _resultat(regles, raisons):
    retenues = [{"cle": c, "nom": regles["rubriques"][c]["nom"], "raisons": raisons[c]}
                for c in regles["ordre"] if raisons.get(c)]
    return retenues or [{"cle": "autres", "nom": NOM_AUTRES, "raisons": ["aucune règle de rubrique ne s'applique"]}]


def classer_essai(essai, regles):
    """Classe un essai d'après les types d'intervention DÉCLARÉS (bras expérimentaux en priorité)."""
    interventions = essai.get("interventions") or []
    noms_experimentaux = {n.split(": ", 1)[-1] for b in essai.get("bras") or []
                          if b.get("type") == "EXPERIMENTAL" for n in b.get("interventions") or []}
    retenues = [i for i in interventions if i["nom"] in noms_experimentaux] or interventions
    origine = "bras expérimental" if noms_experimentaux else "intervention"
    but = (essai.get("plan") or {}).get("but_principal")

    raisons = {}
    for cle in regles["ordre"]:
        r = regles["rubriques"][cle]
        for i in retenues:
            if i["type"] in r["types_registre"]:
                raisons.setdefault(cle, []).append(
                    f"{origine} de type {i['type']} déclaré au registre : {i['nom']}")
        if but and but in r["buts_registre"]:
            raisons.setdefault(cle, []).append(f"but principal déclaré au registre : {but}")
    return _resultat(regles, raisons)


def classer_publication(pub, etiquettes, regles):
    """Classe un article d'après les mots de son titre et ses étiquettes calculées."""
    if etiquettes.get("hors_veille_principale"):
        return [{"cle": "veterinaire", "nom": regles["rubriques"]["veterinaire"]["nom"],
                 "raisons": [f"étiquette vétérinaire ({etiquettes.get('stade_source')})"]}]
    titre = pub.get("titre") or ""
    presentes = {
        "produit_suivi_etudie_suggere": etiquettes.get("produit_suivi_etudie_suggere"),
        "molecule_hors_liste": bool(etiquettes.get("molecules_hors_liste")),
        "stade_preclinique": etiquettes.get("stade") == "Préclinique",
    }
    raisons = {}
    for cle in regles["ordre"]:
        r = regles["rubriques"][cle]
        for terme in r["termes_titre"]:
            trouve = _motif(terme).search(titre)
            if trouve:
                raisons.setdefault(cle, []).append(f"mot du titre : « {trouve.group(0)} »")
        for e in r["etiquettes"]:
            if presentes.get(e):
                raisons.setdefault(cle, []).append(f"étiquette : {LIBELLES_ETIQUETTES.get(e, e)}")
    return _resultat(regles, raisons)
