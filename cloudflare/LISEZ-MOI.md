# Brancher une vraie IA sur l'assistant (Cloudflare Worker, gratuit)

Le site est statique : il ne peut pas cacher une clé d'IA. Ce petit service la garde côté serveur.
Coût : 0 € (offre gratuite Cloudflare : 100 000 requêtes par jour ; Gemini : offre gratuite, sans carte bancaire).

1. Créer un compte gratuit sur https://dash.cloudflare.com/sign-up (vous-même ; aucun moyen de paiement nécessaire).
2. Dans le tableau de bord : **Workers & Pages** → **Create** → **Create Worker** → nom : `glaucoma-assistant` → **Deploy**.
3. **Edit code** : effacer le code d'exemple, coller tout le contenu de `cloudflare/assistant-worker.js`, puis **Deploy**.
4. **Settings** → **Variables and Secrets** → **Add** → type **Secret**, nom `GEMINI_API_KEY`, valeur : une clé Gemini
   (https://aistudio.google.com/apikey, dans un projet **sans facturation**). Enregistrer.
5. Copier l'adresse du Worker (du type `https://glaucoma-assistant.<votre-nom>.workers.dev`) et la coller dans
   `site/data/assistant_en_ligne.json` (champ `"url"`), ou la donner à Claude. La clé, elle, ne se donne à personne.

Pour couper le service : supprimer le Worker, ou vider le champ `"url"`. L'assistant revient alors aux réponses préparées.
