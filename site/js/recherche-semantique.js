/* Glaucoma Intelligence — recherche sémantique dans le navigateur (module réutilisable).
   Même logique que veille/semantique.py : glossaire FR→EN, cosinus sur vecteurs int8 + bonus lexical pondéré (IDF).
   Le modèle (≈ 118 Mo, Xenova/multilingual-e5-small) est téléchargé une fois puis gardé en cache par le navigateur. */
const CDN = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";
let etat = null; // { S, vecteurs, extracteur }

function decoder(S) {
  const brut = Uint8Array.from(atob(S.vecteurs_int8_base64), c => c.charCodeAt(0));
  const octets = new Int8Array(brut.buffer), d = S.dimension, n = S.ids.length, v = new Float32Array(n * d);
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) v[i * d + j] = octets[i * d + j] * S.echelles[i];
  return v;
}

export function etendre(S, question) {
  let reste = question.toLowerCase(); const ajouts = [];
  Object.keys(S.glossaire || {}).sort((a, b) => b.length - a.length).forEach(t => {
    if (reste.includes(t)) { S.glossaire[t].forEach(x => { if (!ajouts.includes(x)) ajouts.push(x); }); reste = reste.split(t).join(" "); }
  });
  return [ajouts.length ? `${question} (${ajouts.join(", ")})` : question, ajouts];
}

/* Charge l'index et le modèle (une seule fois). `informer(texte)` reçoit les messages de progression. */
export async function preparer(racine = "", informer = () => {}) {
  if (etat) return etat;
  informer("Chargement de l'index…");
  const reponse = await fetch(racine + "data/semantique.json", { cache: "no-cache" });
  if (!reponse.ok) throw new Error("index de recherche indisponible");
  const S = await reponse.json();
  informer("Chargement du modèle de recherche (≈ 118 Mo la première fois)…");
  const { pipeline } = await import(CDN);
  const extracteur = await pipeline("feature-extraction", S.modele, { quantized: true });
  etat = { S, vecteurs: decoder(S), extracteur };
  return etat;
}

/* Les k documents les plus proches de la question. */
export async function chercher(question, k = 5, racine = "", informer = () => {}) {
  const { S, vecteurs, extracteur } = await preparer(racine, informer);
  const [etendue, termes] = etendre(S, question);
  const n = S.metas.length, poids = {};
  termes.forEach(t => { const df = S.metas.filter(m => (m.texte || "").toLowerCase().includes(t.toLowerCase())).length; poids[t] = Math.log((n + 1) / (df + 1)) + 1e-6; });
  const total = termes.reduce((a, t) => a + poids[t], 0);
  const q = (await extracteur(S.prefixe_question + etendue, { pooling: "mean", normalize: true })).data, d = S.dimension;
  return S.ids.map((id, i) => {
    let c = 0; for (let j = 0; j < d; j++) c += vecteurs[i * d + j] * q[j];
    const txt = (S.metas[i].texte || "").toLowerCase();
    const lex = total ? termes.reduce((a, t) => a + (txt.includes(t.toLowerCase()) ? poids[t] : 0), 0) / total : 0;
    return { id, ...S.metas[i], score: c + S.poids_lexical * lex };
  }).sort((a, b) => b.score - a.score).slice(0, k);
}
