# `elan-samba-mnt` — client CIFS

Container `elan-samba-mnt`. Monte en CIFS les partages distants nécessaires au PWS (Fiery/presses, RIP, découpe...).

Code : `install/elan-core/app/elan-samba-mnt.py`. Configuration : `config/elan-samba-mnt.yml`.

## Configuration

```yaml
mounts:
  - name: Fiery XEROX
    remote: "//192.168.34.11/HotFolder"
    mount_point: "/mnts/XEROX-Iridesse"
    username: "username"
    password: "password"
    options: "rw,vers=3.0"

  - name: RIP-GMG
    remote: "//192.168.34.12/HotFolder"
    mount_point: "/mnts/RIP-GMG"
    username: "username"
    password: "password"
    options: "rw,vers=3.0,noperm"
```

| Champ | Rôle |
|---|---|
| `name` | Libellé utilisé dans les logs |
| `remote` | Chemin UNC du partage distant (`//ip/partage`) |
| `mount_point` | Point de montage local, sous `/mnts/` |
| `username` / `password` | Identifiants du compte de service Samba distant |
| `options` | Options `mount -t cifs` additionnelles (ex. `vers=3.0`, `noperm`) |

## Fonctionnement

- Un **thread de surveillance dédié par montage** (`monitor_mount`), boucle infinie, vérification toutes les **60 secondes**.
- Montage initial :
  ```
  mount -t cifs <remote> <mount_point> \
    -o username=...,password=...,file_mode=0777,dir_mode=0777,uid=0,gid=0[,<options>]
  ```
- **Nettoyage des montages corrompus** (`cleanup_stale_mount`) : détecte un point de montage qui serait un fichier au lieu d'un dossier, ou un dossier existant mais illisible (démontage forcé `umount -l`, lazy unmount).
- **Backoff exponentiel** par point de montage en cas d'échec répété : 30s → 1min → 2min → 5min → 10min → 30min → plafond 1h. Réinitialisé au premier succès suivant.
- Démontage propre de tous les montages actifs sur `SIGINT`/`SIGTERM`.
- La boucle principale surveille elle-même les threads de montage : redémarre tout thread mort.

## Diagnostiquer une coupure

```bash
# Logs du container
docker logs -f elan-samba-mnt
journalctl -f CONTAINER_NAME=elan-samba-mnt

# État des montages sur l'hôte
mount | grep /mnts

# Tester le montage à la main
mount -t cifs //192.168.34.11/HotFolder /mnts/XEROX-Iridesse -o username=...,password=...,vers=3.0
```

Si un montage reste bloqué en échec malgré une remise en service du partage distant, vérifier le compteur de backoff : le prochain essai peut être différé jusqu'à 1h après plusieurs échecs consécutifs. Redémarrer le container force une nouvelle tentative immédiate :

```bash
docker compose restart elan-samba-mnt
```
