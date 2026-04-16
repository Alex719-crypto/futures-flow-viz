from flask import Flask, jsonify, request, Response
import threading
import websocket
import json
import os
from collections import deque

app = Flask(__name__)

SYMBOLS = ["btcusdt", "ethusdt", "solusdt"]
TRADE_LIMIT = 500
WHALE_THRESHOLD_USD = 50000

lock = threading.Lock()
state = {
    s: {
        "trades": deque(maxlen=TRADE_LIMIT),
        "last_price": 0.0,
        "last_whale": None
    } for s in SYMBOLS
}

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Whale Visualizer</title>
    <style>
        body {
            margin: 0;
            background: #05070a;
            color: white;
            font-family: Arial, sans-serif;
            overflow: hidden;
        }

        #header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 70px;
            background: rgba(17, 24, 39, 0.92);
            display: flex;
            align-items: center;
            padding: 0 25px;
            z-index: 20;
            border-bottom: 1px solid #1f2937;
        }

        .btn {
            background: #111827;
            border: 1px solid #374151;
            color: #9ca3af;
            padding: 10px 18px;
            margin-right: 10px;
            cursor: pointer;
            border-radius: 8px;
            font-weight: 600;
        }

        .active {
            border-color: #3b82f6;
            background: #1e3a8a;
            color: white;
            box-shadow: 0 0 15px rgba(59,130,246,0.45);
        }

        #price {
            margin-left: auto;
            font-size: 24px;
            font-weight: bold;
            color: #3b82f6;
        }

        #whale-alert {
            position: fixed;
            top: 90px;
            right: 30px;
            z-index: 30;
            font-size: 28px;
            font-weight: 800;
            color: #fbbf24;
            text-shadow: 0 0 18px rgba(251,191,36,0.8);
            font-style: italic;
        }

        canvas {
            display: block;
            margin-top: 70px;
            background: #05070a;
        }
    </style>
</head>
<body>
    <div id="header">
        <button class="btn active" onclick="setSymbol('btcusdt', this)">BTC</button>
        <button class="btn" onclick="setSymbol('ethusdt', this)">ETH</button>
        <button class="btn" onclick="setSymbol('solusdt', this)">SOL</button>
        <div id="price">--</div>
    </div>

    <div id="whale-alert"></div>
    <canvas id="chart"></canvas>

    <script>
        const canvas = document.getElementById('chart');
        const ctx = canvas.getContext('2d');

        let currentSymbol = 'btcusdt';
        let currentWhaleTs = null;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight - 70;
        }
        window.addEventListener('resize', resize);
        resize();

        function setSymbol(symbol, el) {
            currentSymbol = symbol;
            document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            document.getElementById('whale-alert').innerText = '';
            currentWhaleTs = null;
        }

        async function updateData() {
            try {
                const res = await fetch('/data?symbol=' + currentSymbol);
                const data = await res.json();

                document.getElementById('price').innerText =
                    currentSymbol.toUpperCase() + ' $' + Number(data.last_price).toLocaleString();

                if (data.last_whale && data.last_whale.ts !== currentWhaleTs) {
                    currentWhaleTs = data.last_whale.ts;

                    document.getElementById('whale-alert').innerText =
                        '🐳 WHALE ' + data.last_whale.side + ' $' + Math.round(data.last_whale.value).toLocaleString();

                    setTimeout(() => {
                        document.getElementById('whale-alert').innerText = '';
                    }, 3500);
                }

                draw(data.trades, data.last_price);
            } catch (e) {
                console.log('fetch error', e);
            }
        }

        function drawGrid() {
            ctx.strokeStyle = "rgba(255,255,255,0.03)";
            ctx.lineWidth = 1;

            for (let x = 0; x < canvas.width; x += 60) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }

            for (let y = 0; y < canvas.height; y += 60) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }
        }

        function draw(trades, lastPrice) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            drawGrid();

            if (!trades || trades.length < 5) return;

            const prices = trades.map(t => t.price);
            const minP = Math.min(...prices);
            const maxP = Math.max(...prices);
            const range = maxP - minP || 1;

            trades.forEach((t, i) => {
                const x = (i / Math.max(trades.length - 1, 1)) * canvas.width;
                const y = canvas.height - ((t.price - minP) / range) * canvas.height;

                let radius = Math.sqrt(t.value) / 22;
                radius = Math.max(3, Math.min(radius, 28));

                const isWhale = t.value >= 50000;

                if (isWhale) {
                    radius *= 1.9;
                }

                const gradient = ctx.createRadialGradient(
                    x - radius / 3,
                    y - radius / 3,
                    radius / 8,
                    x,
                    y,
                    radius
                );

                if (t.side === "BUY") {
                    gradient.addColorStop(0, "#d9ffe8");
                    gradient.addColorStop(0.35, "#22c55e");
                    gradient.addColorStop(1, "#064e3b");
                    ctx.shadowColor = isWhale ? "rgba(34,197,94,0.95)" : "rgba(34,197,94,0.45)";
                } else {
                    gradient.addColorStop(0, "#ffe0e0");
                    gradient.addColorStop(0.35, "#ef4444");
                    gradient.addColorStop(1, "#7f1d1d");
                    ctx.shadowColor = isWhale ? "rgba(239,68,68,0.95)" : "rgba(239,68,68,0.45)";
                }

                ctx.shadowBlur = isWhale ? 35 : 12;

                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fillStyle = gradient;
                ctx.fill();

                if (isWhale) {
                    ctx.beginPath();
                    ctx.arc(x, y, radius * 1.25, 0, Math.PI * 2);
                    ctx.strokeStyle = t.side === "BUY"
                        ? "rgba(34,197,94,0.35)"
                        : "rgba(239,68,68,0.35)";
                    ctx.lineWidth = 3;
                    ctx.stroke();

                    ctx.shadowBlur = 0;
                    ctx.fillStyle = "rgba(255,255,255,0.95)";
                    ctx.font = "16px Arial";
                    ctx.fillText("🐳", x - 8, y + 5);
                }
            });

            ctx.shadowBlur = 0;

            if (lastPrice) {
                const currentY = canvas.height - ((lastPrice - minP) / range) * canvas.height;
                ctx.strokeStyle = "rgba(59,130,246,0.75)";
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 6]);
                ctx.beginPath();
                ctx.moveTo(0, currentY);
                ctx.lineTo(canvas.width, currentY);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }

        setInterval(updateData, 180);
        updateData();
    </script>
</body>
</html>
"""

def on_message(ws, message):
    try:
        msg = json.loads(message)
        sym = msg["s"].lower()
        price = float(msg["p"])
        qty = float(msg["q"])
        side = "SELL" if msg["m"] else "BUY"
        value = price * qty

        whale = None
        if value >= WHALE_THRESHOLD_USD:
            whale = {
                "side": side,
                "value": value,
                "price": price,
                "qty": qty,
                "ts": int(__import__("time").time() * 1000)
            }

        with lock:
            state[sym]["last_price"] = price
            state[sym]["trades"].append({
                "price": price,
                "side": side,
                "value": value
            })
            if whale:
                state[sym]["last_whale"] = whale
    except Exception as e:
        print("parse error:", e)

def start_ws():
    streams = "/".join([f"{s}@aggTrade" for s in SYMBOLS])
    url = f"wss://fstream.binance.com/ws/{streams}"
    ws = websocket.WebSocketApp(url, on_message=on_message)
    ws.run_forever()

@app.route("/")
def index():
    return Response(HTML_PAGE, mimetype="text/html")

@app.route("/data")
def data():
    sym = request.args.get("symbol", "btcusdt")
    with lock:
        return jsonify({
            "trades": list(state[sym]["trades"]),
            "last_price": state[sym]["last_price"],
            "last_whale": state[sym]["last_whale"]
        })

if __name__ == "__main__":
    threading.Thread(target=start_ws, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
