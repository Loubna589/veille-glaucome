"""Contrôle quotidien des rétractations et erratums pour TOUS les articles PubMed déjà connus.

La collecte ne recharge jamais un article déjà en base : un article rétracté APRÈS sa collecte passerait inaperçu.
Ce contrôle redemande à PubMed la notice de chaque PMID connu (par lots de 200, soit 3 requêtes pour ~430 articles)
et met à jour SEULEMENT les 4 champs retracte / avis_retractation / erratum / avis_erratum. Rien d'autre n'est modifié.
"""
import json

from veille.sources import pubmed

CHAMPS = ("retracte", "avis_retractation", "erratum", "avis_erratum")
LOT = 200


def verifier(conn, telecharger=pubmed.telecharger):
    lignes = {str(p): (i, d) for i, p, d in conn.execute(
        "SELECT id, pmid, donnees FROM articles WHERE origine = 'pubmed' AND pmid IS NOT NULL ORDER BY id")}
    pmids = list(lignes)
    bilan = {"verifies": 0, "mis_a_jour": 0, "retractes": [], "erratums": []}
    for debut in range(0, len(pmids), LOT):
        for notice in telecharger(pmids[debut:debut + LOT]):
            n = pubmed.normaliser(notice)
            if n["pmid"] not in lignes:
                continue
            ident, brut = lignes[n["pmid"]]
            d = json.loads(brut)
            bilan["verifies"] += 1
            if n["retracte"]:
                bilan["retractes"].append(n["pmid"])
            if n["erratum"]:
                bilan["erratums"].append(n["pmid"])
            if any(d.get(c, "absent") != n[c] for c in CHAMPS):
                d.update({c: n[c] for c in CHAMPS})
                conn.execute("UPDATE articles SET donnees = ? WHERE id = ?", (json.dumps(d, ensure_ascii=False), ident))
                bilan["mis_a_jour"] += 1
    conn.commit()
    return bilan
