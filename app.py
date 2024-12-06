import os
import websocket
import json
import requests
from dotenv import load_dotenv
from datetime import datetime

# Charger les variables d'environnement
load_dotenv()

# Configuration
PUMP_THRESHOLD = 5  # 5% de hausse
DUMP_THRESHOLD = -5  # 5% de baisse
TIME_WINDOW = 5 * 60 * 1000  # 5 minutes en millisecondes

# Stockage de l'historique des prix
price_history = {}

# Récupérer l'URL du webhook et la liste des cryptos
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')
CRYPTO_PAIRS = os.getenv('CRYPTO_PAIRS', 'BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT')

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
        
        # Détecter pump ou dump
        if change >= PUMP_THRESHOLD or change <= DUMP_THRESHOLD:
            alert = {
                'symbol': symbol,
                'price': price,
                'change': round(change, 2),
                'type': 'PUMP' if change > 0 else 'DUMP',
                'action': 'VENDRE' if change > 0 and is_buy_trade else 'ACHETER' if change < 0 and not is_buy_trade else 'ATTENDRE',
                'tradeType': 'ACHAT' if is_buy_trade else 'VENTE',
                'timestamp': datetime.fromtimestamp(current_time/1000).isoformat()
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
    print(f"Erreur WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket Connection Closed")
    connect_websocket()

def on_open(ws):
    print("Connection établie avec Binance")
    trading_pairs = get_trading_pairs()
    print(f"Surveillance des paires: {trading_pairs}")
    
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": trading_pairs,
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def connect_websocket():
    websocket.enableTrace(True)
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

if __name__ == "__main__":
    print("Démarrage du service de surveillance Binance")
    if not N8N_WEBHOOK_URL:
        print("⚠️ N8N_WEBHOOK_URL non configurée - les alertes ne seront pas envoyées")
    else:
        send_startup_notification()
    connect_websocket() 