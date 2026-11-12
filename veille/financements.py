"""Financements d'une publication, chacun avec la notice qui le justifie.

Sources combinées : notice PubMed (GrantList), OpenAlex (financeurs repérés) et
Crossref (déclaration de l'éditeur, qui sert de justification).
Les financements restent toujours séparés des affiliations des auteurs.
"""
import requests

from veille.sources import crossref


def justifier_financements(article, o):
    """Rassemble les financeurs (PubMed, OpenAlex, Crossref) avec leur justification.

    - déclaré dans la notice PubMed (GrantList)                 → CONFIRMÉ (source : PubMed)
    - trouvé par OpenAlex ET déclaré par l'éditeur dans Crossref → CONFIRMÉ (source : Crossref)
    - trouvé par OpenAlex seulement                              → À VÉRIFIER (OpenAlex ne dit pas d'où il le tient)
    - déclaré dans Crossref mais absent d'OpenAlex               → CONFIRMÉ (source : Crossref)
    """
    resultat = []
    notice_openalex = ("notice OpenAlex", f"https://api.openalex.org/works/{o['openalex_id']}")
    notice_pubmed = ("notice PubMed", f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/?format=pubmed")
    affiliations = [i["nom"] for i in o["institutions"] or []]

    for f in article["financeurs_declares"] or []:
        resultat.append({"nom": f["organisme"], "statut": "CONFIRMÉ — déclaré dans la notice PubMed (GrantList)",
                         "references": [f["reference"]] if f["reference"] else None,
                         "notices": [notice_pubmed], "note": None})

    doi = o["doi"] or article["doi"]
    try:
        declares = crossref.financeurs(doi) if doi else None
    except requests.exceptions.RequestException as erreur:
        declares = None
        print(f"    [Crossref] vérification impossible : {erreur}")
    notice_crossref = ("notice justificative Crossref (déclaration de l'éditeur)", crossref.notice(doi)) if doi else None

    for f in o["financeurs"] or []:
        if any(crossref.meme_nom(f["nom"], r["nom"]) for r in resultat):
            continue
        refs = [s["reference"] for s in o["subventions"] or [] if crossref.meme_nom(s["financeur"], f["nom"]) and s["reference"]]
        correspondant = next((d for d in declares or [] if crossref.meme_nom(d["nom"], f["nom"])), None)
        if correspondant:
            statut = "CONFIRMÉ — déclaré par l'éditeur dans Crossref"
            refs = refs or correspondant["references"]
            notices = [notice_crossref, notice_openalex]
        else:
            raison = ("l'éditeur n'a déclaré aucun financeur dans Crossref" if declares == []
                      else "absent de la déclaration de l'éditeur dans Crossref" if declares
                      else "déclaration Crossref indisponible")
            statut = f"À VÉRIFIER — trouvé par OpenAlex seulement ({raison}) ; à contrôler dans le texte de l'article"
            notices = [notice_openalex] + (
                [("notice Crossref consultée (ne confirme pas ce financeur)", crossref.notice(doi))] if doi else [])
        note = None
        if any(crossref.meme_nom(f["nom"], nom) or f["nom"].lower() in nom.lower() for nom in affiliations):
            note = "cet organisme figure AUSSI parmi les institutions des auteurs : c'est une affiliation, information distincte"
        resultat.append({"nom": f["nom"], "statut": statut, "references": refs or None,
                         "notices": notices, "note": note})

    for d in declares or []:
        if not any(crossref.meme_nom(d["nom"], r["nom"]) for r in resultat):
            resultat.append({"nom": d["nom"], "statut": "CONFIRMÉ — déclaré par l'éditeur dans Crossref (absent d'OpenAlex)",
                             "references": d["references"], "notices": [notice_crossref], "note": None})
    return resultat
