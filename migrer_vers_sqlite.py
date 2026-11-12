"""Migration unique : l'ancien historique JSON (data/historique/) → base SQLite (data/veille.db).

Lancement :  python migrer_vers_sqlite.py     (sans effet si la base contient déjà des données)

Reprend : les essais (et leurs changements passés, convertis en événements datés),
les articles PubMed, les publications OpenAlex (déduplication par PMID / DOI / OpenAlex),
et l'état de la dernière exécution (etat.json).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import base  # noqa: E402

# Ancien historique JSON : archivé après la migration (déplacé, pas supprimé)
HIST = Path(__file__).resolve().parent / "data" / "archive_json_avant_sqlite"


def lire(dossier):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((HIST / dossier).glob("*.json"))]


def migrer(conn):
    bilan = {"essais": 0, "evenements_passes": 0, "articles": 0, "openalex": 0, "doublons_evites": 0}
    for m in lire("essais"):
        d = m["donnees"]
        conn.execute(
            "INSERT OR IGNORE INTO essais (nct, titre, statut, phases, date_fin_principale, participants, resultats_deposes, "
            "promoteur, donnees, annexes, empreinte, premiere_detection, derniere_modification) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["nct"], d.get("titre") or "(titre non rapporté)", d.get("statut"), base.jdump(d.get("phases_declarees")),
             d.get("date_fin_principale"), d.get("participants_nombre"), int(bool(d.get("resultats_deposes"))),
             d.get("promoteur"), base.jdump(d), base.jdump(m.get("annexes") or {}), base.empreinte(d),
             m["premiere_detection"], m.get("derniere_modification_detectee")))
        conn.execute("INSERT OR IGNORE INTO versions_essais (nct, empreinte, instantane, date_detection, execution_id) "
                     "VALUES (?, ?, ?, ?, 'migration')", (d["nct"], base.empreinte(d), base.jdump(d), m["premiere_detection"]))
        base.ajouter_evenement(conn, "nouvel_essai", "essai", d["nct"], m["premiere_detection"], "migration", titre=d.get("titre"))
        for modif in m.get("modifications") or []:
            avant = {c: v["avant"] for c, v in modif["champs"].items()}
            apres = {c: v["apres"] for c, v in modif["champs"].items()}
            for type_, champ, av, ap in base.evenements_essai(avant, apres):
                bilan["evenements_passes"] += base.ajouter_evenement(conn, type_, "essai", d["nct"], modif["date_detection"],
                                                                     "migration", champ, av, ap, d.get("titre"))
        bilan["essais"] += 1
    for m in lire("articles"):
        etat, _ = base.enregistrer_article(conn, m["donnees"], m["premiere_detection"], "pubmed", "pubmed",
                                           m.get("annexes"), "migration")
        bilan["articles" if etat == "nouveau" else "doublons_evites"] += 1
    for m in lire("openalex"):
        etat, _ = base.enregistrer_article(conn, m["donnees"], m["premiere_detection"], "openalex", "openalex",
                                           m.get("annexes"), "migration")
        bilan["openalex" if etat == "nouveau" else "doublons_evites"] += 1
    etat_json = HIST / "etat.json"
    if etat_json.exists():
        etat = json.loads(etat_json.read_text(encoding="utf-8"))
        base.ecrire_meta(conn, "derniere_execution", etat.get("derniere_execution"))
        base.ecrire_meta(conn, "dernier_bilan", etat.get("dernier_bilan"))
    # Les événements migrés sont l'historique : ils ne doivent pas déclencher d'alerte aujourd'hui
    conn.execute("UPDATE evenements SET envoye = 1, date_envoi = 'migration' WHERE execution_id = 'migration'")
    conn.commit()
    return bilan


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conn = base.connecter()
    if conn.execute("SELECT COUNT(*) FROM essais").fetchone()[0] or conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]:
        print("La base contient déjà des données : migration non relancée.")
        return 0
    bilan = migrer(conn)
    print("Migration terminée :", bilan)
    for table in ("essais", "versions_essais", "articles", "articles_sources", "evenements"):
        print(f"  {table} : {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]} ligne(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
