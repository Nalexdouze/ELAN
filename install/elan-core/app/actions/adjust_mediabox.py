# ============================================================================
# FILE: /opt/elan/app/actions/adjust_mediabox.py
# VERSION : 9.0 - Refactorisation: utilisation directe de pikepdf
# ============================================================================

import os
from pathlib import Path
from .base import Action, ActionError


class AdjustMediaboxAction(Action):
    """Ajuste la MediaBox d'un PDF (TrimBox + marge, centré)"""
    
    @property
    def name(self) -> str:
        return "adjust_mediabox"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("margin_mm", 3)           # Marge en mm de chaque côté
        params.setdefault("use_trimbox", True)      # Utiliser TrimBox comme référence
        params.setdefault("fallback_to_cropbox", True)  # Si pas de TrimBox, utiliser CropBox
        params.setdefault("center_content", True)   # Centrer le contenu
        params.setdefault("all_pages", True)        # Appliquer à toutes les pages
        params.setdefault("output_suffix", "_adjusted")
        
        # Validation
        if params["margin_mm"] < 0:
            raise ActionError("margin_mm doit être >= 0")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """
        Ajuste la MediaBox du PDF
        
        Config attendue:
        {
            "params": {
                "margin_mm": 3,                  # Marge en mm (de chaque côté)
                "use_trimbox": true,             # Utiliser TrimBox comme référence
                "fallback_to_cropbox": true,     # Fallback sur CropBox si pas de TrimBox
                "center_content": true,          # Centrer le contenu dans la nouvelle MediaBox
                "all_pages": true,               # Appliquer à toutes les pages
                "output_suffix": "_adjusted"
            }
        }
        
        Exemple: TrimBox 210x297mm + margin 3mm = MediaBox 216x303mm
        """
        params = self.config["params"]
        
        # Détecter le dossier de travail (genstore du job)
        input_path = Path(file_path)
        work_dir = input_path.parent
        
        self.log_info(f"🔨 Ajustement MediaBox dans: {work_dir.name}")
        
        try:
            # Construire le nom de sortie
            output_suffix = params["output_suffix"]
            output_name = f"{input_path.stem}{output_suffix}{input_path.suffix}"
            output_path = work_dir / output_name
            
            # Traiter le PDF directement avec pikepdf
            self._process_pdf(input_path, output_path, params)
            
            # Vérifier que le fichier de sortie existe
            if not output_path.exists():
                raise ActionError(f"Fichier de sortie non créé: {output_path}")

            self.log_info(f"✅ MediaBox ajustée: {output_path}")
            
            return str(output_path) 
            
        except Exception as e:
            raise ActionError(f"Erreur ajustement: {e}")
    
    def _process_pdf(self, input_path: Path, output_path: Path, params: dict):
        """Traite le PDF avec pikepdf directement"""
        try:
            import pikepdf
            
            # Convertir marge mm → points
            margin_mm = params["margin_mm"]
            margin_pt = margin_mm * 2.83465
            
            pdf = pikepdf.open(input_path)
            pages_adjusted = 0
            
            use_trimbox = params["use_trimbox"]
            fallback_to_cropbox = params["fallback_to_cropbox"]
            center_content = params["center_content"]
            all_pages = params["all_pages"]
            
            for page_num, page in enumerate(pdf.pages):
                # Déterminer la boîte de référence
                ref_box = None
                box_name = None
                
                if use_trimbox and "/TrimBox" in page:
                    ref_box = page.TrimBox
                    box_name = "TrimBox"
                elif fallback_to_cropbox and "/CropBox" in page:
                    ref_box = page.CropBox
                    box_name = "CropBox"
                elif "/MediaBox" in page:
                    ref_box = page.MediaBox
                    box_name = "MediaBox (original)"
                else:
                    self.log_debug(f"⚠️  Page {page_num+1}: Aucune boîte de référence trouvée")
                    continue
                
                # Récupérer les coordonnées [x1, y1, x2, y2]
                x1, y1, x2, y2 = [float(v) for v in ref_box]
                width = x2 - x1
                height = y2 - y1
                
                # Calculer la nouvelle MediaBox avec marge
                new_width = width + (2 * margin_pt)
                new_height = height + (2 * margin_pt)
                
                if center_content:
                    # Centrer: déplacer l'origine pour garder le contenu au centre
                    new_x1 = x1 - margin_pt
                    new_y1 = y1 - margin_pt
                    new_x2 = x2 + margin_pt
                    new_y2 = y2 + margin_pt
                else:
                    # Garder l'origine, étendre vers le haut/droite
                    new_x1 = x1
                    new_y1 = y1
                    new_x2 = x1 + new_width
                    new_y2 = y1 + new_height
                
                # Appliquer la nouvelle MediaBox
                page.MediaBox = [new_x1, new_y1, new_x2, new_y2]
                
                pages_adjusted += 1
                self.log_info(f"✅ Page {page_num+1}: {box_name} {width:.1f}×{height:.1f}pt → MediaBox {new_width:.1f}×{new_height:.1f}pt")
                
                if not all_pages:
                    break  # Seulement la première page
            
            # Sauvegarder
            pdf.save(output_path)
            pdf.close()
            
            self.log_info(f"✅ {pages_adjusted} page(s) ajustée(s)")
            
        except ImportError:
            raise ActionError("pikepdf non disponible. Installer avec: pip install pikepdf")
        except Exception as e:
            raise ActionError(f"Erreur traitement PDF: {e}")