# ============================================================================
# FILE: /opt/elan/app/actions/add_trim_guide.py
# VERSION : 58.13 - Complet: TrimBox + BleedBox + Plis + Côtes (tons directs + couleurs)
# ============================================================================

import os
import re
from pathlib import Path
from .base import Action, ActionError


class AddTrimGuideAction(Action):
    """Ajoute un rectangle en pointillé sur la TrimBox + repères de plis optionnels + côtes"""
    
    @property
    def name(self) -> str:
        return "add_trim_guide"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("stroke_width", 0.75)
        params.setdefault("dash_pattern", "2,2")
        params.setdefault("color", "magenta")
        params.setdefault("spot_name", "BL-TrimBox")
        params.setdefault("overprint", True)
        params.setdefault("use_trimbox", True)
        params.setdefault("fallback_to_mediabox", True)
        params.setdefault("all_pages", True)
        params.setdefault("output_suffix", "_trimguide")
        
        # Fold guides
        params.setdefault("fold_guides", True)
        params.setdefault("fold_color", "green")
        params.setdefault("fold_pattern", "3,3")
        params.setdefault("fold_vertical", None)
        params.setdefault("fold_horizontal", None)
        params.setdefault("fold_spot_name", "BL-Fold")
        
        # Côtes (dimensions)
        params.setdefault("dimensions", True)
        params.setdefault("dimension_offset", 6)     # Distance TrimBox → flèche (mm)
        params.setdefault("dimension_text_size", 8)   # Taille police (pt)
        params.setdefault("dimension_arrow_size", 2)  # Taille tête flèche (mm)
        params.setdefault("dimensions_color", "black")
        params.setdefault("dimensions_spot_name", "BL-Dimensions")
        
        # BleedBox (rectangle de fond perdu)
        params.setdefault("bleed_box", True)
        params.setdefault("bleed_color", "cyan")
        params.setdefault("bleed_spot_name", "BL-Bleed")
        
        # Validation couleur
        valid_colors = ["magenta", "cyan", "yellow", "black", "registration", "green", "red", "blue"]
        if params["color"] not in valid_colors:
            raise ActionError(f"color doit être: {', '.join(valid_colors)}")
        
        if params["fold_color"] not in valid_colors:
            raise ActionError(f"fold_color doit être: {', '.join(valid_colors)}")
        
        if params["dimensions_color"] not in valid_colors:
            raise ActionError(f"dimensions_color doit être: {', '.join(valid_colors)}")
        
        if params["bleed_color"] not in valid_colors:
            raise ActionError(f"bleed_color doit être: {', '.join(valid_colors)}")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """Ajoute le rectangle de simulation de rogne + repères de plis + côtes"""
        params = self.config["params"]
        
        # Détection automatique des fold guides
        fold_info = self._parse_fold_from_filename(file_path, params) if params["fold_guides"] else None
        
        if fold_info:
            self.log_info(f"📐 Plis détectés: {fold_info['type']}")
            if fold_info.get("vertical"):
                v_data = fold_info["vertical"]
                if isinstance(v_data, (int, float)):
                    self.log_info(f"   Vertical: {v_data} mm (identique)")
                else:
                    self.log_info(f"   Vertical: {v_data} mm")
            if fold_info.get("horizontal"):
                h_data = fold_info["horizontal"]
                if isinstance(h_data, (int, float)):
                    self.log_info(f"   Horizontal: {h_data} mm (identique)")
                else:
                    self.log_info(f"   Horizontal: {h_data} mm")
        
        # Détecter le dossier de travail (genstore du job)
        input_path = Path(file_path)
        work_dir = input_path.parent
        
        self.log_info(f"🔨 Ajout repères dans: {work_dir.name}")
        
        try:
            # Construire le nom de sortie
            output_suffix = params["output_suffix"]
            output_name = f"{input_path.stem}{output_suffix}{input_path.suffix}"
            output_path = work_dir / output_name
            
            # Traiter le PDF avec pikepdf
            self._process_pdf(input_path, output_path, params, fold_info)
            
            # Vérifier que le fichier de sortie existe
            if not output_path.exists():
                raise ActionError(f"Fichier de sortie non créé: {output_path}")
            
            self.log_progress(f"✅ Guide de rogne ajouté: {output_path}")
                        
            return str(output_path)
            
        except Exception as e:
            raise ActionError(f"Erreur ajouts repères: {e}")
    
    def _parse_fold_from_filename(self, file_path: str, params: dict):
        """
        Parse le nom de fichier pour détecter les repères de plis
        
        Formats supportés:
        - "Depliant-146.5-148.5-148.5" → 3 volets, 2 repères
        - "Depliant-V100" → Division auto selon TrimBox
        - "Plan-V100-H210" → V=100mm de large, H=210mm de haut (identique si une seule valeur)
        """
        filename = Path(file_path).stem
        self.log_debug(f"Parse fold guides dans: {filename}")
        
        # Pattern 1: Depliant/Leaflet-XXX-XXX-XXX ou Depliant-VXXX
        pattern_depliant = r'(?:Depliant|Leaflet|DEPLIANT|LEAFLET)[-_](V)?(\d+(?:[.,]\d+)?(?:[-_]\d+(?:[.,]\d+)?)*)'
        match = re.search(pattern_depliant, filename, re.IGNORECASE)
        
        if match:
            is_auto = match.group(1) is not None
            values_str = match.group(2)
            values = [float(v.replace(',', '.')) for v in re.split(r'[-_]', values_str)]
            
            if is_auto and len(values) == 1:
                self.log_debug(f"Depliant auto-division détecté: {values[0]}mm")
                return {
                    "type": "depliant_auto",
                    "vertical": values[0],
                    "horizontal": None
                }
            else:
                self.log_debug(f"Depliant détecté: {values} mm ({len(values)} volets)")
                return {
                    "type": "depliant",
                    "vertical": values,
                    "horizontal": None
                }

        # Pattern 2: Plan_V97-105-105_H80-80-50 ou Plan-V97-105-105-H80-80-50
        pattern_plan = r'Plan[_\-]V([\d.,]+(?:-[\d.,]+)*)(?:[_\-]H([\d.,]+(?:-[\d.,]+)*))?'
        match = re.search(pattern_plan, filename, re.IGNORECASE)
        
        if match:
            v_str = match.group(1)  # "97-105-105"
            h_str = match.group(2)  # "80-80-50" ou None
            
            # Parse vertical (peut être une liste ou une seule valeur)
            v_parts = re.split(r'-', v_str)
            v_values = [float(v.replace(',', '.')) for v in v_parts if v]
            
            # Parse horizontal si présent (peut être une liste ou une seule valeur)
            h_values = None
            if h_str:
                h_parts = re.split(r'-', h_str)
                h_values = [float(v.replace(',', '.')) for v in h_parts if v]
            
            # Déterminer si les volets sont de dimensions identiques ou différentes 
            if len(v_values) == 1:
                v_data = v_values[0]  # Float = identique
            else:
                v_data = v_values  # Liste = largeurs relatives
            
            if h_values:
                if len(h_values) == 1:
                    h_data = h_values[0]  # Float = identique
                else:
                    h_data = h_values  # Liste = hauteurs relatives
            else:
                h_data = None
            
            self.log_debug(f"Plan détecté: V={v_data}, H={h_data}")
            
            return {
                "type": "plan",
                "vertical": v_data,
                "horizontal": h_data
            }
        
        # Override manuel
        if params.get("fold_vertical") or params.get("fold_horizontal"):
            self.log_debug(f"Plis manuels: V={params.get('fold_vertical')}, H={params.get('fold_horizontal')}")
            return {
                "type": "manual",
                "vertical": params.get("fold_vertical"),
                "horizontal": params.get("fold_horizontal")
            }
        
        return None
    
    def _process_pdf(self, input_path: Path, output_path: Path, params: dict, fold_info: dict = None):
        """Traite le PDF avec pikepdf directement"""
        try:
            import pikepdf
            
            pdf = pikepdf.open(input_path)
            pages_processed = 0
            
            use_trimbox = params["use_trimbox"]
            fallback_to_mediabox = params["fallback_to_mediabox"]
            all_pages = params["all_pages"]
            
            for page_num, page in enumerate(pdf.pages):
                # Déterminer la boîte à utiliser
                ref_box = None
                box_name = None
                
                if use_trimbox and "/TrimBox" in page:
                    ref_box = page.TrimBox
                    box_name = "TrimBox"
                elif fallback_to_mediabox and "/MediaBox" in page:
                    ref_box = page.MediaBox
                    box_name = "MediaBox"
                else:
                    self.log_debug(f"⚠️  Page {page_num+1}: Aucune boîte trouvée")
                    continue
                
                # Récupérer les coordonnées [x1, y1, x2, y2]
                x1, y1, x2, y2 = [float(v) for v in ref_box]
                
                # Ajouter le rectangle de BleedBox si demandé et si elle existe
                if params.get("bleed_box") and "/BleedBox" in page:
                    bleed_box = page.BleedBox
                    bleed_x1, bleed_y1, bleed_x2, bleed_y2 = [float(v) for v in bleed_box]
                    self._add_bleed_box(page, bleed_x1, bleed_y1, bleed_x2, bleed_y2, params, pdf)
                
                # Ajouter le rectangle de trim
                self._add_trim_rectangle(page, x1, y1, x2, y2, params, pdf)
                
                # Ajouter les fold guides si présents
                if fold_info and (fold_info.get("vertical") is not None or fold_info.get("horizontal") is not None):
                    self._add_fold_guides(page, page_num, x1, y1, x2, y2, fold_info, params, pdf)
                
                pages_processed += 1
                self.log_progress(f"✅ Page {page_num+1}: {box_name} {x2-x1:.1f}×{y2-y1:.1f}pt")
                
                if not all_pages:
                    break
            
            # Sauvegarder
            pdf.save(output_path)
            pdf.close()
            
            self.log_info(f"✅ {pages_processed} page(s) traitée(s)")
            
        except Exception as e:
            raise ActionError(f"Erreur traitement PDF: {e}")
    
    def _add_trim_rectangle(self, page, x1, y1, x2, y2, params: dict, pdf):
        """Ajoute le rectangle de simulation de rogne"""
        import pikepdf
        
        stroke_width = params["stroke_width"]
        color = params["color"]
        spot_name = params.get("spot_name")
        overprint = params["overprint"]
        
        # Dash pattern
        dash_pattern = params["dash_pattern"]
        dash_parts = dash_pattern.split(",")
        dash_on_mm = float(dash_parts[0])
        dash_off_mm = float(dash_parts[1]) if len(dash_parts) > 1 else dash_on_mm
        dash_on_pt = dash_on_mm * 2.83465
        dash_off_pt = dash_off_mm * 2.83465
        
        # Déterminer si on utilise un ton direct
        use_spot = spot_name is not None and spot_name != ""
        
        if use_spot:
            # Mode ton direct
            self._add_trim_rectangle_spot(page, x1, y1, x2, y2, stroke_width, 
                                         dash_on_pt, dash_off_pt, spot_name, 
                                         color, overprint, pdf)
        else:
            # Mode process CMYK
            self._add_trim_rectangle_process(page, x1, y1, x2, y2, stroke_width,
                                            dash_on_pt, dash_off_pt, color, 
                                            overprint, pdf)
    
    def _add_trim_rectangle_process(self, page, x1, y1, x2, y2, stroke_width,
                                   dash_on_pt, dash_off_pt, color, overprint, pdf):
        """Ajoute le rectangle en mode process CMYK"""
        import pikepdf
        
        # Couleurs CMYK
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(color, (0, 1, 0, 0))
        
        # Construire le stream
        stream = f"q\n"
        stream += f"/OC /OC_BlueLines BDC\n"
        stream += f"{c} {m} {y} {k} K\n"
        stream += f"{stroke_width} w\n"
        stream += f"[{dash_on_pt} {dash_off_pt}] 0 d\n"
        
        if overprint:
            stream += "/GS1 gs\n"
        
        stream += f"{x1} {y1} {x2 - x1} {y2 - y1} re\n"
        stream += "S\n"
        stream += "EMC\n"
        stream += "Q\n"
        
        # Créer ExtGState si overprint
        if overprint:
            if "/ExtGState" not in page.Resources:
                page.Resources.ExtGState = pikepdf.Dictionary()
            
            page.Resources.ExtGState.GS1 = pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState,
                OP=True,
                op=True,
                OPM=1
            )
        
        # Créer le calque BlueLines
        self._ensure_layer(page, pdf, "BlueLines", "OC_BlueLines")
        
        # Ajouter au contenu de la page
        self._append_content(page, stream, pdf)
    
    def _add_trim_rectangle_spot(self, page, x1, y1, x2, y2, stroke_width,
                                 dash_on_pt, dash_off_pt, spot_name, 
                                 fallback_color, overprint, pdf):
        """Ajoute le rectangle en mode ton direct"""
        import pikepdf
        
        # Fallback CMYK selon la couleur
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(fallback_color, (0, 1, 0, 0))
        
        # Créer le Separation color space
        if "/ColorSpace" not in page.Resources:
            page.Resources.ColorSpace = pikepdf.Dictionary()
        
        page.Resources.ColorSpace.CS_TrimBox = pikepdf.Array([
            pikepdf.Name.Separation,
            pikepdf.Name(f"/{spot_name}"),
            pikepdf.Name.DeviceCMYK,
            pikepdf.Dictionary(
                FunctionType=2,
                Domain=[0, 1],
                Range=[0, 1, 0, 1, 0, 1, 0, 1],
                C0=[0, 0, 0, 0],
                C1=[c, m, y, k],
                N=1
            )
        ])
        
        # Construire le stream
        stream = f"q\n"
        stream += f"/OC /OC_BlueLines BDC\n"
        stream += f"/CS_TrimBox CS\n"
        stream += f"1 SCN\n"
        stream += f"{stroke_width} w\n"
        stream += f"[{dash_on_pt} {dash_off_pt}] 0 d\n"
        
        if overprint:
            stream += "/GS1 gs\n"
        
        stream += f"{x1} {y1} {x2 - x1} {y2 - y1} re\n"
        stream += "S\n"
        stream += "EMC\n"
        stream += "Q\n"
        
        # Créer ExtGState si overprint
        if overprint:
            if "/ExtGState" not in page.Resources:
                page.Resources.ExtGState = pikepdf.Dictionary()
            
            page.Resources.ExtGState.GS1 = pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState,
                OP=True,
                op=True,
                OPM=1
            )
        
        # Créer le calque BlueLines
        self._ensure_layer(page, pdf, "BlueLines", "OC_BlueLines")
        
        # Ajouter au contenu
        self._append_content(page, stream, pdf)
    
    def _add_bleed_box(self, page, x1, y1, x2, y2, params: dict, pdf):
        """Ajoute le rectangle de fond perdu (BleedBox)"""
        import pikepdf
        
        stroke_width = params["stroke_width"]
        color = params["bleed_color"]
        spot_name = params.get("bleed_spot_name")
        overprint = params["overprint"]
        
        # Même dash pattern que TrimBox
        dash_pattern = params["dash_pattern"]
        dash_parts = dash_pattern.split(",")
        dash_on_mm = float(dash_parts[0])
        dash_off_mm = float(dash_parts[1]) if len(dash_parts) > 1 else dash_on_mm
        dash_on_pt = dash_on_mm * 2.83465
        dash_off_pt = dash_off_mm * 2.83465
        
        # Déterminer si on utilise un ton direct
        use_spot = spot_name is not None and spot_name != ""
        
        # Couleurs CMYK
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(color, (1, 0, 0, 0))
        
        # Construire le stream
        stream = f"q\n"
        stream += f"/OC /OC_BlueLines BDC\n"
        
        if use_spot:
            # Créer le Separation color space pour BleedBox
            if "/ColorSpace" not in page.Resources:
                page.Resources.ColorSpace = pikepdf.Dictionary()
            
            page.Resources.ColorSpace.CS_BleedBox = pikepdf.Array([
                pikepdf.Name.Separation,
                pikepdf.Name(f"/{spot_name}"),
                pikepdf.Name.DeviceCMYK,
                pikepdf.Dictionary(
                    FunctionType=2,
                    Domain=[0, 1],
                    Range=[0, 1, 0, 1, 0, 1, 0, 1],
                    C0=[0, 0, 0, 0],
                    C1=[c, m, y, k],
                    N=1
                )
            ])
            
            stream += f"/CS_BleedBox CS\n"
            stream += f"1 SCN\n"
        else:
            stream += f"{c} {m} {y} {k} K\n"
        
        stream += f"{stroke_width} w\n"
        stream += f"[{dash_on_pt} {dash_off_pt}] 0 d\n"
        
        if overprint:
            stream += "/GS1 gs\n"
        
        stream += f"{x1} {y1} {x2 - x1} {y2 - y1} re\n"
        stream += "S\n"
        stream += "EMC\n"
        stream += "Q\n"
        
        # Créer ExtGState si overprint
        if overprint:
            if "/ExtGState" not in page.Resources:
                page.Resources.ExtGState = pikepdf.Dictionary()
            
            page.Resources.ExtGState.GS1 = pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState,
                OP=True,
                op=True,
                OPM=1
            )
        
        # Ajouter au contenu
        self._append_content(page, stream, pdf)
    
    def _ensure_layer(self, page, pdf, layer_name: str, oc_name: str):
        """Crée un calque PDF (Optional Content Group) s'il n'existe pas"""
        import pikepdf
        
        # S'assurer que le catalogue a OCProperties
        if "/OCProperties" not in pdf.Root:
            pdf.Root.OCProperties = pikepdf.Dictionary()
        
        if "/OCGs" not in pdf.Root.OCProperties:
            pdf.Root.OCProperties.OCGs = pikepdf.Array()
        
        if "/D" not in pdf.Root.OCProperties:
            pdf.Root.OCProperties.D = pikepdf.Dictionary(
                Order=pikepdf.Array(),
                RBGroups=pikepdf.Array()
            )
        
        # Vérifier si le calque existe déjà
        for ocg in pdf.Root.OCProperties.OCGs:
            if ocg.get("/Name") == layer_name:
                if "/Properties" not in page.Resources:
                    page.Resources.Properties = pikepdf.Dictionary()
                page.Resources.Properties[pikepdf.Name(f"/{oc_name}")] = ocg
                return
        
        # Créer le nouveau calque
        ocg = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.OCG,
            Name=layer_name
        ))
        
        # Ajouter aux OCGs
        pdf.Root.OCProperties.OCGs.append(ocg)
        pdf.Root.OCProperties.D.Order.append(ocg)
        
        # Ajouter aux Properties de la page
        if "/Properties" not in page.Resources:
            page.Resources.Properties = pikepdf.Dictionary()
        
        page.Resources.Properties[pikepdf.Name(f"/{oc_name}")] = ocg
    
    def _add_fold_guides(self, page, page_num, x1, y1, x2, y2, fold_info: dict, params: dict, pdf):
        """Ajoute les repères de plis sur le calque BlueLines + côtes"""
        import pikepdf
        
        stroke_width = params["stroke_width"]
        color = params["fold_color"]
        spot_name = params.get("fold_spot_name")
        overprint = params["overprint"]
        
        # Dash pattern
        fold_pattern = params["fold_pattern"]
        dash_parts = fold_pattern.split(",")
        dash_on_mm = float(dash_parts[0])
        dash_off_mm = float(dash_parts[1]) if len(dash_parts) > 1 else dash_on_mm
        dash_on_pt = dash_on_mm * 2.83465
        dash_off_pt = dash_off_mm * 2.83465
        
        # Déterminer si on utilise un ton direct pour les plis
        use_spot_fold = spot_name is not None and spot_name != ""
        
        # Couleurs CMYK (fallback)
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(color, (1, 0, 1, 0))
        
        # Si ton direct, créer le Separation color space
        if use_spot_fold:
            if "/ColorSpace" not in page.Resources:
                page.Resources.ColorSpace = pikepdf.Dictionary()
            
            page.Resources.ColorSpace.CS_Fold = pikepdf.Array([
                pikepdf.Name.Separation,
                pikepdf.Name(f"/{spot_name}"),
                pikepdf.Name.DeviceCMYK,
                pikepdf.Dictionary(
                    FunctionType=2,
                    Domain=[0, 1],
                    Range=[0, 1, 0, 1, 0, 1, 0, 1],
                    C0=[0, 0, 0, 0],
                    C1=[c, m, y, k],
                    N=1
                )
            ])
        
        fold_count = 0
        
        # Calculer les positions verticales
        vertical_positions = []
        vertical_widths = []  # Pour les côtes
        
        if fold_info.get("vertical") is not None:
            fold_type = fold_info.get("type")
            v_data = fold_info["vertical"]
            
            if isinstance(v_data, (int, float)):
                # Identique vertical
                volet_width = v_data
                trimbox_width = (x2 - x1) * 0.352778
                num_volets = int(trimbox_width / volet_width)
                
                self.log_info(f"Plan V: {num_volets} volets identiques de {volet_width}mm")
                fold_widths = [volet_width] * num_volets
            
            elif isinstance(v_data, list):
                fold_widths = v_data
            
            else:
                fold_widths = []
            
            # Calculer positions cumulatives (sans le dernier)
            cumul = 0
            for i, width in enumerate(fold_widths[:-1]):
                cumul += width
                vertical_positions.append(cumul)
            
            # Garder les largeurs pour les côtes
            vertical_widths = fold_widths
        
        # Plis verticaux
        if vertical_positions:
            is_verso = (page_num % 2 == 1)
            
            # Inverser pour verso
            if is_verso:
                v_data = fold_info["vertical"]
                
                if isinstance(v_data, (int, float)):
                    volet_width = v_data
                    trimbox_width = (x2 - x1) * 0.352778
                    num_volets = int(trimbox_width / volet_width)
                    total_width = volet_width * num_volets
                elif isinstance(v_data, list):
                    total_width = sum(v_data)
                else:
                    total_width = 0
                
                vertical_positions = [total_width - p for p in reversed(vertical_positions)]
            
            # Extension des repères au-delà de la TrimBox
            extension_mm = 5  # Prolonger de 5mm
            extension_pt = extension_mm / 0.352778
            
            # Dessiner les lignes verticales (prolongées en haut et bas)
            for pos_mm in vertical_positions:
                pos_pt = pos_mm / 0.352778
                x_fold = x1 + pos_pt
                
                stream = f"q\n"
                stream += f"/OC /OC_BlueLines BDC\n"
                
                if use_spot_fold:
                    stream += f"/CS_Fold CS\n"
                    stream += f"1 SCN\n"
                else:
                    stream += f"{c} {m} {y} {k} K\n"
                
                stream += f"{stroke_width} w\n"
                stream += f"[{dash_on_pt} {dash_off_pt}] 0 d\n"
                
                if overprint:
                    stream += "/GS1 gs\n"
                
                # Prolonger en haut et en bas
                stream += f"{x_fold} {y1 - extension_pt} m {x_fold} {y2 + extension_pt} l\n"
                stream += "S\n"
                stream += "EMC\n"
                stream += "Q\n"
                
                self._append_content(page, stream, pdf)
                fold_count += 1
            
            # Ajouter les côtes verticales si activé
            if params.get("dimensions") and vertical_widths:
                self._add_dimension_arrows_vertical(
                    page, vertical_widths, x1, y1, y2, params, pdf
                )
        
        # Calculer les positions horizontales
        horizontal_positions = []
        horizontal_heights = []  # Pour les côtes
        
        if fold_info.get("horizontal") is not None:
            h_data = fold_info["horizontal"]
            
            if isinstance(h_data, (int, float)):
                volet_height = h_data
                trimbox_height = (y2 - y1) * 0.352778
                num_volets = int(trimbox_height / volet_height)
                
                self.log_info(f"Plan H: {num_volets} volets identiques de {volet_height}mm")
                fold_heights = [volet_height] * num_volets
            
            elif isinstance(h_data, list):
                fold_heights = h_data
            
            else:
                fold_heights = []
            
            # Calculer positions cumulatives (sans le dernier)
            cumul = 0
            for i, height in enumerate(fold_heights[:-1]):
                cumul += height
                horizontal_positions.append(cumul)
            
            # Garder les hauteurs pour les côtes
            horizontal_heights = fold_heights
        
        # Plis horizontaux
        if horizontal_positions:
            # Extension des repères au-delà de la TrimBox
            extension_mm = 5
            extension_pt = extension_mm / 0.352778
            
            for pos_mm in horizontal_positions:
                pos_pt = pos_mm / 0.352778
                y_fold = y2 - pos_pt
                
                stream = f"q\n"
                stream += f"/OC /OC_BlueLines BDC\n"
                
                if use_spot_fold:
                    stream += f"/CS_Fold CS\n"
                    stream += f"1 SCN\n"
                else:
                    stream += f"{c} {m} {y} {k} K\n"
                
                stream += f"{stroke_width} w\n"
                stream += f"[{dash_on_pt} {dash_off_pt}] 0 d\n"
                
                if overprint:
                    stream += "/GS1 gs\n"
                
                # Prolonger à gauche et à droite
                stream += f"{x1 - extension_pt} {y_fold} m {x2 + extension_pt} {y_fold} l\n"
                stream += "S\n"
                stream += "EMC\n"
                stream += "Q\n"
                
                self._append_content(page, stream, pdf)
                fold_count += 1
            
            # Ajouter les côtes horizontales si activé
            if params.get("dimensions") and horizontal_heights:
                self._add_dimension_arrows_horizontal(
                    page, horizontal_heights, x1, x2, y2, params, pdf
                )
        
        # S'assurer que le calque BlueLines existe
        if fold_count > 0:
            self._ensure_layer(page, pdf, "BlueLines", "OC_BlueLines")
            self.log_info(f"   📐 {fold_count} repère(s) de pli ajouté(s)")
    
    def _add_dimension_arrows_vertical(self, page, widths: list, x1, y1, y2, params: dict, pdf):
        """
        Ajoute les côtes verticales (au-dessus de la TrimBox)
        
        Format:
        ←─── 100mm ───→
        """
        import pikepdf
        
        offset_mm = params["dimension_offset"]
        text_size = params["dimension_text_size"]
        arrow_size_mm = params["dimension_arrow_size"]
        color = params["dimensions_color"]
        spot_name = params.get("dimensions_spot_name")
        
        offset_pt = offset_mm / 0.352778
        arrow_size_pt = arrow_size_mm / 0.352778
        
        # Position Y des flèches (au-dessus de la TrimBox)
        arrow_y = y2 + offset_pt
        
        # Position X de départ (à gauche de la TrimBox)
        current_x = x1
        
        stream = "q\n"
        stream += "/OC /OC_BlueLines BDC\n"
        
        # Couleurs CMYK
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(color, (0, 0, 0, 1))
        
        # Ton direct ou process
        use_spot = spot_name is not None and spot_name != ""
        
        if use_spot:
            # Créer le Separation color space
            if "/ColorSpace" not in page.Resources:
                page.Resources.ColorSpace = pikepdf.Dictionary()
            
            page.Resources.ColorSpace.CS_Dimensions = pikepdf.Array([
                pikepdf.Name.Separation,
                pikepdf.Name(f"/{spot_name}"),
                pikepdf.Name.DeviceCMYK,
                pikepdf.Dictionary(
                    FunctionType=2,
                    Domain=[0, 1],
                    Range=[0, 1, 0, 1, 0, 1, 0, 1],
                    C0=[0, 0, 0, 0],
                    C1=[c, m, y, k],
                    N=1
                )
            ])
            
            stream += "/CS_Dimensions cs\n"  # Définir pour fill
            stream += "1 sc\n"                # Fill avec ton direct
            stream += "/CS_Dimensions CS\n"  # Définir pour stroke
            stream += "1 SC\n"                # Stroke avec ton direct
        else:
            stream += f"{c} {m} {y} {k} k\n"  # Fill CMYK
            stream += f"{c} {m} {y} {k} K\n"  # Stroke CMYK

        stream += "0.5 w\n"  # Trait 0.5pt
        
        # ExtGState pour surimpression
        if "/ExtGState" not in page.Resources:
            page.Resources.ExtGState = pikepdf.Dictionary()
        
        page.Resources.ExtGState.GS_Dim = pikepdf.Dictionary(
            Type=pikepdf.Name.ExtGState,
            OP=True,
            op=True,
            OPM=1
        )
        
        stream += "/GS_Dim gs\n"
        
        # S'assurer que Helvetica est disponible
        if "/Font" not in page.Resources:
            page.Resources.Font = pikepdf.Dictionary()
        
        page.Resources.Font.F1 = pikepdf.Dictionary(
            Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1,
            BaseFont=pikepdf.Name.Helvetica
        )
        
        for i, width_mm in enumerate(widths):
            width_pt = width_mm / 0.352778
            
            # Position de la flèche pour ce segment
            arrow_x1 = current_x
            arrow_x2 = current_x + width_pt
            
            # Ligne horizontale
            line_y = arrow_y
            stream += f"{arrow_x1} {line_y} m {arrow_x2} {line_y} l S\n"
            
            # Têtes de flèche
            # Flèche gauche: ►
            stream += f"{arrow_x1} {line_y} m "
            stream += f"{arrow_x1 + arrow_size_pt} {line_y + arrow_size_pt/2} l "
            stream += f"{arrow_x1 + arrow_size_pt} {line_y - arrow_size_pt/2} l "
            stream += "h f\n"
            
            # Flèche droite: ◄
            stream += f"{arrow_x2} {line_y} m "
            stream += f"{arrow_x2 - arrow_size_pt} {line_y + arrow_size_pt/2} l "
            stream += f"{arrow_x2 - arrow_size_pt} {line_y - arrow_size_pt/2} l "
            stream += "h f\n"
            
            # Texte centré AU-DESSUS de la ligne
            text = f"{width_mm:.1f}mm"
            text_x = (arrow_x1 + arrow_x2) / 2
            text_y = line_y + 2  # 2pt au-dessus de la ligne
            
            stream += "BT\n"
            stream += f"/F1 {text_size} Tf\n"
            stream += f"{text_x} {text_y} Td\n"
            stream += f"({text}) Tj\n"
            stream += "ET\n"
            
            current_x += width_pt
        
        stream += "EMC\n"
        stream += "Q\n"
        
        self._append_content(page, stream, pdf)
        self.log_debug(f"Côtes verticales ajoutées: {len(widths)} segment(s)")
    
    def _add_dimension_arrows_horizontal(self, page, heights: list, x1, x2, y2, params: dict, pdf):
        """
        Ajoute les côtes horizontales (à gauche de la TrimBox)
        
        Format:
        ↑
        │
        210mm
        │
        ↓
        """
        import pikepdf
        
        offset_mm = params["dimension_offset"]
        text_size = params["dimension_text_size"]
        arrow_size_mm = params["dimension_arrow_size"]
        color = params["dimensions_color"]
        spot_name = params.get("dimensions_spot_name")
        
        offset_pt = offset_mm / 0.352778
        arrow_size_pt = arrow_size_mm / 0.352778
        
        # Position X des flèches (à gauche de la TrimBox)
        arrow_x = x1 - offset_pt
        
        # Position Y de départ (en haut de la TrimBox)
        current_y = y2
        
        stream = "q\n"
        stream += "/OC /OC_BlueLines BDC\n"
        
        # Couleurs CMYK
        color_map = {
            "cyan": (1, 0, 0, 0),
            "magenta": (0, 1, 0, 0),
            "yellow": (0, 0, 1, 0),
            "black": (0, 0, 0, 1),
            "registration": (1, 1, 1, 1),
            "green": (1, 0, 1, 0),
            "red": (0, 1, 1, 0),
            "blue": (1, 1, 0, 0)
        }
        
        c, m, y, k = color_map.get(color, (0, 0, 0, 1))
        
        # Ton direct ou process
        use_spot = spot_name is not None and spot_name != ""
        
        if use_spot:
            # Utiliser le même CS_Dimensions si déjà créé, sinon le créer
            if "/ColorSpace" not in page.Resources:
                page.Resources.ColorSpace = pikepdf.Dictionary()
            
            if "/CS_Dimensions" not in page.Resources.ColorSpace:
                page.Resources.ColorSpace.CS_Dimensions = pikepdf.Array([
                    pikepdf.Name.Separation,
                    pikepdf.Name(f"/{spot_name}"),
                    pikepdf.Name.DeviceCMYK,
                    pikepdf.Dictionary(
                        FunctionType=2,
                        Domain=[0, 1],
                        Range=[0, 1, 0, 1, 0, 1, 0, 1],
                        C0=[0, 0, 0, 0],
                        C1=[c, m, y, k],
                        N=1
                    )
                ])

            stream += "/CS_Dimensions cs\n"  # Définir pour fill
            stream += "1 sc\n"                # Fill avec ton direct
            stream += "/CS_Dimensions CS\n"  # Définir pour stroke
            stream += "1 SC\n"                # Stroke avec ton direct
        else:
            stream += f"{c} {m} {y} {k} k\n"  # Fill CMYK
            stream += f"{c} {m} {y} {k} K\n"  # Stroke CMYK

        stream += "0.5 w\n"
        
        # ExtGState pour surimpression (si pas déjà créé)
        if "/ExtGState" not in page.Resources:
            page.Resources.ExtGState = pikepdf.Dictionary()
        
        if "/GS_Dim" not in page.Resources.ExtGState:
            page.Resources.ExtGState.GS_Dim = pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState,
                OP=True,
                op=True,
                OPM=1
            )
        
        stream += "/GS_Dim gs\n"
        
        # S'assurer que Helvetica est disponible
        if "/Font" not in page.Resources:
            page.Resources.Font = pikepdf.Dictionary()
        
        page.Resources.Font.F1 = pikepdf.Dictionary(
            Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1,
            BaseFont=pikepdf.Name.Helvetica
        )
        
        for i, height_mm in enumerate(heights):
            height_pt = height_mm / 0.352778
            
            # Position de la flèche pour ce segment
            arrow_y1 = current_y
            arrow_y2 = current_y - height_pt
            
            # Ligne verticale
            line_x = arrow_x
            stream += f"{line_x} {arrow_y1} m {line_x} {arrow_y2} l S\n"
            
            # Têtes de flèche
            # Flèche haut: ▲
            stream += f"{line_x} {arrow_y1} m "
            stream += f"{line_x - arrow_size_pt/2} {arrow_y1 - arrow_size_pt} l "
            stream += f"{line_x + arrow_size_pt/2} {arrow_y1 - arrow_size_pt} l "
            stream += "h f\n"
            
            # Flèche bas: ▼
            stream += f"{line_x} {arrow_y2} m "
            stream += f"{line_x - arrow_size_pt/2} {arrow_y2 + arrow_size_pt} l "
            stream += f"{line_x + arrow_size_pt/2} {arrow_y2 + arrow_size_pt} l "
            stream += "h f\n"
            
            # Texte centré et tourné à 90° À GAUCHE de la ligne
            text = f"{height_mm:.1f}mm"
            text_x = line_x - text_size - 2  # 2pt à gauche de la ligne
            text_y = (arrow_y1 + arrow_y2) / 2
            
            # Rotation du texte (90° sens horaire)
            stream += "BT\n"
            stream += f"/F1 {text_size} Tf\n"
            stream += f"0 -1 1 0 {text_x} {text_y} Tm\n"  # Matrice de rotation
            stream += f"({text}) Tj\n"
            stream += "ET\n"
            
            current_y -= height_pt
        
        stream += "EMC\n"
        stream += "Q\n"
        
        self._append_content(page, stream, pdf)
        self.log_debug(f"Côtes horizontales ajoutées: {len(heights)} segment(s)")
    
    def _append_content(self, page, stream: str, pdf):
        """Ajoute du contenu à une page PDF"""
        import pikepdf
        
        if hasattr(page, 'Contents'):
            if not isinstance(page.Contents, pikepdf.Array):
                existing_content = [page.Contents]
            else:
                existing_content = list(page.Contents)
            
            new_stream = pikepdf.Stream(pdf, stream.encode())
            existing_content.append(new_stream)
            page.Contents = pikepdf.Array(existing_content)
        else:
            page.Contents = pikepdf.Stream(pdf, stream.encode())