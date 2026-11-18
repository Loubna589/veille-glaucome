"""E-mail « Un essai a changé d'étape » : au plus un par jour, seulement s'il y a un changement d'étape.

Étapes suivies (déclarées par ClinicalTrials.gov, jamais déduites) : statut (ouvert, recrute, terminé, arrêté…),
phase, et résultats déposés au registre. Les autres changements (date de fin, nombre de participants) restent
sur la page Alertes et dans l'e-mail de la semaine.
"""
from veille import alertes
from veille.synthese import STATUTS_FR, phase_lisible

TYPES_ETAPE = ("changement_statut", "changement_phase", "resultats_deposes")
SITE = "https://loubna589.github.io/veille-glaucome/"


def ce_qui_change(ev):
    if ev["type"] == "resultats_deposes":
        return "les résultats viennent d'être publiés sur le registre"
    if ev["type"] == "changement_phase":
        return f"passe de la {phase_lisible(ev.get('avant'))} à la {phase_lisible(ev.get('apres'))}"
    return f"{STATUTS_FR.get(ev.get('avant'), ev.get('avant') or '?')} → {STATUTS_FR.get(ev.get('apres'), ev.get('apres') or '?')}"


def pourquoi(ev):
    t, apres = ev["type"], ev.get("apres") or ""
    if t == "resultats_deposes":
        return "On peut voir si le traitement a marché, souvent avant tout article scientifique."
    if t == "changement_phase":
        return ("Le produit entre dans la dernière étape avant une demande d'autorisation." if "3" in apres
                else "Le produit avance vers une phase plus avancée : il se rapproche du marché.")
    return {
        "RECRUITING": "L'essai commence à inclure des patients : le projet est lancé pour de bon.",
        "ENROLLING_BY_INVITATION": "L'essai commence à inclure des patients (sur invitation).",
        "ACTIVE_NOT_RECRUITING": "Tous les patients sont inclus : les résultats approchent.",
        "COMPLETED": "L'essai est terminé : résultats, publication et peut-être demande d'autorisation peuvent suivre.",
        "TERMINATED": "Arrêt avant la fin : souvent un signal (efficacité, sécurité, manque de patients ou de budget) à surveiller.",
        "WITHDRAWN": "L'essai est retiré avant d'avoir commencé : le projet est abandonné ou repoussé.",
        "SUSPENDED": "L'essai est mis en pause : à surveiller, la raison est parfois donnée sur le registre.",
    }.get(apres, "Le statut de l'essai a changé : à regarder sur sa fiche.")


def texte(evenements, site=SITE):
    par_essai = {}
    for ev in evenements:
        par_essai.setdefault(ev["objet_id"], []).append(ev)
    lignes = [f"Bonjour, {len(par_essai)} essai(s) suivi(s) ont changé d'étape depuis hier.", ""]
    for i, (nct, evs) in enumerate(par_essai.items(), 1):
        lignes.append(f"{i}. {(evs[0].get('titre') or nct)[:140]}")
        for ev in evs:
            lignes += [f"   Ce qui change : {ce_qui_change(ev)}", f"   Pourquoi c'est important : {pourquoi(ev)}"]
        lignes += [f"   Fiche : {site}fiches/{nct}.html", f"   Registre : https://clinicaltrials.gov/study/{nct}", ""]
    lignes += ["Tous les changements (dates, participants…) : " + site + "alertes.html", "",
               "Message automatique de Glaucoma Intelligence : au plus un par jour, seulement quand un essai change d'étape."]
    return "\n".join(lignes)


def envoyer(evenements):
    """Envoie l'e-mail du jour s'il y a des changements d'étape. Renvoie le nombre d'essais signalés (0 sinon)."""
    etapes = [ev for ev in evenements if ev["type"] in TYPES_ETAPE]
    if not etapes or not alertes.mail_configure():
        return 0
    n = len({ev["objet_id"] for ev in etapes})
    alertes.envoyer_mail(texte(etapes), n, sujet=f"Veille glaucome : {n} essai(s) ont changé d'étape")
    return n
