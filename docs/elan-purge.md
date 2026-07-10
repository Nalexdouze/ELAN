# Purge du stockage — genstore et dossiers de sortie

Script `scripts/purge_elan_storage.sh`, piloté par `config/elan-purge.yml`, exécuté quotidiennement par cron (3h, installé par `install.sh`). Complète la purge immédiate faite à la suppression manuelle d'un ticket dans la WebUI.

## Comportement spécifique à cette édition

Sur ÉLAN Public, `cleanup_job()` (`elan-watchdog.py`) purge déjà chaque dossier de job en temps réel à la fin de son traitement — le genstore ne s'accumule donc pas en usage normal. Ce script agit comme **filet de sécurité** : il purge le genstore de façon **immédiate et inconditionnelle**, sans tenir compte d'un délai de rétention (contrairement à d'autres éditions où `cleanup_job()` peut être neutralisée et où ce script applique alors un vrai délai de rétention configurable).

## Configuration — `config/elan-purge.yml`

```yaml
# Rétention du genstore en heures — ignorée sur cette édition (purge immédiate).
genstore_retention_hours: 720

# Dossiers sous /shares/sortie/ à purger, un par ligne "sous-chemin|heures".
sortie_rules:
  - "PDF pour BAT|72"
  - "PDF pour sous-traitance|720"
```

| Clé | Rôle |
|---|---|
| `genstore_retention_hours` | Délai de rétention du genstore, en heures — présent pour cohérence avec les autres éditions mais **ignoré ici** |
| `sortie_rules` | Liste de règles `"sous-chemin|heures"` : purge les fichiers du sous-dossier concerné (sous `/shares/sortie/`) plus vieux que le délai indiqué |

Ajoutez une règle par dossier de sortie à purger automatiquement, par exemple pour vos propres dossiers presse :

```yaml
sortie_rules:
  - "PDF pour BAT|72"
  - "PDF pour sous-traitance|720"
  - "Presses/XEROX Iridesse/Aplat|168"
```

## Usage manuel

```bash
sudo /opt/elan/scripts/purge_elan_storage.sh PUBLIC
```

Le script journalise chaque suppression (chemin, taille libérée) et affiche un total en fin d'exécution.
