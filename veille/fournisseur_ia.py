"""Choix du service d'IA (gratuit) pour les résumés et l'assistant.

GitHub Models a fermé le 30/07/2026 : depuis, models.github.ai répond « OK » en texte au lieu
d'une réponse (constaté dans Actions les 13 et 14/11/2026). On utilise donc un service qui
parle le même « langage » (chat/completions, format OpenAI) avec une clé GRATUITE :

- MISTRAL_API_KEY : Mistral AI (entreprise française), modèle mistral-small-latest ;
- GEMINI_API_KEY  : Google Gemini, modèle gemini-2.5-flash (porte compatible OpenAI).

La clé se met dans .env (en local) ou dans les Secrets du dépôt (en ligne), jamais dans le code.
Sans clé, les étapes IA sont sautées proprement.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Fournisseur:
    nom: str
    variable: str
    url: str
    modele: str
    cle: str | None = None


CATALOGUE = (
    Fournisseur("Mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
    Fournisseur("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                "gemini-2.5-flash"),
)


def actif(variable_modele="MODELE_IA"):
    """Le premier service dont la clé est présente (sinon Mistral, sans clé : l'étape sera sautée)."""
    for f in CATALOGUE:
        cle = os.getenv(f.variable)
        if cle:
            return Fournisseur(f.nom, f.variable, f.url, os.getenv(variable_modele, f.modele), cle)
    f = CATALOGUE[0]
    return Fournisseur(f.nom, f.variable, f.url, os.getenv(variable_modele, f.modele), None)
