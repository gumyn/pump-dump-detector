from flask import Flask, render_template, Response
import threading
import websocket
import json
import requests
from datetime import datetime
import os
from dotenv import load_dotenv
import time

# Configuration initiale
load_dotenv()
app = Flask(__name__)

# Variables globales
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')  # Commenté
CRYPTO_PAIRS = os.getenv('CRYPTO_PAIRS', 'BTCUSDT').strip().split(',')
PUMP_THRESHOLD = 5
DUMP_THRESHOLD = -5
TIME_WINDOW = 5 * 60 * 1000  # 5 minutes en millisecondes
price_history = {}

def calculate_change(symbol, current_price):
    """Calcule la variation de prix pour une crypto"""
    if symbol not in price_history:
        price_history[symbol] = {
            'prices': [current_price],
            'time': datetime.now()
        }
        return 0

    history = price_history[symbol]
    history['prices'].append(current_price)
    
    # Garder seulement les prix des 5 dernières minutes
    time_diff = (datetime.now() - history['time']).total_seconds()
    if time_diff > 300:  # 5 minutes
        history['prices'] = [current_price]
        history['time'] = datetime.now()
        return 0
        
    # Calculer la variation
    old_price = history['prices'][0]
    return ((current_price - old_price) / old_price) * 100

def send_telegram_alert(message):
    """Envoie une alerte via Telegram"""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN non configuré")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("✅ Message Telegram envoyé")
            return True
        else:
            print(f"❌ Erreur Telegram: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi Telegram: {e}")
        return False

def on_message(ws, message):
    """Gère les messages reçus du WebSocket"""
    try:
        data = json.loads(message)
        
        # Vérifier les données requises
        if not all(k in data for k in ['s', 'p', 'm', 'T']):
            return
            
        symbol = data['s']
        price = float(data['p'])
        is_buy = not data['m']
        
        # Calculer la variation
        change = calculate_change(symbol, price)
        
        # Détecter pump/dump
        if change >= PUMP_THRESHOLD or change <= DUMP_THRESHOLD:
            # Créer le message d'alerte
            alert_message = (
                f"⚠️ <b>{'PUMP' if change > 0 else 'DUMP'} détecté!</b>\n\n"
                f"💱 Symbole: {symbol}\n"
                f"📈 Variation: {change:.2f}%\n"
                f"💰 Prix: {price} USDT\n"
                f"📊 Type: {'ACHAT' if is_buy else 'VENTE'}\n"
                f"🎯 Action suggérée: {'VENDRE' if change > 0 else 'ACHETER'}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            
            print(f"\n{'='*50}")
            print(alert_message)
            print(f"{'='*50}\n")
            
            # Envoyer via Telegram au lieu de n8n
            send_telegram_alert(alert_message)
                
    except Exception as e:
        print(f"Erreur: {e}")

def start_websocket():
    """Démarre la connexion WebSocket"""
    def on_error(ws, error):
        print(f"Erreur WebSocket: {error}")

    def on_close(ws, *args):
        print("WebSocket fermé")
        
    def on_open(ws):
        print("WebSocket connecté")
        # S'abonner aux paires
        pairs = [f"{pair.lower()}@trade" for pair in CRYPTO_PAIRS]
        ws.send(json.dumps({
            "method": "SUBSCRIBE",
            "params": pairs,
            "id": 1
        }))

    while True:
        try:
            ws = websocket.WebSocketApp(
                "wss://stream.binance.com:9443/ws",
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            ws.run_forever()
        except Exception as e:
            print(f"Erreur connexion: {e}")
            import time
            time.sleep(5)

@app.route('/test')
def test_alert():
    """Endpoint de test"""
    test_message = (
        "🧪 <b>TEST ALERTE</b>\n\n"
        "💱 Symbole: BTCUSDT\n"
        "📈 Variation: +5.5%\n"
        "💰 Prix: 50000 USDT\n"
        "📊 Type: TEST\n"
        "⏰ " + datetime.now().strftime('%H:%M:%S')
    )
    
    success = send_telegram_alert(test_message)
    return "Test envoyé" if success else "Erreur", 200 if success else 500

@app.route('/state')
def get_state():
    """Endpoint d'état"""
    return {
        'pairs': CRYPTO_PAIRS,
        'price_history': {
            symbol: {
                'nb_points': len(history['prices']),
                'dernier_prix': history['prices'][-1],
                'variation': f"{calculate_change(symbol, history['prices'][-1]):.2f}%"
            }
            for symbol, history in price_history.items()
        }
    }

@app.route('/dashboard')
def dashboard():
    """Page du dashboard"""
    return render_template('dashboard.html')

@app.route('/stream')
def stream():
    """Stream des données en temps réel"""
    def generate():
        while True:
            # Récupérer l'état actuel
            data = {
                'pairs': CRYPTO_PAIRS,
                'price_history': {
                    symbol: {
                        'nb_points': len(history['prices']),
                        'dernier_prix': history['prices'][-1],
                        'variation': f"{calculate_change(symbol, history['prices'][-1]):.2f}"
                    }
                    for symbol, history in price_history.items()
                    if history['prices']
                }
            }
            
            # Envoyer les données
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)  # Mise à jour toutes les secondes
    
    return Response(generate(), mimetype='text/event-stream')

if __name__ == "__main__":
    print("🚀 Démarrage surveillance Binance")
    
    # Démarrer WebSocket dans un thread séparé
    ws_thread = threading.Thread(target=start_websocket)
    ws_thread.daemon = True
    ws_thread.start()
    
    # Démarrer Flask
    app.run(host='0.0.0.0', port=5000) 