# CFO Virtuel — Atlas Distribution

Workflow n8n de pilotage financier hebdomadaire pour une PME de négoce : chaque
lundi à 8h, il lit les données comptables, calcule une prévision de trésorerie
à 13 semaines, détecte les signaux d'alerte (retard de paiement client,
dépense anormale, tension de trésorerie), fait rédiger un briefing par un LLM
(Google Gemini) et l'envoie sur Telegram avec un détail chiffré garanti
exact en message séparé.

Projet de démonstration construit sur une PME fictive ("Atlas Distribution",
négoce, ~2 M€ de CA annuel). Les principes et l'architecture sont directement
réutilisables pour un client réel (voir [Adapter à un client réel](#adapter-à-un-client-réel)).

## Principe directeur

**Tous les calculs financiers sont faits en JavaScript, dans un seul nœud
Code.** Le LLM ne calcule jamais un chiffre : il reçoit un JSON déjà calculé
et se contente de l'interpréter et de le mettre en mots. C'est ce qui rend le
briefing fiable si le LLM se trompe, il se trompe sur la formulation,
jamais sur les montants.

## Architecture

```
Schedule Trigger (lundi 8h) ─┐
Déclencheur manuel (test)   ─┴─► Transactions bancaires
                                       │ (executeOnce, en série)
                                       ▼
                                 Factures clients
                                       │
                                       ▼
                                 Factures fournisseurs
                                       │
                                       ▼
                                 Charges récurrentes
                                       │
                                       ▼
                                 Solde bancaire de départ
                                       │
                                       ▼
                     Calcul financier (délai paiement, prévisions, anomalies)
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                             ▼
              Envoyer le détail chiffré      Modèle Gemini (Chat Model)
                   (Telegram)                         │
                                                        ▼
                                          Rédaction du briefing (Gemini)
                                                        │
                                                        ▼
                                          Envoyer le briefing (Telegram)

Toute sortie d'erreur (les 5 lectures Sheets, le nœud Code, Gemini,
les 2 envois Telegram) converge vers → Alerte erreur (Telegram)
```

**Pourquoi les 5 lectures Google Sheets sont chaînées en série (pas en
parallèle) :** en n8n, plusieurs nœuds connectés vers la même entrée ne
s'attendent pas mutuellement le nœud suivant démarre dès que la première
branche a livré ses données, sans garantie que les autres aient fini. D'où le
chaînage strict + `executeOnce: true` sur chaque nœud Sheets (sinon, recevant
les items du nœud précédent, il relirait sa feuille une fois par item reçu).

## Credentials à configurer dans n8n

| Credential | Type n8n | Utilisée par |
|---|---|---|
| Google Sheets | `Google Sheets OAuth2 API` | Les 5 nœuds de lecture |
| Google Gemini | `Google Gemini(PaLM) Api` (clé API gratuite [Google AI Studio](https://aistudio.google.com/)) | Modèle Gemini (Chat Model) |
| Telegram | `Telegram API` (token de bot via [@BotFather](https://t.me/BotFather)) | Les 3 nœuds Telegram |

Aucune clé n'est écrite en dur dans le workflow — toutes passent par le
système de credentials n8n. Le `chat_id` Telegram (identifiant numérique du
destinataire, pas un secret) est en revanche stocké directement dans les
paramètres des 3 nœuds Telegram.

## Installation

1. Dans n8n : **Workflows → Import from File** → sélectionner
   [`workflow/cfo-virtuel.json`](workflow/cfo-virtuel.json).
2. L'export est nettoyé de toute donnée personnelle — 3 choses à renseigner
   après import :
   - Les **5 nœuds Google Sheets** : sélectionneur "Document" → remplacer
     `VOTRE_ID_GOOGLE_SHEET` par l'ID de votre propre classeur (visible dans
     son URL, entre `/d/` et `/edit`).
   - Les **3 nœuds Telegram** : champ "Chat ID" → remplacer
     `VOTRE_CHAT_ID_TELEGRAM` par l'identifiant numérique du destinataire
     (demandez-le à [@get_id_bot](https://t.me/get_id_bot) sur Telegram).
   - Les **9 nœuds concernés** (5 Sheets + 3 Telegram + 1 Gemini) : le
     sélecteur de credential est vide après import (normal, aucune clé n'est
     exportée) attacher vos propres credentials, voir tableau ci-dessous.

## Source de données : le Google Sheet

Un classeur à 5 onglets, données synthétiques générées par
[`demo-data/generate_demo_data.py`](demo-data/generate_demo_data.py) :

| Onglet | Colonnes attendues |
|---|---|
| Transactions bancaires | date, libellé, montant, catégorie |
| Factures clients | numéro, client, montant, date d'émission, date d'échéance, date de paiement |
| Factures fournisseurs | numéro, fournisseur, montant, date d'émission, date d'échéance, date de paiement |
| Charges récurrentes | libellé, catégorie, montant, fréquence, prochaine échéance, intervalle (jours) |
| Solde bancaire de départ | solde d'ouverture (une seule ligne) |

**Le nœud Code ne dépend pas de l'orthographe exacte des en-têtes.** Une
fonction `getVal()` compare les noms de colonnes après avoir retiré accents,
casse, espaces et prépositions françaises ("d'", "de", "du"...) — `"Date
d'émission"`, `"date_emission"` et `"DATE EMISSION"` pointent tous vers le
même champ. Utile si un client (ou vous-même) renomme les colonnes en cours
de route ; voir aussi la section [Adapter à un client réel](#adapter-à-un-client-réel)
pour aller plus loin.

## Ce que calcule le nœud Code

Constantes ajustables en tête du nœud `Calcul financier (délai paiement,
prévisions, anomalies)` :

| Constante | Rôle | Valeur actuelle |
|---|---|---|
| `SEUIL_ALERTE_TRESORERIE` | Seuil (€) sous lequel une semaine est signalée | 15 000 |
| `FORECAST_WEEKS` | Horizon de prévision | 13 semaines |
| `SEUIL_DEGRADATION_JOURS` | Écart (jours) entre les 2 fenêtres de 3 mois pour flaguer un client en dégradation | 10 |
| `Z_SCORE_SEUIL` | Seuil d'écart-type pour une dépense anormale | 2 |
| `FENETRE_ANOMALIE_DEPENSE_JOURS` | N'afficher que les dépenses anormales des N derniers jours | 30 |
| `CATEGORIES_ANOMALIE_DEPENSES` | Catégories analysées pour la détection de dépenses anormales | Frais généraux, Loyer, Salaires, Emprunt, Abonnements |

**1. Retard moyen après échéance** nombre de jours entre l'échéance d'une
facture et son paiement réel (ou, si elle est encore ouverte et déjà en
retard, entre l'échéance et aujourd'hui). Calculé globalement et par client,
sur une fenêtre glissante de 3 mois comparée aux 3 mois précédents. **Ce
n'est volontairement pas le DSO comptable classique** (encours / CA × nb de
jours) : ce ratio mélange volume de vente et vitesse de paiement, ce qui
produit un chiffre qui se lit mal à l'oral et peut sembler contredire un
"retard moyen" mesuré autrement. Un seul indicateur, une seule lecture.

**2. Prévision de trésorerie à 13 semaines** solde actuel (solde
d'ouverture + somme des transactions bancaires) projeté semaine par semaine :
encaissements attendus (factures clients ouvertes, échéance ajustée du
retard moyen récent du client concerné), décaissements fournisseurs
(factures ouvertes, payées à échéance) et charges récurrentes (projetées
depuis leur prochaine échéance selon leur fréquence). **Aucune extrapolation
de chiffre d'affaires non encore facturé** : au-delà de l'horizon des
factures déjà émises (`horizon_fiable_semaines`, calculé automatiquement),
la prévision continue mécaniquement mais devient indicative — les alertes
de `semaines_sous_seuil_indicatif` ne doivent pas être lues comme des
ruptures de trésorerie confirmées (le prompt Gemini applique cette règle
explicitement).

**3. Dépenses anormales** — écart-type calculé en "leave-one-out" (la
moyenne/écart-type de référence pour chaque transaction exclut cette
transaction elle-même, pour qu'une grosse anomalie ne gonfle pas sa propre
base de comparaison et ne se masque pas elle-même). Catégories groupées sur
une clé normalisée (accents/casse ignorés) pour que "Frais généraux" et
"Frais generaux" alimentent la même population statistique.

Le JSON de sortie inclut, pour chaque montant, un champ `_eur` (nombre brut,
pour les calculs) et un champ `_fmt` (chaîne déjà formatée, ex. `"59 710 €"`)
— le prompt Gemini a l'instruction explicite de n'utiliser que les champs
`_fmt` et de ne jamais reformater un `_eur` lui-même.

## Gestion des erreurs

Chaque nœud à risque (les 5 lectures Sheets, le nœud Code, Gemini, les 2
envois Telegram) a `onError: continueErrorOutput` + `retryOnFail` (3
tentatives, 5s d'intervalle), et leur sortie d'erreur converge vers **Alerte
erreur (Telegram)**. Ce nœud :
- identifie le nœud réellement en échec via `$prevNode.name` (fiable même
  avec plusieurs sources convergentes) ;
- a `executeOnce: true` pour n'envoyer qu'un seul message par exécution —
  limite connue : si plusieurs nœuds échouaient dans le même run (cas rare),
  seul le premier serait rapporté ;
- échappe les caractères spéciaux Markdown/HTML (`&`, `<`, `>`, `_`, `*`,
  `` ` ``, `[`) pour éviter l'erreur Telegram *"can't parse entities"* —
  observée en pratique quand le mode de parsing par défaut de Telegram
  (Markdown legacy, pas HTML) rencontre un caractère non échappé dans un
  contenu dynamique (ex. un JSON de diagnostic contenant des underscores).

## Limites connues

- **Fiabilité décroissante au-delà de l'horizon fiable** (~4-7 semaines,
  selon les délais de paiement réels) : au-delà, la prévision n'a plus de
  factures connues à projeter et redescend mécaniquement. Voir
  [`demo-data/ANOMALIES.md`](demo-data/ANOMALIES.md) pour le détail de ce
  choix (Option A validée en Phase 2 : pas d'extrapolation de CA futur).
- **Détection d'anomalies de dépense** : nécessite au moins 5 transactions
  dans une catégorie pour constituer une base statistique une catégorie
  trop peu utilisée ne sera jamais analysée.
- **Alerte erreur** : ne rapporte qu'un seul nœud en échec par exécution (voir
  ci-dessus).
- **Pas de nœud de secours si l'alerte Telegram elle-même échoue** : dans ce
  cas, l'exécution apparaît simplement en échec dans l'historique n8n.

## Tester le workflow

Cliquer sur **Execute workflow** (nœud "Déclencheur manuel (test)") dans n8n.
Le résultat de chaque nœud est visible dans l'éditeur ; en cas d'échec,
l'historique d'exécution (`Executions`) donne le détail complet, y compris
les données reçues par chaque nœud.

## Adapter à un client réel

Les 5 lectures Google Sheets sont le seul point à remplacer — tout ce qui
suit (Code, Gemini, Telegram) fonctionne sans changement, à condition que les
données arrivent avec des champs reconnaissables.

**Pennylane** — pas de nœud n8n natif : utiliser un nœud **HTTP Request**
vers l'API Pennylane (credential par clé API, header `Authorization: Bearer
...`). Pennylane expose des endpoints factures clients/fournisseurs et
transactions bancaires directement exploitables.

**Xero** — nœud natif `Xero` disponible dans n8n (credential OAuth2) :
- Transactions bancaires ← *Get Bank Transactions*
- Factures clients ← *Get Invoices* (type `ACCREC`)
- Factures fournisseurs ← *Get Invoices* (type `ACCPAY`)
- Solde de départ ← solde du compte bancaire à une date donnée (*Get Bank
  Transaction* avec filtre, ou endpoint *Reports: Balance Sheet*)
- Charges récurrentes ← *Get Repeating Invoices*, à mapper vers le format
  attendu (libellé/catégorie/montant/fréquence/prochaine échéance)

**QuickBooks Online** — nœud natif `QuickBooks Online` (credential OAuth2),
logique équivalente via *Invoice*, *Bill*, *Purchase*, et le solde de compte.

**Dans tous les cas**, insérer un petit nœud **Set** (ou une IIFE dans un
champ d'expression) entre la source et le nœud Code pour renommer les champs
API (souvent en anglais : `Total`, `DueDate`, `Contact.Name`...) vers les
noms attendus (`montant`, `date_echeance`, `client`...) — ou, plus simple,
laisser tel quel et vérifier que `getVal()` les retrouve (il tolère les
variantes d'accent/casse/espacement, pas les noms de champs dans une langue
différente). Les onglets "Charges récurrentes" et "Solde bancaire de départ"
n'ont pas toujours d'équivalent direct dans un ERP comptable ; un petit
Google Sheet géré à la main par le comptable reste souvent la solution la
plus simple pour ces deux-là.

## Fichiers du projet

- [`workflow/cfo-virtuel.json`](workflow/cfo-virtuel.json) — export du
  workflow, nettoyé de toute donnée personnelle (voir
  [Installation](#installation))
- [`demo-data/generate_demo_data.py`](demo-data/generate_demo_data.py) —
  générateur des données de démonstration (déterministe, seed fixe)
- [`demo-data/ANOMALIES.md`](demo-data/ANOMALIES.md) — détail des anomalies
  injectées dans le jeu de données et du choix méthodologique sur l'horizon
  de prévision
- [`demo-data/output/`](demo-data/output/) — CSV générés (source des onglets
  du Google Sheet)
