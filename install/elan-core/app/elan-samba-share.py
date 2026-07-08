# ============================================================================
# FILE: /opt/elan/app/elan-samba-share.py
# VERSION : 2
# ============================================================================

import yaml
import time
import os
import subprocess
import logging
import signal
import sys

# Configuration
LOG_LEVEL = "DEBUG"
CONFIG_FILE = "/config/elan-samba-share.yml"
SMB_CONF = "/etc/samba/smb.conf"

# Variable globale pour le processus smbd
smbd_process = None

# Configuration du logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("elan-samba-share")

def load_config():
    """Chargement du fichier de configuration du service"""
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

def generate_samba_conf(cfg):
    """Génération de la configuration Samba"""
    shares = []

    for share in cfg.get("share", []):
        if share.get("samba_share"):
            path = share["path"]
            
            # Création du dossier si nécessaire
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                logger.info(f"Dossier créé : {path}")
            
            # Appliquer les permissions pour écriture
            os.chmod(path, 0o777)
            logger.info(f"Permissions 777 appliquées sur : {path}")
            
            shares.append(f"""
[{share["name"]}]
    path = {path}
    browseable = yes
    writable = yes
    read only = no
    guest ok = {str(cfg["samba"].get("guest_ok", True)).lower()}
    force user = nobody
    force group = nogroup
    create mask = 0666
    directory mask = 0777
""")

    conf = f"""[global]
    workgroup = {cfg["samba"].get("workgroup", "WORKGROUP")}
    netbios name = {cfg["samba"].get("netbios", "ELAN-SERVER")}
    server string = {cfg["samba"].get("comment", "ELAN Server")}
    security = user
    map to guest = Bad User
    guest account = nobody
    log level = 1

{"".join(shares)}
"""
    logger.info("=== Configuration SMB-Server générée ===")
    logger.info(f"\n{conf}")

    with open(SMB_CONF, "w") as f:
        f.write(conf)

def test_samba_config():
    """Teste la configuration Samba avant de démarrer"""
    logger.info("Test de la configuration Samba...")
    result = subprocess.run(
        ["testparm", "-s"],
        capture_output=True,
        text=True
    )
    logger.info(f"testparm stdout:\n{result.stdout}")
    if result.stderr:
        logger.warning(f"testparm stderr:\n{result.stderr}")
    return result.returncode == 0

def signal_handler(sig, frame):
    """Gestionnaire de signal pour arrêt propre"""
    global smbd_process
    
    sig_name = signal.Signals(sig).name
    logger.info(f"Signal {sig_name} reçu - Arrêt du service SMB-Server...")
    
    if smbd_process and smbd_process.poll() is None:
        logger.info("Arrêt de smbd...")
        smbd_process.terminate()
        try:
            smbd_process.wait(timeout=10)
            logger.info("smbd arrêté proprement")
        except subprocess.TimeoutExpired:
            logger.warning("smbd ne répond pas, kill forcé...")
            smbd_process.kill()
            smbd_process.wait()
    
    logger.info("Service SMB-Server arrêté")
    sys.exit(0)

def main():
    global smbd_process
    
    logger.info("[elan-samba-share] Démarrage...")
    
    # Charger et appliquer la configuration
    cfg = load_config()
    generate_samba_conf(cfg)

    # Créer les dossiers nécessaires à smbd
    for d in ["/var/run/samba", "/var/log/samba", "/var/cache/samba"]:
        os.makedirs(d, exist_ok=True)

    # Tester la config
    if not test_samba_config():
        logger.error("Configuration Samba invalide!")
        sys.exit(1)

    # Démarrer Samba en foreground avec logs stderr
    logger.info("Démarrage de smbd...")
    smbd_process = subprocess.Popen(
        ["smbd", "--foreground", "--no-process-group", "--debug-stdout"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    logger.info(f"smbd démarré (PID: {smbd_process.pid})")

    # Lire les premières lignes de sortie de smbd
    time.sleep(2)
    if smbd_process.poll() is not None:
        # smbd s'est arrêté, lire la sortie
        output, _ = smbd_process.communicate()
        logger.error(f"smbd s'est arrêté immédiatement. Sortie:\n{output}")
        sys.exit(1)

    # Boucle principale - surveille smbd
    while True:
        # Vérifier si smbd est toujours actif
        if smbd_process.poll() is not None:
            output, _ = smbd_process.communicate()
            logger.error(f"smbd s'est arrêté (code: {smbd_process.returncode})")
            logger.error(f"Sortie smbd:\n{output}")
            sys.exit(1)
        time.sleep(30)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()
