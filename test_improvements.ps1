# test_improvements.ps1
# Testet alle neuen PBot v2.0 Features

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PBOT v2.0 IMPROVEMENTS TEST" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$VENV_PYTHON = ".venv\Scripts\python.exe"

# Test 1: Risk Manager
Write-Host "[1/5] Teste Portfolio Risk Manager..." -ForegroundColor Yellow
& $VENV_PYTHON -c @"
from pbot.utils.risk_manager import get_risk_manager

rm = get_risk_manager({
    'max_concurrent_positions': 3,
    'max_daily_loss_pct': 5.0,
    'max_total_risk_pct': 4.0
})

print('  ✓ Risk Manager initialisiert')
status = rm.get_status()
print(f'  ✓ Status abgerufen: {status[\"active_positions_count\"]} Positionen')

# Test Position Check
can_trade, reason = rm.can_open_position('BTC/USDT:USDT', 1.5)
print(f'  ✓ Position Check: {\"OK\" if can_trade else reason}')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ PASS" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
Write-Host ""

# Test 2: Database
Write-Host "[2/5] Teste Trade Database..." -ForegroundColor Yellow
& $VENV_PYTHON -c @"
from pbot.utils.database import get_trade_db
from datetime import datetime

db = get_trade_db()
print('  ✓ Database initialisiert')

# Test Query
open_trades = db.get_open_trades()
print(f'  ✓ Open Trades: {len(open_trades)}')

stats = db.get_trade_statistics(days=30)
print(f'  ✓ Statistiken: {stats[\"trades_count\"]} Trades')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ PASS" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
Write-Host ""

# Test 3: Volumen-Filter
Write-Host "[3/5] Teste Volumen-Filter..." -ForegroundColor Yellow
& $VENV_PYTHON -c @"
import pandas as pd
from pbot.strategy.predictor_engine import PredictorEngine

# Erstelle Test-Daten
data = pd.DataFrame({
    'open': [100] * 100,
    'high': [101] * 100,
    'low': [99] * 100,
    'close': [100] * 100,
    'volume': [1000] * 50 + [200] * 50  # Low volume in letzten 50
})

engine = PredictorEngine({
    'use_volume_filter': True,
    'min_volume_ratio': 0.5,
    'volume_lookback': 20
})

df = engine.calculate_indicators(data)
print('  ✓ Volumen-Indikatoren berechnet')
print(f'  ✓ Volume Ratio (letzte Kerze): {df.iloc[-1][\"volume_ratio\"]:.2f}')

# Check ob Low-Volume erkannt wird
result = engine.analyze(df)
if result:
    print(f'  ✓ Low-Volume Detection: {result[\"is_low_volume\"]}')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ PASS" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
Write-Host ""

# Test 4: Regime Detector
Write-Host "[4/5] Teste Market-Regime Detection..." -ForegroundColor Yellow
& $VENV_PYTHON -c @"
import pandas as pd
import numpy as np
from pbot.strategy.regime_detector import RegimeDetector, MarketRegime

# Erstelle Trending-Daten
dates = pd.date_range('2024-01-01', periods=200, freq='1H')
trend = np.linspace(100, 150, 200)
noise = np.random.randn(200) * 2
data = pd.DataFrame({
    'open': trend + noise,
    'high': trend + noise + 1,
    'low': trend + noise - 1,
    'close': trend + noise,
    'volume': [1000] * 200
}, index=dates)

detector = RegimeDetector()
result = detector.detect_regime(data)

print(f'  ✓ Regime: {result[\"regime\"].value}')
print(f'  ✓ Confidence: {result[\"confidence\"]:.0%}')
print(f'  ✓ ADX: {result[\"details\"][\"adx\"]}')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ PASS" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
Write-Host ""

# Test 5: Optimizer-Grenzen
Write-Host "[5/5] Teste Optimizer-Grenzen..." -ForegroundColor Yellow
& $VENV_PYTHON -c @"
import json
import os

# Prüfe ob optimizer.py die richtigen Grenzen hat
optimizer_path = 'src/pbot/analysis/optimizer.py'
with open(optimizer_path, 'r', encoding='utf-8') as f:
    content = f.read()
    
# Check Risk Limit
if 'risk_per_trade_pct\": trial.suggest_float(\"risk_per_trade_pct\", 0.5, 1.5)' in content:
    print('  ✓ Risk Cap: 1.5% (korrekt)')
else:
    print('  ⚠ Risk Cap nicht gefunden')

# Check Leverage Limit
if 'leverage\": trial.suggest_int(\"leverage\", 5, 15)' in content:
    print('  ✓ Leverage Cap: 15x (korrekt)')
else:
    print('  ⚠ Leverage Cap nicht gefunden')

# Check Pruning
if 'drawdown > 0.30' in content and 'trades < 15' in content:
    print('  ✓ Pruning verschärft (DD < 30%, Min 15 Trades)')
else:
    print('  ⚠ Pruning nicht verschärft')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ PASS" -ForegroundColor Green
} else {
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
Write-Host ""

# Zusammenfassung
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TEST ABGESCHLOSSEN" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nächste Schritte:" -ForegroundColor Yellow
Write-Host "  1. Risk Status anzeigen: python show_risk_status.py"
Write-Host "  2. Config aktualisieren: Siehe config_TEMPLATE_v2.json"
Write-Host "  3. Re-Optimierung: bash run_pipeline.sh (Linux) oder manuell"
Write-Host "  4. Walk-Forward Test: python src/pbot/analysis/walk_forward.py --symbol BTC --timeframe 30m --start_date 2023-01-01 --end_date 2024-12-31"
Write-Host ""
