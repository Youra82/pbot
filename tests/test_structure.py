# /root/pbot/tests/test_structure.py
import os
import sys
import pytest

# Füge das Projektverzeichnis zum Python-Pfad hinzu, damit Imports funktionieren
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

def test_project_structure():
    """Stellt sicher, dass alle erwarteten Hauptverzeichnisse existieren."""
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'src')), "Das 'src'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'artifacts')), "Das 'artifacts'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'tests')), "Das 'tests'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'src', 'pbot')), "Das 'src/pbot'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy')), "Das 'src/pbot/strategy'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'src', 'pbot', 'analysis')), "Das 'src/pbot/analysis'-Verzeichnis fehlt."
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'src', 'pbot', 'utils')), "Das 'src/pbot/utils'-Verzeichnis fehlt."


def test_core_script_imports():
    """
    Stellt sicher, dass die wichtigsten Funktionen aus den Kernmodulen importiert werden können.
    Dies ist ein schneller Check, ob die grundlegende Code-Struktur intakt ist.
    UPDATE: Angepasst auf PBot (Predictor Logic).
    """
    try:
        # Importiere Kernkomponenten von PBot
        from pbot.utils.trade_manager import housekeeper_routine, check_and_open_new_position, full_trade_cycle
        from pbot.utils.exchange import Exchange
        
        # --- HIER WAR DER FEHLER: Wir importieren jetzt die neuen Module ---
        from pbot.strategy.predictor_engine import PredictorEngine # Statt SMCEngine
        from pbot.strategy.trade_logic import get_pbot_signal # Statt get_titan_signal
        from pbot.analysis.backtester import run_pbot_backtest # Statt run_smc_backtest
        # -----------------------------------------------------------------
        
        # Importiere 'main' aus dem optimizer und gib ihr einen Alias
        from pbot.analysis.optimizer import main as optimizer_main
        from pbot.analysis.portfolio_optimizer import run_portfolio_optimizer

    except ImportError as e:
        pytest.fail(f"Kritischer Import-Fehler. Die Code-Struktur scheint defekt zu sein. Fehler: {e}")
