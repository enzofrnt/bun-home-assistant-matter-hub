# Migration Bun : résultats et comparaison

Les mesures ci-dessous concernent les outils de développement. La vérification complète avec zéro test ignoré est dans [COMPATIBILITY_RESULTS.md](COMPATIBILITY_RESULTS.md), et les mesures du service en fonctionnement dans [RUNTIME_RESULTS.md](RUNTIME_RESULTS.md).

Mesures effectuées le **5 novembre 2026**, sur un **Apple M4 Pro, 14 processeurs logiques, 48 Gio de RAM, macOS 27.2 arm64**. Node **24.19.0**, pnpm **10.33.0**, Bun **1.4.2+43848b5a7**.

La migration exécute les tests existants avec Vitest sous Bun : **2 210 tests réussis, 7 ignorés**, lors des trois passages de comparaison. Les tests, assertions, fixtures, fichiers de préparation, configurations Vitest et délais n'ont pas été modifiés. Le script vérifie leurs empreintes SHA-256.

## Temps écoulé et CPU

Médianes de trois passages. Le temps CPU additionne les secondes utilisateur et système des processus enfants, et peut dépasser le temps écoulé lorsqu'ils travaillent en parallèle.

| Charge | Node/pnpm : durée | Bun : durée | Écart de durée | Node : CPU | Bun : CPU | Écart CPU |
|---|---:|---:|---:|---:|---:|---:|
| Installation depuis les caches locaux | 12.25 s | 2.05 s | -83.3 % | 28.90 s | 1.93 s | -93.3 % |
| Build et création du paquet | 8.09 s | 6.72 s | -16.9 % | 19.38 s | 27.30 s | +40.9 % |
| Toutes les suites, exécutées successivement | 47.85 s | 32.68 s | -31.7 % | 339.79 s | 357.90 s | +5.3 % |

Bun installe environ **6 fois plus vite** et termine les tests environ **32 % plus tôt**. Il utilise cependant davantage de CPU cumulé pour les tests et le build. Un temps écoulé plus court ne signifie donc pas automatiquement moins de calcul ou moins d'énergie consommée.

## Mémoire

Le RSS cumulé est la somme de la mémoire résidente des processus descendants, échantillonnée toutes les ~100 ms. Les pages partagées peuvent être comptées plusieurs fois, et les pics très brefs peuvent échapper à l'échantillonnage. Cette mesure n'est pas la quantité de RAM physique réellement consommée. Le maximum par processus vient séparément de macOS `time -l`.

| Charge | Node : pic RSS cumulé | Bun : pic RSS cumulé | Écart | Node : max. par processus | Bun : max. par processus |
|---|---:|---:|---:|---:|---:|
| Installation depuis les caches locaux | 833 Mio | 66 Mio | -92.1 % | 843 Mio | 49 Mio |
| Build et création du paquet | 1964 Mio | 2947 Mio | +50.0 % | 1303 Mio | 1922 Mio |
| Toutes les suites, exécutées successivement | 4467 Mio | 3709 Mio | -17.0 % | 369 Mio | 351 Mio |

Le build Bun est plus rapide mais son pic RSS cumulé augmente d'environ **50 %**. Pour les tests, le pic RSS cumulé diminue d'environ **17 %**. Les très courtes commandes, notamment les tests du paquet, ont moins de points d'échantillonnage mémoire.

## Résultats des tests

| Suite | Réussis sous Bun | Ignorés |
|---|---:|---:|
| Common | 134 | 0 |
| Backend | 1 986 | 7 |
| Frontend | 88 | 0 |
| Paquet assemblé | 2 | 0 |
| **Total** | **2 210** | **7** |

Cela représente 249 fichiers réussis et 2 fichiers ignorés. Les trois passages Bun réussissent. Sous Node, le premier passage de comparaison échoue sur `vesync-bringup.test.ts`, cas `sends an OnOff off command on a basket as endCook`, avec `Cannot lock ...onOff.state synchronously`. Les deuxième et troisième passages réussissent intégralement. Une exécution Node préliminaire rencontrait déjà cet échec ; sa relance isolée réussissait. Aucune tentative de correction ou de masquage du test n'a été faite.

Les médianes de durée incluent tous les passages, y compris cet échec Node. Le test a été exécuté dans les deux versions ; l'erreur reste une limite à une comparaison parfaitement équivalente.

## Variabilité des durées

| Charge | Node : minimum–maximum | Bun : minimum–maximum |
|---|---:|---:|
| Installation depuis les caches locaux | 11.76–12.42 s | 1.92–2.21 s |
| Build et création du paquet | 7.94–8.24 s | 6.56–6.87 s |
| Toutes les suites, exécutées successivement | 45.42–48.62 s | 32.61–35.20 s |

## Méthode et reproductibilité

La référence est le commit amont `2a32ff3890a77c7d2df329768331a97c6af8dcd1`. Elle est conservée dans un worktree séparé, sans modification de ses sources. Le candidat utilise la migration Bun et ses propres verrous.

Trois passages alternent l'ordre Node/Bun. Avant chaque installation, les `node_modules` de la racine et des quatre workspaces applicatifs sont supprimés. Les caches de chaque gestionnaire sont déjà alimentés, puis l'installation utilise `--offline --frozen-lockfile` : il s'agit d'une réinstallation depuis un cache chaud, pas d'un téléchargement depuis un réseau vierge.

Le build inclut TypeScript, Vite, le backend et le paquet. Les quatre suites Vitest sont ensuite exécutées successivement, avec les mêmes versions, arguments et configurations. Le parallélisme interne de Vitest reste à sa valeur par défaut. Le script continue avec les autres suites si l'une échoue. Les temps des suites sont additionnés ; leur mémoire totale prend le maximum observé, puisque les suites sont successives. La documentation est validée séparément et n'entre pas dans les temps de build du tableau.

Le benchmark compare la migration complète : gestionnaire, arborescence installée et runtime des outils. Le bundling a été adapté pour une résolution isolée et pour préserver l'initialisation de matter.js. Le verrou Bun conserve les versions résolues de pnpm, sauf quatre doublons de contextes de pairs MUI 9 non retenus par Bun. Il ne s'agit donc pas d'une mesure isolant uniquement le moteur JavaScript à arbre de modules strictement identique.

Pour reproduire : suivre `BUN_MIGRATION.md`, puis lancer `scripts/benchmark.py`. Les fichiers JSON conservent les commandes, codes de sortie, temps, empreintes des tests et caractéristiques de la machine. Les logs permettent d'auditer les erreurs et les comptes de tests.

## Vérifications complémentaires

- `bun run test` : les quatre suites passent, sans modification des tests.
- `bun run lint` : réussite ; trois avertissements préexistants restent dans `identify-447-bringup.test.ts`, conservé intact.
- Application et documentation : builds réussis ; installation avec verrous figés réussie.
- YAML des workflows : lecture réussie ; syntaxe du script shell de l'add-on : valide.
- Images Docker autonome et add-on : construction locale arm64 et lancement de la CLI réussis, sans Node installé dans les images par les Dockerfiles du projet.
- Application native : connexion à un faux serveur Home Assistant exclusivement local, API de santé `healthy`, interface HTTP 200 et arrêt propre par SIGTERM avec code 0. Ce scénario utilise zéro pont et aucun appareil réel.
- Installation d'un plugin `.tgz` local par le vrai installateur Bun : réussite, version vérifiée, puis désinstallation réussie.
- Script de version : exécution avec `0.0.0`, puis installation figée réussie ; aucun tag ni publication.

## Limites de validation

Ces résultats décrivent cette machine et ces charges de développement. Ils ne mesurent pas les performances d'un pont actif, l'appairage Matter avec un contrôleur réel, la consommation au repos, l'énergie, une grande installation Home Assistant, ni les ressources sur Raspberry Pi. Les images amd64 et l'exécution dans un vrai Home Assistant Supervisor ne sont pas validées ici.

Bun ne prend pas en charge ARM 32 bits : la cible Docker arm/v7 a été retirée. Les anciens réglages V8 `NODE_OPTIONS` et `heap_size_mb` ne pilotent pas le heap JavaScriptCore ; ce changement est documenté. Les commandes Bun de publication omettent la provenance npm, que Bun ne sait pas produire. Les workflows de publication hérités restent désactivés sur le fork tant que leurs destinations ne sont pas adaptées. Aucune publication de paquet ou d'image n'a été effectuée.

Références techniques : [compatibilité Node de Bun](https://bun.sh/docs/runtime/nodejs-compat), [architectures et images Bun](https://bun.com/docs/installation), [publication et provenance](https://bun.sh/docs/pm/cli/publish).
