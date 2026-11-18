"""« Lire l'article en entier » : uniquement des liens et adresses déclarés par les sources."""
from urllib.parse import unquote

from veille import acces_texte as at

D = {"pmid": "41915113", "titre": "Netarsudil study", "revue": "Adv Ther", "date_publication": "2026-03-31",
     "doi": "10.1007/x", "pmcid": None,
     "affiliations_auteurs": ["Dept, Tokyo, Japan. macaihara1126@gmail.com.", "Other dept, Osaka."]}


def test_email_lu_dans_l_affiliation_sans_point_final():
    assert at.emails_auteurs(D["affiliations_auteurs"]) == ["macaihara1126@gmail.com"]


def test_pas_d_email_pas_de_bouton_auteur():
    html = at.bloc_html({**D, "affiliations_auteurs": ["Dept, Tokyo."]}, {}, peb="")
    assert "Demander à l'auteur" not in html and "mailto:" not in html


def test_mail_pre_redige_avec_titre_doi_et_usage_personnel():
    url = at.mail_auteur(D, "a@b.org")
    assert url.startswith("mailto:a@b.org?subject=")
    corps = unquote(url)
    assert "Netarsudil study" in corps and "DOI: 10.1007/x" in corps and "personal" in corps


def test_texte_gratuit_pmc_puis_openalex_sinon_rien():
    assert at.texte_gratuit({**D, "pmcid": "PMC123"}, {})[0] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"
    assert at.texte_gratuit(D, {"acces_ouvert": True, "url_pdf": "https://x/p.pdf"})[0] == "https://x/p.pdf"
    assert at.texte_gratuit(D, {"acces_ouvert": False, "statut_acces": "closed", "url_texte": "https://x"}) is None
    assert "Aucune version gratuite" in at.bloc_html(D, {}, peb="")


def test_bouton_bu_copie_la_reference_et_n_envoie_rien():
    html = at.bloc_html(D, {}, peb="https://bu.exemple/peb")
    assert 'data-url="https://bu.exemple/peb"' in html and "Type de référence : Article" in html
    assert "<form" not in html
