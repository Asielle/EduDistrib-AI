"""Construit la page HTML autonome du tableau de bord (carte, classement, projection 2030).

Entrees (toutes deja produites par les scripts precedents) :
  01_collecte/04_Cartographie_SIG/geojson/bfa_admin2.geojson   contours des provinces (COD-AB)
  04_analyse/indice_tension_provinces_2024_2025.csv            indice de tension
  03_transformation/panel_province_annee.csv                   stock 2024-2025, historique
  02_nettoyage/population_province_age.csv                     population 6-11 ans 2024-2030
Sortie : 05_interpretation/tableau_de_bord_implantation.html (un seul fichier, aucune dependance externe)

Verification avant ecriture : le calcul JavaScript de la page (scripts/dashboard/calc.js) est execute avec Node et compare
aux resultats Python (projection_province_annee_scenario.csv) pour les 3 scenarios et les 45 provinces.

Usage :
    python build_dashboard.py <racine_du_projet>
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import pandas as pd

K = 100.0                 # pixels par degre de latitude
LAT0 = 12.3               # latitude moyenne pour la projection equirectangulaire
TOL = 0.7                 # tolerance de simplification (Douglas-Peucker), en pixels
LON_MIN, LAT_MAX = -5.56, 15.12
PAD = 6


def proj(lon, lat):
    return ((lon - LON_MIN) * math.cos(math.radians(LAT0)) * K + PAD, (LAT_MAX - lat) * K + PAD)


def douglas_peucker(pts, tol):
    n = len(pts)
    if n < 4:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    pile = [(0, n - 1)]
    while pile:
        a, b = pile.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norme = math.hypot(dx, dy) or 1e-12
        dmax, imax = 0.0, -1
        for i in range(a + 1, b):
            d = abs(dy * pts[i][0] - dx * pts[i][1] + bx * ay - by * ax) / norme
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol:
            keep[imax] = True
            pile.append((a, imax))
            pile.append((imax, b))
    return [p for p, k in zip(pts, keep) if k]


def aire_et_centroide(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-9:
        return 0.0, ring[0][0], ring[0][1]
    return a / 2, cx / (6 * (a / 2)), cy / (6 * (a / 2))


def chemins_provinces(geojson):
    """pcode ancien -> {'d': [chemins SVG], 'c': (x, y) centroide pondere par la surface}."""
    out, w = {}, {}
    for f in geojson["features"]:
        po = f["properties"]["adm2_pcode_old"]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for k, ring in enumerate(poly):
                pts = [proj(lon, lat) for lon, lat in ring[:-1]]
                aire, cx, cy = aire_et_centroide(pts)
                simple = douglas_peucker(pts, TOL)
                if len(simple) < 3 or (k > 0 and abs(aire) < 3):
                    continue
                arr = [(round(x, 1), round(y, 1)) for x, y in simple]
                d = "M" + "L".join(f"{x:g} {y:g}" for x, y in arr) + "Z"
                out.setdefault(po, {"d": [], "c": [0, 0]})["d"].append(d)
                if k == 0:  # anneau exterieur : sert au centroide
                    w[po] = w.get(po, 0) + abs(aire)
                    out[po]["c"][0] += cx * abs(aire)
                    out[po]["c"][1] += cy * abs(aire)
    for po, e in out.items():
        e["c"] = [round(e["c"][0] / w[po], 1), round(e["c"][1] / w[po], 1)]
    return out


def nz(x, d):
    """Nombre arrondi, ou None si la valeur est absente."""
    return None if pd.isna(x) else round(float(x), d)


def construire_donnees(racine):
    idx = pd.read_csv(os.path.join(racine, "04_analyse", "indice_tension_provinces_2024_2025.csv"), sep=";",
                      dtype={"pcode_province_old": str})
    pan = pd.read_csv(os.path.join(racine, "03_transformation", "panel_province_annee.csv"), sep=";",
                      dtype={"pcode_province_old": str})
    pop = pd.read_csv(os.path.join(racine, "02_nettoyage", "population_province_age.csv"), sep=";",
                      dtype={"pcode_province_old": str})
    p611 = pop[(pop.groupe_age == "6-11") & (pop.sexe == "E")]
    pop_tab = p611.pivot(index="pcode_province_old", columns="annee", values="population")
    base = pan[pan.annee_debut == 2024].set_index("pcode_province_old")
    avant = pan[pan.annee_debut == 2020].set_index("pcode_province_old")

    provinces = []
    for r in idx.itertuples(index=False):
        pc = r.pcode_province_old
        b = base.loc[pc]
        provinces.append({
            "id": pc, "nom": r.province, "region": r.region_ancienne, "regionNew": r.region_nouvelle,
            "nouveaux": r.pcodes_province_new.split("|"),
            "rang": int(r.rang), "niveau": r.niveau, "indice": round(float(r.indice_tension), 1),
            "sc": {"salles": round(float(r.score_salles), 1), "enseignants": round(float(r.score_enseignants), 1),
                   "acces": round(float(r.score_acces), 1), "bati": round(float(r.score_bati), 1),
                   "deplaces": round(float(r.score_deplaces), 1)},
            "parSalle": round(float(r.eleves_par_salle), 1), "parEns": round(float(r.eleves_par_enseignant), 1),
            "tbs24": float(b["nb_eleves"] / pop_tab.loc[pc, 2024]), "tbs20": float(avant.loc[pc, "nb_eleves"] / pop_tab.loc[pc, 2020]),
            "partPrec": round(float(r.part_salles_precaires), 4), "partMauvais": round(float(r.part_salles_murs_mauvais_etat), 4),
            "precaires": int(b["salles_paille_banco"]),
            "pdi": int(r.pdi_hebergees_mars_2023), "pdi100": round(float(r.pdi_par_100_hab_mars_2023), 1),
            "salles": int(b["nb_salles"]), "ens": int(b["nb_enseignants"]), "eleves24": int(b["nb_eleves"]),
            "pop": [int(pop_tab.loc[pc, a]) for a in range(2024, 2031)],
            "acces": {"dist": nz(b["distance_theorique_ecole_km"], 1), "dist20": nz(avant.loc[pc, "distance_theorique_ecole_km"], 1),
                      "km2": nz(b["km2_par_ecole"], 0), "ecoles": int(b["nb_ecoles"]), "enfEcole": nz(b["enfants_6_11_par_ecole"], 0)},
            "milieu": {"partRurale": nz(b["part_eleves_rurale"], 4), "epeU": nz(b["eleves_par_enseignant_urbain"], 1),
                       "epeR": nz(b["eleves_par_enseignant_rural"], 1), "rapport": nz(b["rapport_rural_urbain_eleves_par_ens"], 2),
                       "deplacer": None if pd.isna(b["enseignants_a_deplacer_urbain_vers_rural"]) else int(b["enseignants_a_deplacer_urbain_vers_rural"]),
                       "partFillesU": nz(b["part_filles_urbain"], 3), "partFillesR": nz(b["part_filles_rural"], 3)},
        })
    hist = (pan.groupby("annee_debut")["nb_eleves"].sum().loc[2017:2024]).astype(int)
    forte = [p["indice"] for p in provinces if p["niveau"] == "forte"]
    return {
        "provinces": provinces,
        "histEleves": [{"annee": int(a), "eleves": int(v)} for a, v in hist.items()],
        "seuilForte": min(forte),
        "pdiTotal": int(sum(p["pdi"] for p in provinces)),
        "poids": {"salles": 25, "enseignants": 20, "acces": 25, "bati": 15, "deplaces": 15},
    }


def verifier_calcul_js(racine, donnees):
    """Compare le calcul JavaScript de la page aux sorties Python (normes 50 par salle et 40 par enseignant, horizon 2030)."""
    pr = pd.read_csv(os.path.join(racine, "04_analyse", "projection_2030_resume.csv"), sep=";", dtype={"pcode_province_old": str})
    attendu = {(r.scenario, r.pcode_province_old): (r.salles_a_construire, r.enseignants_a_recruter, r.eleves_projetes)
               for r in pr.itertuples()}
    cle_sc = {"statu_quo": "statu_quo", "retour": "retour_2020_2021", "universel": "acces_universel"}
    code = (
        "const c=require(process.argv[1]);const d=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));"
        "const out=[];for(const sc of ['statu_quo','retour','universel'])for(const p of d.provinces){"
        "const b=c.besoins(p,sc,50,40,2030);out.push([sc,p.id,b.salles,b.ens,b.eleves]);}"
        "console.log(JSON.stringify(out));")
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "d.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(donnees, fh)
        res = subprocess.run(["node", "-e", code, os.path.join(racine, "scripts", "dashboard", "calc.js"), f],
                             capture_output=True, text=True, check=True)
    ecarts = 0
    maxe = 0
    for sc, pid, s, e, el in json.loads(res.stdout):
        a_s, a_e, a_el = attendu[(cle_sc[sc], pid)]
        d = max(abs(s - a_s), abs(e - a_e), abs(el - a_el))
        maxe = max(maxe, d)
        ecarts += d > 1
    print(f"verification JS vs Python : {len(attendu)} valeurs, ecart max {maxe}, {ecarts} ecart(s) > 1")
    assert ecarts == 0, "le calcul de la page ne reproduit pas la projection Python"


def logo_html(racine, largeur=440):
    """Logo du projet, reduit et compresse (WebP) puis integre en base64 : la page reste autonome."""
    import base64
    import glob
    import io

    from PIL import Image
    fichiers = glob.glob(os.path.join(racine, "Logo*.png"))
    if not fichiers:
        print("logo introuvable : page sans logo")
        return ""
    im = Image.open(fichiers[0]).convert("RGB")
    h = round(im.height * largeur / im.width)
    im = im.resize((largeur, h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=84, method=6)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    print(f"logo : {im.width}x{im.height}, {len(buf.getvalue()) / 1024:.0f} Ko (original {os.path.getsize(fichiers[0]) / 1024:.0f} Ko)")
    return (f'<img src="data:image/webp;base64,{b64}" width="{im.width}" height="{im.height}" '
            'alt="Logo EduDistrib AI : une éducation mieux répartie, pour un Burkina plus éduqué">')


def donnees_optimisation(racine):
    """Redeploiement des enseignants (resultats du programme lineaire, calcules en Python) pour les 9 combinaisons
    scenario x norme d'enseignants, sans limite de rayon."""
    cle_sc = {"statu_quo": "statu_quo", "retour_2020_2021": "retour", "acces_universel": "universel"}
    d = os.path.join(racine, "04_analyse")
    res = pd.read_csv(os.path.join(d, "optimisation_enseignants_resume.csv"), sep=";")
    res = res[res.rayon_max_km.astype(str) == "aucun"]
    flux = pd.read_csv(os.path.join(d, "optimisation_enseignants_flux.csv"), sep=";")
    flux = flux[flux.rayon_max_km.astype(str) == "aucun"]
    prov = pd.read_csv(os.path.join(d, "optimisation_enseignants_provinces.csv"), sep=";", dtype={"pcode_province_old": str})
    out = {}
    for r in res.itertuples():
        k = f"{cle_sc[r.scenario]}|{r.norme_eleves_enseignant}"
        f = flux[(flux.scenario == r.scenario) & (flux.norme_eleves_enseignant == r.norme_eleves_enseignant)].sort_values("enseignants", ascending=False)
        pv = prov[(prov.scenario == r.scenario) & (prov.norme_eleves_enseignant == r.norme_eleves_enseignant)]
        out[k] = {
            "deficit": int(r.deficit_total), "excedent": int(r.excedent_total), "deplaces": int(r.deplaces),
            "aRecruter": int(r.a_recruter_avec_redeploiement), "distMoy": float(r.distance_moyenne_km), "distMax": float(r.distance_max_km),
            "flux": [[x.pcode_origine, x.pcode_destination, int(x.enseignants), float(x.distance_km)] for x in f.itertuples()],
            "prov": {x.pcode_province_old: [int(x.sortants), int(x.entrants), int(x.reste_a_recruter)] for x in pv.itertuples()},
        }
    return out


def donnees_fiabilite(racine):
    """Evaluation du modele predictif (scripts/modele_predictif.py) : erreurs par methode et par palier de stabilite."""
    d = os.path.join(racine, "04_analyse")
    S = pd.read_csv(os.path.join(d, "modele_evaluation_synthese.csv"), sep=";")
    noms = [("demographique", "-", "Taux de scolarisation constant (démographie seule)"),
            ("constant", "-", "Effectifs constants"),
            ("momentum", "-", "Même croissance que l'année précédente"),
            ("rebond", "REB", "Rebond vers le pic passé (régression robuste, 1 variable)"),
            ("huber", "REC", "Régression robuste, 3 variables"),
            ("huber", "FULL", "Régression robuste, 5 variables (1 an seulement)"),
            ("arbres", "REC", "Arbres de gradient, 3 variables"),
            ("arbres", "FULL", "Arbres de gradient, 5 variables (1 an seulement)")]
    meth = []
    for m, v, nom in noms:
        r = {"nom": nom}
        for h in (1, 2, 3):
            x = S[(S.methode == m) & (S.variables == v) & (S.horizon == h)]
            r[f"h{h}"] = round(float(x.wape.iloc[0]), 4) if len(x) else None
        meth.append(r)
    P = pd.read_csv(os.path.join(d, "modele_fiabilite_provinces.csv"), sep=";", dtype={"pcode_province_old": str})
    seg = pd.read_csv(os.path.join(d, "modele_fiabilite_par_palier.csv"), sep=";")
    lab = {"stable": "Stable", "variable": "Variable", "tres_volatile": "Très volatile"}
    paliers = []
    for pal in ("stable", "variable", "tres_volatile"):
        row = {"palier": pal, "label": lab[pal], "provinces": int((P.palier == pal).sum())}
        for h in (1, 3):
            x = seg[(seg.palier == pal) & (seg.methode == "demographique") & (seg.horizon == h)]
            row[f"h{h}"] = round(float(x.wape.iloc[0]), 4) if len(x) else None
        row["liste"] = sorted(P[P.palier == pal].province) if pal == "tres_volatile" else []
        paliers.append(row)
    return {"methodes": meth, "paliers": paliers,
            "prov": {r.pcode_province_old: {"p": r.palier, "v": float(r.volatilite)} for r in P.itertuples()}}


def verifier_allocation_js(racine, donnees):
    """Compare l'allocation de salles calculee par la page (JavaScript) aux resultats Python (optimisation_2030.py)."""
    cle_sc = {"statu_quo": "statu_quo", "retour_2020_2021": "retour", "acces_universel": "universel"}
    s = pd.read_csv(os.path.join(racine, "04_analyse", "optimisation_salles_strategies.csv"), sep=";")
    code = (
        "const c=require(process.argv[1]);const d=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));"
        "const rows=JSON.parse(require('fs').readFileSync(process.argv[3],'utf8'));const out=[];"
        "for(const r of rows){const y=c.allouer(d.provinces,r.sc,r.ns,r.B,r.strat);out.push(c.metriquesAlloc(d.provinces,r.sc,r.ns,y));}"
        "console.log(JSON.stringify(out));")
    rows = [{"sc": cle_sc[r.scenario], "ns": int(r.norme_eleves_salle), "B": int(r.budget_salles), "strat": r.strategie} for r in s.itertuples()]
    with tempfile.TemporaryDirectory() as tmp:
        f1, f2 = os.path.join(tmp, "d.json"), os.path.join(tmp, "r.json")
        with open(f1, "w", encoding="utf-8") as fh:
            json.dump(donnees, fh)
        with open(f2, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        res = subprocess.run(["node", "-e", code, os.path.join(racine, "scripts", "dashboard", "calc.js"), f1, f2],
                             capture_output=True, text=True, check=True)
    mauvais = 0
    for r, m in zip(s.itertuples(), json.loads(res.stdout)):
        ok = (abs(m["ratioMax"] - r.ratio_max) < 0.011 and m["auDessus50"] == r.provinces_au_dessus_50
              and abs(m["surcharge"] - r.eleves_en_surcharge) <= 1 and abs(m["partForte"] - r.part_salles_tension_forte) < 0.0011)
        mauvais += not ok
    print(f"verification allocation JS vs Python : {len(s)} cas, {mauvais} ecart(s)")
    assert mauvais == 0, "l'allocation de la page ne reproduit pas optimisation_2030.py"


def main():
    racine = sys.argv[1]
    with open(os.path.join(racine, "01_collecte", "04_Cartographie_SIG", "geojson", "bfa_admin2.geojson"), encoding="utf-8") as f:
        geo = json.load(f)
    chemins = chemins_provinces(geo)
    donnees = construire_donnees(racine)
    verifier_calcul_js(racine, donnees)
    verifier_allocation_js(racine, donnees)
    donnees["opt"] = {"ens": donnees_optimisation(racine)}
    donnees["fiab"] = donnees_fiabilite(racine)
    cout = pd.read_csv(os.path.join(racine, "04_analyse", "parametres_cout_salle.csv"), sep=";")
    donnees["cout"] = [{"id": r.id, "libelle": r.libelle, "valeur": float(r.cout_millions_fcfa_par_salle)} for r in cout.itertuples()]

    ids = {p["id"] for p in donnees["provinces"]}
    assert ids == set(chemins), f"provinces sans contour : {ids - set(chemins)}"
    for p in donnees["provinces"]:
        p["centre"] = chemins[p["id"]]["c"]

    svg = []
    for p in donnees["provinces"]:
        traces = "".join(f'<path d="{d}"/>' for d in chemins[p["id"]]["d"])
        svg.append(f'<g class="prov" data-id="{p["id"]}">{traces}</g>')
    largeur = round((2.5 - LON_MIN) * math.cos(math.radians(LAT0)) * K + 2 * PAD)
    hauteur = round((LAT_MAX - 9.3) * K + 2 * PAD)
    carte = f'<svg id="carte" viewBox="0 0 {largeur} {hauteur}" role="img" aria-label="Carte des 45 provinces du Burkina Faso">' \
            + "".join(svg) + '<g id="etiquettes"></g></svg>'

    tpl_dir = os.path.join(racine, "scripts", "dashboard")
    with open(os.path.join(tpl_dir, "template.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(tpl_dir, "calc.js"), encoding="utf-8") as f:
        calc = re.sub(r"if \(typeof module.*\n?", "", f.read())
    html = html.replace("/*__CALC__*/", calc).replace("/*__DATA__*/", "const DATA = " + json.dumps(donnees, ensure_ascii=False, separators=(",", ":")) + ";")
    html = html.replace("<!--__MAP__-->", carte)
    html = html.replace("<!--__LOGO__-->", logo_html(racine))
    sortie = os.path.join(racine, "05_interpretation", "tableau_de_bord_implantation.html")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    with open(sortie, "w", encoding="utf-8") as f:
        f.write(html)
    npts = sum(d.count("L") + 1 for e in chemins.values() for d in e["d"])
    print(f"{len(chemins)} provinces, {npts} points de contour (tolerance {TOL} px) ; page : {os.path.getsize(sortie) / 1024:.0f} Ko -> {sortie}")


if __name__ == "__main__":
    main()
