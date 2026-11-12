"""Démo : simule la modification d'un essai et montre l'alerte générée — sans réseau, sans toucher la vraie base.

Lancement :  python demo_alerte.py [NCT...]

1. copie la base (data/veille.db, ou demo/veille_demo.db si elle est absente) dans un fichier temporaire ;
2. prend un essai réel et fabrique une NOUVELLE VERSION : statut → COMPLETED, date de fin principale
   repoussée, résultats déposés ;
3. l'enregistre comme le ferait le pipeline → événements détectés + nouvelle version conservée ;
4. publie les alertes (fichier demo/alerte_demo.md) ;
5. RE-JOUE exactement la même modification → 0 nouvel événement, 0 alerte : la déduplication marche.
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from veille import alertes, base  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    source = base.CHEMIN if base.CHEMIN.exists() else RACINE / "demo" / "veille_demo.db"
    copie = Path(tempfile.mkdtemp()) / "veille_demo_copie.db"
    shutil.copy(source, copie)
    conn = base.connecter(copie)
    conn.execute("UPDATE evenements SET envoye = 1")  # on ne montre QUE les alertes produites par la démo
    conn.commit()
    print(f"Copie de travail : {copie} (la vraie base n'est pas modifiée)\n")

    nct = sys.argv[1] if len(sys.argv) > 1 else conn.execute(
        "SELECT nct FROM essais WHERE statut = 'RECRUITING' ORDER BY nct LIMIT 1").fetchone()["nct"]
    avant = json.loads(conn.execute("SELECT donnees FROM essais WHERE nct = ?", (nct,)).fetchone()["donnees"])
    apres = dict(avant, statut="COMPLETED", date_fin_principale="2027-06", resultats_deposes=True)
    print(f"Essai {nct} : « {avant.get('titre')} »")
    print(f"  version actuelle   : statut={avant.get('statut')}, fin principale={avant.get('date_fin_principale')}, "
          f"résultats={avant.get('resultats_deposes')}")
    print(f"  version simulée    : statut={apres['statut']}, fin principale={apres['date_fin_principale']}, résultats=True\n")

    nouveaux = {}
    for passage in (1, 2):
        etat, changements, n = base.enregistrer_essai(conn, apres, "2026-11-12", f"demo-{passage}")
        nouveaux[passage] = n
        conn.commit()
        versions = conn.execute("SELECT COUNT(*) FROM versions_essais WHERE nct = ?", (nct,)).fetchone()[0]
        print(f"Passage {passage} : état « {etat} », {n} nouvel(s) événement(s), {versions} version(s) conservée(s) de l'essai")
        nb = alertes.publier(conn, RACINE / "demo" / "alerte_demo.md", exporter=False) if passage == 1 else len(alertes.a_envoyer(conn))
        print(f"           alertes publiées : {nb}\n" if passage == 1 else f"           alertes en attente : {nb} (rien n'est renvoyé)\n")

    print("Événements enregistrés par la démo :")
    for ev in conn.execute("SELECT type, champ, avant, apres, envoye FROM evenements WHERE execution_id LIKE 'demo-%'"):
        print(f"  - {ev['type']:24} {ev['champ'] or '':22} {ev['avant']} → {ev['apres']}  (envoyé : {bool(ev['envoye'])})")
    print(f"\nAlerte écrite dans demo/alerte_demo.md")
    # Pour la page « Alertes » du site : exemple clairement marqué comme démonstration
    evenements = [dict(r) for r in conn.execute(
        "SELECT type, objet_type, objet_id, champ, avant, apres, titre, date_detection FROM evenements "
        "WHERE execution_id LIKE 'demo-%' ORDER BY id")]
    (RACINE / "site" / "data" / "alertes_demo.json").write_text(json.dumps(
        {"demonstration": True, "genere_le": time.strftime("%Y-%m-%d"), "essai": nct, "evenements": evenements,
         "rejeu_nouveaux_evenements": nouveaux[2]}, ensure_ascii=False), encoding="utf-8")
    print("Exemple publié pour la page Alertes : site/data/alertes_demo.json")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
