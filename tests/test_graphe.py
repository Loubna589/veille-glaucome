"""Construction du graphe : uniquement des liens déclarés par les sources."""
from conftest import essai
from veille import base, graphe


def test_liens_issus_des_donnees(conn):
    base.enregistrer_essai(conn, essai("NCT00000001", promoteur="Santen", type_promoteur="INDUSTRY",
                                       collaborateurs=["Université X"],
                                       interventions=[{"type": "DRUG", "nom": "Netarsudil 0.02% ophthalmic solution"}]), "2026-11-01")
    base.enregistrer_essai(conn, essai("NCT00000002", promoteur="Santen",
                                       interventions=[{"type": "DRUG", "nom": "netarsudil"}]), "2026-11-01")
    base.enregistrer_article(conn, {"pmid": "111", "titre": "Article", "nct_declares": ["NCT00000001"]}, "2026-11-01",
                             "pubmed", "pubmed", {"financements": [{"nom": "NEI", "statut": "CONFIRMÉ (PubMed)"},
                                                                   {"nom": "Labo douteux", "statut": "à vérifier"}]})
    g = graphe.construire(conn)
    types = {(l["source"], l["target"], l["type"]) for l in g["liens"]}
    assert ("NCT00000001", "org:santen", "promoteur") in types
    assert ("NCT00000002", "org:santen", "promoteur") in types             # même organisme : un seul nœud
    assert ("NCT00000001", "org:université x", "collaborateur") in types
    assert ("pmid:111", "NCT00000001", "cite_essai") in types
    assert ("pmid:111", "org:nei", "financeur") in types
    assert not any("douteux" in l["target"] for l in g["liens"])         # financeur non confirmé : pas de lien
    # « Netarsudil 0.02% ophthalmic solution » et « netarsudil » = le même traitement
    traitements = [n for n in g["noeuds"] if n["type"] == "traitement"]
    assert len(traitements) == 1 and traitements[0]["degre"] == 2


def test_aucun_lien_vers_un_noeud_absent(conn):
    base.enregistrer_essai(conn, essai("NCT00000001", publications_declarees=[{"pmid": "999", "type": "RESULT"}]), "2026-11-01")
    g = graphe.construire(conn)
    ids = {n["id"] for n in g["noeuds"]}
    assert all(l["source"] in ids and l["target"] in ids for l in g["liens"])


def test_article_qui_cite_un_essai_hors_base(conn):
    base.enregistrer_article(conn, {"pmid": "222", "titre": "A", "nct_declares": ["NCT09999999"]}, "2026-11-01", "pubmed", "pubmed")
    g = graphe.construire(conn)
    hors_base = [n for n in g["noeuds"] if n["id"] == "NCT09999999"]
    assert hors_base and hors_base[0]["hors_base"] is True
    assert graphe.statistiques(g)["liens_par_type"] == {"cite_essai": 1}
