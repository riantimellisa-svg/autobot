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
    "emails": [],
    "threads": 1,
    "is_running": False,
    "current_stats": {"success": 0, "failed": 0, "skipped": 0, "total": 0, "processed": 0},
    "last_error": "" # Diagnostic field
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
    options.add_argument("--window-size=1920,1080") # Set standard size
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = "normal" # More robust than eager
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
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
        "/keyword <name1, name2> - Set names\n"
        "/email <email1, email2> - Set emails\n"
        "/threads <num> - Set parallel workers (1-3 recommended for 1GB RAM)\n"
        "/gas - Start engine\n"
        "/stop - Emergency abort\n"
        "/status - Check configuration\n\n"
        "Optimization: 4NOMALI Cloud is ready."
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

@bot.message_handler(commands=['threads'])
def set_threads(message):
    try:
        num = int(message.text.split(" ", 1)[1].strip())
        if 1 <= num <= 5:
            CONFIG["threads"] = num
            bot.reply_to(message, f"✅ Thread Pool Set to: {num}\n⚠️ Note: 2 vCPU & 1GB RAM optimal at 2-3 threads.")
        else:
            bot.reply_to(message, "❌ Pilih antara 1 sampai 5 thread saja bosku (ingat RAM 1GB).")
    except:
        bot.reply_to(message, "❌ Format salah. Contoh: /threads 2")

@bot.message_handler(commands=['status'])
def show_status(message):
    status = "📊 **4NOMALI STATUS REPORT**\n----------------------------\n"
    status += f"Web: `{CONFIG['target_web'] or '❌ Not Set'}`\n"
    status += f"Names: `{len(CONFIG['keywords'])} loaded`\n"
    status += f"Emails: `{len(CONFIG['emails'])} loaded`\n"
    status += f"Workers: `{CONFIG['threads']} Threads`\n"
    
    if CONFIG["is_running"]:
        s = CONFIG["current_stats"]
        perc = (s["processed"] / s["total"] * 100) if s["total"] > 0 else 0
        status += f"\n🟢 **MISSION ACTIVE ({perc:.1f}%)**\n"
        status += f"✅ Success: `{s['success']}`\n"
        status += f"❌ Failed: `{s['failed']}`\n"
        status += f"⏭️ Skipped: `{s['skipped']}`\n"
        status += f"📦 Processed: `{s['processed']}/{s['total']}`"
        if CONFIG["last_error"]:
            status += f"\n\n⚠️ **LAST ERROR:**\n`{CONFIG['last_error']}`"
    else:
        status += "\n🔴 **SYSTEM IDLE**\nReady for next mission."
    
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
    
    targets = load_list("list.txt")
    if not targets:
        bot.reply_to(message, "❌ Error: list.txt kosong atau tidak ada.")
        CONFIG["is_running"] = False
        return

    # Reset & Init Stats
    CONFIG["current_stats"] = {
        "success": 0, "failed": 0, "skipped": 0, 
        "total": len(targets), "processed": 0, "done_threads": 0
    }
    
    bot.reply_to(message, f"🚀 **MISSION STARTED**\nTarget: {len(targets)} URLs\nWorkers: {CONFIG['threads']} Threads")
    
    num_threads = CONFIG["threads"]
    chunks = [targets[i::num_threads] for i in range(num_threads)]
    lock = threading.Lock()

    def thread_callback():
        with lock:
            CONFIG["current_stats"]["done_threads"] += 1
            if CONFIG["current_stats"]["done_threads"] == num_threads:
                final_report(message.chat.id, CONFIG["current_stats"])

    for chunk in chunks:
        if not chunk: 
            thread_callback()
            continue
        threading.Thread(target=threaded_run, args=(message.chat.id, chunk, lock, thread_callback)).start()

def final_report(chat_id, stats):
    CONFIG["is_running"] = False
    final_msg = (
        "🏁 **MISSION COMPLETE 4NOMALI**\n"
        "----------------------------\n"
        f"✅ SUCCESS : {stats['success']}\n"
        f"❌ FAILED  : {stats['failed']}\n"
        f"⏭️ SKIPPED : {stats['skipped']}\n"
        "----------------------------\n"
        "All threads joined. System Standby."
    )
    bot.send_message(chat_id, final_msg, parse_mode="Markdown")

def threaded_run(chat_id, chunk, lock, callback):
    emails = CONFIG["emails"]
    comments = load_list("komen.txt")
    driver = None
    try:
        driver = get_driver()
        for target in chunk:
            if STOP_EVENT.is_set(): break
            
            if not turbine_precheck(target):
                with lock: 
                    CONFIG["current_stats"]["skipped"] += 1
                    CONFIG["current_stats"]["processed"] += 1
                remove_from_list("list.txt", target)
                continue
            
            try:
                driver.get(target)
                load_cookies(driver, target)
                ghost_behavior(driver)
                solve_math(driver)
                
                nick = random.choice(CONFIG["keywords"])
                mail = random.choice(emails)
                site = CONFIG["target_web"]
                comment = random.choice(comments) if comments else "Nice article!"
                
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
                        with lock: CONFIG["current_stats"]["success"] += 1
                else: 
                    with lock: 
                        CONFIG["current_stats"]["failed"] += 1
                        CONFIG["last_error"] = "Form not found or hidden"
            except Exception as e: 
                with lock: 
                    CONFIG["current_stats"]["failed"] += 1
                    CONFIG["last_error"] = str(e)[:100]
            
            with lock: CONFIG["current_stats"]["processed"] += 1
    finally:
        if driver: driver.quit()
        callback()

if __name__ == "__main__":
    print("4NOMALI Telegram Bot Started...")
    bot.infinity_polling()
