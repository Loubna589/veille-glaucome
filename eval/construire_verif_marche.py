"""Construit eval/verif_marche.csv : 20 médicaments × nos valeurs extraites, à vérifier à la main.

Lancement :  python eval/construire_verif_marche.py   (ne remplace pas un fichier déjà vérifié)

Une ligne par VALEUR à contrôler (date d'AMM, SMR et sa date, ASMR et sa date, taux de remboursement, prix),
avec le lien vers la source officielle pour vérifier. Colonne `verifie_loubna` VIDE :
  1 = la valeur affichée par l'outil est exacte ; 0 = elle est fausse (préciser dans `commentaire`).
Ensuite : python eval/evaluer_verif_marche.py → taux de concordance global et par type de valeur.

Sélection : 2 médicaments par molécule suivie (ceux qui ont un avis HAS d'abord), jusqu'à 20, ordre fixe.
"""
import csv
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FICHIER = RACINE / "eval" / "verif_marche.csv"
COLONNES = ["medicament_id", "molecule", "medicament", "champ", "valeur_outil", "source", "lien_verification",
            "verifie_loubna", "commentaire"]
TAILLE = 20


def lignes_medicament(molecule, s):
    smr, asmr = (s.get("smr") or [None])[0], (s.get("asmr") or [None])[0]
    pres = [p for p in s.get("presentations") or [] if p.get("statut") == "Présentation active"]
    p = pres[0] if pres else {}
    valeurs = [
        ("date_amm", s.get("date_amm"), "BDPM", s.get("lien")),
        ("smr_valeur", smr and smr.get("valeur"), "HAS (via BDPM)", (smr or {}).get("lien") or s.get("lien")),
        ("smr_date", smr and smr.get("date"), "HAS (via BDPM)", (smr or {}).get("lien") or s.get("lien")),
        ("asmr_valeur", asmr and asmr.get("valeur"), "HAS (via BDPM)", (asmr or {}).get("lien") or s.get("lien")),
        ("taux_remboursement", p.get("taux_remboursement"), "BDPM", s.get("lien")),
        ("prix", p.get("prix"), "BDPM", s.get("lien")),
    ]
    return [{"medicament_id": s["cis"], "molecule": molecule, "medicament": s["nom"], "champ": champ,
             "valeur_outil": "" if valeur is None else valeur, "source": source, "lien_verification": lien,
             "verifie_loubna": "", "commentaire": ""} for champ, valeur, source, lien in valeurs if valeur not in (None, "")]


def construire(marche):
    # Tour par tour entre les molécules (1 médicament de chaque, puis un 2e, etc.) : un jeu varié de 20 médicaments
    files = [[(molecule, s) for s in sorted(m.get("france") or [], key=lambda s: (not s.get("smr"), s["nom"]))]
             for molecule, m in marche["molecules"].items()]
    choisis, rang = [], 0
    while len(choisis) < TAILLE and any(len(f) > rang for f in files):
        choisis += [f[rang] for f in files if len(f) > rang][:TAILLE - len(choisis)]
        rang += 1
    return [l for molecule, s in choisis for l in lignes_medicament(molecule, s)], len(choisis)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if FICHIER.exists() and any((l.get("verifie_loubna") or "").strip()
                                for l in csv.DictReader(FICHIER.open(encoding="utf-8-sig"), delimiter=";")):
        print(f"{FICHIER.name} contient déjà des vérifications : il n'est pas remplacé.")
        return 0
    marche = json.loads((RACINE / "data" / "historique" / "marche.json").read_text(encoding="utf-8"))
    lignes, nb = construire(marche)
    with FICHIER.open("w", encoding="utf-8-sig", newline="") as f:
        ecriture = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        ecriture.writeheader()
        ecriture.writerows(lignes)
    print(f"{nb} médicaments, {len(lignes)} valeurs à vérifier écrites dans {FICHIER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
