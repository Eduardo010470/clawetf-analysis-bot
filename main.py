import os
#!/usr/bin/env python3
import yfinance as yf
import requests
import anthropic
from datetime import datetime
import pytz

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SUPABASE_URL = "https://kqkxulsuevfuhmuvhxsp.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
USER_ID = os.environ.get("USER_ID", "")

NOMES = {
    "FBTC": "Fidelity BTC",
    "BITB": "Bitwise BTC",
    "FETH": "Fidelity ETH",
    "ETHW": "Bitwise ETH",
    "ETH":  "Grayscale ETH",
    "ETHA": "iShares ETH",
    "BSOL": "Bitwise SOL",
    "XRPR": "REX XRP",
    "GXRP": "Grayscale XRP",
    "IBIT": "iShares BTC",
    "ARKB": "ARK BTC",
    "MSBT": "Morgan Stanley BTC",
}

def get_positions_supabase():
    url = f"{SUPABASE_URL}/rest/v1/positions?select=*&user_id=eq.{USER_ID}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            portfolio = []
            seen = {}
            for p in data:
                sym = p["symbol"].strip()
                qty = float(p.get("quantity", 0))
                price = float(p.get("avg_price") or p.get("price", 0))
                if sym not in seen:
                    seen[sym] = {"qty": qty, "total": qty * price}
                else:
                    seen[sym]["qty"] += qty
                    seen[sym]["total"] += qty * price
            for sym, v in seen.items():
                avg = v["total"] / v["qty"] if v["qty"] > 0 else 0
                portfolio.append((sym, v["qty"], round(avg, 4)))
            return portfolio
    except Exception as e:
        print(f"Erro Supabase: {e}")
    return []

def get_preco(ticker):
    try:
        t = yf.Ticker(ticker)
        preco = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        if preco:
            return round(float(preco), 2)
        hist = t.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception as e:
        print(f"Erro ao buscar {ticker}: {e}")
    return 0.0

def gerar_relatorio():
    portfolio = get_positions_supabase()
    if not portfolio:
        print("Falha ao buscar posicoes do Supabase")
        return None, None
    br_tz = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(br_tz).strftime("%d/%m/%Y %H:%M")
    total_investido = 0.0
    total_atual = 0.0
    linhas_ativos = []
    dados_ativos = []
    tickers_unicos = list(dict.fromkeys(t for t, _, _ in portfolio))
    precos = {tk: get_preco(tk) for tk in tickers_unicos}
    for ticker, qtd, dca in portfolio:
        preco = precos.get(ticker, 0.0)
        investido = qtd * dca
        atual = qtd * preco
        pl = atual - investido
        pl_pct = (pl / investido * 100) if investido else 0.0
        total_investido += investido
        total_atual += atual
        nome = NOMES.get(ticker, ticker)
        emoji_pl = "OK" if pl >= 0 else "X"
        seta = "ACIMA" if preco >= dca else "ABAIXO"
        linhas_ativos.append(
            seta + " " + ticker + " (" + nome + ")\n"
            "   Cotacao: $ " + str(preco) + "\n"
            "   Valor: $ " + str(round(atual,2)) + "  " + emoji_pl + " P&L: $ " + str(round(pl,2)) + " (" + str(round(pl_pct,2)) + "%)"
        )
        dados_ativos.append({
            "ticker": ticker, "nome": nome, "preco": preco,
            "dca": dca, "qtd": qtd, "investido": round(investido, 2),
            "atual": round(atual, 2), "pl": round(pl, 2), "pl_pct": round(pl_pct, 2),
        })
    pl_total = total_atual - total_investido
    pl_total_pct = (pl_total / total_investido * 100) if total_investido else 0.0
    seta_total = "POSITIVO" if pl_total >= 0 else "NEGATIVO"
    relatorio = (
        "PORTFOLIO CRIPTO ETF - Eduardo\n"
        "Data: " + agora + "\n"
        "------------------------------\n\n"
        "RESUMO GERAL\n"
        "Investido: $ " + str(round(total_investido,2)) + "\n"
        "Valor atual: $ " + str(round(total_atual,2)) + "\n"
        + seta_total + " P&L: $ " + str(round(pl_total,2)) + " (" + str(round(pl_total_pct,2)) + "%)\n\n"
        "------------------------------\n\n"
        "ANALISE INDIVIDUAL\n\n"
        + "\n\n".join(linhas_ativos)
        + "\n\n------------------------------\n"
        "Analise Claude em instantes..."
    )
    return relatorio, dados_ativos

def enviar_telegram(mensagem):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    for tentativa in range(3):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return True
        except Exception as e:
            print("Erro Telegram tentativa " + str(tentativa+1) + ": " + str(e))
            import time
            time.sleep(5)
    return False

def analisar_com_claude(relatorio, dados):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    contexto = "\n".join([
        "- " + d["nome"] + " (" + d["ticker"] + "): cotacao $" + str(d["preco"]) +
        ", DCA $" + str(d["dca"]) + ", P&L " + str(d["pl_pct"]) + "%, valor $" + str(d["atual"])
        for d in dados
    ])
    prompt = "Voce e um assistente financeiro analisando carteira de cripto ETFs de Eduardo, medico brasileiro, DCA longo prazo via Avenue/Nomad.\n\nRELATORIO:\n" + relatorio + "\n\nDADOS:\n" + contexto + "\n\nAnalise CONCISA max 300 palavras: 1) Situacao geral 2) Destaques do dia 3) Sugestao rebalanceamento 4) Sugestao aporte se houver capital 5) Perspectiva mercado. Seja direto e honesto sem otimismo excessivo."
    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return "Erro Claude API: " + str(e)

def main():
    print("Iniciando...")
    relatorio, dados = gerar_relatorio()
    if not relatorio:
        print("Abortado — sem posicoes")
        return
    print("Relatorio gerado")
    if enviar_telegram(relatorio):
        print("Relatorio enviado")
    else:
        print("Falha relatorio")
    print("Consultando Claude...")
    analise = analisar_com_claude(relatorio, dados)
    msg = "ANALISE CLAUDE\n------------------------------\n\n" + analise
    if enviar_telegram(msg):
        print("Analise enviada")
    else:
        print("Falha analise")
    print("Concluido.")

if __name__ == "__main__":
    main()
