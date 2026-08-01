# Analyse & conception — Bot de copie de signaux memecoin (Telegram → Solana)

> **Statut : document de conception à valider AVANT toute ligne de code du bot.**
> Objectif de ce document : décider ensemble du type de bot, de l'architecture, de la
> stratégie d'entrée/sortie v1 et des choix techniques.

---

## 1. Objectif et périmètre

- Lire automatiquement les « calls » publiés dans un canal Telegram auquel **tu es abonné**
  (tu n'en es pas admin).
- Extraire les paramètres du trade : adresse du contrat, market cap d'entrée, niveaux de
  take-profit, stop-loss.
- Acheter le token sur **Solana** automatiquement, puis gérer la position (sorties
  échelonnées, stop-loss, protection anti-rug).
- v1 : pas de stratégie de sortie « parfaite », mais une stratégie qui **maximise le
  winrate** (sécuriser tôt, couper vite).

Hors périmètre v1 : multi-chaînes, interface web, plusieurs canaux sources, machine learning.

---

## 2. Quel type de bot ? (la décision structurante)

### 2.1 Lecture du canal : compte utilisateur obligatoire (MTProto)

Un « bot Telegram » classique (Bot API, via BotFather) **ne peut pas lire un canal** sauf
s'il y est ajouté comme administrateur — impossible ici puisque le canal ne t'appartient pas.

➡️ **La seule option : se connecter avec TON compte Telegram** via le protocole MTProto
(bibliothèque **Telethon** en Python, ou GramJS en Node). Le bot agit alors comme un
« deuxième téléphone » connecté à ton compte, en lecture seule sur le canal.

Conséquences à assumer :
- Il faut créer une paire `api_id` / `api_hash` sur [my.telegram.org](https://my.telegram.org) (2 minutes).
- La session générée donne un **accès complet à ton compte Telegram** → elle doit être
  stockée de façon sécurisée (voir §11).
- L'automatisation d'un compte utilisateur est tolérée par Telegram tant qu'on ne spamme
  pas ; un bot qui **lit** passivement un canal est très bas risque.

### 2.2 Exécution : bot auto-exécutant avec gestion de position active

Deux familles possibles :

| Option | Description | Verdict |
|---|---|---|
| A. Relais vers un bot de sniping existant (Maestro, Trojan, BonkBot…) | Le bot forwarde le contrat à un sniper bot qui achète | ❌ Rejetée |
| B. Bot autonome : achat/vente on-chain en direct | Le bot signe et envoie lui-même les transactions | ✅ **Recommandée** |

Pourquoi B : l'option A ne permet pas d'implémenter **notre** logique de sortie (TP
échelonnés, break-even, trailing, rug-guard), ajoute des frais (~1 % par bot tiers), et
te rend dépendant d'un tiers qui détient tes fonds. L'option B garde le contrôle total :
wallet dédié, logique de sortie sur mesure, aucun intermédiaire.

### 2.3 Point critique : le stop-loss n'existe pas on-chain

Sur Solana/DEX, il n'y a **aucun ordre stop-loss natif**. C'est le bot qui surveille le
prix en continu et déclenche la vente. Donc :

➡️ **Le bot doit tourner 24/7 sur un VPS** (5–10 $/mois). S'il est éteint, les positions
ouvertes ne sont plus protégées.

---

## 3. Architecture (modules)

```
Telegram (ton compte, MTProto)
        │  nouveau message du canal
        ▼
┌─────────────┐    ┌────────────┐    ┌─────────────┐    ┌──────────────┐
│  Listener    │──▶│  Parser     │──▶│  Filtres     │──▶│  Executor     │
│  (Telethon)  │   │  (regex)    │   │  d'entrée    │   │  (achat swap) │
└─────────────┘    └────────────┘    └─────────────┘    └──────┬───────┘
                                                               │ position ouverte
                        ┌──────────────────────────────────────▼───────┐
                        │  Position Manager (boucle prix toutes les 2-5 s)│
                        │  TP échelonnés · SL · break-even · trailing ·   │
                        │  time-stop · rug-guard                          │
                        └──────┬─────────────────────────┬───────────────┘
                               ▼                         ▼
                        ┌────────────┐            ┌──────────────┐
                        │  Storage    │            │  Notifier     │
                        │  (SQLite)   │            │  (bot Telegram│
                        │  trades/logs│            │   privé → toi)│
                        └────────────┘            └──────────────┘
             + Risk Manager transversal (sizing, limites, kill-switch)
```

| Module | Rôle |
|---|---|
| **Listener** | Connexion Telethon, écoute le canal ciblé, pousse chaque nouveau message au parser |
| **Parser** | Extrait ticker, contrat, mcap d'entrée, TP1-4, SL depuis le format du call |
| **Filtres d'entrée** | Décide si on prend le trade (voir §8) |
| **Executor** | Achat via l'API Jupiter (et PumpPortal si le token est encore sur pump.fun), slippage et priority fees configurés |
| **Position Manager** | Boucle de surveillance du prix, exécute la stratégie de sortie (§7) |
| **Risk Manager** | Taille de position, nombre max de positions, perte max journalière, kill-switch |
| **Storage** | SQLite : tous les calls (pris ou non), toutes les transactions, PnL — indispensable pour calibrer la stratégie |
| **Notifier** | Un petit bot Telegram (Bot API, celui-là oui) qui t'envoie en privé : trade ouvert, TP touché, SL, erreurs |

---

## 4. Stack technique recommandée

| Composant | Choix | Pourquoi |
|---|---|---|
| Langage | **Python 3.11+** | Telethon est la lib MTProto la plus mature ; parsing/regex confortable ; écosystème Solana suffisant via `solders` |
| Telegram (lecture) | **Telethon** | Standard de fait, sessions stables |
| Swap | **API Jupiter** (agrégateur n°1 Solana) | Couvre Raydium/Meteora/Orca + tokens pump.fun migrés ; simple API HTTP : quote → transaction → on signe → on envoie |
| Tokens pré-migration pump.fun | **PumpPortal API** (fallback) | Les calls du canal (adresses en `...pump`) sont souvent encore sur la bonding curve pump.fun, pas encore routables par Jupiter |
| Signature / envoi tx | `solders` + RPC | Signature locale de la transaction retournée par Jupiter |
| RPC Solana | **Helius (free tier)** au départ | RPC public = trop lent/instable pour du trading |
| Prix en temps réel | **API DexScreener** (gratuite) + Jupiter Price API | Polling 2–5 s suffisant pour la v1 ; WebSocket plus tard si besoin |
| Base de données | SQLite | Zéro infra, suffisant |
| Notifications | Bot Telegram privé (Bot API) | Tu vois tout en direct sur ton téléphone |
| Hébergement | VPS Linux (Contabo/Hetzner ~5 €/mois) + `systemd` | 24/7 obligatoire (§2.3) |

*Alternative écartée : TypeScript (GramJS + @solana/web3.js). Viable, mais GramJS est
moins robuste que Telethon et le reste passe par des API HTTP de toute façon.*

---

## 5. Parsing du format de call

Exemple analysé :

```
🔹 #Ember/SOL 🔹
Holders: Top10: 40.13% | Total: 79
Insiders: 0%
Snipers: 19.38%
Dev Migrations: 20/1261 (1.59%)
❌ DEX NOT PAID
Entry - MCap: $29.92K
Take-Profit:
🥉 0.000040797 (70% of profit)
🥈 0.000047996 (100% of profit)
🥇 0.000095992 (300% of profit)
🚀 0.000143988 (500% of profit)
Stop loss -30%
Contract address: ESmGDBtEicUicLqrXzjLye1aUXB3QRQYQw9ho4hBpump
```

Champs extraits :

| Champ | Exemple | Usage |
|---|---|---|
| Ticker | `Ember/SOL` | affichage/logs |
| Top10 / Total holders | `40.13 %` / `79` | filtre d'entrée |
| Insiders | `0 %` | filtre d'entrée |
| Snipers | `19.38 %` | filtre d'entrée |
| DEX paid | non (`❌`) | filtre d'entrée |
| **Entry MCap** | `$29.92K` | référence anti-chase + calcul des niveaux |
| TP1–TP4 (prix) | `+70 % / +100 % / +300 % / +500 %` | niveaux de sortie |
| Stop loss | `-30 %` | niveau de sortie |
| **Contract address** | `ESmG…pump` (base58, 32-44 car.) | la seule donnée vraiment indispensable |

Principes du parser :
- Regex tolérantes (émojis/espaces variables) ; **l'adresse de contrat est validée
  base58** — c'est le champ bloquant.
- Les niveaux de TP/SL sont recalculés **en % par rapport à NOTRE prix d'entrée réel**
  (pas les prix absolus du call, car on entrera toujours un peu plus haut/plus bas que lui).
- Si le format change et que le parse échoue → le message est stocké « en quarantaine »
  + notification, jamais de trade sur un parse douteux.
- Les messages du canal qui ne sont pas des calls (updates, pubs) sont ignorés
  silencieusement.

---

## 6. Flux d'un trade

1. Message reçu → parsé → validé par les filtres (§8).
2. **Anti-chase** : on récupère le mcap actuel (DexScreener). S'il a déjà fait plus de
   +X % (défaut : +50 %) depuis le mcap du call → on n'entre pas (on est en retard, le
   ratio risque/gain est détruit).
3. Achat : montant fixe en SOL (§9), slippage max ~15–20 % (les memecoins bougent vite),
   priority fee dynamique. Échec de tx → 2 retries puis abandon + notification.
4. Le prix d'entrée réel exécuté devient la référence des niveaux TP/SL.
5. Position Manager : boucle prix toutes les 2–5 s jusqu'à fermeture complète.
6. Chaque étape est écrite en base + notifiée sur ton Telegram privé.

---

## 7. Stratégie de sortie v1 — « maximiser le winrate »

Philosophie : sur les memecoins, la plupart des calls font un petit pump puis retombent
(souvent à zéro). Maximiser le winrate = **sécuriser tôt et rendre le trade ingagnable à
perdre le plus vite possible**, quitte à laisser filer les rares x10.

Règles (tous les seuils seront configurables) :

| Règle | Détail |
|---|---|
| **TP1 (+70 %)** | Vente de **65 %** de la position → la mise initiale est récupérée + profit sécurisé |
| **Break-even** | Dès TP1 touché, le SL des 35 % restants remonte au prix d'entrée → le trade ne peut plus être perdant |
| **Trailing stop** | Sur le reste : stop suiveur à **-25 % depuis le plus haut** atteint, pour capter les gros runs sans les plafonner |
| **TP4 (+500 %)** | Plafond dur : on solde tout ce qui reste |
| **Stop-loss dur** | **-30 %** par rapport à notre entrée (aligné sur le call) |
| **Time-stop** | Si TP1 non atteint en **30 min** et position en négatif → sortie. Un call qui ne part pas vite ne part généralement jamais |
| **Rug-guard** | Si la liquidité du pool chute brutalement (> 40 % en une boucle) ou si le prix décroche de > 50 % d'un coup → **vente d'urgence immédiate**, slippage élevé accepté |

Espérance : avec TP1 à +70 % sur 65 % de la position + break-even, un trade est gagnant
dès que le token fait +70 % une fois — ce qui est le cas de la majorité des calls qui
« partent », même ceux qui finissent à zéro ensuite.

⚠️ Ces seuils (65 %, 30 min, -25 %…) sont des points de départ raisonnés, pas des
vérités : la **phase de paper trading (§12)** servira à les calibrer sur les données
réelles du canal.

---

## 8. Filtres d'entrée (proposition initiale)

Tous configurables dans un fichier de config ; valeurs de départ :

| Filtre | Seuil proposé | Raison |
|---|---|---|
| Top10 holders | ≤ 45 % | concentration = risque de dump coordonné |
| Insiders | ≤ 5 % | au-delà, distribution truquée |
| Snipers | ≤ 30 % | les snipers vendent sur les premiers acheteurs (nous) |
| Liquidité du pool | ≥ 10 K$ | sinon slippage destructeur à l'achat ET à la vente |
| Anti-chase | mcap actuel ≤ 1,5 × mcap du call | ne pas acheter le sommet |
| DEX paid | **à discuter** (l'exemple est « NOT PAID ») | si on filtre dessus, on saute peut-être la majorité des calls du canal |

Un call rejeté est quand même **enregistré en base avec sa raison de rejet** et suivi en
paper trading → on saura si nos filtres améliorent ou dégradent le winrate réel.

---

## 9. Gestion du risque

- **Wallet dédié au bot**, alimenté uniquement du capital de trading. Jamais ton wallet principal.
- **Taille fixe par trade** (ex. 0,1–0,25 SOL au début) — pas de martingale, pas de % composé en v1.
- **Max 3 positions simultanées** (défaut).
- **Perte max journalière** (ex. -20 % du capital du bot) → le bot s'arrête d'ouvrir des
  trades jusqu'au lendemain et te notifie.
- **Kill-switch** : une commande (`/stop`) sur le bot de notification ferme tout et coupe les entrées.

---

## 10. Risques et réalités (à lire honnêtement)

1. **La qualité du canal est l'inconnue n°1.** Beaucoup de canaux de calls memecoin ont un
   winrate réel désastreux, certains achètent avant de publier et vendent sur leurs abonnés.
   Le bot ne peut pas rendre profitable un canal qui ne l'est pas — d'où le paper trading
   d'abord, qui donnera le winrate **mesuré** du canal.
2. **Latence** : entre la publication du call et notre achat (quelques secondes), le prix
   a souvent déjà bougé — l'anti-chase limite les dégâts mais réduit le nombre de trades pris.
3. **Slippage et liquidité** : sur un mcap de 30 K$, même 0,2 SOL fait bouger le prix ;
   la sortie d'urgence en plein crash peut s'exécuter bien sous le niveau du SL théorique (-30 % peut devenir -45 %).
4. **Rugs / honeypots** : certains tokens sont invendables ou voient leur LP retirée ;
   le rug-guard limite, mais n'annule pas, ce risque. Des pertes totales ponctuelles sur
   un trade font partie du jeu.
5. **Disponibilité** : bot éteint = positions non protégées (§2.3).
6. Ne mettre dans le wallet du bot **que ce que tu acceptes de perdre en totalité**.

---

## 11. Sécurité

- Secrets (`api_id`/`api_hash` Telegram, fichier de session Telethon, clé privée du
  wallet, clé RPC) dans un `.env` **jamais commité** (`.gitignore` dès le premier commit).
- Le fichier de session Telethon = accès total à ton compte Telegram → droits `600`, VPS
  avec clé SSH uniquement, pas de mot de passe.
- Dépôt GitHub **privé**.
- La clé privée du wallet ne quitte jamais la machine : Jupiter renvoie une transaction,
  on la signe **localement**.

---

## 12. Roadmap proposée

| Phase | Contenu | Durée indicative | Sortie |
|---|---|---|---|
| **0** | Validation de ce document (choix ci-dessous) | maintenant | GO/NO-GO |
| **1** | Listener + Parser + Storage + **paper trading** : le bot lit les calls et simule les trades (entrée, TP, SL) sans argent réel | dev : 2–3 j, puis **7–14 j de collecte** | Winrate réel du canal, calibrage des seuils |
| **2** | Executor réel + Position Manager, petit montant (0,05–0,1 SOL/trade) | 3–4 j | Bot live en taille réduite |
| **3** | Tuning des sorties/filtres à partir des stats, montée en taille progressive | continu | v1 stable |

La phase 1 n'est pas une perte de temps : le module de simulation réutilise exactement le
même parser, les mêmes filtres et la même logique de sortie que le bot réel — seule
l'exécution est simulée.

---

## 13. Points à valider avant d'écrire le code

1. **Type de bot** : bot autonome auto-exécutant (option B, §2.2) avec ton compte
   Telegram en lecture via Telethon — OK ?
2. **Stack** : Python + Telethon + Jupiter/PumpPortal + Helius + SQLite + VPS — OK ?
3. **Paper trading d'abord** (phase 1, ~1–2 semaines de collecte avant le premier trade
   réel) — OK, ou tu veux du réel dès le départ en micro-taille ?
4. **Capital** : combien de SOL dans le wallet du bot, et quelle taille par trade ?
5. **Filtre « DEX paid »** : on trade quand même les calls « ❌ DEX NOT PAID » (comme
   l'exemple) ou on les saute ?
6. **Stratégie de sortie v1** (§7 : 65 % vendus à +70 %, break-even, trailing -25 %,
   time-stop 30 min, SL -30 %) — OK comme point de départ ?
7. **VPS** : tu en as déjà un, ou on prévoit l'installation (Hetzner/Contabo ~5 €/mois) ?
