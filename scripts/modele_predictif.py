"""Modele predictif des effectifs du primaire par province, evalue contre des modeles de reference.

Question : un modele statistique prevoit-il mieux les effectifs que les hypotheses simples (effectifs constants, ou taux de
scolarisation constant) ? Reponse mesuree par une validation "a origine glissante" : on se place a la fin de l'annee O, on
entraine sur ce qui est connu jusque-la, on prevoit O+1, O+2, O+3, puis on compare a ce qui s'est reellement passe.

Cible    : croissance des effectifs d'une province, g = log(E[t+1] / E[t]).
Variables (connues a la fin de l'annee t) :
  g1   derniere croissance observee               lrp  log(E[t] / meilleur effectif passe de la province) : rebond possible
  pdi  deplaces heberges / population 2020        gec  croissance du nombre d'ecoles (fermetures)       dpdi  variation de pdi
Deux jeux de variables :
  REC   g1, lrp, pdi              : utilisable pour prevoir plusieurs annees d'affilee (chaque variable se met a jour)
  FULL  g1, lrp, pdi, gec, dpdi   : prevoit seulement l'annee suivante (on ne sait pas prevoir les ecoles ni les deplaces)
Modeles : regression de Huber (lineaire, robuste aux valeurs extremes), arbres de gradient (peu profonds), ridge.
References : CONSTANT (E[t+1] = E[t]) ; DEMOGRAPHIQUE (taux de scolarisation constant = scenario "statu quo") ; MOMENTUM
(meme croissance que l'annee derniere).
Erreur : WAPE = somme des |prevision - observe| / somme des observes, sur les 45 provinces (pese par les effectifs, ce qui
compte pour les besoins), et biais sur le total national.

Donnees : 45 provinces x 8 annees (2017-2018 a 2024-2025) => au plus 270 observations de croissance, dont une crise
(2021-2023). C'est peu : les resultats sont a lire avec cette prudence, et ils sont donnes par annee, pas seulement en moyenne.

Usage :
    python modele_predictif.py <racine_du_projet>
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
REC = ["g1", "lrp", "pdi"]
FULL = ["g1", "lrp", "pdi", "gec", "dpdi"]
ORIGINES = [2021, 2022, 2023]       # fin d'annee d'origine ; cibles O+1 .. min(O+3, 2024)
ANNEE_MAX = 2024
TBS_PLAFOND = 1.30                  # une province ne depasse pas 130 % de scolarisation des 6-11 ans


REB = ["lrp"]


def fabriquer_modeles():
    """nom -> (fabrique, jeux de variables). Les modeles prevoient l'ECART a la croissance demographique de la province
    (g - g_demographique) : ils ne doivent pas redecouvrir la demographie, seulement ce qu'elle n'explique pas."""
    return {
        "rebond": (lambda: make_pipeline(StandardScaler(), HuberRegressor(alpha=1.0, epsilon=1.35, max_iter=2000)),
                   {"REB": REB}),
        "huber": (lambda: make_pipeline(StandardScaler(), HuberRegressor(alpha=1.0, epsilon=1.35, max_iter=2000)),
                  {"REC": REC, "FULL": FULL}),
        "arbres": (lambda: GradientBoostingRegressor(loss="huber", n_estimators=120, max_depth=2, learning_rate=0.05,
                                                     subsample=0.8, min_samples_leaf=6, random_state=0),
                   {"REC": REC, "FULL": FULL}),
    }


def charger(racine):
    pan = pd.read_csv(os.path.join(racine, "03_transformation", "panel_province_annee.csv"), sep=";", dtype={"pcode_province_old": str})
    pop = pd.read_csv(os.path.join(racine, "02_nettoyage", "population_province_age.csv"), sep=";", dtype={"pcode_province_old": str})
    pop = pop[pop.sexe == "E"]
    p611 = pop[pop.groupe_age == "6-11"].pivot(index="pcode_province_old", columns="annee", values="population")
    ptot20 = pop[(pop.groupe_age == "total") & (pop.annee == 2020)].set_index("pcode_province_old")["population"]
    ids = sorted(pan["pcode_province_old"].unique())
    annees = list(range(2017, ANNEE_MAX + 1))
    E = pan.pivot(index="pcode_province_old", columns="annee_debut", values="nb_eleves").reindex(index=ids, columns=annees)
    EC = pan.pivot(index="pcode_province_old", columns="annee_debut", values="nb_ecoles").reindex(index=ids, columns=annees)
    pdi = pan.pivot(index="pcode_province_old", columns="annee_debut", values="pdi_hebergees").reindex(index=ids, columns=annees)
    dernier = pan.groupby("pcode_province_old")["pdi_dernier_stock_connu"].first().reindex(ids)
    pdi.loc[:, [2017, 2018]] = 0.0                          # avant le premier releve (janvier 2019) : pratiquement aucun
    for a in (2023, 2024):                                   # apres le dernier releve (mars 2023) : on garde le dernier stock
        pdi[a] = dernier
    pdi_ratio = pdi.div(ptot20.reindex(ids), axis=0)
    nom = pan.drop_duplicates("pcode_province_old").set_index("pcode_province_old")["province"].reindex(ids)
    return ids, annees, E, EC, pdi_ratio, p611.reindex(ids), nom


def gpop_annee(P611, pid, Y):
    """Croissance demographique des 6-11 ans de la province entre Y-1 et Y (projection INSD, connue d'avance).
    Avant 2021 la population n'est pas dans le pack : on prend la croissance moyenne annuelle 2020-2024."""
    if Y - 1 >= 2020:
        return float(np.log(P611.loc[pid, Y] / P611.loc[pid, Y - 1]))
    return float(np.log(P611.loc[pid, 2024] / P611.loc[pid, 2020]) / 4)


def variables(E, EC, PDI, ids, annees, P611):
    """Table (province, Y) : cible g = log(E[Y]/E[Y-1]) et variables connues a la fin de Y-1."""
    rows = []
    peak = E.cummax(axis=1)
    for pid in ids:
        for Y in range(2019, ANNEE_MAX + 1):
            t = Y - 1
            e_t, e_tm, e_y = E.loc[pid, t], E.loc[pid, t - 1], E.loc[pid, Y]
            c_t, c_tm = EC.loc[pid, t], EC.loc[pid, t - 1]
            gp = gpop_annee(P611, pid, Y)
            rows.append({
                "pcode": pid, "Y": Y, "E_prev": e_t, "E": e_y, "gpop": gp,
                "g": np.log(e_y / e_t) - gp if e_y > 0 and e_t > 0 else np.nan,   # ecart a la croissance demographique
                "g1": np.log(e_t / e_tm) if e_t > 0 and e_tm > 0 else np.nan,
                "lrp": np.log(e_t / peak.loc[pid, t]) if e_t > 0 else np.nan,
                "pdi": PDI.loc[pid, t], "dpdi": PDI.loc[pid, t] - PDI.loc[pid, t - 1],
                "gec": np.log(c_t / c_tm) if c_t > 0 and c_tm > 0 else np.nan,
            })
    return pd.DataFrame(rows)


def wape(prev, obs):
    return float(np.abs(prev - obs).sum() / obs.sum())


def prevoir_recursif(modele, cols, E, EC, PDI, P611, ids, origine, h_max, ref_pop):
    """Prevision recursive des effectifs de chaque province de origine+1 a origine+h_max.
    modele=None : reference. ref_pop : dict de references {nom: callable}."""
    hist = {pid: [E.loc[pid, a] for a in range(2017, origine + 1)] for pid in ids}
    out = {}
    cur = {pid: list(h) for pid, h in hist.items()}
    for s in range(1, h_max + 1):
        Y = origine + s
        X, ok = [], []
        for pid in ids:
            h = cur[pid]
            e_t, e_tm = h[-1], h[-2]
            pk = max(x for x in h if x == x)
            X.append([np.log(e_t / e_tm) if e_t > 0 and e_tm > 0 else 0.0, np.log(e_t / pk) if e_t > 0 else 0.0, PDI.loc[pid, min(Y - 1, ANNEE_MAX)]])
            ok.append(e_t > 0 and e_tm > 0)
        X = np.array(X)
        g = modele.predict(X[:, [REC.index(c) for c in cols]]) if modele is not None else None
        for k, pid in enumerate(ids):
            e_t = cur[pid][-1]
            if not (e_t > 0):
                cur[pid].append(np.nan)
                continue
            gg = gpop_annee(P611, pid, Y) + (g[k] if g is not None else 0.0)   # demographie + ecart prevu par le modele
            e_new = e_t * np.exp(gg)
            cap = TBS_PLAFOND * P611.loc[pid, Y]
            cur[pid].append(min(e_new, cap))
        out[Y] = np.array([cur[pid][-1] for pid in ids])
    return out


def main():
    racine = sys.argv[1]
    d_out = os.path.join(racine, "04_analyse")
    ids, annees, E, EC, PDI, P611, nom = charger(racine)
    D = variables(E, EC, PDI, ids, annees, P611)
    modeles = fabriquer_modeles()
    resultats = []        # une ligne par (methode, jeu, origine, horizon)

    def enregistrer(methode, jeu, O, h, prev, obs, ids_ok):
        resultats.append({"methode": methode, "variables": jeu, "origine": O, "horizon": h, "annee_cible": O + h,
                          "wape": wape(prev[ids_ok], obs[ids_ok]),
                          "biais_total": float(prev[ids_ok].sum() / obs[ids_ok].sum() - 1), "n_provinces": int(ids_ok.sum())})

    for O in ORIGINES:
        hmax = min(3, ANNEE_MAX - O)
        obs_all = {O + s: np.array([E.loc[pid, O + s] for pid in ids], float) for s in range(1, hmax + 1)}
        # ---- references ----
        for h in range(1, hmax + 1):
            obs = obs_all[O + h]
            e0 = np.array([E.loc[pid, O] for pid in ids], float)
            okm = (obs > 0) & (e0 > 0)
            enregistrer("constant", "-", O, h, e0, obs, okm)
            tbs0 = e0 / P611[O].values
            enregistrer("demographique", "-", O, h, tbs0 * P611[O + h].values, obs, okm)
        e1 = np.array([E.loc[pid, O] for pid in ids], float)
        e2 = np.array([E.loc[pid, O - 1] for pid in ids], float)
        for h in range(1, hmax + 1):
            obs = obs_all[O + h]
            okm = (obs > 0) & (e1 > 0) & (e2 > 0)
            mom = np.minimum(e1 * (e1 / e2) ** h, TBS_PLAFOND * P611[O + h].values)
            enregistrer("momentum", "-", O, h, mom, obs, okm)
        # ---- modeles ----
        train = D[(D.Y <= O)].dropna(subset=FULL + ["g"])
        for nm, (fab, jeux) in modeles.items():
            for jeu, cols in jeux.items():
                m = fab()
                m.fit(train[cols].values, train["g"].values)
                if jeu != "FULL":
                    pr = prevoir_recursif(m, cols, E, EC, PDI, P611, ids, O, hmax, None)
                    for h in range(1, hmax + 1):
                        obs = obs_all[O + h]
                        okm = (obs > 0) & np.isfinite(pr[O + h]) & (np.array([E.loc[pid, O] for pid in ids]) > 0)
                        enregistrer(nm, jeu, O, h, np.nan_to_num(pr[O + h]), obs, okm)
                else:   # FULL : un pas, les variables de l'annee O sont observees
                    test = D[D.Y == O + 1].set_index("pcode").reindex(ids)
                    okm = test[FULL + ["g"]].notna().all(axis=1).values & (obs_all[O + 1] > 0)
                    g = np.where(okm, m.predict(np.nan_to_num(test[FULL].values)), 0.0) + test["gpop"].values
                    prev = np.minimum(test["E_prev"].values * np.exp(g), TBS_PLAFOND * P611[O + 1].values)
                    enregistrer(nm, jeu, O, 1, np.nan_to_num(prev), obs_all[O + 1], okm)

    # ---- fiabilite selon la stabilite passee de la province (volatilite de l'ecart a la demographie) ----
    def volatilite(pid_series_rows):
        return float(np.sqrt(np.nanmean(np.square(pid_series_rows))))

    SEUILS = (0.10, 0.30)      # volatilite < 0,10 : stable ; >= 0,30 : tres volatile (log-croissance, hors demographie)
    def palier(v):
        return "stable" if v < SEUILS[0] else ("variable" if v < SEUILS[1] else "tres_volatile")

    seg_rows = []
    for O in ORIGINES:
        hmax = min(3, ANNEE_MAX - O)
        vol = {pid: volatilite(D[(D.pcode == pid) & (D.Y <= O)]["g"].values) for pid in ids}
        pal = np.array([palier(vol[pid]) for pid in ids])
        train = D[(D.Y <= O)].dropna(subset=FULL + ["g"])
        mh = fabriquer_modeles()["huber"][0]()
        mh.fit(train[REC].values, train["g"].values)
        pr_h = prevoir_recursif(mh, REC, E, EC, PDI, P611, ids, O, hmax, None)
        pr_0 = prevoir_recursif(None, REC, E, EC, PDI, P611, ids, O, hmax, None)
        e0 = np.array([E.loc[pid, O] for pid in ids], float)
        for h in range(1, hmax + 1):
            obs = np.array([E.loc[pid, O + h] for pid in ids], float)
            for nm, prev in (("demographique", pr_0[O + h]), ("huber_REC", pr_h[O + h]), ("constant", e0)):
                for niv in ("stable", "variable", "tres_volatile"):
                    mk = (pal == niv) & (obs > 0) & (e0 > 0) & np.isfinite(prev)
                    if mk.sum():
                        seg_rows.append({"methode": nm, "palier": niv, "origine": O, "horizon": h, "n_provinces": int(mk.sum()),
                                         "wape": wape(prev[mk], obs[mk]), "part_effectifs": float(obs[mk].sum() / obs[obs > 0].sum())})
    SEG = pd.DataFrame(seg_rows)
    SEG.to_csv(os.path.join(d_out, "modele_fiabilite_detail.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")
    segs = SEG.groupby(["palier", "methode", "horizon"]).agg(wape=("wape", "mean"), n_provinces=("n_provinces", "mean")).reset_index()
    segs.to_csv(os.path.join(d_out, "modele_fiabilite_par_palier.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")

    # paliers actuels des 45 provinces (donnees jusqu'a 2024-2025)
    prov_rows = []
    for pid in ids:
        v = volatilite(D[D.pcode == pid]["g"].values)
        prov_rows.append({"pcode_province_old": pid, "province": nom[pid], "volatilite": round(v, 3), "palier": palier(v)})
    pd.DataFrame(prov_rows).to_csv(os.path.join(d_out, "modele_fiabilite_provinces.csv"), sep=";", index=False, encoding="utf-8")

    R = pd.DataFrame(resultats)
    R.to_csv(os.path.join(d_out, "modele_evaluation_detail.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")
    # synthese : moyenne des WAPE sur les origines, par horizon
    S = (R.groupby(["methode", "variables", "horizon"]).agg(wape=("wape", "mean"), wape_pire=("wape", "max"),
                                                              biais_moyen=("biais_total", "mean"), n_origines=("origine", "nunique")).reset_index())
    S.to_csv(os.path.join(d_out, "modele_evaluation_synthese.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")
    pd.set_option("display.width", 200)
    print("ERREUR (WAPE, moyenne sur les origines) : plus c'est petit, mieux c'est")
    print(S.pivot_table(index=["methode", "variables"], columns="horizon", values="wape").round(3).to_string())
    print("\nERREUR PAR ANNEE CIBLE, horizon 1 (WAPE)")
    print(R[R.horizon == 1].pivot_table(index=["methode", "variables"], columns="annee_cible", values="wape").round(3).to_string())
    print("\nBIAIS sur le total national, horizon 1 (prevision / observe - 1)")
    print(R[R.horizon == 1].pivot_table(index=["methode", "variables"], columns="annee_cible", values="biais_total").round(3).to_string())
    pp = pd.DataFrame(prov_rows)
    print("\nPALIERS DE STABILITE des provinces (volatilite de l'ecart a la demographie ; seuils 0,10 et 0,30)")
    print(pp.groupby("palier").agg(provinces=("province", "count")).to_string())
    print("tres volatiles :", ", ".join(pp[pp.palier == "tres_volatile"].province))
    print("\nERREUR (WAPE) PAR PALIER, moyenne sur les origines")
    print(segs.pivot_table(index=["palier", "methode"], columns="horizon", values="wape").round(3).to_string())


if __name__ == "__main__":
    main()
