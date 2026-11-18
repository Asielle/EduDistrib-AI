<p align="center"><img src="docs/logo.png" alt="EduDistrib AI" width="420"></p>

# EduDistrib AI

Prototype d'aide à la décision pour **répartir les salles de classe et les enseignants du primaire au Burkina Faso** et estimer les besoins à l'horizon 2030.
Projet de l'équipe **Dem digital**, Data Challenge Burkina, édition Éducation 2026, **défi 3** (optimisation de la répartition des infrastructures et du personnel enseignant).

**Tableau de bord en ligne** : https://asielle.github.io/EduDistrib-AI/05_interpretation/tableau_de_bord_implantation.html

## Ce que fait le projet

- **Nettoyage** de tableaux d'annuaires statistiques (PDF convertis en CSV) : écoles, salles, enseignants, état et équipement des écoles, élèves par milieu, population, déplacés internes.
- **Panel** province × année scolaire (45 provinces, 2017-2018 à 2024-2025), 91 colonnes, avec contrôles de totaux.
- **Indice de tension** par province (5 critères en rangs, poids 25/20/25/15/15) et test de robustesse.
- **Projection 2030** en trois scénarios (statu quo, retour au niveau 2020-2021, accès universel) et sensibilité aux normes.
- **Optimisation** : redéploiement des enseignants (programme linéaire, solveur HiGHS) et répartition d'un budget de salles (trois règles).
- **Évaluation d'un modèle prédictif** contre des références simples (résultat négatif conservé).
- **Tableau de bord** HTML avec carte, classement, plan d'action et fiabilité (`05_interpretation/tableau_de_bord_implantation.html`), et **fiche d'une page** pour décideur.

Résultats clés (scénario de référence, 50 élèves par salle, 40 par enseignant) : 15 provinces en tension forte, 17 447 salles à construire d'ici 2030, 13 157 enseignants à recruter dont 2 318 peuvent être redéployés. La méthode, les limites et les résultats détaillés sont dans `docs/`.

## Mise à jour v2

- **Contrôle du panel** : la somme des provinces reproduit exactement les totaux régionaux officiels de la DGESS (13 régions × 8 ans, écart 0,0 %). Le creux de 2022-2023 dans certaines provinces vient des données officielles, pas de l'extraction.
- **Pistes testées pour le modèle** (mélange démographique + Huber, modèle par palier de stabilité, nouveaux inscrits au CP1) : aucune ne bat la référence démographique de façon constante. Résultats négatifs conservés dans `docs/04_modele.txt`.
- **Fourchette d'incertitude** de la projection 2030 : ± 10 % (provinces stables), ± 37 % (variables), ± 74 % (très volatiles), d'après l'erreur réelle à 3 ans. Affichée dans le détail de chaque province du tableau de bord ; calcul vérifié contre Python avant écriture. C'est un minimum : 2030 est plus loin que le test.
- **Nouveaux scripts** : `controle_regions.py`, `contexte_regional.py`, `esu_province.py`, `modele_cp1.py`, `fourchette_projection.py` (déjà branchés dans `relancer_tout.py`). Ils lisent le classeur DGESS 2015-2025 (à la racine) et la transcription ESU (`01_collecte/esu_transcription_manuelle/`), qui font partie du Data Pack et ne sont pas dans ce dépôt.

## Hypothèses à connaître

- **50 élèves par salle** : standard du primaire cité par la JICA en 2009, peut avoir évolué, non confirmé par le ministère. **40 élèves par enseignant** : hypothèse de travail.
- Le **coût d'une salle** (10 / 15,7 / 33 millions de FCFA) est un ordre de grandeur, avec ses sources dans `04_analyse/parametres_cout_salle.csv`.
- Les scénarios de reprise supposent le retour de la sécurité : ce sont des besoins potentiels, pas des prévisions.

## Relancer la chaîne

Les **données du challenge ne sont pas dans ce dépôt** : le Data Pack est réservé aux équipes admises et ses données ne servent qu'au challenge. Pour relancer, placez le Data Pack dans `01_collecte/` (même arborescence que le Data Pack), puis :

```
pip install pandas numpy scipy scikit-learn pillow matplotlib pymupdf
python scripts/relancer_tout.py .
```

La chaîne s'exécute en environ 40 secondes (nettoyage, panel, projection, indice, optimisation, modèle, tableau de bord, fiche). Testée sur une copie propre : les tables et le tableau de bord produits sont identiques à ceux de référence. Le calcul JavaScript du tableau de bord est vérifié contre le calcul Python avant écriture (Node.js requis pour cette vérification).

## Structure

| Dossier | Contenu |
|---|---|
| `scripts/` | tous les scripts, dans l'ordre de `relancer_tout.py` ; `scripts/dashboard/` : modèle du tableau de bord |
| `04_analyse/parametres_cout_salle.csv` | coût d'une salle, trois repères avec sources |
| `05_interpretation/` | tableau de bord et fiche d'une page |
| `docs/` | notes de méthode et journaux de chaque étape (LISEZ-MOI) |

## Sources

DGESS / MENAPLN (annuaires statistiques du primaire 2017-2025), INSD (RGPH 2019, projections 2020-2035), CONASUR via HDX (déplacés internes), IGB / OCHA via HDX (limites COD-AB), HOT / OpenStreetMap via HDX (contrôle de couverture). Toutes les données sont des statistiques publiques agrégées.

## Usage d'un assistant d'IA

Le code et la documentation ont été écrits avec l'aide de Claude (Anthropic, via Claude Code), les choix de méthode ayant été discutés et validés par l'équipe. Les résultats négatifs ont été conservés. Détail dans la documentation remise au challenge.

## Licence

Aucune licence n'est définie à ce stade : tous droits réservés par défaut.
