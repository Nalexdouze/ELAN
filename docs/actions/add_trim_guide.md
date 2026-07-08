# `add_trim_guide` — Repères visuels (BAT)

Ajoute sur un calque PDF dédié (`BlueLines`, Optional Content Group) des repères visuels destinés au BAT client : zone de rogne (TrimBox), plis, fond perdu (BleedBox) et côtes cotées. Dessin en CMYK process ou en ton direct.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `stroke_width` | 0.75 | Épaisseur du trait TrimBox (pt) |
| `dash_pattern` | `"2,2"` | Motif pointillé `"on,off"` en mm |
| `color` | `magenta` | `magenta`, `cyan`, `yellow`, `black`, `registration`, `green`, `red`, `blue` |
| `spot_name` | `BL-TrimBox` | Si renseigné, dessin en ton direct (Separation) plutôt qu'en CMYK process |
| `overprint` | `true` | Ajoute un ExtGState overprint |
| `use_trimbox` | `true` | — |
| `fallback_to_mediabox` | `true` | Utilisé si pas de TrimBox |
| `all_pages` | `true` | Sinon uniquement la première page |
| `output_suffix` | `_trimguide` | — |
| `fold_guides` | `true` | Active la détection/dessin des plis |
| `fold_color` | `green` | Même liste de couleurs valides |
| `fold_pattern` | `"3,3"` | Motif pointillé des plis |
| `fold_vertical` / `fold_horizontal` | `None` | Override manuel si la détection auto par nom de fichier échoue |
| `fold_spot_name` | `BL-Fold` | Ton direct pour les plis |
| `dimensions` | `true` | Active les côtes (flèches + texte en mm) |
| `dimension_offset` | 6 (mm) | Distance entre la TrimBox et la flèche |
| `dimension_text_size` | 8 (pt) | — |
| `dimension_arrow_size` | 2 (mm) | — |
| `dimensions_color` | `black` | — |
| `dimensions_spot_name` | `BL-Dimensions` | Ton direct des côtes |
| `bleed_box` | `true` | Dessine la BleedBox si présente dans le PDF |
| `bleed_color` | `cyan` | — |
| `bleed_spot_name` | `BL-Bleed` | Ton direct du fond perdu |

## Détection automatique des plis

La détection se fait via le **nom de fichier** (prioritaire sur les paramètres YAML `fold_vertical`/`fold_horizontal`) :

| Pattern nom de fichier | Interprétation |
|---|---|
| `Depliant-146.5-148.5-148.5` | Volets verticaux de largeurs différentes (mm), dans l'ordre |
| `Depliant-V100` | Division automatique de la TrimBox par tranches verticales de 100 mm |
| `Plan-V97-105-105_H80-80-50` | Plis verticaux et horizontaux combinés |

## Exemple

Utilisée en fin de pipeline BAT, après rasterisation :

```yaml
actions:
  - type: adjust_mediabox
    params: { margin_mm: 12 }
  - type: raster
    params: { resolution: 150, output_format: "jpeg", output_color: "rgb", jpeg_quality: 75 }
  - type: add_trim_guide
```

Avec ton direct dédié pour éviter toute confusion avec l'encre process :

```yaml
- type: add_trim_guide
  params:
    color: "magenta"
    spot_name: "BL-TrimBox"
    dimensions: true
    dimensions_spot_name: "BL-Dimensions"
```
