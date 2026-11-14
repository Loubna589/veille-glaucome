"""Appels HTTP robustes, communs à toutes les sources.

Une seule fonction, `requete()`, utilisée par tous les connecteurs (ClinicalTrials.gov,
PubMed, OpenAlex, Crossref, BDPM, EMA, openFDA, GitHub Models) :
- délai maximal (timeout) sur chaque appel ;
- nouvelles tentatives LIMITÉES, avec attente exponentielle (backoff) : 2 s, 4 s, 8 s… ;
- HTTP 429 (trop de requêtes) : on respecte l'en-tête Retry-After s'il est raisonnable,
  sinon on abandonne proprement au lieu de bloquer l'exécution ;
- erreurs passagères (500, 502, 503, 504, coupure réseau, délai dépassé) : nouvelle tentative ;
- erreurs définitives (400, 401, 403, 404…) : pas de nouvelle tentative ;
- chaque appel est journalisé dans data/logs/veille-AAAA-MM-JJ.log (sans clé ni jeton).

En cas d'échec, `ErreurSource` est levée avec une explication en français : l'appelant
la rattrape pour que la panne d'une source n'empêche pas les autres de tourner.
"""
import email.utils
import json
import logging
import time
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_LOGS = RACINE / "data" / "logs"
AGENT = "veille-glaucome/0.3 (outil de veille, usage personnel ; requests)"
REESSAYABLES = {429, 500, 502, 503, 504}
PARAMS_SECRETS = {"api_key", "apikey", "key", "token", "email", "mailto"}

_dormir = time.sleep  # remplacé dans les tests pour ne pas attendre réellement


class ErreurSource(requests.exceptions.RequestException):
    """Échec d'appel à une source, expliqué en français. `statut` = code HTTP (ou None).

    Hérite de RequestException : le code existant qui rattrape les erreurs réseau la rattrape aussi."""

    def __init__(self, message, statut=None, reponse=None):
        super().__init__(message)
        self.statut = statut
        self.reponse = reponse


def journal():
    """Logger commun : fichier quotidien dans data/logs/ + console pour les avertissements."""
    log = logging.getLogger("veille")
    if not log.handlers:
        log.setLevel(logging.INFO)
        try:
            DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
            fichier = logging.FileHandler(DOSSIER_LOGS / f"veille-{time.strftime('%Y-%m-%d')}.log", encoding="utf-8")
            fichier.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(fichier)
        except OSError:
            pass  # pas de journal sur disque (ex. dossier en lecture seule) : on continue
    return log


def _masquer(params):
    """Paramètres affichables dans les logs : clés, jetons et adresses masqués."""
    return {k: ("***" if k.lower() in PARAMS_SECRETS else v) for k, v in (params or {}).items()}


def attente_retry_after(valeur, maintenant=None):
    """Lit l'en-tête Retry-After : un nombre de secondes ou une date HTTP. None si illisible."""
    if not valeur:
        return None
    valeur = str(valeur).strip()
    if valeur.isdigit():
        return int(valeur)
    try:
        date = email.utils.parsedate_to_datetime(valeur)
    except (TypeError, ValueError):
        return None
    if date is None:
        return None
    return max(0, int(date.timestamp() - (maintenant or time.time())))


def requete(methode, url, source, *, params=None, data=None, json_corps=None, headers=None,
            timeout=30, tentatives=4, backoff=2.0, attente_max=60, session=None):
    """Appel HTTP robuste. Renvoie la réponse (statut 2xx) ou lève ErreurSource."""
    log = journal()
    entetes = {"User-Agent": AGENT, **(headers or {})}
    appelant = session or requests
    derniere_erreur = None
    for essai in range(1, tentatives + 1):
        debut = time.monotonic()
        try:
            reponse = appelant.request(methode, url, params=params, data=data, json=json_corps,
                                       headers=entetes, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as erreur:
            derniere_erreur = ErreurSource(f"{source} : réseau indisponible ou délai dépassé ({type(erreur).__name__})")
            log.warning("%s %s %s → %s (tentative %d/%d)", source, methode, url, type(erreur).__name__, essai, tentatives)
            if essai < tentatives:
                _dormir(backoff ** essai)
                continue
            raise derniere_erreur from erreur
        duree = time.monotonic() - debut
        log.info("%s %s %s %s → HTTP %s en %.1f s", source, methode, url, _masquer(params), reponse.status_code, duree)
        if 200 <= reponse.status_code < 300:
            return reponse

        message = f"{source} : HTTP {reponse.status_code}"
        corps = (reponse.text or "")[:200].replace("\n", " ")
        if reponse.status_code == 429:
            pause = attente_retry_after(reponse.headers.get("Retry-After"))
            message += f" — trop de requêtes (Retry-After : {reponse.headers.get('Retry-After') or 'non précisé'})"
            if essai < tentatives and pause is not None and pause <= attente_max:
                log.warning("%s → attente de %s s demandée par la source (tentative %d/%d)", message, pause, essai, tentatives)
                _dormir(pause + 1)
                continue
            if essai < tentatives and pause is None:
                _dormir(backoff ** essai)
                continue
            log.error("%s — abandon (attente trop longue ou tentatives épuisées)", message)
            raise ErreurSource(message, 429, reponse)
        if reponse.status_code in REESSAYABLES and essai < tentatives:
            log.warning("%s — erreur passagère, nouvelle tentative dans %s s", message, backoff ** essai)
            _dormir(backoff ** essai)
            continue
        log.error("%s — %s", message, corps)
        raise ErreurSource(f"{message} — {corps}", reponse.status_code, reponse)
    raise derniere_erreur or ErreurSource(f"{source} : échec après {tentatives} tentatives")


def lire_json(reponse, source):
    """Corps JSON d'une réponse, ou ErreurSource si la source a renvoyé autre chose (page d'erreur HTML…)."""
    try:
        return reponse.json()
    except (ValueError, json.JSONDecodeError) as erreur:
        journal().error("%s : réponse qui n'est pas du JSON valide : %r", source, (reponse.text or "")[:200])
        apercu = (reponse.text or "")[:150].replace("\n", " ") or "corps vide"
        type_contenu = reponse.headers.get("Content-Type", "?")
        raise ErreurSource(f"{source} : réponse invalide (JSON attendu) — HTTP {reponse.status_code}, "
                           f"{type_contenu}, début : {apercu!r}", reponse.status_code, reponse) from erreur


# --- GitHub Models -------------------------------------------------------------------------------
# Deux portes d'entrée officielles. Le 13 et le 14/11/2026, la première a renvoyé « OK » en texte
# au lieu d'une réponse JSON : on essaie alors la seconde (même jeton GITHUB_TOKEN, même modèle).
MODELS_PORTES = (
    ("https://models.github.ai/inference/chat/completions", lambda m: m),
    ("https://models.inference.ai.azure.com/chat/completions", lambda m: m.split("/", 1)[-1]),
)


def appeler_github_models(corps, jeton, source, *, session=None, timeout=60, tentatives=3):
    """Envoie une requête chat/completions à GitHub Models et renvoie le JSON. Essaie la porte de secours si besoin."""
    derniere = None
    for url, nom_modele in MODELS_PORTES:
        reponse = requete("POST", url, source, json_corps={**corps, "model": nom_modele(corps["model"])},
                          timeout=timeout, tentatives=tentatives, session=session,
                          headers={"Authorization": f"Bearer {jeton}", "Accept": "application/json",
                                   "Content-Type": "application/json"})
        try:
            donnees = lire_json(reponse, source)
            if isinstance(donnees, dict) and donnees.get("choices"):
                return donnees
            derniere = ErreurSource(f"{source} : réponse sans « choices » ({url})", reponse.status_code, reponse)
        except ErreurSource as erreur:
            derniere = erreur
        redirections = " → ".join(str(r.status_code) for r in getattr(reponse, "history", []) or [])
        journal().warning("%s : %s (url finale %s%s) — essai de la porte suivante", source, derniere,
                          getattr(reponse, "url", url), f", redirections {redirections}" if redirections else "")
    raise derniere
