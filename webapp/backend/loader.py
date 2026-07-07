"""Auto-discovery de estrategias.

Importa strategies/ recursivamente y deja todas las subclases de
Strategy registradas en StrategyRegistry. Llamar load_all_strategies()
al arranque del backend.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil

import strategies
from strategies.base import StrategyRegistry

logger = logging.getLogger("webapp.loader")


def load_all_strategies() -> int:
    """Walk strategies/ y importa todos los modulos Python.

    Devuelve el numero de strategies registradas.
    Cada modulo es responsable de llamar StrategyRegistry.register().
    """
    package = strategies
    prefix = package.__name__ + "."
    count_before = len(StrategyRegistry.all())

    for finder, modname, ispkg in pkgutil.walk_packages(package.__path__, prefix):
        # Skip _examples — son templates, no strategies para correr
        if "._examples" in modname or "._" in modname:
            continue
        try:
            importlib.import_module(modname)
        except Exception as exc:
            logger.warning("Failed to import %s: %s", modname, exc)

    count_after = len(StrategyRegistry.all())
    logger.info("Loaded %d strategies (was %d before)", count_after, count_before)
    return count_after


def reload_all_strategies() -> int:
    """Re-importa todos los modulos. Util cuando agregas/modificas una strategy."""
    StrategyRegistry.clear()
    # Limpiar el cache de imports
    import sys
    to_remove = [k for k in sys.modules if k.startswith("strategies.")]
    for k in to_remove:
        del sys.modules[k]
    return load_all_strategies()
