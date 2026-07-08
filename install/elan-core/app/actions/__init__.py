# ============================================================================
# FILE: /opt/elan/app/actions/__init__.py
# VERSION : 9
# ============================================================================

from .add_trim_guide import AddTrimGuideAction
from .adjust_mediabox import AdjustMediaboxAction
from .base import Action, ActionError
from .extract_cutting import ExtractCuttingAction
from .impose import ImposeAction
from .perfect_binding_split import PerfectBindingSplitAction
from .print import PrintAction
from .raster import RasterAction
from .saddle_stitch_split import SaddleStitchSplitAction

# Registre des actions disponibles
ACTION_REGISTRY = {
    "add_trim_guide": AddTrimGuideAction,
    "adjust_mediabox": AdjustMediaboxAction,
    "extract_cutting": ExtractCuttingAction,
    "impose": ImposeAction,
    "perfect_binding_split": PerfectBindingSplitAction,
    "print": PrintAction,
    "raster": RasterAction,
    "saddle_stitch_split": SaddleStitchSplitAction,
}

def get_action(action_type: str, config: dict) -> Action:
    """
    Crée une instance d'action à partir de son type
    
    Args:
        action_type: Type de l'action
        config: Configuration de l'action
        
    Returns:
        Instance de l'action
        
    Raises:
        ValueError: Si le type d'action est inconnu
    """
    if action_type not in ACTION_REGISTRY:
        available = ", ".join(ACTION_REGISTRY.keys())
        raise ValueError(f"Action inconnue: '{action_type}'. Disponibles: {available}")
    
    action_class = ACTION_REGISTRY[action_type]
    return action_class(config)

def list_actions():
    """Liste toutes les actions disponibles"""
    return list(ACTION_REGISTRY.keys())
