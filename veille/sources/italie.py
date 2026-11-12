"""Italie : listes AIFA des médicaments remboursés — classe A (remboursés par le SSN) et classe H (usage hospitalier).

Source : https://www.aifa.gov.it/liste-farmaci-a-h — fichiers CSV publics « per principio attivo »,
mis à jour régulièrement (la date figure dans le nom du fichier). Les adresses des fichiers
changent à chaque mise à jour : on lit la page officielle pour trouver les liens .csv
(simple lecture des liens, pas d'extraction de contenu de page).

On garde les présentations « USO OFTALMICO » et on rattache par le principe actif déclaré
(« Dorzolamide/timololo » → dorzolamide + timolol). Ces listes ne donnent PAS de date
d'autorisation : on affiche la classe de remboursement, le prix public et la date de la liste.
"""
import csv
import io
import re
import time

from veille import marche_commun as mc
from veille import reseau

PAGE = "https://www.aifa.gov.it/liste-farmaci-a-h"
BASE = "https://www.aifa.gov.it"
MOTIF = re.compile(r'href="(/documents/[^"]*Classe-([AH])_per_principio-attivo_([\d-]+)\.csv)"')
suivi = {"appels_reseau": 0, "depuis_cache": 0}


def date_liste(texte):
    """« 30-6-2026 » → « 2026-06-30 »."""
    j, m, a = (int(x) for x in texte.split("-"))
    return f"{a:04d}-{m:02d}-{j:02d}"


def nombre(texte):
    try:
        return float((texte or "").replace(".", "").replace(",", "."))
    except ValueError:
        return None


ENTETES = {"principe": "principio attivo", "groupe": "descrizione gruppo", "nom": "denominazione e confezione",
           "prix": "prezzo al pubblico", "titulaire": "titolare aic", "aic": "aic"}


def colonnes(entete):
    """Position de chaque colonne utile d'après l'en-tête (« Titolare AIC » = titulaire déclaré par l'AIFA)."""
    propre = [" ".join((e or "").strip().strip('"').lower().split()) for e in entete]  # « Codice \nAIC » → « codice aic »
    pos = {}
    for cle, debut in ENTETES.items():
        trouve = [i for i, e in enumerate(propre) if (e in ("aic", "codice aic") if cle == "aic" else e.startswith(debut))]
        if not trouve:
            raise ValueError(f"AIFA : colonne « {debut} » absente de l'en-tête (format modifié ?)")
        pos[cle] = trouve[0]
    return pos


def lire_csv(contenu):
    texte = mc.decoder(contenu)
    return list(csv.reader(io.StringIO(texte), delimiter=";"))


def collecter(molecules):
    page = mc.decoder(mc.telecharger(PAGE, "aifa_page.html", suivi))
    liens = {}
    for chemin, classe, date in MOTIF.findall(page):
        liens.setdefault(classe, (chemin, date))
    if not liens:
        raise ValueError("AIFA : aucun fichier CSV trouvé sur la page des listes (format de page modifié ?)")
    resultat = {m["nom"]: [] for m in molecules}
    dates = {}
    for classe, (chemin, date) in sorted(liens.items()):
        dates[classe] = date_liste(date)
        lignes = lire_csv(mc.telecharger(BASE + chemin, f"aifa_classe_{classe}.csv", suivi))
        if not lignes:
            continue
        # Les fichiers A et H n'ont pas les mêmes colonnes (H ajoute les prix ex-factory) : lecture par nom de colonne
        col = colonnes(lignes[0])
        for l in lignes[1:]:
            if len(l) <= max(col.values()) or "OFTALMIC" not in (l[col["groupe"]] or "").upper():
                continue
            molecule = mc.rattacher(l[col["principe"]].split("/"), molecules)
            if not molecule:
                continue
            resultat[molecule["nom"]].append({
                "nom": l[col["nom"]].strip(), "groupe": l[col["groupe"]].strip(), "classe": classe,
                "remboursement": "classe A — remboursé par le SSN" if classe == "A" else "classe H — usage hospitalier",
                "prix": nombre(l[col["prix"]]), "titulaire": l[col["titulaire"]].strip() or None, "aic": l[col["aic"]].strip(),
                "date_liste": dates[classe],
            })
    for liste in resultat.values():
        liste.sort(key=lambda x: (x["classe"], x["prix"] if x["prix"] is not None else 9e9))
    source = {"nom": "AIFA — listes des médicaments de classe A et H (Italie)", "url": PAGE,
              "telecharge_le": time.strftime("%Y-%m-%d"), "dates_listes": dates}
    return resultat, source
