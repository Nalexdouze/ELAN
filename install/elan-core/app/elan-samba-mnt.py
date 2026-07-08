# ============================================================================
# FILE: /opt/elan/app/elan-samba-mnt.py
# VERSION : 2
# ============================================================================

import yaml
import time
import os
import subprocess
import logging
import signal
import sys
from datetime import datetime, timedelta
from threading import Thread, Lock

# Configuration
LOG_LEVEL = "DEBUG"
CONFIG_FILE = "/config/elan-samba-mnt.yml"

# Liste des points de montage actifs (pour démontage propre)
active_mounts = []
active_mounts_lock = Lock()

# Gestion des échecs de montage avec backoff exponentiel
mount_failures = {}  # {mount_point: {'count': X, 'last_attempt': datetime, 'next_retry': datetime}}
mount_failures_lock = Lock()

# Configuration du logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("elan-samba-mnt")

def load_config():
    """Chargement du fichier de configuration du service"""
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

def is_mounted(mount_point):
    """Vérifie si un point de montage est déjà actif"""
    try:
        result = subprocess.run(
            ["mountpoint", "-q", mount_point],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False

def cleanup_stale_mount(mount_point):
    """Nettoie un point de montage corrompu ou bloqué"""
    try:
        # Vérifier si c'est un fichier au lieu d'un dossier
        if os.path.exists(mount_point) and not os.path.isdir(mount_point):
            logger.warning(f"⚠️  {mount_point} est un fichier, suppression...")
            os.remove(mount_point)
            return True
        
        # Si c'est un dossier mais monté de façon corrompue
        if os.path.exists(mount_point) and not is_mounted(mount_point):
            # Vérifier si accessible
            try:
                os.listdir(mount_point)
            except OSError:
                logger.warning(f"⚠️  {mount_point} semble corrompu, tentative de lazy unmount...")
                subprocess.run(["umount", "-l", mount_point], capture_output=True)
                return True
        return True
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage de {mount_point}: {e}")
        return False

def get_retry_delay(mount_point):
    """Calcule le délai avant prochaine tentative (backoff exponentiel)"""
    with mount_failures_lock:
        if mount_point not in mount_failures:
            return 0  # Première tentative
        
        failure_info = mount_failures[mount_point]
        now = datetime.now()
        
        # Si la prochaine tentative n'est pas encore due
        if now < failure_info['next_retry']:
            return (failure_info['next_retry'] - now).total_seconds()
        
        return 0

def record_mount_failure(mount_point):
    """Enregistre un échec de montage et calcule le prochain délai"""
    with mount_failures_lock:
        now = datetime.now()
        
        if mount_point not in mount_failures:
            mount_failures[mount_point] = {
                'count': 1,
                'last_attempt': now,
                'next_retry': now + timedelta(seconds=30)  # 30 secondes pour la première tentative
            }
        else:
            failure_info = mount_failures[mount_point]
            failure_info['count'] += 1
            failure_info['last_attempt'] = now
            
            # Backoff exponentiel: 30s, 1min, 2min, 5min, 10min, 30min, max 1h
            delays = [30, 60, 120, 300, 600, 1800, 3600]
            delay_index = min(failure_info['count'] - 1, len(delays) - 1)
            delay = delays[delay_index]
            
            failure_info['next_retry'] = now + timedelta(seconds=delay)
            
            logger.warning(f"📊 [{mount_point}] Échec #{failure_info['count']} - Prochaine tentative dans {delay}s")

def reset_mount_failure(mount_point):
    """Réinitialise le compteur d'échecs après un succès"""
    with mount_failures_lock:
        if mount_point in mount_failures:
            logger.info(f"✅ [{mount_point}] Réinitialisation du compteur d'échecs")
            del mount_failures[mount_point]

def ensure_mount(m):
    """Monte un partage SMB distant avec gestion des échecs"""
    mount_point = m["mount_point"]
    name = m.get("name", mount_point)
    
    try:
        # Vérifier si on doit attendre avant de retenter
        retry_delay = get_retry_delay(mount_point)
        if retry_delay > 0:
            logger.debug(f"[{name}] Tentative différée, prochaine dans {int(retry_delay)}s")
            return False
        
        # Nettoyer les montages corrompus
        if not cleanup_stale_mount(mount_point):
            logger.error(f"[{name}] Impossible de nettoyer {mount_point}")
            record_mount_failure(mount_point)
            return False
        
        # Création du dossier si nécessaire
        try:
            os.makedirs(mount_point, exist_ok=True)
        except FileExistsError:
            logger.warning(f"[{name}] {mount_point} existe mais n'est pas un dossier, nettoyage...")
            cleanup_stale_mount(mount_point)
            os.makedirs(mount_point, exist_ok=True)
        except Exception as e:
            logger.error(f"[{name}] Impossible de créer {mount_point}: {e}")
            record_mount_failure(mount_point)
            return False
        
        # Vérifier si déjà monté
        if is_mounted(mount_point):
            logger.info(f"[{name}] Déjà monté sur {mount_point}")
            with active_mounts_lock:
                if mount_point not in active_mounts:
                    active_mounts.append(mount_point)
            reset_mount_failure(mount_point)
            return True

        # Construction de la commande de montage
        options = f"username={m['username']},password={m['password']}"
        options += ",file_mode=0777,dir_mode=0777,uid=0,gid=0"
        if m.get('options'):
            options += f",{m['options']}"
        
        cmd = [
            "mount", "-t", "cifs",
            m["remote"], mount_point,
            "-o", options
        ]

        # Log sans le mot de passe
        safe_cmd = cmd.copy()
        safe_cmd[-1] = f"username={m['username']},password=***,file_mode=0777,dir_mode=0777,{m.get('options', '')}"
        logger.info(f"[{name}] Tentative de montage: {' '.join(safe_cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            logger.info(f"[{name}] ✅ Montage réussi sur {mount_point}")
            with active_mounts_lock:
                active_mounts.append(mount_point)
            reset_mount_failure(mount_point)
            return True
        else:
            logger.error(f"[{name}] ❌ Échec du montage (code: {result.returncode})")
            logger.error(f"[{name}] stderr: {result.stderr}")
            record_mount_failure(mount_point)
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"[{name}] ⏱️  Timeout du montage (15s)")
        record_mount_failure(mount_point)
        return False
    except Exception as e:
        logger.error(f"[{name}] ⚠️  Exception lors du montage: {e}")
        record_mount_failure(mount_point)
        return False

def unmount(mount_point):
    """Démonte un point de montage"""
    if not is_mounted(mount_point):
        logger.info(f"Déjà démonté: {mount_point}")
        return True
    
    logger.info(f"Démontage de {mount_point}...")
    try:
        result = subprocess.run(
            ["umount", mount_point],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Démonté: {mount_point}")
            return True
        else:
            # Essai avec -l (lazy unmount) si échec
            logger.warning(f"Démontage normal échoué, essai lazy unmount...")
            result = subprocess.run(
                ["umount", "-l", mount_point],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"Lazy unmount réussi: {mount_point}")
                return True
            else:
                logger.error(f"Échec démontage: {result.stderr}")
                return False
    except Exception as e:
        logger.error(f"Exception lors du démontage: {e}")
        return False

def unmount_all():
    """Démonte tous les points de montage actifs"""
    with active_mounts_lock:
        logger.info(f"Démontage de {len(active_mounts)} point(s) de montage...")
        for mount_point in active_mounts:
            unmount(mount_point)

def signal_handler(sig, frame):
    """Gestionnaire de signal pour arrêt propre"""
    sig_name = signal.Signals(sig).name
    logger.info(f"Signal {sig_name} reçu - Arrêt du service SMB-Montage...")
    
    unmount_all()
    
    logger.info("Service SMB-Montage arrêté")
    sys.exit(0)

def monitor_mount(m):
    """Surveillance d'un montage individuel en boucle"""
    mount_point = m["mount_point"]
    name = m.get("name", mount_point)
    
    # Tentative initiale
    logger.info(f"[{name}] Démarrage de la surveillance")
    ensure_mount(m)
    
    # Boucle de surveillance individuelle
    while True:
        try:
            time.sleep(60)  # Vérification toutes les 60 secondes
            
            # Si déjà monté, tout va bien
            if is_mounted(mount_point):
                continue
            
            # Vérifier si on doit attendre avant de retenter
            retry_delay = get_retry_delay(mount_point)
            if retry_delay > 0:
                continue  # On attend
            
            logger.warning(f"[{name}] Montage perdu, tentative de remontage...")
            ensure_mount(m)
            
        except Exception as e:
            logger.error(f"[{name}] ⚠️  Erreur dans la surveillance: {e}")
            time.sleep(10)  # Attendre un peu avant de continuer

def main():
    logger.info("[elan-samba-mnt] Démarrage...")
    cfg = load_config()
    
    mounts = cfg.get("mounts", [])
    if not mounts:
        logger.warning("Aucun montage configuré!")
        return
    
    logger.info(f"Configuration de {len(mounts)} montage(s)")
    
    # Créer un thread de surveillance pour chaque montage
    threads = []
    for m in mounts:
        name = m.get("name", m["mount_point"])
        logger.info(f"🔄 Création du thread de surveillance pour [{name}]")
        
        thread = Thread(
            target=monitor_mount,
            args=(m,),
            name=f"monitor-{name}",
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    logger.info(f"✅ {len(threads)} thread(s) de surveillance démarrés")
    
    # Boucle principale - garde le processus en vie
    try:
        while True:
            time.sleep(30)
            
            # Vérifier que tous les threads sont vivants
            for i, thread in enumerate(threads):
                if not thread.is_alive():
                    m = mounts[i]
                    name = m.get("name", m["mount_point"])
                    logger.error(f"⚠️  Thread [{name}] est mort, redémarrage...")
                    
                    new_thread = Thread(
                        target=monitor_mount,
                        args=(m,),
                        name=f"monitor-{name}",
                        daemon=True
                    )
                    new_thread.start()
                    threads[i] = new_thread
                    
    except KeyboardInterrupt:
        logger.info("Interruption clavier reçue")
        unmount_all()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()
    