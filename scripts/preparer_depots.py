"""Prepare les depots pour l'espace challenge (equation.africadataentry.com) selon le modele du document du challenge :

    EQUIPE_ETAPE_DEFI_ROLE_description_vN.ext      ex. E07_02-nettoyage_D1_engineer_effectifs-primaire-propres_v2.csv

Un fichier = une etape ; pas d'espace ni d'accent ; versions numerotees ; un LISEZ-MOI par depot.
Les fichiers d'origine ne sont jamais modifies : les depots sont des COPIES dans 06_depots/ (dossier regenere a chaque lancement).
Le code source de chaque etape est depose en .zip (les scripts gardent leurs noms d'origine, car ils s'importent entre eux).

Usage :
    python preparer_depots.py <racine_du_projet> [code_equipe] [version]
    ex. python preparer_depots.py "C:\\EduDistrib AI" E07 1
"""
import csv
import os
import re
import shutil
import sys
import zipfile

DEFI = "D3"
ROLES = {"01-collecte": "engineer", "02-nettoyage": "engineer", "03-transformation": "architect",
         "04-analyse": "scientist", "05-interpretation": "analyst"}
DOSSIERS = {"01-collecte": "01_collecte", "02-nettoyage": "02_nettoyage", "03-transformation": "03_transformation",
            "04-analyse": "04_analyse", "05-interpretation": "05_interpretation"}
MARQUEUR = ".genere_par_preparer_depots"

ANN = "01_collecte/data/01_Education_MENAPLN_DGESS/CNS_DGESS/Annuaires/"
SCRIPTS = {
    "02-nettoyage": ["extract_tableau_I1.py", "extract_enseignants_IV1.py", "extract_salles_VI.py", "extract_equipement_V4.py",
                     "extract_population_provinces.py", "extract_pdi_conasur.py", "extract_eleves_milieu.py", "harmoniser_provinces.py"],
    "03-transformation": ["build_panel.py", "extract_ecoles_osm.py"],
    "04-analyse": ["projection_2030.py", "optimisation_2030.py", "modele_predictif.py", "harmoniser_provinces.py"],
    "05-interpretation": ["indice_tension.py", "build_dashboard.py", "build_fiche_decideur.py", "relancer_tout.py", "dashboard/calc.js", "dashboard/template.html"],
}

# (etape, chemin relatif, description, ext)  -- ext deduite du fichier
FICHIERS = [
    ("01-collecte", "DONNEES_STATISTQUES_ PRESCOLAIRE ET PRIMAIRE_2016_2025_DCB.xlsx", "statistiques-prescolaire-primaire-2016-2025-dgess", None),
    *[("01-collecte", ANN + f, "annuaire-primaire-" + d, None) for f, d in [
        ("CNS521_Annuaire_statistique_de_lenseignement_Primaire_2017_2018.csv", "2017-2018"),
        ("CNS522_Annuaire_statistique_de_lenseignement_Primaire_2018_2019.csv", "2018-2019"),
        ("CNS523_Annuaire_statistique_de_lenseignement_Primaire_2019_2020.csv", "2019-2020"),
        ("CNS524_Annuaire_statistique_de_lenseignement_Primaire_2020_2021.csv", "2020-2021"),
        ("CNS525_Annuaire_statistique_de_lenseignement_Primaire_2021_2022.csv", "2021-2022"),
        ("CNS526_Annuaire_statistique_de_lenseignement_Primaire_2022_2023.csv", "2022-2023"),
        ("CNS529_Annuaire_statistique_de_lenseignement_primaire_2023_2024.csv", "2023-2024"),
        ("CNS530_Annuaire_statistique_de_lenseignement_primaire_2024_2025.csv", "2024-2025")]],
    ("01-collecte", "01_collecte/data/02_Demographie_INSD/INSD_RGPH2019_Vol4_Projections_demographiques_2020-2035.csv", "projections-demographiques-2020-2035-insd", None),
    ("01-collecte", "01_collecte/data/03_Conditions_de_Vie_et_Emploi/PDI_CONASUR/idps4__Tableau.csv", "deplaces-internes-conasur-2019-2023", None),
    ("01-collecte", "01_collecte/data/04_Cartographie_SIG/COD-AB_limites_administratives/bfa_admin_boundaries__bfa_admin2.csv", "limites-provinces-cod-ab-attributs", None),
    ("01-collecte", "01_collecte/04_Cartographie_SIG/geojson/bfa_admin2.geojson", "limites-provinces-cod-ab-contours", None),
    ("01-collecte", "01_collecte/data/04_Cartographie_SIG/Ecoles_OSM_HOTOSM/ecoles_osm_burkina.csv", "ecoles-osm-burkina", None),
    ("02-nettoyage", "02_nettoyage/ref_provinces.csv", "table-reference-provinces-pcodes", None),
    ("02-nettoyage", "02_nettoyage/tableau_I1_propre.csv", "ecoles-salles-maitres-eleves-par-province-propres", None),
    ("02-nettoyage", "02_nettoyage/enseignants_IV1_propre.csv", "enseignants-par-province-et-milieu-propres", None),
    ("02-nettoyage", "02_nettoyage/eleves_milieu_propre.csv", "eleves-urbain-rural-par-province-propres", None),
    ("02-nettoyage", "02_nettoyage/salles_etat_propre.csv", "etat-des-salles-de-classe-propres", None),
    ("02-nettoyage", "02_nettoyage/equipement_ecoles_propre.csv", "equipement-des-ecoles-eau-latrines-propre", None),
    ("02-nettoyage", "02_nettoyage/population_province_age.csv", "population-par-province-age-propre", None),
    ("02-nettoyage", "02_nettoyage/pdi_province_date.csv", "deplaces-internes-par-province-propres", None),
    ("03-transformation", "03_transformation/panel_province_annee.csv", "panel-province-annee", None),
    ("03-transformation", "03_transformation/dictionnaire_variables.csv", "dictionnaire-des-variables", None),
    ("03-transformation", "02_nettoyage/ecoles_osm_province.csv", "ecoles-osm-par-province-controle-de-couverture", None),
    ("03-transformation", "03_transformation/schema_donnees.md", "schema-des-donnees", None),
    ("03-transformation", "03_transformation/plan_parcours_donnees.md", "plan-du-parcours-des-donnees", None),
    ("04-analyse", "04_analyse/projection_province_annee_scenario.csv", "projection-province-annee-scenarios", None),
    ("04-analyse", "04_analyse/projection_2030_resume.csv", "projection-2030-resume-par-province", None),
    ("04-analyse", "04_analyse/projection_sensibilite_normes.csv", "projection-sensibilite-aux-normes", None),
    ("04-analyse", "04_analyse/parametres_cout_salle.csv", "parametres-cout-salle-avec-sources", None),
    ("04-analyse", "04_analyse/optimisation_enseignants_resume.csv", "optimisation-enseignants-resume", None),
    ("04-analyse", "04_analyse/optimisation_enseignants_flux.csv", "optimisation-enseignants-flux", None),
    ("04-analyse", "04_analyse/optimisation_enseignants_provinces.csv", "optimisation-enseignants-par-province", None),
    ("04-analyse", "04_analyse/optimisation_salles_strategies.csv", "optimisation-salles-strategies", None),
    ("04-analyse", "04_analyse/optimisation_salles_allocation_reference.csv", "optimisation-salles-allocation-reference", None),
    ("04-analyse", "04_analyse/modele_evaluation_synthese.csv", "modele-evaluation-synthese", None),
    ("04-analyse", "04_analyse/modele_evaluation_detail.csv", "modele-evaluation-detail", None),
    ("04-analyse", "04_analyse/modele_fiabilite_par_palier.csv", "modele-fiabilite-par-palier", None),
    ("04-analyse", "04_analyse/modele_fiabilite_provinces.csv", "modele-fiabilite-par-province", None),
    ("05-interpretation", "04_analyse/indice_tension_provinces_2024_2025.csv", "indice-de-tension-par-province", None),
    ("05-interpretation", "04_analyse/indice_tension_robustesse.csv", "indice-de-tension-robustesse", None),
    ("05-interpretation", "05_interpretation/tableau_de_bord_implantation.html", "tableau-de-bord-carte-et-plan-d-action", None),
    ("05-interpretation", "05_interpretation/fiche_decideur_une_page.pdf", "fiche-decideur-une-page", None),
]
LISEZ_MOI = {   # etape -> [(fichier source, description)]
    "01-collecte": [("06_depots_modeles/lisez-moi_01_collecte.txt", "lisez-moi")],
    "02-nettoyage": [("02_nettoyage/LISEZ-MOI.txt", "lisez-moi-journal-de-nettoyage")],
    "03-transformation": [("03_transformation/LISEZ-MOI.txt", "lisez-moi")],
    "04-analyse": [("04_analyse/LISEZ-MOI.txt", "lisez-moi-projection"), ("04_analyse/LISEZ-MOI-optimisation.txt", "lisez-moi-optimisation"),
                   ("04_analyse/LISEZ-MOI-modele.txt", "lisez-moi-modele")],
    "05-interpretation": [("05_interpretation/LISEZ-MOI.txt", "lisez-moi")],
}

SOURCES = [  # (fichier de collecte, producteur, publication, annee, lien)
    ("statistiques-prescolaire-primaire-2016-2025-dgess", "DGESS, ministere de l'Education nationale (MENAPLN)", "Donnees statistiques prescolaire et primaire 2016-2025 (fournies dans l'espace challenge)", "2016-2025", "espace challenge equation.africadataentry.com"),
    ("annuaire-primaire-2017-2018 a 2024-2025", "DGESS / MENAPLN (via CNS)", "Annuaires statistiques de l'enseignement primaire (CNS521 a CNS526, CNS529, CNS530)", "2017-2018 a 2024-2025", "https://www.cns.bf/publications/mebapln/"),
    ("projections-demographiques-2020-2035-insd", "INSD", "RGPH 2019, volume 4 : Projection demographique 2020-2035 (chapitre 3, projections provinciales)", "2020-2035", "https://www.insd.bf"),
    ("deplaces-internes-conasur-2019-2023", "SP/CONASUR (via HDX)", "Situation des personnes deplacees internes par commune (fichier idps4)", "2019-2023", "https://data.humdata.org/dataset/situation-des-personnes-deplacees-internes"),
    ("limites-provinces-cod-ab-attributs et contours", "IGB / OCHA (via HDX)", "Limites administratives COD-AB du Burkina Faso (provinces, P-codes)", "2025-2026", "https://data.humdata.org/dataset/cod-ab-bfa"),
    ("ecoles-osm-burkina", "HOT / OpenStreetMap (via HDX)", "Etablissements scolaires geolocalises du Burkina Faso (utilise pour controler la couverture, pas comme source principale)", "2026", "https://data.humdata.org/dataset/hotosm_bfa_education_facilities"),
]


def kebab_ok(s):
    return re.fullmatch(r"[a-z0-9\-]+", s) is not None


def main():
    racine = sys.argv[1]
    equipe = sys.argv[2] if len(sys.argv) > 2 else "EQUIPE"
    ver = f"v{sys.argv[3] if len(sys.argv) > 3 else 1}"
    assert re.fullmatch(r"[A-Za-z0-9]+", equipe), "le code d'equipe ne doit contenir ni espace, ni accent, ni tiret bas"
    sortie = os.path.join(racine, "06_depots")
    if os.path.exists(sortie):
        assert os.path.exists(os.path.join(sortie, MARQUEUR)), f"{sortie} existe et n'a pas ete cree par ce script : je n'y touche pas"
        shutil.rmtree(sortie)
    os.makedirs(sortie)
    open(os.path.join(sortie, MARQUEUR), "w").close()
    modele_lisezmoi = os.path.join(racine, "scripts", "depots_modeles")

    inventaire, manques = [], []

    def nom(etape, desc, ext):
        assert kebab_ok(desc), f"description invalide : {desc}"
        return f"{equipe}_{etape}_{DEFI}_{ROLES[etape]}_{desc}_{ver}{ext}"

    def deposer(etape, src, desc, ext=None, contenu=None):
        dossier = os.path.join(sortie, DOSSIERS[etape])
        os.makedirs(dossier, exist_ok=True)
        if contenu is None and not os.path.exists(src):
            manques.append(src)
            return
        e = ext or os.path.splitext(src)[1].lower()
        n = nom(etape, desc, e)
        dest = os.path.join(dossier, n)
        if contenu is not None:
            with open(dest, "wb") as f:
                f.write(contenu)
        else:
            shutil.copyfile(src, dest)
        inventaire.append({"depot": DOSSIERS[etape] + "/" + n, "etape": etape, "role": ROLES[etape],
                           "origine": os.path.relpath(src, racine) if src else "(genere)", "taille_ko": round(os.path.getsize(dest) / 1024)})

    for etape, rel, desc, ext in FICHIERS:
        deposer(etape, os.path.join(racine, rel), desc, ext)

    # referencement des sources (etape 01) : producteur, publication, annee, lien
    from io import StringIO
    buf = StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["fichier_depose", "producteur", "publication", "annee", "lien"])
    w.writerows(SOURCES)
    deposer("01-collecte", None, "sources-referencees", ".csv", contenu=("\ufeff" + buf.getvalue()).encode("utf-8"))

    # LISEZ-MOI
    for etape, lst in LISEZ_MOI.items():
        for src, desc in lst:
            p = os.path.join(racine, src) if not src.startswith("06_depots_modeles") else os.path.join(modele_lisezmoi, os.path.basename(src))
            deposer(etape, p, desc, ".txt")

    # code source
    for etape, scripts in SCRIPTS.items():
        dossier = os.path.join(sortie, DOSSIERS[etape])
        os.makedirs(dossier, exist_ok=True)
        n = nom(etape, "code-source", ".zip")
        with zipfile.ZipFile(os.path.join(dossier, n), "w", zipfile.ZIP_DEFLATED) as z:
            for s in scripts:
                p = os.path.join(racine, "scripts", s)
                if os.path.exists(p):
                    z.write(p, "scripts/" + s)
                else:
                    manques.append(p)
        inventaire.append({"depot": DOSSIERS[etape] + "/" + n, "etape": etape, "role": ROLES[etape],
                           "origine": "scripts/ (" + ", ".join(scripts) + ")", "taille_ko": round(os.path.getsize(os.path.join(dossier, n)) / 1024)})

    # controle des noms
    motif = re.compile(rf"{equipe}_\d\d-[a-z]+_{DEFI}_(engineer|architect|analyst|scientist)_[a-z0-9\-]+_v\d+\.[a-z0-9]+")
    mauvais = [i["depot"] for i in inventaire if not motif.fullmatch(os.path.basename(i["depot"]))]
    assert not mauvais, f"noms hors modele : {mauvais}"
    assert all(" " not in i["depot"] and i["depot"].isascii() for i in inventaire)

    with open(os.path.join(sortie, "INVENTAIRE.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inventaire[0]), delimiter=";")
        w.writeheader()
        w.writerows(inventaire)
    print(f"{len(inventaire)} fichiers deposes dans {sortie} (code d'equipe : {equipe}, version {ver})")
    for etape in DOSSIERS:
        l = [i for i in inventaire if i["etape"] == etape]
        print(f"  {DOSSIERS[etape]:18} {len(l):3} fichiers, {sum(i['taille_ko'] for i in l) / 1024:6.1f} Mo (role {ROLES[etape]})")
    print("fichiers attendus mais absents :", manques or "aucun")


if __name__ == "__main__":
    main()

