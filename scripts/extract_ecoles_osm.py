"""Ecoles geolocalisees d'OpenStreetMap (HOT/OSM via HDX) comptees par ancienne province, et comparees aux ecoles primaires de la DGESS.

Le fichier du Data Pack donne, pour chaque etablissement, le P-code de sa province (ancien decoupage) : aucun calcul geographique.
OSM recense TOUS les niveaux (primaire, secondaire, prescolaire) et est incomplet : ce fichier sert a verifier la couverture d'OSM,
pas a remplacer les annuaires. La distance d'acces theorique du panel s'appuie sur les ecoles de la DGESS.

Usage :
    python extract_ecoles_osm.py <ecoles_osm_burkina.csv> <panel_province_annee.csv> <ref_provinces.csv> <sortie.csv>
"""
import sys

import pandas as pd


def main():
    osm_csv, panel_csv, ref_csv, sortie = sys.argv[1:5]
    o = pd.read_csv(osm_csv, sep=";", dtype=str, encoding="utf-8")
    ref = pd.read_csv(ref_csv, sep=";", dtype=str)
    pan = pd.read_csv(panel_csv, sep=";", dtype={"pcode_province_old": str})
    codes = set(ref.pcode_province_old)
    o["ok"] = o["adm2_pcode"].isin(codes)
    print(f"{len(o)} etablissements OSM ; types : {o.amenity.value_counts().to_dict()}")
    print(f"rattaches a une ancienne province par leur P-code : {o.ok.mean():.1%} ({int((~o.ok).sum())} non rattaches)")
    o = o[o.ok]
    ecole = o[o.amenity == "school"].groupby("adm2_pcode").size()
    mater = o[o.amenity == "kindergarten"].groupby("adm2_pcode").size()
    p24 = pan[pan.annee_debut == 2024].set_index("pcode_province_old")
    d = pd.DataFrame({"province": p24["province"], "ecoles_osm": ecole, "maternelles_osm": mater}).fillna({"ecoles_osm": 0, "maternelles_osm": 0})
    d["ecoles_primaires_dgess_2024"] = p24["nb_ecoles"]
    d["rapport_osm_sur_dgess"] = (d["ecoles_osm"] / d["ecoles_primaires_dgess_2024"]).round(2)
    d["superficie_km2"] = p24["superficie_km2"]
    d.index.name = "pcode_province_old"
    d.reset_index().to_csv(sortie, sep=";", index=False, encoding="utf-8")
    tot_osm, tot_dg = d.ecoles_osm.sum(), d.ecoles_primaires_dgess_2024.sum()
    print(f"ecoles OSM (school) : {int(tot_osm)} ; ecoles primaires DGESS 2024-2025 : {int(tot_dg)} ; rapport national {tot_osm / tot_dg:.2f}")
    print("rapport OSM / DGESS par province : min %.2f, mediane %.2f, max %.2f" % (d.rapport_osm_sur_dgess.min(), d.rapport_osm_sur_dgess.median(), d.rapport_osm_sur_dgess.max()))
    print("provinces ou OSM recense moins de la moitie des ecoles de la DGESS :", int((d.rapport_osm_sur_dgess < 0.5).sum()))


if __name__ == "__main__":
    main()
