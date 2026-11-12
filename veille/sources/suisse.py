"""Suisse : liste étendue des médicaments à usage humain autorisés par Swissmedic (fichier Excel public).

Source : https://www.swissmedic.ch/swissmedic/fr/home/services/listen_neu.html
(« Liste étendue des médicaments à usage humain ») : n° d'autorisation, titulaire, code ATC,
date de première autorisation, principes actifs (en latin, ex. « netarsudilum, latanoprostum »).

On garde les produits de classe ATC S01E (antiglaucomateux et myotiques) et on rattache par les
principes actifs déclarés. L'adresse du fichier est lue sur la page officielle (lien de téléchargement).
"""
import io
import re
import time

from veille import marche_commun as mc

PAGE = "https://www.swissmedic.ch/swissmedic/fr/home/services/listen_neu.html"
BASE = "https://www.swissmedic.ch"
MOTIF = re.compile(r'href="([^"]*erweiterte_ham_ind\.xlsx[^"]*)"')
suivi = {"appels_reseau": 0, "depuis_cache": 0}


def date_texte(valeur):
    if valeur is None:
        return None
    if hasattr(valeur, "strftime"):
        return valeur.strftime("%Y-%m-%d")
    return mc.date_iso(str(valeur)) or None


def collecter(molecules):
    import openpyxl  # lecture des fichiers Excel (dépendance légère, en pur Python)

    page = mc.decoder(mc.telecharger(PAGE, "swissmedic_page.html", suivi))
    lien = MOTIF.search(page)
    if not lien:
        raise ValueError("Swissmedic : lien vers la liste étendue introuvable sur la page (format modifié ?)")
    contenu = mc.telecharger(BASE + lien.group(1), "swissmedic_etendue.xlsx", suivi)
    lignes = list(openpyxl.load_workbook(io.BytesIO(contenu), read_only=True).active.iter_rows(values_only=True))
    entete = next(i for i, l in enumerate(lignes) if l and str(l[0] or "").lower().startswith("zulassungs"))
    titres = [re.sub(r"\s+", " ", str(x or "")).lower() for x in lignes[entete]]

    def colonne(debut):
        return next(i for i, t in enumerate(titres) if t.startswith(debut))

    c_num, c_nom, c_titulaire = colonne("zulassungs"), colonne("bezeichnung"), colonne("zulassungsinhaberin")
    c_atc, c_date, c_actifs, c_statut = colonne("atc"), colonne("erstzulassungs"), colonne("wirkstoff"), colonne("zulassungsstatus")
    resultat = {m["nom"]: {} for m in molecules}
    for l in lignes[entete + 1:]:
        if not l or not str(l[c_atc] or "").upper().startswith("S01E"):
            continue
        molecule = mc.rattacher(str(l[c_actifs] or "").split(","), molecules)
        if not molecule:
            continue
        numero = str(l[c_num])
        resultat[molecule["nom"]].setdefault(numero, {
            "nom": str(l[c_nom] or "").strip(), "numero": numero, "titulaire": str(l[c_titulaire] or "").strip(),
            "atc": l[c_atc], "date_autorisation": date_texte(l[c_date]), "statut": l[c_statut],
            "substances": l[c_actifs],
        })
    sortie = {nom: sorted(d.values(), key=lambda x: x["date_autorisation"] or "9999") for nom, d in resultat.items()}
    source = {"nom": "Swissmedic — liste étendue des médicaments autorisés (Suisse)", "url": PAGE,
              "telecharge_le": time.strftime("%Y-%m-%d")}
    return sortie, source
