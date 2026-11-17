// Calcul de la projection 2030 (meme methode que scripts/projection_2030.py).
// Fonctions pures : testees avec Node contre les sorties Python, puis incluses telles quelles dans la page HTML.
const ANNEE_BASE = 2024, HORIZON = 2030;
const SCENARIOS = {
  statu_quo: { label: "Statu quo", court: "TBS 2024-2025 maintenu" },
  retour: { label: "Retour au niveau 2020-2021", court: "TBS revient à son niveau de 2020-2021" },
  universel: { label: "Accès universel", court: "TBS à 100 %" },
};

function cibleTbs(p, sc) {
  if (sc === "statu_quo") return p.tbs24;
  if (sc === "retour") return Math.max(p.tbs24, p.tbs20);
  return Math.max(p.tbs24, 1);
}
function tbsAt(p, sc, t) {
  return p.tbs24 + (cibleTbs(p, sc) - p.tbs24) * (t - ANNEE_BASE) / (HORIZON - ANNEE_BASE);
}
function elevesAt(p, sc, t) {
  return Math.round(tbsAt(p, sc, t) * p.pop[t - ANNEE_BASE]);
}
// Besoins d'une province a l'annee t pour un scenario et deux normes (eleves par salle, eleves par enseignant).
function besoins(p, sc, normeSalle, normeEns, t) {
  t = t || HORIZON;
  const eleves = elevesAt(p, sc, t);
  const sallesNec = Math.ceil(eleves / normeSalle);
  const ensNec = Math.ceil(eleves / normeEns);
  return {
    eleves, sallesNec, ensNec,
    salles: Math.max(0, sallesNec - p.salles),
    ens: Math.max(0, ensNec - p.ens),
    sallesRempl: Math.max(0, sallesNec - (p.salles - p.precaires)),
  };
}
function totalNational(provinces, sc, normeSalle, normeEns, t) {
  const r = { eleves: 0, salles: 0, ens: 0, sallesRempl: 0 };
  for (const p of provinces) {
    const b = besoins(p, sc, normeSalle, normeEns, t);
    r.eleves += b.eleves; r.salles += b.salles; r.ens += b.ens; r.sallesRempl += b.sallesRempl;
  }
  return r;
}
// ---- Allocation d'un budget de salles (memes regles que scripts/optimisation_2030.py) ----
const SEUIL_NORME = 50, SEUIL_SURCHARGE = 60;   // standard du primaire ; classes tres chargees (20 % au-dessus)
function deficitsSalles(provs, sc, ns) {
  const o = {};
  for (const p of provs) {
    const e = elevesAt(p, sc, HORIZON);
    o[p.id] = { e, s: p.salles, d: Math.max(0, Math.ceil(e / ns) - p.salles) };
  }
  return o;
}
function budgetTotal(provs, sc, ns) {
  const d = deficitsSalles(provs, sc, ns);
  return Object.values(d).reduce((a, x) => a + x.d, 0);
}
// strat : "equite" (minimise le maximum d'eleves par salle), "tension" (par indice decroissant), "proportionnel"
function allouer(provs, sc, ns, B, strat) {
  const info = deficitsSalles(provs, sc, ns);
  const ids = provs.map(p => p.id).sort();            // ordre des pcodes : meme departage des egalites que Python
  const y = {}; for (const id of ids) y[id] = 0;
  if (strat === "equite") {
    for (let k = 0; k < B; k++) {
      let best = null, br = -1;
      for (const id of ids) {
        if (y[id] >= info[id].d) continue;
        const r = info[id].e / (info[id].s + y[id]);
        if (r > br) { br = r; best = id; }
      }
      if (best === null) break;
      y[best]++;
    }
  } else if (strat === "tension") {
    let reste = B;
    for (const p of provs.slice().sort((a, b) => a.rang - b.rang)) {
      const k = Math.min(info[p.id].d, reste); y[p.id] = k; reste -= k;
    }
  } else {
    const tot = ids.reduce((a, id) => a + info[id].d, 0), brut = {};
    for (const id of ids) { brut[id] = B * info[id].d / tot; y[id] = Math.min(info[id].d, Math.floor(brut[id])); }
    let reste = B - ids.reduce((a, id) => a + y[id], 0);
    for (const id of ids.slice().sort((a, b) => (brut[b] - Math.floor(brut[b])) - (brut[a] - Math.floor(brut[a])))) {
      if (reste <= 0) break;
      if (y[id] < info[id].d) { y[id]++; reste--; }
    }
  }
  return y;
}
function metriquesAlloc(provs, sc, ns, y) {
  const info = deficitsSalles(provs, sc, ns), forte = new Set(provs.filter(p => p.niveau === "forte").map(p => p.id));
  let rmax = 0, sup = 0, surch = 0, tot = 0, totF = 0;
  for (const p of provs) {
    const s = info[p.id].s + y[p.id], e = info[p.id].e, r = e / s;
    rmax = Math.max(rmax, r); if (r > SEUIL_NORME) sup++;
    surch += Math.max(0, e - SEUIL_SURCHARGE * s);
    tot += y[p.id]; if (forte.has(p.id)) totF += y[p.id];
  }
  return { ratioMax: Math.round(rmax * 100) / 100, auDessus50: sup, surcharge: Math.round(surch), partForte: Math.round(1000 * totF / Math.max(1, tot)) / 1000, total: tot };
}
// Seuils de classes par quantiles (n classes) ; renvoie les bornes internes triees.
function bornesQuantiles(valeurs, n) {
  const v = valeurs.slice().sort((a, b) => a - b);
  const b = [];
  for (let k = 1; k < n; k++) b.push(v[Math.floor(v.length * k / n)]);
  return b;
}
function classeDe(valeur, bornes) {
  let c = 0;
  for (const b of bornes) if (valeur >= b) c++;
  return c;
}
if (typeof module !== "undefined") module.exports = { besoins, totalNational, elevesAt, tbsAt, bornesQuantiles, classeDe, SCENARIOS, allouer, metriquesAlloc, budgetTotal };
