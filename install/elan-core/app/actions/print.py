# ============================================================================
# FILE: /opt/elan/app/actions/print.py
# VERSION : 13
# ============================================================================

import os
import subprocess
import shutil
import uuid
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from .base import Action, ActionError


class PrintAction(Action):
    """
    Imprime sur n'importe quelle imprimante CUPS (traceurs, presses, imprimantes bureau)
    
    Fonctionnalités:
    - Support universel via CUPS (Epson, HP, Canon, Brother, etc.)
    - Détection automatique orientation (portrait/paysage)
    - Rotation intelligente selon format papier/rouleau
    - Imbrication: accumule les jobs pendant N minutes pour optimiser l'espace
    - Mode rouleau (traceurs) ou feuille (imprimantes classiques)
    - Configuration par profil réutilisable
    """
    
    # Cache global pour l'imbrication (partagé entre instances)
    _nesting_queue = []
    _nesting_lock_file = Path("/genstore/.print_nesting.lock")
    
    @property
    def name(self) -> str:
        return "print"
    
    def validate_config(self):
        """Valide la configuration"""
        params = self.config.get("params", {})
        
        # Valeurs par défaut
        params.setdefault("printer_name", "default")         # Nom dans CUPS ou "default"
        params.setdefault("printer_ip", None)                # IP si config auto
        params.setdefault("printer_uri", None)               # URI complète (prioritaire sur IP)
        params.setdefault("printer_driver", "everywhere")    # everywhere, gutenprint, ou chemin PPD
        params.setdefault("printer_model", None)             # Modèle pour gutenprint (ex: "escp2-sc-t7200")
        
        # Mode imprimante
        params.setdefault("printer_type", "roll")            # roll (traceur), sheet (feuille), auto
        params.setdefault("media_size", None)                # A4, A3, Letter, roll, ou largeur en mm
        params.setdefault("roll_width_mm", 914)              # Largeur rouleau si mode roll
        params.setdefault("media_type", "plain")             # plain, photo, matte, glossy, etc.
        params.setdefault("quality", "high")                 # draft, normal, high
        params.setdefault("color_mode", "color")             # color, grayscale
        
        # Marges de sécurité
        params.setdefault("margin_left", 3)                  # Marge gauche (mm)
        params.setdefault("margin_right", 3)                 # Marge droite (mm)
        params.setdefault("margin_top", 3)                   # Marge haut (mm)
        params.setdefault("margin_bottom", 3)                # Marge bas (mm)
        
        # Imbrication
        params.setdefault("nesting_enabled", False)          # Activer imbrication
        params.setdefault("nesting_timeout", 300)            # Attente max: 5 minutes
        params.setdefault("nesting_gap", 5)                  # Espacement entre jobs (mm)
        
        # Rotation automatique
        params.setdefault("auto_rotate", True)               # Rotation si gain de place
        params.setdefault("force_rotation", None)            # "90", "180", "270" ou None
                
        # Validation
        if not params["printer_ip"] and not params["printer_uri"] and params["printer_name"] == "default":
            raise ActionError("Spécifier printer_name, printer_ip ou printer_uri")
        
        valid_printer_type = ["roll", "sheet", "auto"]
        if params["printer_type"] not in valid_printer_type:
            raise ActionError(f"printer_type doit être: {', '.join(valid_printer_type)}")
        
        valid_quality = ["draft", "normal", "high"]
        if params["quality"] not in valid_quality:
            raise ActionError(f"quality doit être: {', '.join(valid_quality)}")
        
        valid_color = ["color", "grayscale"]
        if params["color_mode"] not in valid_color:
            raise ActionError(f"color_mode doit être: {', '.join(valid_color)}")
        
        if params["force_rotation"] and params["force_rotation"] not in ["90", "180", "270"]:
            raise ActionError("force_rotation doit être: 90, 180, 270 ou null")
        
        # Vérifier largeur rouleau
        if params["roll_width_mm"] < 100 or params["roll_width_mm"] > 1500:
            raise ActionError(f"roll_width_mm invalide: {params['roll_width_mm']}mm")
        
        self.config["params"] = params
    
    def execute(self, file_path: str) -> str:
        """
        Imprime le PDF sur l'Epson SC-T7200
        
        Config attendue:
        {
            "params": {
                "printer_name": "Epson-SC-T7200",
                "printer_ip": "192.168.8.70",
                "roll_width_mm": 914,              # Largeur rouleau (36")
                "media_type": "plain",
                "quality": "high",
                "color_mode": "color",
                
                "margin_left": 3,
                "margin_right": 3,
                "margin_top": 3,
                "margin_bottom": 3,
                
                "nesting_enabled": false,          # Imbrication désactivée par défaut
                "nesting_timeout": 300,            # 5 minutes
                "nesting_gap": 5,                  # 5mm entre jobs
                
                "auto_rotate": true,               # Rotation auto si optimisation
                "force_rotation": null             # Forcer rotation (90, 180, 270)
            }
        }
        """
        params = self.config["params"]
        
        # 1. Vérifier que CUPS est accessible
        self._check_cups()
        
        # 2. Vérifier/installer l'imprimante
        self._ensure_printer_configured(params)
        
        # 3. Analyser le PDF
        pdf_info = self._analyze_pdf(file_path)
        self.log_info(f"📄 PDF: {pdf_info['width']:.1f} × {pdf_info['height']:.1f} mm, {pdf_info['pages']} page(s)")
        
        # 4. Si imbrication activée, ajouter à la queue
        if params["nesting_enabled"]:
            return self._handle_nesting(file_path, pdf_info, params)
        
        # 5. Sinon, imprimer directement
        return self._print_pdf(file_path, pdf_info, params)
    
    def _check_cups(self):
        """Vérifie que CUPS est accessible"""
        try:
            result = subprocess.run(
                ["lpstat", "-r"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if "scheduler is running" not in result.stdout.lower():
                raise ActionError("CUPS n'est pas démarré. Installer avec: apt-get install cups")
            
        except FileNotFoundError:
            raise ActionError(
                "CUPS non installé. Installer avec:\n"
                "  apt-get update && apt-get install -y cups cups-client"
            )
        except Exception as e:
            raise ActionError(f"Erreur vérification CUPS: {e}")
    
    def _ensure_printer_configured(self, params: dict):
        """Vérifie/configure l'imprimante dans CUPS"""
        printer_name = params["printer_name"]
        
        # Si "default", utiliser l'imprimante par défaut existante
        if printer_name == "default":
            result = subprocess.run(
                ["lpstat", "-d"],
                capture_output=True,
                text=True
            )
            
            if "no system default destination" in result.stdout.lower():
                raise ActionError(
                    "Aucune imprimante par défaut configurée. "
                    "Spécifier printer_name ou configurer une imprimante par défaut."
                )
            
            self.log_info(f"✅ Utilisation imprimante par défaut du système")
            return
        
        # Vérifier si l'imprimante existe
        result = subprocess.run(
            ["lpstat", "-p", printer_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            self.log_debug(f"✅ Imprimante {printer_name} déjà configurée")
            return
        
        # Configuration automatique nécessaire
        if not params.get("printer_ip") and not params.get("printer_uri"):
            raise ActionError(
                f"Imprimante {printer_name} non trouvée. "
                "Spécifier printer_ip ou printer_uri pour configuration auto."
            )
        
        self.log_info(f"🖨️  Configuration de l'imprimante {printer_name}...")
        
        # Construire l'URI
        if params.get("printer_uri"):
            printer_uri = params["printer_uri"]
        else:
            printer_ip = params["printer_ip"]
            # Détecter le protocole selon le type d'imprimante
            # Socket (AppSocket/JetDirect) pour la plupart des imprimantes réseau
            printer_uri = f"socket://{printer_ip}:9100"
        
        self.log_info(f"   URI: {printer_uri}")
        
        try:
            # Déterminer le driver
            driver_option = self._get_driver_option(params)
            
            # Ajouter l'imprimante
            cmd = [
                "lpadmin",
                "-p", printer_name,
                "-v", printer_uri,
                "-E",  # Enable
            ]
            
            # Ajouter l'option driver
            cmd.extend(driver_option)
            
            self.log_debug(f"Commande: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.log_error(f"lpadmin stderr: {result.stderr}")
                raise ActionError(f"Impossible de configurer l'imprimante: {result.stderr}")
            
            self.log_info(f"✅ Imprimante {printer_name} configurée")
            
        except subprocess.TimeoutExpired:
            raise ActionError("Timeout configuration imprimante")
        except Exception as e:
            raise ActionError(f"Erreur configuration imprimante: {e}")
    
    def _get_driver_option(self, params: dict) -> list:
        """
        Détermine l'option driver pour lpadmin
        
        Returns:
            ["-m", "driver"] ou ["-P", "/path/to/ppd"]
        """
        driver = params["printer_driver"]
        
        # PPD explicite
        if driver.endswith(".ppd") or "/" in driver:
            if not os.path.exists(driver):
                raise ActionError(f"Fichier PPD introuvable: {driver}")
            self.log_info(f"   Driver: PPD personnalisé ({driver})")
            return ["-P", driver]
        
        # IPP Everywhere (recommandé)
        if driver == "everywhere":
            self.log_info(f"   Driver: IPP Everywhere (auto-détection)")
            return ["-m", "everywhere"]
        
        # Gutenprint
        if driver == "gutenprint":
            model = params.get("printer_model")
            if not model:
                # Essayer détection auto avec gutenprint
                self.log_info(f"   Driver: Gutenprint (auto)")
                return ["-m", "gutenprint"]
            else:
                # Modèle spécifique
                self.log_info(f"   Driver: Gutenprint ({model})")
                return ["-m", f"gutenprint.5.3://{model}/expert"]
        
        # Driver personnalisé
        self.log_info(f"   Driver: {driver}")
        return ["-m", driver]
    
    def _analyze_pdf(self, file_path: str) -> dict:
        """
        Analyse le PDF pour obtenir dimensions et nombre de pages
        
        Returns:
            {"width": mm, "height": mm, "pages": int, "orientation": "portrait"|"landscape"}
        """
        try:
            import pikepdf
            
            pdf = pikepdf.open(file_path)
            page = pdf.pages[0]  # Première page
            
            # Utiliser TrimBox si disponible, sinon MediaBox
            if "/TrimBox" in page:
                box = page.TrimBox
            else:
                box = page.MediaBox
            
            x1, y1, x2, y2 = [float(v) for v in box]
            width_mm = (x2 - x1) * 0.352778   # pt → mm
            height_mm = (y2 - y1) * 0.352778
            
            pages = len(pdf.pages)
            orientation = "landscape" if width_mm > height_mm else "portrait"
            
            pdf.close()
            
            return {
                "width": width_mm,
                "height": height_mm,
                "pages": pages,
                "orientation": orientation
            }
            
        except Exception as e:
            raise ActionError(f"Impossible d'analyser le PDF: {e}")
    
    def _handle_nesting(self, file_path: str, pdf_info: dict, params: dict) -> str:
        """
        Gère l'imbrication: accumule les jobs et imprime par lot
        
        Stratégie:
        1. Ajouter le job à la queue
        2. Attendre timeout OU largeur rouleau pleine
        3. Créer PDF imbriqué avec tous les jobs en largeur
        4. Imprimer le lot
        """
        nesting_timeout = params["nesting_timeout"]
        roll_width = params["roll_width_mm"]
        margin_left = params["margin_left"]
        margin_right = params["margin_right"]
        gap = params["nesting_gap"]
        
        # Charger la queue existante
        queue = self._load_nesting_queue()
        
        # Ajouter le job actuel
        job = {
            "file_path": file_path,
            "pdf_info": pdf_info,
            "timestamp": datetime.now().isoformat(),
            "width": pdf_info["width"],
            "height": pdf_info["height"]
        }
        
        queue.append(job)
        self.log_info(f"📦 Job ajouté à la queue d'imbrication ({len(queue)} job(s))")
        
        # Calculer la largeur totale nécessaire
        total_width = margin_left + margin_right
        total_width += sum(j["width"] for j in queue)
        total_width += gap * (len(queue) - 1)  # Gaps entre jobs
        
        # Déterminer si on doit imprimer maintenant
        should_print = False
        reason = ""
        
        # Condition 1: Largeur du rouleau atteinte
        if total_width >= roll_width * 0.95:  # 95% = sécurité
            should_print = True
            reason = f"largeur rouleau atteinte ({total_width:.1f}mm / {roll_width}mm)"
        
        # Condition 2: Timeout atteint
        if not should_print and len(queue) > 0:
            first_job_time = datetime.fromisoformat(queue[0]["timestamp"])
            elapsed = (datetime.now() - first_job_time).total_seconds()
            
            if elapsed >= nesting_timeout:
                should_print = True
                reason = f"timeout atteint ({elapsed:.0f}s / {nesting_timeout}s)"
        
        if should_print:
            self.log_info(f"🚀 Impression du lot: {reason}")
            
            # Créer le PDF imbriqué
            nested_pdf = self._create_nested_pdf(queue, params)
            
            # Imprimer
            result = self._print_pdf(nested_pdf, {"width": total_width, "height": max(j["height"] for j in queue), "pages": 1}, params)
            
            # Vider la queue
            self._clear_nesting_queue()
            
            # Nettoyer le PDF temporaire
            try:
                os.remove(nested_pdf)
            except Exception:
                pass
            
            return result
        else:
            # Sauvegarder la queue et attendre
            self._save_nesting_queue(queue)
            self.log_info(f"⏳ Attente d'autres jobs (largeur actuelle: {total_width:.1f}mm / {roll_width}mm)")
            
            # Retourner le chemin original (pas encore imprimé)
            return file_path
    
    def _create_nested_pdf(self, queue: List[dict], params: dict) -> str:
        """
        Crée un PDF avec tous les jobs côte à côte en largeur
        
        Layout horizontal: [Job1] [gap] [Job2] [gap] [Job3]
        """
        try:
            import pikepdf
            from pikepdf import Dictionary, Name, Array, Stream
            
            gap_mm = params["nesting_gap"]
            gap_pt = gap_mm / 0.352778
            
            # Calculer dimensions totales
            total_width = sum(j["width"] for j in queue) + gap_mm * (len(queue) - 1)
            max_height = max(j["height"] for j in queue)
            
            total_width_pt = total_width / 0.352778
            max_height_pt = max_height / 0.352778
            
            self.log_info(f"🔨 Création PDF imbriqué: {total_width:.1f} × {max_height:.1f} mm")
            
            # Créer le PDF de sortie
            output_pdf = pikepdf.new()
            
            # Créer une page blanche aux bonnes dimensions
            nested_page = output_pdf.add_blank_page(
                page_size=(total_width_pt, max_height_pt)
            )
            
            # Placer chaque PDF côte à côte
            current_x = 0
            
            for i, job in enumerate(queue):
                job_pdf = pikepdf.open(job["file_path"])
                job_page = job_pdf.pages[0]
                
                # Dimensions du job en points
                job_w_pt = job["width"] / 0.352778
                job_h_pt = job["height"] / 0.352778
                
                # Centrer verticalement si différentes hauteurs
                y_offset = (max_height_pt - job_h_pt) / 2
                
                # Placer le job
                self._place_page_on_sheet(
                    nested_page, job_page,
                    current_x, y_offset,
                    job_w_pt, job_h_pt
                )
                
                self.log_info(f"   ✅ Job {i+1}/{len(queue)} placé à x={current_x:.1f}pt")
                
                current_x += job_w_pt + gap_pt
                job_pdf.close()
            
            # Sauvegarder
            output_path = f"/genstore/nested_{uuid.uuid4().hex[:8]}.pdf"
            output_pdf.save(output_path)
            output_pdf.close()
            
            self.log_info(f"✅ PDF imbriqué créé: {output_path}")
            
            return output_path
            
        except Exception as e:
            raise ActionError(f"Erreur création PDF imbriqué: {e}")
    
    def _place_page_on_sheet(self, target_page, source_page, x, y, w, h):
        """Place une page source sur une page cible (helper pour imbrication)"""
        import pikepdf
        from pikepdf import Dictionary, Name, Array, Stream
        
        # Récupérer les dimensions de la page source
        src_mediabox = source_page.MediaBox
        src_x1, src_y1, src_x2, src_y2 = [float(v) for v in src_mediabox]
        src_width = src_x2 - src_x1
        src_height = src_y2 - src_y1
        
        # Matrice de transformation (scale + translation)
        scale_x = w / src_width
        scale_y = h / src_height
        
        matrix = [
            scale_x, 0,
            0, scale_y,
            x, y
        ]
        
        # S'assurer que la page a des Resources
        if "/Resources" not in target_page:
            target_page.Resources = Dictionary()
        
        if "/XObject" not in target_page.Resources:
            target_page.Resources.XObject = Dictionary()
        
        # Créer un nom unique
        xobj_name = f"Page{len(target_page.Resources.XObject) + 1}"
        
        # Copier le contenu de la page source
        if source_page.Contents is not None:
            if isinstance(source_page.Contents, list):
                content_bytes = b""
                for stream in source_page.Contents:
                    content_bytes += bytes(stream.read_bytes())
            else:
                content_bytes = bytes(source_page.Contents.read_bytes())
        else:
            content_bytes = b""
        
        # Créer le Form XObject
        form_dict = Dictionary(
            Type=Name.XObject,
            Subtype=Name.Form,
            FormType=1,
            BBox=Array([src_x1, src_y1, src_x2, src_y2]),
        )
        
        if "/Resources" in source_page:
            form_dict.Resources = source_page.Resources
        
        form_xobj = Stream(target_page.pdf, content_bytes)
        form_xobj.update(form_dict)
        
        target_page.Resources.XObject[Name(f"/{xobj_name}")] = form_xobj
        
        # Ajouter au contenu
        content_stream = f"q {' '.join(map(str, matrix))} cm /{xobj_name} Do Q\n"
        
        if target_page.Contents is None:
            target_page.Contents = Stream(target_page.pdf, content_stream.encode())
        else:
            existing = bytes(target_page.Contents.read_bytes())
            target_page.Contents = Stream(target_page.pdf, existing + content_stream.encode())
    
    def _print_pdf(self, file_path: str, pdf_info: dict, params: dict) -> str:
        """
        Imprime le PDF avec les bons paramètres
        
        Rotation automatique si nécessaire pour optimiser l'utilisation du rouleau
        """
        printer_name = params["printer_name"]
        roll_width = params["roll_width_mm"]
        auto_rotate = params["auto_rotate"]
        force_rotation = params["force_rotation"]
        
        pdf_width = pdf_info["width"]
        pdf_height = pdf_info["height"]
        
        # Déterminer la rotation
        rotation = 0
        
        if force_rotation:
            rotation = int(force_rotation)
            self.log_info(f"🔄 Rotation forcée: {rotation}°")
        
        elif auto_rotate:
            # Si le PDF est plus large que le rouleau, essayer rotation 90°
            if pdf_width > roll_width and pdf_height <= roll_width:
                rotation = 90
                self.log_info(f"🔄 Rotation auto 90° (PDF {pdf_width:.0f}mm > rouleau {roll_width}mm)")
            
            # Si paysage sur rouleau portrait, pivoter
            elif pdf_width > pdf_height and pdf_height <= roll_width:
                rotation = 90
                self.log_info(f"🔄 Rotation auto 90° (optimisation paysage→portrait)")
        
        # Construire les options CUPS
        lp_options = []
        
        # Rotation
        if rotation > 0:
            lp_options.extend(["-o", f"orientation-requested={rotation // 90 + 3}"])
        
        # Qualité
        quality_map = {
            "draft": "draft",
            "normal": "normal",
            "high": "high"
        }
        lp_options.extend(["-o", f"print-quality={quality_map[params['quality']]}"])
        
        # Couleur
        if params["color_mode"] == "grayscale":
            lp_options.extend(["-o", "ColorMode=Mono"])
        
        # Type de média
        lp_options.extend(["-o", f"MediaType={params['media_type']}"])
        
        # Mode rouleau (si supporté par le driver)
        lp_options.extend(["-o", "media=roll"])
        
        # Fit to page
        lp_options.extend(["-o", "fit-to-page"])
        
        # Commande d'impression
        cmd = ["lp", "-d", printer_name] + lp_options + [file_path]
        
        self.log_info(f"🖨️  Impression sur {printer_name}...")
        self.log_debug(f"Commande: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise ActionError(f"Impression échouée: {result.stderr}")
            
            # Extraire le job ID
            job_id = None
            if "request id is" in result.stdout:
                job_id = result.stdout.split("request id is")[1].strip().split()[0]
            
            self.log_info(f"✅ Impression envoyée (Job ID: {job_id or 'N/A'})")
            
            return file_path
            
        except subprocess.TimeoutExpired:
            raise ActionError("Timeout lors de l'impression")
        except Exception as e:
            raise ActionError(f"Erreur impression: {e}")
    
    def _load_nesting_queue(self) -> List[dict]:
        """Charge la queue d'imbrication depuis le disque"""
        queue_file = Path("/genstore/.print_queue.json")
        
        if not queue_file.exists():
            return []
        
        try:
            with open(queue_file, "r") as f:
                return json.load(f)
        except Exception as e:
            self.log_error(f"Erreur lecture queue: {e}")
            return []
    
    def _save_nesting_queue(self, queue: List[dict]):
        """Sauvegarde la queue d'imbrication sur le disque"""
        queue_file = Path("/genstore/.print_queue.json")
        
        try:
            with open(queue_file, "w") as f:
                json.dump(queue, f, indent=2)
        except Exception as e:
            self.log_error(f"Erreur sauvegarde queue: {e}")
    
    def _clear_nesting_queue(self):
        """Vide la queue d'imbrication"""
        queue_file = Path("/genstore/.print_queue.json")
        
        if queue_file.exists():
            try:
                os.remove(queue_file)
            except Exception as e:
                self.log_error(f"Erreur suppression queue: {e}")