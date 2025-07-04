import os
import requests
import time
import threading
import io
from datetime import datetime
from collections import deque
from telegram import Bot
from telegram.ext import Updater, CommandHandler
import matplotlib.pyplot as plt
from http.server import HTTPServer, BaseHTTPRequestHandler

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Initialize bot and state
bot = Bot(token=TELEGRAM_TOKEN)
# Immediately remove any existing webhook to avoid conflicts
bot.delete_webhook(drop_pending_updates=True)
watchlist = {}

# Command handlers
def help_cmd(update, context):
    return start_cmd(update, context)

def start_cmd(update, context):
    update.message.reply_text(
        """👋 *Chào mừng bạn đến với bot theo dõi token Solana!*  

🔻 `/down <pair> <price>` – Cảnh báo khi giá *giảm xuống dưới* mức chỉ định
🟢 `/up <pair> <price>` – Cảnh báo khi giá *tăng lên trên* mức chỉ định
❌ `/remove <pair>` – Gỡ token khỏi danh sách theo dõi
📋 `/list` – Danh sách tất cả các token đang được theo dõi
📈 `/chart <pair>` – Gửi biểu đồ biến động 60 mẫu gần nhất
💹 `/price <pair>` – Xem nhanh giá & vốn hóa hiện tại
🧪 `/scan` – Quét nhanh top token mới nhất
📊 `/topcap` – Top token có FDV cao nhất

🧪 *Ví dụ sử dụng:*
`/down 5kFuc... 0.0026`
`/up 5kFuc... 0.0030`
`/price 5kFuc...`""",
        parse_mode='Markdown'
    )

# Fetch token information from Dexscreener
def get_token_info(pair_addr):
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_addr}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json().get("pair", {})
        name = data.get("baseToken", {}).get("name", "Unknown")
        symbol = data.get("baseToken", {}).get("symbol", "")
        price = float(data.get("priceUsd", 0))
        cap = float(data.get("fdv", 0))
        logo = data.get("baseToken", {}).get("iconUrl")
        return name, symbol, price, cap, logo
    except Exception as e:
        print("⚠️ Error fetching token info:", e)
        return None, None, None, None, None

# Get latest token addresses (convert token profiles to pair addresses)
def get_latest_pairs(limit=5):
    """Return list of pair addresses for newest tokens on Solana."""
    profiles_url = "https://api.dexscreener.com/token-profiles/latest/v1"
    pairs = []
    try:
        resp = requests.get(profiles_url, timeout=10)
        profiles = resp.json()
        for entry in profiles:
            if entry.get("chainId") == "solana":
                token_addr = entry.get("tokenAddress")
                # fetch pools for this token
                pools_url = f"https://api.dexscreener.com/token-pairs/v1/solana/{token_addr}"
                pr = requests.get(pools_url, timeout=10).json()
                if isinstance(pr, list) and pr:
                    # take first pool's pairAddress
                    pair_addr = pr[0].get("pairAddress")
                    if pair_addr:
                        pairs.append(pair_addr)
                if len(pairs) >= limit:
                    break
        return pairs[:limit]
    except Exception as e:
        print("⚠️ Error fetching latest pairs:", e)
        return []

# /scan command
def scan_latest_cmd(update, context):
    pairs = get_latest_pairs()
    if not pairs:
        return update.message.reply_text("❌ Không tìm thấy pair nào mới.")
    lines = []
    for i, addr in enumerate(pairs, start=1):
        name, symbol, price, cap, logo = get_token_info(addr)
        if price is not None:
            if logo:
                bot.send_photo(chat_id=update.message.chat_id, photo=logo)
            lines.append(
                f"{i}. `{addr}` – *{name}* (${symbol}): `${price:.6f}` | FDV: ${cap/1e6:.2f}M\n"
                f"➡️ /down {addr} <price> hoặc /up {addr} <price>"
            )
    update.message.reply_text(
        "*🆕 Top 5 token mới trên Solana:*\n" + "\n".join(lines),
        parse_mode='Markdown'
    )

# /down command
def down_cmd(update, context):
    if len(context.args) != 2:
        return update.message.reply_text("❗ Cú pháp: `/down <pair> <price>`", parse_mode='Markdown')
    addr, th = context.args
    try:
        threshold = float(th)
    except:
        return update.message.reply_text("❗ Giá phải là số.", parse_mode='Markdown')
    name, symbol, price, cap, logo = get_token_info(addr)
    if price is None:
        return update.message.reply_text("❌ Không lấy được dữ liệu.", parse_mode='Markdown')
    entry = watchlist.setdefault(addr, {'history': deque()})
    entry['threshold'] = threshold
    entry['history'].append((datetime.now().strftime('%H:%M'), price))
    pct = (price - threshold) / threshold * 100
    if logo:
        bot.send_photo(chat_id=update.message.chat_id, photo=logo)
    update.message.reply_text(
        f"🔻 *DOWN ALERT*\n"
        f"[🪙 {name} (${symbol})]\n"
        f"`{addr}`\n\n"
        f"💰 *Price:* `${price:.6f}` ({pct:.0f}%)\n"
        f"📍 *Alert Trigger:* `$≤{threshold}`\n"
        f"💵 *FDV:* `${cap/1e6:.2f}M`",
        parse_mode='Markdown'
    )

# /up command
def up_cmd(update, context):
    if len(context.args) != 2:
        return update.message.reply_text("❗ Cú pháp: `/up <pair> <price>`", parse_mode='Markdown')
    addr, th = context.args
    try:
        eq = float(th)
    except:
        return update.message.reply_text("❗ Giá phải là số.", parse_mode='Markdown')
    name, symbol, price, cap, logo = get_token_info(addr)
    if price is None:
        return update.message.reply_text("❌ Không lấy được dữ liệu.", parse_mode='Markdown')
    entry = watchlist.setdefault(addr, {'history': deque()})
    entry['eq_price'] = eq
    entry['history'].append((datetime.now().strftime('%H:%M'), price))
    pct = (price - eq) / eq * 100
    if logo:
        bot.send_photo(chat_id=update.message.chat_id, photo=logo)
    update.message.reply_text(
        f"🟢 *UP ALERT*\n"
        f"[🪙 {name} (${symbol})]\n"
        f"`{addr}`\n\n"
        f"💰 *Price:* `${price:.6f}` ({pct:+.0f}%)\n"
        f"📍 *Alert Trigger:* `$≈{eq}`\n"
        f"💵 *FDV:* `${cap/1e6:.2f}M`",
        parse_mode='Markdown'
    )

# /topcap command
def topcap_cmd(update, context):
    pairs = get_latest_pairs(limit=10)
    tokens = []
    for addr in pairs:
        name, symbol, price, cap, _ = get_token_info(addr)
        if cap and price:
            tokens.append((cap, addr, name, symbol, price))
    tokens.sort(reverse=True)
    lines = [
        f"{i+1}. `{addr}` – *{name}* (${symbol}): `${price:.6f}` | FDV: ${cap/1e6:.2f}M"
        for i, (cap, addr, name, symbol, price) in enumerate(tokens[:5])
    ]
    update.message.reply_text(
        "🏆 *Top FDV Tokens:*\n" + "\n".join(lines),
        parse_mode='Markdown'
    )

# /remove command
def remove_cmd(update, context):
    if not context.args:
        return update.message.reply_text("❗ Cú pháp: `/remove <pair>`", parse_mode='Markdown')
    addr = context.args[0]
    if addr in watchlist:
        del watchlist[addr]
        update.message.reply_text(f"🗑 Đã gỡ `{addr}` khỏi danh sách theo dõi.", parse_mode='Markdown')
    else:
        update.message.reply_text(f"⚠️ Không tìm thấy `{addr}` trong danh sách theo dõi.", parse_mode='Markdown')

# /list command
def list_cmd(update, context):
    if not watchlist:
        return update.message.reply_text("📭 Chưa theo dõi token nào.")
    lines = []
    for i, (addr, info) in enumerate(watchlist.items(), start=1):
        parts = [f"{i}. `{addr}`"]
        if 'threshold' in info:
            parts.append(f"🔻≤${info['threshold']}")
        if 'eq_price' in info:
            parts.append(f"🟢≈${info['eq_price']}")
        lines.append(" | ".join(parts))
    update.message.reply_text(
        "📋 *Danh sách theo dõi:*\n" + "\n".join(lines),
        parse_mode='Markdown'
    )

# /price command
def price_cmd(update, context):
    if not context.args:
        return update.message.reply_text("❗ Cú pháp: `/price <pair>`", parse_mode='Markdown')
    addr = context.args[0]
    name, symbol, price, cap, logo = get_token_info(addr)
    if price is None:
        return update.message.reply_text("❌ Không lấy được dữ liệu.", parse_mode='Markdown')
    if logo:
        bot.send_photo(chat_id=update.message.chat_id, photo=logo)
    update.message.reply_text(
        f"💹 *Token:* {name} (${symbol})\n🔗 `{addr}`\n\n💰 *Price:* `${price:.6f}`\n💵 *FDV:* `${cap/1e6:.2f}M`",
        parse_mode='Markdown'
    )

# /chart command
def chart_cmd(update, context):
    if not context.args:
        return update.message.reply_text("❗ Cú pháp: `/chart <pair>`", parse_mode='Markdown')
    addr = context.args[0]
    info = watchlist.get(addr)
    if not info or not info['history']:
        return update.message.reply_text("❌ Chưa có dữ liệu. Hãy `/down` rồi chờ 1 phút.", parse_mode='Markdown')
    times = [t for t, _ in info['history']]
    prices = [p for _, p in info['history']]
    plt.figure(figsize=(6,3))
    plt.plot(times, prices, marker='o', linewidth=2)
    plt.xticks(rotation=45, fontsize=8); plt.yticks(fontsize=8)
    plt.xlabel('🕒 Thời gian', fontsize=9); plt.ylabel('💲 Giá (USD)', fontsize=9)
    plt.title(f'📈 Biểu đồ: {addr}', fontsize=10); plt.tight_layout()
    buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0); plt.close()
    update.message.reply_photo(photo=buf, caption=f"🔍 Biểu đồ 60 mẫu `{addr}`", parse_mode='Markdown')

# Setup Telegram handlers
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
for cmd, fn in [
    ("start", start_cmd), ("help", help_cmd),
    ("scan", scan_latest_cmd), ("down", down_cmd), ("up", up_cmd),
    ("remove", remove_cmd), ("list", list_cmd),
    ("chart", chart_cmd), ("price", price_cmd), ("topcap", topcap_cmd),
]:
    dp.add_handler(CommandHandler(cmd, fn))

if __name__ == "__main__":
    # Remove any existing webhook to prevent getUpdates conflict
    updater.bot.delete_webhook()
    # Start polling and HTTP health-check server
    # Start polling and HTTP health-check server
    updater.start_polling(drop_pending_updates=True)
    print("🤖 Bot đã sẵn sàng — /down, /up, /remove, /list, /chart, /price, /scan, /topcap")

    # Health-check HTTP server for Render
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    port = int(os.getenv("PORT", "8000"))
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever(),
        daemon=True
    ).start()

    updater.idle()
