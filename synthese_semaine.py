"""« Ce qu'il faut retenir cette semaine » : 5 points clés + e-mail hebdomadaire.

Lancement :  python synthese_semaine.py            (ne fait rien si une synthèse a moins de 7 jours)
             python synthese_semaine.py --forcer   (refait la synthèse des 7 derniers jours)
             python synthese_semaine.py --sans-mail
Lancé chaque jour par GitHub Actions : la synthèse et l'e-mail partent donc une fois tous les 7 jours.
Résultat : data/historique/semaines/AAAA-MM-JJ.json (une par semaine, archivées), repris par construire_site.py.

E-mail : seulement si les secrets SMTP_HOTE, SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE et ALERTES_DESTINATAIRE existent
(Settings > Secrets and variables > Actions du dépôt GitHub). Aucune adresse ni aucun mot de passe dans le code.
"""
import configparser
import json
import smtplib
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import alertes, base, synthese  # noqa: E402

RACINE = Path(__file__).resolve().parent
DOSSIER = RACINE / "data" / "historique" / "semaines"


def url_site():
    config = configparser.ConfigParser(interpolation=None)
    config.read(RACINE / "config" / "site.ini", encoding="utf-8")
    return config.get("publication", "url_publique", fallback="").strip().rstrip("/") + "/"


def derniere():
    fichiers = sorted(DOSSIER.glob("*.json"))
    return json.loads(fichiers[-1].read_text(encoding="utf-8")) if fichiers else None


def alertes_semaine(conn, debut, fin):
    marques = ",".join("?" * len(alertes.TYPES_ALERTE))
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM evenements WHERE type IN ({marques}) AND substr(date_detection, 1, 10) BETWEEN ? AND ? "
        "ORDER BY date_detection, id", (*alertes.TYPES_ALERTE, debut, fin))]


def main(argv):
    precedente = derniere()
    if precedente and "--forcer" not in argv and (date.today() - date.fromisoformat(precedente["genere_le"])).days < 7:
        print(f"Synthèse de la semaine : déjà faite le {precedente['genere_le']} (prochaine dans "
              f"{7 - (date.today() - date.fromisoformat(precedente['genere_le'])).days} jour(s))")
        return
    conn = base.connecter()
    s = synthese.construire(conn)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / f"{s['fin']}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Synthèse de la semaine {s['debut']} → {s['fin']} : {len(s['points'])} points (mode {s['mode']})"
          + (f" — {s['erreur']}" if s["erreur"] else ""))
    if "--sans-mail" in argv:
        return
    if not alertes.mail_configure():
        print("E-mail hebdomadaire : non configuré (secrets SMTP absents), synthèse publiée sur le site seulement")
        return
    texte = synthese.texte_mail(s, url_site())
    evs = alertes_semaine(conn, s["debut"], s["fin"])
    if evs:
        texte += "\n\n" + alertes.texte_markdown(evs, titre="Alertes de la semaine (essais cliniques)")
    try:
        alertes.envoyer_mail(texte, len(evs), sujet=f"Veille glaucome : ce qu'il faut retenir cette semaine ({s['fin'][8:10]}/{s['fin'][5:7]})")
        print("E-mail hebdomadaire : envoyé")
    except (OSError, smtplib.SMTPException) as e:  # l'e-mail est un plus : la synthèse reste publiée
        print(f"E-mail hebdomadaire : échec ({e})")


if __name__ == "__main__":
    main(sys.argv[1:])
