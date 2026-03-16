import telebot
import threading
import random
import time
import os
import requests
import pickle
import re
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================================
# CONFIGURATION & GLOBALS
# ==========================================================
# Ganti dengan token dari BotFather jika ingin tes lokal, 
# atau gunakan os.getenv("TELEGRAM_TOKEN") jika memakai Railway variables.
TOKEN = "8690723145:AAGcxuiWN7ZHHZFPRwQZhkxIJ8bnIDse6HI"

if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN environment variable not set.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Shared State
CONFIG = {
    "target_web": "",
    "keywords": [],
    "emails": [], # Added for Telegram control
    "is_running": False
}

STOP_EVENT = threading.Event()
FILE_LOCK = threading.Lock()
COOKIE_DIR = "sentinel_cookies"

if not os.path.exists(COOKIE_DIR):
    os.makedirs(COOKIE_DIR)

# ==========================================================
# BOT ENGINE LOGIC (Optimized for Headless Cloud)
# ==========================================================

def load_list(file):
    try:
        if not os.path.exists(file): return []
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except: return []

def remove_from_list(file_path, target_line):
    with FILE_LOCK:
        try:
            if not os.path.exists(file_path): return
            lines = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            with open(file_path, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.strip() != target_line.strip():
                        f.write(line)
        except: pass

def get_domain(url):
    return urlparse(url).netloc.replace(".", "_")

def save_cookies(driver, url):
    try:
        domain = get_domain(url)
        path = os.path.join(COOKIE_DIR, f"{domain}.pkl")
        with open(path, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
    except: pass

def load_cookies(driver, url):
    try:
        domain = get_domain(url)
        path = os.path.join(COOKIE_DIR, f"{domain}.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
            return True
    except: pass
    return False

def solve_math(driver):
    try:
        page_text = driver.page_source
        match = re.search(r'(\d+)\s*([\+\-\*])\s*(\d+)\s*=', page_text)
        if match:
            num1, op, num2 = int(match.group(1)), match.group(2), int(match.group(3))
            res = num1 + num2 if op == '+' else num1 - num2 if op == '-' else num1 * num2
            caps = driver.find_elements(By.XPATH, "//input[contains(@name, 'captcha') or contains(@id, 'captcha') or contains(@name, 'sum')]")
            if caps: caps[0].send_keys(str(res)); return True
    except: pass
    return False

def ghost_behavior(driver):
    try:
        height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(random.randint(2, 3)):
            target = random.randint(100, min(height, 2000))
            driver.execute_script(f"window.scrollTo({{top: {target}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.5, 1.5))
        time.sleep(random.uniform(1, 2))
    except: pass

def turbine_precheck(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        return response.status_code == 200 and ('<form' in response.text.lower() or 'textarea' in response.text.lower())
    except: return False

def get_driver(timeout=30):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = "eager"
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={ua}")
    
    # In Linux/Railway, Chrome is usually at /usr/bin/google-chrome
    if os.path.exists("/usr/bin/google-chrome"):
        options.binary_location = "/usr/bin/google-chrome"
        
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.webp", "*.mp4", "*.css*"]})
    driver.execute_cdp_cmd("Network.enable", {})
    driver.set_page_load_timeout(timeout)
    return driver

# ==========================================================
# TELEGRAM COMMAND HANDLERS
# ==========================================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "🔥 **4NOMALI CLOUD ENGINE v13.0** 🔥\n\n"
        "Control Commands:\n"
        "/web <url> - Set target website\n"
        "/keyword <nama1, nama2, nama3> - Set names\n"
        "/email <email1, email2> - Set email pool\n"
        "/gas - Start engine (using list.txt on server)\n"
        "/stop - Emergency abort\n"
        "/status - Check current configuration\n\n"
        "Ready for deployment on Railway."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['web'])
def set_web(message):
    try:
        url = message.text.split(" ", 1)[1].strip()
        if not url.startswith("http"):
            bot.reply_to(message, "❌ URL harus diawali http/https")
            return
        CONFIG["target_web"] = url
        bot.reply_to(message, f"✅ Target Web Set to: {url}")
    except:
        bot.reply_to(message, "❌ Format salah. Contoh: /web https://google.com")

@bot.message_handler(commands=['keyword'])
def set_keyword(message):
    try:
        keywords = [k.strip() for k in message.text.split(" ", 1)[1].split(",")]
        CONFIG["keywords"] = keywords
        bot.reply_to(message, f"✅ Identity Pool Updated: {', '.join(keywords)}")
    except:
        bot.reply_to(message, "❌ Format salah. Contoh: /keyword Agus, Yanto, Budi")

@bot.message_handler(commands=['email'])
def set_email(message):
    try:
        emails = [e.strip() for e in message.text.split(" ", 1)[1].split(",")]
        CONFIG["emails"] = emails
        bot.reply_to(message, f"✅ Email Pool Updated: {', '.join(emails)}")
    except:
        bot.reply_to(message, "❌ Format salah. Contoh: /email bot1@mail.com, bot2@mail.com")

@bot.message_handler(commands=['status'])
def show_status(message):
    status = (
        "📊 **CURRENT CONFIG**\n"
        f"Web: {CONFIG['target_web'] or '❌ Not Set'}\n"
        f"Names: {', '.join(CONFIG['keywords']) or '❌ Not Set'}\n"
        f"Emails: {', '.join(CONFIG['emails']) or '❌ Not Set'}\n"
        f"Running: {'🟢 ACTIVE' if CONFIG['is_running'] else '🔴 IDLE'}"
    )
    bot.reply_to(message, status, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_engine(message):
    STOP_EVENT.set()
    bot.reply_to(message, "🛑 Abort signal sent. System will stop after current URL.")

@bot.message_handler(commands=['gas'])
def run_engine(message):
    if CONFIG["is_running"]:
        bot.reply_to(message, "⚠️ Engine is already running!")
        return
    
    if not CONFIG["target_web"] or not CONFIG["keywords"] or not CONFIG["emails"]:
        bot.reply_to(message, "❌ Konfigurasi belum lengkap! Atur /web, /keyword, dan /email dulu.")
        return

    CONFIG["is_running"] = True
    STOP_EVENT.clear()
    bot.reply_to(message, "🚀 **MISSION STARTED**\nInitializing 4NOMALI engine on cloud server...")
    
    threading.Thread(target=threaded_run, args=(message.chat.id,)).start()

def threaded_run(chat_id):
    stats = {"success": 0, "failed": 0, "skipped": 0}
    targets = load_list("list.txt")
    comments = load_list("komen.txt")
    
    if not targets:
        bot.send_message(chat_id, "❌ Error: list.txt tidak ditemukan atau kosong di server.")
        CONFIG["is_running"] = False
        return

    driver = None
    try:
        driver = get_driver()
        for target in targets:
            if STOP_EVENT.is_set(): break
            
            if not turbine_precheck(target):
                stats["skipped"] += 1
                remove_from_list("list.txt", target)
                continue
            
            try:
                driver.get(target)
                load_cookies(driver, target)
                ghost_behavior(driver)
                solve_math(driver)
                
                # Form filling logic
                nick = random.choice(CONFIG["keywords"])
                mail = random.choice(CONFIG["emails"])
                site = CONFIG["target_web"]
                comment = random.choice(comments) if comments else "Nice article!"
                
                # Simplified smart find (no logging to avoid telegram overhead)
                box = None
                for p in ["//textarea[contains(@id, 'comment')]", "//textarea[contains(@name, 'comment')]", "//textarea"]:
                    try:
                        el = driver.find_element(By.XPATH, p)
                        if el.is_displayed(): box = el; break
                    except: continue
                
                if box:
                    for w in ["author", "name"]:
                        try: driver.find_element(By.XPATH, f"//input[contains(@id, '{w}') or contains(@name, '{w}')]").send_keys(nick); break
                        except: pass
                    for w in ["email", "mail"]:
                        try: driver.find_element(By.XPATH, f"//input[contains(@id, '{w}') or contains(@name, '{w}')]").send_keys(mail); break
                        except: pass
                    for w in ["url", "website"]:
                        try: driver.find_element(By.XPATH, f"//input[contains(@id, '{w}') or contains(@name, '{w}')]").send_keys(site); break
                        except: pass
                    
                    box.send_keys(comment)
                    
                    submit = None
                    for p in ["//input[@type='submit']", "//button[@type='submit']", "//*[contains(@id, 'submit')]"]:
                        try:
                            el = driver.find_element(By.XPATH, p)
                            if el.is_displayed(): submit = el; break
                        except: continue
                    
                    if submit:
                        driver.execute_script("arguments[0].click();", submit)
                        driver.execute_script("window.stop();")
                        save_cookies(driver, target)
                        stats["success"] += 1
                    else: stats["failed"] += 1
                else:
                    stats["skipped"] += 1
                    remove_from_list("list.txt", target)
            except: stats["failed"] += 1
            
    finally:
        if driver: driver.quit()
        CONFIG["is_running"] = False
        
        final_msg = (
            "🏁 **MISSION COMPLETE 4NOMALI**\n"
            "----------------------------\n"
            f"✅ SUCCESS : {stats['success']}\n"
            f"❌ FAILED  : {stats['failed']}\n"
            f"⏭️ SKIPPED : {stats['skipped']}\n"
            "----------------------------\n"
            "Cloud instance idle. Over and out."
        )
        bot.send_message(chat_id, final_msg, parse_mode="Markdown")

if __name__ == "__main__":
    print("4NOMALI Telegram Bot Started...")
    bot.infinity_polling()
