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
from telegram.utils.request import Request
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Custom request class with retry logic
class CustomRequest(Request):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# Initialize bot and state
request = CustomRequest()
bot = Bot(token=TELEGRAM_TOKEN, request=request)
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

# Import and assign other command functions here
from commands import (
    get_token_info, get_latest_pairs,
    scan_latest_cmd, down_cmd, up_cmd,
    remove_cmd, list_cmd, price_cmd,
    chart_cmd, topcap_cmd
)

# Setup Telegram handlers
updater = Updater(bot=bot, use_context=True)
dp = updater.dispatcher
for cmd, fn in [
    ("start", start_cmd), ("help", help_cmd),
    ("scan", scan_latest_cmd), ("down", down_cmd), ("up", up_cmd),
    ("remove", remove_cmd), ("list", list_cmd),
    ("chart", chart_cmd), ("price", price_cmd), ("topcap", topcap_cmd),
]:
    dp.add_handler(CommandHandler(cmd, fn))

if __name__ == "__main__":
    updater.bot.delete_webhook()
    updater.start_polling(drop_pending_updates=True)
    print("🤖 Bot đã sẵn sàng — /down, /up, /remove, /list, /chart, /price, /scan, /topcap")

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
