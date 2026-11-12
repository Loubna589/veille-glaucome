"""Collecte « accès au marché » : France (BDPM), Union européenne (EMA), États-Unis (openFDA).

Lancement :  python collecter_marche.py      (les trois sources sont aussi lancées, une par une
                                              et journalisées, par mise_a_jour.py)

Pour chaque molécule de config/marche.ini, on enregistre ce que chaque source DÉCLARE.
Résultat : data/historique/marche.json. Une source en panne n'empêche pas les autres :
on garde alors ses données de la collecte précédente, signalées avec leur date.
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import marche_commun as mc  # noqa: E402
from veille.sources import bdpm, canada, ema, espagne, italie, openfda, pbs, suisse  # noqa: E402

FICHIER = Path(__file__).resolve().parent / "data" / "historique" / "marche.json"
SOURCES = [("france", "BDPM (France)", bdpm), ("ue", "EMA (Union européenne)", ema), ("usa", "openFDA (États-Unis)", openfda),
           ("canada", "Santé Canada DPD", canada), ("espagne", "AEMPS CIMA (Espagne)", espagne),
           ("italie", "AIFA (Italie)", italie), ("suisse", "Swissmedic (Suisse)", suisse),
           ("australie", "PBS (Australie)", pbs)]

# Pays étudiés mais NON automatisés : la raison exacte, affichée sur la page « Autorisations & remboursement »
NON_COUVERTS = [
    {"pays": "Australie — autorisations (TGA)", "sources": "TGA (ARTG)",
     "raison": "Le registre ARTG de la TGA n'a pas d'API publique et son site n'a pas répondu aux requêtes automatiques. "
               "Le remboursement australien (PBS), lui, est couvert dès que la clé publique PBS est dans .env."},
    {"pays": "Royaume-Uni", "sources": "MHRA · NICE",
     "raison": "L'API de NICE est réservée aux organisations (pas aux particuliers ni aux étudiants), avec certification "
               "de cybersécurité (Cyber Essentials Plus ou ISO 27001), licence et redevance hors Royaume-Uni ; l'usage "
               "d'IA sur ses contenus exige cette licence. La MHRA ne publie ses autorisations que sous forme de pages web "
               "et de documents, sans API ni fichier ouvert."},
    {"pays": "Allemagne", "sources": "G-BA (évaluation AMNOG)",
     "raison": "Les évaluations du bénéfice sont publiées en pages web et PDF, sans API ni fichier de données ; "
               "les extraire demanderait un scraping fragile."},
    {"pays": "Japon", "sources": "PMDA",
     "raison": "Moteur de recherche web en japonais, sans API ni fichier de données téléchargeable ; "
               "pas d'accès automatisable stable."},
]


def lire():
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {}


def enregistrer_source(cle, donnees, source):
    """Remplace dans marche.json les données d'UNE source (les autres sont conservées)."""
    sortie = lire()
    sortie["collecte_le"] = time.strftime("%Y-%m-%d")
    sortie["non_couverts"] = NON_COUVERTS
    sortie.setdefault("sources", {})[cle] = dict(source, ok=True)
    molecules = sortie.setdefault("molecules", {})
    for m in mc.charger_molecules():
        molecules.setdefault(m["nom"], {"substances": sorted(m["substances"])})[cle] = donnees.get(m["nom"], [])
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def noter_saute(cle, libelle, raison):
    """Source volontairement non collectée (ex. clé facultative absente) : la page l'explique."""
    sortie = lire()
    sortie["non_couverts"] = NON_COUVERTS
    sortie.setdefault("sources", {})[cle] = {"nom": libelle, "ok": False, "saute": True, "erreur": str(raison)}
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def collecter():
    molecules = mc.charger_molecules()
    echecs = []
    for cle, libelle, module in SOURCES:
        try:
            donnees, source = module.collecter(molecules)
            enregistrer_source(cle, donnees, source)
            print(f"  [OK] {libelle} : {sum(len(v) for v in donnees.values())} médicament(s) rattaché(s)")
        except pbs.CleAbsente as absente:
            noter_saute(cle, libelle, absente)
            print(f"  [SAUTÉ] {libelle} : {absente}")
        except (requests.exceptions.RequestException, ValueError, KeyError) as erreur:
            echecs.append(libelle)
            sortie = lire()
            if cle in sortie.get("sources", {}):
                sortie["sources"][cle].update(ok=False, erreur=str(erreur)[:300])
                FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  [ÉCHEC] {libelle} : {erreur} — données précédentes conservées")
    return {"echecs": echecs}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("Collecte accès au marché (BDPM, EMA, openFDA)")
    sortie = collecter()
    return 1 if len(sortie["echecs"]) == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
