# `impose` — Imposition automatique

Impose un PDF sur une feuille de format donné, avec calcul automatique du nombre optimal de poses, repères de coupe et gestion du recto-verso.

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `layout` | `auto` | `auto` (calcul automatique), `2-up`, `4-up`, `8-up`, `16-up` (grilles fixes) |
| `output_format` | `SRA3` | Format standard (`A5`→`A0`, `SRA1`→`SRA3`) ou `custom` |
| `custom_width` / `custom_height` | `None` | Requis si `output_format: custom` (mm) |
| `margin_x` / `margin_y` | 10 / 10 | Marges d'impression gauche/droite et haut/bas (mm) |
| `gutter_h` / `gutter_v` | 4 / 4 | Gouttières horizontale/verticale entre poses (mm) |
| `bleed` | 3 | Fond perdu conservé par pose (mm) |
| `crop_marks` | `true` | Ajout de repères de coupe |
| `crop_mark_length` | 3 | Longueur des repères (mm) |
| `crop_mark_color` | `all` | `all` (noir total CMJN), `cyan`, `magenta`, `yellow`, `black` |
| `crop_mark_offset` | 2 | Distance entre le repère et la zone de rogne (mm) |
| `crop_mark_width` | 0.25 | Épaisseur du trait (pt) |
| `use_trimbox` | `true` | Utilise la TrimBox du PDF source comme référence de dimension |
| `center_pages` | `true` | Centre la grille de poses sur la feuille |
| `rotate_if_better` | `true` | Rotation automatique des pages si elle augmente le nombre de poses |
| `output_suffix` | `_imposed` | — |
| `mode` | `distribute` | `distribute` (pages successives) ou `repeat` (répétition de la même page sur toutes les poses) |
| `duplex` | `false` | Recto-verso : 1 PDF source → 2 feuilles imposées |

## Calcul du layout `auto`

Le nombre de colonnes/lignes est calculé à partir de la zone imprimable (feuille moins marges), en tenant compte des gouttières et des fonds perdus. Si `rotate_if_better: true`, les deux orientations (normale et pivotée à 90°) sont comparées et celle donnant le plus de poses est retenue.

## Mode `repeat` vs `distribute`

- `distribute` : chaque pose reçoit une page différente du PDF source, dans l'ordre.
- `repeat` : la même page (page 1, ou page 2 pour le verso en duplex) est répétée sur toutes les poses de la feuille — utile pour imposer plusieurs exemplaires identiques d'un même visuel (ex. étiquettes, cartes de visite).

## Mode `duplex`

En `distribute` + `duplex` : les pages impaires du PDF source vont sur la feuille recto, les paires sur la feuille verso (colonnes inversées en miroir pour que le repérage tombe juste à l'impression retournée). En `repeat` + `duplex` : la page 1 est répétée au recto, la page 2 au verso.

## Exemples

Imposition SRA3 automatique, repères de coupe :

```yaml
- type: impose
  params:
    layout: "auto"
    output_format: "SRA3"
    bleed: 3
    crop_marks: true
```

Format custom, recto-verso, mode répétition avec double coupe :

```yaml
- type: impose
  params:
    layout: "auto"
    output_format: "custom"
    custom_width: 450
    custom_height: 320
    gutter_h: 5
    gutter_v: 5
    bleed: 3
    crop_marks: true
    crop_mark_color: "all"
    use_trimbox: true
    mode: "repeat"
    duplex: true
```
