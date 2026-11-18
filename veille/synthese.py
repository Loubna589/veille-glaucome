"""« Ce qu'il faut retenir cette semaine » : 5 points clés sur les 7 derniers jours, avec leurs sources.

1. SÉLECTION (règles fixes, sans IA) : nouveaux essais publiés sur ClinicalTrials.gov, changements d'essais
   (statut, date de fin, recrutement, résultats déposés) et articles entrés dans PubMed pendant la semaine.
   Chaque élément reçoit un score explicable (résultats déposés, essai terminé, phase 3, produit suivi, essai
   randomisé, méta-analyse…). Les 25 meilleurs sont gardés.
2. RÉDACTION (IA, si une clé Gemini ou Mistral existe) : le modèle écrit 5 points en français À PARTIR DE CES
   SEULS ÉLÉMENTS, chaque point citant ses identifiants (PMID ou NCT). Les citations sont vérifiées : un point qui
   cite un identifiant absent de la liste est rejeté.
3. SECOURS : sans clé, ou si la réponse ne passe pas la vérification, les 5 points sont écrits par des règles
   fixes à partir des 5 éléments les mieux classés. Le site indique toujours lequel des deux modes a servi.
"""
import json
import re
from datetime import date, timedelta

from veille import fournisseur_ia, reseau

VERSION_PROMPT = "semaine_v1"
NB_POINTS = 5
NB_CANDIDATS = 25
MOTIF_ID = re.compile(r"\b(NCT\d{8}|PMID:\d+|W\d{6,})\b")

LIBELLES_CHANGEMENT = {
    "changement_statut": "changement de statut", "changement_date_fin": "nouvelle date de fin",
    "changement_recrutement": "recrutement modifié", "changement_phase": "changement de phase",
    "resultats_deposes": "résultats déposés au registre",
}

PROMPT = """Tu rédiges la synthèse hebdomadaire d'une veille sur le glaucome pour une chef de produit pharmaceutique.
On te donne une liste d'ÉLÉMENTS de la semaine (essais cliniques et articles), chacun avec son identifiant entre crochets.

Règles :
- Écris EXACTEMENT 5 points, du plus important au moins important pour un laboratoire pharmaceutique
  (nouveaux traitements, résultats d'essais, essais qui se terminent ou changent, concurrence, tendances).
- Utilise UNIQUEMENT les informations des éléments. N'ajoute aucun chiffre, nom ou conclusion qui n'y figure pas.
- Chaque point cite au moins un identifiant de la liste, écrit exactement comme dans la liste (ex. NCT01234567, PMID:12345678).
- Phrases simples, en français, sans jargon inutile. Un point = un titre court (8 mots maximum) + 1 à 2 phrases.
- Si un élément est seulement un résumé d'article, dis « selon le résumé » ; ne présente pas un résultat comme établi.

Réponds par un objet JSON, et rien d'autre :
{"points": [{"titre": "...", "texte": "...", "sources": ["NCT…", "PMID:…"]}]}"""


def phase_lisible(phases):
    """'["PHASE2", "PHASE3"]' → « phase 2/3 » ; NA ou vide → « sans phase déclarée »."""
    codes = re.findall(r"PHASE(\d)", phases or "")
    return "phase " + "/".join(codes) if codes else "sans phase déclarée"


def couper(texte, n=320):
    """Coupe à la fin d'une phrase (ou d'un mot) avant n caractères."""
    texte = " ".join((texte or "").split())
    if len(texte) <= n:
        return texte
    coupe = texte[:n]
    fin = coupe.rfind(". ")
    return coupe[:fin + 1] if fin > n // 2 else coupe[:coupe.rfind(" ")] + "…"


def fenetre(jour=None, jours=7):
    fin = jour or date.today()
    return (fin - timedelta(days=jours - 1)).isoformat(), fin.isoformat()


def _j(texte):
    try:
        return json.loads(texte) if texte else {}
    except (TypeError, ValueError):
        return {}


def resumes_ia(conn):
    """Résumés IA déjà produits (3 lignes), par identifiant d'objet."""
    return {r[0]: _j(r[1]) for r in conn.execute("SELECT objet_id, resume FROM traitements_ia WHERE resume IS NOT NULL")}


def candidats(conn, debut, fin):
    """Éléments de la semaine, avec un score et la raison du score (aucune IA ici)."""
    ia, elements = resumes_ia(conn), []
    # 1. Nouveaux essais publiés pendant la semaine
    for nct, titre, statut, phases, promoteur, donnees in conn.execute(
            "SELECT nct, titre, statut, phases, promoteur, donnees FROM essais "
            "WHERE json_extract(donnees, '$.date_premiere_publication') BETWEEN ? AND ?", (debut, fin)):
        d = _j(donnees)
        phase = phases or ""
        score, raisons = 3, ["nouvel essai"]
        resume_essai = ia.get(nct)
        if "3" in phase:
            score, raisons = score + 3, raisons + ["phase 3"]
        elif "2" in phase:
            score, raisons = score + 2, raisons + ["phase 2"]
        if (d.get("type_promoteur") or "").upper() == "INDUSTRY":
            score, raisons = score + 2, raisons + ["promoteur industriel"]
        elements.append({"id": nct, "type": "essai", "score": score, "raisons": raisons, "titre": titre,
                         "lien": f"https://clinicaltrials.gov/study/{nct}", "fiche": None, "resume_fr": resume_essai,
                         "texte": f"Nouvel essai ({phase_lisible(phase)}, statut {statut or 'non précisé'}), "
                                  f"promoteur : {promoteur or 'non précisé'}. Interventions : "
                                  + ", ".join(i.get("nom", "") for i in (d.get("interventions") or [])[:4] if isinstance(i, dict))
                                  + ". " + " ".join(ia.get(nct) or [])})
    # 2. Changements d'essais détectés pendant la semaine (regroupés par essai)
    changements = {}
    for type_, nct, champ, avant, apres, titre in conn.execute(
            "SELECT type, objet_id, champ, avant, apres, titre FROM evenements WHERE objet_type = 'essai' "
            "AND type != 'nouvel_essai' AND substr(date_detection, 1, 10) BETWEEN ? AND ?", (debut, fin)):
        c = changements.setdefault(nct, {"titre": titre, "details": [], "score": 0, "raisons": []})
        c["details"].append(f"{LIBELLES_CHANGEMENT.get(type_, type_)} : {avant or '—'} → {apres or '—'}")
        bonus = 6 if type_ == "resultats_deposes" else 4 if apres in ("COMPLETED", "TERMINATED", "WITHDRAWN") else 2
        c["score"] += bonus
        c["raisons"].append(LIBELLES_CHANGEMENT.get(type_, type_))
    for nct, c in changements.items():
        if any(e["id"] == nct for e in elements):
            continue
        elements.append({"id": nct, "type": "essai", "score": c["score"], "raisons": c["raisons"], "titre": c["titre"],
                         "lien": f"https://clinicaltrials.gov/study/{nct}", "fiche": None,
                         "texte": "Changement sur un essai suivi : " + " ; ".join(c["details"])})
    # 3. Articles entrés dans PubMed pendant la semaine
    for pmid, titre, revue, donnees, annexes in conn.execute(
            "SELECT pmid, titre, revue, donnees, annexes FROM articles WHERE pmid IS NOT NULL "
            "AND json_extract(donnees, '$.date_entree_pubmed') BETWEEN ? AND ?", (debut, fin)):
        d, a = _j(donnees), _j(annexes)
        et = a.get("etiquettes") or {}
        types = " ".join(d.get("types_publication") or [])
        score, raisons = 1, ["article de la semaine"]
        etudies = [p["produit"] for p in et.get("produits_suivis") or [] if p.get("role") == "étudié"]
        cites = [p["produit"] for p in et.get("produits_suivis") or [] if p.get("role") != "étudié"]
        if etudies:
            score, raisons = score + 3, raisons + ["produit suivi étudié : " + ", ".join(etudies[:3])]
        elif cites:
            score, raisons = score + 1, raisons + ["produit suivi cité : " + ", ".join(cites[:3])]
        if "Randomized Controlled Trial" in types:
            score, raisons = score + 3, raisons + ["essai randomisé"]
        elif "Clinical Trial" in types:
            score, raisons = score + 2, raisons + ["essai clinique"]
        if "Meta-Analysis" in types or "Systematic Review" in types:
            score, raisons = score + 2, raisons + ["méta-analyse ou revue systématique"]
        if not d.get("resume_present"):
            score -= 1
        if "Case Reports" in types:
            score, raisons = score - 1, raisons + ["cas clinique isolé"]
        resume = ia.get(pmid) or ia.get(str(pmid))
        elements.append({"id": f"PMID:{pmid}", "type": "article", "score": score, "raisons": raisons, "titre": titre,
                         "resume_fr": resume,
                         "lien": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "fiche": f"fiches/{pmid}.html",
                         "texte": f"Article ({revue or 'revue non précisée'}). "
                                  + (" ".join(resume) if resume else (d.get("resume") or "")[:600])})
    elements.sort(key=lambda e: (-e["score"], e["id"]))
    return elements


def compter(conn, debut, fin):
    def n(sql):
        return conn.execute(sql, (debut, fin)).fetchone()[0]
    return {
        "articles": n("SELECT COUNT(*) FROM articles WHERE json_extract(donnees, '$.date_entree_pubmed') BETWEEN ? AND ?"),
        "nouveaux_essais": n("SELECT COUNT(*) FROM essais WHERE json_extract(donnees, '$.date_premiere_publication') BETWEEN ? AND ?"),
        "changements_essais": n("SELECT COUNT(DISTINCT objet_id) FROM evenements WHERE objet_type = 'essai' AND type != 'nouvel_essai' "
                                "AND substr(date_detection, 1, 10) BETWEEN ? AND ?"),
    }


def texte_elements(elements):
    return "\n\n".join(f"[{e['id']}] {e['titre']}\n{e['texte'][:900]}" for e in elements)


def valider(sortie, elements):
    """Garde les points bien formés dont TOUTES les sources sont dans la liste. Renvoie la liste ou None."""
    ids = {e["id"] for e in elements}
    points = (sortie or {}).get("points") if isinstance(sortie, dict) else None
    if not isinstance(points, list):
        return None
    bons = []
    for p in points:
        if not isinstance(p, dict) or not p.get("titre") or not p.get("texte"):
            continue
        sources = [s.strip() for s in p.get("sources") or [] if isinstance(s, str)]
        sources += [s for s in MOTIF_ID.findall(p["texte"]) if s not in sources]
        if not sources or any(s not in ids for s in sources):
            continue
        texte = re.sub(r"\s*\[?\(?(NCT\d{8}|PMID:\d+|W\d{6,})\)?\]?", "", p["texte"]).strip()
        bons.append({"titre": str(p["titre"]).strip(), "texte": texte, "sources": sources})
    return bons[:NB_POINTS] if len(bons) >= NB_POINTS else None


def points_regles(elements):
    """Secours sans IA : un point par élément, avec la raison de sa sélection."""
    points = []
    for e in elements[:NB_POINTS]:
        debut = " ".join(e.get("resume_fr") or []) or e["texte"]
        points.append({"titre": e["titre"] or "Sans titre", "sources": [e["id"]],
                       "texte": (couper(debut) + " " if debut else "") + "(Sélectionné pour : " + ", ".join(e["raisons"]) + ".)"})
    return points


def rediger(elements, cle, session=None):
    f = fournisseur_ia.actif()
    erreur = None
    for modele in (f.modele, *f.secours):
        corps = {**f.options(), "model": modele, "temperature": 0, "max_tokens": 2500,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": PROMPT},
                              {"role": "user", "content": "ÉLÉMENTS DE LA SEMAINE :\n\n" + texte_elements(elements)}]}
        try:
            brut = reseau.appeler_chat(f.url, corps, cle, f"IA ({f.nom}, synthèse)", session=session, timeout=120)
            texte = brut["choices"][0]["message"]["content"].strip()
            texte = re.sub(r"^```(?:json)?|```$", "", texte).strip()
            return _j(texte), modele
        except reseau.ErreurSource as e:
            erreur = e
    raise erreur


def construire(conn, jour=None, cle=None, session=None):
    debut, fin = fenetre(jour)
    elements = candidats(conn, debut, fin)[:NB_CANDIDATS]
    resultat = {"debut": debut, "fin": fin, "genere_le": date.today().isoformat(), "chiffres": compter(conn, debut, fin),
                "mode": "regles", "modele": None, "version_prompt": None, "points": [], "erreur": None,
                "selection": [{k: e[k] for k in ("id", "type", "titre", "lien", "fiche", "score", "raisons")} for e in elements]}
    if not elements:
        return resultat
    cle = cle if cle is not None else fournisseur_ia.actif().cle
    points = None
    if cle and len(elements) >= NB_POINTS:
        try:
            sortie, modele = rediger(elements, cle, session)
            points = valider(sortie, elements)
            if points:
                resultat.update(mode="ia", modele=modele, version_prompt=VERSION_PROMPT)
            else:
                resultat["erreur"] = "réponse de l'IA rejetée (format ou citations invalides) : points écrits par les règles"
        except Exception as e:  # l'IA est un plus : sans elle, la synthèse est quand même publiée
            resultat["erreur"] = f"IA indisponible ({str(e)[:120]}) : points écrits par les règles"
    resultat["points"] = points or points_regles(elements)
    par_id = {e["id"]: e for e in elements}
    for p in resultat["points"]:
        p["liens"] = [{"id": s, "lien": par_id[s]["lien"], "fiche": par_id[s]["fiche"]} for s in p["sources"] if s in par_id]
    return resultat


def texte_mail(s, url_site):
    """Version texte de la synthèse pour l'e-mail hebdomadaire."""
    def d(iso):
        return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
    c = s["chiffres"]
    lignes = [f"Veille glaucome : ce qu'il faut retenir du {d(s['debut'])} au {d(s['fin'])}", "",
              f"{c['articles']} article(s) entré(s) dans PubMed, {c['nouveaux_essais']} nouvel(s) essai(s), "
              f"{c['changements_essais']} essai(s) modifié(s).", ""]
    for i, p in enumerate(s["points"], 1):
        lignes += [f"{i}. {p['titre']}", f"   {p['texte']}"]
        lignes += [f"   → {l['id']} : {l['lien']}" for l in p.get("liens", [])]
        lignes.append("")
    lignes.append("Rédigé par l'IA à partir des seules sources citées (à vérifier)." if s["mode"] == "ia"
                  else "Points sélectionnés par des règles fixes (sans IA).")
    lignes += [f"Tout le détail : {url_site}semaine.html", "",
               "Glaucoma Intelligence — projet étudiant, données publiques uniquement."]
    return "\n".join(lignes)


def texte_issue(s, url_site, alertes_md="", personne=""):
    """Version Markdown pour l'issue GitHub hebdomadaire (GitHub envoie lui-même l'e-mail : aucun secret)."""
    def d(iso):
        return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
    c = s["chiffres"]
    lignes = [f"{personne + ' : ' if personne else ''}voici ce qu'il faut retenir du {d(s['debut'])} au {d(s['fin'])}.", "",
              f"**{c['articles']}** article(s) entré(s) dans PubMed · **{c['nouveaux_essais']}** nouvel(s) essai(s) · "
              f"**{c['changements_essais']}** essai(s) modifié(s)", ""]
    for i, p in enumerate(s["points"], 1):
        sources = " · ".join(f"[{l['id']}]({l['lien']})" for l in p.get("liens", []))
        lignes += [f"### {i}. {p['titre']}", p["texte"], f"Source : {sources}", ""]
    lignes.append("_Rédigé par l'IA à partir des seules sources citées (citations vérifiées, à relire avant de citer)._"
                  if s["mode"] == "ia" else "_Points sélectionnés par des règles fixes (sans IA)._")
    if alertes_md:
        lignes += ["", "---", "", alertes_md.replace("# Alertes de la semaine", "## Alertes de la semaine")]
    lignes += ["", f"➡️ Tout le détail : {url_site}semaine.html", "",
               "---", "_Message automatique de Glaucoma Intelligence (une fois par semaine). Fermez l'issue une fois lue._"]
    return "\n".join(lignes)
