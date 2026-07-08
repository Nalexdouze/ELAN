# ============================================================================
# FILE: /opt/elan/app/actions/raster.py
# VERSION : 40 - Fix: deux méthodes restauration (centered pour CMYK, direct pour separated)
# ============================================================================

import os
import subprocess
import shutil
import zlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from .base import Action, ActionError


# ============================================================================
# FONCTION WORKER POUR PARALLÉLISATION - CONVERSION
# ============================================================================

def _convert_single_page_worker(args):
    """Convertit une page PDF → TIFF"""
    page_file, page_num, output_dir, params_dict = args
    
    tif_file = output_dir / f"page_{page_num:04d}.tif"
    
    resolution = params_dict["resolution"]
    color_mode = params_dict["color_mode"]
    color_profile = params_dict["color_profile"]
    compression = params_dict["tiff_compression"]
    
    device = "tiff32nc" if color_mode == "cmyk" else "tiffgray"
    
    gs_cmd = [
        "gs", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET",
        f"-sDEVICE={device}", f"-r{resolution}",
        "-dGraphicsAlphaBits=4", "-dTextAlphaBits=4",
    ]
    
    if color_mode == "cmyk":
        icc_profiles = {
            "FOGRA51": "/usr/share/color/icc/PSOcoated_v3.icc",
            "FOGRA52": "/usr/share/color/icc/PSOuncoated_v3_FOGRA52.icc",
        }
        icc_path = icc_profiles.get(color_profile)
        
        if icc_path and os.path.exists(icc_path):
            gs_cmd.extend([
                f"-sDefaultCMYKProfile={icc_path}",
                f"-sOutputICCProfile={icc_path}",
                "-dOverrideICC=true",
            ])
    
    if compression != "none":
        gs_cmd.append(f"-sCompression={compression}")
    
    gs_cmd.append(f"-sOutputFile={tif_file}")
    gs_cmd.append(str(page_file))
    
    result = subprocess.run(gs_cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0 or not tif_file.exists():
        raise RuntimeError(f"Page {page_num} erreur: {result.stderr}")
    
    return tif_file


# ============================================================================
# FONCTION WORKER POUR PARALLÉLISATION - ASSEMBLAGE BATCH
# ============================================================================

def _assemble_batch_worker(args):
    """Assemble un petit batch de TIFF → PDF"""
    batch_tif_files, batch_pdf_path, batch_num = args
    
    try:
        import img2pdf
        from PIL import Image
        
        Image.MAX_IMAGE_PIXELS = None
        pdf_bytes = img2pdf.convert([str(p) for p in batch_tif_files])
        
        with open(batch_pdf_path, "wb") as f:
            f.write(pdf_bytes)
        
        if not batch_pdf_path.exists():
            raise RuntimeError(f"Batch {batch_num} non créé")
        
        return batch_pdf_path
        
    except Exception as e:
        raise RuntimeError(f"Erreur assemblage batch {batch_num}: {e}")


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class RasterAction(Action):
    """Rasterise un PDF en TIFF CMYK, Grayscale ou avec séparation tons directs"""
    
    @property
    def name(self) -> str:
        return "raster"
    
    def validate_config(self):
        """Valide la configuration avec valeurs par défaut"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("resolution", 300)
        params.setdefault("color_mode", "cmyk")
        params.setdefault("tiff_compression", "lzw")
        params.setdefault("color_profile", "FOGRA51")
        params.setdefault("output_suffix", "_raster")
        params.setdefault("parallel", True)
        params.setdefault("max_workers", None)
        params.setdefault("keep_boxes", True)
        params.setdefault("keep_annotations", False)
        params.setdefault("keep_layers", False)
        
        # Batch size pour assemblage
        params.setdefault("assembly_batch_size", 4)
        
        # Validation
        valid_color_modes = ["cmyk", "gray", "separated"]
        if params["color_mode"] not in valid_color_modes:
            raise ActionError(f"color_mode doit être: {', '.join(valid_color_modes)}")
        
        valid_profiles = ["FOGRA51", "FOGRA52"]
        if params["color_profile"] not in valid_profiles:
            raise ActionError(f"color_profile doit être: {', '.join(valid_profiles)}")
        
        valid_tiff_comp = ["none", "lzw"]
        if params["tiff_compression"] not in valid_tiff_comp:
            raise ActionError(f"tiff_compression doit être: {', '.join(valid_tiff_comp)}")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """Rasterise le PDF en TIFF"""
        params = self.config["params"]
        
        # Détecter le dossier de travail (genstore du job)
        input_path = Path(file_path)
        work_dir = input_path.parent
        
        self.log_info(f"🔨 Rasterisation dans: {work_dir.name}")
        
        try:
            # Construire le nom de sortie
            output_suffix = params["output_suffix"]
            output_name = f"{input_path.stem}{output_suffix}{input_path.suffix}"
            output_path = work_dir / output_name
            
            # Sauvegarder les boîtes PDF si demandé
            saved_boxes = None
            if params.get("keep_boxes"):
                saved_boxes = self._extract_pdf_boxes(input_path)
            
            # Créer dossier images
            images_dir = work_dir / "images"
            images_dir.mkdir(exist_ok=True)
            
            # Rasteriser selon le mode
            if params["color_mode"] == "separated":
                self.log_info(f"🎨 Mode séparation tons directs à {params['resolution']} DPI")
                # Mode séparation : workflow complet avec reconstruction PDF
                self._process_separated(input_path, output_path, params, saved_boxes)
            else:
                # Mode standard CMYK/Gray
                tif_files = self._pdf_to_tiff_parallel(input_path, images_dir, params)
                self._tiff_to_pdf_parallel(tif_files, output_path, params)
                
                # Restaurer les boîtes
                if saved_boxes and output_path.exists():
                    self._restore_pdf_boxes_centered(output_path, saved_boxes)
            
            # Vérifier existence
            if not output_path.exists():
                raise ActionError(f"Fichier de sortie non créé: {output_path}")
            
            self.log_info(f"✅ PDF rasterisé: {output_path}")
            
            return str(output_path)
            
        except Exception as e:
            raise ActionError(f"Erreur rasterisation: {e}")
    
    # ========================================================================
    # MODE STANDARD (CMYK / GRAY)
    # ========================================================================
    
    def _pdf_to_tiff_parallel(self, input_path: Path, output_dir: Path, params: dict) -> list:
        """Convertit PDF → TIFF avec parallélisation intelligente"""
        resolution = params["resolution"]
        color_mode = params["color_mode"]
        parallel = params["parallel"]
        
        self.log_info(f"🔧 Conversion PDF → TIFF ({color_mode.upper()}) à {resolution} DPI")
        
        total_pages = self._count_pdf_pages(input_path)
        self.log_info(f"   📄 {total_pages} page(s) détectées")
        
        if not parallel or total_pages < 5:
            self.log_info(f"   ⚙️  Mode séquentiel")
            return self._pdf_to_tiff_sequential(input_path, output_dir, params)
        
        max_workers = params["max_workers"] or os.cpu_count()
        self.log_info(f"   ⚙️  Mode parallèle : {max_workers} workers")
        
        # Extraction pages
        pages_dir = output_dir.parent / "pages"
        pages_dir.mkdir(exist_ok=True)
        
        self.log_info(f"   📑 Extraction des pages...")
        page_files = self._extract_pages(input_path, pages_dir, total_pages)
        
        # Conversion parallèle
        self.log_info(f"   🚀 Conversion parallèle...")
        tif_files = self._convert_pages_parallel(page_files, output_dir, params, max_workers)
        
        self.log_info(f"   ✅ {len(tif_files)} fichier(s) TIFF générés")
        
        return tif_files
    
    def _count_pdf_pages(self, pdf_path: Path) -> int:
        """Compte le nombre de pages avec qpdf"""
        try:
            result = subprocess.run(
                ["qpdf", "--show-npages", str(pdf_path)],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                raise ActionError(f"Impossible de compter les pages: {result.stderr}")
            
            return int(result.stdout.strip())
        except Exception as e:
            raise ActionError(f"Erreur comptage pages: {e}")
    
    def _extract_pages(self, input_path: Path, pages_dir: Path, total_pages: int) -> list:
        """Extrait chaque page en PDF individuel"""
        page_files = []
        
        for page_num in range(1, total_pages + 1):
            page_file = pages_dir / f"page_{page_num:04d}.pdf"
            
            cmd = [
                "qpdf", str(input_path),
                "--pages", ".", str(page_num), "--",
                str(page_file)
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    raise ActionError(f"Extraction page {page_num}: {result.stderr}")
                
                if page_file.exists():
                    page_files.append(page_file)
                else:
                    raise ActionError(f"Page {page_num} non créée")
            except subprocess.TimeoutExpired:
                raise ActionError(f"Timeout extraction page {page_num}")
            except Exception as e:
                raise ActionError(f"Erreur extraction page {page_num}: {e}")
        
        return page_files
    
    def _convert_pages_parallel(self, page_files: list, output_dir: Path, 
                                 params: dict, max_workers: int) -> list:
        """Convertit les pages PDF → TIFF en parallèle"""
        params_dict = {
            "resolution": params["resolution"],
            "color_mode": params["color_mode"],
            "color_profile": params["color_profile"],
            "tiff_compression": params["tiff_compression"],
        }
        
        worker_args = [
            (page_file, i+1, output_dir, params_dict)
            for i, page_file in enumerate(page_files)
        ]
        
        tif_files = []
        completed = 0
        total = len(page_files)
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_convert_single_page_worker, args): args[1]
                for args in worker_args
            }
            
            for future in as_completed(futures):
                page_num = futures[future]
                
                try:
                    tif_file = future.result()
                    tif_files.append(tif_file)
                    completed += 1
                    
                    # Afficher progression tous les 10%
                    progress_step = max(1, total // 10)
                    if completed % progress_step == 0 or completed == total:
                        progress = (completed / total) * 100
                        self.log_progress(f"      Progression : {completed}/{total} ({progress:.0f}%)")
                except Exception as e:
                    raise ActionError(f"Erreur page {page_num}: {e}")
        
        tif_files.sort()
        return tif_files
    
    def _pdf_to_tiff_sequential(self, input_path: Path, output_dir: Path, params: dict) -> list:
        """Mode séquentiel classique"""
        resolution = params["resolution"]
        color_mode = params["color_mode"]
        color_profile = params["color_profile"]
        compression = params["tiff_compression"]
        
        devices = {"cmyk": "tiff32nc", "gray": "tiffgray"}
        device = devices[color_mode]
        
        gs_cmd = [
            "gs", "-dNOPAUSE", "-dBATCH", "-dSAFER",
            f"-sDEVICE={device}", f"-r{resolution}",
            "-dGraphicsAlphaBits=4", "-dTextAlphaBits=4",
        ]
        
        if color_mode == "cmyk":
            self._apply_icc_profile(gs_cmd, color_profile)
        
        if compression != "none":
            gs_cmd.append(f"-sCompression={compression}")
        
        gs_cmd.append(f"-sOutputFile={output_dir}/page_%04d.tif")
        gs_cmd.append(str(input_path))
        
        try:
            result = subprocess.run(gs_cmd, capture_output=True, text=True, timeout=2400)
            
            if result.returncode != 0:
                raise ActionError(f"Conversion TIFF: {result.stderr}")
            
            tif_files = sorted(output_dir.glob("page_*.tif"))
            if not tif_files:
                raise ActionError("Aucune image TIFF générée")
            
            self.log_info(f"   ✅ {len(tif_files)} fichier(s) TIFF")
            return tif_files
        except subprocess.TimeoutExpired:
            raise ActionError("Timeout conversion TIFF")
        except Exception as e:
            raise ActionError(f"Erreur conversion TIFF: {e}")
    
    def _tiff_to_pdf_parallel(self, tif_files: list, output_path: Path, params: dict):
        """Convertit TIFF → PDF avec assemblage parallèle par petits batch"""
        batch_size = params["assembly_batch_size"]
        total_pages = len(tif_files)
        
        self.log_info(f"🔧 Assemblage TIFF → PDF ({total_pages} pages)")
        
        # Si moins de 2 batch, conversion directe
        if total_pages <= batch_size:
            self.log_info(f"   📦 Conversion directe")
            self._tiff_to_pdf_direct(tif_files, output_path)
            return
        
        # Calcul des batch
        num_batches = (total_pages + batch_size - 1) // batch_size
        max_workers = min(8, os.cpu_count() or 4)
        
        self.log_info(f"   📦 Assemblage parallèle: {num_batches} batch de {batch_size} pages")
        self.log_info(f"   ⚙️  Workers assemblage: {max_workers}")
        
        batch_dir = output_path.parent / "batches"
        batch_dir.mkdir(exist_ok=True)
        
        # Préparer les arguments pour les workers
        worker_args = []
        for i in range(0, total_pages, batch_size):
            batch_num = i // batch_size + 1
            batch = tif_files[i:i+batch_size]
            batch_pdf = batch_dir / f"batch_{batch_num:03d}.pdf"
            
            worker_args.append((batch, batch_pdf, batch_num))
        
        # Assemblage parallèle des batch
        batch_pdfs = []
        completed = 0
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_assemble_batch_worker, args): args[2]
                for args in worker_args
            }
            
            for future in as_completed(futures):
                batch_num = futures[future]
                
                try:
                    batch_pdf = future.result()
                    batch_pdfs.append(batch_pdf)
                    completed += 1
                    
                    progress = (completed / num_batches) * 100
                    self.log_progress(f"      Batch {completed}/{num_batches} ({progress:.0f}%)")
                    
                except Exception as e:
                    raise ActionError(f"Erreur batch {batch_num}: {e}")
        
        # Trier les batch (important pour l'ordre)
        batch_pdfs.sort()
        
        # Fusion finale
        self.log_info(f"   🔗 Assemblage final ({len(batch_pdfs)} batch)")
        self._merge_pdfs(batch_pdfs, output_path)
    
    def _tiff_to_pdf_direct(self, tif_files: list, output_path: Path):
        """Conversion TIFF → PDF directe"""
        try:
            import img2pdf
            from PIL import Image
            
            Image.MAX_IMAGE_PIXELS = None
            pdf_bytes = img2pdf.convert([str(p) for p in tif_files])
            
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            
            if not output_path.exists():
                raise ActionError("PDF non créé")
        except ImportError:
            raise ActionError("img2pdf non disponible")
        except MemoryError:
            raise ActionError("Mémoire insuffisante")
        except Exception as e:
            raise ActionError(f"Erreur img2pdf: {e}")
    
    def _merge_pdfs(self, pdf_files: list, output_path: Path):
        """Fusionne plusieurs PDF avec qpdf"""
        cmd = ["qpdf", "--empty", "--pages"]
        cmd.extend([str(p) for p in pdf_files])
        cmd.extend(["--", str(output_path)])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise ActionError(f"qpdf merge: {result.stderr}")
            
            if not output_path.exists():
                raise ActionError("PDF fusionné non créé")
            
            output_size = os.path.getsize(output_path)
            self.log_info(f"   ✅ PDF créé: {output_size:,} bytes")
        except subprocess.TimeoutExpired:
            raise ActionError("Timeout fusion PDF")
        except Exception as e:
            raise ActionError(f"Erreur fusion: {e}")
    
    def _apply_icc_profile(self, gs_cmd: list, color_profile: str):
        """Applique le profil ICC CMYK"""
        icc_profiles = {
            "FOGRA51": "/usr/share/color/icc/PSOcoated_v3.icc",
            "FOGRA52": "/usr/share/color/icc/PSOuncoated_v3_FOGRA52.icc",
        }
        
        icc_path = icc_profiles.get(color_profile)
        
        if icc_path and os.path.exists(icc_path):
            gs_cmd.extend([
                "-sDefaultCMYKProfile=" + icc_path,
                "-sOutputICCProfile=" + icc_path,
                "-dOverrideICC=true",
            ])
            self.log_info(f"   ✅ Profil {color_profile} appliqué")
        else:
            raise ActionError(f"Profil ICC {color_profile} manquant")
    
    def _extract_pdf_boxes(self, pdf_path: Path):
        """Extrait les boîtes PDF"""
        try:
            import pikepdf
            
            self.log_info(f"💾 Extraction des métadonnées PDF...")
            pdf = pikepdf.open(pdf_path)
            
            boxes_data = []
            for page_num, page in enumerate(pdf.pages):
                page_boxes = {}
                
                if "/MediaBox" in page:
                    page_boxes["/MediaBox"] = [float(v) for v in page.MediaBox]
                
                for box_name in ["/TrimBox", "/BleedBox", "/CropBox", "/ArtBox"]:
                    if box_name in page:
                        page_boxes[box_name] = [float(v) for v in page[box_name]]
                
                if page_boxes:
                    boxes_data.append({"page": page_num, "boxes": page_boxes})
            
            pdf.close()
            
            if boxes_data:
                self.log_info(f"   📦 {len(boxes_data)} page(s) avec boîtes")
            
            return boxes_data if boxes_data else None
        except ImportError:
            return None
        except Exception as e:
            self.log_error(f"Erreur extraction boîtes: {e}")
            return None
    
    def _restore_pdf_boxes_centered(self, pdf_path: Path, boxes_data: list):
        """
        Restaure les boîtes avec recentrage
        
        Utilisé en mode CMYK/Gray où GhostScript peut changer les dimensions
        """
        try:
            import pikepdf
            
            self.log_info(f"🔄 Restauration des métadonnées PDF...")
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)
            
            for box_info in boxes_data:
                page_num = box_info["page"]
                if page_num >= len(pdf.pages):
                    continue
                
                page = pdf.pages[page_num]
                original_boxes = box_info["boxes"]
                
                new_mediabox = page.MediaBox
                new_x1, new_y1, new_x2, new_y2 = [float(v) for v in new_mediabox]
                new_center_x = (new_x1 + new_x2) / 2
                new_center_y = (new_y1 + new_y2) / 2
                
                if "/MediaBox" in original_boxes:
                    old_x1, old_y1, old_x2, old_y2 = original_boxes["/MediaBox"]
                    old_center_x = (old_x1 + old_x2) / 2
                    old_center_y = (old_y1 + old_y2) / 2
                    
                    offset_x = new_center_x - old_center_x
                    offset_y = new_center_y - old_center_y
                else:
                    offset_x = 0
                    offset_y = 0
                
                for box_name, box_value in original_boxes.items():
                    if box_name == "/MediaBox":
                        continue
                    
                    adjusted_box = [
                        box_value[0] + offset_x,
                        box_value[1] + offset_y,
                        box_value[2] + offset_x,
                        box_value[3] + offset_y
                    ]
                    
                    page[box_name] = adjusted_box
            
            pdf.save()
            pdf.close()
            
            self.log_info(f"✅ Métadonnées restaurées")
        except Exception as e:
            self.log_error(f"Erreur restauration boîtes: {e}")
    
    def _restore_pdf_boxes_direct(self, pdf_path: Path, boxes_data: list):
        """
        Restaure les boîtes exactement comme elles étaient
        
        Utilisé en mode Separated où les dimensions MediaBox sont préservées
        """
        try:
            import pikepdf
            
            self.log_info(f"🔄 Restauration des métadonnées PDF...")
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)
            
            for box_info in boxes_data:
                page_num = box_info["page"]
                if page_num >= len(pdf.pages):
                    continue
                
                page = pdf.pages[page_num]
                original_boxes = box_info["boxes"]
                
                # Restaurer toutes les boxes exactement
                for box_name, box_value in original_boxes.items():
                    page[box_name] = box_value
            
            pdf.save()
            pdf.close()
            
            self.log_info(f"✅ Métadonnées restaurées")
        except Exception as e:
            self.log_error(f"Erreur restauration boîtes: {e}")
    
    # ========================================================================
    # MODE SÉPARATION TONS DIRECTS (Gold, Silver, Pantone, etc.)
    # ========================================================================
    
    def _process_separated(self, input_path: Path, output_path: Path, 
                            params: dict, saved_boxes: dict = None):
        """
        Traitement complet avec séparation des tons directs
        
        Workflow:
        1. GhostScript tiffsep → plaques TIFF grayscale séparées
        2. Inversion des plaques (GS génère noir=encre, PDF attend blanc=encre)
        3. Reconstruction PDF avec colorspaces Separation
        """
        resolution = params["resolution"]
        work_dir = output_path.parent
        
        # Récupérer dimensions originales
        width_pt, height_pt = self._get_pdf_dimensions(input_path)
        self.log_info(f"   📐 Dimensions: {width_pt:.1f} × {height_pt:.1f} pt")
        
        # Compter les pages
        total_pages = self._count_pdf_pages(input_path)
        self.log_info(f"   📄 {total_pages} page(s) à traiter")
        
        if total_pages > 1:
            # Multi-pages : traiter page par page puis fusionner
            self._process_separated_multipage(
                input_path, output_path, params, 
                width_pt, height_pt, total_pages,
                saved_boxes
            )
        else:
            # Single page : traitement direct
            plates_dir = work_dir / "plates"
            plates_dir.mkdir(exist_ok=True)
            
            # Étape 1: Séparation avec tiffsep
            plates = self._ghostscript_tiffsep(input_path, plates_dir, resolution)
            
            if not plates:
                raise ActionError("Aucune plaque générée par tiffsep")
            
            self.log_info(f"   🎨 {len(plates)} plaque(s): {', '.join(plates.keys())}")
            
            # Étape 2: Reconstruction PDF avec séparations
            self._create_pdf_with_separations(plates, output_path, width_pt, height_pt)
            
            # Restaurer les boîtes (restauration directe car dimensions préservées)
            if saved_boxes and output_path.exists():
                self._restore_pdf_boxes_direct(output_path, saved_boxes)
            
            # Nettoyage
            shutil.rmtree(plates_dir, ignore_errors=True)
    
    def _process_separated_multipage(self, input_path: Path, output_path: Path, 
                                      params: dict, width_pt: float, height_pt: float,
                                      total_pages: int, saved_boxes: dict = None):
        """Traitement multi-pages avec séparation"""
        resolution = params["resolution"]
        work_dir = output_path.parent
        
        pages_dir = work_dir / "separated_pages"
        pages_dir.mkdir(exist_ok=True)
        
        page_pdfs = []
        
        for page_num in range(1, total_pages + 1):
            self.log_info(f"   📄 Page {page_num}/{total_pages}")
            
            # Extraire la page
            page_pdf = pages_dir / f"page_{page_num:04d}.pdf"
            self._extract_single_page(input_path, page_num, page_pdf)
            
            # Créer dossier pour les plaques de cette page
            plates_dir = work_dir / f"plates_p{page_num:04d}"
            plates_dir.mkdir(exist_ok=True)
            
            # Séparer
            plates = self._ghostscript_tiffsep(page_pdf, plates_dir, resolution)
            
            if not plates:
                raise ActionError(f"Aucune plaque pour page {page_num}")
            
            self.log_info(f"      🎨 {len(plates)} plaque(s)")
            
            # Reconstruire cette page
            page_output = pages_dir / f"page_{page_num:04d}_sep.pdf"
            self._create_pdf_with_separations(plates, page_output, width_pt, height_pt)
            
            page_pdfs.append(page_output)
            
            # Nettoyage plaques
            shutil.rmtree(plates_dir, ignore_errors=True)
            page_pdf.unlink(missing_ok=True)
        
        # Fusionner toutes les pages
        self.log_info(f"   🔗 Fusion de {len(page_pdfs)} page(s)")
        self._merge_pdfs(page_pdfs, output_path)
        
        # Restaurer les boîtes (restauration directe car dimensions préservées)
        if saved_boxes and output_path.exists():
            self._restore_pdf_boxes_direct(output_path, saved_boxes)
        
        # Nettoyage final
        shutil.rmtree(pages_dir, ignore_errors=True)
    
    def _get_pdf_dimensions(self, pdf_path: Path) -> tuple:
        """Récupère les dimensions du PDF en points"""
        try:
            import pikepdf
            pdf = pikepdf.open(pdf_path)
            page = pdf.pages[0]
            
            # Utiliser MediaBox pour rasteriser sur toute la page
            # (comme en mode CMYK/Gray standard)
            box = page.MediaBox
            
            x1, y1, x2, y2 = [float(v) for v in box]
            width = x2 - x1
            height = y2 - y1
            
            pdf.close()
            return width, height
        except Exception as e:
            self.log_error(f"Erreur lecture dimensions: {e}")
            return 595, 842  # A4 par défaut
    
    def _extract_single_page(self, input_path: Path, page_num: int, output_path: Path):
        """Extrait une page spécifique avec qpdf"""
        cmd = [
            "qpdf", str(input_path),
            "--pages", ".", str(page_num), "--",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise ActionError(f"Extraction page {page_num}: {result.stderr}")
        
        if not output_path.exists():
            raise ActionError(f"Page {page_num} non créée")
    
    def _ghostscript_tiffsep(self, pdf_path: Path, output_dir: Path, 
                             resolution: int) -> dict:
        """
        Sépare le PDF en plaques avec GhostScript tiffsep
        
        IMPORTANT: Utilise %d (pas %s) pour le pattern de sortie !
        GhostScript génère: plate1(Cyan).tif, plate1(Magenta).tif, etc.
        
        Returns:
            Dict[str, Path]: {nom_couleur: chemin_fichier}
        """
        output_base = output_dir / "plate"
        
        cmd = [
            "gs",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=tiffsep",
            f"-r{resolution}",
            "-dGraphicsAlphaBits=4",
            "-dTextAlphaBits=4",
            "-sCompression=none",
            f"-sOutputFile={output_base}%d.tif",  # %d et non %s !
            str(pdf_path)
        ]
        
        self.log_debug(f"Commande tiffsep: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            self.log_error(f"GhostScript erreur: {result.stderr}")
            return {}
        
        # Lister les plaques générées
        # Format: plate1(Cyan).tif, plate1(Magenta).tif, etc.
        all_files = sorted(output_dir.glob("plate*.tif"))
        
        plates = {}
        
        for f in all_files:
            # Extraire le nom de la couleur entre parenthèses
            if '(' in f.name and ')' in f.name:
                start = f.name.index('(') + 1
                end = f.name.index(')')
                plate_name = f.name[start:end]
                plates[plate_name] = f
        
        self.log_debug(f"Plaques trouvées: {list(plates.keys())}")
        
        return plates
    
    def _create_pdf_with_separations(self, plates: dict, output_pdf: Path,
                                      page_width_pt: float, page_height_pt: float):
        """
        Crée un PDF avec des images en colorspace Separation
        
        Chaque plaque devient une image avec son propre colorspace Separation,
        permettant de préserver les tons directs (Gold, Silver, etc.)
        """
        try:
            import pikepdf
            from pikepdf import Dictionary, Name, Array, Stream
            from PIL import Image
            import PIL.ImageOps
        except ImportError as e:
            raise ActionError(f"Module manquant: {e}")
        
        Image.MAX_IMAGE_PIXELS = None
        
        # Ordre des plaques : CMYK d'abord, puis spots alphabétiquement
        cmyk_order = ["Cyan", "Magenta", "Yellow", "Black"]
        cmyk_fallback = {
            "Cyan": [1.0, 0.0, 0.0, 0.0],
            "Magenta": [0.0, 1.0, 0.0, 0.0],
            "Yellow": [0.0, 0.0, 1.0, 0.0],
            "Black": [0.0, 0.0, 0.0, 1.0],
        }
        
        # Fallback CMYK pour spots courants
        spot_fallback = {
            "Gold": [0.0, 0.2, 0.8, 0.1],
            "Silver": [0.0, 0.0, 0.0, 0.3],
            "PANTONE 877 C": [0.0, 0.0, 0.0, 0.3],
            "White": [0.0, 0.0, 0.0, 0.0],
        }
        
        # Collecter les plaques dans l'ordre
        ordered_plates = []
        
        # CMYK d'abord
        for name in cmyk_order:
            if name in plates:
                ordered_plates.append((name, plates[name], cmyk_fallback[name]))
        
        # Spots ensuite (alphabétiquement)
        spot_names = sorted([n for n in plates.keys() if n not in cmyk_order])
        for name in spot_names:
            fallback = spot_fallback.get(name, [0.0, 1.0, 0.0, 0.0])  # Magenta par défaut
            ordered_plates.append((name, plates[name], fallback))
        
        self.log_debug(f"Ordre des plaques: {[p[0] for p in ordered_plates]}")
        
        # Charger la première plaque pour avoir les dimensions image
        first_img = Image.open(ordered_plates[0][1])
        img_width, img_height = first_img.size
        first_img.close()
        
        self.log_debug(f"Dimensions image: {img_width} × {img_height} px")
        
        # Créer le PDF
        pdf = pikepdf.new()
        
        # Créer la page
        page = pdf.add_blank_page(page_size=(page_width_pt, page_height_pt))
        
        # Initialiser les ressources
        page.Resources = Dictionary()
        page.Resources.XObject = Dictionary()
        page.Resources.ExtGState = Dictionary()
        
        # ExtGState pour overprint (important pour les tons directs)
        page.Resources.ExtGState[Name("/GS_OP")] = pdf.make_indirect(Dictionary(
            Type=Name.ExtGState,
            OP=True,
            op=True,
            OPM=1
        ))
        
        # Construire le content stream
        content_parts = []
        content_parts.append("q")
        content_parts.append("/GS_OP gs")
        content_parts.append(f"{page_width_pt} 0 0 {page_height_pt} 0 0 cm")
        
        for i, (plate_name, plate_path, fallback_cmyk) in enumerate(ordered_plates):
            self.log_debug(f"   Traitement: {plate_name}")
            
            # Charger l'image et INVERSER (GS: noir=encre, PDF: blanc=encre)
            img = Image.open(plate_path)
            if img.mode != 'L':
                img = img.convert('L')
            img = PIL.ImageOps.invert(img)
            
            img_bytes = img.tobytes()
            img.close()
            
            # Compresser les données
            compressed = zlib.compress(img_bytes, level=6)
            
            # Créer la fonction de transformation (tint transform)
            tint_function = pdf.make_indirect(Dictionary(
                FunctionType=2,
                Domain=Array([0.0, 1.0]),
                Range=Array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0]),
                C0=Array([0.0, 0.0, 0.0, 0.0]),
                C1=Array(fallback_cmyk),
                N=1.0
            ))
            
            # Créer le colorspace Separation
            separation_cs = pdf.make_indirect(Array([
                Name.Separation,
                Name(f"/{plate_name}"),
                Name.DeviceCMYK,
                tint_function
            ]))
            
            # Créer l'image XObject
            xobj_name = f"Im{i}"
            
            img_stream = Stream(pdf, compressed)
            img_stream[Name.Type] = Name.XObject
            img_stream[Name.Subtype] = Name.Image
            img_stream[Name.Width] = img_width
            img_stream[Name.Height] = img_height
            img_stream[Name.BitsPerComponent] = 8
            img_stream[Name.ColorSpace] = separation_cs
            img_stream[Name.Filter] = Name.FlateDecode
            
            page.Resources.XObject[Name(f"/{xobj_name}")] = img_stream
            content_parts.append(f"/{xobj_name} Do")
        
        content_parts.append("Q")
        
        content_str = "\n".join(content_parts)
        page.Contents = Stream(pdf, content_str.encode('latin-1'))
        
        # Sauvegarder
        pdf.save(output_pdf)
        pdf.close()
        
        if output_pdf.exists():
            size_mb = output_pdf.stat().st_size / (1024 * 1024)
            self.log_info(f"   ✅ PDF avec séparations créé ({size_mb:.2f} MB)")
        else:
            raise ActionError("PDF non créé")