"""Détection des changements d'essais : versions, événements typés, alertes jamais envoyées deux fois."""
from conftest import essai
from veille import alertes, base


def types(conn):
    return sorted(r["type"] for r in conn.execute("SELECT type FROM evenements"))


def test_nouvel_essai(conn):
    assert base.enregistrer_essai(conn, essai(), "2026-11-01")[0] == "nouveau"
    assert types(conn) == ["nouvel_essai"]


def test_essai_inchange_ne_cree_rien(conn):
    base.enregistrer_essai(conn, essai(), "2026-11-01")
    assert base.enregistrer_essai(conn, essai(), "2026-11-02") == ("inchange", {}, 0)
    assert conn.execute("SELECT COUNT(*) FROM versions_essais").fetchone()[0] == 1


def test_changements_detectes_et_types(conn):
    base.enregistrer_essai(conn, essai(), "2026-11-01")
    etat, _, n = base.enregistrer_essai(conn, essai(statut="ACTIVE_NOT_RECRUITING", date_fin_principale="2027-06",
                                                    phases_declarees=["PHASE3"]), "2026-11-02")
    assert etat == "modifie" and n == 3
    assert types(conn) == ["changement_date_fin", "changement_phase", "changement_recrutement", "nouvel_essai"]
    assert conn.execute("SELECT COUNT(*) FROM versions_essais").fetchone()[0] == 2


def test_statut_hors_recrutement_et_resultats(conn):
    base.enregistrer_essai(conn, essai(), "2026-11-01")
    etat, _, _ = base.enregistrer_essai(conn, essai(statut="TERMINATED", resultats_deposes=True), "2026-11-02")
    assert etat == "resultats_ajoutes"
    assert "changement_statut" in types(conn) and "resultats_deposes" in types(conn)


def test_meme_changement_rejoue_aucun_doublon(conn):
    base.enregistrer_essai(conn, essai(), "2026-11-01")
    base.enregistrer_essai(conn, essai(statut="COMPLETED"), "2026-11-02")
    base.enregistrer_essai(conn, essai(), "2026-11-03")            # retour en arrière (correction de la source)
    base.enregistrer_essai(conn, essai(statut="COMPLETED"), "2026-11-04")  # même changement qu'avant
    statuts = conn.execute("SELECT COUNT(*) FROM evenements WHERE champ = 'statut' AND apres = 'COMPLETED'").fetchone()[0]
    assert statuts == 1


def test_alerte_publiee_une_seule_fois(conn, tmp_path):
    base.enregistrer_essai(conn, essai(), "2026-11-01")
    base.enregistrer_essai(conn, essai(statut="COMPLETED"), "2026-11-02")
    conn.commit()
    assert alertes.publier(conn, tmp_path / "alertes.md", exporter=False) == 2   # nouvel essai + statut
    assert alertes.publier(conn, tmp_path / "alertes.md", exporter=False) == 0   # rien n'est renvoyé
    assert conn.execute("SELECT COUNT(*) FROM evenements WHERE envoye = 0").fetchone()[0] == 0


def test_execution_partielle_si_une_source_echoue(conn):
    ex = base.Execution(conn)
    ex.etape("source_ok", lambda: 5)
    ex.etape("source_en_panne", lambda: 1 / 0)
    assert ex.terminer() == "partielle"
    lignes = {r["source"]: r["statut"] for r in conn.execute("SELECT source, statut FROM executions")}
    assert lignes == {"source_ok": "ok", "source_en_panne": "echec", "pipeline": "partielle"}
