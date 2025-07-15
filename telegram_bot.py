import telebot
import threading
import time
import requests
import os
import sys
from datetime import datetime
from flask import Flask
from bip_utils import (
    Bip39MnemonicGenerator, Bip39SeedGenerator,
    Bip44, Bip44Coins, Bip44Changes
)

# === CONFIGURATION ===
BOT_TOKEN = "8010256172:AAEd02PEl8usHN3O0ptrIHLbbGAFUN0TZmA"
OWNER_ID = 6126377611  # <-- Replace with your Telegram user ID
ETHERSCAN_API = "HN4QR1YZJJTNDAMB9HFJCGXBUS35I84P1W"
WALLETS_PER_CHAIN = 2
CHECK_INTERVAL = 2
HISTORY_FILE = "balance_history.txt"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
scanning_threads = {}
wallet_stats = {"total": 0, "last_check": "N/A"}

# === Generate Mnemonic ===
def generate_mnemonic():
    return Bip39MnemonicGenerator().FromWordsNumber(12)

# === Derive Addresses ===
def derive_addresses(mnemonic):
    seed = Bip39SeedGenerator(mnemonic).Generate()
    chains = {
        "ETH": Bip44Coins.ETHEREUM,
        "BNB": Bip44Coins.BINANCE_SMART_CHAIN,
        "MATIC": Bip44Coins.POLYGON,
        "BTC": Bip44Coins.BITCOIN,
        "SOL": Bip44Coins.SOLANA,
        "TRX": Bip44Coins.TRON,
        "DOGE": Bip44Coins.DOGECOIN,
        "LTC": Bip44Coins.LITECOIN,
    }
    wallets = {chain: [] for chain in chains}
    for i in range(WALLETS_PER_CHAIN):
        for name, coin in chains.items():
            try:
                addr = Bip44.FromSeed(seed, coin).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(i).PublicKey().ToAddress()
                wallets[name].append(addr)
            except:
                wallets[name].append("ERROR")
    return wallets

# === Balance Checkers ===
def retry_request(url, retries=3):
    for _ in range(retries):
        try:
            return requests.get(url, timeout=10).json()
        except:
            time.sleep(1)
    return None

def get_eth_balance(addr):
    data = retry_request(f"https://api.etherscan.io/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}")
    try:
        return int(data.get("result", "0")) / 1e18
    except:
        return None

def get_bnb_balance(addr):
    data = retry_request(f"https://api.bscscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}")
    try:
        return int(data.get("result", "0")) / 1e18
    except:
        return None

def get_matic_balance(addr):
    data = retry_request(f"https://api.polygonscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API}")
    try:
        return int(data.get("result", "0")) / 1e18
    except:
        return None

def get_btc_balance(addr):
    data = retry_request(f"https://blockstream.info/api/address/{addr}/utxo")
    try:
        return sum(u["value"] for u in data) / 1e8
    except:
        return None

def get_sol_balance(addr):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [addr]}
        res = requests.post("https://api.mainnet-beta.solana.com", json=payload, timeout=10).json()
        return int(res.get("result", {}).get("value", 0)) / 1e9
    except:
        return None

def get_trx_balance(addr):
    data = retry_request(f"https://apilist.tronscanapi.com/api/account?address={addr}")
    try:
        return int(data.get("balance", 0)) / 1e6
    except:
        return None

def get_doge_balance(addr):
    data = retry_request(f"https://dogechain.info/api/v1/address/balance/{addr}")
    try:
        return float(data.get("balance", 0.0))
    except:
        return None

def get_ltc_balance(addr):
    data = retry_request(f"https://chain.so/api/v2/get_address_balance/LTC/{addr}")
    try:
        return float(data.get("data", {}).get("confirmed_balance", 0.0))
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

# === Logging ===
def save_log(mnemonic, chain, addr, bal):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {chain} | {addr} → {bal}\n")

# === Scanner ===
def scanner_loop(chat_id):
    scanning_threads[chat_id] = True
    while scanning_threads.get(chat_id):
        mnemonic = generate_mnemonic()
        bot.send_message(chat_id, f"🧠 Mnemonic:\n`{mnemonic}`", parse_mode="Markdown")
        wallets = derive_addresses(mnemonic)
        result = "💰 Scan Results:\n"
        wallet_stats["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for chain, addresses in wallets.items():
            for addr in addresses:
                if addr == "ERROR":
                    result += f"{chain} | Address Derivation Error\n"
                    continue
                balance = BALANCE_FUNCS.get(chain, lambda x: None)(addr)
                bal_str = f"{balance:.8f}" if isinstance(balance, float) else "Error"
                result += f"{chain} | {addr} → {bal_str}\n"
                wallet_stats["total"] += 1
                if isinstance(balance, float) and balance > 0:
                    save_log(mnemonic, chain, addr, bal_str)
        bot.send_message(chat_id, result)
        time.sleep(CHECK_INTERVAL)

# === Commands ===
markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
markup.row('/start', '/stop', '/balance', '/status', '/speed')

@bot.message_handler(commands=['start'])
def start(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, "🚀 Scanner started.", reply_markup=markup)
    threading.Thread(target=scanner_loop, args=(msg.chat.id,), daemon=True).start()

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
    bot.send_message(msg.chat.id, f"🔄 Status: {running}\n🕒 Last Check: {wallet_stats['last_check']}")

@bot.message_handler(commands=['speed'])
def speed(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, f"⚡ Wallets Checked: {wallet_stats['total']}")

# === Auto Start ===
def auto_start():
    bot.send_message(OWNER_ID, "👋 Auto-started and scanning.")
    threading.Thread(target=scanner_loop, args=(OWNER_ID,), daemon=True).start()
    bot.infinity_polling()

# === Flask Dummy Server for Render ===
@app.route('/')
def home():
    return "Bot Running!"

if __name__ == '__main__':
    threading.Thread(target=auto_start).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
