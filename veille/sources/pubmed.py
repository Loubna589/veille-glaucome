"""Récupération des articles PubMed (API E-utilities du NCBI, gratuite).

- construire_requetes() : lit config/recherches_pubmed.ini et fabrique les deux recherches ;
- rechercher()          : renvoie des PMID correspondant à une recherche ;
- telecharger()         : récupère la notice complète (XML) de chaque PMID ;
- normaliser()          : garde les champs utiles à la veille.

Règles de la veille :
- « financeur déclaré » = subventions listées par PubMed (GrantList). Ce n'est ni
  l'affiliation des auteurs, ni le promoteur d'un essai ;
- un numéro NCT n'est « déclaré » que s'il figure dans la métadonnée officielle
  DataBankList (liens vers les registres) ; un NCT seulement présent dans le texte
  est rangé à part (« mentionné dans le texte »).
"""
import configparser
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from veille import reseau

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DELAI_MAX = 30
TENTATIVES = 3
CONFIG = Path(__file__).resolve().parents[2] / "config" / "recherches_pubmed.ini"
MOTIF_NCT = re.compile(r"\bNCT\d{8}\b")

_dernier_appel = 0.0


def _appeler(service, params):
    """Appel au NCBI en respectant sa limite (3 requêtes/s sans clé, 10 avec)."""
    global _dernier_appel
    params = {"db": "pubmed", "tool": "veille-glaucome", **params}
    if os.getenv("CONTACT_EMAIL"):
        params["email"] = os.getenv("CONTACT_EMAIL")
    if os.getenv("NCBI_API_KEY"):
        params["api_key"] = os.getenv("NCBI_API_KEY")
    pause = 0.11 if os.getenv("NCBI_API_KEY") else 0.35
    attente = _dernier_appel + pause - time.monotonic()
    if attente > 0:
        time.sleep(attente)
    # POST : accepte les longues requêtes (listes de PMID, recherches détaillées).
    # Tentatives, backoff et 429 : gérés par le module commun veille/reseau.py
    try:
        return reseau.requete("POST", f"{BASE}/{service}", "PubMed", data=params, timeout=DELAI_MAX,
                              tentatives=TENTATIVES + 1)
    finally:
        _dernier_appel = time.monotonic()


# ------------------------------------------------------------ configuration

def _lignes(texte):
    return [l.strip() for l in texte.splitlines() if l.strip() and not l.strip().startswith("#")]


def lire_config(chemin=CONFIG):
    config = configparser.ConfigParser(interpolation=None, comment_prefixes=("#", ";"),
                                       inline_comment_prefixes=None)
    config.read(chemin, encoding="utf-8")
    return config


def construire_requetes(chemin=CONFIG):
    """Renvoie {"large": requête, "ciblee": requête, "associations": [(mol1, mol2), ...]}."""
    config = lire_config(chemin)

    termes_large = _lignes(config["large"]["indexation"]) + _lignes(config["large"]["texte"])
    large = "(" + " OR ".join(termes_large) + ")"
    exclusions = _lignes(config["large"].get("exclusions", ""))
    if exclusions:
        large = f"({large} NOT (" + " OR ".join(exclusions) + "))"

    termes_cibles = []
    for rubrique in ("molecules", "marques"):  # les formulations sont une étiquette à part
        termes_cibles += _lignes(config["ciblee"].get(rubrique, ""))
    ciblee = f"{large} AND (" + " OR ".join(termes_cibles) + ")"

    associations = [
        tuple(m.strip().lower() for m in ligne.split("+"))
        for ligne in _lignes(config["ciblee"].get("associations_fixes", ""))
    ]
    return {"large": large, "ciblee": ciblee, "associations": associations}


# ------------------------------------------------------------ recherche

def compter(requete):
    return int(_appeler("esearch.fcgi", {"term": requete, "retmode": "json", "retmax": 0})
               .json()["esearchresult"]["count"])


def rechercher(requete, max_resultats=10, tri="relevance", jours=None):
    """Renvoie une liste de PMID. `jours` limite aux articles entrés dans PubMed récemment."""
    params = {"term": requete, "retmode": "json", "retmax": max_resultats, "sort": tri}
    if jours:
        params.update({"datetype": "edat", "reldate": jours})
    return _appeler("esearch.fcgi", params).json()["esearchresult"]["idlist"]


def filtrer(requete, pmids):
    """Parmi `pmids`, renvoie ceux qui correspondent aussi à `requete`."""
    if not pmids:
        return set()
    liste = " OR ".join(f"{p}[uid]" for p in pmids)
    return set(rechercher(f"({requete}) AND ({liste})", max_resultats=len(pmids)))


def telecharger(pmids):
    """Renvoie les notices XML complètes (une par PMID)."""
    if not pmids:
        return []
    xml = _appeler("efetch.fcgi", {"id": ",".join(pmids), "retmode": "xml"}).content
    return ET.fromstring(xml).findall("PubmedArticle")


# ------------------------------------------------------------ lecture d'une notice

def _texte(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else None


def _date(element):
    if element is None:
        return None
    morceaux = [element.findtext(c) for c in ("Year", "Month", "Day")]
    morceaux = [m for m in morceaux if m]
    if len(morceaux) >= 2 and morceaux[1].isdigit():
        morceaux[1] = morceaux[1].zfill(2)
    if len(morceaux) == 3:
        morceaux[2] = morceaux[2].zfill(2)
    return "-".join(morceaux) or None


def normaliser(notice):
    citation = notice.find("MedlineCitation")
    article = citation.find("Article")
    pmid = citation.findtext("PMID")

    # Résumé : plusieurs paragraphes possibles, parfois étiquetés (METHODS, RESULTS…)
    paragraphes = []
    for bloc in article.findall("Abstract/AbstractText"):
        texte = _texte(bloc)
        if texte:
            etiquette = bloc.get("Label")
            paragraphes.append(f"{etiquette}: {texte}" if etiquette else texte)
    resume = "\n".join(paragraphes) or None

    doi = notice.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='doi']") \
        or article.findtext("ELocationID[@EIdType='doi']")

    # Affiliations des auteurs (sans doublons, dans l'ordre d'apparition)
    affiliations = []
    for aff in article.findall("AuthorList/Author/AffiliationInfo/Affiliation"):
        texte = _texte(aff)
        if texte and texte not in affiliations:
            affiliations.append(texte)

    financeurs = [
        {
            "organisme": g.findtext("Agency"),
            "pays": g.findtext("Country"),
            "reference": g.findtext("GrantID"),
        }
        for g in article.findall("GrantList/Grant")
    ]

    # NCT déclarés dans la métadonnée officielle DataBankList
    nct_declares = [
        num.text.strip()
        for banque in article.findall("DataBankList/DataBank")
        if (banque.findtext("DataBankName") or "").lower() == "clinicaltrials.gov"
        for num in banque.findall("AccessionNumberList/AccessionNumber")
        if num.text
    ]
    titre = _texte(article.find("ArticleTitle"))
    nct_texte = sorted(set(MOTIF_NCT.findall(f"{titre or ''} {resume or ''}")) - set(nct_declares))

    return {
        "pmid": pmid,
        "titre": titre,
        "lien": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "doi": doi,
        "pmcid": notice.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='pmc']"),
        "revue": article.findtext("Journal/Title"),
        "date_entree_pubmed": _date(notice.find("PubmedData/History/PubMedPubDate[@PubStatus='entrez']")),
        "date_publication": _date(article.find("Journal/JournalIssue/PubDate"))
                            or article.findtext("Journal/JournalIssue/PubDate/MedlineDate"),
        "types_publication": [_texte(t) for t in article.findall("PublicationTypeList/PublicationType")] or None,
        "resume_present": resume is not None,
        "resume": resume,
        # Mots-clés choisis par les auteurs : PubMed les inclut dans les recherches [tiab]
        "mots_cles_auteurs": [_texte(k) for k in citation.findall("KeywordList/Keyword") if _texte(k)] or None,
        "langue": article.findtext("Language"),
        "nombre_auteurs": len(article.findall("AuthorList/Author")),
        "affiliations_auteurs": affiliations or None,
        "financeurs_declares": financeurs or None,
        "nct_declares": nct_declares or None,
        "nct_mentionnes_texte": nct_texte or None,
        "mesh": [_texte(m) for m in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")] or None,
    }
