import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sys

# File Path
DATA_FILE = "domain_data.json"
CHECK_INTERVAL = 600  # 10 menit

# =====================
# HELPER & NORMALIZER
# =====================
def is_group(update: Update):
    """Filter agar bot hanya respon di Grup"""
    return update.effective_chat.type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]

def normalize_domain(input_domain):
    input_domain = input_domain.strip()
    if not input_domain.startswith("http"):
        request_url = "https://" + input_domain
    else:
        request_url = input_domain
    parsed = urlparse(request_url)
    return request_url, parsed.netloc

def get_display_url(url):
    if not url: return "-"
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}"

# =====================
# FILE HANDLER
# =====================
def load_data():
    try:
        with open(DATA_FILE, "r") as f: return json.load(f)
    except: return {}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=2)

# =====================
# AMP CHECKER
# =====================
async def get_amp_url(domain):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(domain, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                amp = soup.find("link", rel="amphtml")
                return amp["href"] if amp else None
    except: return None

# =====================
# COMMANDS (ALL FEATURES INCLUDED)
# =====================

async def tambah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    if not context.args:
        await update.message.reply_text("Gunakan: /tambah example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    chat_id = update.effective_chat.id
    user = update.effective_user # Ambil info pengirim
    
    amp_url = await get_amp_url(request_url)
    data = load_data()
    
    data[request_url] = {
        "initial_amp": amp_url,
        "current_amp": amp_url,
        "last_checked": str(datetime.now()),
        "chat_id": chat_id,
        "added_by_id": user.id,        # SIMPAN ID PENGIRIM
        "added_by_name": user.first_name, 
        "change_notified_count": 0
    }
    save_data(data)

    await update.message.reply_text(
        "✅ *DOMAIN DITAMBAHKAN*\n"
        "────────────────────\n"
        f"🌐 Domain  : `{get_display_url(request_url)}`\n"
        f"🔎 AMP Awal : `{get_display_url(amp_url)}`\n"
        f"👤 Petugas : [{user.first_name}](tg://user?id={user.id})\n"
        "────────────────────",
        parse_mode="Markdown", disable_web_page_preview=True
    )

async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    if not context.args:
        await update.message.reply_text("Gunakan: /hapus example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    data = load_data()

    if request_url in data:
        del data[request_url]
        save_data(data)
        await update.message.reply_text(f"🗑 *DOMAIN DIHAPUS*\n`{get_display_url(request_url)}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠ Domain tidak ditemukan")

async def list_domains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    data = load_data()
    domains = [d for d, info in data.items() if info.get("chat_id") == chat_id]

    if not domains:
        await update.message.reply_text("Belum ada domain tersimpan di grup ini.")
        return

    msg = ["📋 *DAFTAR MONITORING GRUP*\n"]
    for d in domains:
        info = data[d]
        msg.append(f"────────────────────\n🌐 `{get_display_url(d)}`\n• AMP Sekarang : `{get_display_url(info.get('current_amp'))}`")

    await update.message.reply_text("\n".join(msg), parse_mode="Markdown", disable_web_page_preview=True)

async def cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    if not context.args:
        await update.message.reply_text("Gunakan: /cek example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    amp = await get_amp_url(request_url)
    await update.message.reply_text(f"🔎 *HASIL CEK*\nDomain: `{get_display_url(request_url)}`\nAMP: `{get_display_url(amp)}`", parse_mode="Markdown")

async def update_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update otomatis semua atau spesifik domain"""
    if not is_group(update): return
    chat_id = update.effective_chat.id
    data = load_data()
    
    if context.args:
        req_url, _ = normalize_domain(context.args[0])
        if req_url in data and data[req_url].get("chat_id") == chat_id:
            new_amp = await get_amp_url(req_url)
            data[req_url].update({
                "current_amp": new_amp,
                "initial_amp": new_amp, # Reset patokan
                "last_checked": str(datetime.now()),
                "change_notified_count": 0
            })
            save_data(data)
            await update.message.reply_text(f"✅ Update Sukses: `{get_display_url(req_url)}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠ Domain tidak ditemukan.")
    else:
        targets = [d for d, info in data.items() if info.get("chat_id") == chat_id]
        for d in targets:
            new_amp = await get_amp_url(d)
            data[d].update({"current_amp": new_amp, "initial_amp": new_amp, "change_notified_count": 0})
        save_data(data)
        await update.message.reply_text("✅ Semua data AMP grup disinkronkan.", parse_mode="Markdown")

# =====================
# PERIODIC CHECK (WITH AUTO-TAG)
# =====================
async def periodic_check(app):
    await asyncio.sleep(10)
    while True:
        data = load_data()
        updated = False
        for domain, info in data.items():
            new_amp = await get_amp_url(domain)
            
            # Cek jika berubah dari patokan awal (initial_amp)
            if new_amp != info.get("initial_amp") and info.get("change_notified_count", 0) < 3:
                user_id = info.get("added_by_id")
                # Tag "Ghaib" di spasi transparan agar HP bunyi tapi gak ngerusak teks
                tag_hidden = f"[\u200b](tg://user?id={user_id})" if user_id else ""
                
                try:
                    await app.bot.send_message(
                        chat_id=info["chat_id"],
                        text=(
                            f"🚨 *AMP BERUBAH TERDETEKSI* {tag_hidden}\n"
                            "────────────────────\n"
                            f"🌐 Domain : `{get_display_url(domain)}`\n"
                            f"⚠ AMP Baru: `{get_display_url(new_amp)}`\n"
                            f"🔔 Notif  : {info.get('change_notified_count', 0) + 1}/3\n"
                            "────────────────────\n"
                            f"CC: [Petugas](tg://user?id={user_id})"
                        ),
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                    data[domain]["change_notified_count"] = info.get("change_notified_count", 0) + 1
                    data[domain]["current_amp"] = new_amp # Catat perubahan sekarang
                    updated = True
                except: pass

            # Jika kembali normal
            if new_amp == info.get("initial_amp") and info.get("current_amp") != info.get("initial_amp"):
                try:
                    await app.bot.send_message(
                        chat_id=info["chat_id"],
                        text=f"✅ *AMP KEMBALI NORMAL*\n🌐 `{get_display_url(domain)}`",
                        parse_mode="Markdown"
                    )
                    data[domain]["change_notified_count"] = 0
                    data[domain]["current_amp"] = new_amp
                    updated = True
                except: pass

        if updated: save_data(data)
        await asyncio.sleep(CHECK_INTERVAL)

# =====================
# MAIN
# =====================
def main():
    # TOKEN BOT LU
    app = ApplicationBuilder().token("7779977084:AAFBkRL6TCzL1WMcyh5eM9S2BjVmYvwhqdc").build()

    app.add_handler(CommandHandler("tambah", tambah))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(CommandHandler("list", list_domains))
    app.add_handler(CommandHandler("cek", cek))
    app.add_handler(CommandHandler("update", update_manual))

    async def startup(application):
        application.create_task(periodic_check(application))

    app.post_init = startup
    app.run_polling()

if __name__ == "__main__":
    main()
