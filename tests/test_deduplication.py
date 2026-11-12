"""Déduplication des publications entre sources (PMID, DOI, OpenAlex) et des événements."""
from veille import base


def test_meme_pmid_enregistre_une_seule_fois(conn):
    a = {"pmid": "123", "doi": "10.1/ABC", "titre": "Article A"}
    assert base.enregistrer_article(conn, a, "2026-11-01", "pubmed", "pubmed")[0] == "nouveau"
    assert base.enregistrer_article(conn, a, "2026-11-02", "pubmed", "pubmed")[0] == "deja_connu"
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1


def test_meme_doi_vu_par_openalex_puis_pubmed_fusionne(conn):
    oa = {"openalex_id": "W1", "doi": "10.1/abc", "titre": "Article vu par OpenAlex"}
    pm = {"pmid": "123", "doi": "10.1/ABC", "titre": "Article vu par PubMed", "date_entree_pubmed": "2026-11-02"}
    etat1, id1 = base.enregistrer_article(conn, oa, "2026-11-01", "openalex", "openalex")
    etat2, id2 = base.enregistrer_article(conn, pm, "2026-11-02", "pubmed", "pubmed")
    assert (etat1, etat2) == ("nouveau", "deja_connu") and id1 == id2
    ligne = conn.execute("SELECT * FROM articles").fetchone()
    # une seule ligne, qui porte les trois identifiants ; PubMed devient la notice de référence
    assert (ligne["pmid"], ligne["doi"], ligne["openalex_id"], ligne["origine"]) == ("123", "10.1/abc", "W1", "pubmed")
    sources = {r["source"] for r in conn.execute("SELECT source FROM articles_sources")}
    assert sources == {"openalex", "pubmed"}


def test_doi_compare_sans_tenir_compte_des_majuscules(conn):
    base.enregistrer_article(conn, {"openalex_id": "W1", "doi": "10.1/AbC", "titre": "x"}, "2026-11-01", "openalex", "openalex")
    assert base.trouver_article(conn, doi="10.1/ABC") is not None


def test_evenement_jamais_cree_deux_fois(conn):
    assert base.ajouter_evenement(conn, "changement_statut", "essai", "NCT1", "2026-11-01", champ="statut",
                                  avant="RECRUITING", apres="COMPLETED") is True
    assert base.ajouter_evenement(conn, "changement_statut", "essai", "NCT1", "2026-11-05", champ="statut",
                                  avant="RECRUITING", apres="COMPLETED") is False
    assert conn.execute("SELECT COUNT(*) FROM evenements").fetchone()[0] == 1
