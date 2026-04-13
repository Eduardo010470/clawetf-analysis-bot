import anthropic
import requests
import os
from datetime import datetime
import pytz

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def get_price(ticker):
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if len(hist) >= 1:
            return float(hist["Close"].iloc[-1])
    except:
        pass
    return 0

def send_telegram(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for attempt in range(3):
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=30)
            if r.status_code == 200:
                return True
        except:
            import time
            time.sleep(5)
    return False

def analyze_with_claude(portfolio_text):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": f"Voce e um analista financeiro senior. Analise este portfolio de ETFs cripto da NASDAQ de um investidor brasileiro com estrategia DCA de longo prazo.\n\nPORTFOLIO:\n{portfolio_text}\n\nForneca analise concisa em portugues (max 300 palavras): 1) Situacao geral 2) Destaques do dia 3) Recomendacao pratica 4) Perspectiva de mercado. Seja direto e honesto."}]
    )
    return response.content[0].text

def main():
    br_tz = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(br_tz).strftime("%d/%m/%Y %H:%M")
    print(f"[{agora}] Iniciando envio de analises...")
    
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/user_connections?telegram_chat_id=not.is.null&select=user_id,telegram_chat_id",
        headers=headers
    )
    connections = res.json()
    print(f"Usuarios com Telegram: {len(connections)}")
    
    for conn in connections:
        user_id = conn["user_id"]
        chat_id = conn["telegram_chat_id"]
        try:
            pos_res = requests.get(
                f"{SUPABASE_URL}/rest/v1/positions?user_id=eq.{user_id}&select=*",
                headers=headers
            )
            positions = pos_res.json()
            if not positions:
                continue
            
            total_invested = 0
            total_current = 0
            lines = []
            tickers = list(set(p["symbol"] for p in positions))
            prices = {t: get_price(t) for t in tickers}
            
            for p in positions:
                price = prices.get(p["symbol"], p["avg_price"])
                invested = p["quantity"] * p["avg_price"]
                current = p["quantity"] * price
                pl = current - invested
                pl_pct = (pl / invested * 100) if invested > 0 else 0
                total_invested += invested
                total_current += current
                lines.append(f"{p['symbol']}: {p['quantity']:.4f} cotas @ ${p['avg_price']:.2f} | Atual: ${price:.2f} | P&L: {pl_pct:.2f}%")
            
            total_pl = total_current - total_invested
            total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0
            
            portfolio_text = f"Total Investido: ${total_invested:.2f}\nValor Atual: ${total_current:.2f}\nP&L Total: ${total_pl:.2f} ({total_pl_pct:.2f}%)\n\n" + "\n".join(lines)
            analysis = analyze_with_claude(portfolio_text)
            
            message = f"<b>ClawETF - Analise Diaria</b>\nData: {agora}\n\n<b>RESUMO</b>\nInvestido: ${total_invested:.2f}\nAtual: ${total_current:.2f}\nP&L: ${total_pl:.2f} ({total_pl_pct:.2f}%)\n\n<b>ANALISE CLAUDE</b>\n{analysis}\n\n<i>Powered by ClawETF kruptos</i>"
            
            if send_telegram(chat_id, message):
                print(f"Enviado para {chat_id}")
            else:
                print(f"Falha para {chat_id}")
        except Exception as e:
            print(f"Erro para {user_id}: {e}")
    
    print("Concluido!")

if __name__ == "__main__":
    main()
