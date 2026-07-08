# ============================================================================
# FILE: /opt/elan/app/actions/perfect_binding_split.py
# VERSION: 1.0.1
# DESCRIPTION: Découpe un PDF en cahiers pour dos carré collé (perfect binding)
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


class PerfectBindingSplitAction(Action):
    """Découpe un PDF en cahiers pour dos carré collé"""
    
    @property
    def name(self) -> str:
        return "perfect_binding_split"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("max_up", 8)  # 8up = 16 pages max par cahier
        params.setdefault("prefix", "C%nb%_")
        params.setdefault("route_actions", [])  # Actions communes à tous les cahiers
        
        # Destinations par format
        destinations = params.get("destinations", {})
        if not destinations:
            raise ActionError("Paramètre 'destinations' manquant")
        
        # Vérifier que les clés sont valides (8up, 4up, 2up, etc.)
        valid_ups = ["8up", "4up", "2up", "1up"]
        for up_key in destinations:
            if up_key not in valid_ups:
                raise ActionError(f"Format invalide: {up_key} (attendu: {valid_ups})")
            
            if not isinstance(destinations[up_key], list):
                raise ActionError(f"destinations.{up_key} doit être une liste")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """Découpe le PDF en cahiers et distribue"""
        params = self.config["params"]
        
        input_path = Path(file_path)
        work_dir = input_path.parent
        base_name = input_path.stem
        
        self.log_info(f"📖 Découpe Perfect Binding dans: {work_dir.name}")
        
        try:
            # Compter pages
            total_pages = self._get_page_count(input_path)
            self.log_info(f"📄 PDF: {total_pages} pages")
            
            # Calculer découpage en cahiers
            max_pages_per_sig = params["max_up"] * 2  # 8up = 16 pages
            signatures = self._calculate_signatures(total_pages, max_pages_per_sig)
            
            self.log_info(f"✂️ Découpage en {len(signatures)} cahier(s)")
            
            # Traiter chaque cahier
            last_path = file_path
            for i, sig in enumerate(signatures, 1):
                last_path = self._process_signature(
                    input_path, work_dir, base_name,
                    sig, i, params
                )
            
            return last_path
            
        except Exception as e:
            raise ActionError(f"Erreur perfect_binding_split: {e}")
    
    def _calculate_signatures(self, total_pages: int, max_pages: int) -> List[Dict[str, Any]]:
        """
        Calcule le découpage optimal en cahiers
        
        Règle métier : Insérer les petits cahiers entre deux gros
        1. Premier cahier complet (16p si max=16)
        2. Quelques petits cahiers au milieu pour ajuster (8p, puis 4p si nécessaire)
        3. Terminer avec cahiers complets (16p)
        
        Exemple: 60 pages avec max=16
        -> C1: 16p (complet)
        -> C2: 8p  (ajustement)
        -> C3: 4p  (ajustement)
        -> C4: 16p (complet)
        -> C5: 16p (complet)
        Total: 16 + 8 + 4 + 16 + 16 = 60
        """
        signatures = []
        current_page = 1
        sig_number = 1
        
        # Étape 1 : Premier cahier complet
        if total_pages >= max_pages:
            signatures.append(self._make_signature(sig_number, current_page, max_pages, max_pages))
            current_page += max_pages
            sig_number += 1
        
        remaining = total_pages - current_page + 1
        
        # Étape 2 : Calculer combien de cahiers complets on peut faire avec le reste
        full_sigs_remaining = remaining // max_pages
        leftover = remaining % max_pages
        
        # Étape 3 : Si on a un reste non-multiple de max_pages, insérer des petits cahiers
        if leftover > 0 and full_sigs_remaining >= 1:
            # On a besoin d'ajuster avec des petits cahiers
            # Stratégie : décomposer le leftover en 8p + 4p si possible
            
            if leftover >= (max_pages // 2) + (max_pages // 4):
                # Leftover >= 12 (8+4) -> faire 8p + 4p
                signatures.append(self._make_signature(sig_number, current_page, max_pages // 2, max_pages))
                current_page += max_pages // 2
                sig_number += 1
                
                signatures.append(self._make_signature(sig_number, current_page, max_pages // 4, max_pages))
                current_page += max_pages // 4
                sig_number += 1
                
            elif leftover >= (max_pages // 2):
                # Leftover >= 8 -> faire un 8p
                signatures.append(self._make_signature(sig_number, current_page, max_pages // 2, max_pages))
                current_page += max_pages // 2
                sig_number += 1
                
            elif leftover >= (max_pages // 4):
                # Leftover >= 4 -> faire un 4p
                signatures.append(self._make_signature(sig_number, current_page, max_pages // 4, max_pages))
                current_page += max_pages // 4
                sig_number += 1
        
        # Étape 4 : Remplir avec des cahiers complets
        while current_page <= total_pages:
            remaining = total_pages - current_page + 1
            
            if remaining >= max_pages:
                pages = max_pages
            else:
                # Dernier cahier incomplet (normalement ne devrait pas arriver)
                pages = remaining
                if pages > 4:
                    pages = (pages // 4) * 4
                pages = max(4, pages)
            
            signatures.append(self._make_signature(sig_number, current_page, pages, max_pages))
            current_page += pages
            sig_number += 1
            
            # Sécurité
            if sig_number > 100:
                break
        
        return signatures
    
    def _make_signature(self, number: int, start: int, pages: int, max_pages: int) -> Dict[str, Any]:
        """Crée un dictionnaire de cahier"""
        end = start + pages - 1
        
        # Déterminer le format
        if pages >= max_pages:
            up_format = f"{max_pages // 2}up"
        elif pages >= max_pages // 2:
            up_format = f"{max_pages // 4}up"
        elif pages >= max_pages // 4:
            up_format = f"{max_pages // 8}up"
        else:
            up_format = "1up"
        
        return {
            "number": number,
            "start": start,
            "end": end,
            "pages": pages,
            "format": up_format
        }
    
    def _process_signature(
        self, 
        input_path: Path, 
        work_dir: Path, 
        base_name: str,
        signature: Dict[str, Any],
        sig_num: int,
        params: Dict[str, Any]
    ) -> str:
        """Traite un cahier individuel"""
        
        # Générer nom avec préfixe
        prefix_template = params["prefix"]
        prefix = prefix_template.replace("%nb%", str(sig_num))
        sig_filename = f"{prefix}{base_name}.pdf"
        sig_path = work_dir / sig_filename
        
        # Extraire pages
        pages_range = f"{signature['start']}-{signature['end']}"
        self.log_info(f"   📄 Cahier {sig_num}: pages {pages_range} ({signature['pages']}p = {signature['format']})")
        
        self._extract_pages(input_path, sig_path, pages_range)
        
        # Exécuter actions communes (si configurées)
        current_path = str(sig_path)
        route_actions = params.get("route_actions", [])
        
        if route_actions:
            from . import get_action
            
            for action_config in route_actions:
                action_type = action_config.get("type")
                if not action_type:
                    continue
                
                try:
                    action = get_action(action_type, action_config)
                    action.job_logger = self.job_logger
                    current_path = action.execute(current_path)
                except Exception as e:
                    raise ActionError(f"Cahier {sig_num}, action {action_type}: {e}")
        
        # Distribuer vers destinations appropriées
        destinations = params["destinations"].get(signature["format"], [])
        
        if destinations:
            self.log_info(f"   📤 Distribution vers {len(destinations)} destination(s) {signature['format']}")
            self._distribute_file(current_path, destinations)
        else:
            self.log_warning(f"   ⚠️ Aucune destination pour format {signature['format']}")
        
        return current_path
    
    def _distribute_file(self, file_path: str, destinations: List[str]):
        """Distribue un fichier vers plusieurs destinations"""
        file_path = Path(file_path)
        
        for dest in destinations:
            try:
                os.makedirs(dest, exist_ok=True)
                
                try:
                    os.chmod(dest, 0o777)
                except Exception:
                    pass
                
                dest_path = Path(dest) / file_path.name
                
                # Gérer doublons
                if dest_path.exists():
                    base, ext = os.path.splitext(file_path.name)
                    counter = 1
                    while dest_path.exists():
                        dest_path = Path(dest) / f"{base}_{counter}{ext}"
                        counter += 1
                    self.log_info(f"      ⚠️ Renommage: {dest_path.name}")
                
                shutil.copy2(file_path, dest_path)
                
                if not dest_path.exists():
                    raise ActionError(f"Échec copie vers {dest_path}")
                
                try:
                    os.chmod(dest_path, 0o666)
                except Exception:
                    pass
                
                self.log_info(f"      ✅ {dest_path}")
                
            except Exception as e:
                self.log_error(f"      ❌ Erreur distribution vers {dest}: {e}")
                raise ActionError(f"Distribution vers {dest}: {e}")
    
    def _extract_pages(self, input_path: Path, output_path: Path, pages: str):
        """Extrait des pages avec qpdf"""
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
            self.log_debug(f"      {page_count} pages, {size:,} bytes")
            
        except subprocess.TimeoutExpired:
            raise ActionError(f"Timeout extraction pages {pages}")
        except Exception as e:
            raise ActionError(f"Erreur extraction pages {pages}: {e}")
    
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