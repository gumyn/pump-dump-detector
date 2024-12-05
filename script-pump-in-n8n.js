const PUMP_THRESHOLD = 5;
const DUMP_THRESHOLD = -5;
const TIME_WINDOW = 5 * 60 * 1000;

let priceHistory = {};

function calculateChange(symbol, currentPrice) {
        if (!priceHistory[symbol]) {
            priceHistory[symbol] = {
                prices: [currentPrice],
                lastCheck: Date.now()
    
        };
        return 0;
    }

    const history = priceHistory[symbol];
    const now = Date.now();
    
    history.prices = history.prices.filter(p => 
            (now - history.lastCheck) <= TIME_WINDOW
    );
    
    history.prices.push(currentPrice);
    history.lastCheck = now;
    
    const oldPrice = history.prices[0];
    const percentChange = ((currentPrice - oldPrice) / oldPrice) * 100;
    
    return percentChange;
}

// Récupérer les données du body
const data = $input.body;
const symbol = data.s;
const price = parseFloat(data.p);
const change = calculateChange(symbol, price);

if (change >= PUMP_THRESHOLD || change <= DUMP_THRESHOLD) {
    return {
        json: {
            symbol,
            price,
            change,
            type: change > 0 ? 'PUMP' : 'DUMP',
            timestamp: new Date().toISOString()
        }
    };
}

return null;