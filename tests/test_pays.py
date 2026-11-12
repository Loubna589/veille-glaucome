"""Nouveaux pays (Canada, Espagne, Italie, Suisse) : noms multilingues et rattachement, avec des réponses simulées."""
import io
import json

import pytest

from veille import marche_commun as mc
from veille.sources import canada, espagne, italie, suisse

MOLECULES = [{"nom": "Latanoprost", "substances": frozenset({"latanoprost"})},
             {"nom": "Dorzolamide + timolol", "substances": frozenset({"dorzolamide", "timolol"})},
             {"nom": "Roclanda", "substances": frozenset({"netarsudil", "latanoprost"})}]


@pytest.mark.parametrize("nom, attendu", [
    ("timololo", "timolol"), ("Dorzolamida", "dorzolamide"), ("latanoprostum", "latanoprost"),
    ("netarsudili dimesilas", "netarsudil"), ("TIMOLOL (TIMOLOL MALEATE)", "timolol"),
    ("brimonidini tartras", "brimonidine"), ("MÉSYLATE DE NÉTARSUDIL", "netarsudil"),
])
def test_noms_multilingues(nom, attendu):
    assert mc.cle_substance(nom) == attendu


@pytest.fixture
def cache_vide(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "CACHE", tmp_path)
    return tmp_path


def test_espagne_rattachement_et_dates(cache_vide, monkeypatch):
    resultats = [
        {"nregistro": "1", "nombre": "ROCLANDA", "labtitular": "Santen Oy", "estado": {"aut": 1690458129000}, "comerc": True,
         "viasAdministracion": [{"nombre": "VÍA OFTÁLMICA"}], "vtm": {"nombre": "latanoprost + netarsudil"}},
        {"nregistro": "2", "nombre": "LATANOPROST ORAL ?", "estado": {}, "viasAdministracion": [{"nombre": "VÍA ORAL"}],
         "vtm": {"nombre": "latanoprost"}},
    ]
    monkeypatch.setattr(espagne, "rechercher", lambda s: resultats)
    sortie, source = espagne.collecter(MOLECULES)
    assert [x["numero"] for x in sortie["Roclanda"]] == ["1"]          # la voie orale est écartée
    assert sortie["Roclanda"][0]["date_autorisation"] == "2023-07-27"   # millisecondes → date
    assert sortie["Latanoprost"] == []


def test_canada_exige_toutes_les_substances(cache_vide, monkeypatch):
    def faux_appel(service, **p):
        if service == "activeingredient":
            nom = p["ingredientname"]
            return {"LATANOPROST": [{"drug_code": 1, "ingredient_name": "LATANOPROST"},
                                    {"drug_code": 2, "ingredient_name": "LATANOPROST"}],
                    "TIMOLOL": [{"drug_code": 3, "ingredient_name": "TIMOLOL (TIMOLOL MALEATE)"}],
                    "DORZOLAMIDE": [{"drug_code": 3, "ingredient_name": "DORZOLAMIDE (DORZOLAMIDE HYDROCHLORIDE)"}]}.get(nom, [])
        code = int(p["id"])  # le code produit circule en texte, comme dans l'API réelle
        if service == "drugproduct":
            return [{"brand_name": f"P{code}", "company_name": "X", "number_of_ais": "2" if code in (2, 3) else "1"}]
        if service == "status":
            return [{"status": "Commercialisé", "original_market_date": "2010-01-01"}]
        return [{"route_of_administration_name": "Ophtalmique"}]
    monkeypatch.setattr(canada, "appeler", faux_appel)
    sortie, _ = canada.collecter(MOLECULES)
    assert [x["nom"] for x in sortie["Latanoprost"]] == ["P1"]   # P2 contient une 2e substance non suivie : écarté
    assert [x["nom"] for x in sortie["Dorzolamide + timolol"]] == ["P3"]


def test_italie_listes_a_et_h(cache_vide, monkeypatch):
    page = '<a href="/documents/1/Classe-A_per_principio-attivo_30-6-2026.csv">A</a>'
    csv_a = ("Principio attivo;Descrizione gruppo;Denominazione e Confezione;Prezzo al pubblico €;Titolare AIC;AIC\n"
             "Dorzolamide/timololo;DORZOLAMIDE+TIMOLOLO SOLUZIONE USO OFTALMICO;COSOPT*collirio;9,85;SANTEN;034242103\n"
             "Latanoprost;LATANOPROST CPR USO ORALE;X;1,00;Y;1\n")
    monkeypatch.setattr(mc, "telecharger", lambda url, nom, suivi: (page if nom.endswith(".html") else csv_a).encode("utf-8"))
    sortie, source = italie.collecter(MOLECULES)
    assert sortie["Dorzolamide + timolol"][0]["prix"] == 9.85 and sortie["Dorzolamide + timolol"][0]["classe"] == "A"
    assert sortie["Dorzolamide + timolol"][0]["titulaire"] == "SANTEN"
    assert sortie["Latanoprost"] == [] and source["dates_listes"] == {"A": "2026-06-30"}


def test_italie_classe_h_colonnes_differentes(cache_vide, monkeypatch):
    """Le fichier de classe H insère deux colonnes de prix : le titulaire (Titolare AIC) est lu par son nom de colonne."""
    page = '<a href="/documents/1/Classe-H_per_principio-attivo_30-6-2026.csv">H</a>'
    csv_h = ("Principio attivo;Descrizione gruppo;Denominazione e Confezione;Prezzo al pubblico €;Prezzo Ex-factory €;"
             "Prezzo massimo di cessione €;Titolare AIC;AIC\n"
             "Latanoprost;LATANOPROST SOLUZIONE USO OFTALMICO;XALATAN*collirio;12,50;7,10;6,90;PFIZER ITALIA Srl;028406010\n")
    monkeypatch.setattr(mc, "telecharger", lambda url, nom, suivi: (page if nom.endswith(".html") else csv_h).encode("utf-8"))
    sortie, _ = italie.collecter(MOLECULES)
    x = sortie["Latanoprost"][0]
    assert (x["classe"], x["titulaire"], x["aic"], x["prix"]) == ("H", "PFIZER ITALIA Srl", "028406010", 12.5)


def test_suisse_classe_atc_et_latin(cache_vide, monkeypatch):
    import openpyxl
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.append(["Liste"])
    feuille.append(["Zulassungs-nummer", "Dosis", "Bezeichnung", "Zulassungsinhaberin", "ATC-Code", "Erstzulassungs-datum",
                    "Wirkstoff(e)", "Zulassungsstatus"])
    feuille.append(["69043", "1", "Roclanda", "Santen SA", "S01EE51", "2023-10-03", "netarsudilum, latanoprostum", "zugelassen"])
    feuille.append(["1", "1", "Autre", "Z", "N02BE01", "2000-01-01", "latanoprostum", "zugelassen"])
    tampon = io.BytesIO()
    classeur.save(tampon)
    page = '<a href="/dam/x/erweiterte_ham_ind.xlsx.download.xlsx/erweiterte_ham_ind.xlsx">x</a>'
    monkeypatch.setattr(mc, "telecharger", lambda url, nom, suivi: page.encode() if nom.endswith(".html") else tampon.getvalue())
    sortie, _ = suisse.collecter(MOLECULES)
    assert sortie["Roclanda"][0]["date_autorisation"] == "2023-10-03"
    assert sortie["Latanoprost"] == []   # code ATC hors S01E : écarté
