# telegram_bot.py (Full Code with 9 Blockchain Support using Free Public APIs)
# Import all necessary modules
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
from bitcoinlib.mnemonic import Mnemonic as BTCMnemonic
from bitcoinlib.keys import HDKey
from web3 import Web3

# Config
TOKEN = os.getenv("TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
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

def get_balance_web3(web3_instance, address):
    try:
        balance = web3_instance.eth.get_balance(address)
        return balance / 1e18
    except:
        return 0

def check_eth_balance(addr): return get_balance_web3(w3_eth, addr)
def check_bnb_balance(addr): return get_balance_web3(w3_bnb, addr)
def check_matic_balance(addr): return get_balance_web3(w3_matic, addr)
def check_avax_balance(addr): return get_balance_web3(w3_avax, addr)
def check_btc_balance(addr): return int(requests.get(f"https://blockchain.info/q/addressbalance/{addr}").text) / 1e8 if addr else 0
def check_doge_balance(addr): return float(requests.get(f"https://sochain.com/api/v2/get_address_balance/DOGE/{addr}").json()['data']['confirmed_balance']) if addr else 0
def check_ltc_balance(addr): return float(requests.get(f"https://sochain.com/api/v2/get_address_balance/LTC/{addr}").json()['data']['confirmed_balance']) if addr else 0
def check_trx_balance(addr): return float(tron_client.get_account_balance(addr)) if addr else 0
def check_sol_balance(addr): return int(solana_client.get_balance(PublicKey(addr))["result"]["value"]) / 1e9 if addr else 0

# Wallet mining logic (truncated below)
# Full mining and Telegram command code continues...