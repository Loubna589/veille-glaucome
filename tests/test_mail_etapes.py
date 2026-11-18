from veille import mail_etapes


def test_texte_simple_avec_pourquoi_et_fiche():
    evs = [{"type": "changement_statut", "objet_id": "NCT00000001", "avant": "RECRUITING", "apres": "COMPLETED", "titre": "Essai A"},
           {"type": "resultats_deposes", "objet_id": "NCT00000002", "avant": "non", "apres": "oui", "titre": "Essai B"},
           {"type": "changement_date_fin", "objet_id": "NCT00000003", "avant": "2026-01-01", "apres": "2026-02-01", "titre": "Essai C"}]
    etapes = [e for e in evs if e["type"] in mail_etapes.TYPES_ETAPE]
    t = mail_etapes.texte(etapes, site="https://x/")
    assert "2 essai(s)" in t and "recrute des patients → terminé" in t and "Pourquoi c'est important" in t
    assert "https://x/fiches/NCT00000001.html" in t and "Essai C" not in t


def test_pas_de_mail_sans_changement_d_etape(monkeypatch):
    monkeypatch.setattr(mail_etapes.alertes, "mail_configure", lambda: True)
    envoyes = []
    monkeypatch.setattr(mail_etapes.alertes, "envoyer_mail", lambda *a, **k: envoyes.append(a))
    assert mail_etapes.envoyer([{"type": "changement_date_fin", "objet_id": "NCT1"}]) == 0 and not envoyes
    assert mail_etapes.envoyer([{"type": "changement_phase", "objet_id": "NCT1", "avant": '["PHASE2"]', "apres": '["PHASE3"]'}]) == 1
    assert len(envoyes) == 1
