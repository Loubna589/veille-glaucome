"""Export de la base SQLite vers des fichiers JSON propres (site/data/*.json), après contrôles qualité.

GitHub Pages est un hébergement STATIQUE : il ne peut pas interroger SQLite. Le tableau de bord
lit donc des fichiers JSON générés ici, et seulement s'ils passent les contrôles :

- champs obligatoires présents (identifiant, titre, source, date de détection) ;
- dates valides (format AAAA, AAAA-MM ou AAAA-MM-JJ, date réelle, pas dans le futur
  pour les dates de détection) ;
- pas de doublon d'identifiant, ni de DOI partagé par deux études.

Une étude qui échoue un contrôle est EXCLUE de l'export et listée dans site/data/qualite.json
(avec la raison) : le site ne montre jamais une donnée invalide en silence.
"""
import json
import re
import time
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / "site" / "data"
OBLIGATOIRES = ("id", "type", "source", "titre", "date_detection")
MOTIF_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def date_valide(texte, futur_permis=True, aujourd_hui=None):
    """True si la date est au format AAAA, AAAA-MM ou AAAA-MM-JJ et existe vraiment (pas de 31 février)."""
    if not isinstance(texte, str) or not MOTIF_DATE.match(texte):
        return False
    morceaux = [int(x) for x in texte.split("-")] + [1, 1]
    try:
        d = date(morceaux[0], morceaux[1], morceaux[2])
    except ValueError:
        return False
    if not 1900 <= d.year <= 2100:
        return False
    return futur_permis or d <= (aujourd_hui or date.today())


def controler(etudes, aujourd_hui=None):
    """Renvoie (études valides, rapport). Les études invalides sont écartées, avec leur raison."""
    valides, rejets, vus_id, vus_doi = [], [], set(), {}
    for e in etudes:
        raisons = [f"champ obligatoire manquant : {c}" for c in OBLIGATOIRES if not e.get(c)]
        if e.get("date_detection") and not date_valide(e["date_detection"], futur_permis=False, aujourd_hui=aujourd_hui):
            raisons.append(f"date de détection invalide : {e['date_detection']!r}")
        if e.get("date_source") and not date_valide(e["date_source"]):
            raisons.append(f"date source invalide : {e['date_source']!r}")
        if e.get("id") in vus_id:
            raisons.append(f"doublon d'identifiant : {e['id']}")
        doi = (e.get("doi") or "").lower()
        if doi and doi in vus_doi:
            raisons.append(f"doublon de DOI {doi} (déjà porté par {vus_doi[doi]})")
        if raisons:
            rejets.append({"id": e.get("id"), "titre": (e.get("titre") or "")[:120], "raisons": raisons})
            continue
        vus_id.add(e["id"])
        if doi:
            vus_doi[doi] = e["id"]
        valides.append(e)
    rapport = {"controle_le": time.strftime("%Y-%m-%d %H:%M"), "etudes_recues": len(etudes),
               "etudes_exportees": len(valides), "etudes_rejetees": len(rejets), "rejets": rejets,
               "controles": ["champs obligatoires : " + ", ".join(OBLIGATOIRES), "dates valides (format et calendrier)",
                             "date de détection pas dans le futur", "identifiants uniques", "DOI uniques"]}
    return valides, rapport


def ecrire(nom, contenu):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER / nom
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(contenu, ensure_ascii=False) + "\n", encoding="utf-8")
    temporaire.replace(chemin)  # écriture atomique : jamais de fichier à moitié écrit en ligne


def exporter_tables(conn, limite_evenements=500):
    """Exports techniques lus par les pages Alertes et Pipeline : événements, exécutions, sources."""
    evenements = [dict(r) for r in conn.execute(
        "SELECT id, type, objet_type, objet_id, champ, avant, apres, titre, date_detection, execution_id, envoye "
        "FROM evenements WHERE execution_id IS NOT 'migration' ORDER BY date_detection DESC, id DESC LIMIT ?",
        (limite_evenements,))]
    executions = [dict(r) for r in conn.execute(
        "SELECT execution_id, source, debut, fin, statut, nb_elements, erreurs FROM executions "
        "ORDER BY id DESC LIMIT 300")]
    comptes = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
               for t in ("essais", "versions_essais", "articles", "evenements", "executions", "traitements_ia")}
    ecrire("evenements.json", {"evenements": evenements})
    ecrire("executions.json", {"executions": executions, "tables": comptes})
    return comptes
