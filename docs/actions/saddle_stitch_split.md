# `saddle_stitch_split` — Piqûre à cheval

Sépare un PDF de brochure en deux fichiers — couverture et intérieur — pour un assemblage par piqûre à cheval (saddle stitch), chacun routé (sous-pipeline + distribution) indépendamment. Utile notamment pour répartir couverture et intérieur sur deux presses différentes.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `cover_pages` | `"1-2,-2--1"` | Pages de couverture : 2 premières + 2 dernières par défaut |
| `cover_suffix` | `_cover` | — |
| `inner_suffix` | `_inner` | — |
| `route_cover` | — | **Requis** — dict `{actions, destinations}` |
| `route_inner` | — | **Requis** — dict `{actions, destinations}` |

Si `cover_pages` garde sa valeur par défaut, l'intérieur correspond aux pages 3 à `total-2`. Avec un format `"X-Y"` explicite, l'intérieur suit après la page `Y`.

## Exemple

Couverture sur une presse feuille, intérieur sur une presse rouleau/toner avec correction fonds perdus :

```yaml
- type: saddle_stitch_split
  params:
    cover_pages: "1-2,-2--1"
    cover_suffix: "_cover"
    inner_suffix: "_inner"
    route_cover:
      actions:
        - type: raster
          params: { resolution: 600, output_suffix: "_raster-600" }
      destinations:
        - "/mnts/XEROX-Iridesse/BROCHURE"
    route_inner:
      actions:
        - type: adjust_mediabox
          params: { margin_mm: 3, center_content: true }
        - type: raster
          params: { resolution: 800, output_suffix: "_raster-800" }
      destinations:
        - "/mnts/HP-Indigo/BROCHURE"
```
