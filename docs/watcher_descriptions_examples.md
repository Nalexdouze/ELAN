# Exemples de watchers — cookbook

Recueil d'exemples organisés par cas d'usage. Pour le schéma YAML complet d'un watcher et la liste des actions disponibles, voir le [README](../README.md) et [docs/actions/](actions/README.md).

## Aplat simple (une presse, une résolution)

```yaml
- name: "XEROX Aplat"
  description: |
    Rasterisation à *600 DPI* pour aplat CMJN sur **Xerox Iridesse**.
  folder: /shares/entree/Presses/XEROX Iridesse/Aplat
  patterns: ["*.pdf"]
  actions:
    - type: raster
      params:
        resolution: 600
        output_suffix: "_raster-600"
  destinations:
    - "/mnts/XEROX-Iridesse/APLAT"
```

## Aplat avec tons directs (PMS)

```yaml
- name: "XEROX Aplat PMS"
  description: |
    Rasterisation à *600 DPI* pour aplat incluant des tons directs sur **Xerox Iridesse**.
  folder: /shares/entree/Presses/XEROX Iridesse/Aplat PMS
  patterns: ["*.pdf"]
  actions:
    - type: raster
      params:
        resolution: 600
        output_suffix: "_raster-600-spots"
        color_mode: "separated"
  destinations:
    - "/mnts/XEROX-Iridesse/APLAT"
```

## Correction fonds perdus avant rasterisation (bug DFE)

Pattern utile quand un DFE presse n'exploite pas correctement les fonds perdus déclarés dans la TrimBox :

```yaml
- name: "HP Aplat Recto"
  description: |
    Rasterisation à *800 DPI* pour aplat **RECTO** sur **HP Indigo**.
    Correction pour compenser le bug du DFE avec les fonds perdu.
    Automatiquement envoyé en CMYK et EMP.
  folder: /shares/entree/Presses/HP Indigo/Aplat/Recto/Quadri
  patterns: ["*.pdf"]
  actions:
    - type: adjust_mediabox
      params: { margin_mm: 3, use_trimbox: true, center_content: true }
    - type: raster
      params: { resolution: 800, output_suffix: "_raster-800" }
  destinations:
    - "/mnts/HP-Indigo/APLAT AUTO Recto"
    - "/mnts/HP-Indigo/APLAT AUTO Recto EPM"
```

## Découpe : simulation + impression séparées

```yaml
- name: "HP Aplat Recto Découpe"
  description: |
    Rasterisation à *800 DPI* pour aplat **RECTO** incluant des tons directs ou calque de découpe sur **HP Indigo**.
    Envoie de 2 PDF séparant automatiquement les découpes.
  folder: /shares/entree/Presses/HP Indigo/Aplat/Recto/Decoupe
  patterns: ["*.pdf"]
  actions:
    - type: adjust_mediabox
      params: { margin_mm: 3, use_trimbox: true, center_content: true }
    - type: extract_cutting
      params:
        simulation_suffix: "_simulation"
        print_suffix: "_print"
        route_simulation:
          actions: [{ type: raster, params: { resolution: 150, output_suffix: "_raster-150" } }]
          destinations: ["/mnts/HP-Indigo/APLAT AUTO Recto EPM"]
        route_print:
          actions: [{ type: raster, params: { resolution: 800, output_suffix: "_raster-800" } }]
          destinations:
            - "/mnts/HP-Indigo/APLAT AUTO Recto"
            - "/mnts/HP-Indigo/APLAT AUTO Recto EPM"
```

## Imposition recto-verso avec double coupe

```yaml
- name: "XEROX Aplat Impose RV"
  description: |
    Rasterisation à *600 DPI* pour aplat sur **Xerox Iridesse**.
    Imposition **RECTO-VERSO** en mode **répétition**.
    Double coupe de **5 mm**
  folder: /shares/entree/Presses/XEROX Iridesse/Aplat-Impose-Repeat-RV
  patterns: ["*.pdf"]
  actions:
    - type: raster
      params: { resolution: 600, output_suffix: "_raster-600" }
    - type: impose
      params:
        layout: "auto"
        output_format: "custom"
        custom_width: 450
        custom_height: 320
        margin_x: 3
        margin_y: 3
        gutter_h: 5
        gutter_v: 5
        bleed: 3
        crop_marks: true
        crop_mark_color: "all"
        use_trimbox: true
        center_pages: true
        rotate_if_better: true
        mode: "repeat"
        duplex: true
  destinations:
    - "/mnts/XEROX-Iridesse/APLAT"
```

## Brochure piquée répartie sur deux presses

```yaml
- name: "Brochure HP+XEROX - Automatique"
  description: |
    Séparation automatique :
    - couverture sur **Xerox Iridesse**
    - intérieur sur **HP Indigo**
  folder: /shares/entree/Presses/Brochures - XEROX-Couv HP-Interieur
  patterns: ["*.pdf"]
  stability_timeout: 600
  actions:
    - type: saddle_stitch_split
      params:
        cover_pages: "1-2,-2--1"
        route_cover:
          actions: [{ type: raster, params: { resolution: 600, output_suffix: "_raster-600" } }]
          destinations: ["/mnts/XEROX-Iridesse/BROCHURE"]
        route_inner:
          actions:
            - type: adjust_mediabox
              params: { margin_mm: 3, center_content: true }
            - type: raster
              params: { resolution: 800, output_suffix: "_raster-800" }
          destinations:
            - "/mnts/HP-Indigo/BROCHURE AUTO ENCARTE"
            - "/mnts/HP-Indigo/BROCHURE AUTO ENCARTE EPM"
```

## Brochure dos carré avec cahiers d'ajustement

```yaml
- name: "HP Brochure Dos Carré (Petit format ± A5)"
  description: |
    Sépare de façon intelligente une brochure en 16, 8 ou 4 pages et les distribue sur les bonnes impositions.
    Fonctionne pour un format proche de l'A5, imposable en 16 pages.
  folder: /shares/entree/Presses/HP Indigo/Brochure/Dos carre A5
  patterns: ["*.pdf"]
  actions:
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
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-16P"
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-16P - EPM"
          4up:
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-8P"
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-8P - EPM"
          2up:
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-4P"
            - "/mnts/HP-Indigo/BROCHURE AUTO COLLE-4P - EPM"
```

## PDF pour BAT (repères visuels, allégement JPEG)

```yaml
- name: "PDF pour BAT RVB-150"
  description: |
    **PDF à usage de BAT**
    Rasterisation *150 DPI* **avec** compression JPEG et **conversion RVB**, équivalent à un PDF taille minimale.
    Ajouts des repères visuels : coupe, fond perdu, plis, côtes des volets en cas de plis.
  folder: /shares/entree/PDF pour BAT/RVB-150
  patterns: ["*.pdf"]
  downloadable: true
  actions:
    - type: adjust_mediabox
      params: { margin_mm: 12 }
    - type: raster
      params:
        resolution: 150
        output_format: "jpeg"
        output_color: "rgb"
        jpeg_quality: 75
        output_suffix: "_raster_comp-150"
    - type: add_trim_guide
  destinations:
    - "/shares/sortie/PDF pour BAT/RVB-150"
```

## Sous-traitance (résolution seule, aucune imposition)

```yaml
- name: "PDF pour sous-traitance CMJN-600"
  description: |
    **PDF à destination de sous-traitants**.
    Rasterisation *600 DPI* **sans** compression.
  folder: /shares/entree/PDF pour sous-traitance/CMJN-600
  patterns: ["*.pdf"]
  downloadable: true
  actions:
    - type: raster
      params: { resolution: 600, output_suffix: "_ST_CMJN_raster-600" }
  destinations:
    - "/shares/sortie/PDF pour sous-traitance/CMJN-600"
```

## Traceur grand format (impression directe)

```yaml
- name: "EPSON SC-T7200 Qualité Max"
  description: |
    Ajustement des zones pour être certains d'avoir les repères de coupe.
    Rasterisation à *300 DPI*. Envoi sur le traceur *EPSON SureColor T7200*.
  folder: /shares/entree/Traceurs/EPSON SC-T7200/Qualite Max
  patterns: ["*.pdf"]
  actions:
    - type: adjust_mediabox
      params: { margin_mm: 10 }
    - type: raster
      params: { resolution: 300 }
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

## Envoi direct sans traitement

```yaml
- name: "EPSON SC-P5000"
  description: |
    Envoi direct **sans** traitement dans le RIP pour épreuve chromatique.
  folder: /shares/entree/Traceurs/EPSON SC-P5000 (GMG)
  patterns: ["*.pdf"]
  destinations:
    - "/mnts/RIP-GMG/Fogra39L sans gamme"
```

Un watcher sans `actions` est valide : le fichier est simplement déplacé du genstore vers ses `destinations` sans traitement.

## Fichiers de découpe (formats non-PDF)

```yaml
- name: "Morgana SC7100ProT XL"
  description: |
    Envoi direct des fichiers de découpe sur ColorCutPro
  folder: /shares/entree/Decoupe/Morgana SC7100ProT XL - ColorCutPro
  patterns: ["*.jbf", "*.ilm"]
  destinations:
    - "/mnts/PC-ColorCutPro"
  overwrite: true
```

`patterns` n'est pas limité aux PDF — tout format reconnu par le hotfolder peut être surveillé.
