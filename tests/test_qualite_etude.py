from veille import qualite_etude as q


def test_pyramide_et_criteres():
    rct = q.evaluer({"titre": "A randomized double-masked trial", "types_publication": ["Journal Article"],
                     "resume": "A total of 325 patients were randomized versus placebo at 12 centers. NCT01234567"})
    assert rct["niveau"] == 2 and rct["participants"] == 325 and rct["taille"] == "grand effectif"
    noms = {c["nom"]: c["present"] for c in rct["criteres"]}
    assert noms["Tirage au sort"] and noms["Insu (« aveugle »)"] and noms["Groupe de comparaison"]
    assert q.evaluer({"titre": "X", "types_publication": ["Meta-Analysis"], "resume": "..."})["niveau"] == 1
    assert q.evaluer({"titre": "A case of glaucoma", "types_publication": [], "resume": "We report a case of..."})["niveau"] == 5
    assert q.evaluer({"titre": "Retinal ganglion cells in mice", "types_publication": [], "resume": "In mice, ..."})["niveau"] == 0
    assert "Qualité de l'étude" in q.bloc_html(rct)
