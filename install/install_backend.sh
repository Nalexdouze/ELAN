# ============================================================================
# FILE: /opt/elan/install_backend.sh
# VERSION : 6
# ============================================================================

#!/bin/bash

echo "🛠️  Installation backend en cours…"
sleep 3

WORKDIR="/opt/elan"

# ----------------------------------------------------------
# Installation les dépendances
# ----------------------------------------------------------

echo "📦 Installation de dépendances..."
apt-get update && apt-get upgrade -y

# ----------------------------------------------------------
# Installation et configuration de Chrony (NTP)
# ----------------------------------------------------------
echo ""
echo "⏰ Installation et configuration de Chrony (synchronisation temps)..."
echo ""

if ! command -v chronyc > /dev/null 2>&1; then
    echo "📦 Installation de Chrony..."
    apt-get install -y chrony
else
    echo "✔️  Chrony est déjà installé."
fi

# Activer et démarrer Chrony
systemctl enable chrony
systemctl restart chrony

# Vérifier la synchronisation
sleep 2
if chronyc tracking | grep -q "Leap status"; then
    echo "✅ Chrony actif et synchronisé"
    chronyc tracking | head -3
else
    echo "⚠️  Chrony démarré mais sync en cours..."
fi

echo ""

# ----------------------------------------------------------
# Installation et configuration de Avahi (mDNS)
# ----------------------------------------------------------
echo ""
echo "📡 Installation et configuration du service mDNS (Avahi)..."
echo ""

# Installer Avahi s'il n'est pas déjà présent
if ! command -v avahi-daemon > /dev/null 2>&1; then
    echo "📦 Installation d'Avahi..."
    apt-get install -y avahi-daemon avahi-utils
else
    echo "✔️  Avahi est déjà installé."
fi

# Activer + démarrer Avahi
systemctl enable avahi-daemon
systemctl restart avahi-daemon

# ----------------------------------------------------------
# Annonce mDNS de l'hôte
# ----------------------------------------------------------
echo "🛠️  Définition du mDNS : $(hostname).local"

hostnamectl set-hostname "$(hostname)"

# Avahi doit connaître le nom
cat <<EOF >/etc/avahi/avahi-daemon.conf
[server]
host-name=$(hostname)
domain-name=local
use-ipv4=yes
use-ipv6=no

[wide-area]
enable-wide-area=yes

[publish]
publish-addresses=yes
publish-hinfo=yes
publish-workstation=yes
EOF

systemctl restart avahi-daemon

# ----------------------------------------------------------
# Annonce mDNS du service SMB (Samba dans le conteneur)
# ----------------------------------------------------------
AVAHI_SERVICE_FILE="/etc/avahi/services/samba.service"

echo "🛠️  Création de l'annonce mDNS pour Samba..."
mkdir -p /etc/avahi/services

cat << 'EOF' > "$AVAHI_SERVICE_FILE"
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service>
    <type>_smb._tcp</type>
    <port>445</port>
  </service>
</service-group>
EOF

systemctl restart avahi-daemon

# ----------------------------------------------------------
# Vérification de l'annonce
# ----------------------------------------------------------
echo "🔍 Vérification de l'annonce mDNS..."
sleep 2

if avahi-browse -rt _smb._tcp | grep -q "$(hostname)"; then
    echo "✅ Service SMB annoncé avec succès via mDNS !"
    echo "   → Visible dans le Finder / Réseau / '$(hostname)'"
    echo "   → Accessible via : smb://$(hostname).local"
else
    echo "⚠️ L'annonce mDNS ne semble pas active."
    echo "   Vérifiez Avahi avec : systemctl status avahi-daemon"
fi

echo ""


# ----------------------------------------------------------
# Installation du Core
# ----------------------------------------------------------

echo "🚀 Configuration d'ÉLAN-Core"


# ----------------------------------------------------------
# Configuration automatique journald depuis docker-compose
# ----------------------------------------------------------
echo "📦 Configuration des logs journald pour les containers..."

JOURNALD_DIR="/etc/systemd/journald.conf.d"
COMPOSE_FILE="$WORKDIR/docker/docker-compose.yml"

mkdir -p "$JOURNALD_DIR"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "⚠️  docker-compose.yml introuvable, skip config journald"
else
    # Extraction des container_name depuis docker-compose.yml
    # Exclut les lignes commentées avec #
    container_names=$(grep -v '^\s*#' "$COMPOSE_FILE" | grep 'container_name:' | awk '{print $2}')
    
    if [ -z "$container_names" ]; then
        echo "⚠️  Aucun container détecté dans docker-compose.yml"
    else
        echo "   Containers détectés : $(echo $container_names | tr '\n' ' ')"
        
        for container in $container_names; do
            CONF_FILE="$JOURNALD_DIR/${container}.conf"
            
            if [ -f "$CONF_FILE" ]; then
                echo "   ⏭️  $container : config existe déjà"
            else
                echo "   ✅ $container : création de la config"
                cat <<EOF > "$CONF_FILE"
[Journal]
SystemMaxUse=100M
SystemMaxFileSize=10M
MaxRetentionSec=1month
EOF
            fi
        done
    fi
fi

# ✅ Créer la structure de données (seulement si elle n'existe pas)
mkdir -p /data/elan/{genstore,mounts,shares}

# ✅ Vérifier si /data/elan/mounts est déjà un bind mount
if ! mount | grep -q "on /data/elan/mounts type"; then
    echo "📌 Configuration du bind mount rshared pour /data/elan/mounts"
    mount --bind /data/elan/mounts /data/elan/mounts
    mount --make-rshared /data/elan/mounts

    # ✅ Ajouter au fstab pour persistance (si pas déjà présent)
    if ! grep -q "/data/elan/mounts" /etc/fstab; then
        echo "/data/elan/mounts /data/elan/mounts none bind,rshared 0 0" >> /etc/fstab
    fi
else
    echo "✅ Le bind mount rshared existe déjà"
    # ✅ S'assurer qu'il est bien rshared (au cas où)
    mount --make-rshared /data/elan/mounts 2>/dev/null || true
fi

systemctl restart systemd-journald

# docker
cd "$WORKDIR" || exit 1

# ----------------------------------------------------------
# Migration vers la nouvelle architecture
# ----------------------------------------------------------
echo "🔄 Vérification de la migration..."

OLD_CONTAINERS=("core_samba_mnt" "core_samba_share" "core_watchdog_hf")
MIGRATION_NEEDED=false

for container in "${OLD_CONTAINERS[@]}"; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
        MIGRATION_NEEDED=true
        break
    fi
done

if [ "$MIGRATION_NEEDED" = true ]; then
    echo ""
    echo "⚠️  Anciens containers détectés :"
    docker ps -a --filter "name=core_" --format "  - {{.Names}} ({{.Status}})"
    echo ""
    echo "🔄 Migration vers la nouvelle architecture (elan-*) recommandée"
    echo ""
    read -p "Supprimer les anciens containers ? (o/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Oo]$ ]]; then
        echo "🛑 Arrêt et suppression des anciens containers..."
        
        for container in "${OLD_CONTAINERS[@]}"; do
            if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
                echo "  - Suppression de $container"
                docker stop "$container" 2>/dev/null || true
                docker rm "$container" 2>/dev/null || true
            fi
        done
        
        # Suppression des anciennes images (optionnel)
        echo ""
        read -p "Supprimer aussi les anciennes images Docker ? (o/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Oo]$ ]]; then
            docker images --format "{{.Repository}}:{{.Tag}}" | grep "^docker-core_" | xargs -r docker rmi 2>/dev/null || true
            echo "✅ Anciennes images supprimées"
        fi
        
        echo ""
        echo "✅ Migration terminée"
        echo ""
    else
        echo ""
        echo "⏭️  Migration ignorée"
        echo "⚠️  ATTENTION : Risque de conflits entre anciens et nouveaux containers"
        echo "   (ports, volumes, logs journald...)"
        echo ""
    fi
fi

# ----------------------------------------------------------
# Construction et démarrage
# ----------------------------------------------------------

# ✅ Vérifier si les containers existent déjà
REBUILD_NEEDED=false
if ! docker ps -a --format '{{.Names}}' | grep -q "elan-samba-mnt"; then
    REBUILD_NEEDED=true
    echo "🔨 Construction des images Docker..."
    docker compose -f "$WORKDIR/docker/docker-compose.yml" build build-base
    docker compose -f "$WORKDIR/docker/docker-compose.yml" build build-base-heavy
    docker compose -f "$WORKDIR/docker/docker-compose.yml" build
else
    echo "📦 Images Docker détectées"
    # ✅ Rebuild seulement si le code a changé
    read -p "Voulez-vous reconstruire les images ? (o/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Oo]$ ]]; then
        echo "🔨 Reconstruction des images Docker..."
        docker compose -f "$WORKDIR/docker/docker-compose.yml" build build-base
        docker compose -f "$WORKDIR/docker/docker-compose.yml" build build-base-heavy
        docker compose -f "$WORKDIR/docker/docker-compose.yml" build
    fi
fi

# ----------------------------------------------------------
# Cron de surveillance mDNS (redémarre Avahi s'il ne répond plus)
# ----------------------------------------------------------
echo "📡 Configuration de la surveillance mDNS..."

chmod +x /opt/elan/scripts/check_mdns.sh

MDNS_CRON_LINE="*/5 * * * * /opt/elan/scripts/check_mdns.sh >> /var/log/elan-mdns-watchdog.log 2>&1"
( crontab -l 2>/dev/null | grep -vF "check_mdns.sh" ; echo "$MDNS_CRON_LINE" ) | crontab -
echo "✅ Cron mDNS installé (vérification toutes les 5 minutes)"

# ✅ Démarrage/redémarrage propre
echo "🚀 Démarrage des services..."
docker compose -f "$WORKDIR/docker/docker-compose.yml" up -d

echo ""
echo "----------------------------------------------------"
echo "🎉 Installation terminée !"
echo "🌐 Interface ÉLAN : http://$(hostname).local"
echo "----------------------------------------------------"
echo ""

# ----------------------------------------------------------
# Configuration des groupes utilisateur
# ----------------------------------------------------------
echo "👤 Configuration de l'utilisateur $REAL_USER..."

# Récupérer l'utilisateur réel (celui qui a lancé sudo)
REAL_USER="${SUDO_USER:-$USER}"

if [ "$REAL_USER" != "root" ]; then
    # Ajouter aux groupes nécessaires
    usermod -aG docker,systemd-journal,adm,disk "$REAL_USER"
    echo "✅ $REAL_USER ajouté aux groupes : docker, systemd-journal, adm, disk"
    echo ""
    echo "⚠️  IMPORTANT : Déconnectez-vous et reconnectez-vous pour que les groupes soient actifs"
    echo "   Ou utilisez : su - $REAL_USER"
else
    echo "⚠️  Utilisateur root détecté, skip configuration groupes"
fi

echo ""
echo "📊 État des services :"
docker compose -f "$WORKDIR/docker/docker-compose.yml" ps
echo ""