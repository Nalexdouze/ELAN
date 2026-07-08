# `perfect_binding_split` — Dos carré collé

Découpe un PDF de brochure en cahiers pour reliure dos carré collé (perfect binding). L'algorithme privilégie des cahiers complets (ex. 16 pages en 8up) et insère des cahiers d'ajustement plus petits (8p/4p) si le nombre total de pages n'est pas un multiple exact.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `max_up` | 8 | Nombre de pages max par cahier : 8up = 16 pages, 4up = 8 pages |
| `prefix` | `"C%nb%_"` | Préfixe du nom de fichier, `%nb%` remplacé par le numéro du cahier |
| `route_actions` | `[]` | Actions communes appliquées à chaque cahier avant distribution |
| `destinations` | — | **Requis** — dict par format Nup, chaque valeur étant une liste de chemins |

Clés valides pour `destinations` : `8up`, `4up`, `2up`, `1up`. Chaque cahier extrait est routé automatiquement vers la liste correspondant à son format déterminé selon son nombre de pages.

## Exemple

Brochure au format proche A5, imposable en 16 pages, avec cahiers d'ajustement 8p/4p :

```yaml
- type: perfect_binding_split
  params:
    max_up: 8
    prefix: "C%nb%_"
    route_actions:
      - type: adjust_mediabox
        params: { margin_mm: 3, use_trimbox: true, center_content: true }
      - type: raster
        params: { resolution: 800, output_suffix: "_raster-800" }
    destinations:
      8up:
        - "/mnts/HP-Indigo-12KVP15K-HD/BROCHURE AUTO COLLE-16P"
        - "/mnts/HP-Indigo-12KVP15K-HD/BROCHURE AUTO COLLE-16P - EPM"
      4up:
        - "/mnts/HP-Indigo-12KVP15K-HD/BROCHURE AUTO COLLE-8P"
      2up:
        - "/mnts/HP-Indigo-12KVP15K-HD/BROCHURE AUTO COLLE-4P"
```

Pour un format proche A4 (imposable en 8 pages), utiliser `max_up: 4` avec les clés `4up`/`2up`.
