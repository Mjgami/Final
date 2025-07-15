import telebot
from telebot import types
import threading
import time
import requests
import os
import sys
from datetime import datetime
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# ==== CONFIG ====
BOT_TOKEN = "8010256172:AAEd02PEl8usHN3O0ptrIHLbbGAFUN0TZmA"
ADMIN_ID = 6126377611
ETHERSCAN_API_KEY = "HN4QR1YZJJTNDAMB9HFJCGXBUS35I84P1W"
HISTORY_FILE = "balance_history.txt"
WALLETS_PER_CHAIN = 1
CHECK_INTERVAL = 10  # seconds

bot = telebot.TeleBot(BOT_TOKEN)

# === Generate Mnemonic ===
def generate_mnemonic():
    return Bip39MnemonicGenerator().FromWordsNumber(12)

# === Derive Wallets ===
def derive_addresses(mnemonic):
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
    result = {c: [] for c in coins}
    for i in range(WALLETS_PER_CHAIN):
        for name, coin in coins.items():
            addr = Bip44.FromSeed(seed, coin).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(i).PublicKey().ToAddress()
            result[name].append(addr)
    return result

# === Balance Checkers (ETH/BNB/MATIC via Etherscan Multichain Key) ===
def get_eth_balance(addr):
    for _ in range(3):
        try:
            res = requests.get(f"https://api.etherscan.io/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API_KEY}", timeout=10).json()
            return int(res["result"]) / 1e18
        except:
            time.sleep(1)
    return None

def get_bnb_balance(addr):
    for _ in range(3):
        try:
            res = requests.get(f"https://api.bscscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API_KEY}", timeout=10).json()
            return int(res["result"]) / 1e18
        except:
            time.sleep(1)
    return None

def get_matic_balance(addr):
    for _ in range(3):
        try:
            res = requests.get(f"https://api.polygonscan.com/api?module=account&action=balance&address={addr}&tag=latest&apikey={ETHERSCAN_API_KEY}", timeout=10).json()
            return int(res["result"]) / 1e18
        except:
            time.sleep(1)
    return None

# === Public Balance Checkers ===
def get_btc_balance(addr):
    try:
        data = requests.get(f"https://blockstream.info/api/address/{addr}/utxo", timeout=10).json()
        sats = sum(u["value"] for u in data)
        return sats / 1e8
    except:
        return None

def get_sol_balance(addr):
    try:
        payload = {"jsonrpc":"2.0","id":1,"method":"getBalance","params":[addr]}
        res = requests.post("https://api.mainnet-beta.solana.com", json=payload, timeout=10).json()
        lamports = res.get("result", {}).get("value", 0)
        return lamports / 1e9
    except:
        return None

def get_trx_balance(addr):
    try:
        res = requests.get(f"https://apilist.tronscanapi.com/api/account?address={addr}", timeout=10).json()
        return res.get("balance", 0) / 1e6
    except:
        return None

def get_doge_balance(addr):
    try:
        res = requests.get(f"https://dogechain.info/api/v1/address/balance/{addr}", timeout=10).json()
        return float(res.get("balance", 0.0))
    except:
        return None

def get_ltc_balance(addr):
    try:
        res = requests.get(f"https://chain.so/api/v2/get_address_balance/LTC/{addr}", timeout=10).json()
        return float(res.get("data", {}).get("confirmed_balance", 0.0))
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

# === Log Wallets with Balance ===
def save_log(mnemonic, chain, addr, bal):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {chain} | {addr} → {bal} | mnemonic: {mnemonic}\n")

# === Wallet Scanner ===
stop_flag = threading.Event()

def scanner_loop(chat_id):
    while not stop_flag.is_set():
        mnemonic = generate_mnemonic()
        bot.send_message(chat_id, f"🧠 Mnemonic:\n`{mnemonic}`", parse_mode="Markdown")
        wallets = derive_addresses(mnemonic)
        msg = "💰 Scan Results:\n"
        for chain, addrs in wallets.items():
            for addr in addrs:
                bal = BALANCE_FUNCS[chain](addr)
                if isinstance(bal, float):
                    msg += f"{chain} | {addr} → {bal:.8f}\n"
                    if bal > 0:
                        save_log(mnemonic, chain, addr, bal)
                else:
                    msg += f"{chain} | {addr} → Error\n"
        bot.send_message(chat_id, msg)
        time.sleep(CHECK_INTERVAL)

# === Handlers ===
@bot.message_handler(commands=["start"])
def handle_start(msg):
    if msg.chat.id != ADMIN_ID:
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("/start", "/balance", "/stop")
    bot.send_message(msg.chat.id, "✅ Auto scanner running...", reply_markup=markup)
    stop_flag.clear()
    threading.Thread(target=scanner_loop, args=(msg.chat.id,), daemon=True).start()

@bot.message_handler(commands=["stop"])
def handle_stop(msg):
    if msg.chat.id != ADMIN_ID:
        return
    stop_flag.set()
    bot.send_message(msg.chat.id, "🛑 Scanner stopped.")

@bot.message_handler(commands=["balance"])
def handle_balance(msg):
    if msg.chat.id != ADMIN_ID:
        return
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "rb") as f:
            bot.send_document(msg.chat.id, f, caption="📄 Wallets with Balance")
    else:
        bot.send_message(msg.chat.id, "No wallet with balance found yet.")

# === Auto Start on Launch ===
def auto_start():
    stop_flag.clear()
    threading.Thread(target=scanner_loop, args=(ADMIN_ID,), daemon=True).start()

auto_start()
bot.infinity_polling()
