#!/bin/bash
# run_walk_forward.sh
# Führt Walk-Forward Testing für alle konfigurierten Strategien aus

echo "=================================="
echo "  PBOT WALK-FORWARD TESTING"
echo "=================================="

# Aktiviere virtuelle Umgebung
source .venv/bin/activate

# Parameter
START_DATE="2023-01-01"
END_DATE="2024-12-31"
TRAIN_MONTHS=6
TEST_MONTHS=2
STEP_MONTHS=2
TRIALS=50

# Zu testende Symbole und Timeframes
SYMBOLS="BTC ETH SOL"
TIMEFRAMES="30m 1h 4h"

echo ""
echo "📊 Konfiguration:"
echo "   Training Window: ${TRAIN_MONTHS} Monate"
echo "   Test Window: ${TEST_MONTHS} Monate"
echo "   Step Size: ${STEP_MONTHS} Monate"
echo "   Trials per Window: ${TRIALS}"
echo "   Zeitraum: ${START_DATE} bis ${END_DATE}"
echo ""

# Durchlaufe alle Symbol/Timeframe Kombinationen
for SYMBOL in $SYMBOLS; do
    for TF in $TIMEFRAMES; do
        echo ""
        echo "🚀 Starte Walk-Forward für ${SYMBOL}/${TF}..."
        echo ""
        
        python3 src/pbot/analysis/walk_forward.py \
            --symbol ${SYMBOL} \
            --timeframe ${TF} \
            --start_date ${START_DATE} \
            --end_date ${END_DATE} \
            --train_months ${TRAIN_MONTHS} \
            --test_months ${TEST_MONTHS} \
            --step_months ${STEP_MONTHS} \
            --trials ${TRIALS}
        
        echo ""
        echo "✅ ${SYMBOL}/${TF} abgeschlossen"
        echo "-----------------------------------"
    done
done

echo ""
echo "=================================="
echo "  Walk-Forward Testing abgeschlossen!"
echo "=================================="
echo ""
echo "Ergebnisse gespeichert in: artifacts/results/walk_forward/"
echo ""
