"""IA traçable : résumé en français + classification dans des catégories fermées (GitHub Models, gratuit).

Pour chaque étude de la base (essai, article PubMed, publication OpenAlex) qui a un résumé
dans sa source, on demande à un modèle léger une sortie JSON :
    {"resume": [3 lignes], "categorie": <catégorie fermée>, "justification": "..."}

Traçabilité (table `traitements_ia` de la base SQLite) :
- le MODÈLE utilisé, la VERSION DU PROMPT (fichier versionné config/prompts/<version>.md), la DATE ;
- l'EMPREINTE du texte source : si la source change, le traitement est refait ; sinon jamais ;
- un STATUT DE VALIDATION humain : « non_verifie » par défaut (puis valide / corrige / rejete) ;
- la sortie brute du modèle, conservée telle quelle.

La sortie est VALIDÉE (JSON, clés attendues, 3 lignes, catégorie dans la liste fermée) ;
une sortie invalide n'est jamais enregistrée.

Accès : https://models.github.ai/inference/chat/completions avec le jeton GITHUB_TOKEN
(automatique sur GitHub Actions avec `permissions: models: read`). Sans jeton, l'étape est sautée.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from veille import base, reseau

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_PROMPTS = RACINE / "config" / "prompts"
VERSION_PROMPT = os.getenv("VERSION_PROMPT", "resume_classification_v1")
API = "https://models.github.ai/inference/chat/completions"
MODELE = os.getenv("MODELE_IA", "openai/gpt-4o-mini")
MAX_PAR_EXECUTION = 40   # reste sous les limites gratuites de GitHub Models
MAX_ECHECS = 3           # au-delà, on s'arrête (problème d'accès probable)
PAUSE = 5                # secondes entre deux appels
MENTION = "Généré par IA, non vérifié"

CATEGORIES = {
    "traitement_medicamenteux": "Traitement médicamenteux",
    "chirurgie_laser": "Chirurgie / laser",
    "dispositif": "Dispositif",
    "diagnostic_imagerie": "Diagnostic / imagerie",
    "epidemiologie": "Épidémiologie",
    "autre": "Autre",
}


class SortieInvalide(ValueError):
    """La réponse du modèle ne respecte pas le format attendu."""


def prompt(version=VERSION_PROMPT):
    return (DOSSIER_PROMPTS / f"{version}.md").read_text(encoding="utf-8")


def empreinte(texte):
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def valider_sortie(texte):
    """Analyse et valide la réponse du modèle. Renvoie un dict propre ou lève SortieInvalide."""
    texte = (texte or "").strip()
    if texte.startswith("```"):  # certains modèles entourent le JSON de ```json … ```
        texte = texte.strip("`").removeprefix("json").strip()
    try:
        sortie = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise SortieInvalide(f"pas du JSON : {erreur}") from erreur
    if not isinstance(sortie, dict):
        raise SortieInvalide("objet JSON attendu")
    manquantes = {"resume", "categorie", "justification"} - set(sortie)
    if manquantes:
        raise SortieInvalide(f"clés manquantes : {sorted(manquantes)}")
    resume = sortie["resume"]
    if not (isinstance(resume, list) and len(resume) == 3 and all(isinstance(l, str) and l.strip() for l in resume)):
        raise SortieInvalide("« resume » doit contenir exactement 3 lignes non vides")
    if sortie["categorie"] not in CATEGORIES:
        raise SortieInvalide(f"catégorie hors liste : {sortie['categorie']!r}")
    if not isinstance(sortie["justification"], str) or not sortie["justification"].strip():
        raise SortieInvalide("« justification » vide")
    return {"resume": [l.strip() for l in resume], "categorie": sortie["categorie"],
            "justification": sortie["justification"].strip()}


def etudes_a_traiter(conn):
    """(type, identifiant, date de détection, texte source) des études ayant un résumé dans leur source."""
    sortie = []
    for e in conn.execute("SELECT nct, donnees, premiere_detection FROM essais"):
        d = json.loads(e["donnees"])
        if d.get("resume_source"):
            sortie.append(("essai", e["nct"], e["premiere_detection"], f"Titre : {d.get('titre')}\n\nRésumé :\n{d['resume_source']}"))
    for a in conn.execute("SELECT pmid, openalex_id, origine, donnees, premiere_detection FROM articles"):
        d = json.loads(a["donnees"])
        if d.get("resume"):
            ident = a["pmid"] if a["origine"] == "pubmed" else a["openalex_id"]
            sortie.append(("article", ident, a["premiere_detection"], f"Titre : {d.get('titre')}\n\nRésumé :\n{d['resume']}"))
    return sorted(sortie, key=lambda x: (x[2] or "", x[1]), reverse=True)  # les plus récentes d'abord


def deja_traite(conn, objet_id, emp, version=VERSION_PROMPT):
    return conn.execute("SELECT 1 FROM traitements_ia WHERE objet_id = ? AND empreinte_source = ? AND version_prompt = ?",
                        (objet_id, emp, version)).fetchone() is not None


def demander(texte, jeton, session=None):
    reponse = reseau.requete("POST", API, "GitHub Models", timeout=60, tentatives=3, session=session, headers={
        "Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
    }, json_corps={"model": MODELE, "temperature": 0, "max_tokens": 400, "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": prompt()}, {"role": "user", "content": texte[:6000]}]})
    return reseau.lire_json(reponse, "GitHub Models")["choices"][0]["message"]["content"]


def enregistrer(conn, objet_type, objet_id, emp, brut, sortie, modele=MODELE, version=VERSION_PROMPT):
    conn.execute("INSERT OR IGNORE INTO traitements_ia (objet_type, objet_id, empreinte_source, modele, version_prompt, date, "
                 "sortie, categorie, resume, pourquoi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (objet_type, objet_id, emp, modele, version, time.strftime("%Y-%m-%d"), brut, sortie["categorie"],
                  base.jdump(sortie["resume"]), sortie["justification"]))


def traiter(conn, jeton=None, session=None, maximum=MAX_PAR_EXECUTION, pause=PAUSE):
    """Traite les études pas encore traitées par CETTE version du prompt. Renvoie un bilan."""
    jeton = jeton or os.getenv("GITHUB_TOKEN")
    bilan = {"traites": 0, "invalides": 0, "restants": 0, "saute": False, "erreur": None}
    if not jeton:
        bilan["saute"] = True
        return bilan
    a_faire = [(t, i, txt) for t, i, _, txt in etudes_a_traiter(conn) if not deja_traite(conn, i, empreinte(txt))]
    echecs = 0
    for objet_type, objet_id, texte in a_faire[:maximum]:
        try:
            brut = demander(texte, jeton, session)
            sortie = valider_sortie(brut)
        except SortieInvalide as erreur:
            bilan["invalides"] += 1
            reseau.journal().warning("IA : sortie invalide pour %s : %s", objet_id, erreur)
            echecs += 1
        except reseau.ErreurSource as erreur:
            bilan["erreur"] = str(erreur)
            reseau.journal().error("IA : %s", erreur)
            break  # 429 ou accès refusé : on reprendra à la prochaine exécution
        else:
            enregistrer(conn, objet_type, objet_id, empreinte(texte), brut, sortie)
            conn.commit()
            bilan["traites"] += 1
        if echecs >= MAX_ECHECS:
            bilan["erreur"] = f"{echecs} sorties invalides : arrêt par prudence"
            break
        time.sleep(pause)
    bilan["restants"] = len(a_faire) - bilan["traites"]
    return bilan


def charger(conn):
    """Dernier traitement IA de chaque étude, pour le site (avec toute sa traçabilité)."""
    sortie = {}
    for t in conn.execute("SELECT * FROM traitements_ia ORDER BY date, id"):
        sortie[t["objet_id"]] = {
            "resume": json.loads(t["resume"] or "[]"), "categorie": t["categorie"],
            "categorie_libelle": CATEGORIES.get(t["categorie"], t["categorie"]), "justification": t["pourquoi"],
            "modele": t["modele"], "version_prompt": t["version_prompt"], "genere_le": t["date"],
            "statut_validation": t["statut_validation"],
            "mention": MENTION if t["statut_validation"] == "non_verifie" else f"Généré par IA, {t['statut_validation']}",
        }
    return sortie
