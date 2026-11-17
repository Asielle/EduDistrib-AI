# Schéma des données : EduDistrib AI (Défi 3)

Modèle commun **province × année × statut**, au niveau des 45 anciennes provinces (celles des annuaires DGESS).
Toutes les tables se rejoignent par le **P-code de l'ancienne province** (`pcode_province_old`, ex. `BF5603` = Soum), issu du COD-AB.

## Clés de jointure

| Clé | Rôle |
|---|---|
| `pcode_province_old` | Identifiant de la province, commun à toutes les tables |
| `annee_scolaire` (ex. `2024-2025`) / `annee_debut` (ex. `2024`) | Année scolaire. L'année civile `annee_debut` est celle de la population INSD correspondante |
| `statut` | `Public`, `Prive` ou `Total` (public + privé) |
| `sexe` | `F`, `H`, `T` (tableau des enseignants) ; `H`, `F`, `E` (population) |

## Tables

| Table | Étape | Grain (clé primaire) | Lignes | Source |
|---|---|---|---|---|
| `ref_provinces` | 02 | `pcode_province_old` | 45 | COD-AB (adm2, colonnes `*_old`) + noms DGESS |
| `tableau_I1_propre` | 02 | `annee_scolaire`, `niveau`, `pcode_province_old`, `statut` | 1 413 | Annuaires DGESS, tableau I.1 / II.1 |
| `enseignants_IV1_propre` | 02 | `annee_scolaire`, `niveau`, `pcode_province_old`, `statut`, `sexe` (statut : `Public`, `Prive`, `Total`, `Urbain`, `Rural`) | 7 065 | Annuaires DGESS, tableaux IV.1 (dont IV.1.4 urbain et IV.1.5 rural) |
| `eleves_milieu_propre` | 02 | `annee_scolaire`, `niveau`, `pcode_province_old` | 463 | Annuaires DGESS, tableau I.2 (élèves, filles, urbain et rural) |
| `salles_etat_propre` | 02 | `annee_scolaire`, `niveau`, `pcode_province_old`, `statut` | 1 389 | Annuaires DGESS, tableaux VI.1 à VI.4 |
| `equipement_ecoles_propre` | 02 | `annee_scolaire`, `niveau`, `pcode_province_old`, `statut` | 1 383 | Annuaires DGESS, tableau V.4 / VI.4 (eau potable, électricité, latrines, cantine, clôture) |
| `population_province_age` | 02 | `pcode_province_old`, `annee`, `groupe_age`, `sexe` | 48 909 | INSD, RGPH 2019, projections 2020-2035 |
| `pdi_province_date` | 02 | `pcode_province_old`, `date` | 1 864 | CONASUR (via HDX) |
| `panel_province_annee` | 03 | `annee_scolaire`, `pcode_province_old` | 360 | Jointure des tables ci-dessus |
| `projection_province_annee_scenario` | 04 | `scenario`, `annee_debut`, `pcode_province_old` | 945 | Panel + population |
| `optimisation_enseignants_*`, `optimisation_salles_*` | 04 | voir leurs LISEZ-MOI | | Projection + indice |
| `modele_evaluation_*`, `modele_fiabilite_*` | 04 | méthode × origine × horizon ; province | | Panel + population + PDI |
| `indice_tension_provinces_2024_2025` | 05 | `pcode_province_old` | 45 | Panel 2024-2025 |

`niveau` vaut `province`, `region` (13 anciennes régions) ou `national` : les totaux sont dans les mêmes tables que les provinces, ce qui permet les contrôles de somme.

## Relations

```
                         ref_provinces (45)
                                 | pcode_province_old
     +-------------+-------------+-------------+--------------+
     |             |             |             |              |
 tableau_I1   enseignants_IV1  salles_etat  population     pdi_province  (+ equipement, eleves_milieu)
 (annee,      (annee,statut,   (annee,      (annee,        _date
  statut)      sexe)            statut)      groupe, sexe)  (date)
     |             |             |             |              |
     +-------------+------+------+-------------+--------------+
                          |
                 panel_province_annee  (annee_scolaire x pcode_province_old, 360 lignes)
                          |
        +-----------------+------------------+--------------------+
        |                 |                  |                    |
  projection 2030   modele prédictif   indice de tension   optimisation
  (3 scénarios)     (évaluation)       (45 provinces)      (enseignants, salles)
                          |
                  prototype EduDistrib AI (tableau de bord avec carte)
```

## Volumes et traçabilité

- Chaque ligne issue d'un annuaire garde `source_fichier` et `page_pdf` : on remonte à la page du PDF d'origine.
- Types : identifiants et noms en texte ; effectifs en entiers ; ratios en réels ; booléens `scindee` et `donnee_absente`.
- Valeurs manquantes : jamais remplacées par zéro. Cas particuliers documentés : Komandjari 2022-2023 absente des annuaires (`donnee_absente`), population absente avant 2020, déplacés absents après mars 2023.

## Découpage administratif

Les 13 anciennes régions et les 17 nouvelles ne s'emboîtent pas. L'unité d'analyse est donc l'ancienne province, et chaque ligne porte aussi la région nouvelle (`region_nouvelle`, `pcode_region_nouvelle`) et les P-codes nouveaux (`pcodes_province_new`). Soum et Tapoa, scindées, gardent deux P-codes nouveaux.

## Dictionnaire des variables

Le panel a son dictionnaire complet : `dictionnaire_variables.csv` (nom, type, description de chacune des 91 colonnes). Les autres tables sont décrites dans le `LISEZ-MOI.txt` de leur dossier.




