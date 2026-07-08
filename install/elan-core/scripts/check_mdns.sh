#!/bin/bash
# ============================================================================
# FILE: /opt/elan/scripts/check_mdns.sh
# Watchdog mDNS : vérifie qu'Avahi répond réellement (pas seulement que le
# process tourne) et redémarre avahi-daemon sinon. Corrige le cas vécu où,
# après un reboot ou une coupure, Avahi reste up mais ne répond plus.
# Silencieux si tout va bien (log uniquement en cas de problème).
# Exécuté périodiquement par cron (voir install_backend.sh).
# ============================================================================

set -uo pipefail

HOSTNAME_LOCAL="$(hostname).local"
LOG_TAG="[check_mdns]"
log() { echo "$(date '+%F %T') $LOG_TAG $1"; }

if ! systemctl is-active --quiet avahi-daemon; then
    log "❌ avahi-daemon inactif, redémarrage..."
    systemctl restart avahi-daemon
    exit 0
fi

if ! avahi-resolve -n4 "$HOSTNAME_LOCAL" > /dev/null 2>&1; then
    log "⚠️  $HOSTNAME_LOCAL ne répond plus au mDNS, redémarrage d'avahi-daemon..."
    systemctl restart avahi-daemon
    sleep 2
    if avahi-resolve -n4 "$HOSTNAME_LOCAL" > /dev/null 2>&1; then
        log "✅ mDNS rétabli après redémarrage."
    else
        log "❌ mDNS toujours en échec après redémarrage — vérification manuelle requise."
    fi
fi
