# `print` — Impression CUPS (traceurs)

Envoie un PDF vers une imprimante CUPS, avec calcul automatique du format personnalisé et de l'orientation optimale selon la largeur du rouleau.

Conçue à l'origine pour piloter un traceur **Epson SureColor** (SC-T7200), l'action reste générique : elle s'appuie sur CUPS standard (`lp`/`lpadmin`), donc utilisable avec n'importe quelle imprimante ou traceur pris en charge par CUPS. Seuls `printer_driver` (auto-détection du PPD Epson par défaut) et certaines options (`print_quality`, `mode`, `auto_cut`) sont taillées sur les options CUPS spécifiques aux traceurs Epson — à ajuster ou ignorer selon le matériel réellement piloté.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `printer_name` | — | **Requis** |
| `printer_ip` | `None` | Pour configuration CUPS automatique (URI `socket://ip:9100`) si l'imprimante n'est pas déjà déclarée |
| `printer_uri` | `None` | Prioritaire sur `printer_ip` |
| `printer_driver` | `None` | Auto-détection du PPD Epson SC-T7200 ; sinon `everywhere`, `gutenprint`, ou chemin PPD explicite |
| `roll_width_mm` | 1118 | Largeur du rouleau, utilisée pour choisir l'orientation |
| `media_source` | `RollPaper1` | `RollPaper1`, `RollPaper1_Banner`, `Sheet` |
| `media_type` | `None` | Type de papier (option CUPS `MediaType`), ex. `PHOTO_QUALITY_INKJET_PAPER` |
| `margin_top/bottom/left/right` | `0/0/0/4` | Marges ajoutées au format personnalisé (mm) |
| `print_quality` | `Quality` | `Speed`, `Quality`, `Max_Quality`, `Ultra_Max_Quality` |
| `color` | `Color` | `Color` ou `Black` |
| `high_speed` | `true` | Impression bidirectionnelle ; forcé à `false` automatiquement si `print_quality: Ultra_Max_Quality` |
| `mode` | `Standard` | `Standard`, `ChartsGraphs`, `LineDrawing` |
| `auto_cut` | `NormalCut` | `Off`, `SingleCut`, `DoubleCut`, `NormalCut` |
| `borderless` | `false` | Option CUPS `Borderless=On` |
| `quantity` | 1 | Doit être compris entre 1 et `max_quantity` |
| `max_quantity` | 99 | Plafond de sécurité |
| `auto_rotate` | `true` | Rotation automatique si elle permet de tenir dans `roll_width_mm` |
| `scaling` | 100 | Option CUPS `scaling` |
| `icc_profile` | `None` | Chemin d'un fichier ICC ; avertissement si le fichier n'existe pas |
| `output_dir` | `None` | Copie du fichier envoyé à l'impression, pour archivage |

## Fonctionnement

1. Vérifie que le scheduler CUPS tourne (`lpstat -r`).
2. Vérifie si l'imprimante est déjà configurée (`lpstat -p <printer_name>`) ; sinon la déclare automatiquement (`lpadmin -p <name> -v <uri> -E -m <driver>`) si `printer_ip`/`printer_uri` est fourni.
3. Lit les dimensions réelles du PDF (via `pikepdf`) pour calculer un format `Custom.{w}x{h}mm`, avec rotation si nécessaire pour tenir dans `roll_width_mm`.
4. Une quantité peut être surchargée par un fichier `.{nom_fichier}.metadata.json` adjacent au PDF (déposé par une interface d'upload), lu puis supprimé.
5. Construit et exécute la commande `lp` (une commande par exemplaire, boucle sur `quantity`).

## Exemple

```yaml
- type: print
  params:
    printer_name: "EPSON-SC-T7200"
    printer_ip: "192.168.34.20"
    roll_width_mm: 1118
    media_type: "PHOTO_QUALITY_INKJET_PAPER"
    quantity: 1
    max_quantity: 10
    print_quality: "Max_Quality"
```

Généralement précédée d'un ajustement des fonds perdus et d'une rasterisation :

```yaml
actions:
  - type: adjust_mediabox
    params: { margin_mm: 10 }
  - type: raster
    params: { resolution: 300 }
  - type: print
    params: { printer_name: "EPSON-SC-T7200", printer_ip: "192.168.34.20" }
```

`print` est une action **terminale** : elle ne retourne pas de fichier à distribuer, le watcher n'a donc pas besoin de `destinations`.
