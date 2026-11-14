"""Assistant RAG local : http://127.0.0.1:8770  (Flask, accessible uniquement depuis cet ordinateur).

    python assistant.py                         → lance l'application (page « Assistant »)
    python assistant.py --question "..."        → une question en ligne de commande
    python assistant.py --sauver-demo           → enregistre la réponse RÉELLE à la question de démo
                                                  dans demo/reponse_rag_demo.json (mode hors ligne)

Clé IA : MISTRAL_API_KEY (ou GEMINI_API_KEY) dans le fichier .env (jamais dans le code, jamais versionné).
Sans jeton : les sources retrouvées s'affichent, sans synthèse.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

QUESTION_DEMO = "Quels traitements du glaucome sans conservateur font actuellement l'objet de recherches cliniques ?"
FICHIER_DEMO = RACINE / "demo" / "reponse_rag_demo.json"
ORIGINES_AUTORISEES = {"http://127.0.0.1:8766", "http://localhost:8766"}  # le site local servi par ouvrir_site.bat


def charger_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(RACINE / ".env")
    except ImportError:
        pass


def application(assistant):
    from flask import Flask, jsonify, request, send_from_directory
    app = Flask(__name__, static_folder=str(RACINE / "site"), static_url_path="/site")

    @app.after_request
    def cors(reponse):
        # CORS limité au site local (ouvrir_site.bat) : la bulle d'assistant des pages peut interroger l'API,
        # aucun autre site web ne le peut. Flask répond seul aux requêtes OPTIONS (pré-vérification).
        origine = request.headers.get("Origin")
        if origine in ORIGINES_AUTORISEES and request.path.startswith("/api/"):
            reponse.headers["Access-Control-Allow-Origin"] = origine
            reponse.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            reponse.headers["Access-Control-Allow-Headers"] = "Content-Type"
            reponse.headers["Access-Control-Max-Age"] = "600"
            reponse.headers["Vary"] = "Origin"
        return reponse

    @app.get("/")
    def page():
        return send_from_directory(RACINE / "app", "assistant.html")

    @app.post("/api/question")
    def question():
        texte = ((request.get_json(silent=True) or {}).get("question") or "").strip()
        if not texte or len(texte) > 500:
            return jsonify({"erreur": "question vide ou trop longue (500 caractères au plus)"}), 400
        return jsonify(assistant.repondre(texte))

    @app.get("/api/demo")
    def demo():
        if not FICHIER_DEMO.exists():
            return jsonify({"erreur": "aucune réponse de démo enregistrée (python assistant.py --sauver-demo)"}), 404
        return jsonify(json.loads(FICHIER_DEMO.read_text(encoding="utf-8")))

    @app.get("/api/etat")
    def etat():
        return jsonify({"jeton": bool(assistant.jeton), "modele": __import__("veille.fournisseur_ia").fournisseur_ia.actif("MODELE_RAG").modele,
                        "version_prompt": __import__("veille.rag").rag.VERSION_PROMPT, "documents": len(assistant.index.ids),
                        "question_demo": QUESTION_DEMO, "demo_disponible": FICHIER_DEMO.exists()})

    return app


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--question")
    parser.add_argument("--sauver-demo", action="store_true")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    charger_env()
    from veille.rag import Assistant
    assistant = Assistant()

    if args.question or args.sauver_demo:
        sortie = assistant.repondre(args.question or QUESTION_DEMO)
        print(f"Statut : {sortie['statut']} · modèle : {sortie['modele'] or '—'} · prompt : {sortie['version_prompt']} "
              f"· {sortie['duree_ms']} ms")
        print(f"\nRéponse :\n{sortie['reponse'] or '(pas de synthèse : clé MISTRAL_API_KEY ou GEMINI_API_KEY absente de .env)'}\n")
        print("Sources retrouvées :")
        for s in sortie["sources"]:
            print(f"  [{s['citation']}] {s['score']:.3f} — {(s['titre'] or '')[:100]}")
        if args.sauver_demo:
            if sortie["statut"] != "ok":
                print(f"\nRéponse NON enregistrée pour la démo (statut « {sortie['statut']} ») : il faut une réponse réelle validée.")
                return 1
            FICHIER_DEMO.write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
            # Copie pour la page « Poser une question » du site (exemple de réponse réelle)
            (RACINE / "site" / "data" / "reponse_rag_demo.json").write_text(json.dumps(sortie, ensure_ascii=False), encoding="utf-8")
            print(f"\nRéponse de démo enregistrée : {FICHIER_DEMO}")
        return 0

    print(f"Assistant prêt sur http://127.0.0.1:{args.port} — jeton : {'oui' if assistant.jeton else 'NON (sources seules)'}")
    application(assistant).run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
