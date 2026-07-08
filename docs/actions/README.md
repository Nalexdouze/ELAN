# Actions PDF disponibles

Chaque action du pipeline PWS est documentée séparément : rôle, paramètres complets, exemples. Voir le [README](../../README.md) pour l'installation et la configuration générale.

| Type YAML | Rôle en une phrase | Détails |
|---|---|---|
| `raster` | Rasterise un PDF (Ghostscript), CMYK/Gray/tons directs, sortie TIFF ou JPEG | [raster.md](raster.md) |
| `impose` | Impose un PDF avec calcul automatique des poses et repères de coupe | [impose.md](impose.md) |
| `adjust_mediabox` | Ajuste MediaBox/CropBox autour de la TrimBox (fonds perdus) | [adjust_mediabox.md](adjust_mediabox.md) |
| `add_trim_guide` | Ajoute repères visuels de coupe, plis, côtes (BAT) | [add_trim_guide.md](add_trim_guide.md) |
| `extract_cutting` | Sépare un PDF avec calque/tons de découpe en versions simulation + impression | [extract_cutting.md](extract_cutting.md) |
| `saddle_stitch_split` | Sépare couverture / intérieur pour piqûre à cheval | [saddle_stitch_split.md](saddle_stitch_split.md) |
| `perfect_binding_split` | Découpe en cahiers pour reliure dos carré collé | [perfect_binding_split.md](perfect_binding_split.md) |
| `print` | Envoie vers une imprimante CUPS (traceurs) | [print.md](print.md) |

`duplicate_sheets` et `import_jdf` sont des actions supplémentaires, disponibles uniquement dans ÉLAN Premium (accès sur demande, voir le [README](../../README.md) principal).

Pour des exemples de watchers complets combinant plusieurs actions, voir [watcher_descriptions_examples.md](../watcher_descriptions_examples.md).
