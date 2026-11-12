"""Frise des délais d'accès au marché : pour chaque molécule, les étapes datées par les sources, dans l'ordre.

Règle : UNIQUEMENT des dates déclarées par les sources. Une étape sans date reste vide (affichée
« non déclarée »), et n'entre pas dans le calcul des délais.

Étapes (première date connue pour la molécule) :
  FDA (États-Unis)        1re approbation d'un médicament de marque (NDA) ; à défaut, 1re approbation
  EMA (Union européenne)  1re autorisation en procédure centralisée
  Suisse (Swissmedic)     1re autorisation
  Espagne (AEMPS)         1re autorisation
  Canada (Santé Canada)   1re commercialisation déclarée (la DPD ne publie pas de date d'autorisation)
  Australie (PBS)         1re inscription au remboursement (si la clé PBS est configurée)
  France — AMM            1re autorisation de mise sur le marché (BDPM)
  France — avis HAS       1er avis de la Commission de la transparence (SMR)
  France — remboursement  taux déclaré par la BDPM ; la BDPM ne date pas l'inscription au remboursement
  Italie — remboursement  classe A/H (AIFA) ; les listes ne datent pas l'inscription

Délai entre deux étapes datées consécutives = nombre de mois (jours / 30,44, arrondi).
"""
from datetime import date


def _date(texte):
    try:
        a, m, j = (int(x) for x in texte[:10].split("-"))
        return date(a, m, j)
    except (AttributeError, ValueError, TypeError):
        return None


def mois_entre(debut, fin):
    """Nombre de mois (arrondi) entre deux dates ISO."""
    d1, d2 = _date(debut), _date(fin)
    if not d1 or not d2:
        return None
    return round((d2 - d1).days / 30.44)


def _premiere(elements, champ, filtre=None):
    """(date la plus ancienne, élément correspondant) parmi les éléments datés qui passent le filtre."""
    dates = [(e[champ], e) for e in elements if e.get(champ) and _date(e[champ]) and (filtre is None or filtre(e))]
    return min(dates, key=lambda x: x[0]) if dates else (None, None)


def etapes_molecule(m):
    usa, ue = m.get("usa") or [], m.get("ue") or []
    fr = m.get("france") or []
    d_fda, e_fda = _premiere(usa, "date_approbation", lambda e: str(e.get("numero", "")).startswith("NDA"))
    if not d_fda:
        d_fda, e_fda = _premiere(usa, "date_approbation")
    d_ema, e_ema = _premiere(ue, "date_autorisation")
    d_ch, e_ch = _premiere(m.get("suisse") or [], "date_autorisation")
    d_es, e_es = _premiere(m.get("espagne") or [], "date_autorisation")
    d_ca, e_ca = _premiere(m.get("canada") or [], "date_commercialisation")
    d_au, e_au = _premiere(m.get("australie") or [], "date_inscription")
    d_amm, e_amm = _premiere(fr, "date_amm")
    # Avis HAS : la HAS ne déclare pas de titulaire ; on reprend celui que la BDPM déclare pour la spécialité évaluée
    avis = [dict(a, specialite=s.get("nom"),
                 laboratoire=dict(s["laboratoire"], champ="BDPM — titulaire de la spécialité évaluée") if s.get("laboratoire") else None)
            for s in fr for a in (s.get("smr") or [])]
    d_has, e_has = _premiere(avis, "date")
    rembourses = [s for s in fr if any(p.get("taux_remboursement") and p.get("statut") == "Présentation active"
                                       for p in s.get("presentations") or [])]
    taux = sorted({p.get("taux_remboursement") for s in fr for p in s.get("presentations") or []
                   if p.get("taux_remboursement") and p.get("statut") == "Présentation active"})
    classes = sorted({e.get("classe") for e in m.get("italie") or [] if e.get("classe")})

    def labos(elements):
        """Étapes qui regroupent plusieurs produits : liste des laboratoires déclarés (sans doublon)."""
        vus = {}
        for e in elements:
            lab = e.get("laboratoire") or {}
            if lab.get("declare"):
                vus.setdefault(lab["declare"], lab)
        return sorted(vus.values(), key=lambda x: (x.get("groupe") or "", x["declare"]))

    def etape(cle, pays, libelle, d, element, detail=None, lien=None, laboratoires=None):
        sortie = {"cle": cle, "pays": pays, "libelle": libelle, "date": d,
                  "detail": detail if detail is not None else (element or {}).get("nom") or (element or {}).get("specialite"),
                  "lien": lien if lien is not None else (element or {}).get("lien")}
        if laboratoires is not None:
            sortie["laboratoires"] = laboratoires
        elif element is not None:
            sortie["laboratoire"] = element.get("laboratoire")
        return sortie

    return [
        etape("fda", "États-Unis", "Approbation FDA", d_fda, e_fda,
              detail=(", ".join(e_fda.get("marques") or []) if e_fda else None)),
        etape("ema", "Union européenne", "Autorisation EMA", d_ema, e_ema),
        etape("suisse", "Suisse", "Autorisation Swissmedic", d_ch, e_ch),
        etape("espagne", "Espagne", "Autorisation AEMPS", d_es, e_es),
        etape("canada", "Canada", "1re commercialisation", d_ca, e_ca),
        etape("australie", "Australie", "Inscription au PBS (remboursement)", d_au, e_au),
        etape("france_amm", "France", "AMM", d_amm, e_amm),
        etape("france_has", "France", "Avis HAS (SMR)", d_has, e_has,
              detail=(f"SMR {e_has.get('valeur')} — {e_has.get('specialite')}" if e_has else None)),
        etape("france_remb", "France", "Remboursement", None, None,
              detail=("taux " + " · ".join(taux) + " (date d'inscription non publiée par la BDPM)") if taux else None,
              laboratoires=labos(rembourses)),
        etape("italie_remb", "Italie", "Remboursement", None, None,
              detail=("classe " + " · ".join(classes) + " (date d'inscription non publiée par l'AIFA)") if classes else None,
              laboratoires=labos(m.get("italie") or [])),
    ]


def frise(m):
    """Étapes datées dans l'ordre chronologique, avec le délai (mois) depuis l'étape précédente et depuis la première."""
    etapes = etapes_molecule(m)
    datees = sorted((e for e in etapes if e["date"]), key=lambda e: e["date"])
    for i, e in enumerate(datees):
        e["mois_depuis_precedente"] = mois_entre(datees[i - 1]["date"], e["date"]) if i else None
        e["mois_depuis_premiere"] = mois_entre(datees[0]["date"], e["date"])
    non_datees = [e for e in etapes if not e["date"]]
    return {"datees": datees, "non_datees": non_datees,
            "duree_totale_mois": mois_entre(datees[0]["date"], datees[-1]["date"]) if len(datees) > 1 else None}


def calculer(marche):
    return {nom: frise(m) for nom, m in (marche or {}).get("molecules", {}).items()}
