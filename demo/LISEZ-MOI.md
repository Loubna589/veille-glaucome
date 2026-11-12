# Kit de démo de secours — Glaucoma Intelligence (fonctionne SANS réseau)

| Fichier | Contenu |
|---|---|
| `veille_demo.db` | copie de la base SQLite : 75 essais, 434 publications, 509 événements, 509 embeddings, journal complet |
| `index/` | index de recherche (509 vecteurs, modèle multilingual-e5-small) |
| `recherche_demo.txt` | résultat réel de la recherche sur la question de démo (exécuté hors ligne le 11/11/2026) |
| `logs/execution_reussie_20261111T205713.log` | journal réel d'une exécution réussie (7 sources « ok ») |
| `alerte_test.md` | alerte générée par la démo (statut, date de fin, résultats déposés) |
| `reponse_rag_demo.json` | **à créer** avec le jeton GitHub : `python assistant.py --sauver-demo` (réponse réelle, citations vérifiées) |

Le modèle d'embeddings (118 Mo) est déjà sur ce PC (`data/local/modeles/`) : la recherche en ligne de commande marche
hors ligne. La page « Recherche » du site, elle, télécharge le modèle dans le navigateur la première fois : l'ouvrir une
fois AVANT la présentation pour qu'il soit en cache.

## Scénario de démo en 5 étapes (≈ 6 min) — PowerShell, dans le dossier `Veille-glaucome`

1. **Le pipeline** (1 min) — double-clic sur `ouvrir_site.bat` → page **Pipeline** : schéma, tables SQLite, journal
   de l'exécution (7 sources « ok »). Phrase : « chaque source est isolée ; une panne rend l'exécution partielle ».
2. **La recherche sémantique** (1 min) — `python chercher.py "Quels traitements du glaucome sans conservateur font actuellement l'objet de recherches cliniques ?"`
   → 1er résultat NCT07845357 (ZOLYMBUS sans conservateur), score détaillé (cosinus + glossaire).
   Puis la même question sur la page **Recherche** du site (encodée dans le navigateur).
3. **L'assistant** (1,5 min) — `python assistant.py` puis http://127.0.0.1:8770 → réponse citée [NCT…][PMID:…],
   citations vérifiées ; hors ligne : bouton « Réponse de démo ». Sans jeton : sources seules (le dire, c'est voulu).
4. **La carte et les alertes** (1,5 min) — page **Carte** : cliquer sur un essai (promoteur, traitement, sources) ;
   puis `python demo_alerte.py` : un essai change → 3 alertes ; rejoué → 0 (déduplication).
5. **La qualité** (1 min) — `python -m pytest -q` (71 verts), puis `$env:CASSER_TEST_DEMO="1"; python -m pytest -q`
   (1 rouge = publication bloquée), `Remove-Item Env:CASSER_TEST_DEMO` ; page **Performances** (F1, P@5, MRR).

Si `data/veille.db` est absente, `demo_alerte.py` utilise automatiquement `demo/veille_demo.db`.
