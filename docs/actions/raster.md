# `raster` — Rasterisation Ghostscript

Convertit un PDF vectoriel en PDF rasterisé (image), avec préservation optionnelle des boîtes PDF (TrimBox/BleedBox), et prise en charge des tons directs.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `resolution` | 300 | Résolution en DPI |
| `color_mode` | `cmyk` | `cmyk`, `gray`, `separated` (tons directs) |
| `tiff_compression` | `lzw` | `none`, `lzw` |
| `color_profile` | `FOGRA51` | `FOGRA51`, `FOGRA52` — profil ICC CMYK appliqué par Ghostscript |
| `output_format` | `tiff` | `tiff` ou `jpeg` |
| `output_color` | `cmyk` | `cmyk` ou `rgb` (conversion Adobe RGB avec profil ICC) — ignoré si `output_format: tiff` |
| `jpeg_quality` | 85 | 1–95, utilisé seulement si `output_format: jpeg` |
| `output_suffix` | `_raster` | Suffixe ajouté au nom de fichier de sortie |
| `parallel` | `true` | Parallélisation par page (désactivée automatiquement si < 5 pages) |
| `max_workers` | `None` | Nombre de workers ; défaut = nombre de CPU disponibles |
| `keep_boxes` | `true` | Préserve TrimBox/BleedBox/CropBox/ArtBox du PDF original, recentrées après rasterisation |
| `keep_annotations` | `false` | Réservé, non traité par Ghostscript directement |
| `keep_layers` | `false` | Réservé, non traité par Ghostscript directement |
| `assembly_batch_size` | 4 | Nombre de pages par lot lors de l'assemblage TIFF → PDF en parallèle |

## Combinaisons de sortie

| `output_format` | `output_color` | Résultat |
|---|---|---|
| `tiff` | `cmyk` | TIFF LZW → assemblage `img2pdf` — production, fichiers volumineux mais fidèles |
| `jpeg` | `cmyk` | TIFF CMYK → JPEG CMYK natif → assemblage `pikepdf` (DCTDecode) — BAT impression, allégé |
| `jpeg` | `rgb` | TIFF CMYK → conversion Adobe RGB (profil ICC) → JPEG → `img2pdf` — BAT écran/email |

## Mode séparation (tons directs)

`color_mode: separated` isole chaque plaque couleur (CMJN + tons directs type Gold, Silver, Pantone) via `gs -sDEVICE=tiffsep`, puis reconstruit un PDF avec des colorspaces `Separation` par plaque (overprint activé via ExtGState). Permet de préserver un ton direct dans le fichier rasterisé final au lieu de le convertir en process.

## Exemples

Rasterisation standard CMYK pour presse :

```yaml
- type: raster
  params:
    resolution: 600
    output_suffix: "_raster-600"
```

Rasterisation avec tons directs :

```yaml
- type: raster
  params:
    resolution: 600
    output_suffix: "_raster-600-spots"
    color_mode: "separated"
```

PDF de BAT allégé (JPEG RGB pour écran) :

```yaml
- type: raster
  params:
    resolution: 150
    output_format: "jpeg"
    output_color: "rgb"
    jpeg_quality: 75
    output_suffix: "_raster_comp-150"
```
