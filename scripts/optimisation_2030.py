"""Optimisation de la repartition des enseignants et des salles de classe, horizon 2030 (45 anciennes provinces).

Deux problemes, deux methodes :

1. REDEPLOIEMENT DES ENSEIGNANTS  (programmation lineaire, probleme de transport)
   Variables : x[i, j] = enseignants deplaces de la province i (excedent) vers la province j (deficit).
   Excedent de i  = max(0, enseignants en poste - enseignants necessaires en 2030, a la norme choisie)
   Deficit de j   = max(0, enseignants necessaires - enseignants en poste)
   On deplace un maximum d'enseignants, puis, parmi ces solutions, on minimise la distance totale parcourue :
       minimiser  sum (d[i, j] - M) * x[i, j]      sous  sum_j x[i, j] <= excedent[i],  sum_i x[i, j] <= deficit[j]
   (M = 10 000 km est plus grand que toute distance : le nombre d'enseignants deplaces passe avant la distance.)
   Un rayon maximal optionnel interdit les deplacements trop longs.  Solveur : HiGHS (scipy.optimize.linprog).
   Un probleme de transport a une solution entiere : aucun arrondi n'est necessaire (verifie).
   Un enseignant deplace n'est plus a recruter : le gain = recrutements evites.

2. PRIORISATION DES SALLES A CONSTRUIRE  (allocation d'un budget exprime en nombre de salles)
   Deficit de j = max(0, ceil(eleves 2030 / norme) - salles en 2024-2025).  Budget = B salles a repartir.
   Trois strategies comparees :
     equite        minimise le nombre maximal d'eleves par salle (nivellement : on ajoute la salle suivante a la
                   province la plus chargee ; optimal pour ce critere, verifie par une recherche dichotomique)
     tension       sert d'abord les provinces par indice de tension decroissant
     proportionnel repartit B au prorata des deficits (reference simple)
   Indicateurs : eleves par salle maximal, provinces au-dessus de 50 eleves par salle (le standard), eleves en surcharge (au-dela de 60 par salle)
   (au-dela de 50 par salle), part des salles allouees aux provinces a tension forte.
   Pas de cout par salle : le budget est un NOMBRE de salles. Pour passer en francs CFA il suffit de multiplier
   par un cout unitaire (hypothese a fournir) ; un cout different selon les provinces n'est pas modelise.

Limites : distances a vol d'oiseau entre centres de provinces ; securite et acceptabilite des affectations non
modelisees ; le stock de salles et d'enseignants est celui de 2024-2025, sans attrition ni remplacement.

Usage :
    python optimisation_2030.py <racine_du_projet>
"""
import heapq
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linprog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projection_2030 as pj  # noqa: E402
from harmoniser_provinces import lire_admin2  # noqa: E402

SCENARIOS = pj.SCENARIOS
NORMES_ENS = [40, 45, 50]
NORMES_SALLE = [40, 45, 50]
RAYONS = [None, 300]            # km ; None = pas de limite
SEUIL_NORME = 50                # standard du primaire : au-dessus, la province depasse la norme
SEUIL_SURCHARGE = 60            # eleves par salle au-dela duquel une classe est jugee tres chargee (20 % au-dessus du standard)
REF_NS = 50                     # norme de reference pour les salles (la configuration de reference des fichiers de sortie)
BUDGETS_PCT = [0.25, 0.5, 0.75, 1.0]   # parts du deficit national de salles


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def centres(geojson_path):
    """Centre (centroide pondere par la surface) de chaque ANCIENNE province, a partir des contours COD-AB.
    Les colonnes center_lat / center_lon du CSV sont vides ; une province scindee est regroupee."""
    import json
    with open(geojson_path, encoding="utf-8") as f:
        geo = json.load(f)
    acc = {}
    for ft in geo["features"]:
        g = ft["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = poly[0][:-1]
            a = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
                c = x0 * y1 - x1 * y0
                a += c
                cx += (x0 + x1) * c
                cy += (y0 + y1) * c
            if abs(a) < 1e-12:
                continue
            aire = abs(a) / 2
            e = acc.setdefault(ft["properties"]["adm2_pcode_old"], [0.0, 0.0, 0.0])
            e[0] += aire
            e[1] += cx / (3 * a) * aire
            e[2] += cy / (3 * a) * aire
    return pd.DataFrame({k: {"lon": v[1] / v[0], "lat": v[2] / v[0]} for k, v in acc.items()}).T


def transport(surplus, deficit, dist, rayon):
    """Flot de cout minimal apres maximisation du nombre d'enseignants deplaces. Retourne {(i, j): n}."""
    S = {i: v for i, v in surplus.items() if v > 0}
    D = {j: v for j, v in deficit.items() if v > 0}
    arcs = [(i, j) for i in S for j in D if rayon is None or dist[i][j] <= rayon]
    if not arcs:
        return {}
    M = 10_000.0
    c = np.array([dist[i][j] - M for i, j in arcs])
    ligne_i = {i: k for k, i in enumerate(S)}
    ligne_j = {j: k for k, j in enumerate(D)}
    A = np.zeros((len(S) + len(D), len(arcs)))
    for a, (i, j) in enumerate(arcs):
        A[ligne_i[i], a] = 1
        A[len(S) + ligne_j[j], a] = 1
    b = np.array(list(S.values()) + list(D.values()), dtype=float)
    res = linprog(c, A_ub=A, b_ub=b, bounds=(0, None), method="highs")
    assert res.status == 0, res.message
    x = res.x
    assert np.allclose(x, np.round(x), atol=1e-6), "solution non entiere"
    return {arcs[a]: int(round(x[a])) for a in range(len(arcs)) if round(x[a]) > 0}


def redeploiement(proj_t, ne, rayon, dist):
    stock = proj_t.set_index("pcode_province_old")["nb_enseignants"].astype(int)
    need = np.ceil(proj_t.set_index("pcode_province_old")["eleves_projetes"] / ne).astype(int)
    surplus = (stock - need).clip(lower=0).to_dict()
    deficit = (need - stock).clip(lower=0).to_dict()
    flux = transport(surplus, deficit, dist, rayon)
    # verifications
    sortants = {i: 0 for i in surplus}
    entrants = {j: 0 for j in deficit}
    for (i, j), n in flux.items():
        sortants[i] += n
        entrants[j] += n
    assert all(sortants[i] <= surplus[i] for i in surplus) and all(entrants[j] <= deficit[j] for j in deficit)
    if rayon is None:
        assert sum(flux.values()) == min(sum(surplus.values()), sum(deficit.values())), "flot non maximal"
    return stock, need, surplus, deficit, flux, sortants, entrants


# ---------------------------------------------------------------- salles ----
def alloc_equite(eleves, salles, deficit, B):
    y = {j: 0 for j in deficit}
    tas = [(-eleves[j] / salles[j], j) for j in deficit if deficit[j] > 0]
    heapq.heapify(tas)
    reste = B
    while reste > 0 and tas:
        _, j = heapq.heappop(tas)
        y[j] += 1
        reste -= 1
        if y[j] < deficit[j]:
            heapq.heappush(tas, (-eleves[j] / (salles[j] + y[j]), j))
    return y


def alloc_tension(deficit, ordre, B):
    y = {j: 0 for j in deficit}
    reste = B
    for j in ordre:
        k = min(deficit[j], reste)
        y[j], reste = k, reste - k
    return y


def alloc_proportionnel(deficit, B):
    tot = sum(deficit.values())
    brut = {j: B * d / tot for j, d in deficit.items()}
    y = {j: min(deficit[j], int(math.floor(v))) for j, v in brut.items()}
    reste = B - sum(y.values())
    for j in sorted(deficit, key=lambda k: brut[k] - math.floor(brut[k]), reverse=True):
        if reste <= 0:
            break
        if y[j] < deficit[j]:
            y[j] += 1
            reste -= 1
    return y


def minmax_dichotomie(eleves, salles, deficit, B, norme):
    """Plus petit ratio r tel que atteindre r partout coute <= B salles (verifie l'optimalite de alloc_equite).
    Le deficit plafonne le nombre de salles d'une province : on ne descend jamais sous la norme."""
    def cout(r):
        return sum(min(deficit[j], max(0, math.ceil(eleves[j] / r) - salles[j])) for j in deficit)
    lo, hi = float(norme), max(max(eleves[j] / salles[j] for j in deficit), float(norme))
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if cout(mid) <= B else (mid, hi)
    return hi


def metriques(eleves, salles, y, forte):
    ratio = {j: eleves[j] / (salles[j] + y.get(j, 0)) for j in eleves}
    return {
        "ratio_max": round(max(ratio.values()), 2),
        "provinces_au_dessus_50": sum(r > SEUIL_NORME for r in ratio.values()),
        "eleves_en_surcharge": int(sum(max(0, eleves[j] - SEUIL_SURCHARGE * (salles[j] + y.get(j, 0))) for j in eleves)),
        "part_salles_tension_forte": round(sum(v for j, v in y.items() if j in forte) / max(1, sum(y.values())), 3),
    }


def main():
    racine = sys.argv[1]
    d_out = os.path.join(racine, "04_analyse")
    pan, pop = pj.charger(os.path.join(racine, "03_transformation", "panel_province_annee.csv"),
                          os.path.join(racine, "02_nettoyage", "population_province_age.csv"))
    cibles = pj.tbs_cibles(pan, pop)
    ref = pd.read_csv(os.path.join(racine, "02_nettoyage", "ref_provinces.csv"), sep=";", dtype=str)
    nom = ref.set_index("pcode_province_old")["province"].to_dict()
    ctr = centres(os.path.join(racine, "01_collecte", "04_Cartographie_SIG", "geojson", "bfa_admin2.geojson"))
    assert len(ctr) == 45 and not ctr.isna().any().any()
    ids = list(ctr.index)
    dist = {i: {j: haversine(ctr.loc[i, "lat"], ctr.loc[i, "lon"], ctr.loc[j, "lat"], ctr.loc[j, "lon"]) for j in ids} for i in ids}
    idx = pd.read_csv(os.path.join(d_out, "indice_tension_provinces_2024_2025.csv"), sep=";", dtype={"pcode_province_old": str})
    forte = set(idx.loc[idx.niveau == "forte", "pcode_province_old"])
    ordre_tension = list(idx.sort_values("rang")["pcode_province_old"])

    resumes, flux_rows, prov_rows = [], [], []
    for ne in NORMES_ENS:
        proj_all = pj.projeter(pan, pop, cibles, 40.0, float(ne))
        for sc in SCENARIOS:
            p = proj_all[(proj_all.scenario == sc) & (proj_all.annee_debut == pj.HORIZON)]
            for rayon in RAYONS:
                stock, need, sur, dfc, flux, sort, entr = redeploiement(p, ne, rayon, dist)
                moved = sum(flux.values())
                D, S = sum(dfc.values()), sum(sur.values())
                km = sum(dist[i][j] * n for (i, j), n in flux.items())
                resumes.append({"scenario": sc, "norme_eleves_enseignant": ne, "rayon_max_km": rayon if rayon else "aucun",
                                "enseignants_en_poste_2024": int(stock.sum()), "necessaires_2030": int(need.sum()),
                                "excedent_total": S, "deficit_total": D, "deplaces": moved,
                                "a_recruter_sans_redeploiement": D, "a_recruter_avec_redeploiement": D - moved,
                                "part_du_deficit_couverte": round(moved / D, 3) if D else 1.0,
                                "distance_moyenne_km": round(km / moved, 1) if moved else 0,
                                "distance_max_km": round(max((dist[i][j] for (i, j) in flux), default=0), 1)})
                for (i, j), n in flux.items():
                    flux_rows.append({"scenario": sc, "norme_eleves_enseignant": ne, "rayon_max_km": rayon if rayon else "aucun",
                                      "pcode_origine": i, "province_origine": nom[i], "pcode_destination": j,
                                      "province_destination": nom[j], "enseignants": n, "distance_km": round(dist[i][j], 1)})
                if rayon is None:
                    for pid in stock.index:
                        prov_rows.append({"scenario": sc, "norme_eleves_enseignant": ne, "pcode_province_old": pid,
                                          "province": nom[pid], "en_poste_2024": int(stock[pid]), "necessaires_2030": int(need[pid]),
                                          "excedent": sur[pid], "deficit": dfc[pid], "sortants": sort.get(pid, 0),
                                          "entrants": entr.get(pid, 0), "reste_a_recruter": dfc[pid] - entr.get(pid, 0)})
    pd.DataFrame(resumes).to_csv(os.path.join(d_out, "optimisation_enseignants_resume.csv"), sep=";", index=False, encoding="utf-8")
    pd.DataFrame(flux_rows).to_csv(os.path.join(d_out, "optimisation_enseignants_flux.csv"), sep=";", index=False, encoding="utf-8")
    pd.DataFrame(prov_rows).to_csv(os.path.join(d_out, "optimisation_enseignants_provinces.csv"), sep=";", index=False, encoding="utf-8")

    # ---- salles ----
    strat_rows, alloc_rows = [], []
    for ns in NORMES_SALLE:
        proj_all = pj.projeter(pan, pop, cibles, float(ns), 40.0)
        for sc in SCENARIOS:
            p = proj_all[(proj_all.scenario == sc) & (proj_all.annee_debut == pj.HORIZON)].set_index("pcode_province_old")
            eleves = p["eleves_projetes"].astype(float).to_dict()
            salles = p["nb_salles"].astype(int).to_dict()
            deficit = {j: max(0, math.ceil(eleves[j] / ns) - salles[j]) for j in eleves}
            Dtot = sum(deficit.values())
            for pct in BUDGETS_PCT:
                B = int(round(Dtot * pct))
                strategies = {"equite": alloc_equite(eleves, salles, deficit, B),
                              "tension": alloc_tension(deficit, ordre_tension, B),
                              "proportionnel": alloc_proportionnel(deficit, B)}
                r_opt = minmax_dichotomie(eleves, salles, deficit, B, ns)
                m_eq = metriques(eleves, salles, strategies["equite"], forte)["ratio_max"]
                assert m_eq <= r_opt + 0.05, f"nivellement non optimal : {m_eq} > {r_opt}"
                for nm, y in strategies.items():
                    assert sum(y.values()) <= B and all(0 <= y[j] <= deficit[j] for j in deficit)
                    strat_rows.append({"scenario": sc, "norme_eleves_salle": ns, "budget_part_du_deficit": pct,
                                       "budget_salles": B, "deficit_national": Dtot, "strategie": nm,
                                       "salles_allouees": sum(y.values()), **metriques(eleves, salles, y, forte)})
                    if ns == REF_NS and sc == "retour_2020_2021" and pct == 0.5:
                        for j in deficit:
                            alloc_rows.append({"strategie": nm, "pcode_province_old": j, "province": nom[j],
                                               "eleves_2030": int(eleves[j]), "salles_2024": salles[j], "deficit_salles": deficit[j],
                                               "salles_allouees": y[j], "eleves_par_salle_apres": round(eleves[j] / (salles[j] + y[j]), 1),
                                               "tension_forte": j in forte})
    pd.DataFrame(strat_rows).to_csv(os.path.join(d_out, "optimisation_salles_strategies.csv"), sep=";", index=False, encoding="utf-8")
    pd.DataFrame(alloc_rows).to_csv(os.path.join(d_out, "optimisation_salles_allocation_reference.csv"), sep=";", index=False, encoding="utf-8")

    # ---- affichage ----
    r = pd.DataFrame(resumes)
    print("REDEPLOIEMENT DES ENSEIGNANTS (horizon 2030, norme 40 eleves par enseignant)")
    a = r[(r.norme_eleves_enseignant == 40)][["scenario", "rayon_max_km", "deficit_total", "excedent_total", "deplaces",
                                              "a_recruter_avec_redeploiement", "part_du_deficit_couverte", "distance_moyenne_km"]]
    print(a.to_string(index=False))
    s = pd.DataFrame(strat_rows)
    print(f"\nSALLES : scenario retour_2020_2021, norme {REF_NS}, budget = 50 % du deficit")
    print(s[(s.scenario == "retour_2020_2021") & (s.norme_eleves_salle == REF_NS) & (s.budget_part_du_deficit == 0.5)]
          .drop(columns=["scenario", "norme_eleves_salle", "budget_part_du_deficit"]).to_string(index=False))


if __name__ == "__main__":
    main()
