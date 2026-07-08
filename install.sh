#!/bin/bash
# ============================================================================
# FILE: /install.sh
# VERSION : 17 - Corrections syntaxe POSIX + systemd mount
# ============================================================================

set -e

printf "%b\n" "
            \033[38;5;22m████████████████████████████\033[0m                \033[38;5;22m████████████\033[0m    \033[38;5;22m████████\033[0m    \033[38;5;22m████████\033[0m
          \033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m            \033[38;5;22m██████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m
        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m██████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m██████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
      \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m    \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
    \033[38;5;22m████\033[0m\033[38;5;46m████████████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m██████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m██\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m  \033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m  \033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m████████████████████████████████████████████████\033[0m    \033[38;5;22m████████████████\033[0m    \033[38;5;22m████████\033[0m
--------------------------------------------------------------------------------------------
                        L’automatisation qui franchit les obstacles
--------------------------------------------------------------------------------------------
"

# ----------------------------------------------------------------------------------
# Déterminer le vrai utilisateur et son dossier home
# ----------------------------------------------------------------------------------
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo "➡️  Utilisateur détecté : $REAL_USER"
echo "➡️  Home : $REAL_HOME"
echo ""

# ----------------------------------------------------------
# Vérifier les privilèges root (compatible POSIX)
# ----------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Ce script doit être exécuté en tant que root"
    echo "Utilisez : sudo ./install.sh"
    exit 1
fi

# Installer sudo si absent
if ! command -v sudo >/dev/null 2>&1; then
    echo "📦 Installation de sudo..."
    apt-get update
    apt-get install -y sudo
    echo ""
    echo "✅ sudo installé, relancez le script."
    echo "Utilisez : sudo ./install.sh"
    exit 1
fi

# ----------------------------------------------------------
# Mise à jour initiale du système
# ----------------------------------------------------------
echo "📦 Mise à jour des dépôts et du système..."
echo ""
apt-get update
apt-get upgrade -y

# ----------------------------------------------------------
# Installer screen si nécessaire
# ----------------------------------------------------------
if ! command -v screen >/dev/null 2>&1; then
    echo "📦 Installation de screen..."
    apt-get update && apt-get install -y screen
fi

# ----------------------------------------------------------
# Installer curl si nécessaire
# ----------------------------------------------------------
if ! command -v curl >/dev/null 2>&1; then
    echo "📦 Installation de curl..."
    apt-get update && apt-get install -y curl
fi

# ----------------------------------------------------------
# Installer unzip si nécessaire
# ----------------------------------------------------------
if ! command -v unzip >/dev/null 2>&1; then
    echo "📦 Installation de unzip..."
    apt-get update && apt-get install -y unzip
fi

# ----------------------------------------------------------
# Installer docker si nécessaire
# ----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "📦 Installation de Docker..."
    echo ""
    apt-get install -y ca-certificates curl gnupg lsb-release

    # Repo officiel Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
    $(lsb_release -cs) stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo ""
echo "Configuration du stockage..."
echo ""

USE_ISCSI=false
MOUNT_PATH="/data/elan"

if [ -f ./lun.yml ]; then
    echo "Mode : Stockage iSCSI"
    USE_ISCSI=true
    
    NAS_IP=$(grep 'nas_ip:' lun.yml | awk '{print $2}' | tr -d '"')
    IQN_SERVER=$(grep 'iqn_server:' lun.yml | awk '{print $2}' | tr -d '"')
    IQN_HOST=$(grep 'iqn_host:' lun.yml | awk '{print $2}' | tr -d '"')
    MOUNT_PATH=$(grep 'mount_path:' lun.yml | awk '{print $2}' | tr -d '"')
    FS=$(grep 'filesystem:' lun.yml | awk '{print $2}' | tr -d '"')
    
    # Valeurs par défaut
    test -z "$IQN_HOST" && IQN_HOST="iqn.2025-01.sph"
    test -z "$MOUNT_PATH" && MOUNT_PATH="/data/elan"
    test -z "$FS" && FS="ext4"
    
    echo "NAS IP: $NAS_IP"
    echo "IQN Server: $IQN_SERVER"
    echo "IQN Host: $IQN_HOST"
    echo "Mount: $MOUNT_PATH"
    echo ""
else
    echo "Mode : Stockage LOCAL"
    printf "Confirmer stockage local ? (o/N) "
    read -r REPLY
    echo ""
    case "$REPLY" in
        [Oo]*)
            echo "OK, stockage local"
            ;;
        *)
            echo "Installation annulée"
            exit 1
            ;;
    esac
fi

mkdir -p /opt/elan/config

if [ "$USE_ISCSI" = "true" ]; then
    if ! command -v iscsiadm >/dev/null 2>&1; then
        echo "📦 Installation du support iSCSI..."
        apt-get install -y open-iscsi
    fi
    
    INITIATOR_CONFIG="/etc/iscsi/initiatorname.iscsi"
    echo "Configuration IQN initiateur..."
    
    if [ -f "$INITIATOR_CONFIG" ]; then
        CURRENT_IQN=$(grep "InitiatorName=" "$INITIATOR_CONFIG" | cut -d'=' -f2)
        if [ "$CURRENT_IQN" != "$IQN_HOST" ]; then
            cp "$INITIATOR_CONFIG" "${INITIATOR_CONFIG}.backup-$(date +%Y%m%d-%H%M%S)"
            echo "InitiatorName=$IQN_HOST" > "$INITIATOR_CONFIG"
            systemctl restart iscsid open-iscsi 2>/dev/null || systemctl restart open-iscsi
            sleep 2
        fi
    else
        echo "InitiatorName=$IQN_HOST" > "$INITIATOR_CONFIG"
        systemctl restart iscsid open-iscsi 2>/dev/null || systemctl restart open-iscsi
        sleep 2
    fi
    
    # Désactiver connexion automatique à TOUS les targets
    echo "🔧 Configuration iSCSI : désactivation auto-login global..."
    if [ ! -f /etc/iscsi/iscsid.conf.backup ]; then
        cp /etc/iscsi/iscsid.conf /etc/iscsi/iscsid.conf.backup
    fi
    
    # Forcer node.startup = manual (pas automatic)
    if ! grep -q "^node.startup = manual" /etc/iscsi/iscsid.conf; then
        sed -i 's/^node.startup = automatic/node.startup = manual/' /etc/iscsi/iscsid.conf
        # Si la ligne n'existe pas, l'ajouter
        if ! grep -q "^node.startup" /etc/iscsi/iscsid.conf; then
            cat >> /etc/iscsi/iscsid.conf << EOFISCSI

# SPH: Disable auto-login to all targets (use systemd mount instead)
node.startup = manual
node.conn[0].timeo.login_timeout = 15
node.conn[0].timeo.logout_timeout = 15
node.session.timeo.replacement_timeout = 120
EOFISCSI
        fi
        systemctl restart iscsid
        sleep 2
    fi
    
    ALREADY_CONNECTED=false
    ALREADY_MOUNTED=false
    
    if iscsiadm -m session 2>/dev/null | grep -q "$IQN_SERVER"; then
        ALREADY_CONNECTED=true
    fi
    
    if mount | grep -q "$MOUNT_PATH"; then
        ALREADY_MOUNTED=true
    fi
    
    if [ "$ALREADY_CONNECTED" = "true" ] && [ "$ALREADY_MOUNTED" = "true" ]; then
        echo "✅ iSCSI déjà opérationnel"
    else
        if [ "$ALREADY_CONNECTED" = "false" ]; then
            echo "Vérification NAS..."
            if ! ping -c 2 -W 3 "$NAS_IP" >/dev/null 2>&1; then
                echo "⚠️  Le NAS ne répond pas"
                printf "Continuer ? (o/N) "
                read -r REPLY
                echo ""
                case "$REPLY" in
                    [Oo]*)
                        echo "OK, on continue"
                        ;;
                    *)
                        exit 1
                        ;;
                esac
            fi
            
            echo "Découverte iSCSI..."
            iscsiadm -m discovery -t st -p "$NAS_IP"
            
            echo "Connexion au LUN SPH..."
            iscsiadm -m node -T "$IQN_SERVER" -p "$NAS_IP:3260" --login 2>&1 | grep -v "fe80:" || true
            sleep 3
        fi
        
        DEVICE_PATTERN=$(ls /dev/disk/by-path/ 2>/dev/null | grep "iscsi-$IQN_SERVER" | head -n 1)
        if [ -z "$DEVICE_PATTERN" ]; then
            echo "❌ Device iSCSI introuvable"
            exit 1
        fi
        
        DEVICE="/dev/disk/by-path/$DEVICE_PATTERN"
        echo "✅ Device détecté : $DEVICE"
        
        if ! blkid "$DEVICE" >/dev/null 2>&1; then
            printf "⚠️  Formater en $FS ? (o/N) "
            read -r REPLY
            echo ""
            case "$REPLY" in
                [Oo]*)
                    mkfs.$FS -F "$DEVICE"
                    ;;
                *)
                    exit 1
                    ;;
            esac
        fi
        
        mkdir -p "$MOUNT_PATH"
        
        # ✅ Créer les services systemd pour un boot robuste
        echo "📝 Création de la configuration systemd iSCSI..."
        
        # Service de connexion iSCSI
        cat > /etc/systemd/system/iscsi-sph-login.service << EOFSVC1
[Unit]
Description=Connexion iSCSI LUN SPH
After=network-online.target iscsid.service
Requires=iscsid.service
Before=data-elan.mount

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iscsiadm -m node -T $IQN_SERVER -p $NAS_IP:3260 --login
ExecStop=/usr/sbin/iscsiadm -m node -T $IQN_SERVER -p $NAS_IP:3260 --logout
TimeoutStartSec=60
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFSVC1

        # Service de vérification filesystem
        cat > /etc/systemd/system/iscsi-sph-fsck.service << EOFSVC2
[Unit]
Description=Vérification filesystem LUN SPH
After=iscsi-sph-login.service
Requires=iscsi-sph-login.service
Before=data-elan.mount

[Service]
Type=oneshot
RemainAfterExit=yes
# Attendre que le device apparaisse (max 30s)
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 30); do [ -b $DEVICE ] && break || sleep 1; done'
# Vérifier le filesystem (-p = correction auto des erreurs simples)
ExecStart=/usr/sbin/e2fsck -p $DEVICE
# Codes de sortie acceptables (0=OK, 1=erreurs corrigées, 2=reboot suggéré)
SuccessExitStatus=0 1 2
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOFSVC2

        # Fichier .mount avec chemin stable by-path
        MOUNT_UNIT_NAME="data-elan.mount"
        
        cat > /etc/systemd/system/"$MOUNT_UNIT_NAME" << EOFMOUNT
[Unit]
Description=LUN iSCSI SPH
After=iscsi-sph-fsck.service
Requires=iscsi-sph-login.service
Before=docker.service

[Mount]
What=$DEVICE
Where=$MOUNT_PATH
Type=$FS
Options=_netdev,nofail

[Install]
WantedBy=multi-user.target
EOFMOUNT

        # Activer tous les services
        systemctl daemon-reload
        systemctl enable iscsi-sph-login.service
        systemctl enable iscsi-sph-fsck.service
        systemctl enable "$MOUNT_UNIT_NAME"
        
        # Démarrer si pas déjà monté
        if [ "$ALREADY_MOUNTED" = "false" ]; then
            echo "🚀 Démarrage des services iSCSI..."
            systemctl start iscsi-sph-login.service
            sleep 2
            systemctl start iscsi-sph-fsck.service
            sleep 2
            systemctl start "$MOUNT_UNIT_NAME"
            sleep 2
            
            if mount | grep -q "$MOUNT_PATH"; then
                echo "✅ LUN monté avec succès via systemd"
            else
                echo "❌ Échec du montage"
                systemctl status iscsi-sph-login.service
                systemctl status iscsi-sph-fsck.service
                systemctl status "$MOUNT_UNIT_NAME"
                exit 1
            fi
        fi
    fi
    
    cat > /opt/elan/config/lun.conf << EOFCONF
nas_ip=$NAS_IP
iqn_server=$IQN_SERVER
iqn_host=$IQN_HOST
device=$DEVICE
mount_path=$MOUNT_PATH
filesystem=$FS
EOFCONF

    cat > /usr/local/bin/check-lun.sh << 'EOFSCRIPT'
#!/bin/bash
# check-lun.sh - Vérifie l'état du LUN iSCSI et étend le filesystem si nécessaire

CONF="/opt/elan/config/lun.conf"
LOG_FILE="/var/log/sph-lun-check.log"
STATUS_FILE="/var/run/sph-lun-status"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Charger la config
if [ ! -f "$CONF" ]; then
    log_message "ERROR: Config file not found: $CONF"
    exit 1
fi

. "$CONF"

# Vérifier la connexion iSCSI
if ! /usr/sbin/iscsiadm -m session 2>/dev/null | grep -q "$iqn_server"; then
    log_message "WARNING: LUN déconnecté, reconnexion..."
    if /usr/sbin/iscsiadm -m node -T "$iqn_server" --login >/dev/null 2>&1; then
        log_message "INFO: Reconnexion réussie"
        sleep 2
    else
        log_message "ERROR: Échec de la reconnexion"
        echo "status=error" > "$STATUS_FILE"
        exit 1
    fi
fi

# Vérifier que le device existe
if [ ! -b "$device" ]; then
    log_message "ERROR: Device $device introuvable"
    echo "status=error" > "$STATUS_FILE"
    exit 1
fi

# Obtenir les tailles
DEVICE_SIZE=$(blockdev --getsize64 "$device" 2>/dev/null)
if [ -z "$DEVICE_SIZE" ] || [ "$DEVICE_SIZE" -eq 0 ]; then
    log_message "ERROR: Impossible de lire la taille du device"
    echo "status=error" > "$STATUS_FILE"
    exit 1
fi

# Taille du filesystem (en bytes)
FS_SIZE=$(df --output=size "$mount_path" 2>/dev/null | tail -1)
if [ -z "$FS_SIZE" ]; then
    log_message "ERROR: Impossible de lire la taille du filesystem"
    echo "status=error" > "$STATUS_FILE"
    exit 1
fi
FS_SIZE=$((FS_SIZE * 1024))

# Convertir en Go pour affichage
DEVICE_SIZE_GB=$((DEVICE_SIZE / 1024 / 1024 / 1024))
FS_SIZE_GB=$((FS_SIZE / 1024 / 1024 / 1024))

# Vérifier si extension nécessaire (avec marge de 1 Go)
DIFF=$((DEVICE_SIZE - FS_SIZE))
DIFF_GB=$((DIFF / 1024 / 1024 / 1024))

if [ "$DIFF_GB" -ge 1 ]; then
    log_message "INFO: Extension détectée - Device: ${DEVICE_SIZE_GB}Go, FS: ${FS_SIZE_GB}Go, Diff: ${DIFF_GB}Go"
    
    # Extension du filesystem selon le type
    case "$filesystem" in
        ext4|ext3|ext2)
            log_message "INFO: Extension ext4 en cours..."
            if resize2fs "$device" >/dev/null 2>&1; then
                NEW_FS_SIZE=$(df --output=size "$mount_path" 2>/dev/null | tail -1)
                NEW_FS_SIZE_GB=$((NEW_FS_SIZE / 1024 / 1024))
                log_message "SUCCESS: Filesystem étendu à ${NEW_FS_SIZE_GB}Go"
                echo "status=extended" > "$STATUS_FILE"
                echo "old_size_gb=$FS_SIZE_GB" >> "$STATUS_FILE"
                echo "new_size_gb=$NEW_FS_SIZE_GB" >> "$STATUS_FILE"
            else
                log_message "ERROR: Échec de resize2fs"
                echo "status=error" > "$STATUS_FILE"
                exit 1
            fi
            ;;
        xfs)
            log_message "INFO: Extension XFS en cours..."
            if xfs_growfs "$mount_path" >/dev/null 2>&1; then
                NEW_FS_SIZE=$(df --output=size "$mount_path" 2>/dev/null | tail -1)
                NEW_FS_SIZE_GB=$((NEW_FS_SIZE / 1024 / 1024))
                log_message "SUCCESS: Filesystem étendu à ${NEW_FS_SIZE_GB}Go"
                echo "status=extended" > "$STATUS_FILE"
                echo "old_size_gb=$FS_SIZE_GB" >> "$STATUS_FILE"
                echo "new_size_gb=$NEW_FS_SIZE_GB" >> "$STATUS_FILE"
            else
                log_message "ERROR: Échec de xfs_growfs"
                echo "status=error" > "$STATUS_FILE"
                exit 1
            fi
            ;;
        *)
            log_message "WARNING: Type de filesystem non supporté pour extension auto: $filesystem"
            echo "status=warning" > "$STATUS_FILE"
            echo "message=Extension manuelle requise" >> "$STATUS_FILE"
            ;;
    esac
else
    # Tout est OK
    echo "status=ok" > "$STATUS_FILE"
    echo "device_size_gb=$DEVICE_SIZE_GB" >> "$STATUS_FILE"
    echo "fs_size_gb=$FS_SIZE_GB" >> "$STATUS_FILE"
fi

exit 0
EOFSCRIPT
    chmod +x /usr/local/bin/check-lun.sh

else
    mkdir -p "$MOUNT_PATH"
    chmod 755 "$MOUNT_PATH"
    cat > /opt/elan/config/lun.conf << EOFCONF
mode=local
mount_path=$MOUNT_PATH
EOFCONF
fi

# ----------------------------------------------------------
# Téléchargement de l'archive et décompression
# ----------------------------------------------------------
echo ""
echo "📦 Installation/Mise à jour du code ÉLAN-Core..."
echo ""

# ✅ Arrêter les containers avant la mise à jour
if command -v docker >/dev/null 2>&1 && [ -f /opt/elan/docker/docker-compose.yml ]; then
    echo "⏸️  Arrêt des containers..."
    echo ""
    docker compose -f /opt/elan/docker/docker-compose.yml down || true
fi

# ✅ Backup de la config si elle existe
if [ -d /opt/elan/config ]; then
    cp -r /opt/elan/config /tmp/elan-core-config-backup
fi

# ✅ Suppression propre
rm -rf /opt/elan/app /opt/elan/docker /opt/elan/scripts
# ⚠️ On ne supprime PAS /opt/elan/config car il contient lun.conf

# ✅ Décompression
unzip -oq install.zip -d /tmp/sph-install
mkdir -p /opt/elan

# ✅ Copie sélective (on ne touche pas à config/)
if [ -d /tmp/sph-install/elan-core/app ]; then
    cp -r /tmp/sph-install/elan-core/app /opt/elan/
fi

if [ -d /tmp/sph-install/elan-core/docker ]; then
    cp -r /tmp/sph-install/elan-core/docker /opt/elan/
fi

if [ -d /tmp/sph-install/elan-core/scripts ]; then
    cp -r /tmp/sph-install/elan-core/scripts /opt/elan/
fi

# ✅ Merge de config (écrasement automatique en Phase 0)
if [ -d /tmp/sph-install/elan-core/config ]; then
    mkdir -p /opt/elan/config

    echo "📋 Copie des fichiers de configuration..."
    echo ""

    # Copie les nouveaux fichiers de config
    for config_file in /tmp/sph-install/elan-core/config/*.yml; do
        [ -f "$config_file" ] || continue  # Skip si pas de fichiers .yml
        
        filename=$(basename "$config_file")
        target="/opt/elan/config/$filename"
        
        # Sauter lun.conf (géré par le script)
        [ "$filename" = "lun.conf" ] && continue
        
        # Backup si le fichier existe
        if [ -f "$target" ]; then
            cp "$target" "${target}.backup-$(date +%Y%m%d-%H%M%S)"
            echo "   💾 $filename : backup créé"
        fi
        
        # Copie
        cp "$config_file" "$target"
        echo "   ✅ $filename copié"
        echo ""
    done
fi

cp /tmp/sph-install/install_backend.sh /tmp
rm -rf /tmp/sph-install
rm -f install.zip

# ----------------------------------------------------------
# Lancement du script backend dans screen
# ----------------------------------------------------------
SESSION_NAME="ELAN-install"
BACKEND_SCRIPT="/tmp/install_backend.sh"

# Kill ancienne session screen si elle existe
if screen -list | grep -q "$SESSION_NAME"; then
    screen -S "$SESSION_NAME" -X quit
fi

chmod +x "$BACKEND_SCRIPT"

echo "🚀 Lancement du script d'installation backend..."
echo ""
screen -L -Logfile /tmp/sph-install.log \
    -dmS "$SESSION_NAME" bash -c "$BACKEND_SCRIPT; exec bash"
echo "➡️  Screen lancé : $SESSION_NAME"
echo "➡️  Log : cat /tmp/sph-install.log"
echo ""
echo "⏳ L'installation continue en arrière-plan."
echo ""
echo "➡️  Pour suivre la progression : sudo screen -R $SESSION_NAME"
echo ""

# ----------------------------------------------------------
# MOTD avec couleurs
# ----------------------------------------------------------
cat > /etc/profile.d/sph-motd.sh << 'EOFMOTD'
#!/bin/bash
test -z "$PS1" && return

# --- INFOS SYSTEME ---
IP_ADDR=$(hostname -I | awk '{print $1}')
UPTIME=$(uptime -p)
LOAD=$(cut -d " " -f1-3 /proc/loadavg)
RAM_USED=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
MDNS_NAME="$(hostname).local"
CONF="/opt/elan/config/lun.conf"
STATUS_FILE="/var/run/sph-lun-status"

if [ -f "$CONF" ]; then
    . "$CONF"
else
    device="N/A"
    mount_path="/data/elan"
fi

# Détection machine
if [ -f /sys/class/dmi/id/product_name ]; then
    MACHINE=$(cat /sys/class/dmi/id/product_name)
else
    MACHINE="Inconnue"
fi

# Docker containers actifs + inactifs
if command -v docker >/dev/null 2>&1; then
    DOCKER_ACTIVE=$(docker ps --format " - {{.Names}} ({{.Status}})" 2>/dev/null)
    test -z "$DOCKER_ACTIVE" && DOCKER_ACTIVE="Aucun conteneur actif."
    DOCKER_INACTIVE=$(docker ps -a --filter "status=exited" --format " - {{.Names}} ({{.Status}})" 2>/dev/null)
    test -z "$DOCKER_INACTIVE" && DOCKER_INACTIVE="Aucun conteneur inactif."
else
    DOCKER_ACTIVE="Docker non installé."
    DOCKER_INACTIVE=""
fi

# Exécuter check-lun.sh via sudo sans mot de passe (si mode iSCSI)
LUN_STATUS_MSG=""
if [ -f "$CONF" ] && grep -q "iqn_server" "$CONF" 2>/dev/null; then
    # Mode iSCSI détecté
    if command -v sudo >/dev/null 2>&1; then
        # Exécuter le check (silencieux)
        sudo /usr/local/bin/check-lun.sh >/dev/null 2>&1
        
        # Lire le status
        if [ -f "$STATUS_FILE" ]; then
            . "$STATUS_FILE"
            
            case "$status" in
                extended)
                    LUN_STATUS_MSG="LUN étendu : ${old_size_gb}Go -> ${new_size_gb}Go"
                    ;;
                warning)
                    LUN_STATUS_MSG="ATTENTION : $message"
                    ;;
                error)
                    LUN_STATUS_MSG="ERREUR : Vérifier /var/log/sph-lun-check.log"
                    ;;
            esac
        fi
    fi
fi

if [ -b "$device" ]; then
    DEVICE_SIZE=$(blockdev --getsize64 "$device" 2>/dev/null || echo "0")
    if [ -d "$mount_path" ]; then
        USED=$(df -h "$mount_path" --output=used 2>/dev/null | tail -1 || echo "N/A")
        FREE=$(df -h "$mount_path" --output=avail 2>/dev/null | tail -1 || echo "N/A")
    else
        USED="N/A"
        FREE="N/A"
    fi
else
    DEVICE_SIZE="0"
    USED="N/A"
    FREE="N/A"
fi

printf "%b\n" "
            \033[38;5;22m████████████████████████████\033[0m                \033[38;5;22m████████████\033[0m    \033[38;5;22m████████\033[0m    \033[38;5;22m████████\033[0m
          \033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m            \033[38;5;22m██████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m
        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m██████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m██████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
      \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m    \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
    \033[38;5;22m████\033[0m\033[38;5;46m████████████\033[0m\033[38;5;22m██\033[0m  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
  \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m        \033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m██████\033[0m\033[38;5;46m██████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m██\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████████████████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m  \033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m  \033[38;5;22m██\033[0m\033[38;5;46m████\033[0m\033[38;5;22m████\033[0m
\033[38;5;22m████████████████████████████████████████████████\033[0m    \033[38;5;22m████████████████\033[0m    \033[38;5;22m████████\033[0m
--------------------------------------------------------------------------------------------
                        L’automatisation qui franchit les obstacles
--------------------------------------------------------------------------------------------
"

printf "\033[36mMachine détectée :\033[0m   $MACHINE\n"
printf "\033[36mNom mDNS :\033[0m           $MDNS_NAME\n"
printf "\033[36mIP locale :\033[0m          $IP_ADDR\n"
printf "\033[36mUptime :\033[0m             $UPTIME\n"
printf "\033[36mCharge CPU :\033[0m         $LOAD\n"
printf "\033[36mRAM utilisée :\033[0m       $RAM_USED\n"
echo ""
printf "\033[36m[LUN iSCSI ÉLAN]\033[0m\n"
printf "\033[36mDevice :\033[0m             $device\n"
printf "\033[36mTaille :\033[0m             $(numfmt --to=iec "$DEVICE_SIZE" 2>/dev/null || echo "N/A")\n"
printf "\033[36mUtilisé :\033[0m            $USED\n"
printf "\033[36mLibre :\033[0m              $FREE\n"

# Afficher le message de status du LUN si présent
if [ -n "$LUN_STATUS_MSG" ]; then
    echo ""
    printf "\033[33m*** $LUN_STATUS_MSG ***\033[0m\n"
fi

echo ""
printf "\033[33mConteneurs Docker actifs :\033[0m\n"
echo "$DOCKER_ACTIVE"
echo ""
printf "\033[31mConteneurs Docker inactifs :\033[0m\n"
echo "$DOCKER_INACTIVE"
echo ""
EOFMOTD

chmod +x /etc/profile.d/sph-motd.sh

# Configuration sudo pour permettre check-lun.sh sans mot de passe
echo "Configuration sudo pour check-lun.sh..."
cat > /etc/sudoers.d/sph-check-lun << EOFSUDO
# Permettre à tous les users d'exécuter check-lun.sh sans mot de passe
ALL ALL=(ALL) NOPASSWD: /usr/local/bin/check-lun.sh
EOFSUDO

chmod 440 /etc/sudoers.d/sph-check-lun

echo ""
echo "✅ Installation initiale terminée"
echo ""