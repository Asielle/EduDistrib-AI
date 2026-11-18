"""Fiche d'une page pour un decideur (PDF) : les messages cles du defi 3, avec des chiffres lus dans les fichiers de 04_analyse et 05.

Usage :
    python build_fiche_decideur.py <racine_du_projet>
Sortie : 05_interpretation/fiche_decideur_une_page.pdf
"""
import base64
import html
import os
import subprocess
import sys
import tempfile

import pandas as pd

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
NB = "\u202f"      # espace fine insecable


def nb(x):
    return f"{int(round(x)):,}".replace(",", NB)


def f1(x):
    return f"{x:.1f}".replace(".", ",")


def main():
    r = os.path.abspath(sys.argv[1])
    A = lambda *p: os.path.join(r, *p)
    idx = pd.read_csv(A("04_analyse", "indice_tension_provinces_2024_2025.csv"), sep=";").sort_values("rang")
    sens = pd.read_csv(A("04_analyse", "projection_sensibilite_normes.csv"), sep=";")
    base = sens[(sens.norme_eleves_salle == 50) & (sens.norme_eleves_enseignant == 40)].set_index("scenario")
    ens = pd.read_csv(A("04_analyse", "optimisation_enseignants_resume.csv"), sep=";")
    e = ens[(ens.scenario == "retour_2020_2021") & (ens.norme_eleves_enseignant == 40) & (ens.rayon_max_km.astype(str) == "aucun")].iloc[0]
    st = pd.read_csv(A("04_analyse", "optimisation_salles_strategies.csv"), sep=";")
    q = st[(st.scenario == "retour_2020_2021") & (st.norme_eleves_salle == 50) & (abs(st.budget_part_du_deficit - 0.5) < 1e-9)].set_index("strategie")
    cout = pd.read_csv(A("04_analyse", "parametres_cout_salle.csv"), sep=";").set_index("id").cout_millions_fcfa_par_salle
    pal = pd.read_csv(A("04_analyse", "modele_fiabilite_provinces.csv"), sep=";")
    ref, sq, au = base.loc["retour_2020_2021"], base.loc["statu_quo"], base.loc["acces_universel"]
    cen = float(cout["central"])
    md = lambda salles: salles * cen / 1000
    forte = idx[idx.niveau == "forte"]
    top = idx.head(5)
    n_vol = int((pal.palier == "tres_volatile").sum())
    inc = pd.read_csv(A("04_analyse", "modele_incertitude_par_palier.csv"), sep=";")
    mg = {x.palier: round(100 * x.erreur_p80) for x in inc[inc.horizon == 3].itertuples()}     # meme marge que le tableau de bord
    n_pal = pal.palier.value_counts()
    lignes = "".join(
        f"<tr><td class=r>{int(x.rang)}</td><td>{html.escape(x.province)}</td><td class=n>{f1(x.indice_tension)}</td><td class=n>{f1(x.eleves_par_salle)}</td>"
        f"<td class=n>{round(100 * x.tbs)}{NB}%</td><td class=n>{nb(x.besoin_salles_2030_retour)}</td></tr>" for x in top.itertuples())
    logo = A("07_documentation", "figures", "logo.png")
    b64 = base64.b64encode(open(logo, "rb").read()).decode() if os.path.exists(logo) else ""
    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>EduDistrib AI - fiche decideur</title><style>
@page {{ size: A4; margin: 13mm 14mm; }}
body {{ font: 10pt/1.35 Calibri, 'Segoe UI', Arial, sans-serif; color: #111; margin: 0; }}
header {{ display: flex; align-items: center; gap: 12px; border-bottom: 3px solid #D79C0C; padding-bottom: 6px; }}
header img {{ height: 46px; }} h1 {{ font-size: 17pt; margin: 0; color: #0B5A2C; }} .sous {{ color: #444; font-size: 9.5pt; }}
h2 {{ font-size: 11pt; color: #0B5A2C; margin: 10px 0 3px; }}
.cles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 9px 0 2px; }}
.cle {{ border: 1px solid #cfd8d2; border-top: 3px solid #0B5A2C; border-radius: 3px; padding: 5px 7px; }}
.cle b {{ display: block; font-size: 15pt; color: #0B5A2C; }} .cle span {{ font-size: 8.5pt; color: #444; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9pt; margin: 3px 0; }} th {{ background: #E3F1E7; text-align: left; }}
th, td {{ border: 1px solid #ccc; padding: 2px 5px; }} td.n, td.r {{ text-align: right; }}
ul {{ margin: 2px 0 2px; padding-left: 16px; }} li {{ margin: 0 0 2px; }}
.lim {{ background: #FFF6DD; border-left: 4px solid #D79C0C; padding: 4px 8px; font-size: 9pt; margin-top: 8px; }}
.pied {{ font-size: 8pt; color: #666; margin-top: 8px; border-top: 1px solid #ddd; padding-top: 3px; }}
</style></head><body>
<header>{'<img src="data:image/png;base64,' + b64 + '">' if b64 else ''}<div><h1>Où construire, où affecter : le primaire au Burkina Faso</h1>
<div class="sous">Fiche d'une page pour décideur · EduDistrib AI · Dem digital · Défi 3, Data Challenge Burkina, édition Éducation 2026</div></div></header>

<div class="cles">
<div class="cle"><b>{len(forte)} provinces</b><span>en tension forte sur 45 (Sahel et Est surtout)</span></div>
<div class="cle"><b>{nb(ref.salles_a_construire)} salles</b><span>à construire d'ici 2030 (scénario de référence), soit environ {nb(md(ref.salles_a_construire))} milliards de FCFA</span></div>
<div class="cle"><b>{nb(ref.enseignants_a_recruter)} enseignants</b><span>manquent en 2030 (référence) ; {nb(e.deplaces)} peuvent être redéployés avant de recruter</span></div>
<div class="cle"><b>{f1(q.loc['equite'].ratio_max)} contre {f1(q.loc['tension'].ratio_max)}</b><span>élèves par salle au maximum avec la moitié du budget : règle « équité » contre règle « tension »</span></div>
</div>

<h2>1. Où la situation est-elle la plus tendue ?</h2>
<table><tr><th>Rang</th><th>Province</th><th>Indice (0-100)</th><th>Élèves / salle</th><th>Scolarisation</th><th>Salles à construire 2030</th></tr>{lignes}</table>
<ul><li>L'indice combine cinq critères en rangs : élèves par salle (25 %), par enseignant (20 %), enfants non scolarisés (25 %), bâti dégradé (15 %), déplacés hébergés (15 %).</li>
<li>Dans les provinces les plus touchées, peu d'élèves par salle ne veut pas dire « bien doté » : les écoles y sont fermées (scolarisation de 12 % au Yagha).</li></ul>

<h2>2. Combien en 2030 ? (50 élèves par salle, 40 par enseignant)</h2>
<ul><li><b>{nb(sq.salles_a_construire)} salles</b> si la scolarisation reste au niveau de 2024-2025 ; <b>{nb(ref.salles_a_construire)}</b> si elle revient au niveau de 2020-2021 ; <b>{nb(au.salles_a_construire)}</b> si tous les enfants sont scolarisés.</li>
<li>Les grandes provinces peu tendues pèsent lourd en volume : Houet (rang {int(idx[idx.province == 'Houet'].rang.iloc[0])}) est la province où il faut construire le plus de salles ({nb(idx[idx.province == 'Houet'].besoin_salles_2030_retour.iloc[0])}) et Kadiogo (rang {int(idx[idx.province == 'Kadiogo'].rang.iloc[0])}) celle où il manque le plus d'enseignants ({nb(idx[idx.province == 'Kadiogo'].besoin_enseignants_2030_retour.iloc[0])}).</li></ul>

<h2>3. Que faire d'abord ?</h2>
<ul><li><b>Redéployer avant de recruter</b> : {nb(e.deplaces)} enseignants, soit {round(100 * e.part_du_deficit_couverte)}{NB}% du manque de référence, peuvent aller des provinces en excédent vers les provinces voisines en déficit.</li>
<li><b>Répartir le budget de salles</b> : avec la moitié du besoin ({nb(q.loc['equite'].budget_salles)} salles, environ {nb(md(q.loc['equite'].budget_salles))} milliards de FCFA), la règle « équité » évite toute classe de plus de 60 élèves ; la règle « tension » concentre {round(100 * q.loc['tension'].part_salles_tension_forte)}{NB}% des salles sur les provinces tendues mais laisse des classes jusqu'à {nb(q.loc['tension'].ratio_max)} élèves. Le choix est politique : le tableau de bord montre l'effet de chaque règle.</li>
<li><b>Utiliser le tableau de bord</b> : changer le scénario, les normes, le budget et le coût d'une salle, et lire la carte, le classement et le plan d'action de chaque province.</li></ul>

<div class="lim"><b>À savoir avant de décider.</b> La norme de 50 élèves par salle vient d'un standard cité par la JICA en 2009 (à confirmer auprès du ministère) ; celle de 40 élèves par enseignant est une hypothèse. Le coût d'une salle est un ordre de grandeur ({nb(cout['bas'])} à {nb(cout['haut'])} millions de FCFA, valeur centrale {f1(cen)}). Les scénarios de reprise supposent le retour de la sécurité. Les besoins de 2030 sont des ordres de grandeur : selon la stabilité passée de la province, la marge d'erreur est d'environ ±{mg['stable']}{NB}% ({n_pal['stable']} provinces stables), ±{mg['variable']}{NB}% ({n_pal['variable']} variables) et ±{mg['tres_volatile']}{NB}% ({n_pal['tres_volatile']} très volatiles) ; c'est un minimum, la fourchette de chaque province est dans le tableau de bord.</div>
<div class="pied">Sources : DGESS/MENAPLN (annuaires 2017-2025), INSD (RGPH 2019, projections), CONASUR (déplacés, mars 2023), IGB/OCHA (COD-AB). Statistiques publiques agrégées. Détail et méthode : documentation de 15 pages maximum.</div>
</body></html>"""
    sortie = A("05_interpretation", "fiche_decideur_une_page.pdf")
    with tempfile.TemporaryDirectory() as tmp:
        h = os.path.join(tmp, "fiche.html")
        open(h, "w", encoding="utf-8").write(page)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={sortie}", "file:///" + h.replace("\\", "/")],
                       capture_output=True, check=True)
    import pymupdf
    n = len(pymupdf.open(sortie))
    print(f"fiche : {n} page(s) -> {sortie}")
    assert n == 1, "la fiche depasse une page"


if __name__ == "__main__":
    main()

