import sys
import os
import requests
import logging
import time
import threading
from queue import Queue
from dotenv import load_dotenv
from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    Bip39WordsNum,
)

# Constants
LOG_FILE_NAME = "wallet_scanner.log"
TRANSACTIONS_LOG_FILE = "wallets_with_transactions.log"
ENV_FILE_NAME = ".env"
WALLETS_FILE_NAME = "wallets_with_balance.txt"
SUPPORTED_COINS = {
    "ETH": Bip44Coins.ETHEREUM,
    "BTC": Bip44Coins.BITCOIN,
    "LTC": Bip44Coins.LITECOIN,
    "DOGE": Bip44Coins.DOGECOIN,
    "BCH": Bip44Coins.BITCOIN_CASH,
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_NAME),
        logging.StreamHandler(sys.stdout),
    ],
)

logger_tx = logging.getLogger("LoggerTransactions")
file_handler_tx = logging.FileHandler(TRANSACTIONS_LOG_FILE)
logger_tx.addHandler(file_handler_tx)

# Load environment variables
load_dotenv(ENV_FILE_NAME)

# Validate environment variables
required_env_vars = ["ETHERSCAN_API_KEY"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing_vars)}")

# API keys
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# Threading queue
queue = Queue()

def generate_mnemonic():
    """Generate a 12-word BIP39 mnemonic."""
    return Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_12)

def derive_wallet_address(seed, coin):
    """Derive a wallet address for a specific coin."""
    seed_bytes = Bip39SeedGenerator(seed).Generate()
    bip44_ctx = Bip44.FromSeed(seed_bytes, SUPPORTED_COINS[coin])
    account_ctx = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    return account_ctx.PublicKey().ToAddress()

def check_balance(address, coin):
    """Check the balance of an address for a specific coin."""
    try:
        if coin == "ETH":
            url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            response = requests.get(url)
            data = response.json()
            if data["status"] == "1":
                return int(data["result"]) / 1e18  # Convert Wei to Ether
        elif coin == "BTC":
            url = f"https://blockchain.info/balance?active={address}"
            response = requests.get(url)
            data = response.json()
            return data[address]["final_balance"] / 1e8  # Convert satoshi to BTC
    except Exception as e:
        logging.error(f"Error checking {coin} balance: {e}")
    return 0

def check_transactions(address, coin):
    """Check if an address has any transaction history."""
    try:
        if coin == "ETH":
            url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}"
        elif coin == "BTC":
            url = f"https://blockchain.info/rawaddr/{address}"
        else:
            return False

        response = requests.get(url)
        data = response.json()
        if (coin == "ETH" and data["status"] == "1" and data["result"]) or (coin == "BTC" and "txs" in data and data["txs"]):
            return True
    except Exception as e:
        logging.error(f"Error checking {coin} transactions for {address}: {e}")
    return False

def write_to_file(seed, coin, address, balance):
    """Write wallet details to a file."""
    with open(WALLETS_FILE_NAME, "a") as f:
        log_message = f"Seed: {seed}\nCoin: {coin}\nAddress: {address}\nBalance: {balance} {coin}\n\n"
        f.write(log_message)
        logging.info(f"Written to file: {log_message}")

def write_active_wallet(seed, coin, address):
    """Log active wallets with transaction history."""
    with open(TRANSACTIONS_LOG_FILE, "a") as f:
        log_message = f"Active Wallet Found!\nSeed: {seed}\nCoin: {coin}\nAddress: {address}\n\n"
        f.write(log_message)
        logger_tx.info(log_message)

def process_wallet():
    """Process wallets from the queue."""
    while not queue.empty():
        seed = queue.get()
        for coin in SUPPORTED_COINS:
            address = derive_wallet_address(seed, coin)
            balance = check_balance(address, coin)
            has_tx = check_transactions(address, coin)

            logging.info(f"Seed: {seed}")
            logging.info(f"{coin} Address: {address}")
            logging.info(f"{coin} Balance: {balance}")

            if balance > 0:
                logging.info(f"(!) Wallet with balance found for {coin}!")
                write_to_file(seed, coin, address, balance)
            if has_tx:
                logging.info(f"(!) Active wallet with transactions found for {coin}!")
                write_active_wallet(seed, coin, address)

        queue.task_done()

def main():
    """Main function to initialize the wallet scanner."""
    num_threads = 15  # Adjust based on your system's capacity
    num_wallets = 500000  # Number of wallets to scan

    logging.info("Starting wallet scanner...")

    # Generate mnemonics and populate the queue
    for _ in range(num_wallets):
        queue.put(generate_mnemonic())

    # Start threads
    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=process_wallet)
        thread.start()
        threads.append(thread)

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    logging.info("Wallet scanner completed.")

if __name__ == "__main__":
    main()
