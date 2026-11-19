"""Page « Comparer deux produits » : forces et limites calculées par des règles, sans IA."""
from veille import comparaison


def test_essai_randomise_bien_construit():
    s = comparaison.solidite_article({"titre": "A randomized, double-masked, multicenter trial", "types_publication": ["Randomized Controlled Trial"],
                                      "resume": "We randomized 246 patients versus placebo in 12 centers. NCT01234567.", "nct_mentionnes_texte": ["NCT01234567"]})
    assert s["niveau"] == 2 and "Tirage au sort" in s["forces"] and "246 participants (effectif moyen)" in s["forces"]
    assert "jugé sur le résumé seulement" in s["limites"]


def test_etude_sur_la_souris_randomisee_reste_preclinique():
    s = comparaison.solidite_article({"titre": "In vivo study of bimatoprost in C57BL/6 mice",
                                      "resume": "Mice were randomized into 3 groups and compared with controls."})
    assert s["niveau"] == 0 and s["force"] == "Recherche préclinique" and "animal" in s["limites"][0]


def test_lien_avec_un_laboratoire_est_une_limite():
    s = comparaison.solidite_article({"titre": "Cohort", "resume": "A retrospective cohort of 50 eyes."}, industriel=True)
    assert any("laboratoire" in l for l in s["limites"]) and any("petit effectif" in l for l in s["limites"])


def test_essai_du_registre():
    s = comparaison.solidite_essai({"type_etude": "INTERVENTIONAL", "plan": {"repartition": "RANDOMIZED", "insu": "DOUBLE"},
                                    "participants_nombre": "600", "participants_type": "ESTIMATED", "type_promoteur": "INDUSTRY",
                                    "resultats_deposes": False})
    assert s["niveau"] == 2 and "Insu (double insu)" in s["forces"] and "600 participants prévus (grand effectif)" in s["forces"]
    assert any("laboratoire" in l for l in s["limites"])
