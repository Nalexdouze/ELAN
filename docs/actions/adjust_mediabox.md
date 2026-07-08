# `adjust_mediabox` — Ajustement des fonds perdus

Recalcule la MediaBox (et la CropBox) d'un PDF en ajoutant une marge autour de la TrimBox, en centrant le contenu. Utile pour compenser des DFE presse qui n'exploitent pas correctement les fonds perdus déclarés dans la TrimBox.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `margin_mm` | 3 | Marge ajoutée de chaque côté (≥ 0) |
| `use_trimbox` | `true` | Utilise la TrimBox comme référence |
| `fallback_to_cropbox` | `true` | Utilise la CropBox si pas de TrimBox trouvée |
| `center_content` | `true` | Centre le contenu dans la nouvelle MediaBox (sinon extension seulement en haut/à droite) |
| `all_pages` | `true` | Applique à toutes les pages (sinon uniquement la première) |
| `output_suffix` | `_adjusted` | — |

## Exemple

TrimBox 210×297 mm + marge 3 mm = MediaBox 216×303 mm, centrée :

```yaml
- type: adjust_mediabox
  params:
    margin_mm: 3
    use_trimbox: true
    center_content: true
```

Généralement utilisée en première étape d'un pipeline, avant `raster` ou `impose` :

```yaml
actions:
  - type: adjust_mediabox
    params: { margin_mm: 3, use_trimbox: true, center_content: true }
  - type: raster
    params: { resolution: 800 }
```
