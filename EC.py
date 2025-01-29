import sys
import os
import requests
import logging
import asyncio
import aiohttp
import itertools
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
LOG_FILE_NAME_12 = "wallet_scanner_12.log"
LOG_FILE_NAME_24 = "wallet_scanner_24.log"
ERROR_LOG_FILE_NAME = "wallet_scanner_errors.log"
ENV_FILE_NAME = ".env"
WALLETS_FILE_NAME_12 = "wallets_with_balance_12.txt"
WALLETS_FILE_NAME_24 = "wallets_with_balance_24.txt"

# Configuration
NUM_WALLETS = 500000
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
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE_NAME_12),
        logging.FileHandler(LOG_FILE_NAME_24),
        logging.FileHandler(ERROR_LOG_FILE_NAME),
    ],
)

# Load environment variables
load_dotenv(ENV_FILE_NAME)

# API keys handling
API_KEYS = os.getenv("ETHERSCAN_API_KEYS", "").split(",")
if not API_KEYS:
    raise EnvironmentError("No API keys found in the environment variables.")
api_key_gen = itertools.cycle(API_KEYS)

# Wallet-related functions
def generate_mnemonic(words_num):
    """Generate a BIP39 mnemonic with the specified length."""
    return Bip39MnemonicGenerator().FromWordsNumber(words_num)

def derive_wallet_address(seed, coin):
    """Derive a wallet address for a specific coin."""
    seed_bytes = Bip39SeedGenerator(seed).Generate()
    bip44_ctx = Bip44.FromSeed(seed_bytes, SUPPORTED_COINS[coin])
    account_ctx = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    return account_ctx.PublicKey().ToAddress()

async def check_balance_async(session, address, coin):
    """Check the balance of an address for a specific coin asynchronously."""
    try:
        api_key = next(api_key_gen)
        if coin == "ETH":
            url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={api_key}"
        elif coin == "BTC":
            url = f"https://blockchain.info/balance?active={address}"
        elif coin == "LTC":
            url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance"
        elif coin == "DOGE":
            url = f"https://dogechain.info/api/v1/address/balance/{address}"
        elif coin == "BCH":
            url = f"https://rest.bitcoin.com/v2/address/details/{address}"
        else:
            return 0
        async with session.get(url) as response:
            data = await response.json()
            if "balance" in data:
                return float(data["balance"])
            elif "final_balance" in data:
                return data["final_balance"] / 1e8
            elif "result" in data:
                return int(data["result"]) / 1e18
    except Exception as e:
        logging.error(f"Error checking {coin} balance for address {address}: {e}")
    return 0

def write_to_file(file_name, seed, coin, address, balance):
    """Write wallet details to a file."""
    with open(file_name, "a") as f:
        log_message = f"Seed: {seed}\nCoin: {coin}\nAddress: {address}\nBalance: {balance} {coin}\n\n"
        f.write(log_message)

async def process_wallet_async(mnemonic_list, logger, file_name):
    """Process wallets asynchronously."""
    async with aiohttp.ClientSession() as session:
        for seed in mnemonic_list:
            for coin in SUPPORTED_COINS:
                address = derive_wallet_address(seed, coin)
                balance = await check_balance_async(session, address, coin)
                logger.info(f"Seed: {seed}")
                logger.info(f"{coin} Address: {address}")
                logger.info(f"{coin} Balance: {balance}")
                if balance > 0:
                    logger.info(f"(!) Wallet with balance found for {coin}!")
                    write_to_file(file_name, seed, coin, address, balance)

def generate_mnemonics(words_num, count):
    """Generate a list of mnemonics."""
    return [generate_mnemonic(words_num) for _ in range(count)]

async def main_async():
    """Main asynchronous function to initialize the wallet scanner."""
    logging.info("Starting wallet scanner...")
    mnemonics_12 = generate_mnemonics(Bip39WordsNum.WORDS_NUM_12, NUM_WALLETS)
    mnemonics_24 = generate_mnemonics(Bip39WordsNum.WORDS_NUM_24, NUM_WALLETS)
    tasks = [
        asyncio.create_task(process_wallet_async(mnemonics_12, logging.getLogger("Logger12"), WALLETS_FILE_NAME_12)),
        asyncio.create_task(process_wallet_async(mnemonics_24, logging.getLogger("Logger24"), WALLETS_FILE_NAME_24)),
    ]
    await asyncio.gather(*tasks)
    logging.info("Wallet scanner completed.")

if __name__ == "__main__":
    asyncio.run(main_async())
