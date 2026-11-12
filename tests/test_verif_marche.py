"""Validation des extractions « accès au marché » : construction du fichier et taux de concordance."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import construire_verif_marche  # noqa: E402
import evaluer_verif_marche  # noqa: E402

MARCHE = {"molecules": {"Latanoprost": {"france": [
    {"cis": "1", "nom": "XALATAN", "date_amm": "1997-07-24", "lien": "https://bdpm/1",
     "smr": [{"valeur": "Important", "date": "2016-05-11", "lien": "https://has/1"}], "asmr": [],
     "presentations": [{"statut": "Présentation active", "taux_remboursement": "65 %", "prix": 10.5}]},
    {"cis": "2", "nom": "SANS AVIS", "date_amm": None, "lien": "https://bdpm/2", "smr": [], "asmr": [], "presentations": []},
]}}}


def test_construction_une_ligne_par_valeur_presente():
    lignes, nb = construire_verif_marche.construire(MARCHE)
    assert nb == 2
    champs = [(l["medicament_id"], l["champ"]) for l in lignes]
    assert ("1", "smr_valeur") in champs and ("1", "prix") in champs
    assert not any(m == "2" for m, _ in champs)      # aucune valeur pour le médicament 2 : rien à vérifier
    assert all(l["verifie_loubna"] == "" for l in lignes)
    assert next(l for l in lignes if l["champ"] == "smr_valeur")["lien_verification"] == "https://has/1"


def test_concordance_globale_et_par_champ():
    lignes = [{"champ": "smr_valeur", "verifie_loubna": "1", "medicament": "A", "valeur_outil": "Important"},
              {"champ": "smr_valeur", "verifie_loubna": "0", "medicament": "B", "valeur_outil": "Faible", "commentaire": "c'est Modéré"},
              {"champ": "prix", "verifie_loubna": "1", "medicament": "A", "valeur_outil": "10.5"},
              {"champ": "prix", "verifie_loubna": "", "medicament": "B", "valeur_outil": "3"}]
    bilan = evaluer_verif_marche.concordance(lignes)
    assert bilan["taux_concordance"] == 0.667 and bilan["valeurs_verifiees"] == 3 and bilan["valeurs_total"] == 4
    assert bilan["par_champ"]["smr_valeur"]["taux"] == 0.5 and bilan["par_champ"]["prix"]["taux"] == 1.0
    assert bilan["ecarts"][0]["commentaire"] == "c'est Modéré"


def test_rien_de_verifie():
    assert evaluer_verif_marche.concordance([{"champ": "prix", "verifie_loubna": ""}]) is None
