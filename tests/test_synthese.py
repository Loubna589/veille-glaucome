import json
import sqlite3
from datetime import date

from veille import synthese


def base_test():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
    CREATE TABLE articles (pmid TEXT, titre TEXT, revue TEXT, donnees TEXT, annexes TEXT);
    CREATE TABLE essais (nct TEXT, titre TEXT, statut TEXT, phases TEXT, promoteur TEXT, donnees TEXT);
    CREATE TABLE evenements (type TEXT, objet_type TEXT, objet_id TEXT, champ TEXT, avant TEXT, apres TEXT, titre TEXT, date_detection TEXT);
    CREATE TABLE traitements_ia (objet_id TEXT, resume TEXT);""")
    for i in range(6):
        conn.execute("INSERT INTO articles VALUES (?,?,?,?,?)", (str(100 + i), f"Article {i}", "Ophthalmology", json.dumps(
            {"date_entree_pubmed": "2026-11-16", "resume_present": True,
             "types_publication": ["Randomized Controlled Trial"] if i == 0 else ["Journal Article"]}), "{}"))
    conn.execute("INSERT INTO articles VALUES ('999','Vieux','X',?, '{}')", (json.dumps({"date_entree_pubmed": "2026-10-01"}),))
    conn.execute("INSERT INTO essais VALUES ('NCT00000001','Essai neuf','RECRUITING','[\"PHASE3\"]','Labo',?)",
                 (json.dumps({"date_premiere_publication": "2026-11-17", "type_promoteur": "INDUSTRY"}),))
    conn.execute("INSERT INTO evenements VALUES ('resultats_deposes','essai','NCT00000002','resultats','non','oui','Essai fini','2026-11-15T06:00:00')")
    return conn


def test_selection_par_regles_et_fenetre_de_7_jours():
    conn = base_test()
    el = synthese.candidats(conn, *synthese.fenetre(date(2026, 11, 18)))
    ids = [e["id"] for e in el]
    assert "PMID:999" not in ids and ids[:2] == ["NCT00000001", "NCT00000002"]
    assert synthese.compter(conn, "2026-11-12", "2026-11-18") == {"articles": 6, "nouveaux_essais": 1, "changements_essais": 1}


def test_validation_rejette_les_citations_inventees():
    el = [{"id": f"PMID:{i}"} for i in range(5)]
    bons = {"points": [{"titre": f"T{i}", "texte": f"Texte [PMID:{i}]", "sources": [f"PMID:{i}"]} for i in range(5)]}
    v = synthese.valider(bons, el)
    assert len(v) == 5 and v[0]["texte"] == "Texte"
    faux = {"points": bons["points"][:4] + [{"titre": "X", "texte": "Y", "sources": ["NCT99999999"]}]}
    assert synthese.valider(faux, el) is None


def test_sans_cle_les_regles_ecrivent_5_points_avec_liens():
    s = synthese.construire(base_test(), jour=date(2026, 11, 18), cle="")
    assert s["mode"] == "regles" and len(s["points"]) == 5
    assert s["points"][0]["liens"][0]["lien"] == "https://clinicaltrials.gov/study/NCT00000001"
    assert "ce qu'il faut retenir du 12/11/2026 au 18/11/2026" in synthese.texte_mail(s, "https://x/")


def test_issue_hebdomadaire_en_markdown_avec_liens():
    s = synthese.construire(base_test(), jour=date(2026, 11, 18), cle="")
    md = synthese.texte_issue(s, "https://x/", personne="@moi")
    assert md.startswith("@moi : voici ce qu'il faut retenir du 12/11/2026 au 18/11/2026")
    assert "[NCT00000001](https://clinicaltrials.gov/study/NCT00000001)" in md and "https://x/semaine.html" in md
