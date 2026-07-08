# ============================================================================
# FILE: /opt/elan/app/actions/saddle_stitch_split.py
# VERSION: 1.14 - Travail dans genstore du job
# DESCRIPTION: Sépare un PDF en couverture et intérieur (brochure piquée)
# Utilise qpdf en CLI (subprocess) plutôt que pikepdf comme le reste du pipeline :
# extraction/réorganisation de pages via qpdf --pages est nettement plus rapide sur
# les gros PDF (brochures) que la manipulation objet-par-objet de pikepdf, qui charge
# tout l'arbre PDF en mémoire Python. Pas de mesure chiffrée conservée, mais c'est la
# raison d'être de cet écart avec le reste du pipeline.
# ============================================================================

import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any
from .base import Action, ActionError


class SaddleStitchSplitAction(Action):
    """Sépare un PDF en couverture et intérieur pour brochure piquée (saddle stitch)"""
    
    @property
    def name(self) -> str:
        return "saddle_stitch_split"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        params.setdefault("cover_pages", "1-2,-2--1")
        params.setdefault("cover_suffix", "_cover")
        params.setdefault("inner_suffix", "_inner")
        params.setdefault("route_cover", None)
        params.setdefault("route_inner", None)
        
        if not params.get("route_cover"):
            raise ActionError("Paramètre 'route_cover' manquant")
        
        if not params.get("route_inner"):
            raise ActionError("Paramètre 'route_inner' manquant")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """Sépare le PDF et distribue les parties"""
        params = self.config["params"]
        
        # Détecter le dossier de travail (genstore du job)
        input_path = Path(file_path)
        work_dir = input_path.parent
        
        self.log_info(f"✂️ Séparation Saddle Stitch dans: {work_dir.name}")
        
        try:
            # Compter pages
            total_pages = self._get_page_count(input_path)
            self.log_info(f"📄 PDF: {total_pages} pages")
            
            # Créer les fichiers splittés
            base_name = input_path.stem
            cover_path = work_dir / f"{base_name}{params['cover_suffix']}.pdf"
            inner_path = work_dir / f"{base_name}{params['inner_suffix']}.pdf"
            
            # Convertir format pages
            cover_pages = params["cover_pages"]
            cover_pages_qpdf = self._convert_cover_pages_to_qpdf(cover_pages, total_pages)
            inner_pages = self._calculate_inner_pages(total_pages, cover_pages)
            
            # Séparer avec qpdf
            self._split_pdf(input_path, cover_path, cover_pages_qpdf, "couverture")
            self._split_pdf(input_path, inner_path, inner_pages, "intérieur")
            
            # Router la couverture
            self.log_info(f"📌 Routage couverture")
            last_cover_path = self._route_through_pipeline(
                cover_path, 
                params["route_cover"],
                "couverture"
            )
            
            # Router l'intérieur
            self.log_info(f"📌 Routage intérieur")
            last_inner_path = self._route_through_pipeline(
                inner_path,
                params["route_inner"],
                "intérieur"
            )
            
            # Retourner le dernier fichier créé
            return last_inner_path or last_cover_path or file_path
            
        except Exception as e:
            raise ActionError(f"Erreur saddle_stitch_split: {e}")
    
    def _calculate_inner_pages(self, total_pages: int, cover_pages: str) -> str:
        """Calcule automatiquement les pages intérieures"""
        if cover_pages == "1-2,-2--1":
            if total_pages <= 4:
                raise ActionError(f"PDF trop petit ({total_pages} pages)")
            return f"3-{total_pages - 2}"
        
        if "-" in cover_pages and not cover_pages.startswith("-"):
            try:
                parts = cover_pages.split(",")[0]
                cover_end = int(parts.split("-")[1])
                inner_start = cover_end + 1
                if inner_start >= total_pages:
                    raise ActionError(f"Couverture trop grande")
                return f"{inner_start}-{total_pages}"
            except Exception:
                pass
        
        raise ActionError(f"Format cover_pages non reconnu: {cover_pages}")
    
    def _convert_cover_pages_to_qpdf(self, cover_pages: str, total_pages: int) -> str:
        """Convertit le format en syntaxe qpdf"""
        if cover_pages == "1-2,-2--1":
            if total_pages <= 4:
                raise ActionError(f"PDF trop petit ({total_pages} pages)")
            return f"1-2,{total_pages-1}-{total_pages}"
        
        return cover_pages
    
    def _route_through_pipeline(self, file_path: Path, route_config: dict, label: str) -> str:
        """
        Exécute un pipeline d'actions sur le fichier splitté + distribution
        
        IMPORTANT: 
        - Travaille dans le genstore du job
        - Les destinations sont dans route_config["destinations"]
        """
        from . import get_action
        
        actions_config = route_config.get("actions", [])
        destinations = route_config.get("destinations", [])
        
        if not actions_config:
            raise ActionError(f"Pipeline {label}: aucune action")
        
        current_path = str(file_path)
        
        self.log_info(f"   Pipeline {label}: {len(actions_config)} action(s)")
        
        # Exécuter les actions (toutes dans le même genstore)
        for i, action_config in enumerate(actions_config, 1):
            action_type = action_config.get("type")
            if not action_type:
                raise ActionError(f"Pipeline {label}, action #{i}: type manquant")
            
            try:
                action = get_action(action_type, action_config)
                # ✅ Injecter le job_logger dans la sous-action
                action.job_logger = self.job_logger
                
                self.log_info(f"   ⚙️ {label} - Action {i}/{len(actions_config)}: {action.name}")
                current_path = action.execute(current_path)
                
                # Vérifier que le fichier existe après l'action
                if not os.path.exists(current_path):
                    raise ActionError(f"Fichier introuvable après action {action.name}: {current_path}")
                
            except Exception as e:
                raise ActionError(f"Pipeline {label}, action {action_type}: {e}")
        
        # Distribuer vers destinations (si présentes dans la route)
        if destinations:
            if isinstance(destinations, str):
                destinations = [destinations]
            
            self.log_info(f"   📤 Distribution {label} vers {len(destinations)} destination(s)")
            
            # Vérifier que le fichier final existe
            if not os.path.exists(current_path):
                raise ActionError(f"Fichier final introuvable: {current_path}")
            
            for dest in destinations:
                try:
                    # Créer le dossier
                    os.makedirs(dest, exist_ok=True)
                    
                    # Permissions
                    try:
                        os.chmod(dest, 0o777)
                    except Exception:
                        pass
                    
                    # Copier
                    filename = Path(current_path).name
                    dest_path = Path(dest) / filename
                    
                    # Gérer doublons
                    if dest_path.exists():
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while dest_path.exists():
                            dest_path = Path(dest) / f"{base}_{counter}{ext}"
                            counter += 1
                        self.log_info(f"      Renommage: {dest_path.name}")
                    
                    # Copier le fichier
                    self.log_debug(f"      Copie: {current_path} → {dest_path}")
                    shutil.copy2(current_path, dest_path)
                    
                    # Vérifier que la copie a réussi
                    if not dest_path.exists():
                        raise ActionError(f"Échec copie vers {dest_path}")
                    
                    # Permissions fichier
                    try:
                        os.chmod(dest_path, 0o666)
                    except Exception:
                        pass
                    
                    self.log_info(f"      ✅ {dest_path}")
                    
                except Exception as e:
                    self.log_error(f"      ❌ Erreur distribution vers {dest}: {e}")
                    raise ActionError(f"Distribution {label} vers {dest}: {e}")
        
        return current_path
    
    def _get_page_count(self, pdf_path: Path) -> int:
        """Compte le nombre de pages avec qpdf"""
        try:
            result = subprocess.run(
                ["qpdf", "--show-npages", str(pdf_path)],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                raise ActionError(f"Comptage pages: {result.stderr}")
            
            return int(result.stdout.strip())
        except Exception as e:
            raise ActionError(f"Erreur comptage pages: {e}")
    
    def _split_pdf(self, input_path: Path, output_path: Path, pages: str, label: str):
        """Extrait des pages avec qpdf"""
        self.log_info(f"✂️ Extraction {label}: pages {pages}")
        
        cmd = [
            "qpdf", str(input_path),
            "--pages", ".", pages, "--",
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                raise ActionError(f"qpdf: {result.stderr}")
            
            if not output_path.exists():
                raise ActionError(f"Fichier non créé: {output_path}")
            
            page_count = self._get_page_count(output_path)
            size = os.path.getsize(output_path)
            self.log_info(f"✅ {label}: {page_count} pages, {size:,} bytes")
            
        except subprocess.TimeoutExpired:
            raise ActionError(f"Timeout extraction {label}")
        except Exception as e:
            raise ActionError(f"Erreur extraction {label}: {e}")