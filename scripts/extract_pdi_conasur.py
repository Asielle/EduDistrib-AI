"""Personnes deplacees internes (PDI) hebergees par ancienne province, serie mensuelle CONASUR (janv. 2019 - mars 2023).

Source : fichier "idps4" du Data Pack (SP/CONASUR via HDX), une ligne par commune ou site d'ACCUEIL (destination)
et par date. Les P-codes "Admin 2" sont ceux de l'ANCIEN decoupage : meme cle que le panel (pcode_province_old).

Sortie : pdi_province_date.csv (province x date), avec totaux hommes / femmes / enfants quand ils existent
(ils ne sont renseignes qu'a partir de fevrier 2022 ; avant, seul le total existe).

Controle : la somme nationale au 31/12/2022 doit etre egale au total publie par le CONASUR (1 882 391).

Usage :
    python extract_pdi_conasur.py <idps4__Tableau.csv> <ref_provinces.csv> <sortie.csv>
"""
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
TOTAL_CONASUR_31_12_2022 = 1_882_391  # "BURKINA FASO" dans le fichier STATISTIQUES du 31/12/2022

COLS = ["source", "pays", "region", "province", "commune", "village", "site", "hommes", "femmes",
        "enfants_moins_5", "enfants_plus_5", "enfants", "total", "pcode_region", "pcode_province_old",
        "pcode_commune", "date"]


def main():
    src, ref_csv, sortie = sys.argv[1:4]
    d = pd.read_csv(src, sep=";", skiprows=[1], dtype=str, encoding="utf-8").iloc[:, :17]  # ligne 2 = codes HXL
    d.columns = COLS
    for c in ["hommes", "femmes", "enfants_moins_5", "enfants_plus_5", "enfants", "total"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    n0 = len(d)
    d = d.dropna(subset=["date", "total"])
    ref = pd.read_csv(ref_csv, sep=";", dtype=str)
    inconnus = sorted(set(d["pcode_province_old"]) - set(ref["pcode_province_old"]))
    d = d[d["pcode_province_old"].isin(ref["pcode_province_old"])]

    g = d.groupby(["pcode_province_old", "date"], as_index=False).agg(
        pdi_total=("total", "sum"), pdi_hommes=("hommes", "sum"), pdi_femmes=("femmes", "sum"),
        pdi_enfants=("enfants", "sum"), nb_lignes=("total", "size"))
    # avant fev. 2022 les details n'existent pas : on remet des vides au lieu de zeros trompeurs
    sans_detail = g["date"] < "2022-02-01"
    g.loc[sans_detail, ["pdi_hommes", "pdi_femmes", "pdi_enfants"]] = pd.NA
    g = g.merge(ref[["pcode_province_old", "province"]], on="pcode_province_old", how="left")
    g = g.sort_values(["date", "pcode_province_old"])
    g["date"] = g["date"].dt.strftime("%Y-%m-%d")
    g.to_csv(sortie, sep=";", index=False, encoding="utf-8")

    nat = g.groupby("date")["pdi_total"].sum()
    print(f"{n0} lignes lues, {len(d)} retenues ; P-codes hors reference : {inconnus}")
    print(f"{g['date'].nunique()} dates ({g['date'].min()} -> {g['date'].max()}), {g['pcode_province_old'].nunique()} provinces ; {len(g)} lignes")
    ecart = int(nat.get("2022-12-31", 0)) - TOTAL_CONASUR_31_12_2022
    print(f"total national au 2022-12-31 : {int(nat.get('2022-12-31', 0)):,} (CONASUR : {TOTAL_CONASUR_31_12_2022:,}) -> ecart {ecart}".replace(",", " "))
    print(f"dernier total national ({nat.index[-1]}) : {int(nat.iloc[-1]):,}".replace(",", " "))


if __name__ == "__main__":
    main()
