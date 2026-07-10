# ÉLAN — Community Edition

> Le hub intelligent du prépresse : automatisez vos workflows d'impression avec élégance

[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.12-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE)

---

**Version gratuite et open-source** sous licence GPLv3 — libre, sans limitation de fonctionnalités sur le moteur de traitement.

ÉLAN Community Edition contient le **PWS (Prepress Workflow System)** complet : un moteur de hotfolders qui surveille des dossiers réseau, traite automatiquement vos PDF selon des règles YAML, et les distribue vers vos presses et équipements — sans interface web ni ERP (réservés à la version Premium).

---

## 💡 Pourquoi ÉLAN

ÉLAN est né d'une urgence de terrain : la coupure brutale d'un flux de production suite à un changement interne, sans plus aucun outil pour recevoir et envoyer les travaux vers les presses. Plutôt que de multiplier les montages réseau sur chaque poste pour atteindre les hotfolders de chaque presse, l'idée a été de centraliser tout dépôt de fichier en un point unique et d'automatiser le traitement qui suit.

La rasterisation systématique en amont (action [`raster`](docs/actions/raster.md)) n'est pas un détail : elle garantit qu'un BAT présenté au client aura exactement le même rendu que ce qui sortira en presse, puisque les deux traversent le même pipeline. Des RIP différents entre poste de contrôle et presse peuvent interpréter un même PDF vectoriel différemment — rasteriser une seule fois, en amont, élimine cette source d'erreur.

---

## 📖 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Installation](#-installation)
- [Configuration](#️-configuration)
- [Actions disponibles](#-actions-disponibles)
- [Monitoring](#-monitoring)
- [Version Premium](#-version-premium)
- [Licence](#-licence)

---

## 🎯 Vue d'ensemble

Chaque fichier déposé dans un dossier surveillé (hotfolder) déclenche un pipeline d'actions configurable en YAML — rasterisation, imposition, split de brochure, ajustement des fonds perdus, détection de découpe — puis est distribué automatiquement vers une ou plusieurs destinations (presses, sous-traitance, archivage).

- ✅ **Monitoring hotfolder intelligent** : attente de stabilité du transfert, nettoyage des fichiers junk macOS, reprise au redémarrage
- ✅ **Pipeline d'actions modulaire** : les actions se chaînent, chacune retourne le fichier suivant
- ✅ **Robuste** : file d'attente automatique si un montage réseau (CIFS) est down, retry jusqu'à réussite
- ✅ **Multi-presses** : distribution simultanée vers plusieurs équipements
- ✅ **Observable** : un journal détaillé par job dans `/shares/sortie/journaux/`
- ✅ **Impression CUPS** : traceurs grand format (Epson SureColor)

## 🚀 Installation

### Prérequis

- Debian/Ubuntu Server (testé sur Debian 12)
- Docker et Docker Compose
- Support iSCSI si LUN réseau
- Accès root

### Installation

Récupérez `install.sh` et `install.zip` (générés depuis ce dépôt), placez-les dans le même dossier sur votre serveur, configurez `lun.yml` si vous utilisez un LUN iSCSI, puis :

```bash
chmod +x install.sh
sudo ./install.sh
```

Le script installe Docker, configure le montage iSCSI si `lun.yml` est présent, et démarre les containers du PWS (`elan-guardian`, `elan-samba-mnt`, `elan-samba-share`, `elan-watchdog`, `elan-cups`, `elan-pdf-processor`).

### Vérification

```bash
docker compose ps
docker logs -f elan-watchdog
journalctl -f CONTAINER_NAME=elan-watchdog
```

## ⚙️ Configuration

- **Montages CIFS distants** (presses, RIP) : `config/elan-samba-mnt.yml` — voir [docs/elan-samba-mnt.md](docs/elan-samba-mnt.md)
- **Partages locaux exposés** (dépôt/retrait) : `config/elan-samba-share.yml`
- **Watchers** (hotfolders + pipeline d'actions) : `config/elan-watchdog.yml`

Schéma d'un watcher :

```yaml
watchers:
  - name: "mon-watcher"           # str, obligatoire
    description: "..."             # str, optionnel
    folder: /shares/entree/xxx      # str, obligatoire — créé automatiquement si absent
    patterns: ["*.pdf"]             # liste de globs fnmatch, défaut ["*"]
    stability_timeout: 300         # secondes max d'attente de stabilité du transfert
    stability_checks: 3            # nb de vérifications de taille identique requises
    cleanup_macos_junk: true       # supprime .DS_Store, ._*, etc.
    overwrite: false               # écrase les fichiers existants en destination
    actions:                       # pipeline d'actions, optionnel — voir ci-dessous
      - type: raster
        params: { resolution: 600 }
    destinations:                  # str ou liste de chemins
      - /mnts/XEROX-Iridesse/APLAT
```

Exemples complets combinant plusieurs actions (aplat, imposition, découpe, BAT, brochure, traceur...) : [docs/watcher_descriptions_examples.md](docs/watcher_descriptions_examples.md).

## 🎬 Actions disponibles

| Type YAML | Rôle en une phrase | Détails |
|---|---|---|
| `raster` | Rasterise un PDF (Ghostscript), CMYK/Gray/tons directs, sortie TIFF ou JPEG | [docs/actions/raster.md](docs/actions/raster.md) |
| `impose` ⚠️ | Impose un PDF avec calcul automatique des poses et repères de coupe — **en développement**, géométrie pas encore validée sur tous les cas réels | [docs/actions/impose.md](docs/actions/impose.md) |
| `adjust_mediabox` | Ajuste MediaBox/CropBox autour de la TrimBox (fonds perdus) | [docs/actions/adjust_mediabox.md](docs/actions/adjust_mediabox.md) |
| `add_trim_guide` | Ajoute repères visuels de coupe, plis, côtes (BAT) | [docs/actions/add_trim_guide.md](docs/actions/add_trim_guide.md) |
| `extract_cutting` | Sépare un PDF avec calque/tons de découpe en versions simulation + impression | [docs/actions/extract_cutting.md](docs/actions/extract_cutting.md) |
| `saddle_stitch_split` | Sépare couverture / intérieur pour piqûre à cheval | [docs/actions/saddle_stitch_split.md](docs/actions/saddle_stitch_split.md) |
| `perfect_binding_split` | Découpe en cahiers pour reliure dos carré collé | [docs/actions/perfect_binding_split.md](docs/actions/perfect_binding_split.md) |
| `print` | Envoie vers une imprimante CUPS (traceurs) | [docs/actions/print.md](docs/actions/print.md) |

Index complet : [docs/actions/](docs/actions/README.md).

## 📊 Monitoring

```bash
# Logs temps réel
docker logs -f elan-watchdog
journalctl -f CONTAINER_NAME=elan-watchdog

# État des containers
docker compose ps
docker stats
```

Chaque job traité écrit son propre journal dans `/shares/sortie/journaux/`.

## 💎 Version Premium

**ÉLAN Premium** ajoute par-dessus le PWS :
- 🌐 Interface Web complète (suivi jobs, imposition, planning)
- 📊 ERP de production (OF, BAT, besoins papier, pointages) — actions supplémentaires `duplicate_sheets`, `import_jdf`
- 👥 Multi-utilisateurs
- 🎨 Client proofing (BAT en ligne)
- 🤝 Support prioritaire

## 📜 Licence

GPLv3 — voir [LICENSE](LICENSE)

**Vous êtes libre de :**\
✓ Utiliser commercialement\
✓ Modifier le code\
✓ Distribuer

**À condition de :**\
✓ Partager vos modifications (copyleft)\
✓ Garder la même licence\
✓ Créditer l'auteur original
