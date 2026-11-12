"""Alertes : chaque événement (nouvel essai, changement d'essai, résultats déposés…) est publié UNE SEULE FOIS.

Déduplication à deux niveaux :
1. à la détection : la table `evenements` a une clé unique (type | essai | champ | avant | après) ;
   le même changement vu deux fois ne crée pas deux événements ;
2. à l'envoi : chaque événement porte un drapeau `envoye` ; on ne publie que ceux qui ne l'ont
   jamais été, puis on les marque (date d'envoi).

Sorties :
- alertes.md (à la racine du dépôt) : les alertes de la dernière publication, lisibles sur GitHub ;
- la page « Alertes » du site (site/alertes.html, à partir de site/data/evenements.json) ;
- e-mail FACULTATIF, seulement si les secrets SMTP_HOTE, SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE et
  ALERTES_DESTINATAIRE existent. Si l'envoi échoue, les alertes restent « à envoyer » (nouvel essai demain).
"""
import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from veille import base, export, reseau

RACINE = Path(__file__).resolve().parents[1]
FICHIER_MD = RACINE / "alertes.md"

LIBELLES = {
    "nouvel_essai": "Nouvel essai",
    "nouvel_article": "Nouvelle publication",
    "changement_statut": "Changement de statut",
    "changement_recrutement": "Changement de recrutement",
    "changement_date_fin": "Changement de date de fin",
    "changement_phase": "Changement de phase",
    "resultats_deposes": "Résultats déposés au registre",
}
TYPES_ALERTE = tuple(t for t in LIBELLES if t != "nouvel_article")  # les publications vont dans le site, pas en alerte


def lien(ev):
    if ev["objet_type"] == "essai":
        return f"https://clinicaltrials.gov/study/{ev['objet_id']}"
    return f"https://pubmed.ncbi.nlm.nih.gov/{ev['objet_id']}/" if str(ev["objet_id"]).isdigit() else None


def a_envoyer(conn):
    marques = ",".join("?" * len(TYPES_ALERTE))
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM evenements WHERE envoye = 0 AND type IN ({marques}) ORDER BY date_detection, id", TYPES_ALERTE)]


def texte_markdown(evenements, titre="Alertes de la veille glaucome"):
    lignes = [f"# {titre}", "", f"Publié le {time.strftime('%d/%m/%Y à %H:%M')} — {len(evenements)} alerte(s).", ""]
    if not evenements:
        lignes.append("Aucune nouvelle alerte.")
    for ev in evenements:
        detail = f" : `{ev['avant']}` → `{ev['apres']}`" if ev.get("champ") and ev["type"] != "nouvel_essai" else ""
        url = lien(ev)
        lignes.append(f"- **{LIBELLES.get(ev['type'], ev['type'])}** — [{ev['objet_id']}]({url}) "
                      f"{(ev.get('titre') or '')[:110]}{detail} _(détecté le {ev['date_detection']})_")
    return "\n".join(lignes) + "\n"


def envoyer_mail(texte, nombre):
    """E-mail facultatif. Renvoie True (envoyé), False (non configuré) ; lève une exception si l'envoi échoue."""
    hote, utilisateur = os.getenv("SMTP_HOTE"), os.getenv("SMTP_UTILISATEUR")
    mot_de_passe, destinataire = os.getenv("SMTP_MOT_DE_PASSE"), os.getenv("ALERTES_DESTINATAIRE")
    if not all((hote, utilisateur, mot_de_passe, destinataire)):
        return False
    message = EmailMessage()
    message["Subject"] = f"Veille glaucome : {nombre} alerte(s)"
    message["From"], message["To"] = utilisateur, destinataire
    message.set_content(texte)
    with smtplib.SMTP(hote, int(os.getenv("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(utilisateur, mot_de_passe)
        smtp.send_message(message)
    return True


def publier(conn, fichier=FICHIER_MD, exporter=True):
    """Publie les alertes jamais envoyées, puis les marque. Renvoie le nombre d'alertes publiées.

    `exporter=False` : n'écrit pas site/data/evenements.json (utilisé par la démo, sur une copie de la base)."""
    evenements = a_envoyer(conn)
    texte = texte_markdown(evenements)
    if evenements:
        try:
            par_mail = envoyer_mail(texte, len(evenements))
        except (OSError, smtplib.SMTPException) as erreur:
            reseau.journal().error("Alertes : e-mail non envoyé (%s) — les alertes seront retentées", erreur)
            par_mail = None
        Path(fichier).write_text(texte, encoding="utf-8")
        if par_mail is not None:  # échec d'e-mail : on ne marque pas, pour réessayer à la prochaine exécution
            conn.executemany("UPDATE evenements SET envoye = 1, date_envoi = ? WHERE id = ?",
                             [(base.maintenant(), ev["id"]) for ev in evenements])
            conn.commit()
        print(f"Alertes : {len(evenements)} publiée(s) dans {Path(fichier).name}" + (" et par e-mail" if par_mail else ""))
    else:
        print("Alertes : aucune nouvelle alerte")
    if exporter:
        export.exporter_tables(conn)
    return len(evenements)
