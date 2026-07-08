# ============================================================================
# FILE: /opt/elan/app/actions/extract_cutting.py
# VERSION : 15 - Architecture pipeline (comme split.py)
# ============================================================================

import os
from pathlib import Path
from typing import List, Dict, Set
from .base import Action, ActionError


class ExtractCuttingAction(Action):
    """
    Détecte les tons directs de découpe et génère deux versions :
    1. Simulation : avec découpe visible (route_simulation)
    2. Impression : sans découpe (route_print)
    """
    
    # Dictionnaire des noms de tons directs reconnus comme découpe/rainage
    CUTTING_SPOT_NAMES = {
        # Variations CutContour
        "CutContour", "cutcontour", "CUTCONTOUR", "Cut Contour",
        # Variations Découpe
        "Découpe", "découpe", "DÉCOUPE", "Decoupe", "decoupe", "DECOUPE",
        # Variations Rainage
        "Rainage", "rainage", "RAINAGE",
        # Variations DieCut
        "DieCut", "diecut", "DIECUT", "Die Cut", "Die-Cut",
        # Autres
        "Cut", "cut", "CUT",
        "Forme", "forme", "FORME",
        "Die", "die", "DIE",
        "Crease", "crease", "CREASE",
        "Pliage", "pliage", "PLIAGE",
        "Knife", "knife", "KNIFE",
        "Micro-perfo", "Micro-Perfo", "micro-perfo"
    }
    
    # Noms de calques reconnus comme découpe
    CUTTING_LAYER_NAMES = {
        "CutContour", "cutcontour", "CUTCONTOUR",
        "Découpe", "découpe", "DÉCOUPE",
        "Decoupe", "decoupe", "DECOUPE",
        "Rainage", "rainage", "RAINAGE",
        "Forme", "forme", "FORME",
        "Die", "die", "DIE",
    }
    
    @property
    def name(self) -> str:
        return "extract_cutting"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("simulation_suffix", "_simulation")
        params.setdefault("print_suffix", "_print")
        params.setdefault("detect_spots", True)
        params.setdefault("detect_layers", True)
        params.setdefault("custom_spot_names", [])
        params.setdefault("custom_layer_names", [])
        
        # Vérifier qu'au moins un des deux routes existe
        if "route_simulation" not in params and "route_print" not in params:
            raise ActionError("Au moins 'route_simulation' ou 'route_print' requis")
        
        # Valider route_simulation si présente
        if "route_simulation" in params:
            route = params["route_simulation"]
            if not isinstance(route, dict):
                raise ActionError("route_simulation doit être un dict")
            if "actions" not in route:
                raise ActionError("route_simulation: 'actions' manquant")
        
        # Valider route_print si présente
        if "route_print" in params:
            route = params["route_print"]
            if not isinstance(route, dict):
                raise ActionError("route_print doit être un dict")
            if "actions" not in route:
                raise ActionError("route_print: 'actions' manquant")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """
        Détecte la découpe et route vers les pipelines
        
        Returns:
            Chemin du dernier fichier généré (print en priorité)
        """
        params = self.config["params"]
        
        # Détecter le dossier de travail
        input_path = Path(file_path)
        work_dir = input_path.parent
        
        self.log_info(f"🔍 Détection découpe/rainage")
        
        try:
            # Analyser le PDF
            cutting_info = self._analyze_pdf(input_path, params)
            
            if not cutting_info["has_cutting"]:
                self.log_info("⚠️  Aucun ton de découpe détecté")
                # Pas de séparation, mais continuer quand même les routes
                # (utile si on veut quand même deux résolutions différentes)
            else:
                # Afficher ce qui a été détecté
                if cutting_info["spots"]:
                    self.log_info(f"   ✂️  Tons directs : {', '.join(cutting_info['spots'])}")
                if cutting_info["layers"]:
                    self.log_info(f"   📑 Calques : {', '.join(cutting_info['layers'])}")
            
            # Créer les deux versions
            simulation_path = None
            print_path = None
            
            # 1. Version SIMULATION (si route configurée)
            if "route_simulation" in params:
                self.log_info(f"🎨 Pipeline simulation...")
                
                # Créer une copie pour la simulation
                sim_name = f"{input_path.stem}{params['simulation_suffix']}{input_path.suffix}"
                simulation_path = work_dir / sim_name
                
                import shutil
                shutil.copy2(input_path, simulation_path)
                
                # Router à travers le pipeline simulation
                simulation_path = self._route_through_pipeline(
                    simulation_path,
                    params["route_simulation"],
                    "simulation"
                )
            
            # 2. Version IMPRESSION (si route configurée)
            if "route_print" in params:
                self.log_info(f"🖨️  Pipeline impression...")
                
                # Créer une copie pour l'impression
                print_name = f"{input_path.stem}{params['print_suffix']}{input_path.suffix}"
                print_path = work_dir / print_name
                
                import shutil
                shutil.copy2(input_path, print_path)
                
                # Supprimer les découpes si détectées
                if cutting_info["has_cutting"]:
                    self._remove_cutting_from_pdf(print_path, cutting_info)
                
                # Router à travers le pipeline impression
                print_path = self._route_through_pipeline(
                    print_path,
                    params["route_print"],
                    "impression"
                )
            
            # Retourner le fichier d'impression en priorité
            return str(print_path or simulation_path or input_path)
            
        except Exception as e:
            raise ActionError(f"Erreur extraction découpe: {e}")
    
    def _analyze_pdf(self, pdf_path: Path, params: dict) -> Dict:
        """
        Analyse le PDF pour détecter tons directs et calques de découpe
        """
        try:
            import pikepdf
            
            pdf = pikepdf.open(pdf_path)
            
            detected_spots = set()
            detected_layers = set()
            
            # Construire la liste complète des noms
            spot_names = set(self.CUTTING_SPOT_NAMES)
            layer_names = set(self.CUTTING_LAYER_NAMES)
            
            if params.get("custom_spot_names"):
                spot_names.update(params["custom_spot_names"])
            
            if params.get("custom_layer_names"):
                layer_names.update(params["custom_layer_names"])
            
            # Parcourir les pages
            for page in pdf.pages:
                # Détecter tons directs
                if params["detect_spots"]:
                    page_spots = self._find_spots_in_page(page, spot_names)
                    detected_spots.update(page_spots)
                
                # Détecter calques
                if params["detect_layers"]:
                    page_layers = self._find_layers_in_page(page, layer_names)
                    detected_layers.update(page_layers)
            
            pdf.close()
            
            return {
                "has_cutting": len(detected_spots) > 0 or len(detected_layers) > 0,
                "spots": list(detected_spots),
                "layers": list(detected_layers),
            }
            
        except Exception as e:
            raise ActionError(f"Erreur analyse PDF: {e}")
    
    def _find_spots_in_page(self, page, spot_names: Set[str]) -> Set[str]:
        """Recherche les tons directs dans une page"""
        import pikepdf
        detected = set()
        
        try:
            if "/Resources" not in page:
                return detected
            
            resources = page.Resources
            
            # Chercher dans /ColorSpace
            if "/ColorSpace" in resources:
                colorspaces = resources.ColorSpace
                
                for cs_name in colorspaces.keys():
                    try:
                        cs_value = colorspaces[cs_name]
                        
                        # Vérifier si c'est un Array pikepdf
                        if isinstance(cs_value, pikepdf.Array):
                            cs_list = list(cs_value)
                            
                            # [/Separation Name ...]
                            if len(cs_list) >= 2:
                                # Utiliser pikepdf.Name pour comparer proprement
                                cs_type = cs_list[0]
                                
                                if cs_type == pikepdf.Name.Separation:
                                    # Le nom du spot est en position 1
                                    spot_name_obj = cs_list[1]
                                    
                                    # Extraire le nom proprement
                                    if isinstance(spot_name_obj, pikepdf.Name):
                                        # pikepdf.Name a une représentation string propre
                                        spot_name = str(spot_name_obj)[1:]  # Enlever le / initial
                                    elif isinstance(spot_name_obj, (str, bytes)):
                                        try:
                                            spot_name = spot_name_obj.decode('latin-1') if isinstance(spot_name_obj, bytes) else spot_name_obj
                                            spot_name = spot_name.strip("/").strip()
                                        except Exception:
                                            continue
                                    else:
                                        continue
                                    
                                    self.log_debug(f"   Ton trouvé : '{spot_name}'")
                                    
                                    # Vérifier si c'est un nom de découpe
                                    if spot_name in spot_names:
                                        detected.add(spot_name)
                                        self.log_debug(f"   ✂️  Match : {spot_name}")
                    except Exception as e:
                        self.log_debug(f"Erreur traitement ColorSpace {cs_name}: {e}")
                        continue
            
            # Chercher récursivement dans les XObjects
            if "/XObject" in resources:
                xobjects = resources.XObject
                
                for xobj_name in xobjects.keys():
                    try:
                        xobj = xobjects[xobj_name]
                        
                        if "/Resources" in xobj:
                            sub_spots = self._find_spots_in_page(xobj, spot_names)
                            detected.update(sub_spots)
                    except Exception as e:
                        self.log_debug(f"Erreur traitement XObject {xobj_name}: {e}")
                        continue
            
        except Exception as e:
            self.log_debug(f"Erreur recherche spots: {e}")
        
        return detected
    
    def _find_layers_in_page(self, page, layer_names: Set[str]) -> Set[str]:
        """Recherche les calques PDF dans une page"""
        import pikepdf
        detected = set()
        
        try:
            if "/Resources" not in page:
                return detected
            
            resources = page.Resources
            
            if "/Properties" in resources:
                properties = resources.Properties
                
                # Utiliser .keys() au lieu de .values()
                for prop_name in properties.keys():
                    try:
                        prop_value = properties[prop_name]
                        
                        if "/Name" in prop_value:
                            layer_name_obj = prop_value.Name
                            
                            # Extraire le nom proprement
                            if isinstance(layer_name_obj, pikepdf.Name):
                                layer_name = str(layer_name_obj)[1:]  # Enlever le / initial
                            elif isinstance(layer_name_obj, pikepdf.String):
                                layer_name = str(layer_name_obj)
                            else:
                                try:
                                    layer_name = str(layer_name_obj).strip("/").strip()
                                except Exception:
                                    continue
                            
                            self.log_debug(f"   Calque trouvé : '{layer_name}'")
                            
                            if layer_name in layer_names:
                                detected.add(layer_name)
                                self.log_debug(f"   📑 Match : {layer_name}")
                    except Exception as e:
                        self.log_debug(f"Erreur traitement Property {prop_name}: {e}")
                        continue
            
        except Exception as e:
            self.log_debug(f"Erreur recherche calques: {e}")
        
        return detected
    
    def _remove_cutting_from_pdf(self, pdf_path: Path, cutting_info: Dict):
        """
        Supprime les tons directs de découpe du PDF
        
        Approche robuste :
        1. Pour les calques : désactiver la visibilité + aplatir avec Ghostscript
        2. Pour les tons directs : identifier et filtrer le contenu
        """
        try:
            import pikepdf
            
            spots_to_remove = set(cutting_info["spots"])
            layers_to_remove = set(cutting_info["layers"])
            
            self.log_info(f"   🧹 Suppression des découpes...")
            
            if layers_to_remove:
                # Méthode CALQUES : désactiver + aplatir
                self.log_info(f"   📑 Désactivation des calques...")
                self._hide_layers(pdf_path, layers_to_remove)
                
                # Aplatir avec Ghostscript
                self.log_info(f"   🎨 Aplatissement du PDF...")
                self._flatten_pdf_with_gs(pdf_path)
            
            elif spots_to_remove:
                # Méthode TONS DIRECTS : nettoyage pikepdf
                self.log_info(f"   ✂️  Suppression des tons directs...")
                
                pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)
                pages_cleaned = 0
                
                for page in pdf.pages:
                    cleaned = self._remove_spot_colors_from_page(page, spots_to_remove)
                    if cleaned:
                        pages_cleaned += 1
                
                pdf.save()
                pdf.close()
                
                self.log_info(f"   ✅ {pages_cleaned} page(s) nettoyée(s)")
            
        except Exception as e:
            self.log_error(f"Erreur suppression découpe: {e}")
    
    def _hide_layers(self, pdf_path: Path, layers: Set[str]):
        """
        Désactive la visibilité des calques dans OCProperties
        
        IMPORTANT: Après cette opération, il FAUT aplatir le PDF avec GS
        car GS en mode tiffsep/tiff32nc (raster) ignore les calques cachés !
        """
        try:
            import pikepdf
            
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)
            
            # Accéder au catalogue
            if "/OCProperties" not in pdf.Root:
                self.log_warning("Pas de OCProperties trouvé")
                pdf.close()
                return
            
            oc_props = pdf.Root.OCProperties
            
            if "/OCGs" not in oc_props:
                pdf.close()
                return
            
            # Identifier les OCG à désactiver
            ocgs_to_hide = []
            
            for ocg in oc_props.OCGs:
                if "/Name" in ocg:
                    layer_name_obj = ocg.Name
                    
                    if isinstance(layer_name_obj, pikepdf.Name):
                        layer_name = str(layer_name_obj)[1:]
                    else:
                        layer_name = str(layer_name_obj).strip("/").strip()
                    
                    if layer_name in layers:
                        ocgs_to_hide.append(ocg)
                        self.log_debug(f"   Calque à masquer : {layer_name}")
            
            if not ocgs_to_hide:
                pdf.close()
                return
            
            # Créer/modifier la configuration par défaut pour cacher ces calques
            if "/D" not in oc_props:
                oc_props.D = pikepdf.Dictionary()
            
            d_config = oc_props.D
            
            # Ajouter à la liste "OFF" (calques désactivés)
            if "/OFF" not in d_config:
                d_config.OFF = pikepdf.Array()
            
            for ocg in ocgs_to_hide:
                if ocg not in d_config.OFF:
                    d_config.OFF.append(ocg)
            
            pdf.save()
            pdf.close()
            
            self.log_info(f"   ✅ {len(ocgs_to_hide)} calque(s) masqué(s)")
            
        except Exception as e:
            self.log_error(f"Erreur masquage calques: {e}")
    
    def _flatten_pdf_with_gs(self, pdf_path: Path):
        """
        Aplatit le PDF avec Ghostscript pour appliquer les calques cachés
        
        Utilise pdfwrite pour respecter l'état des calques et générer
        un PDF propre sans Optional Content.
        
        ATTENTION: Cette opération peut prendre du temps sur de gros PDF !
        Si le raster suit immédiatement après, on pourrait optimiser en
        rasterisant directement, mais GS en mode image IGNORE les calques.
        """
        import subprocess
        
        temp_path = pdf_path.parent / f"{pdf_path.stem}_flattened.pdf"
        
        gs_cmd = [
            "gs",
            "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/prepress",
            "-dPreserveAnnots=false",  # Pas besoin des annotations
            "-dPreserveOPI=false",
            "-dUseCIEColor",  # Préserver les couleurs
            f"-sOutputFile={temp_path}",
            str(pdf_path)
        ]
        
        try:
            result = subprocess.run(
                gs_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise ActionError(f"Ghostscript flatten: {result.stderr}")
            
            if not temp_path.exists():
                raise ActionError("PDF aplati non créé")
            
            # Remplacer l'original
            import shutil
            shutil.move(str(temp_path), str(pdf_path))
            
            self.log_info(f"   ✅ PDF aplati (calques supprimés)")
            
        except subprocess.TimeoutExpired:
            raise ActionError("Timeout aplatissement (PDF trop gros ?)")
        except Exception as e:
            raise ActionError(f"Erreur aplatissement: {e}")
    
    def _remove_spot_colors_from_page(self, page, spots: Set[str]) -> bool:
        """
        Supprime les objets graphiques utilisant des tons directs de découpe
        
        Approche : filtrer le stream de contenu en supprimant les blocs q...Q
        qui contiennent une référence aux ColorSpace de découpe
        """
        import pikepdf
        import re
        
        try:
            # Identifier les noms de ColorSpace à supprimer
            cs_names = []
            
            if "/Resources" not in page or "/ColorSpace" not in page.Resources:
                return False
            
            colorspaces = page.Resources.ColorSpace
            
            for cs_name in list(colorspaces.keys()):
                try:
                    cs_value = colorspaces[cs_name]
                    
                    if isinstance(cs_value, pikepdf.Array):
                        cs_list = list(cs_value)
                        
                        if len(cs_list) >= 2 and cs_list[0] == pikepdf.Name.Separation:
                            spot_name_obj = cs_list[1]
                            
                            if isinstance(spot_name_obj, pikepdf.Name):
                                spot_name = str(spot_name_obj)[1:]
                            else:
                                spot_name = str(spot_name_obj).strip("/").strip()
                            
                            if spot_name in spots:
                                cs_key = str(cs_name)[1:] if str(cs_name).startswith("/") else str(cs_name)
                                cs_names.append(cs_key)
                                self.log_debug(f"   ColorSpace à supprimer : /{cs_key} ({spot_name})")
                except Exception:
                    continue
            
            if not cs_names:
                return False
            
            # Supprimer les ColorSpace des ressources
            for cs_name in cs_names:
                cs_key = pikepdf.Name(f"/{cs_name}")
                if cs_key in colorspaces:
                    del colorspaces[cs_key]
            
            # Nettoyer le contenu de la page
            if not hasattr(page, 'Contents') or page.Contents is None:
                return True  # Resources nettoyés au moins
            
            # Lire le stream
            if isinstance(page.Contents, pikepdf.Array):
                content_bytes = b""
                for stream in page.Contents:
                    content_bytes += bytes(stream.read_bytes())
            else:
                content_bytes = bytes(page.Contents.read_bytes())
            
            try:
                content_str = content_bytes.decode('latin-1')
            except Exception:
                return True  # Pas pu nettoyer le contenu, mais Resources OK
            
            # Filtrer le contenu : supprimer les blocs q...Q contenant les ColorSpace
            modified_content = self._filter_content_blocks(content_str, cs_names)
            
            if modified_content != content_str:
                # ✅ CORRECTION v13 : Utiliser parse_content_stream pour réécrire proprement
                # On écrase le contenu existant avec le nouveau
                page.Contents = pikepdf.Stream(page.obj.pdf, modified_content.encode('latin-1'))
            
            return True
            
        except Exception as e:
            self.log_debug(f"Erreur suppression tons directs: {e}")
            return False
    
    def _filter_content_blocks(self, content: str, cs_names: List[str]) -> str:
        """
        Filtre les blocs q...Q qui utilisent les ColorSpace de découpe
        
        Stratégie simple : supprimer tout bloc q...Q contenant cs_name cs ou CS
        """
        import re
        
        # Split en blocs q...Q
        # Pattern: q ... Q
        blocks = []
        current_block = []
        depth = 0
        
        for line in content.split('\n'):
            line_stripped = line.strip()
            
            if line_stripped == 'q':
                depth += 1
                current_block.append(line)
            elif line_stripped == 'Q':
                current_block.append(line)
                depth -= 1
                
                if depth == 0 and current_block:
                    # Bloc complet, vérifier si on le garde
                    block_content = '\n'.join(current_block)
                    
                    # Chercher si le bloc utilise un des ColorSpace à supprimer
                    uses_cutting_cs = False
                    for cs_name in cs_names:
                        if f'/{cs_name} cs' in block_content or f'/{cs_name} CS' in block_content:
                            uses_cutting_cs = True
                            self.log_debug(f"   Suppression bloc utilisant /{cs_name}")
                            break
                    
                    if not uses_cutting_cs:
                        blocks.append(block_content)
                    
                    current_block = []
            else:
                current_block.append(line)
        
        # Ajouter le reste (en dehors des blocs q...Q)
        if current_block:
            blocks.append('\n'.join(current_block))
        
        return '\n'.join(blocks)
    
    def _route_through_pipeline(self, file_path: Path, route_config: dict, label: str) -> str:
        """Execute le pipeline d'actions + distribution"""
        from . import get_action
        
        actions_config = route_config.get("actions", [])
        destinations = route_config.get("destinations", [])
        
        if not actions_config:
            self.log_info(f"   ⚠️  Pipeline {label}: aucune action")
            return str(file_path)
        
        current_path = str(file_path)
        
        self.log_info(f"   📋 Pipeline {label}: {len(actions_config)} action(s)")
        
        # Exécuter les actions
        for i, action_config in enumerate(actions_config, 1):
            action_type = action_config.get("type")
            if not action_type:
                raise ActionError(f"Pipeline {label}, action #{i}: type manquant")
            
            try:
                action = get_action(action_type, action_config)
                self.log_info(f"   ⚙️  {label} - Action {i}/{len(actions_config)}: {action.name}")
                current_path = action.execute(current_path)
            except Exception as e:
                raise ActionError(f"Pipeline {label}, action {action_type}: {e}")
        
        # Distribuer vers destinations (si présentes)
        if destinations:
            if isinstance(destinations, str):
                destinations = [destinations]
            
            self.log_info(f"   📤 Distribution {label} vers {len(destinations)} destination(s)")
            
            import shutil
            for dest in destinations:
                os.makedirs(dest, exist_ok=True)
                
                try:
                    os.chmod(dest, 0o777)
                except Exception:
                    pass
                
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
                
                shutil.copy2(current_path, dest_path)
                
                try:
                    os.chmod(dest_path, 0o666)
                except Exception:
                    pass
                
                self.log_info(f"      ✅ {dest_path}")
        
        return current_path