# ⚡ PBot - Smart Money Concepts Trading Bot

<div align="center">

![PBot Logo](https://img.shields.io/badge/PBot-v2.0-blue?style=for-the-badge)
[![Python](https://img.shields.io/badge/Python-3.8+-green?style=for-the-badge&logo=python)](https://www.python.org/)
[![CCXT](https://img.shields.io/badge/CCXT-4.3.5-red?style=for-the-badge)](https://github.com/ccxt/ccxt)
[![Optuna](https://img.shields.io/badge/Optuna-4.5-purple?style=for-the-badge)](https://optuna.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**Ein professioneller Trading-Bot basierend auf Smart Money Concepts (SMC) mit fortgeschrittener technischer Analyse**

[Features](#-features) • [Installation](#-installation) • [Optimierung](#-optimierung) • [Live-Trading](#-live-trading) • [Monitoring](#-monitoring) • [Wartung](#-wartung)

</div>

---

## 📊 Übersicht

PBot ist ein hochentwickelter Trading-Bot, der Smart Money Concepts (SMC) mit klassischer technischer Analyse kombiniert. Das System nutzt Predictor-basierte Signale mit RSI, ADX, Volume-Filtern und Multi-Timeframe-Analyse für präzise Ein- und Ausstiegspunkte.

### 🧭 Trading-Logik (Kurzfassung)
- **Tageskerzen-Predictor**: Prognostiziert die nächste Daily-Candle-Richtung (bias long/short) und legt damit das Grund-Sentiment fest.
- **SMC-Core**: Identifiziert Liquiditätszonen, Breaker-Blocks und Marktstrukturbrüche; kombiniert mit RSI/ADX für Trendkraft.
- **Predictor-Score**: RSI + Wick-Analyse + Volumen-Ratio + Supertrend werden gewichtet aggregiert (siehe `predictor_settings`).
- **MTF-Bestätigung**: Höherer Timeframe dient als Bias-Filter, um Trades nur in Trendrichtung zuzulassen.
- **Risk Layer**: Fixer SL/TP, optionales Trail; Positionsgröße abhängig von Volatilität und Konto-Risk.

Architektur-Skizze:
```
OHLCV → Feature-Engine (RSI/ADX/Vol/Wick) → Predictor-Score → Bias-Filter (MTF) → Risk Engine → Order Router (CCXT)
```

### 🎯 Hauptmerkmale

- **🧠 Smart Money Concepts**: Professionelle SMC-basierte Trading-Strategie
- **📊 Multi-Indicator**: RSI, ADX, Volume, Supertrend und mehr
- **🔧 Auto-Optimization**: Vollautomatische Parameteroptimierung
- **💰 Multi-Asset**: Handel mehrerer Kryptowährungen parallel
- **⚡ High Performance**: Optimiert für schnelle Ausführung
- **📈 Advanced Analytics**: Umfassende Analyse-Tools
- **🛡️ Risk Management**: Dynamisches Risikomanagement
- **🔔 Telegram Integration**: Real-time Notifications

---

## 🚀 Features

### Trading Features
- ✅ Smart Money Concepts Implementierung
- ✅ Predictor-basierte Signalgenerierung
- ✅ RSI mit anpassbarer Gewichtung
- ✅ ADX-Filter für Trend-Stärke
- ✅ Multi-Timeframe-Analyse (MTF)
- ✅ Volume-Filter mit anpassbaren Schwellenwerten
- ✅ Supertrend-Indikator Integration
- ✅ Dynamisches Position Sizing
- ✅ Intelligentes Stop-Loss/Take-Profit Management

### Technical Features
- ✅ Optuna Hyperparameter-Optimierung
- ✅ Wick-basierte Signalvalidierung
- ✅ Volume-Ratio-Analyse
- ✅ Walk-Forward-Testing
- ✅ Backtesting mit realistischer Simulation
- ✅ Feature-Importance-Analyse

---

## 📋 Systemanforderungen

### Hardware
- **CPU**: Multi-Core Prozessor (i5 oder besser)
- **RAM**: Minimum 4GB, empfohlen 8GB+
- **Speicher**: 2GB freier Speicherplatz

### Software
- **OS**: Linux (Ubuntu 20.04+), macOS, Windows 10/11
- **Python**: Version 3.8 oder höher
- **Git**: Für Repository-Verwaltung

---

## 💻 Installation

### 1. Repository klonen

```bash
git clone <repository-url>
cd pbot
```

### 2. Automatische Installation

```bash
# Linux/macOS
chmod +x install.sh
./install.sh

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Das Installations-Script:
- ✅ Erstellt virtuelle Python-Umgebung
- ✅ Installiert alle Dependencies (siehe requirements.txt)
- ✅ Erstellt Verzeichnisstruktur
- ✅ Initialisiert Konfigurationen

### 3. API-Credentials konfigurieren

Erstelle `secret.json` im Root-Verzeichnis:

```json
{
  "pbot": [
    {
      "name": "Binance Main",
      "exchange": "binance",
      "apiKey": "DEIN_API_KEY",
      "secret": "DEIN_SECRET_KEY",
      "options": {
        "defaultType": "future"
      }
    }
  ],
  "telegram": {
    "bot_token": "DEIN_BOT_TOKEN",
    "chat_id": "DEINE_CHAT_ID"
  }
}
```

⚠️ **Sicherheit**:
- `secret.json` niemals committen!
- Nur API-Keys ohne Withdrawal-Rechte
- IP-Whitelist aktivieren
- 2FA aktivieren

### 4. Trading-Strategien konfigurieren

Bearbeite `settings.json`:

```json
{
  "live_trading_settings": {
    "use_auto_optimizer_results": false,
    "active_strategies": [
      {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "30m",
        "use_macd_filter": false,
        "active": true
      },
      {
        "symbol": "SOL/USDT:USDT",
        "timeframe": "30m",
        "use_macd_filter": false,
        "active": true
      }
    ]
  },
  "predictor_settings": {
    "length": 14,
    "rsi_weight": 1.5,
    "wick_weight": 1.0,
    "use_adx_filter": true,
    "adx_threshold": 20,
    "use_mtf": true,
    "use_volume_filter": true,
    "min_volume_ratio": 0.5,
    "volume_lookback": 20,
    "supertrend_factor": 3.0,
    "supertrend_period": 10
  }
}
```

**Parameter-Erklärung**:

*Live Trading Settings*:
- `symbol`: Handelspaar (Format: BASE/QUOTE:SETTLE)
- `timeframe`: Zeitrahmen (15m, 30m, 1h, 2h, 4h, 6h, 1d)
- `use_macd_filter`: Zusätzlicher MACD-Filter
- `active`: Strategie aktivieren/deaktivieren

*Predictor Settings*:
- `length`: RSI/Indicator Periode (Standard: 14)
- `rsi_weight`: Gewichtung des RSI-Signals (1.0-2.0)
- `wick_weight`: Gewichtung der Docht-Analyse (0.5-1.5)
- `use_adx_filter`: ADX-Trend-Filter aktivieren
- `adx_threshold`: Minimale ADX-Stärke (typisch: 20-25)
- `use_mtf`: Multi-Timeframe-Analyse aktivieren
- `use_volume_filter`: Volume-basierte Filterung
- `min_volume_ratio`: Minimales Volumen-Verhältnis (0.3-1.0)
- `volume_lookback`: Perioden für Volume-Durchschnitt
- `supertrend_factor`: Supertrend ATR-Multiplikator
- `supertrend_period`: Supertrend ATR-Periode

---

## 🎯 Optimierung & Training

### Vollständige Pipeline (Empfohlen)

```bash
# Interaktives Optimierungs-Script
./run_pipeline.sh
```

Pipeline-Schritte:

1. **Aufräumen** (Optional): Löscht alte Konfigurationen
2. **Symbol-Eingabe**: Wähle Handelspaare (z.B. BTC ETH SOL)
3. **Timeframe-Auswahl**: Wähle Zeitrahmen für jedes Paar
4. **Daten-Download**: Lädt historische Marktdaten
5. **Optimierung**: Findet beste Parameter mit Optuna
6. **Backtest**: Validiert optimierte Strategien
7. **Config-Generierung**: Erstellt Konfigs für Live-Trading

### Manuelle Optimierung

```bash
source .venv/bin/activate

# Optimierung starten
python src/pbot/analysis/optimizer.py
```

**Erweiterte Optionen**:
```bash
# Spezifische Symbole optimieren
python src/pbot/analysis/optimizer.py --symbols BTC ETH ADA

# Custom Timeframes
python src/pbot/analysis/optimizer.py --timeframes 30m 1h 4h

# Mehr Optimierungs-Trials (bessere Ergebnisse)
python src/pbot/analysis/optimizer.py --trials 500

# Mit Walk-Forward Analyse
python src/pbot/analysis/optimizer.py --walk-forward --windows 5

# Spezifische Daten-Range
python src/pbot/analysis/optimizer.py --start-date 2024-01-01 --end-date 2024-12-31
```

**Optimierte Parameter**:
- RSI-Perioden und Gewichtungen
- ADX-Schwellenwerte
- Volume-Filter-Parameter
- Supertrend-Einstellungen
- Stop-Loss/Take-Profit Levels
- Position Sizing

### Optimierungsergebnisse analysieren

```bash
# Ergebnisse anzeigen
cat artifacts/results/optimization_results.json | python -m json.tool

# Beste Config kopieren
cp artifacts/results/best_config_BTC_30m.json src/pbot/strategy/configs/
```

---

## 🔴 Live Trading

### Start des Live-Trading

```bash
# Master Runner starten (alle aktiven Strategien)
python master_runner.py
```

### Manuell starten / Cronjob testen
Sofortiger Start ohne Cron-Wartezeit:

```bash
cd /home/ubuntu/pbot && /home/ubuntu/pbot/.venv/bin/python3 /home/ubuntu/pbot/master_runner.py
```

Der Master Runner:
- ✅ Lädt Konfigurationen aus `settings.json`
- ✅ Startet separate Prozesse pro Strategie
- ✅ Überwacht Kontostand und Kapital
- ✅ Verwaltet Positionen und Orders
- ✅ Telegram-Benachrichtigungen
- ✅ Detailliertes Logging

### Einzelne Strategie starten

```bash
# Spezifisches Paar handeln
python src/pbot/strategy/run.py --symbol BTC/USDT:USDT --timeframe 30m
```

### Automatisierter Start

```bash
# Optimierung + Live-Trading
./run_pipeline_automated.sh
```

### Als Systemd Service (Linux)

Für 24/7 Betrieb:

```bash
# Service-Datei erstellen
sudo nano /etc/systemd/system/pbot.service
```

```ini
[Unit]
Description=PBot SMC Trading System
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/pbot
ExecStart=/path/to/pbot/.venv/bin/python master_runner.py
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

```bash
# Service aktivieren
sudo systemctl enable pbot
sudo systemctl start pbot

# Status prüfen
sudo systemctl status pbot

# Logs verfolgen
sudo journalctl -u pbot -f
```

---

## 📊 Monitoring & Status

### Status-Dashboard

```bash
# Vollständiger Status
./show_status.sh
```

Zeigt:
- 📊 Aktuelle Konfiguration
- 🔐 API-Status (ohne Credentials)
- 📈 Offene Positionen
- 💰 Kontostand und verfügbares Kapital
- 📝 Recent Trading-Logs

### Risk-Status überwachen

```bash
# Risk-Management-Status
python show_risk_status.py
```

Zeigt:
- Aktuelle Positionsgrößen
- Risk per Trade
- Total Exposure
- Margin-Nutzung

### Leverage anzeigen

```bash
# Aktuelle Hebel-Einstellungen
python show_leverage.py
```

### Chart-Generierung

```bash
# Equity-Curve und Performance-Charts
./show_chart.sh

# Chart per Telegram senden
python generate_and_send_chart.py
```

### Log-Files überwachen

```bash
# Live-Trading Logs (alle Strategien)
tail -f logs/live_trading_*.log

# Spezifisches Symbol
tail -f logs/live_trading_BTC_USDT_30m.log

# Nur Trade-Signale
grep -i "signal\|buy\|sell\|close" logs/live_trading_*.log

# Fehler-Logs
tail -f logs/error_*.log

# Performance-Zusammenfassung
grep "Profit:" logs/*.log | awk '{sum+=$NF} END {print "Total Profit:", sum}'
```

### Performance-Berichte

```bash
# Detaillierte Ergebnisse
./show_results.sh

# Trades analysieren
python -c "
import pandas as pd
trades = pd.read_csv('logs/trades_history.csv')
print('Total Trades:', len(trades))
print('Win Rate:', (trades['pnl'] > 0).mean() * 100, '%')
print('Average Profit:', trades['pnl'].mean())
print('Best Trade:', trades['pnl'].max())
print('Worst Trade:', trades['pnl'].min())
"
```

---

## 🛠️ Wartung & Pflege

### Regelmäßige Wartung

#### 1. Updates installieren

```bash
# Automatisches Update
./update.sh
```

Das Update-Script:
- ✅ Pulled Git-Changes
- ✅ Updated Python-Dependencies
- ✅ Migriert Konfigurationen
- ✅ Führt Tests aus
- ✅ Erstellt Backup

#### 2. Log-Rotation

```bash
# Logs komprimieren (älter als 30 Tage)
find logs/ -name "*.log" -type f -mtime +30 -exec gzip {} \;

# Archivierte Logs löschen (älter als 90 Tage)
find logs/ -name "*.log.gz" -type f -mtime +90 -delete

# Log-Größe prüfen
du -sh logs/
```

#### 3. Performance-Check

```bash
# Wöchentliche Performance-Prüfung
python -c "
import pandas as pd
from datetime import datetime, timedelta

trades = pd.read_csv('logs/trades_history.csv')
trades['date'] = pd.to_datetime(trades['timestamp'])
week_ago = datetime.now() - timedelta(days=7)
recent = trades[trades['date'] > week_ago]

print('Last 7 Days Performance:')
print('Trades:', len(recent))
print('Win Rate:', (recent['pnl'] > 0).mean() * 100, '%')
print('Total PnL:', recent['pnl'].sum())
"
```

### Vollständiges Aufräumen

#### Konfigurationen zurücksetzen

```bash
# Nur generierte Configs löschen
rm -f src/pbot/strategy/configs/config_*.json

# Prüfen
ls -la src/pbot/strategy/configs/

# Optimierungsergebnisse löschen
rm -rf artifacts/results/*

# Verification
ls -la artifacts/results/
```

#### Cache und Daten löschen

```bash
# Heruntergeladene Marktdaten
rm -rf data/raw/*
rm -rf data/processed/*

# Backtest-Cache
rm -rf data/backtest_cache/*

# Größe prüfen
du -sh data/*

# Alles prüfen
find data/ -type f | wc -l  # Sollte 0 oder sehr niedrig sein
```

#### Kompletter Neustart

```bash
# Vollständiges Backup erstellen
tar -czf pbot_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
    secret.json settings.json artifacts/ logs/ src/pbot/strategy/configs/

# Alles zurücksetzen
rm -rf artifacts/* data/* logs/* src/pbot/strategy/configs/config_*.json
mkdir -p artifacts/{results,backtest} data/{raw,processed} logs/

# Re-Installation
./install.sh

# Konfiguration wiederherstellen
cp settings.json.backup settings.json

# Verification
ls -R artifacts/ data/ logs/ | wc -l
```

### Tests ausführen

```bash
# Alle Tests
./run_tests.sh

# Spezifische Test-Dateien
pytest tests/test_predictor.py -v
pytest tests/test_smc_strategy.py -v
pytest tests/test_exchange.py -v

# Mit Coverage-Report
pytest --cov=src --cov-report=html tests/

# Nur schnelle Tests
pytest -m "not slow" tests/
```

### API-Account prüfen

```bash
# Account-Type und Permissions prüfen
python check_account_type.py

# API-Test durchführen
python test_api.py
```

---

## 🔧 Nützliche Befehle

### Konfiguration

```bash
# Settings validieren
python -c "import json; data=json.load(open('settings.json')); print(data)" | python -m json.tool

# Predictor-Settings anzeigen
python -c "import json; print(json.load(open('settings.json'))['predictor_settings'])"

# Backup mit Timestamp
cp settings.json settings.json.backup.$(date +%Y%m%d_%H%M%S)

# Diff prüfen
diff settings.json settings.json.backup
```

### Prozess-Management

```bash
# Alle PBot-Prozesse
ps aux | grep python | grep pbot

# Master Runner PID
pgrep -f "python.*master_runner"

# Einzelne Strategien
ps aux | grep "run.py"

# Sauber beenden (SIGTERM)
pkill -f master_runner.py

# Sofort beenden (SIGKILL)
pkill -9 -f master_runner.py

# Alle PBot-Prozesse beenden
pkill -f "pbot"
```

### Exchange-Diagnose

```bash
# Verbindung testen
python -c "from src.pbot.utils.exchange import Exchange; \
    e = Exchange('binance'); print('Connected:', e.exchange.has)"

# Balance abrufen
python -c "from src.pbot.utils.exchange import Exchange; \
    e = Exchange('binance'); print(e.fetch_balance())"

# Offene Positionen
python -c "from src.pbot.utils.exchange import Exchange; \
    e = Exchange('binance'); \
    positions = e.fetch_positions(); \
    for p in positions: \
        if float(p['contracts']) != 0: print(p)"

# Marktdaten testen
python -c "from src.pbot.utils.exchange import Exchange; \
    e = Exchange('binance'); \
    ohlcv = e.fetch_ohlcv('BTC/USDT:USDT', '30m', limit=10); \
    print('Fetched', len(ohlcv), 'candles')"
```

### Performance-Analyse

```bash
# Equity-Curves vergleichen
python -c "
import pandas as pd
import matplotlib.pyplot as plt

manual = pd.read_csv('manual_portfolio_equity.csv')
optimal = pd.read_csv('optimal_portfolio_equity.csv')

plt.figure(figsize=(12, 6))
plt.plot(manual['timestamp'], manual['equity'], label='Manual', alpha=0.7)
plt.plot(optimal['timestamp'], optimal['equity'], label='Optimal', alpha=0.7)
plt.legend()
plt.title('Portfolio Equity Comparison')
plt.savefig('equity_comparison.png')
print('Chart saved to equity_comparison.png')
"

# Win-Rate nach Symbol
python -c "
import pandas as pd
trades = pd.read_csv('logs/trades_history.csv')
for symbol in trades['symbol'].unique():
    symbol_trades = trades[trades['symbol'] == symbol]
    win_rate = (symbol_trades['pnl'] > 0).mean() * 100
    print(f'{symbol}: Win Rate {win_rate:.2f}%, Trades: {len(symbol_trades)}')
"

# Backtest-Ergebnisse zusammenfassen
find artifacts/backtest/ -name "*.json" | while read file; do
    echo "=== $(basename $file) ==="
    cat "$file" | python -m json.tool | grep -E "(total_return|sharpe_ratio|max_drawdown|win_rate)"
done
```

### Debugging

```bash
# Debug-Modus aktivieren
export PBOT_DEBUG=1
export PYTHONUNBUFFERED=1
python master_runner.py

# Strategie-Signale live verfolgen
tail -f logs/live_trading_*.log | grep --color=auto -i "signal\|predictor\|score"

# Mit Python Debugger
python -m pdb src/pbot/strategy/run.py

# Interactive Python Shell mit Bot-Kontext
python -i -c "
from src.pbot.strategy.smc_strategy import SMCStrategy
from src.pbot.utils.exchange import Exchange
exchange = Exchange('binance')
strategy = SMCStrategy(exchange, 'BTC/USDT:USDT', '30m')
print('Bot loaded. Use strategy.* and exchange.* objects')
"
```

---

## 📂 Projekt-Struktur

```
pbot/
├── src/
│   └── pbot/
│       ├── analysis/              # Optimierung & Analyse
│       │   ├── optimizer.py
│       │   └── performance_analyzer.py
│       ├── strategy/              # Trading-Strategien
│       │   ├── run.py             # Main Runner
│       │   ├── smc_strategy.py    # SMC Implementation
│       │   ├── predictor.py       # Signal Predictor
│       │   └── configs/           # Generierte Configs
│       ├── backtest/              # Backtesting
│       │   └── backtester.py
│       └── utils/                 # Utilities
│           ├── exchange.py        # Exchange-Wrapper
│           ├── indicators.py      # Technical Indicators
│           └── risk_manager.py    # Risk Management
├── tests/                         # Unit-Tests
│   ├── test_predictor.py
│   ├── test_smc_strategy.py
│   └── test_exchange.py
├── data/                          # Marktdaten
│   ├── raw/                       # Rohdaten
│   └── processed/                 # Verarbeitete Daten
├── logs/                          # Log-Files
│   ├── live_trading_*.log
│   ├── error_*.log
│   └── trades_history.csv
├── artifacts/                     # Ergebnisse
│   ├── results/                   # Optimierungsergebnisse
│   └── backtest/                  # Backtest-Berichte
├── master_runner.py              # Main Entry-Point
├── settings.json                 # Haupt-Konfiguration
├── secret.json                   # API-Credentials
├── requirements.txt              # Python-Dependencies
└── pytest.ini                    # Test-Konfiguration
```

---

## ⚠️ Wichtige Hinweise

### Risiko-Disclaimer

⚠️ **Kryptowährungs-Trading ist hochriskant!**

- Nur Geld riskieren, dessen Verlust Sie verkraften können
- Keine Gewinn-Garantien
- Vergangene Performance ≠ Zukünftige Ergebnisse
- Ausgiebiges Testing auf Demo-Account empfohlen
- Mit kleinen Beträgen beginnen

### Security Best Practices

- 🔐 **Niemals** API-Keys mit Withdrawal-Rechten verwenden
- 🔐 IP-Whitelist auf Exchange aktivieren
- 🔐 2-Faktor-Authentifizierung aktivieren
- 🔐 `secret.json` in `.gitignore` eintragen
- 🔐 Regelmäßige Security-Updates durchführen
- 🔐 Logs regelmäßig prüfen auf ungewöhnliche Aktivitäten

### Performance-Tipps

- 💡 Mit 1-2 Strategien starten, dann skalieren
- 💡 Längere Timeframes (30m+) = Stabilere Signale
- 💡 ADX-Filter in schwachen Trends aktivieren
- 💡 Volume-Filter bei illiquiden Märkten aktivieren
- 💡 MTF-Analyse für bessere Einstiege
- 💡 Re-Optimierung alle 3-4 Wochen
- 💡 Monitoring ist essentiell!

---

## 🤝 Support & Community

### Probleme melden

Bei Issues oder Fragen:

1. **Logs prüfen**: `logs/` Verzeichnis
2. **Tests ausführen**: `./run_tests.sh`
3. **GitHub Issue** erstellen mit:
   - Detaillierte Problembeschreibung
   - Relevante Log-Auszüge
   - System-Informationen (OS, Python-Version)
   - Reproduktions-Schritte
   - Screenshots (falls relevant)

### Updates erhalten

```bash
# Updates prüfen
git fetch origin
git log HEAD..origin/main --oneline

# Updates installieren
git pull origin main
./update.sh
```

---

## 📜 Lizenz

Dieses Projekt ist lizenziert unter der MIT License - siehe [LICENSE](LICENSE) Datei für Details.

---

## 🙏 Credits

Entwickelt mit:
- [CCXT](https://github.com/ccxt/ccxt) - Cryptocurrency Exchange Trading Library
- [Optuna](https://optuna.org/) - Hyperparameter Optimization Framework
- [Pandas](https://pandas.pydata.org/) - Data Analysis Library
- [NumPy](https://numpy.org/) - Numerical Computing
- [SciPy](https://scipy.org/) - Scientific Computing
- [TA-Lib](https://github.com/mrjbq7/ta-lib) - Technical Analysis Library
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API

---

<div align="center">

**Built with ❤️ for Smart Money Trading**

⭐ Star this repo if it helps your trading!

[🔝 Nach oben](#-pbot---smart-money-concepts-trading-bot)

</div>
