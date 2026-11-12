"""Frise des délais d'accès au marché : uniquement des dates déclarées, ordre chronologique, mois entre étapes."""
from veille import delais

MOLECULE = {
    "usa": [{"numero": "ANDA1", "date_approbation": "2015-01-01"}, {"numero": "NDA2", "date_approbation": "2019-03-12", "marques": ["ROCKLATAN"]}],
    "ue": [{"nom": "Roclanda", "date_autorisation": "2021-01-07"}],
    "france": [{"nom": "ROCLANDA", "date_amm": "2021-01-07",
                "smr": [{"date": "2023-07-05", "valeur": "Faible"}],
                "presentations": [{"statut": "Présentation active", "taux_remboursement": "15 %"}]}],
    "suisse": [{"nom": "Roclanda", "date_autorisation": "2023-10-03"}],
    "canada": [],
}


def test_mois_entre():
    assert delais.mois_entre("2019-03-12", "2021-01-07") == 22
    assert delais.mois_entre("2021-01-07", None) is None


def test_fda_prend_la_marque_et_non_le_generique():
    fda = next(e for e in delais.etapes_molecule(MOLECULE) if e["cle"] == "fda")
    assert fda["date"] == "2019-03-12" and fda["detail"] == "ROCKLATAN"


def test_frise_ordonnee_et_delais():
    f = delais.frise(MOLECULE)
    assert [e["cle"] for e in f["datees"]] == ["fda", "ema", "france_amm", "france_has", "suisse"]
    assert [e["mois_depuis_precedente"] for e in f["datees"]] == [None, 22, 0, 30, 3]
    assert f["duree_totale_mois"] == 55


def test_etapes_sans_date_restent_vides():
    f = delais.frise(MOLECULE)
    vides = {e["cle"]: e for e in f["non_datees"]}
    assert {"canada", "espagne", "france_remb", "italie_remb"} <= set(vides)
    assert vides["france_remb"]["date"] is None and "15 %" in vides["france_remb"]["detail"]
    assert vides["canada"]["detail"] is None


def test_molecule_sans_aucune_donnee():
    f = delais.frise({})
    assert f["datees"] == [] and f["duree_totale_mois"] is None
