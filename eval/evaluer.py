"""Évalue la classification : matrice de confusion et F1 macro, à partir de eval/jeu_etiquete.csv.

Lancement :  python eval/evaluer.py

Vérité terrain : la colonne `etiquette_loubna` (remplie à la main). Sont comparées à elle :
1. `etiquette_proposee` : les règles de l'outil ;
2. la catégorie donnée par l'IA (table traitements_ia de la base), si l'IA a déjà traité ces publications.

F1 macro = moyenne, sur les catégories, de F1 = 2 × précision × rappel / (précision + rappel).
Chaque catégorie compte autant, même rare : c'est plus exigeant que l'exactitude simple.
"""
import csv
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from veille import base, resumer_ia  # noqa: E402

FICHIER = RACINE / "eval" / "jeu_etiquete.csv"
CATEGORIES = list(resumer_ia.CATEGORIES)


def matrice_confusion(vrais, predits, categories=CATEGORIES):
    """matrice[vrai][prédit] = nombre de publications."""
    m = {v: {p: 0 for p in categories} for v in categories}
    for v, p in zip(vrais, predits):
        m[v][p] += 1
    return m


def f1_macro(vrais, predits, categories=CATEGORIES):
    """(F1 macro, détail par catégorie). Les catégories absentes à la fois de la vérité et des
    prédictions sont ignorées (elles n'apportent aucune information)."""
    detail, f1_exacts = {}, []
    for c in categories:
        vp = sum(1 for v, p in zip(vrais, predits) if v == c and p == c)
        fp = sum(1 for v, p in zip(vrais, predits) if v != c and p == c)
        fn = sum(1 for v, p in zip(vrais, predits) if v == c and p != c)
        if vp + fp + fn == 0:
            continue
        precision = vp / (vp + fp) if vp + fp else 0.0
        rappel = vp / (vp + fn) if vp + fn else 0.0
        f1 = 2 * precision * rappel / (precision + rappel) if precision + rappel else 0.0
        detail[c] = {"precision": round(precision, 3), "rappel": round(rappel, 3), "f1": round(f1, 3), "effectif": vp + fn}
        f1_exacts.append(f1)
    macro = sum(f1_exacts) / len(f1_exacts) if f1_exacts else 0.0  # moyenne des valeurs EXACTES, arrondie à la fin
    return round(macro, 3), detail


def afficher(nom, vrais, predits):
    macro, detail = f1_macro(vrais, predits)
    exactitude = sum(v == p for v, p in zip(vrais, predits)) / len(vrais)
    print(f"\n=== {nom} — {len(vrais)} publications · exactitude {exactitude:.0%} · F1 macro {macro:.3f} ===")
    m = matrice_confusion(vrais, predits)
    courts = {c: c[:10] for c in CATEGORIES}
    print("vrai \\ prédit".ljust(26) + "".join(courts[c].rjust(11) for c in CATEGORIES))
    for v in CATEGORIES:
        print(v.ljust(26) + "".join(str(m[v][p]).rjust(11) for p in CATEGORIES))
    for c, d in detail.items():
        print(f"  {c:26} précision {d['precision']:.2f} · rappel {d['rappel']:.2f} · F1 {d['f1']:.2f} (n={d['effectif']})")
    return {"f1_macro": macro, "exactitude": round(exactitude, 3), "detail": detail, "matrice": m}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    lignes = list(csv.DictReader(FICHIER.open(encoding="utf-8-sig"), delimiter=";"))
    etiquetees = [l for l in lignes if (l.get("etiquette_loubna") or "").strip()]
    if not etiquetees:
        print(f"Aucune étiquette dans la colonne etiquette_loubna de {FICHIER.name} ({len(lignes)} lignes) : "
              "remplissez-la avec l'une des catégories " + ", ".join(CATEGORIES))
        return 0
    inconnues = [l["etiquette_loubna"] for l in etiquetees if l["etiquette_loubna"].strip() not in CATEGORIES]
    if inconnues:
        print(f"Étiquettes hors liste à corriger : {sorted(set(inconnues))}")
        return 1
    vrais = [l["etiquette_loubna"].strip() for l in etiquetees]
    resultats = {"regles": afficher("Règles de l'outil (etiquette_proposee)", vrais, [l["etiquette_proposee"] for l in etiquetees])}
    ia = resumer_ia.charger(base.connecter())
    avec_ia = [l for l in etiquetees if l["id"] in ia]
    if avec_ia:
        resultats["ia"] = afficher(f"IA ({ia[avec_ia[0]['id']]['modele']}, {ia[avec_ia[0]['id']]['version_prompt']})",
                                   [l["etiquette_loubna"].strip() for l in avec_ia], [ia[l["id"]]["categorie"] for l in avec_ia])
    else:
        print("\n(L'IA n'a encore traité aucune de ces publications : évaluation IA disponible après un passage sur GitHub Actions.)")
    (RACINE / "eval" / "resultats.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRésultats enregistrés dans eval/resultats.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
