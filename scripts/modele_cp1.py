"""Test : les nouveaux inscrits au CP1 (serie regionale DGESS) ameliorent-ils la prevision a 1 an ?

Meme protocole que modele_predictif.py (origine glissante 2021, 2022, 2023 ; cible = ecart a la croissance demographique ; WAPE ; Huber).
Variables ajoutees, connues a la fin de l'annee t et propres a la REGION de la province (13 regions) :
  cp1_part : nouveaux inscrits CP1 / effectifs de la region          (poids des entrants dans le primaire)
  dcp1     : log(CP1[t] / CP1[t-1]) de la region                    (dynamique des entrants)
Seul l'horizon 1 an est teste (les deux variables ne se projettent pas sans hypothese supplementaire).
Usage : python modele_cp1.py <racine_du_projet>
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modele_predictif as M  # noqa: E402

warnings.filterwarnings("ignore")
racine = sys.argv[1]
ids, annees, E, EC, PDI, P611, nom = M.charger(racine)
D = M.variables(E, EC, PDI, ids, annees, P611)
S = pd.read_csv(os.path.join(racine, "03_transformation", "series_regionales_dgess.csv"), sep=";")
pan = pd.read_csv(os.path.join(racine, "03_transformation", "panel_province_annee.csv"), sep=";", dtype={"pcode_province_old": str})
reg = pan.drop_duplicates("pcode_province_old").set_index("pcode_province_old")["region_ancienne"]

S = S.sort_values(["region", "annee_debut"])
S["cp1_part"] = S.nouveaux_cp1 / S.eleves
S["dcp1"] = np.log(S.nouveaux_cp1 / S.groupby("region").nouveaux_cp1.shift(1))
S = S.set_index(["region", "annee_debut"])
D["region"] = D.pcode.map(reg)
t = D.Y - 1
D["cp1_part"] = [S.cp1_part.get((r, a), np.nan) for r, a in zip(D.region, t)]
D["dcp1"] = [S.dcp1.get((r, a), np.nan) for r, a in zip(D.region, t)]

JEUX = {"REC (reference Huber)": M.REC, "REC + CP1": M.REC + ["cp1_part", "dcp1"], "CP1 seul": ["cp1_part", "dcp1"]}
fab = M.fabriquer_modeles()["huber"][0]
rows = []
for O in M.ORIGINES:
    obs = np.array([E.loc[p, O + 1] for p in ids], float)
    e0 = np.array([E.loc[p, O] for p in ids], float)
    tr = D[D.Y <= O].dropna(subset=["g", "cp1_part", "dcp1"] + M.REC)
    te = D[D.Y == O + 1].set_index("pcode").reindex(ids)
    ok = (obs > 0) & (e0 > 0) & te[M.REC + ["cp1_part", "dcp1"]].notna().all(axis=1).values
    demo = (e0 / P611[O].values) * P611[O + 1].values
    rows.append({"jeu": "Demographique (reference)", "origine": O, "wape": M.wape(demo[ok], obs[ok]), "n": int(ok.sum()), "n_train": len(tr)})
    for nom_j, cols in JEUX.items():
        m = fab()
        m.fit(tr[cols].values, tr["g"].values)
        g = m.predict(te[cols].fillna(0).values) + te["gpop"].values
        prev = np.minimum(te["E_prev"].values * np.exp(g), M.TBS_PLAFOND * P611[O + 1].values)
        rows.append({"jeu": nom_j, "origine": O, "wape": M.wape(np.nan_to_num(prev)[ok], obs[ok]), "n": int(ok.sum()), "n_train": len(tr)})
R = pd.DataFrame(rows)
T = R.pivot_table(index="jeu", columns="origine", values="wape")
T["moyenne"] = T.mean(axis=1)
print("ERREUR A 1 AN (WAPE) PAR ORIGINE - plus petit = mieux")
print((T * 100).round(1).to_string())
print("\nlignes d'entrainement par origine :", R[R.jeu == "REC + CP1"].set_index("origine").n_train.to_dict())
R.to_csv(os.path.join(racine, "04_analyse", "modele_cp1_test.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")
