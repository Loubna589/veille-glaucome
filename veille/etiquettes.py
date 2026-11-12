"""Étiquettes calculées sur une publication (PubMed ou OpenAlex).

Tout est calculé à partir de ce que la source contient (titre, résumé, mots-clés,
indexation MeSH, revue) et des listes de config/recherches_pubmed.ini.
Chaque étiquette dit d'où elle vient ; aucune n'est présentée comme un fait
rapporté par les auteurs.

Rôle d'un produit (traitement étudié ou comparateur) — règle automatique simple :
- produit cité dans le TITRE avant un mot de comparaison (versus, vs, compared to/with…)
  ou dans un titre sans comparaison            → rôle « étudié »
- produit cité dans le titre APRÈS ce mot      → rôle « comparateur »
- produit cité seulement dans le résumé, les mots-clés ou l'indexation
                                               → rôle « non déterminé »
Un rôle issu de cette règle est TOUJOURS présenté comme « suggéré, à vérifier » :
PubMed et OpenAlex ne décrivent pas les bras d'une étude de façon structurée, donc
rien ici ne permet de le confirmer.
"""
import re

from veille.sources import pubmed as pm

ROLE_SUGGERE = "rôle suggéré, à vérifier (règle automatique appliquée au titre)"

MOTS_COMPARAISON = re.compile(
    r"\b(?:versus|vs\.?|compared\s+(?:to|with)|in\s+comparison\s+(?:to|with)|against|relative\s+to)\b",
    re.IGNORECASE,
)


def _termes(lignes, avec_mesh=False):
    """'"latanoprostene bunod"[tiab]' → 'latanoprostene bunod'. Sépare texte et MeSH."""
    texte, mesh = [], []
    for ligne in lignes:
        nom = re.sub(r"\[.*?\]", "", ligne).replace('"', "").strip()
        (mesh if "[Mesh]" in ligne else texte).append(nom)
    return (texte, mesh) if avec_mesh else texte


def _motif(terme):
    motif = re.escape(terme).replace(r"\*", r"\w*").replace(r"\ ", r"[\s-]+")
    return re.compile(r"\b" + motif + r"\b", re.IGNORECASE)


def _role(titre, terme):
    """Rôle d'un terme selon sa position dans le titre, ou None s'il n'y figure pas."""
    positions = [m.start() for m in _motif(terme).finditer(titre or "")]
    if not positions:
        return None
    comparaison = MOTS_COMPARAISON.search(titre)
    if not comparaison:
        return "étudié"
    avant = any(p < comparaison.start() for p in positions)
    apres = any(p > comparaison.start() for p in positions)
    if avant and apres:
        return "étudié et comparateur"
    return "étudié" if avant else "comparateur"


def charger_regles(config=None):
    config = config or pm.lire_config()
    c, e = config["ciblee"], config["etiquettes"]
    molecules, molecules_mesh = _termes(pm._lignes(c["molecules"]), avec_mesh=True)
    formulations, formulations_mesh = _termes(pm._lignes(e["formulations"]), avec_mesh=True)
    return {
        "produits": molecules + _termes(pm._lignes(c["marques"])),
        "produits_mesh": molecules_mesh,
        "associations": [tuple(m.strip().lower() for m in l.split("+"))
                         for l in pm._lignes(c.get("associations_fixes", ""))],
        "formulations": formulations,
        "formulations_mesh": formulations_mesh,
        "suffixes_dci": pm._lignes(e["suffixes_dci"]),
        "preclinique_mesh": pm._lignes(e["preclinique_mesh_si_present"]),
        "preclinique_animaux": e.get("preclinique_animaux_sans_humains", "oui").strip().lower() == "oui",
        "veterinaire_revues": [r.lower() for r in pm._lignes(e["veterinaire_revues"])],
        "veterinaire_mesh": pm._lignes(e["veterinaire_mesh"]),
    }


def etiqueter(pub, regles):
    """`pub` : dict avec titre, resume, mots_cles_auteurs, mesh, revue (valeurs possiblement None)."""
    titre = pub.get("titre") or ""
    reste = " ".join([pub.get("resume") or "", *(pub.get("mots_cles_auteurs") or [])])
    mesh = pub.get("mesh")  # None = pas encore indexé
    mesh_min = {m.lower() for m in mesh or []}

    # 1) Produits suivis (molécules et marques), avec leur rôle
    produits = []
    for terme in regles["produits"]:
        role = _role(titre, terme)
        if role:
            produits.append({"produit": terme, "role": role, "statut_role": ROLE_SUGGERE})
        elif _motif(terme).search(reste):
            produits.append({"produit": terme, "role": "non déterminé",
                             "statut_role": "cité dans le résumé ou les mots-clés"})
    for terme in regles["produits_mesh"]:
        if terme.lower() in mesh_min:
            produits.append({"produit": terme, "role": "non déterminé", "statut_role": "indexation MeSH"})
    cites = {p["produit"].lower() for p in produits}

    # 2) Molécules HORS liste repérées dans le titre par leur suffixe de DCI
    connus = {t.lower() for t in regles["produits"]}
    suffixes = "|".join(re.escape(s) for s in regles["suffixes_dci"])
    hors_liste = []
    for mot in sorted({m.group(0) for m in re.finditer(rf"\b[A-Za-z][A-Za-z-]{{2,}}(?:{suffixes})\b", titre)}):
        if mot.lower() not in connus:
            hors_liste.append({"molecule": mot.lower(), "role": _role(titre, mot), "statut_role": ROLE_SUGGERE,
                               "reperage": "suffixe de DCI dans le titre, à vérifier"})

    # 3) Formulations / voies d'administration (étiquette séparée des produits)
    formulations = [t for t in regles["formulations"] if _motif(t).search(f"{titre} {reste}")]
    formulations += [t for t in regles["formulations_mesh"] if t.lower() in mesh_min]

    # 4) Stade (d'après l'indexation) et études vétérinaires
    revue = (pub.get("revue") or "").lower()
    veto_mesh = [t for t in regles["veterinaire_mesh"] if t.lower() in mesh_min]
    if revue in regles["veterinaire_revues"] or veto_mesh:
        stade = "Vétérinaire (animaux soignés) — hors veille principale"
        raison = f"revue vétérinaire ({pub.get('revue')})" if revue in regles["veterinaire_revues"] \
            else f"indexation MeSH : {', '.join(veto_mesh)}"
    elif any(t.lower() in mesh_min for t in regles["preclinique_mesh"]) or (
            regles["preclinique_animaux"] and "animals" in mesh_min and "humans" not in mesh_min):
        stade, raison = "Préclinique", "indexation MeSH de PubMed (modèle animal / animaux sans humains)"
    elif mesh is None:
        stade, raison = "Non renseigné", "pas d'indexation MeSH disponible"
    else:
        stade, raison = "Non renseigné", None

    return {
        "ciblee": bool(produits),
        # Plus précis que « ciblée » : un produit suivi est-il SUGGÉRÉ comme traitement étudié par le titre ?
        "produit_suivi_etudie_suggere": any(p["role"].startswith("étudié") for p in produits),
        "produits_suivis": produits or None,
        "molecules_hors_liste": hors_liste or None,
        "molecules_citees_ensemble": [f"{a} + {b}" for a, b in regles["associations"]
                                      if a in cites and b in cites] or None,
        "formulations_voies": formulations or None,
        "stade": stade,
        "stade_source": raison,
        "hors_veille_principale": stade.startswith("Vétérinaire"),
    }
