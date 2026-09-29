# Anomalies injectées dans le jeu de données "Atlas Distribution"

Jeu de données généré par `generate_demo_data.py` (seed fixe = 42, reproductible).
Ancrage temporel : "aujourd'hui" = **2026-09-27**. Historique : 2025-10-01 → 2026-09-26.
Horizon de prévision : 13 semaines (jusqu'au 2026-12-27).

Ce fichier sert de corrigé pour vérifier, en Phase 3, que le nœud Code détecte bien
chaque anomalie. Les valeurs exactes peuvent varier légèrement si le script est relancé
avec une seed différente.

---

## 1. Dégradation du délai de paiement — client "Meunier Négoce"

Le client paie de plus en plus tard, mois après mois (conditions contractuelles : 30 jours) :

| Facture | Émission | Échéance | Retard réel | Statut |
|---|---|---|---|---|
| FC…0007 | 2026-04-01 | 2026-05-01 | +6 j | payée |
| FC…0008 | 2026-05-21 | 2026-06-20 | +7 j | payée |
| FC…0009 | 2026-06-08 | 2026-07-08 | +13 j | payée |
| FC…0010 | 2026-07-26 | 2026-08-25 | +20 j | payée |
| FC…0011 | 2026-08-06 | 2026-09-05 | +38 j | **ouverte, en retard** |
| FC…0012 | 2026-09-05 | 2026-10-05 | +48 j (projeté) | **ouverte, en retard** |

**Détection attendue :** le nœud Code doit calculer le DSO par client sur des fenêtres
glissantes (ex. M-3/M-2/M-1) et signaler une tendance haussière significative pour ce
client, distincte des autres (ex. "Petit & Cie" a un retard chronique mais **stable**
autour de 15 j — ce n'est pas une anomalie, juste un mauvais payeur habituel).

## 2. Dépense inhabituelle — catégorie "Frais généraux"

- Transaction du **2026-07-14** : *"Réparation urgente véhicule utilitaire (panne
  moteur)"*, **-4 300 €**.
- Moyenne de la catégorie (hors cette ligne) : **-454,60 €** ; écart-type : **282,73 €**.
- Seuil (moyenne - 2σ) : **-1 020,05 €** → la dépense est très en dehors de la norme.

**Détection attendue :** écart > 2 écarts-types par rapport à la moyenne de la catégorie.

## 3. Semaine(s) de trésorerie tendue à venir

Convergence volontaire, dans la semaine du **4 au 10 octobre 2026**, de :
- Loyer entrepôt trimestriel : **-10 500 €** (échéance 2026-10-08)
- Emprunts (véhicules + local) : **-11 600 €** (échéance 2026-10-05)
- Abonnements logiciels : **-620 €** (échéance 2026-10-05)
- Commande de réapprovisionnement exceptionnelle chez "Global Import SA" (avant pic
  d'activité de fin d'année) : **-100 000 €** (échéance 2026-10-08)

Avec un solde d'ouverture (2025-10-01) fixé à **35 000 €** et un solde actuel résultant
au 2026-09-27 de **≈ 59 710 €**, la simulation interne de QA (voir sortie du script)
projette un solde sous le seuil d'alerte de 15 000 € :
- **Semaine 2** (04→10 oct. 2026) : ≈ 14 331 €
- **Semaine 6** (01→07 nov. 2026) : ≈ 11 458 € (lié aux échéances mensuelles suivantes)

**Détection attendue :** le nœud Code doit projeter le solde semaine par semaine et
flaguer toute semaine où il passe sous le seuil paramétrable (défaut 15 000 €).

## Point méthodologique à trancher en Phase 2/3 (pas une anomalie)

Au-delà de l'horizon des factures déjà émises (~4 à 6 semaines, vu les délais de
paiement clients de 30-45 jours), plus aucune facture "connue" n'arrive à échéance —
la prévision simplifiée redescend alors et se stabilise juste sous le seuil sur les
semaines 11 à 13, faute de nouvelles factures dans le jeu de données (par construction,
aucune facture n'est émise après le 2026-09-26).

C'est cohérent avec le cahier des charges ("encaissements attendus... ajustés du retard
moyen de chaque client" = à partir des factures déjà émises), mais cela veut dire que la
prévision est surtout fiable sur les 4-6 premières semaines, et devient plus incertaine
ensuite. **Deux options pour la Phase 2 :**
- **Option A (fidèle au cahier des charges initial) :** ne projeter que les factures déjà
  émises + charges récurrentes connues. Le nœud Code signale explicitement que
  l'horizon de confiance est plus court, sans extrapoler de nouvelles ventes.
- **Option B :** ajouter une hypothèse de chiffre d'affaires récurrent (ex. moyenne
  mobile des encaissements des 3 derniers mois) pour les semaines au-delà de l'horizon
  des factures connues, ce qui lisse l'artefact de fin de période mais ajoute une
  hypothèse à documenter clairement dans le briefing.

À trancher avec l'utilisateur avant la Phase 3.
