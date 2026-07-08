# ============================================================================
# FILE: /opt/elan/app/actions/base.py
# VERSION : 2.2 - Support JobLogger
# ============================================================================

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("core_watchdog_hf")


class ActionError(Exception):
    """Exception levée lors d'une erreur dans une action"""
    pass


class Action(ABC):
    """Classe de base abstraite pour toutes les actions"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialise l'action avec sa configuration
        
        Args:
            config: Dictionnaire de configuration de l'action
        """
        self.config = config
        self.job_logger = None  # ✅ Sera injecté par le pipeline
        self.validate_config()
    
    @abstractmethod
    def validate_config(self):
        """Valide la configuration de l'action"""
        pass
    
    @abstractmethod
    def execute(self, file_path: str) -> str:
        """
        Exécute l'action sur un fichier
        
        Args:
            file_path: Chemin du fichier à traiter
            
        Returns:
            Chemin du fichier résultant (peut être différent de l'entrée)
            
        Raises:
            ActionError: Si l'action échoue
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nom de l'action pour les logs"""
        pass
    
    def log_info(self, message: str):
        """Log un message info"""
        if self.job_logger:
            self.job_logger.log("INFO", f"[{self.name}] {message}")
        else:
            logger.info(f"[{self.name}] {message}")
    
    def log_error(self, message: str):
        """Log un message d'erreur"""
        if self.job_logger:
            self.job_logger.log("ERROR", f"[{self.name}] {message}")
        else:
            logger.error(f"❌ [{self.name}] {message}")
    
    def log_warning(self, message: str):
        """Log un message warning"""
        if self.job_logger:
            self.job_logger.log("WARNING", f"[{self.name}] {message}")
        else:
            logger.warning(f"⚠️  [{self.name}] {message}")
    
    def log_debug(self, message: str):
        """
        Log un message debug
        
        🔧 CORRECTION : Les messages DEBUG vont SEULEMENT dans journald,
        PAS dans les fichiers de logs individuels
        """
        # Toujours logger dans journald pour debug temps réel
        logger.debug(f"[{self.name}] {message}")
        
        # NE PAS utiliser job_logger pour DEBUG
        # (sinon ça va dans le fichier de log)

    def log_progress(self, message: str):
        """
        Log un message de progression (visible dans journald, pas dans fichier)
        
        Utilisé pour les indicateurs de progression qui n'ont pas besoin d'être
        dans les fichiers de logs individuels mais utiles en temps réel.
        """
        if self.job_logger:
            self.job_logger.log("PROGRESS", f"[{self.name}] {message}")
        else:
            logger.info(f"[{self.name}] {message}")