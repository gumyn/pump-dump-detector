import os
import websocket
import json
import requests
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Récupérer l'URL du webhook et la liste des cryptos depuis les variables d'environnement
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')
CRYPTO_PAIRS = os.getenv('CRYPTO_PAIRS', 'BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT')

def get_trading_pairs():
    pairs = CRYPTO_PAIRS.strip().split(',')
    return [f"{pair.lower()}@trade" for pair in pairs]

def on_message(ws, message):
    try:
        # Convertir le message en JSON
        data = json.loads(message)
        
        # Envoyer les données au webhook n8n avec les bons headers
        headers = {
            'Content-Type': 'application/json'
        }
        
        print(f"Envoi vers {N8N_WEBHOOK_URL}")
        print(f"Données: {json.dumps(data, indent=2)}")
        print(f"Headers: {headers}")
        
        response = requests.post(
            N8N_WEBHOOK_URL, 
            json=data,
            headers=headers
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Réponse: {response.text}")
        
        if response.status_code != 200:
            print(f"Erreur HTTP {response.status_code}: {response.text}")
        else:
            print(f"Données envoyées avec succès pour {data.get('s', 'inconnu')}")
            
    except Exception as e:
        print(f"Erreur lors de l'envoi au webhook: {e}")
        print(f"Message reçu: {message}")

def on_error(ws, error):
    print(f"Erreur WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket Connection Closed")
    # Tentative de reconnexion
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

if __name__ == "__main__":
    print("Démarrage du service de surveillance Binance")
    print(f"Paires configurées: {CRYPTO_PAIRS}")
    connect_websocket() 