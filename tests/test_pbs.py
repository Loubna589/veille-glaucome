"""Australie (PBS) : sans clé → étape sautée proprement ; avec clé → items oculaires rattachés (API simulée)."""
import pytest

from veille import base
from veille import marche_commun as mc
from veille.sources import pbs

MOLECULES = [{"nom": "Latanoprost + timolol", "substances": frozenset({"latanoprost", "timolol"})},
             {"nom": "Latanoprost", "substances": frozenset({"latanoprost"})}]


def test_sans_cle_source_sautee(monkeypatch):
    monkeypatch.delenv("PBS_API_KEY", raising=False)
    with pytest.raises(pbs.CleAbsente):
        pbs.collecter(MOLECULES)


def test_sans_cle_execution_reste_ok(conn):
    ex = base.Execution(conn)
    ex.etape("autre_source", lambda: 3)
    ex.etape("australie_pbs", lambda: pbs.collecter(MOLECULES, cle=""))
    assert ex.terminer() == "ok"   # une clé facultative absente n'est pas une panne
    statuts = {r["source"]: r["statut"] for r in conn.execute("SELECT source, statut FROM executions")}
    assert statuts["australie_pbs"] == "saute"


def test_avec_cle_items_oculaires(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "CACHE", tmp_path)
    appels = []

    def faux_appel(service, cle, **params):
        appels.append((service, cle, params))
        if service == "schedules":
            return {"data": [{"schedule_code": "4000", "effective_date": "2026-10-01"},
                             {"schedule_code": "4100", "effective_date": "2026-11-01"}]}
        return {"data": [
            {"pbs_code": "1", "drug_name": "latanoprost with timolol", "brand_name": "Xalacom", "li_form": "Eye drops 2.5 mL",
             "first_listed_date": "2004-08-01"},
            {"pbs_code": "2", "drug_name": "latanoprost", "brand_name": "Xalatan", "manner_of_administration": "Application to the eye"},
            {"pbs_code": "3", "drug_name": "latanoprost", "brand_name": "Oral?", "li_form": "Tablet"},
        ]}
    monkeypatch.setattr(pbs, "appeler", faux_appel)
    sortie, source = pbs.collecter(MOLECULES, cle="cle-test")
    assert [x["nom"] for x in sortie["Latanoprost + timolol"]] == ["Xalacom"]
    assert sortie["Latanoprost + timolol"][0]["date_inscription"] == "2004-08-01"
    assert [x["nom"] for x in sortie["Latanoprost"]] == ["Xalatan"]            # le comprimé est écarté
    assert sortie["Latanoprost"][0]["date_inscription"] is None                 # pas de date : pas d'invention
    assert appels[1][2]["schedule_code"] == "4100"                              # barème le plus récent
    assert source["bareme"] == "4100"


def test_noms_de_medicaments_pbs():
    assert pbs.substances("latanoprost with timolol") == ["latanoprost", "timolol"]
    assert pbs.substances("dorzolamide + timolol") == ["dorzolamide", "timolol"]
