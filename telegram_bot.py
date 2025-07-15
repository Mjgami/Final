import telebot
import threading
import time
import requests
import os
import sys
from flask import Flask
from datetime import datetime
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes, Bip44Depth, Bip44Levels

# === CONFIGURATION ===
BOT_TOKEN = "8010256172:AAEd02PEl8usHN3O0ptrIHLbbGAFUN0TZmA"
OWNER_ID = 6126377611  # your Telegram user ID
ETHERSCAN_API = "HN4QR1YZJJTNDAMB9HFJCGXBUS35I84P1W"
WALLETS_PER_CHAIN = 2
CHECK_INTERVAL = 2  # seconds
HISTORY_FILE = "balance_history.txt"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
scanning_threads = {}
wallet_stats = {"total": 0, "last_check": "Never"}

# === GENERATE MNEMONIC ===
def generate_mnemonic():
    return Bip39MnemonicGenerator().FromWordsNumber(12)

# === DERIVE ADDRESSES ===
def derive_wallets(mnemonic):
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
    wallets = {c: [] for c in coins}
    for chain, coin in coins.items():
        bip = Bip44.FromSeed(seed, coin).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT)
        for i in range(WALLETS_PER_CHAIN):
            w = bip.AddressIndex(i)
            wallets[chain].append({
                "address": w.PublicKey().ToAddress(),
                "private": w.PrivateKey().ToWif()
            })
    return wallets

# === BALANCE CHECKERS ===
def retry_request(url, tries=3):
    for _ in range(tries):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            time.sleep(1)
    return {}

def get_eth_balance(addr):  # ETH, BNB, MATIC
    url = f"https://api.etherscan.io/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}"
    res = retry_request(url)
    return int(res.get("result", 0)) / 1e18 if "result" in res else None

def get_btc_balance(addr):
    res = retry_request(f"https://blockstream.info/api/address/{addr}/utxo")
    sats = sum(i["value"] for i in res) if isinstance(res, list) else 0
    return sats / 1e8

def get_sol_balance(addr):
    data = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [addr]}
    for _ in range(3):
        try:
            r = requests.post("https://api.mainnet-beta.solana.com", json=data, timeout=10).json()
            return r["result"]["value"] / 1e9
        except:
            time.sleep(1)
    return None

def get_trx_balance(addr):
    url = f"https://apilist.tronscanapi.com/api/account?address={addr}"
    res = retry_request(url)
    return res.get("balance", 0) / 1e6 if "balance" in res else 0

def get_doge_balance(addr):
    res = retry_request(f"https://dogechain.info/api/v1/address/balance/{addr}")
    return float(res.get("balance", 0.0)) if "balance" in res else None

def get_ltc_balance(addr):
    res = retry_request(f"https://chain.so/api/v2/get_address_balance/LTC/{addr}")
    return float(res.get("data", {}).get("confirmed_balance", 0.0)) if "data" in res else None

BALANCE_FUNCS = {
    "ETH": get_eth_balance,
    "BNB": get_eth_balance,
    "MATIC": get_eth_balance,
    "BTC": get_btc_balance,
    "SOL": get_sol_balance,
    "TRX": get_trx_balance,
    "DOGE": get_doge_balance,
    "LTC": get_ltc_balance,
}

# === SAVE RESULTS ===
def save_log(mnemonic, privkey, chain, addr, balance):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {chain} | {addr} → {balance}\nMnemonic: {mnemonic}\nPrivate Key: {privkey}\n{'-'*50}\n")

# === SCAN LOOP ===
def scanner(chat_id):
    scanning_threads[chat_id] = True
    while scanning_threads[chat_id]:
        mnemonic = generate_mnemonic()
        bot.send_message(chat_id, f"🧠 Mnemonic:\n`{mnemonic}`", parse_mode="Markdown")
        wallets = derive_wallets(mnemonic)
        msg = "💰 Scan Results:\n"
        wallet_stats["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for chain, items in wallets.items():
            for w in items:
                addr, priv = w["address"], w["private"]
                bal = BALANCE_FUNCS[chain](addr)
                wallet_stats["total"] += 1
                b = f"{bal:.8f}" if isinstance(bal, float) else "Error"
                msg += f"{chain} | {addr} → {b}\n"
                if isinstance(bal, float) and bal > 0:
                    save_log(mnemonic, priv, chain, addr, b)
        bot.send_message(chat_id, msg)
        time.sleep(CHECK_INTERVAL)

# === TELEGRAM COMMANDS ===
markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
markup.add("/start", "/stop", "/balance", "/status", "/speed")

@bot.message_handler(commands=['start'])
def start(msg):
    if msg.chat.id != OWNER_ID: return
    if scanning_threads.get(msg.chat.id): return
    bot.send_message(msg.chat.id, "🔄 Scanning started...", reply_markup=markup)
    threading.Thread(target=scanner, args=(msg.chat.id,), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop(msg):
    if msg.chat.id != OWNER_ID: return
    scanning_threads[msg.chat.id] = False
    bot.send_message(msg.chat.id, "🛑 Scanning stopped.", reply_markup=markup)

@bot.message_handler(commands=['balance'])
def balance(msg):
    if msg.chat.id != OWNER_ID: return
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "rb") as f:
            bot.send_document(msg.chat.id, f, caption="📄 Found Wallets")
    else:
        bot.send_message(msg.chat.id, "No balance found yet.")

@bot.message_handler(commands=['status'])
def status(msg):
    if msg.chat.id != OWNER_ID: return
    running = "✅ Running" if scanning_threads.get(msg.chat.id) else "❌ Stopped"
    bot.send_message(msg.chat.id, f"🔄 Status: {running}\n⏱ Last Check: {wallet_stats['last_check']}")

@bot.message_handler(commands=['speed'])
def speed(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, f"⚡ Wallets Checked: {wallet_stats['total']}")

# === AUTO START FOR OWNER_ID ===
def auto_start():
    bot.send_message(OWNER_ID, "🚀 Auto-scanner started.")
    threading.Thread(target=scanner, args=(OWNER_ID,), daemon=True).start()
    bot.infinity_polling()

# === FAKE WEB SERVER FOR RENDER ===
@app.route('/')
def index():
    return "Bot Running"

if __name__ == "__main__":
    threading.Thread(target=auto_start).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
