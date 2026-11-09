# Instructions permanentes pour Codex

<!-- PHYSALIX_CODEX_BUDGET_START -->

## Règles prioritaires — Budget Codex et maîtrise des tests

**Cette politique prime sur les consignes génériques d'audit/checkpoint qui demanderaient de tester largement. Elle ne remplace pas les consignes de sûreté, les instructions explicites de l'utilisateur ni les règles d'architecture du projet.**

### 1. Budget et choix du modèle

- Conseiller **GPT-5.6 Sol — Minimal** par défaut pour les corrections localisées, l'UI, la documentation et les tâches Git simples. Conseiller **Sol — Moyen** pour un diagnostic difficile ou des modifications touchant plusieurs modules. **Sol — Élevé** seulement après accord explicite. Le choix effectif du modèle appartient à l'utilisateur.
- Une tâche = un périmètre délimité, un résultat concret, puis arrêt. Pas de travaux supplémentaires « au passage », de nouveaux audits ni de nouvelles optimisations non demandées.
- Si la tâche risque de dépasser **15 minutes** d'exécution ou nécessite plus de **12 appels d'outils significatifs**, s'arrêter et demander l'autorisation de continuer, avec un bilan des actions déjà réalisées.
- Lire `AGENTS.md` et `PROJECT_CONTEXT.md` une seule fois au début d'une conversation, puis réutiliser les informations déjà en contexte tant que les fichiers n'ont pas changé ; éviter de les relire intégralement à chaque sous-tâche.
- Communication concise : annoncer le plan, signaler un blocage réel et fournir le bilan. **Ne pas envoyer de messages périodiques répétitifs pour dire qu'un processus tourne toujours.**

### 2. Autorisation des tests (règle impérative)

- **Par défaut : tests ciblés uniquement**, portant sur les fichiers et comportements modifiés. Ne pas lancer automatiquement `unittest discover`, le pipeline complet, une compilation, un build ou un audit transversal.
- Une demande générale telle que « audit final », « stabiliser », « préparer la fusion » ou même une liste d'étapes incluant « suite complète » **ne vaut pas autorisation de lancer immédiatement une suite complète**. Avant celle-ci, présenter sa portée, le nombre de tests et la durée historique connue, puis **obtenir un feu vert distinct et explicite de l'utilisateur**.
- Limiter les tests ciblés à **un lot initial**, puis **un lot de vérification après correction** si nécessaire. Demander l'accord avant d'élargir sensiblement la couverture.
- **Durée maximale d'une commande de tests ciblés : 3 minutes.** Si ce plafond est insuffisant, demander l'autorisation préalable de lancer une commande plus longue. Utiliser un mécanisme de timeout effectif ; ne pas laisser l'exécution sans borne.
- **Si exceptionnellement autorisée**, une suite complète ne peut durer plus de **12 minutes**, à moins qu'un nouveau budget ait été expressément approuvé AVANT son lancement. À l'échéance, interrompre proprement, indiquer que la suite est incomplète et diagnostiquer le test en cause par un appel ciblé.
- Si une suite n'affiche aucune progression pendant **5 minutes**, considérer la situation comme anormale : arrêter et diagnostiquer, même si le CPU consomme encore. La seule activité CPU **n'est jamais une justification pour attendre indéfiniment**.
- Après un timeout, échec ou interruption : **jamais de relance automatique de la suite complète**. Reproduire le cas isolément, documenter les résultats, demander l'accord avant tout nouveau checkpoint global.
- Ne pas multiplier les sondages de processus, attentes d'une minute, ou messages de surveillance : une commande bornée, un résultat, puis décision.

### 3. Règles de livraison

- Ne jamais annoncer qu'une suite interrompue est passée. Distinguer : tests ciblés réussis, partie du global exécutée, global **non validé**.
- Rapport final compact : fichiers modifiés, défaut corrigé, commandes/tests exécutés avec durée et résultat, risques ou tests restant à faire ; pas de journal d'attente.
- Par défaut aucun commit, push, merge, tag, release, build ni changement de version sans instruction explicite propre à l'étape.
- Toute exception à un plafond de temps ou au périmètre exige d'abord l'accord de l'utilisateur ; aucune autonomie illimitée.

<!-- PHYSALIX_CODEX_BUDGET_END -->

- Lire `PROJECT_CONTEXT.md` avant toute intervention dans le dépôt.
- Préserver les crédits et le temps d’exécution sans réduire la fiabilité : limiter l’exploration aux fichiers utiles et éviter les opérations redondantes.
- Prévenir l’utilisateur avant une opération potentiellement longue et en estimer la durée. En cas de problème de permissions ou d’environnement, diagnostiquer avant de relancer une opération coûteuse.
- Choisir le niveau GPT-5.6 Sol adapté à la difficulté : minimal pour une opération locale et mécanique, moyen pour une évolution circonscrite à plusieurs fichiers, élevé pour une intégration complexe ou une release, très élevé seulement pour un problème exceptionnellement ambigu ou transversal.
- Utiliser des tests ciblés pendant le développement. N’exécuter qu’une seule suite complète aux checkpoints techniques pertinents et ne pas répéter les tests ou builds déjà validés lorsque le code concerné n’a pas changé.
- Ne pas créer de commit, pousser, taguer ou publier avant validation explicite de l’utilisateur.
- Pour tout test manuel demandé, fournir une commande PowerShell directement prête à copier.
- Respecter la chaîne de release et de signature Authenticode Certum décrite dans `PROJECT_CONTEXT.md`. Ne jamais publier un installateur non signé ou insuffisamment vérifié.
- L’authentification SimplySign reste interactive. Ne jamais stocker ni exposer de PIN, OTP, jeton, clé privée ou accès au compte Certum.
- Avant une suite complète de release, utiliser un worktree propre avec les fixtures Git canoniques et exécuter le précontrôle léger de version/métadonnées. Ne construire ni signer qu’après un résumé global sans échec ni erreur, et ne jamais relancer automatiquement après un échec.
