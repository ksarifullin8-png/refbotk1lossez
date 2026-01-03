from flask import Flask
from threading import Thread
import time
import logging

app = Flask('')

@app.route('/')
def home():
    return "🤖 Бот активен! | " + time.strftime("%Y-%m-%d %H:%M:%S")

@app.route('/health')
def health():
    return "OK", 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """
    Запускает веб-сервер в отдельном потоке
    для поддержания активности бота
    """
    logger = logging.getLogger(__name__)
    logger.info("Запуск keep-alive сервера...")
    
    t = Thread(target=run)
    t.daemon = True
    t.start()
    return t
