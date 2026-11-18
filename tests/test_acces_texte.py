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
    assert "non indiqué" in at.bloc_html(D, {}, peb="") and "Texte intégral gratuit</a>" not in at.bloc_html(D, {}, peb="")


def test_bouton_bu_copie_la_reference_et_n_envoie_rien():
    html = at.bloc_html(D, {}, peb="https://bu.exemple/peb")
    assert 'data-url="https://bu.exemple/peb"' in html and "Type de référence : Article" in html
    assert "<form" not in html


def test_lien_openurl_pour_la_bu():
    from urllib.parse import parse_qsl, urlsplit
    url = at.lien_openurl(D, "https://bu.exemple/discovery/openurl?institution=X&vid=X:Y")
    q = parse_qsl(urlsplit(url).query)
    assert ("rft.atitle", "Netarsudil study") in q and ("rft.jtitle", "Adv Ther") in q and ("rft.date", "2026") in q
    assert ("rft_id", "info:doi/10.1007/x") in q and ("rft_id", "info:pmid/41915113") in q and ("vid", "X:Y") in q
    assert at.lien_openurl(D, "") == ""
    html = at.bloc_html(D, {}, peb="https://bu.exemple/peb", openurl="https://bu.exemple/openurl?vid=V")
    assert "https://bu.exemple/openurl?vid=V&amp;ctx_ver" in html and "formulaire PEB vierge" in html


def test_lien_researchgate_par_titre():
    assert at.lien_researchgate(D) == "https://www.researchgate.net/search/publication?q=Netarsudil%20study"
    assert "Chercher sur ResearchGate" in at.bloc_html(D, {}, peb="", openurl="")


def test_statut_acces():
    assert at.statut_acces({"pmcid": "PMC1"}, {}) == "libre"
    assert at.statut_acces({}, {"statut_acces": "closed", "acces_ouvert": False}) == "payant"
    assert at.statut_acces({}, {}) == "inconnu"
    assert "Article payant" in at.bloc_html(D, {"statut_acces": "closed"}, peb="", openurl="")
    assert "non indiqué" in at.bloc_html(D, {}, peb="", openurl="")
