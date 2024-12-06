from flask import Flask
import threading
import websocket
import json
import requests
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

# Configuration initiale
load_dotenv()
app = Flask(__name__)

# Désactiver les logs Flask par défaut
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Configuration websocket et variables globales (comme avant)
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')
CRYPTO_PAIRS = os.getenv('CRYPTO_PAIRS', '').split(',')
PUMP_THRESHOLD = 5
DUMP_THRESHOLD = -5
TIME_WINDOW = 5 * 60 * 1000
ALERT_COOLDOWN = {}
MARKET_CALM_THRESHOLD = 2

price_history = {}

def calculate_change(symbol, current_price, current_time):
    """Calcule la variation de prix pour une crypto donnée"""
    if symbol not in price_history:
        price_history[symbol] = {
            'prices': [current_price],
            'lastCheck': current_time
        }
        return 0

    history = price_history[symbol]
    
    # Nettoyer l'historique plus ancien que TIME_WINDOW
    history['prices'] = [p for p in history['prices'] 
                        if (current_time - history['lastCheck']) <= TIME_WINDOW]
    
    # Ajouter le nouveau prix
    history['prices'].append(current_price)
    history['lastCheck'] = current_time
    
    # Calculer la variation
    old_price = history['prices'][0]
    percent_change = ((current_price - old_price) / old_price) * 100
    
    return percent_change

def analyze_trade(data):
    """Analyse un trade pour détecter un pump ou dump"""
    try:
        symbol = data['s']
        price = float(data['p'])
        is_buy_trade = not data['m']
        current_time = int(data['T'])
        
        change = calculate_change(symbol, price, current_time)
        
        # Vérifier si nous sommes déjà en alerte pour ce symbole
        is_already_alerted = symbol in ALERT_COOLDOWN
        
        # Détecter pump ou dump
        if (change >= PUMP_THRESHOLD or change <= DUMP_THRESHOLD) and not is_already_alerted:
            # Première détection d'une variation importante
            ALERT_COOLDOWN[symbol] = {
                'type': 'PUMP' if change > 0 else 'DUMP',
                'initial_price': price
            }
            
            alert = {
                'symbol': symbol,
                'price': price,
                'change': round(change, 2),
                'type': 'PUMP' if change > 0 else 'DUMP',
                'action': 'VENDRE' if change > 0 and is_buy_trade else 'ACHETER' if change < 0 and not is_buy_trade else 'ATTENDRE',
                'tradeType': 'ACHAT' if is_buy_trade else 'VENTE',
                'timestamp': datetime.fromtimestamp(current_time/1000).isoformat(),
            }
            return alert
            
        elif is_already_alerted:
            # Calculer la variation depuis le dernier prix d'alerte
            initial_price = ALERT_COOLDOWN[symbol]['initial_price']
            current_change = ((price - initial_price) / initial_price) * 100
            
            # Si le marché s'est calmé (variation revenue sous le seuil de calme)
            if abs(current_change) <= MARKET_CALM_THRESHOLD:
                alert_type = ALERT_COOLDOWN[symbol]['type']
                del ALERT_COOLDOWN[symbol]  # Réinitialiser l'état d'alerte
                
                alert = {
                    'symbol': symbol,
                    'price': price,
                    'change': round(current_change, 2),
                    'type': alert_type,
                    'action': 'MARCHÉ CALMÉ',
                    'tradeType': 'STABILISATION',
                    'timestamp': datetime.fromtimestamp(current_time/1000).isoformat(),
                }
                return alert
                
    except Exception as e:
        print(f"Erreur lors de l'analyse du trade: {e}")
    
    return None

def get_trading_pairs():
    pairs = CRYPTO_PAIRS.strip().split(',')
    return [f"{pair.lower()}@trade" for pair in pairs]

def on_message(ws, message):
    try:
        data = json.loads(message)
        
        # Analyser le trade
        alert = analyze_trade(data)
        
        # Si une alerte est générée et qu'une URL webhook est configurée, l'envoyer
        if alert and N8N_WEBHOOK_URL:
            print("\n" + "="*50)
            print(f"⚠️ {alert['type']} détecté sur {alert['symbol']} !")
            print(f"Variation: {alert['change']}%")
            print(f"Prix actuel: {alert['price']} USDT")
            print(f"Type de trade: {alert['tradeType']}")
            print(f"Action suggérée: {alert['action']}")
            print("="*50)
            
            headers = {'Content-Type': 'application/json'}
            print(f"\nEnvoi de l'alerte à {N8N_WEBHOOK_URL}")
            response = requests.post(N8N_WEBHOOK_URL, json=alert, headers=headers)
            print(f"Statut de la réponse: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Erreur lors de l'envoi de l'alerte: {response.status_code}")
                print(f"Réponse: {response.text}")
            else:
                print("Alerte envoyée avec succès !")
            print("="*50 + "\n")
            
    except Exception as e:
        print(f"Erreur lors du traitement du message: {e}")

def on_error(ws, error):
    # Ne logger que les erreurs importantes
    if isinstance(error, websocket.WebSocketConnectionClosedException):
        print("⚠️ Connexion WebSocket perdue - Tentative de reconnexion...")
    else:
        print(f"❌ Erreur critique WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔄 Reconnexion au WebSocket...")
    connect_websocket()

def on_open(ws):
    print("✅ Connexion établie avec Binance")
    trading_pairs = get_trading_pairs()
    print(f"👀 Surveillance des paires: {trading_pairs}")
    
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": trading_pairs,
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def connect_websocket():
    # Désactiver les logs websocket
    websocket.enableTrace(False)  # Explicitement désactiver les traces
    
    # Rediriger les logs de websocket-client vers null
    import logging
    logging.getLogger('websocket').setLevel(logging.CRITICAL)
    
    ws = websocket.WebSocketApp("wss://stream.binance.com:9443/ws",
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(ping_interval=30, ping_timeout=10)

def send_startup_notification():
    """Envoie une notification de démarrage à n8n"""
    if N8N_WEBHOOK_URL:
        startup_message = {
            'type': 'STARTUP',
            'message': 'Service de surveillance Binance démarré',
            'timestamp': datetime.now().isoformat(),
            'pairs_surveillees': CRYPTO_PAIRS
        }
        
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(N8N_WEBHOOK_URL, json=startup_message, headers=headers)
            
            if response.status_code == 200:
                print("✅ Notification de démarrage envoyée avec succès")
            else:
                print(f"❌ Erreur lors de l'envoi de la notification de démarrage: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi de la notification de démarrage: {e}")

def start_websocket():
    """Démarre le websocket Binance dans un thread séparé"""
    websocket.enableTrace(False)
    logging.getLogger('websocket').setLevel(logging.CRITICAL)
    
    ws = websocket.WebSocketApp("wss://stream.binance.com:9443/ws",
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(ping_interval=30, ping_timeout=10)

@app.route('/')
def health_check():
    """Endpoint simple pour vérifier que le service fonctionne"""
    return 'OK', 200

def run_flask():
    """Démarre Flask sans les logs de développement"""
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    print("🚀 Démarrage du service de surveillance Binance")
    
    if not N8N_WEBHOOK_URL:
        print("⚠️ N8N_WEBHOOK_URL non configurée - les alertes ne seront pas envoyées")
    else:
        send_startup_notification()
    
    # Démarrer le websocket dans un thread séparé
    websocket_thread = threading.Thread(target=start_websocket)
    websocket_thread.daemon = True  # Le thread s'arrêtera quand le programme principal s'arrête
    websocket_thread.start()
    
    # Démarrer Flask dans le thread principal
    run_flask() 