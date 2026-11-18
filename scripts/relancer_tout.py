"""Relance toute la chaine, de 01_collecte a 05_interpretation, dans l'ordre.

Usage :
    python relancer_tout.py <racine_du_projet>

Entrees : 01_collecte/ (donnees brutes du Data Pack) et 04_analyse/parametres_cout_salle.csv (fichier saisi a la main, avec ses sources).
Sorties : 02_nettoyage/, 03_transformation/ (panel), 04_analyse/ (projection, indice, optimisation, modele) et 05_interpretation/ (tableau de bord).
Chaque etape est un script de ce dossier ; le script s'arrete a la premiere erreur.
"""
import os
import subprocess
import sys
import time

racine = os.path.abspath(sys.argv[1])
ici = os.path.dirname(os.path.abspath(__file__))
P = lambda *x: os.path.join(racine, *x)
col = P("01_collecte")
annuaires = os.path.join(col, "data", "01_Education_MENAPLN_DGESS", "CNS_DGESS", "Annuaires")
admin2 = os.path.join(col, "data", "04_Cartographie_SIG", "COD-AB_limites_administratives", "bfa_admin_boundaries__bfa_admin2.csv")
insd = os.path.join(col, "data", "02_Demographie_INSD", "INSD_RGPH2019_Vol4_Projections_demographiques_2020-2035.csv")
conasur = os.path.join(col, "data", "03_Conditions_de_Vie_et_Emploi", "PDI_CONASUR", "idps4__Tableau.csv")
osm = os.path.join(col, "data", "04_Cartographie_SIG", "Ecoles_OSM_HOTOSM", "ecoles_osm_burkina.csv")
n2, n3, n4, n5 = P("02_nettoyage"), P("03_transformation"), P("04_analyse"), P("05_interpretation")
for d in (n2, n3, n4, n5):
    os.makedirs(d, exist_ok=True)

ETAPES = [
    ("02", "extract_tableau_I1.py", [annuaires, os.path.join(n2, "tableau_I1_brut.csv")]),
    ("02", "harmoniser_provinces.py", [admin2, os.path.join(n2, "tableau_I1_brut.csv"), n2]),
    ("02", "extract_enseignants_IV1.py", [annuaires, admin2, os.path.join(n2, "enseignants_IV1_propre.csv")]),
    ("02", "extract_salles_VI.py", [annuaires, admin2, os.path.join(n2, "tableau_I1_propre.csv"), os.path.join(n2, "salles_etat_propre.csv")]),
    ("02", "extract_equipement_V4.py", [annuaires, admin2, os.path.join(n2, "tableau_I1_propre.csv"), os.path.join(n2, "equipement_ecoles_propre.csv")]),
    ("02", "extract_eleves_milieu.py", [annuaires, admin2, os.path.join(n2, "tableau_I1_propre.csv"), os.path.join(n2, "enseignants_IV1_propre.csv"), os.path.join(n2, "eleves_milieu_propre.csv")]),
    ("02", "extract_population_provinces.py", [insd, admin2, os.path.join(n2, "population_province_age.csv")]),
    ("02", "extract_pdi_conasur.py", [conasur, os.path.join(n2, "ref_provinces.csv"), os.path.join(n2, "pdi_province_date.csv")]),
    ("03", "build_panel.py", [n2, n3, "50", "40"]),
    ("03", "controle_regions.py", [racine]),
    ("03", "contexte_regional.py", [racine]),
    ("02", "esu_province.py", [racine]),
    ("03", "extract_ecoles_osm.py", [osm, os.path.join(n3, "panel_province_annee.csv"), os.path.join(n2, "ref_provinces.csv"), os.path.join(n2, "ecoles_osm_province.csv")]),
    ("04", "projection_2030.py", [os.path.join(n3, "panel_province_annee.csv"), os.path.join(n2, "population_province_age.csv"), n4]),
    ("04", "indice_tension.py", [os.path.join(n3, "panel_province_annee.csv"), os.path.join(n4, "projection_2030_resume.csv"), n4]),
    ("04", "optimisation_2030.py", [racine]),
    ("04", "modele_predictif.py", [racine]),
    ("04", "modele_cp1.py", [racine]),
    ("04", "fourchette_projection.py", [racine]),
    ("05", "build_dashboard.py", [racine]),
    ("05", "build_fiche_decideur.py", [racine]),
]

debut = time.time()
for etape, script, args in ETAPES:
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ici, script)] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = r.returncode == 0
    print(f"[{etape}] {script:36s} {'OK' if ok else 'ECHEC'}  ({time.time() - t0:.0f} s)")
    if not ok:
        print(r.stdout[-1500:])
        print(r.stderr[-2500:])
        sys.exit(1)
print(f"Chaine complete relancee en {time.time() - debut:.0f} s.")

