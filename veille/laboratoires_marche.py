"""Laboratoire (titulaire de l'autorisation ou demandeur) de chaque produit de la page « Autorisations & remboursement ».

Règles :
- le nom vient UNIQUEMENT du champ déclaré par la source du produit (tableau CHAMPS) : jamais déduit d'une autre
  source ni d'un rachat. S'il manque : « non déclaré par la source » ;
- pour regrouper (filtre, comptages), le nom est normalisé : formes juridiques (Oy, SAS, GmbH, S.p.A.…), pays entre
  parenthèses ou en fin de nom, mots génériques (Pharma, Laboratoires, Farmaceutica…) retirés.
  Exemple : « Santen Oy », « SANTEN ITALY Srl », « Santen SA » → « Santen ». Le nom exact reste affiché au survol ;
- regroupement « par préfixe » : « Teva Parenteral » rejoint « Teva » seulement si « Teva » existe déjà tel quel ;
- regroupements manuels possibles dans config/laboratoires.ini, rubrique [alias].
"""
import configparser
import re
import unicodedata
from pathlib import Path

NON_DECLARE = "non déclaré par la source"

# zone du fichier marche.json → (champ du produit, champ d'origine dans la source)
CHAMPS = {
    "france": ("titulaire", "BDPM — titulaire"),
    "ue": ("titulaire", "EMA — marketing authorisation holder"),
    "usa": ("sponsor", "openFDA — sponsor_name"),
    "canada": ("titulaire", "Santé Canada DPD — company"),
    "espagne": ("titulaire", "AEMPS CIMA — labtitular"),
    "italie": ("titulaire", "AIFA — Titolare AIC (ditta)"),
    "suisse": ("titulaire", "Swissmedic — Zulassungsinhaberin"),
    "australie": ("titulaire", "PBS — fabricant déclaré"),
}

JURIDIQUE = {"inc", "incorporated", "ltd", "limited", "limitee", "ulc", "co", "kg", "gmbh", "ag", "sa", "sas", "sasu",
             "sarl", "sau", "sl", "slu", "srl", "spa", "ab", "oy", "bv", "nv", "eeig", "llc", "plc", "corp",
             "corporation", "company", "kk", "as", "aps", "pty", "lda", "of"}
GENERIQUES = {"pharma", "pharmaceutical", "pharmaceuticals", "pharms", "pharm", "farma", "farmaceutica",
              "farmaceutici", "farmaceuticos", "healthcare", "sante", "therap", "theraps", "therapeutics",
              "generiques", "genericos", "generici", "europharm", "division"}
# retirés seulement en tête de nom (« Laboratoires Théa » → « Théa ») : « Upsher Smith Labs » garde « Labs »
EN_TETE = {"laboratoires", "laboratoire", "laboratorios", "laboratorio", "labo", "laboratori"}
PAYS = {"france", "canada", "italy", "italia", "spain", "espana", "ireland", "irlande", "schweiz", "suisse",
        "switzerland", "deutschland", "germany", "allemagne", "uk", "us", "usa", "india", "iberia", "europe",
        "japan", "nederland", "netherlands"}
CONFIG = Path(__file__).resolve().parents[1] / "config" / "laboratoires.ini"


def _sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def cle(nom):
    """Clé de regroupement : minuscules, sans accents, sans forme juridique, pays ni mot générique."""
    if not nom or not str(nom).strip():
        return None
    t = _sans_accents(re.sub(r"\(.*?\)", " ", str(nom))).lower()
    t = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", t)          # s.p.a. → spa, s.a.u. → sau
    t = re.sub(r"\b([a-z])\.([a-z])\b\.?", r"\1\2", t)       # s.a / b.v. → sa / bv
    mots = re.sub(r"[^a-z0-9]+", " ", t.replace("&", " ").replace("+", " ")).split()
    mots = [m for m in mots if m != "and"]
    while mots and mots[0] in EN_TETE:
        mots = mots[1:]
    utiles = [m for m in mots if m not in JURIDIQUE and m not in GENERIQUES and m not in PAYS]
    if not utiles or all(m.isdigit() for m in utiles):    # « Farma 1000 » : on garde le nom sans forme juridique
        utiles = [m for m in mots if m not in JURIDIQUE] or mots
    return " ".join(utiles) or None


def libelle(c):
    return " ".join(m.upper() if len(m) <= 2 and m != "dr" else m.capitalize() for m in c.split())


def charger_alias(chemin=CONFIG):
    config = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    config.optionxform = str
    config.read(chemin, encoding="utf-8")
    alias = {}
    if config.has_section("alias"):
        for nom, variantes in config["alias"].items():
            for v in [nom, *variantes.split("|")]:
                if cle(v):
                    alias[cle(v)] = nom.strip()
    return alias


def regrouper(noms, alias=None):
    """{nom exact: nom du groupe} pour une liste de noms déclarés."""
    alias = alias or {}
    cles = {n: cle(n) for n in noms if cle(n)}
    existantes = set(cles.values())

    def racine(c):
        if c in alias:
            return c
        mots = c.split()
        for i in range(1, len(mots)):        # le plus court préfixe qui existe déjà comme nom complet
            p = " ".join(mots[:i])
            if p in existantes and len(p) >= 2:
                return p
        return c
    return {n: alias.get(racine(c)) or alias.get(c) or libelle(racine(c)) for n, c in cles.items()}


def enrichir(marche, alias=None):
    """Ajoute à chaque produit `laboratoire` = {declare, groupe, champ} et à `marche` la liste `laboratoires`."""
    if not marche:
        return marche
    alias = charger_alias() if alias is None else alias
    molecules = marche.get("molecules") or {}
    noms = {(x.get(champ) or "").strip() for m in molecules.values() for zone, (champ, _) in CHAMPS.items()
            for x in m.get(zone) or [] if (x.get(champ) or "").strip()}
    groupes = regrouper(sorted(noms), alias)
    synthese = {}
    for nom_mol, m in molecules.items():
        for zone, (champ, origine) in CHAMPS.items():
            for x in m.get(zone) or []:
                declare = (x.get(champ) or "").strip() or None
                groupe = groupes.get(declare) if declare else None
                x["laboratoire"] = {"declare": declare, "groupe": groupe, "champ": origine}
                if groupe:
                    g = synthese.setdefault(groupe, {"groupe": groupe, "variantes": set(), "produits": 0,
                                                     "molecules": set(), "zones": set()})
                    g["variantes"].add(declare)
                    g["produits"] += 1
                    g["molecules"].add(nom_mol)
                    g["zones"].add(zone)
    marche["laboratoires"] = sorted(
        ({**g, "variantes": sorted(g["variantes"]), "molecules": sorted(g["molecules"]), "zones": sorted(g["zones"])}
         for g in synthese.values()), key=lambda g: (-g["produits"], g["groupe"]))
    return marche
