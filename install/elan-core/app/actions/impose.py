# ============================================================================
# FILE: /opt/elan/app/actions/impose.py
# VERSION : 56
# ============================================================================

import os
import subprocess
import shutil
import uuid
from pathlib import Path
from typing import Dict, Tuple, List
from .base import Action, ActionError


class ImposeAction(Action):
    """Impose un PDF avec calcul automatique des poses (APLAT uniquement)"""
    
    @property
    def name(self) -> str:
        return "impose"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("layout", "auto")              # auto, 2-up, 4-up, 8-up, 16-up
        params.setdefault("output_format", "SRA3")       # A3, A2, A1, SRA3, format custom
        params.setdefault("custom_width", None)          # Pour format custom (mm)
        params.setdefault("custom_height", None)         # Pour format custom (mm)
        
        # Marges et espacements
        params.setdefault("margin_x", 10)                # Marge gauche/droite (mm)
        params.setdefault("margin_y", 10)                # Marge haut/bas (mm)
        params.setdefault("gutter_h", 4)                 # Gouttière horizontale (mm)
        params.setdefault("gutter_v", 4)                 # Gouttière verticale (mm)
        params.setdefault("bleed", 3)                    # Fond perdu à garder (mm)
        
        # Repères de coupe
        params.setdefault("crop_marks", True)
        params.setdefault("crop_mark_length", 3)         # Longueur repères (mm)
        params.setdefault("crop_mark_color", "all")      # all, cyan, magenta, yellow, black
        params.setdefault("crop_mark_offset", 2)         # Distance du repère à la zone (mm)
        params.setdefault("crop_mark_width", 0.25)       # Épaisseur trait (pt)
        
        # Options
        params.setdefault("use_trimbox", True)           # Utiliser TrimBox comme référence
        params.setdefault("center_pages", True)          # Centrer les pages sur la feuille
        params.setdefault("rotate_if_better", True)      # Rotation auto si plus de poses
        params.setdefault("output_suffix", "_imposed")   # Suffixe du fichier de sortie
        params.setdefault("mode", "distribute")          # distribute (défaut) ou repeat
        
        # Validation
        valid_layouts = ["auto", "2-up", "4-up", "8-up", "16-up"]
        if params["layout"] not in valid_layouts:
            raise ActionError(f"layout doit être: {', '.join(valid_layouts)}")
        
        # Validation mode
        valid_modes = ["distribute", "repeat"]
        if params["mode"] not in valid_modes:
            raise ActionError(f"mode doit être: {', '.join(valid_modes)}")
        
        # Validation format custom
        if params["output_format"] == "custom":
            if not params["custom_width"] or not params["custom_height"]:
                raise ActionError("Format custom nécessite custom_width et custom_height")
        
        # Validation couleur repères
        valid_colors = ["all", "cyan", "magenta", "yellow", "black"]
        if params["crop_mark_color"] not in valid_colors:
            raise ActionError(f"crop_mark_color doit être: {', '.join(valid_colors)}")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """
        Impose le PDF avec calcul automatique des poses
        
        Config attendue:
        {
            "params": {
                "layout": "auto",              # Calcul auto du meilleur layout
                "output_format": "SRA3",       # Format de feuille (A3, SRA3, A2, etc.)
                "margin_x": 10,                # Marge impression gauche/droite (mm)
                "margin_y": 10,                # Marge impression haut/bas (mm)
                "gutter_h": 4,                 # Gouttière horizontale (mm)
                "gutter_v": 4,                 # Gouttière verticale (mm)
                "bleed": 3,                    # Fond perdu à garder (mm)
                "crop_marks": true,            # Repères de coupe
                "crop_mark_length": 3,         # Longueur repères (mm)
                "crop_mark_color": "all",      # Couleur repères (all, cyan, magenta, yellow, black)
                "crop_mark_offset": 2,         # Distance repère-zone (mm)
                "crop_mark_width": 0.25,       # Épaisseur trait (pt)
                "use_trimbox": true,           # Utiliser TrimBox comme zone de rogne
                "center_pages": true,          # Centrer sur la feuille
                "rotate_if_better": true,      # Rotation auto si gain de poses
                "output_suffix": "_imposed"
            }
        }
        """
        params = self.config["params"]
        
        # Détecter le dossier de travail (genstore du job)
        input_path = Path(file_path)
        work_dir = input_path.parent  # On travaille dans le genstore du job
        
        self.log_info(f"🔨 Imposition dans: {work_dir.name}")
        
        try:
            # Construire le nom de sortie
            output_suffix = params["output_suffix"]
            output_name = f"{input_path.stem}{output_suffix}{input_path.suffix}"
            output_path = work_dir / output_name
            
            # Extraire les dimensions du PDF (TrimBox ou MediaBox)
            page_width, page_height = self._get_pdf_dimensions(input_path, params)
            self.log_info(f"📐 Dimensions page: {page_width:.1f} × {page_height:.1f} mm")
            
            # Obtenir les dimensions de la feuille de sortie
            sheet_width, sheet_height = self._get_sheet_dimensions(params)
            self.log_info(f"📄 Format feuille: {sheet_width:.1f} × {sheet_height:.1f} mm ({params['output_format']})")
            
            # Calculer le layout optimal
            layout = self._calculate_optimal_layout(
                page_width, page_height,
                sheet_width, sheet_height,
                params
            )
            
            cols, rows, rotated = layout
            total_poses = cols * rows
            self.log_info(f"🎯 Layout optimal: {cols}×{rows} = {total_poses} pose(s)")
            if rotated:
                self.log_info(f"   🔄 Pages en rotation de 90°")
            
            if total_poses == 0:
                raise ActionError(
                    f"Impossible de placer la page ({page_width:.1f}×{page_height:.1f}mm) "
                    f"sur la feuille ({sheet_width:.1f}×{sheet_height:.1f}mm) "
                    f"avec les marges configurées"
                )
            
            # Générer l'imposition
            self._create_imposition(
                input_path, output_path,
                page_width, page_height,
                sheet_width, sheet_height,
                layout, params
            )
            
            # Vérifier que le fichier existe
            if not output_path.exists():
                raise ActionError(f"Fichier de sortie non créé: {output_path}")
            
            self.log_info(f"✅ Imposition créée: {output_path}")
            
            return str(output_path)
            
        except Exception as e:
            raise ActionError(f"Erreur imposition: {e}")
    
    def _get_pdf_dimensions(self, pdf_path: Path, params: dict) -> Tuple[float, float]:
        """Extrait les dimensions d'une page PDF (en mm)"""
        try:
            import pikepdf
            
            pdf = pikepdf.open(pdf_path)
            page = pdf.pages[0]
            
            # Utiliser TrimBox si disponible, sinon MediaBox
            if params["use_trimbox"] and "/TrimBox" in page:
                box = page.TrimBox
                self.log_debug("Utilisation de TrimBox")
            else:
                box = page.MediaBox
                self.log_debug("Utilisation de MediaBox")
            
            pdf.close()
            
            # Convertir points → mm (1 pt = 0.352778 mm)
            x1, y1, x2, y2 = [float(v) for v in box]
            width_mm = (x2 - x1) * 0.352778
            height_mm = (y2 - y1) * 0.352778
            
            return width_mm, height_mm
            
        except Exception as e:
            raise ActionError(f"Impossible de lire les dimensions du PDF: {e}")
    
    def _get_sheet_dimensions(self, params: dict) -> Tuple[float, float]:
        """Retourne les dimensions de la feuille (en mm)"""
        format_name = params["output_format"]
        
        # Formats standards (mm)
        formats = {
            "A5": (148, 210),
            "A4": (210, 297),
            "A3": (297, 420),
            "A2": (420, 594),
            "A1": (594, 841),
            "A0": (841, 1189),
            "SRA3": (320, 450),      # Format SRA3 (A3+)
            "SRA2": (450, 640),
            "SRA1": (640, 900),
        }
        
        if format_name == "custom":
            return params["custom_width"], params["custom_height"]
        
        if format_name not in formats:
            raise ActionError(f"Format inconnu: {format_name}")
        
        return formats[format_name]
    
    def _calculate_optimal_layout(
        self,
        page_w: float, page_h: float,
        sheet_w: float, sheet_h: float,
        params: dict
    ) -> Tuple[int, int, bool]:
        """
        Calcule le layout optimal (colonnes, lignes, rotation)
        
        Prend en compte:
        - Marges d'impression
        - Gouttières
        - Fonds perdus
        - Rotation possible
        
        Returns:
            (colonnes, lignes, rotated)
        """
        layout = params["layout"]
        margin_x = params["margin_x"]
        margin_y = params["margin_y"]
        gutter_h = params["gutter_h"]
        gutter_v = params["gutter_v"]
        bleed = params["bleed"]
        rotate_if_better = params["rotate_if_better"]
        
        # Zone imprimable = feuille - marges
        printable_w = sheet_w - (2 * margin_x)
        printable_h = sheet_h - (2 * margin_y)
        
        # Dimensions page (TrimBox seulement, pas de bleed ici)
        page_w_only = page_w
        page_h_only = page_h
        
        self.log_debug(f"Zone imprimable: {printable_w:.1f} × {printable_h:.1f} mm")
        self.log_debug(f"Page TrimBox: {page_w_only:.1f} × {page_h_only:.1f} mm")
        self.log_debug(f"Gouttière: {gutter_h:.1f} × {gutter_v:.1f} mm")
        self.log_debug(f"Bleed: {bleed:.1f} mm")
        
        # Si layout spécifique (2-up, 4-up, etc.)
        if layout != "auto":
            return self._parse_fixed_layout(layout)
        
        # Calcul automatique - orientation normale
        cols_normal = self._calc_cols(printable_w, page_w_only, gutter_h)
        rows_normal = self._calc_rows(printable_h, page_h_only, gutter_v)
        poses_normal = cols_normal * rows_normal
        
        self.log_debug(f"Normal: {cols_normal}×{rows_normal} = {poses_normal} poses")
        
        # Calcul avec rotation si autorisé
        if rotate_if_better:
            cols_rotated = self._calc_cols(printable_w, page_h_only, gutter_h)
            rows_rotated = self._calc_rows(printable_h, page_w_only, gutter_v)
            poses_rotated = cols_rotated * rows_rotated
            
            self.log_debug(f"Roté: {cols_rotated}×{rows_rotated} = {poses_rotated} poses")
            
            # Choisir le meilleur
            if poses_rotated > poses_normal:
                return cols_rotated, rows_rotated, True
        
        return cols_normal, rows_normal, False
    
    def _calc_cols(self, available_width: float, page_width: float, gutter: float) -> int:
        """
        Calcule le nombre de colonnes possibles
        
        Logique correcte:
        - 1 colonne = page_width
        - 2 colonnes = page_width + gutter + page_width
        - N colonnes = N×page_width + (N-1)×gutter
        
        Avec bleed aux extrémités:
        Total = 2×bleed + N×page_width + (N-1)×gutter
        """
        # On cherche le N maximum tel que:
        # 2×bleed + N×page_width + (N-1)×gutter ≤ available_width
        
        # Cas N=1 (une seule colonne, pas de gouttière)
        if page_width > available_width:
            return 0
        
        cols = 1
        # Pour chaque colonne supplémentaire, on ajoute: gutter + page_width
        while cols * page_width + (cols - 1) * gutter <= available_width:
            cols += 1
        
        # On a dépassé, retour à la valeur précédente
        return cols - 1
    
    def _calc_rows(self, available_height: float, page_height: float, gutter: float) -> int:
        """
        Calcule le nombre de lignes possibles
        
        Même logique que _calc_cols
        """
        if page_height > available_height:
            return 0
        
        rows = 1
        while rows * page_height + (rows - 1) * gutter <= available_height:
            rows += 1
        
        return rows - 1
    
    def _parse_fixed_layout(self, layout: str) -> Tuple[int, int, bool]:
        """Parse un layout fixe (2-up, 4-up, etc.)"""
        layouts = {
            "2-up": (2, 1, False),
            "4-up": (2, 2, False),
            "8-up": (4, 2, False),
            "16-up": (4, 4, False),
        }
        
        if layout not in layouts:
            raise ActionError(f"Layout inconnu: {layout}")
        
        return layouts[layout]
    
    def _create_imposition(
        self,
        input_pdf: Path,
        output_pdf: Path,
        page_w: float, page_h: float,
        sheet_w: float, sheet_h: float,
        layout: Tuple[int, int, bool],
        params: dict
    ):
        """Crée le PDF imposé avec pikepdf"""
        try:
            import pikepdf
            
            cols, rows, rotated = layout
            
            self.log_info(f"🔨 Création de l'imposition...")
            
            # Ouvrir le PDF source
            src_pdf = pikepdf.open(input_pdf)
            
            # Créer le PDF de sortie
            out_pdf = pikepdf.new()
            
            # Créer autant de feuilles imposées que nécessaire
            total_pages = len(src_pdf.pages)
            poses_per_sheet = cols * rows
            num_sheets = (total_pages + poses_per_sheet - 1) // poses_per_sheet
            
            self.log_info(f"   📄 {total_pages} page(s) → {num_sheets} feuille(s) imposée(s)")
            self.log_info(f"   📐 Layout: {cols} colonnes × {rows} lignes = {poses_per_sheet} poses/feuille")
            
            # Indiquer le mode
            mode = params["mode"]
            if mode == "repeat":
                self.log_info(f"   🔁 Mode: REPEAT (répétition de la page 1)")
            else:
                self.log_info(f"   📑 Mode: DISTRIBUTE (distribution des pages)")
            
            page_index = 0
            for sheet_num in range(num_sheets):
                self.log_debug(f"Création feuille #{sheet_num + 1}/{num_sheets}")
                self._create_imposed_sheet(
                    src_pdf, page_index,
                    out_pdf,
                    page_w, page_h,
                    sheet_w, sheet_h,
                    layout, params
                )
                
                page_index += poses_per_sheet
                self.log_debug(f"Feuille #{sheet_num + 1} terminée, page_index = {page_index}")
            
            # Sauvegarder
            out_pdf.save(output_pdf)
            out_pdf.close()
            src_pdf.close()
            
            self.log_info(f"✅ Imposition terminée")
            
        except Exception as e:
            raise ActionError(f"Erreur création imposition: {e}")
    
    def _create_imposed_sheet(
        self,
        src_pdf,
        start_page_index: int,
        out_pdf,
        page_w: float, page_h: float,
        sheet_w: float, sheet_h: float,
        layout: Tuple[int, int, bool],
        params: dict
    ):
        """Crée une feuille imposée avec toutes les poses"""
        import pikepdf
        from pikepdf import Dictionary, Name, Array
        
        cols, rows, rotated = layout
        margin_x = params["margin_x"]
        margin_y = params["margin_y"]
        gutter_h = params["gutter_h"]
        gutter_v = params["gutter_v"]
        bleed = params["bleed"]
        
        # Convertir mm → points
        sheet_w_pt = sheet_w / 0.352778
        sheet_h_pt = sheet_h / 0.352778
        margin_x_pt = margin_x / 0.352778
        margin_y_pt = margin_y / 0.352778
        gutter_h_pt = gutter_h / 0.352778
        gutter_v_pt = gutter_v / 0.352778
        bleed_pt = bleed / 0.352778
        
        # Créer une nouvelle page blanche avec pikepdf
        imposed_page = out_pdf.add_blank_page(
            page_size=(sheet_w_pt, sheet_h_pt)
        )
        
        # Dimensions pose = TrimBox + 2×bleed
        if rotated:
            pose_w_pt = (page_h + 2 * bleed) / 0.352778
            pose_h_pt = (page_w + 2 * bleed) / 0.352778
        else:
            pose_w_pt = (page_w + 2 * bleed) / 0.352778
            pose_h_pt = (page_h + 2 * bleed) / 0.352778
        
        # Calculer l'espace total occupé (pour centrage)
        # Total = 2×bleed + N×TrimBox + (N-1)×gutter
        # Mais pose inclut déjà 2×bleed, donc:
        # Total = N×pose + (N-1)×gutter - (N-1)×2×bleed
        # Simplifié: N×TrimBox + (N-1)×gutter + 2×bleed
        
        trimbox_w_pt = page_w / 0.352778 if not rotated else page_h / 0.352778
        trimbox_h_pt = page_h / 0.352778 if not rotated else page_w / 0.352778
        bleed_pt_single = bleed / 0.352778
        
        total_w = cols * trimbox_w_pt + (cols - 1) * gutter_h_pt + 2 * bleed_pt_single
        total_h = rows * trimbox_h_pt + (rows - 1) * gutter_v_pt + 2 * bleed_pt_single
        
        if params["center_pages"]:
            printable_w_pt = sheet_w_pt - (2 * margin_x_pt)
            printable_h_pt = sheet_h_pt - (2 * margin_y_pt)
            offset_x = margin_x_pt + (printable_w_pt - total_w) / 2
            offset_y = margin_y_pt + (printable_h_pt - total_h) / 2
        else:
            offset_x = margin_x_pt
            offset_y = margin_y_pt
        
        # Placer les poses
        poses_info = []  # Pour les repères de coupe
        page_index = start_page_index
        
        self.log_debug(f"Placement de {cols}×{rows} poses, à partir de la page {start_page_index}")
        self.log_debug(f"Offset initial: ({offset_x:.1f}, {offset_y:.1f})")
        self.log_debug(f"Pose TrimBox: {trimbox_w_pt:.1f} × {trimbox_h_pt:.1f} pt")
        self.log_debug(f"Pose avec bleed: {pose_w_pt:.1f} × {pose_h_pt:.1f} pt")
        
        for row in range(rows):
            for col in range(cols):
                if page_index >= len(src_pdf.pages):
                    self.log_debug(f"  Plus de pages à placer (page_index={page_index} >= {len(src_pdf.pages)})")
                    break  # Plus de pages à placer
                
                # Position = offset + col×(TrimBox + gutter) - bleed
                # Car chaque pose commence à -bleed de sa TrimBox
                x = offset_x + bleed_pt_single + col * (trimbox_w_pt + gutter_h_pt) - bleed_pt_single
                y = sheet_h_pt - (offset_y + bleed_pt_single + row * (trimbox_h_pt + gutter_v_pt) + pose_h_pt - bleed_pt_single)
                
                self.log_debug(f"  Pose [{row},{col}]: page {page_index} à ({x:.1f}, {y:.1f})")
                
                self._place_page_on_sheet(
                    imposed_page, src_pdf.pages[page_index],
                    out_pdf,
                    x, y, pose_w_pt, pose_h_pt,
                    rotated, bleed_pt_single
                )
                
                # Enregistrer la position pour les repères
                poses_info.append({
                    "x": x,
                    "y": y,
                    "width": pose_w_pt,
                    "height": pose_h_pt,
                    "bleed": bleed_pt
                })
                
                page_index += 1
            
            # Si on a épuisé les pages, sortir aussi de la boucle externe
            if page_index >= len(src_pdf.pages):
                break
        
        # Ajouter repères de coupe si demandé
        if params["crop_marks"]:
            self._add_crop_marks(imposed_page, poses_info, params, out_pdf)
    
    def _place_page_on_sheet(self, imposed_page, src_page, out_pdf, x, y, w, h, rotated, bleed_pt):
        """
        Place une copie de la page source sur la feuille imposée
        
        IMPORTANT: x, y représentent la position de la TrimBox (pas de la MediaBox)
        Il faut calculer le décalage entre MediaBox et TrimBox pour placer correctement
        """
        import pikepdf
        from pikepdf import Dictionary, Name, Array, Stream
        
        self.log_debug(f"Placement page à x={x:.1f}, y={y:.1f} (position TrimBox)")
        
        # Récupérer les dimensions de la page source
        src_mediabox = src_page.MediaBox
        src_x1, src_y1, src_x2, src_y2 = [float(v) for v in src_mediabox]
        src_width = src_x2 - src_x1
        src_height = src_y2 - src_y1
        
        # Récupérer la TrimBox si elle existe
        if "/TrimBox" in src_page:
            src_trimbox = src_page.TrimBox
            trim_x1, trim_y1, trim_x2, trim_y2 = [float(v) for v in src_trimbox]
            trim_width = trim_x2 - trim_x1
            trim_height = trim_y2 - trim_y1
            
            # Calculer le décalage entre MediaBox et TrimBox
            offset_x = trim_x1 - src_x1
            offset_y = trim_y1 - src_y1
            
            self.log_debug(f"MediaBox: {src_width:.1f}×{src_height:.1f}pt origine ({src_x1:.1f}, {src_y1:.1f})")
            self.log_debug(f"TrimBox: {trim_width:.1f}×{trim_height:.1f}pt origine ({trim_x1:.1f}, {trim_y1:.1f})")
            self.log_debug(f"Offset MediaBox→TrimBox: ({offset_x:.1f}, {offset_y:.1f})")
        else:
            # Pas de TrimBox, utiliser MediaBox
            offset_x = 0
            offset_y = 0
            self.log_debug(f"MediaBox: {src_width:.1f}×{src_height:.1f}pt (pas de TrimBox)")
        
        # Pour l'imposition APLAT, on veut placer le PDF à 100% (pas de scaling)
        scale_x = 1.0
        scale_y = 1.0
        
        # Position finale de la MediaBox = position TrimBox - offset
        final_x = x - offset_x
        final_y = y - offset_y
        
        self.log_debug(f"Position finale MediaBox: ({final_x:.1f}, {final_y:.1f})")
        self.log_debug(f"Scaling: {scale_x} × {scale_y} (100%, pas de réduction)")
        
        # Construire la matrice de transformation
        if rotated:
            # Rotation 90° sens horaire sans scaling
            # Pour rotation 90°: [0 -1 1 0 tx ty]
            matrix = [
                0, -1,
                1, 0,
                mediabox_x, mediabox_y + src_width  # Ajuster pour la rotation
            ]
            self.log_debug(f"Matrice: rotation 90°")
        else:
            # Placement direct sans scaling
            matrix = [
                1, 0,
                0, 1,
                mediabox_x, mediabox_y
            ]
            self.log_debug(f"Matrice: identité (pas de transformation)")
        
        # S'assurer que la page a des Resources
        if "/Resources" not in imposed_page:
            imposed_page.Resources = Dictionary()
        
        if "/XObject" not in imposed_page.Resources:
            imposed_page.Resources.XObject = Dictionary()
        
        # Créer un nom unique pour cette page
        xobj_name = f"Page{len(imposed_page.Resources.XObject) + 1}"
        
        # ÉTAPE 1: Dessiner un rectangle de détourage DEBUG
        # Ce rectangle montre exactement où doit être la pose (TrimBox + bleed)
        debug_rect_stream = f"""
q
1 0 0 RG  % Rouge
0.5 w     % Épaisseur 0.5pt
{final_x} {final_y} {w} {h} re
S
Q
"""
        
        self.log_debug(f"Rectangle détourage: x={final_x:.1f}, y={final_y:.1f}, w={w:.1f}, h={h:.1f}")
        
        # Copier le contenu de la page source
        if src_page.Contents is not None:
            if isinstance(src_page.Contents, list):
                # Plusieurs streams, les concaténer
                content_bytes = b""
                for stream in src_page.Contents:
                    content_bytes += bytes(stream.read_bytes())
            else:
                content_bytes = bytes(src_page.Contents.read_bytes())
        else:
            content_bytes = b""
        
        # Créer le Form XObject avec son dictionnaire
        form_xobj = Stream(out_pdf, content_bytes)
        form_xobj.Type = Name.XObject
        form_xobj.Subtype = Name.Form
        form_xobj.FormType = 1
        form_xobj.BBox = Array([src_x1, src_y1, src_x2, src_y2])
        
        self.log_debug(f"Form XObject créé: {xobj_name}")
        
        # Copier les ressources de la page source
        # On doit copier manuellement car copy_foreign ne fonctionne pas sur un dictionnaire direct
        if "/Resources" in src_page:
            self.log_debug(f"Copie des ressources depuis la page source...")
            # Créer un nouveau dictionnaire Resources vide
            form_xobj.Resources = Dictionary()
            
            # Copier chaque type de ressource
            src_resources = src_page.Resources
            self.log_debug(f"Ressources trouvées: {list(src_resources.keys())}")
            
            for key in src_resources.keys():
                try:
                    self.log_debug(f"  Copie de la ressource: {key}")
                    
                    # Cas spécial pour /XObject qui est un dictionnaire d'objets
                    if key == "/XObject":
                        form_xobj.Resources.XObject = Dictionary()
                        src_xobjects = src_resources[key]
                        for xobj_key in src_xobjects.keys():
                            self.log_debug(f"    Copie XObject: {xobj_key}")
                            form_xobj.Resources.XObject[xobj_key] = out_pdf.copy_foreign(src_xobjects[xobj_key])
                    # Cas spécial pour /Font qui est un dictionnaire de fonts
                    elif key == "/Font":
                        form_xobj.Resources.Font = Dictionary()
                        src_fonts = src_resources[key]
                        for font_key in src_fonts.keys():
                            self.log_debug(f"    Copie Font: {font_key}")
                            form_xobj.Resources.Font[font_key] = out_pdf.copy_foreign(src_fonts[font_key])
                    # Pour les autres ressources, essayer copy_foreign
                    else:
                        form_xobj.Resources[key] = out_pdf.copy_foreign(src_resources[key])
                    
                    self.log_debug(f"  ✅ {key} copié")
                except Exception as e:
                    self.log_error(f"  ❌ Erreur copie {key}: {e}")
                    self.log_debug(f"  Type de {key}: {type(src_resources[key])}")
                    raise
        else:
            self.log_debug(f"Aucune ressource à copier depuis la page source")
        
        # Ajouter le XObject aux ressources
        self.log_debug(f"Ajout du XObject {xobj_name} aux ressources de la page imposée")
        imposed_page.Resources.XObject[Name(f"/{xobj_name}")] = form_xobj
        
        # Créer le stream de contenu avec la transformation
        content_stream = f"q {' '.join(map(str, matrix))} cm /{xobj_name} Do Q\n"
        self.log_debug(f"Stream de contenu: {content_stream.strip()}")
        
        # Ajouter au contenu existant de la page imposée
        if imposed_page.Contents is None:
            self.log_debug(f"Création du contenu de la page imposée")
            imposed_page.Contents = Stream(out_pdf, (debug_rect_stream + content_stream).encode())
        else:
            self.log_debug(f"Ajout au contenu existant de la page imposée")
            # Lire le contenu existant
            existing = bytes(imposed_page.Contents.read_bytes())
            # Créer un nouveau stream avec le contenu combiné
            new_stream = Stream(out_pdf, existing + (debug_rect_stream + content_stream).encode())
            # Remplacer le contenu de la page
            imposed_page.Contents = new_stream
        
        self.log_debug(f"✅ Page placée avec succès")
    
    def _add_crop_marks(self, page, poses_info: List[dict], params: dict, pdf):
        """Ajoute les repères de coupe"""
        mark_length = params["crop_mark_length"] / 0.352778  # mm → pt
        mark_offset = params["crop_mark_offset"] / 0.352778
        mark_width = params["crop_mark_width"]
        color = params["crop_mark_color"]
        gutter_h = params["gutter_h"] / 0.352778  # Convertir en pt
        gutter_v = params["gutter_v"] / 0.352778
        
        self.log_debug(f"Ajout des repères de coupe sur {len(poses_info)} pose(s)")
        self.log_debug(f"Gouttière: {gutter_h:.1f}×{gutter_v:.1f}pt, Offset: {mark_offset:.1f}pt")
        
        # Déterminer les couleurs CMYK
        if color == "all":
            # Pour un vrai ton direct "Registration", il faudrait définir un Separation
            # En attendant, on utilise 100% CMJN (noir total)
            colors = [(1, 1, 1, 1)]
            self.log_debug(f"Couleur repères: Noir total (C=100 M=100 Y=100 K=100)")
        elif color == "cyan":
            colors = [(1, 0, 0, 0)]
        elif color == "magenta":
            colors = [(0, 1, 0, 0)]
        elif color == "yellow":
            colors = [(0, 0, 1, 0)]
        elif color == "black":
            colors = [(0, 0, 0, 1)]
        else:
            colors = [(0, 0, 0, 1)]  # Fallback noir
        
        # Construire le stream PDF pour les repères
        marks_stream = f"{mark_width} w\n"  # Largeur du trait
        
        # Calculer le nombre de colonnes et lignes pour détecter les bords
        # (on va déduire ça des positions relatives des poses)
        poses_by_row = {}
        poses_by_col = {}
        
        for i, pose in enumerate(poses_info):
            # Grouper par position Y (lignes)
            y_key = round(pose["y"] / 10) * 10  # Arrondir à 10pt près
            if y_key not in poses_by_row:
                poses_by_row[y_key] = []
            poses_by_row[y_key].append(i)
            
            # Grouper par position X (colonnes)
            x_key = round(pose["x"] / 10) * 10
            if x_key not in poses_by_col:
                poses_by_col[x_key] = []
            poses_by_col[x_key].append(i)
        
        # Trier pour identifier première/dernière ligne et colonne
        sorted_rows = sorted(poses_by_row.keys())
        sorted_cols = sorted(poses_by_col.keys())
        first_row = sorted_rows[0] if sorted_rows else None
        last_row = sorted_rows[-1] if sorted_rows else None
        first_col = sorted_cols[0] if sorted_cols else None
        last_col = sorted_cols[-1] if sorted_cols else None
        
        for i, pose in enumerate(poses_info):
            x = pose["x"]
            y = pose["y"]
            w = pose["width"]
            h = pose["height"]
            bleed = pose["bleed"]
            
            # Déterminer si c'est un bord extérieur
            y_key = round(y / 10) * 10
            x_key = round(x / 10) * 10
            is_top = (y_key == last_row)
            is_bottom = (y_key == first_row)
            is_left = (x_key == first_col)
            is_right = (x_key == last_col)
            
            # Position de la zone de rogne (sans fond perdu)
            trim_x1 = x + bleed
            trim_y1 = y + bleed
            trim_x2 = x + w - bleed
            trim_y2 = y + h - bleed
            
            # Calculer la longueur des repères selon la position
            # Extérieur = longueur normale, Intérieur = longueur réduite
            max_mark_h = (gutter_h / 2) - mark_offset
            max_mark_v = (gutter_v / 2) - mark_offset
            
            # 4 coins avec repères en croix
            corners = [
                (trim_x1, trim_y1, is_left, is_bottom),  # Coin bas-gauche
                (trim_x2, trim_y1, is_right, is_bottom), # Coin bas-droit
                (trim_x1, trim_y2, is_left, is_top),     # Coin haut-gauche
                (trim_x2, trim_y2, is_right, is_top),    # Coin haut-droit
            ]
            
            for c, m, ye, k in colors:
                marks_stream += f"{c} {m} {ye} {k} K\n"
                
                for corner_x, corner_y, is_edge_h, is_edge_v in corners:
                    # Longueur repère horizontal
                    if is_edge_h:
                        # Bord extérieur = longueur normale
                        actual_mark_h = mark_length
                    else:
                        # Bord intérieur = longueur réduite
                        actual_mark_h = min(mark_length, max_mark_h) if max_mark_h > 0 else mark_length
                    
                    # Repère horizontal
                    if corner_x == trim_x1:  # Côté gauche
                        h_start_x = corner_x - mark_offset - actual_mark_h
                        h_end_x = corner_x - mark_offset
                    else:  # Côté droit
                        h_start_x = corner_x + mark_offset
                        h_end_x = corner_x + mark_offset + actual_mark_h
                    
                    marks_stream += f"{h_start_x} {corner_y} m {h_end_x} {corner_y} l S\n"
                    
                    # Longueur repère vertical
                    if is_edge_v:
                        # Bord extérieur = longueur normale
                        actual_mark_v = mark_length
                    else:
                        # Bord intérieur = longueur réduite
                        actual_mark_v = min(mark_length, max_mark_v) if max_mark_v > 0 else mark_length
                    
                    # Repère vertical
                    if corner_y == trim_y1:  # Côté bas
                        v_start_y = corner_y - mark_offset - actual_mark_v
                        v_end_y = corner_y - mark_offset
                    else:  # Côté haut
                        v_start_y = corner_y + mark_offset
                        v_end_y = corner_y + mark_offset + actual_mark_v
                    
                    marks_stream += f"{corner_x} {v_start_y} m {corner_x} {v_end_y} l S\n"
        
        # Ajouter les repères au contenu de la page
        from pikepdf import Stream
        existing = page.Contents.read_bytes() if page.Contents else b""
        new_content = existing + marks_stream.encode()
        page.Contents = Stream(pdf, new_content)
        
        self.log_debug(f"✅ Repères de coupe ajoutés")