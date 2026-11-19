"""Page « Comparer deux produits » : repère de solidité de chaque étude, calculé par des règles (sans IA).

Chaque étude exportée reçoit un champ « solidite » : ses FORCES et ses LIMITES en mots simples, lues dans
les types de publication PubMed, le titre et le résumé (veille/qualite_etude.py), ou dans le plan déclaré au
registre pour un essai (tirage au sort, insu, nombre de participants, phase, promoteur industriel).
La page compare ensuite deux produits côté navigateur ; la lecture critique par l'IA est faite à la demande.
"""
import re

from veille import qualite_etude

MANQUE = {"Tirage au sort": "pas de tirage au sort signalé", "Insu (« aveugle »)": "pas d'insu signalé",
          "Groupe de comparaison": "pas de groupe de comparaison signalé", "Plusieurs centres": "un seul centre (ou non précisé)",
          "Essai enregistré": "pas de numéro d'essai enregistré"}
INSU = {"NONE": None, "SINGLE": "simple insu", "DOUBLE": "double insu", "TRIPLE": "triple insu", "QUADRUPLE": "quadruple insu"}


def _taille(n):
    return None if n is None else ("grand effectif" if n >= 300 else "effectif moyen" if n >= 100 else "petit effectif")


def solidite_article(d, industriel=False):
    q = qualite_etude.evaluer(d, financement_industriel=industriel)
    texte = f"{d.get('titre') or ''}\n{d.get('resume') or ''}"
    if q["niveau"] and qualite_etude._cherche("preclin", texte) and not re.search(r"\bpatients?\b", texte, re.I):
        # Une étude sur l'animal « randomisée » reste une étude sur l'animal : ce n'est pas une preuve chez l'humain
        q = {**q, "niveau": 0, "libelle": qualite_etude.PRECLINIQUE[0], "force": "Recherche préclinique"}
    forces, limites = [], []
    for c in q["criteres"]:
        if c["present"]:
            forces.append(c["nom"])
        else:
            limites.append(MANQUE.get(c["nom"], "non signalé : " + c["nom"].lower()))
    if q["participants"]:
        (forces if q["participants"] >= 100 else limites).append(f"{q['participants']} participants ({q['taille']})")
    else:
        limites.append("nombre de participants non indiqué dans le résumé")
    if q["niveau"] == 0:
        limites.insert(0, "étude sur l'animal ou en laboratoire : pas encore une preuve chez l'humain")
    if industriel:
        limites.append("auteurs liés à un laboratoire (conflit d'intérêts possible)")
    if q["prepublication"]:
        limites.append("prépublication, pas encore relue par des experts")
    if not q["resume_present"]:
        limites.append("pas de résumé : contenu inconnu")
    else:
        limites.append("jugé sur le résumé seulement")
    return {"niveau": q["niveau"], "type": q["libelle"], "force": q["force"], "participants": q["participants"],
            "forces": forces, "limites": limites}


def solidite_essai(d):
    plan = d.get("plan") or {}
    forces, limites = [], []
    if plan.get("repartition") == "RANDOMIZED":
        forces.append("Tirage au sort")
    elif d.get("type_etude") == "INTERVENTIONAL":
        limites.append("pas de tirage au sort déclaré")
    insu = INSU.get(plan.get("insu"))
    (forces.append(f"Insu ({insu})") if insu else limites.append("pas d'insu déclaré"))
    try:
        n = int(d.get("participants_nombre") or 0) or None
    except ValueError:
        n = None
    if n:
        txt = f"{n} participants{' prévus' if d.get('participants_type') == 'ESTIMATED' else ''} ({_taille(n)})"
        (forces if n >= 100 else limites).append(txt)
    if d.get("type_promoteur") == "INDUSTRY":
        limites.append("financé par un laboratoire (normal pour un essai de médicament, à garder en tête)")
    if d.get("resultats_deposes"):
        forces.append("résultats déposés au registre")
    else:
        limites.append("pas encore de résultats publiés au registre")
    if d.get("type_etude") == "OBSERVATIONAL":
        niveau, type_ = 4, "Étude observationnelle (registre)"
    elif plan.get("repartition") == "RANDOMIZED":
        niveau, type_ = 2, "Essai randomisé (registre)"
    else:
        niveau, type_ = 3, "Essai non randomisé (registre)"
    return {"niveau": niveau, "type": type_, "force": qualite_etude.FORCE.get(niveau), "participants": n,
            "forces": forces, "limites": limites}
