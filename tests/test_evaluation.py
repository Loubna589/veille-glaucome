"""Métriques d'évaluation : F1 macro / matrice de confusion, précision@5 et MRR."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import evaluer  # noqa: E402
import evaluer_recherche  # noqa: E402


def test_f1_macro_parfait_et_matrice():
    vrais = ["dispositif", "autre", "dispositif"]
    macro, detail = evaluer.f1_macro(vrais, vrais)
    assert macro == 1.0 and set(detail) == {"dispositif", "autre"}
    assert evaluer.matrice_confusion(vrais, vrais)["dispositif"]["dispositif"] == 2


def test_f1_macro_valeur_connue():
    vrais = ["autre", "autre", "dispositif", "dispositif"]
    predits = ["autre", "dispositif", "dispositif", "dispositif"]
    macro, detail = evaluer.f1_macro(vrais, predits)
    # autre : P=1, R=0,5 → F1=0,667 ; dispositif : P=0,667, R=1 → F1=0,8 ; macro = 0,733
    assert detail["autre"]["f1"] == 0.667 and detail["dispositif"]["f1"] == 0.8 and macro == 0.733


def test_precision_a_5_et_mrr():
    assert evaluer_recherche.precision_a_k([1, 0, 1, 0, 0]) == 0.4
    assert evaluer_recherche.rang_reciproque([0, 0, 1, 0, 0]) == 1 / 3
    assert evaluer_recherche.rang_reciproque([0, 0, 0, 0, 0]) == 0.0


def test_evaluer_ignore_les_questions_non_jugees():
    lignes = [{"question_id": "1", "question": "q1", "rang": str(r), "pertinent_loubna": v} for r, v in zip(range(1, 6), "10100")]
    lignes += [{"question_id": "2", "question": "q2", "rang": str(r), "pertinent_loubna": ""} for r in range(1, 6)]
    res = evaluer_recherche.evaluer(lignes)
    assert res["questions_jugees"] == 1 and res["precision_a_5"] == 0.4 and res["mrr"] == 1.0
