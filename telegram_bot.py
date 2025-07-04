import telebot
import threading
import time
import os
from mnemonic import Mnemonic
from eth_account import Account
import requests
from tronpy import Tron
from solana.publickey import PublicKey
from solana.rpc.api import Client as SolanaClient
from bitcoinlib.wallets import Wallet
from bitcoinlib.keys import HDKey
from web3 import Web3

TOKEN = os.getenv("TOKEN", "7953492315:AAFkQ-G6IFQR2N5Jhi2oqREBQQMMtTQOC-Q")
PASSWORD = os.getenv("PASSWORD", "M31S9760")

ETH_RPC = "https://cloudflare-eth.com"
BNB_RPC = "https://bsc-dataseed.binance.org/"
MATIC_RPC = "https://polygon-rpc.com"
AVAX_RPC = "https://api.avax.network/ext/bc/C/rpc"

AUTHORIZED_USERS = set()
MINING_THREADS = {}
STATS = {}
USER_CHAINS = {}

bot = telebot.TeleBot(TOKEN)
mnemo = Mnemonic("english")
solana_client = SolanaClient("https://api.mainnet-beta.solana.com")
tron_client = Tron()

w3_eth = Web3(Web3.HTTPProvider(ETH_RPC))
w3_bnb = Web3(Web3.HTTPProvider(BNB_RPC))
w3_matic = Web3(Web3.HTTPProvider(MATIC_RPC))
w3_avax = Web3(Web3.HTTPProvider(AVAX_RPC))

def get_balance_web3(w3, address):
    try:
        return w3.eth.get_balance(address) / 1e18
    except:
        return 0

def check_eth_balance(addr): return get_balance_web3(w3_eth, addr)
def check_bnb_balance(addr): return get_balance_web3(w3_bnb, addr)
def check_matic_balance(addr): return get_balance_web3(w3_matic, addr)
def check_avax_balance(addr): return get_balance_web3(w3_avax, addr)

def check_btc_balance(addr):
    try:
        return int(requests.get(f"https://blockchain.info/q/addressbalance/{addr}").text) / 1e8
    except:
        return 0

def check_doge_balance(addr):
    try:
        return float(requests.get(f"https://sochain.com/api/v2/get_address_balance/DOGE/{addr}").json()['data']['confirmed_balance'])
    except:
        return 0

def check_ltc_balance(addr):
    try:
        return float(requests.get(f"https://sochain.com/api/v2/get_address_balance/LTC/{addr}").json()['data']['confirmed_balance'])
    except:
        return 0

def check_trx_balance(addr):
    try:
        return float(tron_client.get_account_balance(addr))
    except:
        return 0

def check_sol_balance(addr):
    try:
        return int(solana_client.get_balance(PublicKey(addr))["result"]["value"]) / 1e9
    except:
        return 0

def mine_wallets(user_id):
    STATS[user_id] = {"scanned": 0, "found": 0}
    chains = USER_CHAINS.get(user_id, ["ETH", "BTC", "BNB", "DOGE", "SOL", "MATIC", "AVAX", "TRX", "LTC"])

    while user_id in MINING_THREADS:
        mnemonic = mnemo.generate(strength=128)
        msg_parts = []
        found_any = False

        def add_if_balance(label, addr, bal):
            nonlocal found_any
            if bal > 0:
                found_any = True
                msg_parts.append(f"{label}: {addr} | {bal:.4f} {label}")

        acct = Account.from_mnemonic(mnemonic)
        if "ETH" in chains:
            add_if_balance("ETH", acct.address, check_eth_balance(acct.address))
        if "BNB" in chains:
            add_if_balance("BNB", acct.address, check_bnb_balance(acct.address))
        if "MATIC" in chains:
            add_if_balance("MATIC", acct.address, check_matic_balance(acct.address))
        if "AVAX" in chains:
            add_if_balance("AVAX", acct.address, check_avax_balance(acct.address))
        if "BTC" in chains:
            try:
                btc_wallet = Wallet.create(name=None, keys=mnemonic, witness_type='segwit', network='bitcoin')
                btc_addr = btc_wallet.get_key().address
                add_if_balance("BTC", btc_addr, check_btc_balance(btc_addr))
            except:
                pass
        if "DOGE" in chains:
            try:
                doge_key = HDKey().from_passphrase(mnemonic, network='dogecoin')
                add_if_balance("DOGE", doge_key.address(), check_doge_balance(doge_key.address()))
            except:
                pass
        if "LTC" in chains:
            try:
                ltc_key = HDKey().from_passphrase(mnemonic, network='litecoin')
                add_if_balance("LTC", ltc_key.address(), check_ltc_balance(ltc_key.address()))
            except:
                pass
        if "TRX" in chains:
            try:
                acct = tron_client.generate_address(mnemonic=mnemonic)
                addr = acct["base58check_address"]
                add_if_balance("TRX", addr, check_trx_balance(addr))
            except:
                pass
        if "SOL" in chains:
            try:
                seed = mnemo.to_seed(mnemonic)
                pubkey = PublicKey(seed[:32])
                addr = str(pubkey)
                add_if_balance("SOL", addr, check_sol_balance(addr))
            except:
                pass

        STATS[user_id]["scanned"] += 1

        if found_any:
            STATS[user_id]["found"] += 1
            full_msg = f"🔑 Mnemonic: {mnemonic}\n" + "\n".join(msg_parts)
            with open("history.txt", "a") as f:
                f.write(full_msg + "\n\n")
            bot.send_message(user_id, f"🚨 Found Wallet!\n{full_msg}")

        time.sleep(1)

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "🔐 Enter password:")

@bot.message_handler(func=lambda msg: msg.text and msg.chat.id not in AUTHORIZED_USERS)
def check_password(message):
    if message.text == PASSWORD:
        AUTHORIZED_USERS.add(message.chat.id)
        bot.send_message(message.chat.id, "✅ Access granted. Use /mine /stop /status /history /setchain")
    else:
        bot.send_message(message.chat.id, "❌ Incorrect password.")

@bot.message_handler(commands=["mine"])
def mine(message):
    uid = message.chat.id
    if uid in AUTHORIZED_USERS and uid not in MINING_THREADS:
        thread = threading.Thread(target=mine_wallets, args=(uid,))
        MINING_THREADS[uid] = thread
        thread.start()
        bot.send_message(uid, "🚀 Mining started...")
    else:
        bot.send_message(uid, "⚠️ Already mining or unauthorized.")

@bot.message_handler(commands=["stop"])
def stop(message):
    uid = message.chat.id
    if uid in MINING_THREADS:
        del MINING_THREADS[uid]
        bot.send_message(uid, "🛑 Mining stopped.")
    else:
        bot.send_message(uid, "ℹ️ Not mining.")

@bot.message_handler(commands=["status"])
def status(message):
    uid = message.chat.id
    stats = STATS.get(uid, {"scanned": 0, "found": 0})
    running = "Yes" if uid in MINING_THREADS else "No"
    bot.send_message(uid, f"📊 Status:\nRunning: {running}\nScanned: {stats['scanned']}\nFound: {stats['found']}")

@bot.message_handler(commands=["history"])
def history(message):
    uid = message.chat.id
    if os.path.exists("history.txt"):
        with open("history.txt", "rb") as f:
            bot.send_document(uid, f)
    else:
        bot.send_message(uid, "📂 No history found.")

@bot.message_handler(commands=["setchain"])
def set_chain(message):
    uid = message.chat.id
    bot.send_message(uid, "✏️ Type chains to scan (e.g. ETH BTC SOL TRX):")
    bot.register_next_step_handler(message, lambda msg: USER_CHAINS.update({uid: msg.text.upper().split()}))

print("🤖 Bot running...")
bot.infinity_polling()
