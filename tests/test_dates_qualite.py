"""Validation des dates et contrôles qualité de l'export JSON."""
from datetime import date

import pytest

from veille import export, marche_commun

AUJOURDHUI = date(2026, 11, 11)


@pytest.mark.parametrize("texte", ["2026", "2026-02", "2026-02-28", "2024-02-29"])
def test_dates_valides(texte):
    assert export.date_valide(texte)


@pytest.mark.parametrize("texte", ["2026-02-30", "2023-02-29", "2026-13", "26-01-01", "01/02/2026", "", None, "1850-01-01"])
def test_dates_invalides(texte):
    assert not export.date_valide(texte)


def test_date_de_detection_dans_le_futur_refusee():
    assert export.date_valide("2026-12-01")
    assert not export.date_valide("2026-12-01", futur_permis=False, aujourd_hui=AUJOURDHUI)


def test_conversion_des_dates_des_sources():
    assert marche_commun.date_iso("07/01/2021") == "2021-01-07"
    assert marche_commun.date_iso("20210107") == "2021-01-07"
    assert marche_commun.date_iso("janvier 2021") is None


def etude(i, **champs):
    e = {"id": i, "type": "article", "source": "PubMed", "titre": f"Titre {i}", "date_detection": "2026-11-01",
         "date_source": "2026-10"}
    e.update(champs)
    return e


def test_controle_qualite_ecarte_les_etudes_invalides():
    etudes = [etude("1"), etude("2", titre=""), etude("3", date_source="2026-02-30"), etude("1"),
              etude("4", doi="10.1/x"), etude("5", doi="10.1/X"), etude("6", date_detection="2027-01-01")]
    valides, rapport = export.controler(etudes, aujourd_hui=AUJOURDHUI)
    assert [e["id"] for e in valides] == ["1", "4"]
    raisons = {r["id"]: " ".join(r["raisons"]) for r in rapport["rejets"]}
    assert "titre" in raisons["2"]
    assert "date source invalide" in raisons["3"]
    assert "doublon d'identifiant" in raisons["1"]
    assert "doublon de DOI" in raisons["5"]
    assert "date de détection invalide" in raisons["6"]
    assert (rapport["etudes_recues"], rapport["etudes_exportees"], rapport["etudes_rejetees"]) == (7, 2, 5)
