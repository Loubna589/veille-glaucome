"""Accès au marché en France : Base de données publique des médicaments (BDPM).

Source officielle (ANSM, HAS, Assurance maladie), gratuite, sans clé :
https://base-donnees-publique.medicaments.gouv.fr — fichiers texte téléchargeables,
une ligne par enregistrement, colonnes séparées par des tabulations.

Fichiers utilisés :
- CIS_bdpm.txt          : spécialités (nom, voie, AMM, procédure, date d'AMM, titulaire) ;
- CIS_COMPO_bdpm.txt    : composition (substances actives) → rattachement aux molécules suivies ;
- CIS_CIP_bdpm.txt      : présentations (boîtes), taux de remboursement et prix ;
- CIS_HAS_SMR_bdpm.txt  : avis de la Commission de la transparence (HAS) — Service médical rendu ;
- CIS_HAS_ASMR_bdpm.txt : avis HAS — Amélioration du service médical rendu ;
- HAS_LiensPageCT_bdpm.txt : lien vers la page de chaque avis sur has-sante.fr.

Règle de la veille : on ne garde que ce que la base déclare. Une information absente
vaut None et s'affiche « non renseigné ». Une molécule sans spécialité dans la base
n'est PAS déclarée « non autorisée » : elle est « absente de la BDPM ».
"""
import re
import time

from veille import marche_commun as mc

BASE = "https://base-donnees-publique.medicaments.gouv.fr/download/file/"
SITE_FICHE = "https://base-donnees-publique.medicaments.gouv.fr/medicament/{cis}/extrait"
FICHIERS = ["CIS_bdpm.txt", "CIS_COMPO_bdpm.txt", "CIS_CIP_bdpm.txt",
            "CIS_HAS_SMR_bdpm.txt", "CIS_HAS_ASMR_bdpm.txt", "HAS_LiensPageCT_bdpm.txt"]
suivi = {"appels_reseau": 0, "depuis_cache": 0}


def lignes(nom_fichier):
    texte = mc.decoder(mc.telecharger(BASE + nom_fichier, nom_fichier, suivi))
    return [l.split("\t") for l in texte.splitlines() if l.strip()]


def col(ligne, i):
    """Valeur nettoyée de la colonne i (None si vide ou absente)."""
    v = ligne[i].strip() if i < len(ligne) else ""
    return v or None


def nombre(texte):
    """« 1 234,56 » → 1234.56 (None si vide)."""
    if not texte:
        return None
    try:
        return float(texte.replace("\xa0", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def taux(texte):
    """« 65% » et « 65 % » sont la même valeur écrite de deux façons dans la base : on unifie."""
    return re.sub(r"\s*%", " %", texte) if texte else None


def sans_balises(texte):
    return " ".join(re.sub(r"<[^>]+>", " ", texte or "").split()) or None


def substances_par_cis(compo):
    """CIS → liste des substances actives. Pour chaque composant (numéro de liaison),
    la « fraction thérapeutique » (FT) est préférée au sel déclaré comme substance (SA)."""
    par_cis = {}
    for l in compo:
        cis, nom, nature, liaison = col(l, 0), col(l, 3), col(l, 6), col(l, 7)
        if not cis or not nom:
            continue
        composants = par_cis.setdefault(cis, {})
        if nature == "FT" or liaison not in composants:
            composants[liaison or nom] = nom
    return {cis: list(c.values()) for cis, c in par_cis.items()}


def avis_par_cis(lignes_avis, liens):
    par_cis = {}
    for l in lignes_avis:
        cis, code = col(l, 0), col(l, 1)
        if not cis:
            continue
        par_cis.setdefault(cis, []).append({
            "code_dossier": code, "motif": col(l, 2), "date": mc.date_iso(col(l, 3)),
            "valeur": col(l, 4), "libelle": sans_balises(col(l, 5)), "lien": liens.get(code),
        })
    for avis in par_cis.values():
        avis.sort(key=lambda a: a["date"] or "", reverse=True)  # le plus récent d'abord
    return par_cis


def collecter(molecules):
    """Spécialités ophtalmiques de la BDPM rattachées aux molécules suivies.

    Renvoie {nom de molécule: [spécialités]} et les informations sur la source."""
    specialites = lignes("CIS_bdpm.txt")
    substances = substances_par_cis(lignes("CIS_COMPO_bdpm.txt"))
    presentations = {}
    for l in lignes("CIS_CIP_bdpm.txt"):
        presentations.setdefault(col(l, 0), []).append({
            "cip13": col(l, 6), "libelle": col(l, 2), "statut": col(l, 3), "commercialisation": col(l, 4),
            "date_commercialisation": mc.date_iso(col(l, 5)), "taux_remboursement": taux(col(l, 8)),
            "prix_hors_honoraire": nombre(col(l, 9)), "prix": nombre(col(l, 10)),
            "honoraire": nombre(col(l, 11)),
        })
    liens = {col(l, 0): col(l, 1) for l in lignes("HAS_LiensPageCT_bdpm.txt")}
    smr = avis_par_cis(lignes("CIS_HAS_SMR_bdpm.txt"), liens)
    asmr = avis_par_cis(lignes("CIS_HAS_ASMR_bdpm.txt"), liens)

    resultat = {m["nom"]: [] for m in molecules}
    for l in specialites:
        cis, voies = col(l, 0), (col(l, 3) or "").lower()
        if not cis or "ophtalmique" not in voies:
            continue
        molecule = mc.rattacher(substances.get(cis, []), molecules)
        if not molecule:
            continue
        resultat[molecule["nom"]].append({
            "cis": cis, "nom": col(l, 1), "forme": col(l, 2), "statut_amm": col(l, 4),
            "procedure": col(l, 5), "commercialisation": col(l, 6), "date_amm": mc.date_iso(col(l, 7)),
            "numero_ue": col(l, 9), "titulaire": col(l, 10), "substances": substances.get(cis, []),
            "presentations": presentations.get(cis, []), "smr": smr.get(cis, []), "asmr": asmr.get(cis, []),
            "lien": SITE_FICHE.format(cis=cis),
        })
    for liste in resultat.values():
        liste.sort(key=lambda s: s["nom"] or "")
    source = {"nom": "BDPM (ANSM · HAS · Assurance maladie)", "url": "https://base-donnees-publique.medicaments.gouv.fr",
              "telecharge_le": time.strftime("%Y-%m-%d"), "fichiers": FICHIERS}
    return resultat, source
