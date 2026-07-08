# ============================================================================
# FILE: /opt/elan/app/elan-watchdog.py
# VERSION : 14.4 - Pool intelligent + timing
# ============================================================================

import yaml
import time
import os
import logging
import signal
import sys
import shutil
import uuid
import json
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from queue import Queue
from threading import Thread, Lock

# Import du registre d'actions
from actions import get_action, list_actions, ActionError

# Configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
CONFIG_FILE = "/config/elan-watchdog.yml"
GENSTORE_ROOT = Path("/genstore")
JOURNAL_ROOT = Path("/shares/sortie/journaux")

# File d'attente pour jobs en pause (montages down)
pending_jobs_queue = []
pending_jobs_lock = Lock()

# Configuration du logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("elan-watchdog")


# ============================================================================
# GESTION DES PERMISSIONS
# ============================================================================

def ensure_permissions(path: str, is_directory: bool = False):
    """Assure que les permissions sont correctes (777 pour tous)"""
    try:
        if not os.path.exists(path):
            return
        
        os.chmod(path, 0o777)
        
        if is_directory and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o777)
                    except Exception:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o666)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Permissions {path}: {e}")


# ============================================================================
# LOGGER PAR JOB
# ============================================================================

class JobLogger:
    """Logger dédié à un job avec export dans /shares/sortie/journaux/"""
    
    def __init__(self, job_id: str, filename: str, watcher_name: str):
        self.job_id = job_id
        self.filename = filename
        self.watcher_name = watcher_name
        self.logs = []
        
        # Créer le dossier journaux
        JOURNAL_ROOT.mkdir(parents=True, exist_ok=True)
        ensure_permissions(str(JOURNAL_ROOT), is_directory=True)
        
        # Nom du fichier journal
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        safe_name = Path(filename).stem[:50]  # Limiter longueur
        self.log_file = JOURNAL_ROOT / f"{safe_name}_{timestamp}.log"
    
    def log(self, level: str, message: str, file_only: bool = False):
        """
        Ajoute un message au journal
        
        Args:
            level: Niveau de log (INFO, WARNING, ERROR, DEBUG, PROGRESS)
            message: Message à logger
            file_only: Si True, log uniquement dans le fichier (pas dans journald)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{self.watcher_name}] [{level}] {message}"
        
        # PROGRESS : afficher dans journald mais PAS dans le fichier
        if level == "PROGRESS":
            # Log dans journald avec niveau INFO
            logger.info(f"[Job {self.job_id[:8]}] {message}")
            # NE PAS ajouter à self.logs (donc pas dans le fichier)
            return
        
        # Tous les autres niveaux : dans le fichier
        self.logs.append(log_entry)
        
        # Log aussi dans journald (sauf si file_only)
        if not file_only:
            if level == "ERROR":
                logger.error(f"[Job {self.job_id[:8]}] {message}")
            elif level == "WARNING":
                logger.warning(f"[Job {self.job_id[:8]}] {message}")
            elif level == "DEBUG":
                logger.debug(f"[Job {self.job_id[:8]}] {message}")
            else:
                logger.info(f"[Job {self.job_id[:8]}] {message}")
    
    def save(self):
        """Sauvegarde le journal sur disque"""
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(self.logs))
            
            ensure_permissions(str(self.log_file), is_directory=False)
            logger.info(f"📄 Journal sauvegardé: {self.log_file.name}")
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde journal: {e}")


# ============================================================================
# JOB (unité de traitement)
# ============================================================================

class Job:
    """Représente un fichier à traiter"""
    
    def __init__(self, file_path: str, watcher_config: dict):
        self.job_id = uuid.uuid4().hex
        self.original_path = Path(file_path)
        self.filename = self.original_path.name
        self.watcher_name = watcher_config.get("name", "Unknown")
        self.watcher_config = watcher_config
        self.status = "pending"  # pending, processing, completed, error, waiting_mount
        self.error_message = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        # Détection du type de job
        self.page_count = self._count_pages_fast(file_path)
        self.is_brochure = self._is_brochure_job()
        
        # Chemins de travail
        self.genstore_dir = GENSTORE_ROOT / f"job_{self.job_id}"
        self.genstore_input = None
        self.current_file = None
        
        # Logger dédié
        self.job_logger = JobLogger(self.job_id, self.filename, self.watcher_name)
    
    def __repr__(self):
        return f"Job({self.job_id[:8]}, {self.filename}, {self.status})"
    
    def get_size_mb(self) -> float:
        """Retourne la taille en MB"""
        return self.size_bytes / (1024 * 1024)
    
    def get_duration(self) -> str:
        """Retourne la durée d'exécution formatée"""
        if not self.started_at or not self.completed_at:
            return "N/A"
        
        duration = (self.completed_at - self.started_at).total_seconds()
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        
        if minutes > 0:
            return f"{minutes} min {seconds} sec"
        else:
            return f"{seconds} sec"
    
    def _count_pages_fast(self, file_path: str) -> int:
        """Compte rapidement le nombre de pages d'un PDF"""
        try:
            result = subprocess.run(
                ["qpdf", "--show-npages", file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        return 0
    
    def _is_brochure_job(self) -> bool:
        """Détermine si c'est un job de type brochure"""
        # Critère 1 : Plus de 4 pages
        if self.page_count > 4:
            return True
        
        # Critère 2 : Nom du watcher contient "brochure"
        if "brochure" in self.watcher_name.lower():
            return True
        
        return False


# ============================================================================
# PIPELINE D'ACTIONS
# ============================================================================

class ActionPipeline:
    """Exécute une série d'actions sur un job"""
    
    def __init__(self, job: Job):
        self.job = job
        self.actions = []
        
        # Créer les instances d'actions
        actions_config = job.watcher_config.get("actions", [])
        
        if actions_config is None:
            actions_config = []
        
        for i, action_config in enumerate(actions_config, 1):
            action_type = action_config.get("type")
            if not action_type:
                raise ValueError(f"Action #{i}: type manquant")
            
            try:
                action = get_action(action_type, action_config)
                action.job_logger = job.job_logger
                self.actions.append(action)
            except Exception as e:
                raise ValueError(f"Action #{i} ({action_type}): {e}")
    
    def execute(self) -> bool:
        """
        Exécute toutes les actions séquentiellement
        
        Returns:
            True si succès, False si erreur
        """
        job = self.job
        current_file = str(job.genstore_input)
        
        job.job_logger.log("INFO", f"🚀 Début du pipeline ({len(self.actions)} action(s))")
        job.status = "processing"
        job.started_at = datetime.now()
        
        for i, action in enumerate(self.actions, 1):
            try:
                job.job_logger.log("INFO", f"⚙️  Action {i}/{len(self.actions)}: {action.name}")
                
                # Exécuter l'action
                current_file = action.execute(current_file)
                job.current_file = current_file
                
                # Assurer permissions
                if current_file and os.path.exists(current_file):
                    ensure_permissions(current_file, is_directory=False)
                
            except ActionError as e:
                job.job_logger.log("ERROR", f"❌ Action {action.name}: {e}")
                job.status = "error"
                job.error_message = f"Action {action.name}: {e}"
                return False
                
            except Exception as e:
                job.job_logger.log("ERROR", f"💥 Action {action.name}: erreur inattendue: {e}")
                job.status = "error"
                job.error_message = f"Action {action.name}: {e}"
                return False
        
        job.job_logger.log("INFO", f"✅ Pipeline terminé avec succès")
        return True


# ============================================================================
# GESTIONNAIRE DE DISTRIBUTION (remplace copy/move)
# ============================================================================

def distribute_to_destinations(job: Job) -> bool:
    """
    Distribue le fichier traité vers les destination(s)
    
    Gère aussi les montages down (mise en attente) et overwrite
    """
    destinations = job.watcher_config.get("destinations", [])
    overwrite = job.watcher_config.get("overwrite", False)
    
    if not destinations:
        job.job_logger.log("WARNING", "Aucune destination configurée")
        return True
    
    if isinstance(destinations, str):
        destinations = [destinations]
    
    job.job_logger.log("INFO", f"📤 Distribution vers {len(destinations)} destination(s)")
    
    final_file = job.current_file or job.genstore_input
    filename = Path(final_file).name
    
    success_count = 0
    failed_destinations = []
    
    for dest in destinations:
        try:
            # Vérifier si le montage est accessible
            if not is_mount_available(dest):
                job.job_logger.log("WARNING", f"⏸️  Montage inaccessible: {dest}")
                failed_destinations.append(dest)
                continue
            
            # Créer le dossier de destination
            os.makedirs(dest, exist_ok=True)
            ensure_permissions(dest, is_directory=True)
            
            # Construire le chemin de destination
            dest_path = Path(dest) / filename
            
            # Gérer les doublons ou overwrite
            if dest_path.exists():
                if overwrite:
                    os.remove(dest_path)
                    job.job_logger.log("INFO", f"   ⚠️  Fichier écrasé: {filename}")
                else:
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    while dest_path.exists():
                        dest_path = Path(dest) / f"{base}_{counter}{ext}"
                        counter += 1
                    job.job_logger.log("INFO", f"   Renommage: {dest_path.name}")
            
            # Vérifier que le fichier source existe avant copie
            if not os.path.exists(final_file):
                job.job_logger.log("ERROR", f"   ❌ Fichier source introuvable: {final_file}")
                failed_destinations.append(dest)
                continue
            
            # Copier le fichier
            shutil.copy2(final_file, dest_path)
            ensure_permissions(str(dest_path), is_directory=False)
            
            job.job_logger.log("INFO", f"   ✅ {dest_path}")
            success_count += 1
            
        except Exception as e:
            job.job_logger.log("ERROR", f"   ❌ {dest}: {e}")
            job.job_logger.log("ERROR", f"      Fichier source: {final_file}")
            job.job_logger.log("ERROR", f"      Destination: {dest_path}")
            failed_destinations.append(dest)
    
    # Si tous les montages sont down, mettre en pause
    if failed_destinations and success_count == 0:
        job.job_logger.log("WARNING", f"🔄 Job mis en pause (montages inaccessibles)")
        job.status = "waiting_mount"
        job.watcher_config["failed_destinations"] = failed_destinations
        
        # Ajouter à la file d'attente
        with pending_jobs_lock:
            pending_jobs_queue.append(job)
        
        return False
    
    # Si au moins une destination a réussi
    if success_count > 0:
        if failed_destinations:
            job.job_logger.log("WARNING", f"⚠️  Distribution partielle ({success_count}/{len(destinations)})")
        return True
    
    return False


def is_mount_available(path: str) -> bool:
    """
    Vérifie si le montage sous-jacent à `path` est accessible.

    On ne teste pas le dossier de destination final : il n'existe souvent pas
    encore (sous-dossier jamais créé), ce qui ne veut pas dire que le montage
    est down. On remonte donc jusqu'au premier ancêtre existant et on teste
    celui-ci : un montage CIFS down reste bien détecté (le dossier existe mais
    n'est plus listable), tandis qu'un simple sous-dossier manquant ne bloque
    plus la distribution (il sera créé par distribute_to_destinations).
    """
    try:
        p = Path(path)
        while not p.exists():
            if p.parent == p:
                return False
            p = p.parent
        os.listdir(p)
        return True
    except Exception:
        return False


# ============================================================================
# WORKER DE RETRY (pour jobs en pause)
# ============================================================================

def retry_pending_jobs_worker():
    """Thread qui essaie de redistribuer les jobs en pause"""
    logger.info("🔄 Worker de retry démarré")
    
    while True:
        time.sleep(60)  # Vérifier toutes les minutes
        
        with pending_jobs_lock:
            if not pending_jobs_queue:
                continue
            
            logger.info(f"🔄 {len(pending_jobs_queue)} job(s) en attente de montage")
            
            # Copier la liste pour itération sûre
            jobs_to_retry = pending_jobs_queue.copy()
        
        jobs_completed = []
        
        for job in jobs_to_retry:
            try:
                failed_destinations = job.watcher_config.get("failed_destinations", [])
                
                # Vérifier si les montages sont de retour
                available = [d for d in failed_destinations if is_mount_available(d)]
                
                if available:
                    job.job_logger.log("INFO", f"🔄 Retry distribution ({len(available)} montage(s) disponibles)")
                    
                    # Remettre les destinations disponibles
                    job.watcher_config["destinations"] = available
                    
                    # Essayer de redistribuer
                    if distribute_to_destinations(job):
                        job.status = "completed"
                        job.completed_at = datetime.now()
                        job.job_logger.log("INFO", f"🎉 Job terminé avec succès en {job.get_duration()}")
                        job.job_logger.save()
                        cleanup_job(job)
                        jobs_completed.append(job)
                        logger.info(f"✅ Job {job.job_id[:8]} ({job.filename}) terminé après retry")
                    else:
                        # Toujours en attente
                        job.job_logger.log("WARNING", f"⏸️  Distribution échouée, reste en attente")
            
            except Exception as e:
                job.job_logger.log("ERROR", f"Erreur retry: {e}")
                logger.error(f"❌ Erreur retry job {job.job_id[:8]}: {e}")
        
        # Retirer les jobs terminés de la queue
        if jobs_completed:
            with pending_jobs_lock:
                for job in jobs_completed:
                    if job in pending_jobs_queue:
                        pending_jobs_queue.remove(job)
            
            logger.info(f"✅ {len(jobs_completed)} job(s) retiré(s) de la queue de retry")


# ============================================================================
# NETTOYAGE
# ============================================================================

def cleanup_job(job: Job):
    """Nettoie le genstore d'un job"""
    try:
        if job.genstore_dir.exists():
            shutil.rmtree(job.genstore_dir)
            job.job_logger.log("INFO", f"🧹 Genstore nettoyé")
    except Exception as e:
        job.job_logger.log("ERROR", f"Erreur nettoyage genstore: {e}")


# ============================================================================
# PROCESSOR (traite un job)
# ============================================================================

def process_job(job: Job) -> bool:
    """
    Traite un job complet
    
    Workflow:
    1. Déplacer fichier vers genstore
    2. Exécuter pipeline d'actions
    3. Distribuer vers destinations
    4. Nettoyer genstore
    5. Sauvegarder journal
    """
    try:
        job.job_logger.log("INFO", f"📋 Nouveau job: {job.filename} ({job.get_size_mb():.2f} MB, {job.page_count} pages)")
        
        # 1. Créer genstore et déplacer fichier
        job.genstore_dir.mkdir(parents=True, exist_ok=True)
        job.genstore_input = job.genstore_dir / job.filename
        
        shutil.move(str(job.original_path), str(job.genstore_input))
        job.current_file = str(job.genstore_input)
        
        job.job_logger.log("INFO", f"📦 Fichier déplacé vers genstore: {job.job_id[:8]}")
        
        actions_config = job.watcher_config.get("actions")
        
        if actions_config and len(actions_config) > 0:
            # 2. Exécuter le pipeline
            pipeline = ActionPipeline(job)
            
            if not pipeline.execute():
                job.job_logger.log("ERROR", f"💥 Pipeline échoué: {job.error_message}")
                job.completed_at = datetime.now()
                job.job_logger.save()
                cleanup_job(job)
                return False
        else:
            # Pas d'actions = copie simple
            job.job_logger.log("INFO", f"📋 Aucune action configurée (copie simple)")
            job.status = "processing"
            job.started_at = datetime.now()
        
        # 3. Distribuer vers destinations
        if not distribute_to_destinations(job):
            # Job mis en pause (montage down)
            job.job_logger.save()
            # Ne pas nettoyer le genstore, on garde le fichier traité
            return False
        
        # 4. Nettoyer genstore
        cleanup_job(job)
        
        # 5. Marquer comme terminé
        job.status = "completed"
        job.completed_at = datetime.now()
        job.job_logger.log("INFO", f"🎉 Job terminé avec succès en {job.get_duration()}")
        job.job_logger.save()
        
        return True
        
    except Exception as e:
        job.job_logger.log("ERROR", f"💥 Erreur inattendue: {e}")
        job.status = "error"
        job.error_message = str(e)
        job.completed_at = datetime.now()
        job.job_logger.save()
        cleanup_job(job)
        return False


# ============================================================================
# POOL DE WORKERS INTELLIGENT (multi-processing)
# ============================================================================

class SmartJobPool:
    """
    Pool intelligent avec gestion de priorité
    
    Règles:
    - 1 brochure à la fois (> 4 pages)
    - 3 petits jobs en parallèle (≤ 4 pages)
    """
    
    def __init__(self):
        self.brochure_executor = ProcessPoolExecutor(max_workers=1)
        self.small_executor = ProcessPoolExecutor(max_workers=3)
        
        self.active_brochure = None  # Job brochure en cours
        self.active_small_jobs = {}  # Jobs petits en cours
        
        self.brochure_queue = []  # Queue des brochures
        self.small_queue = []     # Queue des petits jobs
        
        self.lock = Lock()
        
        logger.info(f"🔧 Pool intelligent: 1 brochure + 3 petits jobs")
    
    def submit_job(self, job: Job):
        """Ajoute un job à la queue appropriée"""
        with self.lock:
            if job.is_brochure:
                self.brochure_queue.append(job)
                logger.info(f"📚 Brochure ajoutée à la queue: {job.filename} ({job.page_count} pages)")
            else:
                self.small_queue.append(job)
                logger.info(f"📄 Petit job ajouté à la queue: {job.filename} ({job.page_count} pages)")
            
            # Trier les queues par taille (petits fichiers en premier)
            self.brochure_queue.sort(key=lambda j: j.size_bytes)
            self.small_queue.sort(key=lambda j: j.size_bytes)
    
    def process_queue(self):
        """Traite les queues (appelé régulièrement)"""
        with self.lock:
            # Nettoyer les jobs terminés
            if self.active_brochure and self.active_brochure[1].done():
                job_id, future = self.active_brochure
                self.active_brochure = None
            
            completed_small = [job_id for job_id, future in self.active_small_jobs.items() if future.done()]
            for job_id in completed_small:
                del self.active_small_jobs[job_id]
            
            # Lancer nouvelle brochure si slot libre
            if not self.active_brochure and self.brochure_queue:
                job = self.brochure_queue.pop(0)
                future = self.brochure_executor.submit(process_job, job)
                self.active_brochure = (job.job_id, future)
                logger.info(f"🚀 Brochure lancée: {job.filename}")
            
            # Lancer petits jobs si slots libres
            while len(self.active_small_jobs) < 3 and self.small_queue:
                job = self.small_queue.pop(0)
                future = self.small_executor.submit(process_job, job)
                self.active_small_jobs[job.job_id] = future
                logger.info(f"🚀 Petit job lancé: {job.filename}")
    
    def get_status(self) -> dict:
        """Retourne l'état du pool"""
        with self.lock:
            return {
                "brochure_active": self.active_brochure is not None,
                "small_jobs_active": len(self.active_small_jobs),
                "brochure_queue": len(self.brochure_queue),
                "small_queue": len(self.small_queue)
            }


# Instance globale du pool
job_pool = SmartJobPool()


# ============================================================================
# HANDLER HOTFOLDER
# ============================================================================

class HotFolderHandler(PatternMatchingEventHandler):
    """Gestionnaire d'événements pour un dossier surveillé"""
    
    MACOS_JUNK_PATTERNS = [
        ".DS_Store", "._*", ".*.pdf", ".Spotlight-V100",
        ".Trashes", ".fseventsd", "Thumbs.db"
    ]
    
    def __init__(self, watcher_config: Dict[str, Any]):
        patterns = watcher_config.get("patterns", ["*"])
        super().__init__(patterns=patterns, ignore_directories=True)
        
        self.watcher_config = watcher_config
        self.name = watcher_config.get("name", "Unnamed")
        self.folder = watcher_config.get("folder")
        self.cleanup_macos_junk = watcher_config.get("cleanup_macos_junk", True)
        self.stability_timeout = watcher_config.get("stability_timeout", 300)
        self.stability_checks = watcher_config.get("stability_checks", 3)
        
        logger.info(f"📁 Watcher: {self.name}")
        logger.info(f"   Dossier: {self.folder}")
        logger.info(f"   Patterns: {patterns}")
        
        ensure_permissions(self.folder, is_directory=True)
    
    def _is_macos_junk(self, file_path: str) -> bool:
        import fnmatch
        filename = os.path.basename(file_path)
        return any(fnmatch.fnmatch(filename, p) for p in self.MACOS_JUNK_PATTERNS)
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Ignorer fichiers macOS
        if self._is_macos_junk(file_path):
            if self.cleanup_macos_junk:
                try:
                    time.sleep(0.5)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
            return
        
        logger.info(f"🆕 [{self.name}] {filename}")
        
        # Attendre stabilité
        if not self._wait_for_file_stable(file_path):
            logger.warning(f"⚠️  [{self.name}] Fichier instable: {filename}")
            return
        
        # Créer un job et l'ajouter au pool
        try:
            job = Job(file_path, self.watcher_config)
            job_pool.submit_job(job)
            logger.info(f"✅ [{self.name}] Job créé: {job.job_id[:8]}")
        except Exception as e:
            logger.error(f"❌ [{self.name}] Erreur création job: {e}")
    
    def _wait_for_file_stable(self, file_path: str) -> bool:
        waited = 0
        last_size = -1
        stable_count = 0
        
        while waited < self.stability_timeout:
            try:
                if not os.path.exists(file_path):
                    return False
                
                current_size = os.path.getsize(file_path)
                
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    
                    if stable_count >= self.stability_checks:
                        if self._check_file_not_locked(file_path):
                            return True
                else:
                    stable_count = 0
                
                last_size = current_size
                time.sleep(2)
                waited += 2
                
            except Exception:
                return False
        
        return False
    
    def _check_file_not_locked(self, file_path: str) -> bool:
        try:
            with open(file_path, 'ab'):
                pass
            return True
        except Exception:
            return False


# ============================================================================
# SCAN AU DÉMARRAGE (traiter fichiers existants)
# ============================================================================

def scan_existing_files(watchers_config: List[dict]):
    """Scan les dossiers pour traiter les fichiers déjà présents"""
    logger.info("🔍 Scan des fichiers existants...")
    
    total_found = 0
    
    for watcher_config in watchers_config:
        folder = watcher_config.get("folder")
        patterns = watcher_config.get("patterns", ["*.pdf"])
        name = watcher_config.get("name", "Unknown")
        
        if not folder or not os.path.exists(folder):
            continue
        
        # Scanner le dossier
        import fnmatch
        for file in Path(folder).iterdir():
            if file.is_dir():
                continue
            
            # Vérifier patterns
            match = any(fnmatch.fnmatch(file.name, p) for p in patterns)
            if not match:
                continue
            
            # Ignorer fichiers macOS
            if any(fnmatch.fnmatch(file.name, p) for p in HotFolderHandler.MACOS_JUNK_PATTERNS):
                continue
            
            logger.info(f"📄 [{name}] Fichier existant: {file.name}")
            
            try:
                job = Job(str(file), watcher_config)
                job_pool.submit_job(job)
                total_found += 1
            except Exception as e:
                logger.error(f"❌ Erreur: {e}")
    
    if total_found > 0:
        logger.info(f"✅ {total_found} fichier(s) existant(s) ajoutés à la queue")
    else:
        logger.info("✅ Aucun fichier existant à traiter")


# ============================================================================
# MAIN
# ============================================================================

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Erreur config: {e}")
        sys.exit(1)

def validate_config(cfg: dict) -> bool:
    watchers = cfg.get("watchers", [])
    
    if not watchers:
        logger.error("❌ Aucun watcher configuré")
        return False
    
    for i, watcher in enumerate(watchers, 1):
        name = watcher.get("name", f"Watcher #{i}")
        folder = watcher.get("folder")
        
        if not folder:
            logger.error(f"❌ [{name}] 'folder' manquant")
            return False
        
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            ensure_permissions(folder, is_directory=True)
        
        # Valider destinations (sauf si perfect_binding_split, saddle_stitch_split ou extract_cutting avec routage)
        destinations = watcher.get("destinations")
        actions = watcher.get("actions", [])

        # Si c'est un perfect_binding_split ou saddle_stitch_split extract_cutting avec routage, pas besoin de destinations au niveau watcher
        has_routing = False
        if actions:
            for action in actions:
                action_type = action.get("type")

                # Split avec routage saddle stitch
                if action_type == "saddle_stitch_split":
                    params = action.get("params", {})
                    if params.get("route_cover") or params.get("route_inner"):
                        has_routing = True
                        break

                # Extract_cutting avec routage
                if action_type == "extract_cutting":
                    params = action.get("params", {})
                    if params.get("route_simulation") or params.get("route_print"):
                        has_routing = True
                        break

                # Perfect binding avec destinations dynamiques
                if action_type == "perfect_binding_split":
                    params = action.get("params", {})
                    if params.get("destinations"):
                        has_routing = True
                        break
        
        if not has_routing and not destinations:
            logger.error(f"❌ [{name}] 'destinations' manquant")
            return False
    
    return True

def signal_handler(sig, frame):
    logger.info(f"🛑 Signal {signal.Signals(sig).name} reçu")
    sys.exit(0)

def main():
    logger.info("=" * 70)
    logger.info("🚀 [elan-watchdog] v14.2 - Démarrage")
    logger.info("=" * 70)
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🎯 Actions: {', '.join(list_actions())}")
    logger.info("")
    
    # Config
    cfg = load_config()
    if not validate_config(cfg):
        sys.exit(1)

    # Permissions dossiers racines
    for path in ["/shares/entree", "/shares/sortie", "/genstore"]:
        if os.path.exists(path):
            ensure_permissions(path, is_directory=True)

    JOURNAL_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_permissions(str(JOURNAL_ROOT), is_directory=True)

    # Lancer worker de retry
    retry_thread = Thread(target=retry_pending_jobs_worker, daemon=True)
    retry_thread.start()

    # Observer watchdog
    observer = Observer()
    watchers = cfg.get("watchers", [])

    for watcher_config in watchers:
        handler = HotFolderHandler(watcher_config)
        observer.schedule(handler, watcher_config["folder"], recursive=False)

    observer.start()

    # Scan fichiers existants
    scan_existing_files(watchers)

    logger.info("=" * 70)
    logger.info("✅ Surveillance active")
    logger.info("=" * 70)

    # Boucle principale avec affichage statut périodique
    try:
        last_status_log = time.time()
        
        while True:
            job_pool.process_queue()
            
            # Afficher statut toutes les 30 secondes
            if time.time() - last_status_log > 30:
                status = job_pool.get_status()
                if any(status.values()):  # Seulement si activité
                    logger.info(f"📊 Pool: Brochure={status['brochure_active']}, "
                            f"Petits={status['small_jobs_active']}/3, "
                            f"Queue: Broch.={status['brochure_queue']}, "
                            f"Petits={status['small_queue']}")
                last_status_log = time.time()
            
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("⌨️  Arrêt")
        observer.stop()

    observer.join()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()