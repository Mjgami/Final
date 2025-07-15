import os
import time 
import json 
import requests
import threading
import logging
from flask import Flask, request
from telebot import TeleBot, types
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes
from datetime import datetime

BOT_TOKEN = "8010256172:AAEd02PEl8usHN3O0ptrIHLbbGAFUN0TZmA"
OWNER_ID = 6126377611
ETHERSCAN_API = "HN4QR1YZJJTNDAMB9HFJCGXBUS35I84P1W"
WEBHOOK_URL = "https://final-xtfg.onrender.com/"  # <- Replace with your actual Render URL
HISTORY_FILE = "balance_history.txt"
WALLETS_PER_CHAIN = 2
CHECK_INTERVAL = 2 # seconds time 

bot = TeleBot(BOT_TOKEN)
app = Flask(__name__)
scanning_threads = {}
wallet_stats = {"last_check": "Never", "total": 0}

# === Generate mnemonic ===
def generate_mnemonic():
    return Bip39MnemonicGenerator().FromWordsNumber(12)

# === Derive addresses from mnemonic ===
def derive_addresses_and_privates(mnemonic):
    seed = Bip39SeedGenerator(mnemonic).Generate()
    coins = {
        "ETH": Bip44Coins.ETHEREUM,
        "BNB": Bip44Coins.BINANCE_SMART_CHAIN,
        "MATIC": Bip44Coins.POLYGON,
        "BTC": Bip44Coins.BITCOIN,
        "SOL": Bip44Coins.SOLANA,
        "TRX": Bip44Coins.TRON,
        "DOGE": Bip44Coins.DOGECOIN,
        "LTC": Bip44Coins.LITECOIN,
    }
    results = {c: [] for c in coins}
    for i in range(WALLETS_PER_CHAIN):
        for name, coin in coins.items():
            wallet = Bip44.FromSeed(seed, coin).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(i)
            addr = wallet.PublicKey().ToAddress()
            priv = wallet.PrivateKey().Raw().ToHex()
            results[name].append((addr, priv))
    return results

# === Public API balance functions ===
def get_eth_balance(addr):
    try:
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}"
        res = requests.get(url, timeout=10).json()
        return int(res["result"]) / 1e18
    except:
        return None

def get_rpc_balance(rpc, method, params):
    try:
        res = requests.post(rpc, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=10).json()
        return int(res.get("result", 0))
    except:
        return None

def get_btc_balance(addr):
    try:
        utxos = requests.get(f"https://blockstream.info/api/address/{addr}/utxo", timeout=10).json()
        return sum([u["value"] for u in utxos]) / 1e8
    except:
        return None

def get_sol_balance(addr):
    lam = get_rpc_balance("https://api.mainnet-beta.solana.com", "getBalance", [addr])
    return lam / 1e9 if lam else None

def get_trx_balance(addr):
    try:
        data = requests.get(f"https://apilist.tronscanapi.com/api/account?address={addr}", timeout=10).json()
        return float(data.get("balance", 0)) / 1e6
    except:
        return None

def get_doge_balance(addr):
    try:
        data = requests.get(f"https://dogechain.info/api/v1/address/balance/{addr}", timeout=10).json()
        return float(data.get("balance", 0.0))
    except:
        return None

def get_ltc_balance(addr):
    try:
        data = requests.get(f"https://chain.so/api/v2/get_address_balance/LTC/{addr}", timeout=10).json()
        return float(data.get("data", {}).get("confirmed_balance", 0.0))
    except:
        return None

def get_matic_balance(addr):
    try:
        url = f"https://api.polygonscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}"
        res = requests.get(url, timeout=10).json()
        return int(res["result"]) / 1e18
    except:
        return None

def get_bnb_balance(addr):
    try:
        url = f"https://api.bscscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}"
        res = requests.get(url, timeout=10).json()
        return int(res["result"]) / 1e18
    except:
        return None

BALANCE_FUNCS = {
    "ETH": get_eth_balance,
    "BNB": get_bnb_balance,
    "MATIC": get_matic_balance,
    "BTC": get_btc_balance,
    "SOL": get_sol_balance,
    "TRX": get_trx_balance,
    "DOGE": get_doge_balance,
    "LTC": get_ltc_balance,
}

def save_log(mnemonic, chain, addr, priv, bal):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {chain} | {addr} → {bal} | mnemonic: {mnemonic} | priv: {priv}\n")

def scanner_loop(chat_id):
    scanning_threads[chat_id] = True
    while scanning_threads.get(chat_id, False):
        mnemonic = generate_mnemonic()
        bot.send_message(chat_id, f"🧠 Mnemonic:\n`{mnemonic}`", parse_mode="Markdown")
        wallets = derive_addresses_and_privates(mnemonic)
        wallet_stats["last_check"] = datetime.now().strftime("%H:%M:%S")
        wallet_stats["total"] += WALLETS_PER_CHAIN * len(wallets)
        msg = "💰 Scan Results:\n"
        for chain, data in wallets.items():
            for addr, priv in data:
                try:
                    bal = BALANCE_FUNCS[chain](addr)
                except:
                    bal = None
                bal_str = f"{bal:.8f}" if isinstance(bal, float) else "Error"
                msg += f"{chain} | {addr} → {bal_str}\n"
                if isinstance(bal, float) and bal > 0:
                    save_log(mnemonic, chain, addr, priv, bal_str)
        bot.send_message(chat_id, msg)
        time.sleep(CHECK_INTERVAL)

# === Commands ===
@bot.message_handler(commands=['start'])
def start(msg):
    if msg.chat.id != OWNER_ID: return
    if scanning_threads.get(msg.chat.id): return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("/start", "/stop", "/balance", "/status", "/speed")
    bot.send_message(msg.chat.id, "✅ Scanner started", reply_markup=markup)
    threading.Thread(target=scanner_loop, args=(msg.chat.id,), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop(msg):
    if msg.chat.id != OWNER_ID: return
    scanning_threads[msg.chat.id] = False
    bot.send_message(msg.chat.id, "🛑 Stopped.")

@bot.message_handler(commands=['balance'])
def balance(msg):
    if msg.chat.id != OWNER_ID: return
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "rb") as f:
            bot.send_document(msg.chat.id, f)
    else:
        bot.send_message(msg.chat.id, "📭 No history yet.")

@bot.message_handler(commands=['status'])
def status(msg):
    if msg.chat.id != OWNER_ID: return
    running = "✅ Running" if scanning_threads.get(msg.chat.id) else "❌ Stopped"
    bot.send_message(msg.chat.id, f"Status: {running}\nLast check: {wallet_stats['last_check']}")

@bot.message_handler(commands=['speed'])
def speed(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, f"⚡ Wallets checked: {wallet_stats['total']}")

# === Webhook for Render ===
@app.route('/', methods=['GET'])
def index():
    return "Bot running via webhook!"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

if __name__ == "__main__":
    setup_webhook()
    threading.Thread(target=lambda: bot.send_message(OWNER_ID, "🚀 Bot Online & Auto-Scanning"), daemon=True).start()
    threading.Thread(target=lambda: scanner_loop(OWNER_ID), daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
