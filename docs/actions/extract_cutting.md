# `extract_cutting` — Détection de découpe / rainage

Détecte les tons directs ou calques de découpe-rainage (`CutContour`, `Découpe`, `Rainage`, `DieCut`, etc.) dans un PDF, et génère deux dérivés routés indépendamment : une version **simulation** (découpe visible, pour vérification visuelle) et une version **impression** (découpe supprimée ou aplatie, pour envoi presse).

## Paramètres

| Paramètre | Défaut | Détail |
|---|---|---|
| `simulation_suffix` | `_simulation` | Suffixe du dérivé simulation |
| `print_suffix` | `_print` | Suffixe du dérivé impression |
| `detect_spots` | `true` | Recherche dans `/ColorSpace` (Separation) |
| `detect_layers` | `true` | Recherche dans `/Properties` (Optional Content Groups) |
| `custom_spot_names` | `[]` | Noms de tons directs additionnels à reconnaître |
| `custom_layer_names` | `[]` | Noms de calques additionnels à reconnaître |
| `route_simulation` | — | Dict `{actions, destinations}` — au moins une des deux routes requise |
| `route_print` | — | Dict `{actions, destinations}` |

## Structure d'une route

```yaml
route_simulation:   # ou route_print
  actions:
    - type: raster
      params: { resolution: 150 }
  destinations:
    - /shares/sortie/simulation
```

Chaque route exécute son propre sous-pipeline d'actions puis distribue le résultat vers ses `destinations` propres (indépendamment de la route parallèle).

## Traitement de la version impression

- Si des **calques** ont été détectés : aplatissement via Ghostscript (`gs -sDEVICE=pdfwrite -dPDFSETTINGS=/prepress`), après désactivation des OCG concernés (le rasterizeur Ghostscript ignore silencieusement les calques masqués sans cette étape).
- Si seuls des **tons directs** ont été trouvés (pas de calque) : nettoyage direct des blocs de contenu PDF (`q...Q`) référençant le colorspace concerné, sans passer par Ghostscript.

## Exemple

Séparation basse résolution pour vérification, haute résolution pour presse :

```yaml
- type: extract_cutting
  params:
    simulation_suffix: "_simulation"
    print_suffix: "_print"
    route_simulation:
      actions:
        - type: raster
          params: { resolution: 150, output_suffix: "_raster-150" }
      destinations:
        - "/mnts/XEROX-Iridesse/APLAT"
    route_print:
      actions:
        - type: raster
          params: { resolution: 600, output_suffix: "_raster-600" }
      destinations:
        - "/mnts/XEROX-Iridesse/APLAT"
```
