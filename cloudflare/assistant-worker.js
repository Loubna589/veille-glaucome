/* Glaucoma Intelligence — petit service « assistant » (Cloudflare Worker, offre gratuite).

   Pourquoi : le site est statique (GitHub Pages). Une clé d'IA ne doit JAMAIS être dans le site, sinon n'importe qui la lit.
   Ce Worker garde la clé Gemini côté serveur (secret GEMINI_API_KEY du Worker) et ne fait qu'une chose :
   recevoir une question + les documents de la veille trouvés par le navigateur, et renvoyer une réponse simple qui les cite.

   Garde-fous : seules les pages du site (Origin) sont servies ; question ≤ 500 caractères ; 6 documents au plus ;
   pas de stockage ; utiliser une clé Gemini d'un projet SANS facturation (offre gratuite : aucun coût possible).

   Installation (une fois, ~10 min) : voir cloudflare/LISEZ-MOI.md */

const ORIGINES = ["https://loubna589.github.io"];
const MODELES = ["gemini-flash-lite-latest", "gemini-2.5-flash-lite"];

const CONSIGNE = `Tu es l'assistant d'un site de veille sur le glaucome, utilisé par une étudiante en management (pas une professionnelle de santé).
Règles :
- Réponds en français très simple : 4 à 10 phrases courtes, ou une courte liste à puces (lignes commençant par « - »).
- Tout mot médical est expliqué entre parenthèses la première fois.
- Pour les notions générales (maladie, traitements, étapes de prise en charge, réglementation), utilise les connaissances médicales
  établies, par exemple les recommandations de la Société européenne du glaucome (EGS), sans inventer de chiffres précis.
- On te donne aussi des DOCUMENTS de la veille, numérotés. Quand une phrase s'appuie sur un document, ajoute son numéro entre crochets, ex. [2].
  Ne cite jamais un numéro qui n'existe pas. N'attribue à un document que ce qu'il dit.
- N'invente aucun résultat d'essai, aucun chiffre d'étude, aucun nom d'étude.
- Pas de conseil médical personnel : pour un cas personnel, renvoie vers un ophtalmologiste.
- Si la question n'a rien à voir avec le glaucome, l'œil, les médicaments ou leur marché, dis-le poliment en une phrase.`;

function json(corps, statut, entetes) {
  return new Response(JSON.stringify(corps), { status: statut || 200, headers: { "Content-Type": "application/json; charset=utf-8", ...entetes } });
}

export default {
  async fetch(requete, env) {
    const origine = requete.headers.get("Origin") || "";
    const autorisee = ORIGINES.includes(origine);
    const cors = { "Access-Control-Allow-Origin": autorisee ? origine : ORIGINES[0], "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "600", "Vary": "Origin" };
    if (requete.method === "OPTIONS") return new Response(null, { headers: cors });
    if (requete.method !== "POST" || !autorisee) return json({ erreur: "accès réservé au site Glaucoma Intelligence" }, 403, cors);
    if (!env.GEMINI_API_KEY) return json({ erreur: "clé GEMINI_API_KEY absente du Worker" }, 500, cors);

    let entree;
    try { entree = await requete.json(); } catch (e) { return json({ erreur: "requête invalide" }, 400, cors); }
    const question = String(entree.question || "").trim().slice(0, 500);
    if (!question) return json({ erreur: "question vide" }, 400, cors);
    const documents = (Array.isArray(entree.documents) ? entree.documents : []).slice(0, 6)
      .map((d, i) => `[${i + 1}] ${String(d.titre || "").slice(0, 300)}\n${String(d.texte || "").slice(0, 1200)}`);

    const corps = {
      systemInstruction: { parts: [{ text: CONSIGNE }] },
      contents: [{ role: "user", parts: [{ text: `QUESTION : ${question}\n\nDOCUMENTS DE LA VEILLE :\n\n${documents.join("\n\n") || "(aucun)"}` }] }],
      generationConfig: { temperature: 0.2, maxOutputTokens: 900 },
    };
    let derniere = "";
    for (const modele of MODELES) {
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${modele}:generateContent`, {
        method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY }, body: JSON.stringify(corps) });
      if (!r.ok) { derniere = `${modele} : HTTP ${r.status}`; continue; }
      const d = await r.json();
      const texte = (d.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
      if (texte) return json({ reponse: texte, modele }, 200, cors);
      derniere = `${modele} : réponse vide`;
    }
    return json({ erreur: `IA indisponible (${derniere})` }, 502, cors);
  },
};
