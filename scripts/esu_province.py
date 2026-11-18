"""Met en forme la transcription ESU (reouvertures / delocalisations, primaire, mai 2023 et mai 2024) : 45 provinces, controles de totaux.

Entrees : 01_collecte/esu_transcription_manuelle/esu_primaire_mai_par_province.csv (saisi a la main depuis les PDF scannes),
          02_nettoyage/ref_provinces.csv
Sortie  : 02_nettoyage/esu_province_mai.csv
Usage   : python esu_province.py <racine_du_projet>
"""
import os
import re
import sys
import unicodedata

import pandas as pd

racine = sys.argv[1]
P = lambda *x: os.path.join(racine, *x)
norm = lambda s: re.sub(r"[^A-Z]", "", unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode())

# totaux PRIMAIRE imprimes dans les rapports : (structures, eleves). Source : dernier tableau de chaque section.
TOTAUX_IMPRIMES = {(2023, "rouvert"): (447, 95219), (2024, "rouvert"): (1135, 221706),
                   (2023, "delocalise"): (230, 37515), (2024, "delocalise"): (317, 46331)}

T = pd.read_csv(P("01_collecte", "esu_transcription_manuelle", "esu_primaire_mai_par_province.csv"), sep=";", encoding="utf-8")
ref = pd.read_csv(P("02_nettoyage", "ref_provinces.csv"), sep=";", encoding="utf-8-sig", dtype={"pcode_province_old": str})
cle = {norm(p): (c, p) for c, p in zip(ref.pcode_province_old, ref.province)}
cle["LESBALE"] = cle["BALE"]
T["k"] = T.province_source.map(norm)
inconnues = sorted(set(T.k) - set(cle))
assert not inconnues, f"provinces non reconnues : {inconnues}"
T["pcode_province_old"] = T.k.map(lambda k: cle[k][0])
assert not T.duplicated(["annee_mai", "type", "pcode_province_old"]).any(), "doublon"

print("CONTROLE DES TOTAUX (somme des provinces saisies vs total PRIMAIRE imprime)")
for (an, typ), (s_imp, e_imp) in TOTAUX_IMPRIMES.items():
    x = T[(T.annee_mai == an) & (T.type == typ)]
    s, e = int(x.structures.sum()), int(x.eleves.sum())
    flag = "OK" if (s, e) == (s_imp, e_imp) else f"ECART (structures {s - s_imp:+d}, eleves {e - e_imp:+d})"
    print(f"  {an} {typ:10s} saisi {s:5d} struct. / {e:7d} eleves ; imprime {s_imp:5d} / {e_imp:7d}  -> {flag}")

W = T.pivot_table(index="pcode_province_old", columns=["type", "annee_mai"], values=["structures", "eleves"], aggfunc="sum", fill_value=0)
W.columns = [f"esu_{typ}_{v}_{an}" for v, typ, an in W.columns]
W = ref[["pcode_province_old", "province"]].merge(W, left_on="pcode_province_old", right_index=True, how="left").fillna(0)
for c in W.columns[2:]:
    W[c] = W[c].astype(int)

W = W[["pcode_province_old", "province"] + sorted(c for c in W.columns if c.startswith("esu_"))]
W.to_csv(P("02_nettoyage", "esu_province_mai.csv"), sep=";", index=False, encoding="utf-8")
print("\n", len(W), "provinces ecrites ->", P("02_nettoyage", "esu_province_mai.csv"))
print("provinces sans aucune structure rouverte ni delocalisee (0 partout) :", ", ".join(W[(W.filter(like="structures").sum(axis=1)) == 0].province))
W["esu_struct_2024"] = W.esu_rouvert_structures_2024 + W.esu_delocalise_structures_2024
top = W.sort_values("esu_struct_2024", ascending=False).head(8)[["province", "esu_rouvert_structures_2024", "esu_delocalise_structures_2024", "esu_rouvert_eleves_2024"]]
print("\nProvinces avec le plus de structures rouvertes + delocalisees (primaire, mai 2024) :")
print(top.to_string(index=False))
