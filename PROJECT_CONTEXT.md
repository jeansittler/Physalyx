# PHYSALYX — CONTEXTE DE TRAVAIL

<!-- PHYSALIX_CODEX_BUDGET_START -->

## Politique prioritaire d'économie de crédits Codex

La politique détaillée et exécutoire se trouve dans `AGENTS.md`, section « Règles prioritaires — Budget Codex et maîtrise des tests ». **Elle prévaut sur toute mention historique de « suite complète au checkpoint » dans le présent contexte.**

- **Sol Minimal par défaut** ; Sol Moyen si la complexité le justifie ; Sol Élevé seulement sur accord.
- **Tests ciblés uniquement par défaut.** Une suite complète nécessite **un feu vert distinct**, obtenu après annonce de son coût/temps estimé ; une demande générale d'audit ne suffit pas.
- **Timeout effectif : 3 minutes par commande ciblée ; 12 minutes maximum pour une suite complète explicitement autorisée.** Arrêt et diagnostic si 5 minutes sans progression, même avec CPU actif ; aucune relance globale automatique.
- **Budget de tâche : environ 15 minutes ou 12 appels d'outils significatifs**, puis bilan et demande d'accord avant poursuite.
- Pas de surveillance verbale répétitive, d'audit général non requis, de relecture intégrale répétée des consignes ou de travaux « au passage ».
- Après un test interrompu : rapporter « suite complète non validée », pas « tests complets OK ».
- Aucune modification non sollicitée ; aucun build, commit, push, tag ou publication sans autorisation explicite propre à l'étape.

Cette politique est une **règle permanente du projet**. Elle ne doit pas être écartée par une formulation trop large d'un prompt ponctuel.

<!-- PHYSALIX_CODEX_BUDGET_END -->

> **Source de référence du projet**
>
> Ce fichier sert de contexte initial pour tout nouveau chat ChatGPT/Codex consacré à Physalyx.
> Avant de proposer une modification, un prompt Codex, une refonte UI, une release ou un test, respecter les conventions, décisions d’architecture et méthodes de travail décrites ici.
>
> Ne pas demander à l’utilisateur de répéter une information déjà présente dans ce fichier.
>
> Ce fichier doit rester **compact, actuel et maintenable** : remplacer les informations devenues obsolètes au lieu d’empiler un historique exhaustif.

---

## 1. Projet

**Nom public :** Physalyx
**Ancien nom public :** Physalix
**Type :** logiciel pédagogique de physique / traitement et acquisition de données
**Dépôt :** `C:\Physalix`
**Dépôt GitHub officiel :** `jeansittler/Physalyx`
**Domaine officiel prévu :** `physalyx.fr` — site non encore déployé
**Licence :** GPL-3.0

Physalyx est une application desktop Python/PySide6 destinée notamment à l’enseignement de la physique-chimie.

Fonctionnalités principales existantes :
- Données / tableaux de mesures ;
- Graphique ;
- Modélisation ;
- Pointage vidéo ;
- Calculs ;
- Statistiques ;
- Numérisation de graphiques ;
- Analyse d'images ;
- Acquisition Arduino ;
- Spectrophotométrie Arduino.

---

## 2. État actuel

### Version publique

**Physalyx 1.9.0**

Commit de release :

`41a8e642adda5e99be3c34ee04713b418d0cdf4b`

Tag :

`v1.9.0`

Branche stable :

`main`

Release GitHub :

`https://github.com/jeansittler/Physalyx/releases/tag/v1.9.0`

Le tag annoté `v1.9.0` pointe exactement sur le commit de release ci-dessus.
Physalyx 1.9.0 est la release stable et Latest sur GitHub. Le README public a été
modernisé après la publication par le commit
`7f24f47e68ba3dfbacd2e84c1e27795f6fee4f12`, actuellement sur `main`.
Le dépôt GitHub existant a ensuite été renommé de `jeansittler/Physalix` vers
`jeansittler/Physalyx` ; les anciennes URL GitHub redirigent vers le dépôt renommé.

Assets publiés :
- `Physalyx-Setup-1.9.0.exe`
- `Physalyx-Setup-1.9.0.exe.sha256`
- `update.json`

Taille de l'installateur 1.9.0 : `85 511 056 octets`.

SHA-256 de l’installateur 1.9.0 :

`11be3c56a6be9a6c5185bfe3287312c12e1036e0038fea8e6428207866cb6c79`

`update.json` public :
- version `1.9.0`
- `mandatory = false`
- URL de l’installateur cohérente avec la release GitHub
- SHA identique à celui de l’installateur
- changelog cumulatif

Validation de release : build PyInstaller `onedir`, contrôles de distribution et
smoke test réussis. Les signatures Authenticode Certum avec horodatage RFC 3161 sont
valides pour `Physalyx.exe`, le désinstalleur et l'installateur. La procédure
`ExternalSignedUninstallerDir` a été utilisée avec succès. Les trois assets publics,
leur SHA-256 et `update.json` ont été revérifiés. La migration manuelle réelle de
Physalix 1.8.0 vers Physalyx 1.9.0 a été validée sur un portable Windows, et la mise
à jour automatique réelle 1.8.0 vers 1.9.0 sur un PC fixe.
La suite complète de 689 tests reste **NON VALIDÉE** ; les vérifications ciblées
ne constituent pas une validation globale.

Compatibilité impérative conservée malgré le changement de nom public : package
Python `physalix`, format interne `Physalix`, extensions `.physalix` et `.physalyx`,
ProgID et AppUserModelID historiques, mutex d'instance unique, chemins de
configuration, URL historique de l'updater et AppId Inno Setup
`{807A4F23-674E-4CD3-9B57-D66B7B819B72}`. Ne pas renommer ces identifiants sans
plan de migration explicite.

Les règles permanentes de travail avec Codex sont centralisées dans `AGENTS.md`.

---

## 4. Commandes et tests manuels

Commande habituelle de lancement en développement :

```powershell
cd C:\Physalix
.\.venv\Scripts\python.exe .\main.py
```

Si une branche particulière est requise, inclure aussi explicitement :

```powershell
git switch <branche>
```

Ne pas utiliser :

```text
python -m physalix
```

car le projet ne repose pas sur un `__main__.py` pour le lancement habituel.

Minimiser les étapes de test : ne demander que les contrôles réellement utiles.

---

## 5. Conventions UI Physalyx

### Principe général

L’interface doit rester :
- sobre ;
- desktop ;
- scientifique ;
- compacte mais lisible ;
- cohérente d’un onglet à l’autre ;
- adaptée aux écrans portables ;
- sans aspect « dashboard web » ;
- sans apparence « générée par IA ».

Ne pas gagner de place en réduisant abusivement les polices.

Le gain d’espace doit venir de :
- meilleurs layouts ;
- regroupements logiques ;
- marges maîtrisées ;
- suppression des hauteurs inutiles ;
- panneaux scrollables localement si nécessaire.

### Onglets de référence visuelle

Lors d’une nouvelle refonte, prendre en priorité comme références internes :
- Graphique ;
- Modélisation ;
- Pointage ;
- Numérisation ;
- Acquisition.

Réutiliser les mêmes composants, marges, rôles et conventions existants plutôt que créer une nouvelle identité.

### Menus déroulants — règle importante

**Ne pas créer un `QComboBox` Qt brut si le composant harmonisé Physalix est applicable.**

Utiliser le composant partagé :

`PopupComboBox`

avec les helpers existants :

- `configure_popup()`
- `update_popup_height()`

Ce comportement a déjà été harmonisé entre plusieurs écrans.

Règle visuelle :
- popup propre ;
- hauteur adaptée au contenu ;
- environ 8 éléments visibles maximum ;
- scroll au-delà ;
- première et dernière lignes entièrement visibles, y compris après défilement ;
- ouverture vers le haut lorsque l'espace manque sous le sélecteur ;
- cohérence avec les menus de Graphique / Calculs / Modélisation.

Règle d'interaction :
- la molette ne doit jamais modifier la sélection d'un menu fermé, même s'il a le focus ;
- un popup ouvert doit défiler normalement sans sélection involontaire ;
- le défilement des panneaux parents doit rester disponible lorsque le popup est fermé.

Lorsqu’un nouvel écran ou un nouveau sélecteur est ajouté, vérifier explicitement qu’il suit cette convention.

### Tableur scientifique

Conventions durables :
- une formule de cellule commence par `=` et peut être composée dans la barre `fx` au clavier et par insertion de références A1 lors de clics sur les cellules ;
- la session d’édition conserve sa cellule cible, le curseur et la sélection ; simple clic, double-clic, `F2`, Entrée et Échap doivent conduire à un comportement cohérent, sans validation intermédiaire de l’éditeur Qt ;
- la cellule cible et les cellules référencées sont distinguées temporairement pendant la composition, puis ces indications disparaissent à la fin de la session ;
- les formules acceptent les références A1, les noms scientifiques comme `=x+y` ou `=sqrt(vx^2+vy^2)`, ainsi qu’une syntaxe mixte ; un nom désigne la valeur de sa grandeur sur la ligne courante ;
- les références scientifiques sont conservées sous une forme interne liée aux colonnes logiques : renommage et déplacement visuel ne doivent pas les réorienter, tandis que la suppression produit explicitement `#REF!` ;
- les noms ambigus, réservés ou incompatibles utilisent l’adressage A1 comme solution de repli ; la recopie verticale traduit les références A1 relatives et conserve les références par nom ;
- une validation incorrecte conserve intégralement la saisie et l’ancienne valeur, puis affiche une erreur pédagogique ; aucun dialogue ne doit apparaître pendant un recalcul, une recopie ou le chargement d’un projet ;
- les projets historiques contenant des formules A1 restent compatibles et utilisent le même moteur `CellFormula`, sans système de calcul parallèle.

### Graphique

Conventions durables :
- les choix essentiels restent présentés côte à côte sous les intitulés « Grandeur en abscisse » / « Axe horizontal » et « Grandeur en ordonnée » / « Axe vertical » ;
- le rappel dynamique « Tracé : … en fonction de … » reflète les sélections réelles ;
- les options de série secondaires restent regroupées plus discrètement afin de préserver la surface du graphique ;
- les numéros visibles des séries et les noms génériques des graphiques sont continus et réutilisent les places libérées après suppression ;
- cette renumérotation d'affichage ne doit jamais modifier les identifiants internes stables, les couleurs, modèles, réglages ni la sauvegarde/relecture ;
- fermer un graphique en disposition « Onglets » doit conserver l'état maximisé du graphique restant, sans sous-fenêtre flottante, barre de titre interne ni zone noire.

### Modélisation

Conventions durables :
- les sélecteurs utilisent `PopupComboBox` et les helpers partagés ;
- chaque série conserve son propre historique de modélisations, sans dupliquer les données scientifiques déjà portées par Graphique ;
- une modélisation est présentée sur trois lignes compactes distinguant clairement la série et le type de modèle, l'équation obtenue, puis le coefficient R² ;
- la sélection permet de retrouver les paramètres et résultats, de recalculer et remplacer le modèle choisi, ou de le supprimer sans affecter les autres modèles ;
- toute création, modification ou suppression reste synchronisée avec Graphique et compatible avec la sauvegarde et la réouverture des projets existants ;
- la barre d'actions et la liste doivent rester utilisables sans chevauchement ni contenu tronqué sur les écrans portables, notamment en `1366×768` et `1100×700`.
- toute mise à jour différée d’un widget doit utiliser un timer parenté au QObject concerné afin d’être annulée automatiquement lors de sa destruction.

### Calculs

Conventions durables :
- la création directe à partir des champs Nom, Unité et Formule reste le parcours principal, avec un sélecteur d'unité éditable ;
- les formules affichées, saisies et modifiées utilisent en priorité les noms scientifiques des grandeurs, tandis que les identifiants internes restent stables et compatibles avec les références historiques `C1`, `C2`, etc. ;
- les formules et dérivées peuvent être modifiées ou supprimées depuis le tableau ; les dépendances, recalculs et détections de cycles sont appliqués atomiquement afin qu'un échec ne laisse jamais un état partiellement modifié ;
- l'insertion d'une grandeur existante utilise son nom exploitable dans la formule et ne doit pas interrompre la saisie ;
- les erreurs distinguent de façon pédagogique les grandeurs inexistantes, les erreurs de syntaxe, les fonctions inconnues et les références circulaires, tout en préservant les champs saisis ;
- après une création réussie uniquement, les champs Nom, Unité et Formule sont réinitialisés et le focus revient sur Nom ; une modification conserve son contexte ;
- le tableau et la barre d'actions réutilisent les composants et conventions visuelles partagés avec les autres onglets.

### Responsive

Pour les écrans complexes, penser notamment à :
- `1366×768`
- `1600×900`
- `1920×1080` en fenêtre non maximisée

Éviter un scroll vertical global si un layout principal avec panneaux locaux peut faire mieux.

---

## 6. Architecture et intégrations importantes

### Modèle de données

Physalix utilise un modèle de mesures partagé.

Ne pas créer inutilement un second système de données parallèle.

L’Acquisition transfère ses résultats vers les mécanismes existants de Données et Graphique.

APIs importantes utilisées par Acquisition :
- `DataTab.append_measurements(...)`
- `GraphWorkspace.add_data_graph(...)`
- `GraphWorkspace.add_data_graph_series(...)`

Préserver la compatibilité de ces APIs sauf refonte explicitement décidée.

### Onglets

L’onglet Acquisition a été ajouté en dernier afin de préserver les indices historiques des onglets existants.

Ne pas réordonner les onglets sans raison forte, car des préférences/états sauvegardés peuvent dépendre de leur ordre.

### Chargement de projet

Les changements impliquant un remplacement de projet doivent tenir compte des nettoyages/callbacks de l’Acquisition.

Ne pas introduire de callback ou état matériel persistant après un `replace_project()`.

---

## 7. Acquisition Arduino — état fonctionnel

### Matériel cible

Carte de référence :
- Arduino Uno R3 ou compatible ;
- ATmega328P ;
- logique 5 V.

Carte physique déjà utilisée :
- Funduino compatible Uno R3.

### Montage RC de référence

Montage de test :

`D8 → R → nœud`

Le nœud est relié :
- à `A0`
- au condensateur

Condensateur :
- borne positive côté nœud / A0 ;
- borne négative vers `GND`.

Montage de validation historique :
- `R = 1 kΩ`
- `C = 1000 µF`
- `τ = 1 s`

Montage pédagogique prévu pour le TP :
- `R = 1 kΩ`
- `C = 100 µF`
- `τ = 0,10 s`

### Fonctionnalités Acquisition 1.5.0

Le module gère :
- détection du port série ;
- connexion / déconnexion ;
- détection de version firmware ;
- installation/mise à jour firmware depuis Physalyx ;
- acquisition analogique A0 ;
- affichage temporaire en temps réel ;
- résultats partiels ;
- transfert vers Données / Graphique ;
- Échelon ;
- Carré — N périodes ;
- GBF carré continu ;
- synchronisation sur front montant ;
- affichage de `uC(t)` et de `E(t)` ;
- indicateur d’échantillonnage en mode GBF.

### Interface Acquisition

Architecture UI validée :
- bandeau Connexion compact en haut ;
- grande courbe à gauche ;
- panneau de réglages à droite ;
- scroll uniquement local aux réglages ;
- Actions fixes dans le panneau droit ;
- pas de scroll global ;
- graphique majoritaire ;
- adapté à un portable.

Les boutons GBF « Démarrer le générateur » et « Arrêter le générateur » sont sur deux lignes pleine largeur pour préserver la lisibilité.

### Indicateur d’échantillonnage GBF

Calcul :

`Fe acquisition / fréquence GBF réellement appliquée`

La fréquence GBF doit provenir de la valeur réellement appliquée après ACK, pas de la consigne demandée.

Seuils :
- `>= 100 pts/période` : excellent
- `>= 50` : très bon
- `>= 20` : correct
- `>= 10` : limité
- `< 10` : faible

Cet indicateur est pédagogique uniquement :
- il ne bloque jamais l’acquisition ;
- aucun warning bloquant ;
- aucune confirmation supplémentaire.

---

## 8. Contrôleur Acquisition / protocole

### Transport

`QSerialPort` est utilisé.

Principe :
- communication événementielle ;
- pas de boucle bloquante GUI ;
- `readyRead` ;
- buffer borné ;
- mise à jour UI par lots.

### Framing

Format historique du protocole :

`A5 5A | version:u8 | type:u8 | length:u16 LE | payload | CRC16:u16 LE`

CRC :
- CRC-16/CCITT-FALSE
- calculé sur version/type/length/payload

Payload maximum :
- 512 octets

Protocol version :
- `1`

### États / messages importants

Le protocole comprend notamment :
- HELLO
- HELLO_ACK
- CONFIG
- CONFIG_ACK
- START
- STOP
- DATA
- END
- ERROR

Extensions GBF :
- GEN_CONFIG
- GEN_CONFIG_ACK
- GEN_START
- GEN_START_ACK
- GEN_STOP
- GEN_STOP_ACK
- GEN_STATUS
- GEN_STATUS_ACK
- GEN_KEEPALIVE
- ACQ_STARTED
- DATA_GBF

Ne pas changer le protocole sans raison forte et plan de compatibilité explicite.

---

## 9. Firmware Arduino

### Version actuelle

Firmware Physalix :

`1.2.0`

Protocol :

`1`

Capabilities :

`0x0000001F` / `31`

### Artefacts de référence

HEX SHA-256 :

`2c2ac15843fdaaae6bc63a9ece84bc5a61740f25ad2c3d81bf9b07010901f30f`

Manifest SHA-256 :

`98e8de11f415991d296afcd9895ac498676fcd8b5461cb899bfe2d01fa55919a`

AVRDUDE 8.1 — exe SHA-256 :

`b08186071b0877ceed6ec3e86dd42ee6d2b7556859659b34d4e326069cafbf45`

AVRDUDE 8.1 — conf SHA-256 :

`690c40a8163ae845bf2b6d4635e8a3534ea75c263d8e7e59d693b182c738cf41`

Ne pas reconstruire le firmware « pour être sûr » lors d’une release applicative si aucun changement firmware n’a eu lieu.

### Toolchain firmware

- Arduino CLI 1.5.1
- core `arduino:avr@1.8.8`
- FQBN `arduino:avr:uno`

Le build doit utiliser l’application `.ino.hex`, jamais `.with_bootloader.hex`.

---

## 10. GBF continu

### Architecture

GBF indépendant de l’acquisition.

- Timer2 : génération GBF
- Timer1 : acquisition ADC
- sortie : D8
- signal carré 0–5 V
- duty-cycle 50 %

Plage :
- environ `0,1 Hz` à `1000 Hz`

Fréquence d’acquisition maximale utile actuelle :
- environ `4 kHz`

Conséquence pédagogique :
- 10 Hz → ~400 points/période
- 50 Hz → ~80
- 100 Hz → ~40
- 200 Hz → ~20
- 500 Hz → ~8
- 1 kHz → ~4

À haute fréquence, ne pas prétendre que la courbe est finement résolue : l’indicateur d’échantillonnage existe précisément pour l’expliciter.

### Synchronisation

Si le GBF est déjà RUNNING :
- START acquisition → état ARMED ;
- attente du prochain front montant ;
- ce front définit `t = 0` ;
- `ACQ_STARTED` déclenche le passage en acquisition réelle.

Les données `DATA_GBF` incluent :
- ADC ;
- bitmap de l’état physique E ;
- indices/session/sequence.

`E_k` correspond à l’état physique de D8 capturé juste avant l’ADC de l’échantillon k.

---

## 11. Flash firmware depuis Physalyx

Module dédié :

`physalix/firmware_flash.py`

Le flash :
- est explicite ;
- n’est jamais automatique ;
- utilise un `QProcess` asynchrone ;
- ne doit pas bloquer l’UI.

Commande AVRDUDE de référence :

```text
avrdude.exe -C <conf> -p atmega328p -c arduino -P COMx -b 115200 -D -U flash:w:<hex>:i
```

Ne pas ajouter `-V`.

Ne pas toucher :
- fuses ;
- EEPROM ;
- bootloader.

Le succès n’est validé qu’après :
- code retour flash correct ;
- reconnexion ;
- handshake firmware compatible.

---

## 12. Tests de référence

### Acquisition

Checkpoint complet historique avant finalisation UI/GBF :
- `391 tests` — OK

Suite complète de release 1.5.0 :
- `399 tests`
- `405,141 s`
- OK

Checkpoint technique historique Physalix 1.5.1 :
- `408 tests`
- `454,254 s`
- OK

Préparation locale signée Physalix 1.5.2 :
- `410 tests`
- OK

Release Physalix 1.6.0 :
- `615 tests` — OK dans le pipeline signé ;
- bundle PyInstaller, inventaire tiers et smoke test — OK ;
- signatures Authenticode et horodatages RFC 3161 — OK ;
- assets GitHub publics et SHA-256 — OK.

Release Physalix 1.7.0 :
- tests scientifiques et Qt ciblés — OK ;
- build PyInstaller et smoke test — OK ;
- programme, désinstalleur et installateur signés Certum et horodatés — OK ;
- installation et mise à jour automatique réelles — confirmées par l'utilisateur ;
- suite complète interrompue — **NON VALIDÉE**.

Release Physalix 1.8.0 :
- suite complète de 689 tests exécutée mais **NON VALIDÉE** : 35 échecs et 4 erreurs ;
- cause commune identifiée : d'anciens tests Qt sélectionnaient directement un
  onglet sans afficher son conteneur après l'introduction du `QStackedWidget` ;
- tests concernés adaptés à l'API publique `MainWindow.show_module(...)` ;
- les 39 anomalies historiques ont été couvertes par des vérifications ciblées réussies ;
- aucun défaut scientifique n'a été démontré par ce diagnostic ;
- build, bundle, smoke test, signatures Certum et assets publics — OK ;
- mise à jour réelle 1.7.0 vers 1.8.0 — confirmée par l'utilisateur le 18 octobre 2026.

Release Physalyx 1.9.0 :
- renommage public Physalix vers Physalyx, sans changement des identifiants internes
  nécessaires à la compatibilité ;
- interface et branding validés visuellement, y compris la navigation responsive ;
- build PyInstaller `onedir`, contrôles de distribution et smoke test — OK ;
- `Physalyx.exe`, désinstalleur et installateur signés Certum et horodatés — OK ;
- assets GitHub, SHA-256 et `update.json` publics — OK ;
- migration manuelle réelle 1.8.0 vers 1.9.0 sur portable — confirmée ;
- mise à jour automatique réelle 1.8.0 vers 1.9.0 sur PC fixe — confirmée ;
- suite complète non relancée pour ce renommage — **NON VALIDÉE**.

Le flash réel du Nano, sa reconnexion et sa réutilisation après flash avaient été
validés avant la release. Le 16 octobre 2026, la mise à jour réelle vers 1.6.0 et
le fonctionnement général sur portable ont également été confirmés par l'utilisateur.

Dernière validation ciblée UI Acquisition/Firmware UI avant intégration :
- `56 tests`
- OK

Ne pas utiliser ces nombres comme exigence absolue après de futurs ajouts : ils sont uniquement des repères historiques et le nombre de tests évoluera.

### Méthode

Pendant le développement :
- tests ciblés.

Avant une release importante :
- présenter la portée, le nombre de tests et la durée historique d'une suite complète ;
- ne la lancer qu'après autorisation distincte et explicite.

Après correction d’un échec :
- tests ciblés ;
- puis une nouvelle suite complète uniquement quand la correction est prête.

Ne jamais désactiver ou supprimer un test pour faire passer une release.

---

## 13. Packaging et updater

### Release Windows

Physalyx est distribué sous Windows sous forme de bundle PyInstaller `onedir` et
d'un installateur Inno Setup.

Workflow actuel :
- build/bundle ;
- smoke test ;
- signature Authenticode SHA-256 de `Physalyx.exe` avec horodatage RFC 3161 ;
- installateur Inno avec signature native de Setup, du désinstalleur et de ses copies temporaires ;
- vérification du certificat attendu et de l'horodatage ;
- SHA-256 ;
- `update.json` ;
- release GitHub.

Depuis la release 1.7.0, `packaging/installer/Physalix.iss` propose aussi le mode
optionnel `ExternalSignedUninstallerDir`. Il conserve la procédure intégrée
historique, mais permet, sans directive `SignTool` active :
- une première compilation Inno générant le désinstalleur persistant ;
- sa signature externe Certum avec `scripts/sign_release.ps1` ;
- une seconde compilation réutilisant ce désinstalleur signé et ses copies
  temporaires signées ;
- la signature externe de l'installateur final ;
- la vérification Authenticode, de l'horodatage RFC 3161 et du SHA-256.

Ce mode a été utilisé avec succès pour Physalix 1.7.0 après des problèmes de
visibilité du certificat SimplySign dans le SignTool lancé directement par Inno,
puis à nouveau pour les distributions signées Physalix 1.8.0 et Physalyx 1.9.0.

Une release Windows est bloquée si le certificat SimplySign, sa clé privée,
SignTool, la signature ou l'horodatage ne sont pas disponibles. L'authentification
SimplySign reste interactive ; aucun OTP, PIN ni accès au compte n'est stocké.

Le certificat Certum SimplySign est opérationnel. La chaîne automatisée a été
validée par des distributions signées et des installations réelles sous Windows :
`Physalyx.exe`, l'installateur et `unins000.exe` ont une signature
valide et horodatée, avec l'éditeur « Open Source Developer Jean SITTLER » affiché
par Windows. Avast peut encore soumettre le fichier temporaire de l'installateur
à CyberCapture pendant environ 50 secondes et analyser `Physalyx.exe` pendant
environ 10 secondes au premier lancement, avant de déclarer les fichiers sûrs.
La signature améliore l'identification de l'éditeur mais ne supprime donc pas
immédiatement toutes les analyses de réputation antivirus.
Une demande de reconnaissance du certificat a été envoyée à Avast ; la réponse
est en attente.

Les ressources firmware nécessaires au runtime doivent être incluses :
- firmware et manifeste Uno pour l'Acquisition ;
- firmware et manifeste Nano pour la Spectrophotométrie ;
- AVRDUDE 8.1 et sa configuration, partagés par les deux cartes.

Le bundle publié contient les ressources Nano et Uno ainsi qu'AVRDUDE. Les
contrôles de distribution, de signature et de publication publique ont réussi.
Pour Physalyx 1.9.0, les trois assets publics sont
`Physalyx-Setup-1.9.0.exe`, `Physalyx-Setup-1.9.0.exe.sha256` et `update.json`.

### Updater

Le système de mise à jour utilise `update.json`.
Le canal public `releases/latest/download/update.json` sert le manifeste 1.9.0,
avec `mandatory = false`. L'URL historique `jeansittler/Physalix` reste volontairement
utilisée par les versions déjà distribuées et redirige vers `jeansittler/Physalyx`.
Le client de mise à jour valide et suit explicitement les redirections HTTPS.

Une release doit vérifier :
- version correcte ;
- URL correcte ;
- SHA exact ;
- changelog UTF-8 ;
- compatibilité de l’updater existant.

Ne pas modifier la logique de fallback cumulatif sans nécessité.

Une étude ultérieure pourra évaluer un updater incrémental dans un worktree dédié.
Elle devra conserver un fallback sûr vers l'installateur complet, la vérification
d'intégrité et les exigences de signature. Aucun développement incrémental n'est
engagé à ce stade.

---

## 14. Workflow de release

Pour une version publique :

1. vérifier branche / working tree / origin ;
2. intégrer les branches de développement proprement ;
3. résoudre les conflits en conservant les deux intentions, jamais `ours/theirs` aveuglément ;
4. mettre à jour version et release notes ;
5. exécuter tests ciblés nécessaires ;
6. exécuter une seule suite complète ;
7. `git diff --check` ;
8. build / bundle / smoke test ;
9. produire installateur ;
10. calculer SHA-256 ;
11. produire/vérifier `update.json` ;
12. commit `release: prepare Physalyx X.Y.Z` ;
13. push `main` ;
14. tag annoté `vX.Y.Z` pointant exactement sur le commit de release ;
15. push tag ;
16. publier release GitHub stable/Latest ;
17. vérifier publiquement les assets et `update.json` ;
18. tester ensuite la vraie mise à jour depuis la version précédente.

Ne jamais prétendre qu’une validation réelle de mise à jour a été faite si l’utilisateur ne l’a pas effectivement réalisée.

---

## 15. Git / branches

### Stable

`main` = branche publique stable.

Ne pas développer directement une grosse fonctionnalité sur `main`.

### Organisation des conversations Codex et des worktrees

- Utiliser par défaut le projet Codex `C:\Physalix`, avec plusieurs conversations
  spécialisées selon les fonctionnalités.
- Une conversation Codex n'est pas une branche Git indépendante : plusieurs
  conversations peuvent partager les mêmes fichiers et le même worktree.
- Réserver les worktrees séparés aux gros chantiers nécessitant une isolation Git.
- `C:\Physalix` et sa branche `main` portent le contexte principal de référence.
- Dans la mesure du possible, actualiser et versionner `PROJECT_CONTEXT.md` avant de
  créer un nouveau worktree. Le worktree récupère alors le contexte versionné par
  Git ; aucune copie manuelle n'est requise.
- Ne pas entretenir des modifications locales divergentes de `PROJECT_CONTEXT.md`
  dans plusieurs worktrees. Placer les informations propres à un chantier dans une
  documentation dédiée.
- Avant une fusion, inspecter les éventuelles modifications documentaires non
  commitées dans les deux worktrees. Ne jamais écraser un contexte local.
- Après une fusion, actualiser les états historiques et retirer les instructions
  devenues périmées.
- Avant de retirer un ancien worktree, vérifier et sauvegarder toute modification
  locale encore utile.
- Avant chaque prompt Codex, préciser explicitement :
  - s'il faut ouvrir une nouvelle conversation ou reprendre une conversation
    existante ;
  - le projet et le dossier de travail ;
  - la branche Git ;
  - le modèle et le niveau de raisonnement ;
  - les actions Git autorisées et interdites.
- Après fusion d'une fonctionnalité dans `main`, réaliser les corrections courantes
  dans `C:\Physalix`, sauf nouveau chantier isolé.
- Éviter que deux sessions Codex modifient simultanément les mêmes fichiers.
- Préserver l'économie de crédits : utiliser des tests ciblés pendant le
  développement et réserver la suite complète aux checkpoints pertinents.
- Pour toute nouvelle conversation, demander explicitement la lecture intégrale de
  `AGENTS.md` et de `PROJECT_CONTEXT.md` avant toute intervention.

### Acquisition

La branche historique :

`feature/acquisition`

est conservée.

Dernier commit avant intégration dans main :

`f0e43dc7796d39bd8a1244e3350d3aa7dca8e63a`

Message :

`feat: add GBF sampling quality indicator`

Commit de merge dans main :

`9b9c3785874d4f096b1d0ba95f91fb8dcd90669f`

Message :

`feat: integrate Arduino acquisition`

Après stabilisation définitive, la branche pourra éventuellement être supprimée, mais uniquement sur décision explicite.

---

## 16. Versioning

Version applicative actuelle :

`1.9.0`

Version publique actuelle : `1.9.0`.

Firmware Arduino :

`1.2.0`

Les deux versions sont indépendantes.

Ne pas incrémenter le firmware lorsqu’une release applicative ne modifie pas le firmware.

### Convention de versions

- patch `1.5.1` : corrections / petites améliorations compatibles ;
- minor `1.6.0` : nouvelle fonctionnalité significative compatible ;
- major `2.0.0` : vraie rupture importante, incompatibilité ou transformation majeure.

Ne pas passer à `2.0.0` simplement parce qu’une fonctionnalité est importante.

---

## 17. Décisions pédagogiques Acquisition

Pour l’étude RC, le critère pédagogique utile est le rapport entre :
- demi-période `T/2`
- constante de temps `τ = RC`

Une charge/décharge quasi complète est obtenue approximativement lorsque :

`T/2 >= 5τ`

Avec `R = 1 kΩ` et `C = 100 µF` :

`τ = 0,10 s`

Exemples :
- 0,1 Hz → `T/2 = 5 s = 50τ`
- 0,5 Hz → `10τ`
- 1 Hz → `5τ`
- 5 Hz → `1τ`
- 10 Hz → `0,5τ`
- 50 Hz → `0,1τ`
- 100 Hz → `0,05τ`
- 200 Hz → `0,025τ`

Pour le TP, `200 Hz` est plus exploitable qu’un `1 kHz` très pauvre en points par période avec l’échantillonnage actuel.

À haute fréquence avec un carré 0–5 V, la tension du condensateur tend vers une faible ondulation autour de la valeur moyenne (~2,5 V en régime établi), pas vers 0 V.

---

## 18. Ce qu’il ne faut pas faire automatiquement

Ne pas :
- lancer des audits globaux inutiles ;
- refactorer « au passage » ;
- refaire une UI déjà validée ;
- remplacer un composant harmonisé par un widget Qt brut ;
- changer le firmware pendant une tâche purement applicative ;
- changer le protocole sans plan de compatibilité ;
- lancer plusieurs suites complètes redondantes ;
- commit/push avant validation si le workflow prévoit une inspection manuelle ;
- publier une release sans vérification publique des assets ;
- inventer une validation matérielle non réalisée.

---

## 19. Mise à jour de ce fichier

À la fin d’un milestone important, mettre à jour ce fichier avec uniquement les informations durables.

Ajouter ou remplacer :
- version actuelle ;
- commit/tag actuels ;
- état des branches importantes ;
- nouvelle fonctionnalité structurante ;
- décision d’architecture durable ;
- nouvelle convention UI durable ;
- nouvelle commande de référence ;
- état des tests/release ;
- prochaine étape clairement décidée.

Ne pas en faire un journal exhaustif.

Quand une information devient obsolète :
- la remplacer ;
- ou la supprimer.

Éviter de conserver plusieurs « états actuels » contradictoires.

---

## 20. Consigne à utiliser au début d’un nouveau chat

Message recommandé :

> On continue le développement de Physalyx (anciennement Physalix).
> Le fichier `PROJECT_CONTEXT.md` joint est la source de référence actuelle du projet.
> Lis-le avant toute proposition et respecte notamment les conventions UI, le workflow Codex, les niveaux GPT-5.6 Sol et l’état Git/version qui y sont décrits.
> Si une information du chat courant est plus récente que le fichier, elle prévaut et le fichier devra être mis à jour au prochain checkpoint.

---

## 21. Spectrophotométrie intégrée

### État

La Spectrophotométrie est intégrée à `main` par le commit de fusion :

`852eb5f987ce6140d3ad9944d6dbc1b01a3c3c9a`

Ce commit conserve les six commits de `feature/spectrophotometry`, dont le dernier
est `9c2577e46af869b203988285c3781fa1391bf4d0`. Le module est publié dans la release
1.6.0, taguée sur `5306f57a09000cdce5c7bf538cedd84dd85ece0c`.

Le développement parallèle dans `C:\Physalix-spectro` est terminé. Les corrections
courantes du module se font désormais dans `C:\Physalix` sur `main`, sauf
ouverture explicite d'un nouveau chantier isolé.

### Fonctions intégrées

Le module comprend notamment :

- acquisition des huit bandes visibles de l'AS7341 ;
- mesures noire, blanche et échantillon ;
- spectre d'absorbance à huit points expérimentaux ;
- mesure d'absorbance sur une bande choisie ;
- Beer-Lambert, régression linéaire et concentration inconnue ;
- suivi cinétique et diagnostics ;
- transfert vers Données et Graphique ;
- persistance dans les projets Physalix ;
- installation et contrôle du firmware Nano depuis Physalyx.

### Invariants scientifiques

Bandes réellement mesurées :

`415, 445, 480, 515, 555, 590, 630 et 680 nm`

Pour chaque bande :

`T(λ) = (I(λ) - I_dark(λ)) / (I0(λ) - I_dark(λ))`

`A(λ) = -log10(T(λ))`

Le noir, le blanc et l'échantillon doivent appartenir à une calibration compatible :
même session, mêmes paramètres d'acquisition, absence de saturation utile,
`I0 > I_dark` et `I > I_dark`.

Les huit points mesurés doivent rester identifiables. Toute interpolation est
uniquement visuelle et ne doit jamais être présentée comme une mesure continue.

### Firmware et distribution

Firmware Spectro Nano :

- version `1.0.0` ;
- protocole `1` ;
- capacités `0x0000001F` / `31` ;
- carte cible : Arduino Nano officiel A000005, ATmega328P, logique 5 V.

Le flash reste explicite, ne touche ni aux fuses, ni à l'EEPROM, ni au bootloader,
et n'est considéré comme réussi qu'après reconnexion et handshake compatible.
Les ressources Nano et Uno doivent être incluses dans la distribution. Elles
partagent AVRDUDE 8.1 et sa configuration validée.

### Documentation détaillée

Les détails matériels, mécaniques, scientifiques, protocolaires et historiques sont
conservés dans :

`docs/SPECTROPHOTOMETRY_CONTEXT.md`

Cette annexe distingue le fonctionnement confirmé, l'historique du prototype et les
expérimentations non garanties. La maintenir lors d'un changement durable du module
Spectrophotométrie sans alourdir inutilement le présent contexte principal.

### Validations

Validations conservées :

- `615 tests` complets réussis avant la fusion ;
- build PyInstaller avec firmware Nano validé ;
- flash Nano réel validé ;
- reconnexion et réutilisation du Nano après flash validées ;
- validation visuelle utilisateur réussie.

La release signée 1.6.0 intégrant Spectro est publiée et ses assets publics sont
vérifiés. Le 16 octobre 2026, l'utilisateur a validé le module Spectrophotométrie
1.6.0 sur son matériel réel Arduino Nano et capteur AS7341. La validation matérielle
finale du module n'est donc plus en attente.

Cette confirmation valide le fonctionnement matériel du module dans la release
1.6.0. Elle ne constitue pas une validation pédagogique exhaustive de chaque
expérience possible et ne permet pas d'inventer des mesures ou performances
expérimentales qui n'ont pas été communiquées.

---

## 22. Analyse d'images intégrée

### Architecture

Le module est intégré à `main` et s'appuie principalement sur :
- `physalix/image_analysis.py` pour les calculs scientifiques de profils,
  étalonnages et mesures ;
- `physalix/ui/image_analysis_canvas.py` pour l'affichage de l'image et les
  interactions graphiques ;
- `physalix/ui/image_analysis_tab.py` pour l'interface, le parcours pédagogique,
  les profils, mesures, transferts et la persistance ;
- les composants existants de projet, Données et Graphique pour l'intégration au
  modèle partagé, sans système de données parallèle.

### Fonctions intégrées

- chargement et analyse de photographies JPG, PNG et BMP ;
- étalonnages spatial et spectral, relatifs ou absolus selon le parcours choisi ;
- extraction, moyennage et comparaison de profils d'intensité ;
- tracé interactif des segments en deux clics, puis manipulation directe ;
- réticule synchronisé entre graphique, photographie et coordonnées ;
- placement des points et mesures d'écarts ou d'interfranges moyens ;
- transfert vers Données et Graphique ;
- sauvegarde de l'image et de l'état scientifique dans les projets Physalix,
  avec restauration et compatibilité des anciens projets.

Les traitements généraux avancés d'image ne font pas partie du périmètre du module.
Les validations conservées sont les tests scientifiques et Qt ciblés, le smoke test
du bundle et la validation manuelle. Elles ne remplacent pas une suite complète,
qui reste non validée pour cette release.

---

## 23. Page d'accueil scientifique

Physalyx dispose d'une véritable page d'accueil pédagogique, validée
visuellement par l'utilisateur. Elle fournit :
- une galerie visuelle des dix modules avec prévisualisations scientifiques vectorielles ;
- une grille responsive adaptée aux dimensions de la fenêtre et un accès direct
  aux modules ;
- un bandeau compact pour créer ou ouvrir un projet ;
- un bouton Accueil permanent et une navigation qui conserve le projet et les
  données en cours ;
- une intégration par `QStackedWidget` qui préserve les indices historiques du
  `QTabWidget`, ainsi que la compatibilité avec `replace_project()` et l'import CSV.

Fichiers de référence :
- `physalix/ui/home_page.py` ;
- `physalix/ui/main_window.py` ;
- `physalix/ui/theme.py` ;
- `tests/test_home_page.py`.

Toute évolution de la navigation doit utiliser l'API publique
`MainWindow.show_module(...)` lorsqu'un module doit être rendu visible, notamment
dans les tests Qt. Ne pas sélectionner directement un onglet en supposant que son
conteneur est déjà visible.

---

## 24. Prochaines étapes

1. Pour chaque nouvelle expérience pédagogique, valider séparément le protocole,
   les mesures attendues et leur interprétation avant de les documenter comme acquises.
2. Étudier ultérieurement un updater incrémental dans un worktree dédié, sans
   commencer son développement sans décision explicite.
3. Préparer ultérieurement le site officiel `physalyx.fr`, non encore déployé, de
   préférence avec GitHub Pages et le domaine géré chez OVHcloud. Ne pas annoncer
   le site comme accessible avant sa mise en ligne et sa validation réelles.

Ne jamais présenter ces validations de release ou de mise à jour comme réalisées
avant leur exécution effective.
