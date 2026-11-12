"""Outils communs aux sources « accès au marché » (BDPM, EMA, openFDA).

- charger_molecules() : lit config/marche.ini (molécules et associations suivies) ;
- cle_substance()     : ramène un nom de substance à une clé comparable entre sources
                        (« MALÉATE DE TIMOLOL », « Timolol maleate » → « timolol ») ;
- telecharger()       : télécharge un fichier public avec un cache local d'une journée.

Règle de la veille : on n'invente rien. Un médicament n'est rattaché à une molécule
que si ses substances actives déclarées par la source sont exactement celles de la ligne.
"""
import configparser
import re
import time
import unicodedata
from pathlib import Path

from veille import reseau

RACINE = Path(__file__).resolve().parents[1]
CONFIG = RACINE / "config" / "marche.ini"
CACHE = RACINE / "data" / "local" / "cache_marche"
DUREE_CACHE = 20 * 3600  # un fichier téléchargé sert pendant 20 h (une exécution par jour)
DELAI_MAX = 120
AGENT = "veille-glaucome/0.2 (outil de veille local, usage personnel)"

# Mots de sel ou de forme chimique retirés des noms de substance
SELS = {
    "maleate", "hydrochloride", "chlorhydrate", "tartrate", "mesilate", "mesylate", "dimesylate",
    "dimesilate", "hemihydrate", "monohydrate", "dihydrate", "sodium", "potassium", "base",
    "anhydre", "anhydrous", "isopropyl", "de", "d", "du",
    # espagnol, italien, latin (Suisse)
    "maleato", "tartrato", "hidrocloruro", "cloridrato", "mesilato", "dimesilato", "isopropilo",
    "maleas", "tartras", "hydrochloridum", "mesilas", "dimesilas", "ut", "di",
}
# Noms des substances dans les autres langues des sources (Espagne, Italie, Suisse en latin) → DCI anglaise
SYNONYMES = {
    "latanoprostum": "latanoprost", "bimatoprostum": "bimatoprost", "travoprostum": "travoprost",
    "tafluprostum": "tafluprost", "timololum": "timolol", "timololi": "timolol", "timololo": "timolol",
    "dorzolamidum": "dorzolamide", "dorzolamidi": "dorzolamide", "dorzolamida": "dorzolamide",
    "brinzolamidum": "brinzolamide", "brinzolamida": "brinzolamide",
    "brimonidinum": "brimonidine", "brimonidini": "brimonidine", "brimonidina": "brimonidine",
    "netarsudilum": "netarsudil", "netarsudili": "netarsudil",
    "latanoprostenum bunodum": "latanoprostene bunod", "latanoprosteno bunod": "latanoprostene bunod",
    "omidenepagum": "omidenepag",
}


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn")


def cle_substance(nom):
    """« MÉSYLATE DE NÉTARSUDIL » → « netarsudil » ; « latanoprostène bunod » → « latanoprostene bunod » ;
    « timololo » (italien), « dorzolamida » (espagnol), « latanoprostum » (latin) → la DCI anglaise."""
    nom = re.sub(r"\(.*?\)", " ", nom or "")  # « TIMOLOL (TIMOLOL MALEATE) » → « TIMOLOL »
    mots = re.sub(r"[^a-z0-9 ]", " ", sans_accents(nom).lower()).split()
    cle = " ".join(m for m in mots if m not in SELS)
    if cle in SYNONYMES:
        return SYNONYMES[cle]
    return " ".join(SYNONYMES.get(m, m) for m in cle.split())


def charger_molecules():
    """Liste de {nom, substances (ensemble de clés)} dans l'ordre de config/marche.ini."""
    config = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    config.optionxform = str  # garder les majuscules du nom affiché
    config.read(CONFIG, encoding="utf-8")
    molecules = []
    for nom, valeur in config["molecules"].items():
        substances = frozenset(cle_substance(s) for s in valeur.split("+") if s.strip())
        molecules.append({"nom": nom.strip(), "substances": substances})
    return molecules


def rattacher(substances, molecules):
    """La molécule suivie dont les substances sont exactement celles-ci (ou None)."""
    cles = frozenset(cle_substance(s) for s in substances if s)
    return next((m for m in molecules if m["substances"] == cles), None)


def telecharger(url, nom_fichier, suivi):
    """Contenu binaire d'un fichier public, depuis le cache s'il a moins de 20 h."""
    fichier = CACHE / nom_fichier
    if fichier.exists() and time.time() - fichier.stat().st_mtime < DUREE_CACHE:
        suivi["depuis_cache"] += 1
        return fichier.read_bytes()
    suivi["appels_reseau"] += 1
    reponse = reseau.requete("GET", url, nom_fichier, headers={"User-Agent": AGENT}, timeout=DELAI_MAX)
    CACHE.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(reponse.content)
    return reponse.content


def decoder(contenu):
    """Les fichiers publics n'ont pas tous le même encodage : UTF-8 d'abord, sinon Windows-1252."""
    try:
        return contenu.decode("utf-8")
    except UnicodeDecodeError:
        return contenu.decode("cp1252")


def date_iso(texte):
    """« 07/01/2021 » ou « 20210107 » → « 2021-01-07 » ; sinon None."""
    texte = (texte or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texte)
    if m:
        return f"{m[3]}-{m[2]}-{m[1]}"
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", texte)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$", texte)  # « 2023-10-03 » ou « 2023-10-03 00:00:00 »
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    return None
