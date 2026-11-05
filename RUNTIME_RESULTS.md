# Bun contre Node : compatibilité complète et efficacité au runtime

## Lecture pratique des résultats

**Pour économiser la RAM sur le scénario Matter appairé, Node est le meilleur des deux ici** : 275.8 Mio au repos contre 315.8 Mio pour Bun, et 277.7 contre 312.0 Mio pendant les changements d'état. Le CPU et les latences Matter restent du même ordre dans cette charge contrôlée.

**Bun apporte un gain net sur l'API HTTP** : environ 31–37 % de requêtes supplémentaires par seconde, avec moins de CPU par requête. Il reste fonctionnellement compatible avec l'ensemble des 2 217 tests. Le choix dépend donc de la priorité : RAM du hub ou capacité de son API, pour les versions et charges mesurées ici.


## Résultat de compatibilité

**2 217 tests réussis sous Bun, zéro échec, zéro test ignoré.** Les tests, assertions, fixtures, configurations Vitest et délais restent identiques au dépôt d'origine.

Les cinq tests réseau optionnels ont été activés avec `HAMH_LOOPBACK=1`. Les deux tests de diagnostic du port 80 ont été exécutés dans un conteneur Linux isolé, où ce port pouvait être réservé. La répartition est : common 134, backend 1 993, frontend 88, paquet 2. Les suites Linux utilisent au plus quatre workers Vitest ; aucune assertion n'a été adaptée pour Bun.

Sur macOS, Bun réussit aussi 2 215 tests, et les deux tests de port 80 se désactivent via leur condition existante. Sous Node/macOS, un passage parallèle a rencontré deux erreurs de verrouillage/transaction matter.js, conservées dans les logs. Cela ne sert pas de preuve que Node serait globalement instable.

## Ce que mesure le benchmark

Les deux versions de production tournent dans des conteneurs Linux ARM64, chacun limité à **2 CPU et 2 Gio de RAM**, sur un Apple M4 Pro. Node 24.19.0 et Bun 1.4.2. Trois passages alternent leur ordre. Chaque passage repart avec un processus et un stockage neufs.

Les profils sont : zéro pont/zéro entité, puis un pont actif de 100 ou 500 endpoints Matter. Les entités simulées sont pour moitié des capteurs de température et pour moitié des interrupteurs. Un faux Home Assistant fournit les registres et les états, puis envoie **100 changements d'état par seconde**. Aucun appareil ou compte réel n'est utilisé.

Après un échauffement API de 2 s et 5 s de repos, chaque phase dure environ 10 s : repos initial, changements d'état seuls, puis requêtes API pendant que les changements continuent. Le retour au calme dure 5 s. Le client de charge fixe utilise Node, quatre threads et 16 connexions persistantes ; ses ressources sont exclues de celles du serveur. Chaque route reçoit exactement un quart du trafic, avec vérification automatique de cet équilibre à chaque essai. Chaque réponse est contrôlée : statut HTTP, nombre d'entités/endpoints et santé du pont. Un instantané des endpoints Matter confirme aussi le changement des valeurs des capteurs après les mesures. Le service doit s'arrêter proprement, sans OOM.

Les tableaux présentent les médianes des trois passages. La RAM est le RSS courant du processus applicatif lu dans le noyau Linux (`smaps_rollup`), comprenant moteur JavaScript et mémoire native. Ce n'est ni seulement le heap JavaScript, ni la taille de l'image Docker. Les pages partagées restent incluses dans le RSS ; les mesures PSS/privées et la mémoire cgroup sont également conservées dans le JSON.

## RAM au repos initial

| Entités | Node | Bun | Surcoût Bun |
|---|---:|---:|---:|
| 0 | 232.8 Mio | 284.1 Mio | +51.4 Mio (+22.1 %) |
| 100 | 314.1 Mio | 350.4 Mio | +36.3 Mio (+11.5 %) |
| 500 | 397.0 Mio | 411.1 Mio | +14.1 Mio (+3.5 %) |

## RAM pendant et après l'activité

| Entités | Node : mises à jour | Bun : mises à jour | Node : charge API | Bun : charge API | Node : retour au calme | Bun : retour au calme |
|---|---:|---:|---:|---:|---:|---:|
| 0 | — | — | 233.1 Mio | 289.9 Mio | 234.7 Mio | 286.3 Mio |
| 100 | 311.4 Mio | 326.2 Mio | 322.9 Mio | 385.7 Mio | 324.4 Mio | 359.3 Mio |
| 500 | 402.9 Mio | 398.3 Mio | 432.9 Mio | 476.5 Mio | 452.3 Mio | 449.8 Mio |

Ces valeurs changent avec le rythme du ramasse-miettes et de l'allocateur. Le repos initial suit une préparation courte ; le retour au calme suit la charge décrite ici. Aucun ramasse-miettes n'est forcé. Ce protocole ne prédit pas la mémoire après des jours d'utilisation ni l'absence de fuite mémoire.

## Débit et latence de l'API

| Entités | Node : requêtes/s | Bun : requêtes/s | Gain Bun | Node : latence p95 | Bun : latence p95 |
|---|---:|---:|---:|---:|---:|
| 0 | 35233 | 46777 | +32.8 % | 0.79 ms | 0.58 ms |
| 100 | 8895 | 11675 | +31.3 % | 3.11 ms | 2.60 ms |
| 500 | 3694 | 5047 | +36.6 % | 7.16 ms | 5.46 ms |

Le mélange de requêtes porte sur les entités Home Assistant, les statistiques, la santé détaillée des ponts et les métriques. Les profils non vides continuent à recevoir leurs changements d'état pendant cette charge.

## CPU et travail effectué

100 % représente un CPU logique ; la limite de deux CPU autorise jusqu'à 200 %. Le coût CPU par requête est utile pour comparer l'efficacité à débit différent : une valeur plus basse signifie moins de CPU cumulé par requête traitée. Les mises à jour de fond restent incluses pour les profils non vides.

| Entités | Node : CPU pendant API | Bun : CPU pendant API | Node : CPU par requête | Bun : CPU par requête |
|---|---:|---:|---:|---:|
| 0 | 96.8 % | 98.2 % | 0.0289 ms | 0.0222 ms |
| 100 | 112.3 % | 105.5 % | 0.1347 ms | 0.0952 ms |
| 500 | 107.0 % | 105.7 % | 0.3042 ms | 0.2206 ms |

| Entités | Node : CPU pour les seuls changements d'état | Bun : CPU pour les seuls changements d'état |
|---|---:|---:|
| 100 | 18.1 % | 16.7 % |
| 500 | 20.7 % | 16.5 % |

Le CPU vient de `cpu.stat` du conteneur. Le petit échantillonneur `docker exec`, lancé approximativement une fois par seconde, est inclus dans ces compteurs. Les faibles différences de CPU au repos sont donc à lire avec prudence. Les ressources du faux Home Assistant et du client de charge sont séparées. Le JSON conserve également le CPU du client afin de vérifier qu'il ne plafonne pas artificiellement le serveur.

## Démarrage et création du pont

| Entités | Node : API prête | Bun : API prête | Node : création du pont | Bun : création du pont |
|---|---:|---:|---:|---:|
| 0 | 6.16 s | 6.40 s | 0.00 s | 0.00 s |
| 100 | 6.28 s | 6.38 s | 0.65 s | 6.52 s |
| 500 | 6.28 s | 6.26 s | 2.64 s | 46.09 s |

Le temps « API prête » comprend l'attente de cinq secondes codée dans le client Home Assistant. La création du pont et de ses endpoints est mesurée séparément ; ces nombres ne sont pas des microbenchmarks du seul chargement du moteur JavaScript.

## Contrôles et limites

Les 18 essais retenus réussissent : aucune erreur HTTP, aucun endpoint manquant, aucun OOM et un arrêt normal pour chaque essai. Les séries brutes permettent de contrôler les variations plutôt que de s'en tenir à la médiane.

Il s'agit des deux **versions déployées**, avec leurs modes de packaging et leurs arbres de dépendances. La version d'origine bundle une partie de matter.js et installe via npm ; la migration préserve les bibliothèques externes et installe via Bun. La comparaison n'isole donc pas uniquement le moteur à fichiers installés strictement identiques.

Le premier scénario, consacré à l'API HTTP, utilise des endpoints Matter actifs sans contrôleur appairé. Le complément Matter appairé est décrit plus bas. Il mesure les changements Home Assistant → endpoints et le débit HTTP. Il ne mesure pas le débit des commandes Matter chiffrées, les notifications vers des contrôleurs appairés, le streaming vidéo, le transcodage, ni les ressources sur Raspberry Pi. Les tests fonctionnels couvrent des contrôleurs simulés et les échanges caméra, mais leurs performances ne sont pas déduites des requêtes HTTP/s.

Une première série de mise au point a été écartée : son choix de route dépendait de l'ordre de fin des réponses et déséquilibrait le trafic. Toute la série retenue a été recommencée avec le générateur cyclique corrigé et son assertion d'équilibre. Les chiffres provisoires de débit ne sont pas utilisés ici.

Docker Desktop a dû être redémarré, avec autorisation, avant la série retenue. Les quatre services myownnotion préexistants ont été rétablis et vérifiés healthy. Les tests et les essais de mise au point ont été terminés avant les mesures retenues ; les autres services de bureau sont restés présents. Il s'agit d'un comparatif local reproductible, pas d'une machine physique exclusivement dédiée au benchmark.

## Reproduction et pièces jointes

Les commandes de construction et de reproduction sont dans `RUNTIME_BENCHMARK.md` sur la branche `migrate-to-bun`. Le programme est `scripts/runtime-benchmark/run.py`, avec le faux Home Assistant et le générateur HTTP dans le même dossier. Le fichier `runtime-results.json` contient les images exactes, les limites, les échantillons de RAM/CPU, les latences et les comptes de réponses. `runtime-summary.json` contient les médianes. Les rapports JSON de compatibilité listent les statuts individuels des tests.

## Complément : contrôleur Matter logiciel réellement appairé

Un second scénario utilise un contrôleur matter.js 0.18.0 identique pour les deux serveurs, exécuté séparément sous Bun 1.4.2. Le pont expose **100 entités**. Le contrôleur est appairé, ce que confirme la présence d'un fabric dans les métriques serveur. Il s'abonne aux 50 températures et aux 50 états On/Off, reçoit leurs changements chiffrés, puis effectue des lectures de **100 attributs par transaction**. Les filtres de versions connues sont désactivés pour demander une réponse complète à chaque lecture.

L'abonnement autorise un intervalle minimal de 0 s et maximal de 10 s. Les phases sont : repos appairé, 100 changements d'état/s, puis lectures séquentielles pendant que ces changements continuent, chacune mesurée sur 10 s. Un retour au calme de 5 s suit. Trois passages alternent Node/Bun, avec nouveaux processus et stockages. Les ressources du contrôleur et du faux Home Assistant ne sont pas incluses dans celles du serveur.

Ce scénario ne comprend pas l'échauffement HTTP intensif du premier benchmark. Ses valeurs absolues de RAM ne doivent donc pas être comparées directement à celles d'un processus qui vient de traiter des dizaines de milliers de requêtes API.

| Mesure, 100 entités appairées | Node | Bun |
|---|---:|---:|
| RAM au repos | 275.8 Mio | 315.8 Mio |
| RAM pendant les changements d’état | 277.7 Mio | 312.0 Mio |
| RAM pendant lectures et changements d’état | 278.5 Mio | 321.6 Mio |
| RAM après retour au calme | 295.1 Mio | 326.5 Mio |
| CPU pendant les changements d’état | 22.7 % | 21.2 % |
| CPU pendant lectures et changements d’état | 20.7 % | 21.4 % |
| Lectures de 100 attributs par seconde | 9.66 | 9.60 |
| Latence médiane d’une lecture de 100 attributs | 103.54 ms | 105.32 ms |
| Latence p95 d’une lecture de 100 attributs | 115.36 ms | 117.62 ms |
| Appairage | 0.248 s | 0.247 s |

Les six essais appairés réussissent : fabric présent, 100 valeurs initiales reçues, changements d'état reçus dans les abonnements, aucune erreur de lecture, aucun OOM, aucun message d'erreur runtime dans les logs applicatifs et arrêt normal. Les compteurs réseau et le CPU du contrôleur sont conservés dans les résultats bruts.

Les lectures sont volontairement séquentielles, avec un seul contrôleur : elles mesurent une latence de bout en bout pour cette transaction de 100 attributs, pas le débit maximal théorique du serveur Matter. Leur cadence est très proche entre les deux versions dans ce scénario. Le gain HTTP ne se traduit donc pas ici par une accélération comparable des lectures Matter. Le contrôleur reste logiciel ; l'interopérabilité et les latences sur des contrôleurs physiques, le Wi-Fi, Thread, la vidéo et le fonctionnement sur plusieurs jours ne sont pas déduits de ce test.

Pour reproduire après construction de l'image de compatibilité et des deux images applicatives :

```bash
docker build -f scripts/runtime-benchmark/Controller.Dockerfile \
  -t hamh-runtime-benchmark:controller scripts/runtime-benchmark
python3 scripts/runtime-benchmark/paired-run.py \
  --output benchmark-results/paired --rounds 3 --seconds 10 --entities 100
```

Le fichier `paired-runtime-results.json` contient les essais et échantillons individuels ; `paired-runtime-summary.json` contient les médianes.
