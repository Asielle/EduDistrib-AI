"""Extraction du tableau "Repartition des enseignants par sexe, corps et fonction" (IV.1)
des annuaires statistiques de l'enseignement primaire (DGESS), par province, statut et sexe.

Colonnes de chaque ligne source (verifiees sur 2024-2025, p. 201-202 du PDF) :
  corps : I.P., I.C., I.A.C., I.A., Autre, P.C.E, P.E   |  Total
  fonction : directeur, titulaire, suppleant (somme = Total)
  tenant une classe (somme des 3 types de classe : simples, multigrades, double flux)

Entrees : CSV des annuaires (Data Pack) + COD-AB adm2
Sortie  : un CSV long + rapport de controle

Usage :
    python extract_enseignants_IV1.py <dossier_annuaires_csv> <admin2.csv> <fichier_sortie.csv>
"""
import csv
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_tableau_I1 import REGIONS, annee_du_fichier, lire_lignes, num, region_canonique  # noqa: E402
from harmoniser_provinces import cle, construire_ref, lire_admin2  # noqa: E402

CHAMPS = ["nb_enseignants", "tenant_classe", "directeur", "titulaire", "suppleant",
          "classe_simple", "classe_multigrade", "classe_double_flux"]
SEXES = {"femmes": "F", "femme": "F", "hommes": "H", "homme": "H", "total": "T"}
AVERT = []  # ecarts non bloquants (tenant_classe vs somme des types de classe)
BRUIT = {"DT", "SEXE", "CLASSE", "BF/MEBAPLN/SG/DGESS"}


def statut_du_titre(texte):
    """'IV.1.2 Prive' -> 'Prive' ; 'IV.1.3 Public + Prive' -> 'Total' ; urbain/rural -> '' (ignores)."""
    m = re.match(r"^[IVX]+\.?\s*1\.\d+\s*(.*)$", texte, re.I)  # IV.1.x seulement (pas IV.2.x)
    if not m:
        return None
    t = m.group(1).lower().replace("é", "e")
    if "urbain" in t:
        return "Urbain"
    if "rural" in t:
        return "Rural"
    if "public" in t and "priv" in t:
        return "Total"
    if "public" in t:
        return "Public"
    if "priv" in t:
        return "Prive"
    return None


def extraire(chemin):
    annee = annee_du_fichier(os.path.basename(chemin))
    sec, region, ctx = None, None, None
    sortie, ignorees = [], 0
    for page, cells in lire_lignes(chemin):
        if not cells:
            continue
        t0 = cells[0]
        if len(cells) == 1:
            up = t0.upper()
            if re.match(r"^[IVX]+\.", up):  # titre numerote
                st = statut_du_titre(t0)
                if st is not None:
                    sec = st or None
                elif "PAR SEXE, CORPS ET FONCTION" not in up and not re.match(r"^[IVX]+\.\s*PERSONNEL", up):
                    sec = None
                continue
            if sec is None or up in BRUIT:
                continue
            if region_canonique(t0):
                region, ctx = region_canonique(t0), None
            elif up.startswith("TOTAL R"):
                ctx = ("region", None)
            elif up.startswith("TOTAL N") or up.startswith("TOTAL PAYS") or up.startswith("BURKINA"):
                ctx = ("national", None)
            elif re.fullmatch(r"[A-ZÉÈÊÀÂÎÔÛÇ' \-]{3,}", up):
                ctx = ("province", up)
            continue
        if sec is None or ctx is None:
            continue
        label = t0.split()[0].lower() if t0.split() else ""
        if label not in SEXES or len(set(t0.lower().split())) != 1:
            continue
        nums = [num(c) for c in cells[1:]]
        # deux mises en page : 15 valeurs (2023-2025 : 7 corps) ou 13 valeurs (2017-2023 : 5 corps)
        if len(nums) not in (13, 15) or any(n is None for n in nums):
            ignorees += 1
            continue
        k = len(nums) - 8  # nombre de colonnes "corps"
        corps, reste = nums[:k], nums[k:]
        sortie.append({
            "annee_scolaire": annee, "niveau": ctx[0],
            "region_ancienne": "" if ctx[0] == "national" else (region or ""),
            "province": ctx[1] or "", "statut": sec, "sexe": SEXES[label],
            "corps_valeurs": "|".join(str(c) for c in corps), "corps_nb_colonnes": k,
            **dict(zip(CHAMPS, reste)),
            "source_fichier": os.path.basename(chemin), "page_pdf": page,
        })
    return sortie, ignorees


def controles(lignes):
    pb = []
    idx = {}
    for l in lignes:
        idx.setdefault((l["annee_scolaire"], l["niveau"], l["region_ancienne"], l["province"], l["statut"]), {})[l["sexe"]] = l
    for k, d in idx.items():
        if {"F", "H", "T"} <= d.keys():
            if d["F"]["nb_enseignants"] + d["H"]["nb_enseignants"] != d["T"]["nb_enseignants"]:
                pb.append(f"{k} F+H != T")
            t = d["T"]
            if sum(int(x) for x in t["corps_valeurs"].split("|")) != t["nb_enseignants"]:
                pb.append(f"{k} somme des corps != total")
            if t["classe_simple"] + t["classe_multigrade"] + t["classe_double_flux"] != t["tenant_classe"]:
                AVERT.append(k)  # ecart present dans la source elle-meme : simple avertissement
            if t["directeur"] + t["titulaire"] + t["suppleant"] != t["nb_enseignants"]:
                pb.append(f"{k} directeur+titulaire+suppleant != total")
        else:
            pb.append(f"{k} sexes incomplets {sorted(d)}")
    tot = {k: d["T"]["nb_enseignants"] for k, d in idx.items() if "T" in d}
    for (an, niv, reg, prov, st), v in tot.items():
        if niv == "region":
            s = sum(x for (a, n, r, p, s2), x in tot.items() if a == an and n == "province" and r == reg and s2 == st)
            if s != v:
                pb.append(f"{an} {reg} {st}: somme provinces {s} != total region {v}")
        if niv == "national":
            s = sum(x for (a, n, r, p, s2), x in tot.items() if a == an and n == "region" and s2 == st)
            if s != v:
                pb.append(f"{an} {st}: somme regions {s} != total pays {v}")
    for (an, niv, reg, prov, st), v in tot.items():
        if st == "Total":
            pub = tot.get((an, niv, reg, prov, "Public"))
            pri = tot.get((an, niv, reg, prov, "Prive"))
            if pub is not None and pri is not None and pub + pri != v:
                pb.append(f"{an} {niv} {reg} {prov}: public {pub} + prive {pri} != total {v}")
            urb = tot.get((an, niv, reg, prov, "Urbain"))
            rur = tot.get((an, niv, reg, prov, "Rural"))
            if urb is not None and rur is not None and urb + rur != v:
                pb.append(f"{an} {niv} {reg} {prov}: urbain {urb} + rural {rur} != total {v}")
    return pb


def main():
    dossier, admin2, sortie = sys.argv[1:4]
    par_cle = {cle(e["province"]): e for e in construire_ref(lire_admin2(admin2)).values()}
    toutes = []
    for f in sorted(glob.glob(os.path.join(dossier, "*nseignement*rimaire*.csv"))):
        lignes, ign = extraire(f)
        npv = len({l["province"] for l in lignes if l["niveau"] == "province"})
        sts = sorted({l["statut"] for l in lignes})
        print(f"{os.path.basename(f)[:72]:72} lignes={len(lignes):4} provinces={npv:2} statuts={sts} ignorees={ign}")
        toutes += lignes
    pb = controles(toutes)
    for l in toutes:
        e = par_cle.get(cle(l["province"])) if l["niveau"] == "province" else None
        l["province_std"] = e["province"] if e else l["province"]
        l["pcode_province_old"] = e["pcode_old"] if e else ""
        l["pcodes_province_new"] = "|".join(e["pcodes_new"]) if e else ""
        if l["niveau"] == "province" and not e:
            pb.append(f"province sans correspondance : {l['province']} ({l['annee_scolaire']})")
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    cols = ["annee_scolaire", "niveau", "region_ancienne", "province_std", "pcode_province_old",
            "pcodes_province_new", "statut", "sexe", *CHAMPS, "corps_valeurs", "corps_nb_colonnes",
            "source_fichier", "page_pdf"]
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(toutes)
    print(f"\n{len(toutes)} lignes -> {sortie}")
    print(f"{len(AVERT)} groupe(s) avec simples+multigrades+double flux != tenant_classe (ecart de la source, non bloquant)")
    print(f"{len(pb)} controle(s) en echec")
    for p in sorted(set(pb))[:40]:
        print("  -", p)


if __name__ == "__main__":
    main()
