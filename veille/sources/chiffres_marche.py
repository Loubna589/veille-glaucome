"""Chiffres de marché PUBLICS et gratuits des antiglaucomateux (aucune donnée sous licence, pas d'IQVIA ni de Xponent).

1. France : Open Medic (Assurance Maladie, licence ouverte). Médicaments délivrés en ville et remboursés, tous
   régimes, par année. Fichier annuel « base complète » (un zip d'environ 27 Mo). On garde la classe ATC S01E
   (antiglaucomateux et myotiques) : boîtes remboursées et montants remboursés par molécule ATC, par type
   (princeps, générique, hors répertoire des génériques), par spécialité du prescripteur et par produit.
2. États-Unis : Medicare Part D Spending by Drug (CMS, données publiques). Dépenses et nombre de prescriptions
   par médicament (marque ou générique), sur 5 ans.

Les deux sources ont environ un an de décalage : l'année N est publiée au cours de l'année N+1.
Aucune valeur n'est estimée : on additionne seulement ce que les fichiers déclarent.
"""
import csv
import io
import json
import re
import urllib.request
import zipfile
from collections import defaultdict

OPEN_MEDIC = "https://open-data-assurance-maladie.ameli.fr/medicaments/"
OPEN_MEDIC_PAGE = "https://www.data.gouv.fr/fr/datasets/open-medic-base-complete-sur-les-depenses-de-medicaments-interregimes/"
CMS_CATALOGUE = "https://data.cms.gov/data.json"
CMS_TITRE = "Medicare Part D Spending by Drug"
CMS_PAGE = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug"
CLASSE = "S01E"
PREMIERE_ANNEE = 2015

# Code TOP_GEN d'Open Medic : 4 = princeps (médicament de référence d'un groupe générique), 1 = générique,
# 0 = hors répertoire des génériques (aucun générique inscrit : nouveautés, unidoses sans conservateur…).
TYPES = {"4": "princeps", "1": "generiques", "0": "hors_repertoire"}
# Spécialité du prescripteur (PSP_SPE, nomenclature de l'Assurance Maladie)
PRESCRIPTEURS = {"15": "ophtalmologues", "1": "generalistes"}

# Substances antiglaucomateuses cherchées dans le fichier Medicare (le nom générique y est en anglais)
SUBSTANCES_US = re.compile(r"latanoprost|bimatoprost|travoprost|tafluprost|timolol|dorzolamide|brinzolamide|brimonidine|"
                           r"netarsudil|omidenepag|apraclonidine|betaxolol|carteolol|levobunolol", re.I)
# Même substance, autre usage que le glaucome : exclu
HORS_GLAUCOME_US = {"mirvaso"}   # brimonidine en gel pour la rosacée


def telecharger(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "veille-glaucome (projet etudiant)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def nombre(texte):
    """« 1 234,56 » ou « 1234.56 » → 1234.56 ; vide → 0."""
    t = (texte or "").replace("\xa0", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t) if t else 0.0
    except ValueError:
        return 0.0


def nom_produit(libelle):
    """« LATANOPROST VIATRIS 0,005% COLLYRE » → « LATANOPROST VIATRIS » (nom avant le premier dosage)."""
    m = re.match(r"\s*(.*?)(?=\s+\d|\s*\(|$)", libelle or "")
    return " ".join((m.group(1) if m else libelle or "").split()).upper() or "NON RAPPORTÉ"


def lien_open_medic(annee):
    """Lien du zip de l'année (la page de téléchargement donne un lien à jeton), ou None si l'année n'est pas publiée."""
    page = telecharger(OPEN_MEDIC + f"download.php?Dir_Rep=Open_MEDIC_Base_Complete&Annee={annee}", 120)
    liens = re.findall(r'href="\./(download_file\.php\?[^"]+\.zip)"', page.decode("utf-8", "replace"))
    return OPEN_MEDIC + liens[0].replace("&amp;", "&") if liens else None


def agreger_open_medic(lignes_csv, nb_produits=15):
    """Lignes du fichier (avec en-tête) → agrégats de la classe S01E pour une année."""
    lecteur = csv.reader(lignes_csv, delimiter=";")
    entete = [c.strip().upper() for c in next(lecteur)]
    i = {c: k for k, c in enumerate(entete)}
    for c in ("ATC4", "ATC5", "L_ATC5", "BOITES", "REM"):
        if c not in i:
            raise ValueError(f"Colonne {c} absente du fichier Open Medic : {entete}")
    mol = defaultdict(lambda: {"boites": 0.0, "rem": 0.0, "princeps": 0.0, "generiques": 0.0, "hors_repertoire": 0.0})
    presc, prod, libelles = defaultdict(float), defaultdict(lambda: [0.0, 0.0, ""]), {}
    for l in lecteur:
        if len(l) < len(entete) or not l[i["ATC4"]].startswith(CLASSE):
            continue
        atc, boites, rem = l[i["ATC5"]], nombre(l[i["BOITES"]]), nombre(l[i["REM"]])
        libelles[atc] = l[i["L_ATC5"]].strip()
        m = mol[atc]
        m["boites"] += boites
        m["rem"] += rem
        if "TOP_GEN" in i:
            m[TYPES.get(l[i["TOP_GEN"]].strip(), "hors_repertoire")] += boites
        if "PSP_SPE" in i:
            presc[PRESCRIPTEURS.get(l[i["PSP_SPE"]].strip().lstrip("0"), "autres")] += boites
        if "L_CIP13" in i:
            p = prod[nom_produit(l[i["L_CIP13"]])]
            p[0] += boites
            p[1] += rem
            p[2] = atc
    arrondi = {k: {c: round(v) for c, v in d.items()} | {"libelle": libelles[k]} for k, d in mol.items()}
    produits = sorted(prod.items(), key=lambda kv: -kv[1][0])[:nb_produits]
    return {
        "boites": round(sum(d["boites"] for d in mol.values())), "rem": round(sum(d["rem"] for d in mol.values())),
        "molecules": dict(sorted(arrondi.items(), key=lambda kv: -kv[1]["boites"])),
        "prescripteurs": {k: round(v) for k, v in presc.items()},
        "produits": [{"nom": n, "atc": v[2], "boites": round(v[0]), "rem": round(v[1])} for n, v in produits],
    }


def open_medic_annee(annee):
    lien = lien_open_medic(annee)
    if not lien:
        return None
    z = zipfile.ZipFile(io.BytesIO(telecharger(lien)))
    nom = next(n for n in z.namelist() if n.upper().endswith((".CSV", ".TXT")))
    with z.open(nom) as f:
        return agreger_open_medic(io.TextIOWrapper(f, "latin-1"))


def type_us(marque, generique):
    """Medicare écrit le nom générique comme « marque » quand le produit est un générique."""
    mots = re.findall(r"[a-z]{5,}", generique.lower())
    return "generique" if any(m in marque.lower() for m in mots) else "marque"


def medicare_lignes(texte_csv):
    lignes = []
    for x in csv.DictReader(io.StringIO(texte_csv)):
        if x.get("Mftr_Name") != "Overall" or not SUBSTANCES_US.search(x.get("Gnrc_Name") or ""):
            continue
        marque = (x.get("Brnd_Name") or "").strip()
        if marque.lower().rstrip("*") in HORS_GLAUCOME_US:
            continue
        annees = sorted({m.group(1) for k in x for m in [re.match(r"Tot_Spndng_(\d{4})$", k)] if m})
        lignes.append({
            "marque": marque.rstrip("*").strip(), "generique": (x.get("Gnrc_Name") or "").strip(),
            "type": type_us(marque, x.get("Gnrc_Name") or ""), "fabricants": int(nombre(x.get("Tot_Mftr"))),
            "depenses": {a: round(nombre(x.get(f"Tot_Spndng_{a}"))) for a in annees if x.get(f"Tot_Spndng_{a}")},
            "prescriptions": {a: round(nombre(x.get(f"Tot_Clms_{a}"))) for a in annees if x.get(f"Tot_Clms_{a}")},
        })
    return lignes


def medicare(deja=None):
    """Lignes Medicare des antiglaucomateux. Ne retélécharge que si CMS a publié une nouvelle version."""
    cat = json.loads(telecharger(CMS_CATALOGUE, 180))
    ds = next(d for d in cat["dataset"] if d.get("title") == CMS_TITRE)
    csv_url = next(x.get("downloadURL") for x in ds["distribution"] if (x.get("format") or "").upper() == "CSV")
    if deja and deja.get("fichier") == csv_url:
        return deja
    lignes = medicare_lignes(telecharger(csv_url).decode("utf-8", "replace"))
    annees = sorted({a for l in lignes for a in l["depenses"]})
    return {"source": "CMS — Medicare Part D Spending by Drug", "url": CMS_PAGE, "fichier": csv_url,
            "version": ds.get("modified"), "annees": annees, "lignes": lignes}
