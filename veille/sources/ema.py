"""Accès au marché dans l'Union européenne : Agence européenne des médicaments (EMA).

Source officielle, gratuite, sans clé : le rapport « Medicines » publié chaque jour par
l'EMA (le même contenu existe en Excel ; on lit la version JSON, plus simple) :
https://www.ema.europa.eu/en/about-us/about-website/download-website-data-json-data-format

Ce fichier ne contient que les médicaments évalués par l'EMA (procédure CENTRALISÉE).
Beaucoup de collyres du glaucome ont été autorisés pays par pays (procédures nationales,
de reconnaissance mutuelle ou décentralisée) : ils n'y figurent pas. « Absent du fichier
EMA » ne veut donc PAS dire « non autorisé en Europe ».
"""
import json
import time

from veille import marche_commun as mc

URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
PAGE = "https://www.ema.europa.eu/en/medicines/download-medicine-data"
suivi = {"appels_reseau": 0, "depuis_cache": 0}
OPHTALMO = ("glaucoma", "ocular hypertension", "ophthalmolog")


def substances(m):
    """Substances déclarées : champ « active_substance », séparateur « ; »."""
    brut = m.get("active_substance") or m.get("international_non_proprietary_name_common_name") or ""
    return [s for s in brut.replace("/", ";").replace(",", ";").split(";") if s.strip()]


def collecter(molecules):
    """Médicaments à usage humain de l'EMA rattachés aux molécules suivies."""
    donnees = json.loads(mc.decoder(mc.telecharger(URL, "ema_medicines.json", suivi)))
    medicaments = donnees.get("data", donnees) if isinstance(donnees, dict) else donnees
    resultat = {m["nom"]: [] for m in molecules}
    for m in medicaments:
        if m.get("category") != "Human":
            continue
        domaine = " ".join(str(m.get(c) or "") for c in ("therapeutic_area_mesh", "pharmacotherapeutic_group_human",
                                                           "therapeutic_indication")).lower()
        if not any(mot in domaine for mot in OPHTALMO):
            continue
        molecule = mc.rattacher(substances(m), molecules)
        if not molecule:
            continue
        resultat[molecule["nom"]].append({
            "nom": m.get("name_of_medicine"), "numero": m.get("ema_product_number"),
            "statut": m.get("medicine_status") or None, "titulaire": m.get("marketing_authorisation_developer_applicant_holder") or None,
            "substances": substances(m), "generique": m.get("generic") == "Yes",
            "date_autorisation": mc.date_iso(m.get("marketing_authorisation_date")),
            "date_avis_chmp": mc.date_iso(m.get("opinion_adopted_date")),
            "date_retrait": mc.date_iso(m.get("withdrawal_expiry_revocation_lapse_of_marketing_authorisation_date")),
            "date_mise_a_jour": mc.date_iso(m.get("last_updated_date")),
            "lien": m.get("medicine_url") or None,
        })
    for liste in resultat.values():
        liste.sort(key=lambda x: x["date_autorisation"] or "9999")
    meta = donnees.get("meta", {}) if isinstance(donnees, dict) else {}
    source = {"nom": "EMA — rapport « Medicines » (procédure centralisée)", "url": PAGE,
              "telecharge_le": time.strftime("%Y-%m-%d"), "meta": meta}
    return resultat, source
