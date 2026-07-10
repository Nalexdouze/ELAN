#!/bin/bash
# ============================================================================
# FILE: /opt/elan/scripts/purge_elan_storage.sh
# Purge du genstore (tickets PWS) et des dossiers de sortie, pilotée par
# config/elan-purge.yml. Complète la purge immédiate faite à la suppression
# manuelle d'un ticket (pws_api.py, delete_pws_job) — ce script couvre tout
# ce qui n'a pas été supprimé à la main.
#
# Usage : purge_elan_storage.sh <BETA|PROD|PUBLIC> (label passé par
# install_backend.sh/install.sh, même convention que backup_elan_erp_db.sh).
# Sur PUBLIC : purge du genstore immédiate et inconditionnelle (filet de
# sécurité — cleanup_job() y fait déjà le nettoyage en temps réel, contrairement
# à BETA/PROD où cleanup_job() est neutralisée depuis le 2026-07-10).
# À exécuter par cron (voir install_backend.sh).
# ============================================================================

set -euo pipefail

ENV_LABEL="${1:-UNKNOWN}"
GENSTORE_ROOT="/data/elan/genstore"
SORTIE_ROOT="/data/elan/shares/sortie"
CONFIG="/opt/elan/config/elan-purge.yml"

yaml_int() {
    # yaml_int <clé> <valeur par défaut>
    local key="$1" default="$2" value
    value=$(grep -E "^\s*${key}:" "$CONFIG" 2>/dev/null | head -n1 | awk -F: '{print $2}' | tr -d ' "')
    [[ "$value" =~ ^[0-9]+$ ]] && echo "$value" || echo "$default"
}

GENSTORE_RETENTION_HOURS=$(yaml_int genstore_retention_hours 720)

TOTAL_FREED_KB=0
TOTAL_COUNT=0

purge_dir() {
    # purge_dir <dossier> <label log>
    local dir="$1"
    local size_kb
    size_kb=$(du -sk "$dir" 2>/dev/null | awk '{print $1}')
    rm -rf "$dir"
    TOTAL_FREED_KB=$((TOTAL_FREED_KB + ${size_kb:-0}))
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    echo "🗑️  Purgé [$ENV_LABEL] : $dir (${size_kb:-0} Ko)"
}

# ----------------------------------------------------------
# Genstore
# ----------------------------------------------------------
if [ -d "$GENSTORE_ROOT" ]; then
    if [ "$ENV_LABEL" = "PUBLIC" ]; then
        echo "🧹 Genstore [$ENV_LABEL] : purge immédiate et inconditionnelle"
        for job_dir in "$GENSTORE_ROOT"/job_*; do
            [ -d "$job_dir" ] || continue
            purge_dir "$job_dir"
        done
    else
        echo "🧹 Genstore [$ENV_LABEL] : purge des dossiers > ${GENSTORE_RETENTION_HOURS}h"
        while IFS= read -r job_dir; do
            purge_dir "$job_dir"
        done < <(find "$GENSTORE_ROOT" -maxdepth 1 -type d -name "job_*" -mmin "+$((GENSTORE_RETENTION_HOURS * 60))")
    fi
fi

# ----------------------------------------------------------
# Dossiers de sortie (règles "sous-chemin|heures" dans elan-purge.yml)
# ----------------------------------------------------------
if [ -d "$SORTIE_ROOT" ]; then
    while IFS= read -r rule; do
        [ -z "$rule" ] && continue
        sub_path="${rule%%|*}"
        retention_hours="${rule##*|}"
        [[ "$retention_hours" =~ ^[0-9]+$ ]] || continue

        target="$SORTIE_ROOT/$sub_path"
        [ -d "$target" ] || continue

        echo "🧹 Sortie [$ENV_LABEL] : $sub_path (> ${retention_hours}h)"
        while IFS= read -r file; do
            size_kb=$(du -k "$file" 2>/dev/null | awk '{print $1}')
            rm -f "$file"
            TOTAL_FREED_KB=$((TOTAL_FREED_KB + ${size_kb:-0}))
            TOTAL_COUNT=$((TOTAL_COUNT + 1))
            echo "🗑️  Purgé [$ENV_LABEL] : $file (${size_kb:-0} Ko)"
        done < <(find "$target" -type f -mmin "+$((retention_hours * 60))")
    done < <(awk '/^sortie_rules:/{flag=1;next} /^[a-zA-Z]/{flag=0} flag' "$CONFIG" | grep -oP '(?<=- ").*(?=")')
fi

echo "✅ Purge [$ENV_LABEL] terminée : $TOTAL_COUNT élément(s), $((TOTAL_FREED_KB / 1024)) Mo libérés"
