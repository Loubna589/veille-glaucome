"""Articles rétractés et erratums : repérés dans la notice PubMed et signalés sur la fiche article."""
import xml.etree.ElementTree as ET

from veille import fiches
from veille.sources import pubmed


def notice(types=("Journal Article",), liens=(), pmid="9500320", titre="Titre"):
    """Notice PubMed réduite aux champs utiles (même structure XML que efetch)."""
    t = "".join(f"<PublicationType>{x}</PublicationType>" for x in types)
    c = "".join(f'<CommentsCorrections RefType="{r}"><RefSource>Avis</RefSource><PMID Version="1">{p}</PMID></CommentsCorrections>'
                for r, p in liens)
    return ET.fromstring(f"""<PubmedArticle><MedlineCitation><PMID Version="1">{pmid}</PMID>
      <Article><Journal><Title>Lancet</Title><JournalIssue><PubDate><Year>1998</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>{titre}</ArticleTitle><PublicationTypeList>{t}</PublicationTypeList></Article>
      <CommentsCorrectionsList>{c}</CommentsCorrectionsList></MedlineCitation>
      <PubmedData><ArticleIdList/></PubmedData></PubmedArticle>""")


def test_article_wakefield_retracte():
    # PMID 9500320 (Lancet 1998) : PubMed indique le type « Retracted Publication » et un lien « RetractionIn »
    d = pubmed.normaliser(notice(("Journal Article", "Retracted Publication"), [("RetractionIn", "20137807")]))
    assert d["retracte"] is True and d["avis_retractation"] == ["20137807"]
    assert d["erratum"] is False and d["avis_erratum"] is None


def test_lien_de_retractation_seul_suffit():
    assert pubmed.normaliser(notice(liens=[("RetractionIn", "1")]))["retracte"] is True


def test_type_seul_suffit():
    assert pubmed.normaliser(notice(("Retracted Publication",)))["retracte"] is True


def test_erratum_repere_par_le_lien_erratumin():
    d = pubmed.normaliser(notice(liens=[("ErratumIn", "555")]))
    assert d["erratum"] is True and d["avis_erratum"] == ["555"] and d["retracte"] is False


def test_avis_d_erratum_et_avis_de_retractation_ne_sont_pas_marques():
    erratum = pubmed.normaliser(notice(("Published Erratum",), [("ErratumFor", "9")]))
    avis = pubmed.normaliser(notice(("Retraction of Publication",), [("RetractionOf", "9500320")]))
    assert not erratum["erratum"] and not erratum["retracte"]
    assert not avis["retracte"] and not avis["erratum"]


def test_simple_commentaire_ne_declenche_rien():
    d = pubmed.normaliser(notice(liens=[("CommentIn", "7"), ("Cites", "8")]))
    assert d["retracte"] is False and d["erratum"] is False


def test_badges_de_la_fiche():
    alerte, ligne = fiches.signalement_html({"retracte": True, "avis_retractation": ["20137807"], "erratum": False})
    assert "Article rétracté" in alerte and "pubmed.ncbi.nlm.nih.gov/20137807/" in alerte and ligne == "article rétracté"
    alerte, ligne = fiches.signalement_html({"retracte": False, "erratum": False})
    assert alerte == "" and ligne == "aucun signalé par PubMed"


def test_article_collecte_avant_le_controle_est_non_verifie():
    alerte, ligne = fiches.signalement_html({"pmid": "1"})
    assert alerte == "" and "non vérifié" in ligne


def test_controle_des_articles_deja_connus(conn):
    import json
    from veille import retractations
    for pmid in ("1", "2"):
        conn.execute("INSERT INTO articles (pmid, origine, titre, donnees, premiere_detection, derniere_maj) "
                     "VALUES (?, 'pubmed', 'T', ?, '2026-11-01', '2026-11-01')", (pmid, json.dumps({"pmid": pmid, "titre": "T"})))
    faux = lambda pmids: [notice(("Retracted Publication",), [("RetractionIn", "99")], pmid="1"), notice(pmid="2")]
    b = retractations.verifier(conn, telecharger=faux)
    assert b["verifies"] == 2 and b["mis_a_jour"] == 2 and b["retractes"] == ["1"]
    d1 = json.loads(conn.execute("SELECT donnees FROM articles WHERE pmid = '1'").fetchone()[0])
    assert d1["retracte"] is True and d1["avis_retractation"] == ["99"] and d1["titre"] == "T"
    assert retractations.verifier(conn, telecharger=faux)["mis_a_jour"] == 0
