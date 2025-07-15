import telebot
import threading
import time
import requests
import os
from datetime import datetime
from flask import Flask
from bip_utils import (
    Bip39MnemonicGenerator, Bip39SeedGenerator,
    Bip44, Bip44Coins, Bip44Changes
)

# === CONFIG ===
BOT_TOKEN = "8010256172:AAEd02PEl8usHN3O0ptrIHLbbGAFUN0TZmA"
OWNER_ID = 6126377611  # <-- Replace with your Telegram user ID
MULTICHAIN_API_KEY = "HN4QR1YZJJTNDAMB9HFJCGXBUS35I84P1W"
HISTORY_FILE = "balance_history.txt"
WALLETS_PER_CHAIN = 1
CHECK_INTERVAL = 10  # seconds

# === BOT SETUP ===
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
scanning = {}

# === BUTTONS ===
def main_buttons():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('/start', '/balance', '/stop')
    return markup

# === MNEMONIC & WALLET GEN ===
def generate_mnemonic():
    return Bip39MnemonicGenerator().FromWordsNumber(12)

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
            except Exception:
                wallets[name].append("Error")
    return wallets

# === BALANCE CHECKERS ===
def get_balance_eth(addr):
    try:
        r = requests.get(f"https://api.etherscan.io/api?module=account&action=balance&address={addr}&tag=latest&apikey={MULTICHAIN_API_KEY}", timeout=10).json()
        return int(r['result']) / 1e18
    except: return None

def get_balance_bnb(addr):
    try:
        r = requests.get(f"https://api.bscscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={MULTICHAIN_API_KEY}", timeout=10).json()
        return int(r['result']) / 1e18
    except: return None

def get_balance_matic(addr):
    try:
        r = requests.get(f"https://api.polygonscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={MULTICHAIN_API_KEY}", timeout=10).json()
        return int(r['result']) / 1e18
    except: return None

def get_balance_btc(addr):
    try:
        r = requests.get(f"https://blockstream.info/api/address/{addr}/utxo", timeout=10).json()
        return sum(tx['value'] for tx in r) / 1e8
    except: return None

def get_balance_sol(addr):
    try:
        body = {"jsonrpc":"2.0","id":1,"method":"getBalance","params":[addr]}
        r = requests.post("https://api.mainnet-beta.solana.com", json=body, timeout=10).json()
        return int(r['result']['value']) / 1e9
    except: return None

def get_balance_trx(addr):
    try:
        r = requests.get(f"https://apilist.tronscanapi.com/api/account?address={addr}", timeout=10).json()
        return int(r.get('balance', 0)) / 1e6
    except: return None

def get_balance_doge(addr):
    try:
        r = requests.get(f"https://dogechain.info/api/v1/address/balance/{addr}", timeout=10).json()
        return float(r['balance'])
    except: return None

def get_balance_ltc(addr):
    try:
        r = requests.get(f"https://chain.so/api/v2/get_address_balance/LTC/{addr}", timeout=10).json()
        return float(r['data']['confirmed_balance'])
    except: return None

BALANCE_FUNCS = {
    "ETH": get_balance_eth,
    "BNB": get_balance_bnb,
    "MATIC": get_balance_matic,
    "BTC": get_balance_btc,
    "SOL": get_balance_sol,
    "TRX": get_balance_trx,
    "DOGE": get_balance_doge,
    "LTC": get_balance_ltc,
}

def save_log(mnemonic, chain, addr, bal):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {chain} | {addr} → {bal}\nMnemonic: {mnemonic}\n{'-'*60}\n")

# === SCAN THREAD ===
def scan_loop(chat_id):
    while scanning.get(chat_id, False):
        mnemonic = generate_mnemonic()
        bot.send_message(chat_id, f"🧠 Mnemonic:\n`{mnemonic}`", parse_mode="Markdown")
        wallets = derive_addresses(mnemonic)
        msg = "💰 Scan Results:\n"
        for chain, addresses in wallets.items():
            for addr in addresses:
                if addr == "Error":
                    msg += f"{chain} | Error\n"
                    continue
                bal = BALANCE_FUNCS[chain](addr)
                time.sleep(1)
                if bal is None:
                    msg += f"{chain} | {addr} → Error\n"
                else:
                    msg += f"{chain} | {addr} → {bal:.8f}\n"
                    if bal > 0:
                        save_log(mnemonic, chain, addr, bal)
        bot.send_message(chat_id, msg)
        time.sleep(CHECK_INTERVAL)

# === HANDLERS ===
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    if msg.chat.id != OWNER_ID: return
    bot.send_message(msg.chat.id, "✅ Auto-scanning started...", reply_markup=main_buttons())
    scanning[msg.chat.id] = True
    threading.Thread(target=scan_loop, args=(msg.chat.id,), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop_cmd(msg):
    if msg.chat.id != OWNER_ID: return
    scanning[msg.chat.id] = False
    bot.send_message(msg.chat.id, "⏹️ Scanning stopped.")

@bot.message_handler(commands=['balance'])
def bal_cmd(msg):
    if msg.chat.id != OWNER_ID: return
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "rb") as f:
            bot.send_document(msg.chat.id, f)
    else:
        bot.send_message(msg.chat.id, "📂 No balance history found.")

# === AUTO START ===
def auto_start():
    time.sleep(2)
    scanning[OWNER_ID] = True
    threading.Thread(target=scan_loop, args=(OWNER_ID,), daemon=True).start()

# === FAKE SERVER FOR RENDER ===
@app.route('/')
def home():
    return "Telegram bot is running."

if __name__ == "__main__":
    threading.Thread(target=auto_start).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
