"""Rôle des produits d'un essai : celui DÉCLARÉ au registre, sans réinterprétation trompeuse."""
import construire_site as cs


def bras(type_, *produits):
    return {"type": type_, "interventions": [f"Drug: {p}" for p in produits] or None}


def test_bras_experimental_et_comparateur():
    r = cs.produits_essai({"bras": [bras("EXPERIMENTAL", "A"), bras("ACTIVE_COMPARATOR", "B")]})
    assert r == [{"nom": "A", "role": "bras expérimental (registre)"}, {"nom": "B", "role": "bras comparateur (registre)"}]


def test_seul_bras_traite_declare_comparateur():
    """Cas réel NCT07891910 : Iopidine déclarée « Active Comparator » face à un groupe sans traitement."""
    r = cs.produits_essai({"bras": [bras("ACTIVE_COMPARATOR", "Apraclonidine"), bras("NO_INTERVENTION")]})
    assert r[0]["role"].startswith("bras traité")


def test_essai_face_a_face():
    r = cs.produits_essai({"bras": [bras("ACTIVE_COMPARATOR", "A"), bras("ACTIVE_COMPARATOR", "B")]})
    assert all(p["role"].startswith("comparé à un autre traitement") for p in r)


def test_bras_sans_type_garde_ses_produits():
    assert cs.produits_essai({"bras": [bras(None, "A")]})[0]["role"] == "bras du registre (type non précisé)"
