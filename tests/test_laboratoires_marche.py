"""Laboratoire déclaré par chaque source (page « Autorisations & remboursement ») : regroupement et absence de déduction."""
from veille import delais
from veille import laboratoires_marche as L


def test_cle_retire_formes_juridiques_pays_et_mots_generiques():
    assert L.cle("Santen Oy") == L.cle("SANTEN ITALY Srl") == L.cle("Santen SA") == "santen"
    assert L.cle("Laboratorios Thea S.A.") == L.cle("THEA FARMA SpA") == L.cle("Laboratoires Théa") == "thea"
    assert L.cle("ABBVIE DEUTSCHLAND (ALLEMAGNE)") == L.cle("AbbVie Deutschland GmbH & Co. KG") == "abbvie"
    assert L.cle("Bausch + Lomb Ireland Limited") == L.cle("BAUSCH AND LOMB INC") == "bausch lomb"
    assert L.cle("FARMA 1000 Srl") == "farma 1000"   # un nom fait de mots génériques n'est pas vidé
    assert L.cle("") is None and L.cle(None) is None


def test_regroupement_par_prefixe_seulement_si_le_nom_court_existe():
    g = L.regrouper(["TEVA PARENTERAL", "TEVA SANTE", "ALCON LABS INC", "ALCON CANADA INC", "UPSHER SMITH LABS"], alias={})
    assert g["TEVA PARENTERAL"] == g["TEVA SANTE"] == "Teva"
    assert g["ALCON LABS INC"] == g["ALCON CANADA INC"] == "Alcon"
    assert g["UPSHER SMITH LABS"] == "Upsher Smith Labs"   # aucun « Upsher » seul : pas de fusion


def test_alias_manuel():
    alias = {L.cle("Pfizer Europe MA EEIG"): "Pfizer", L.cle("Thea"): "Théa"}
    g = L.regrouper(["Pfizer Europe MA EEIG", "Laboratoires Thea", "THEA"], alias)
    assert g == {"Pfizer Europe MA EEIG": "Pfizer", "Laboratoires Thea": "Théa", "THEA": "Théa"}


def marche_exemple():
    return {"molecules": {"Netarsudil + latanoprost": {
        "france": [{"nom": "ROCLANDA", "titulaire": " SANTEN OY", "date_amm": "2021-01-07",
                    "smr": [{"valeur": "faible", "date": "2023-07-05"}], "asmr": [], "presentations": []}],
        "ue": [{"nom": "Roclanda", "titulaire": "Santen Oy", "date_autorisation": "2021-01-07"}],
        "usa": [{"numero": "NDA208259", "sponsor": "ALCON LABS INC", "marques": ["ROCKLATAN"], "date_approbation": "2019-03-12"}],
        "espagne": [{"nom": "ROCLANDA", "titulaire": None, "date_autorisation": "2023-07-27"}],
        "suisse": [{"nom": "Roclanda", "titulaire": "Santen SA", "date_autorisation": "2023-10-03"}],
    }}}


def test_enrichir_nom_exact_groupe_et_champ_source():
    m = L.enrichir(marche_exemple(), alias={})["molecules"]["Netarsudil + latanoprost"]
    assert m["france"][0]["laboratoire"] == {"declare": "SANTEN OY", "groupe": "Santen", "champ": "BDPM — titulaire"}
    assert m["usa"][0]["laboratoire"]["champ"] == "openFDA — sponsor_name"
    assert m["suisse"][0]["laboratoire"]["groupe"] == "Santen"


def test_titulaire_absent_jamais_deduit_d_une_autre_source():
    """CIMA ne déclare pas de titulaire ici : on ne reprend PAS celui de l'EMA ou de la BDPM."""
    M = L.enrichir(marche_exemple(), alias={})
    es = M["molecules"]["Netarsudil + latanoprost"]["espagne"][0]["laboratoire"]
    assert es == {"declare": None, "groupe": None, "champ": "AEMPS CIMA — labtitular"}
    santen = next(g for g in M["laboratoires"] if g["groupe"] == "Santen")
    assert santen["zones"] == ["france", "suisse", "ue"] and "espagne" not in santen["zones"]


def test_frise_porte_le_laboratoire_de_chaque_etape():
    M = L.enrichir(marche_exemple(), alias={})
    f = delais.frise(M["molecules"]["Netarsudil + latanoprost"])
    par_cle = {e["cle"]: e for e in f["datees"]}
    assert par_cle["fda"]["laboratoire"]["declare"] == "ALCON LABS INC"
    assert par_cle["ema"]["laboratoire"]["declare"] == "Santen Oy"
    assert par_cle["espagne"]["laboratoire"]["declare"] is None          # affiché « non déclaré par la source »
    assert par_cle["france_has"]["laboratoire"]["champ"].startswith("BDPM")  # la HAS ne déclare pas de titulaire
