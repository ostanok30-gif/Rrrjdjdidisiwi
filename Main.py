#!/usr/bin/env python3
"""
Telegram Физ-Шоп v17.0 - ПОЛНАЯ ВЕРСИЯ
- WebApp с падающими звёздами
- Интеграция с LolzTeam Market
- Авто-проверка аккаунтов
- Наценка 3% (минимум 50₽)
- Пополнение через Stars и Crypto Bot

Запуск: python3 shop.py
"""

import asyncio
import logging
import os
import re
import hashlib
import sqlite3
import json
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    FloodWaitError,
    RPCError
)
import phonenumbers

# ==================== КОНФИГ ====================
BOT_TOKEN = "572563:AA3hmr9NaieDjw50EYp6RjoyMJe2SL7cCFW"
ADMIN_IDS = [8640180536]
API_ID = 34928216
API_HASH = "29f66350a892e8b69a83b50d7e99bd27"
MANAGER_USERNAME = "oxatov"

# LolzTeam API
LOLZTEAM_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWIiOjk5MzQ3MTcsImlzcyI6Imx6dCIsImlhdCI6MTc4MDE5MzAyOCwianRpIjoiOTgwODQ0Iiwic2NvcGUiOiJiYXNpYyByZWFkIHBvc3QgY29udmVyc2F0ZSBwYXltZW50IGludm9pY2UgY2hhdGJveCBtYXJrZXQiLCJleHAiOjE5Mzc4NzMwMjh9.v3JT_IICmM9DDaEYPDAu50ZfkeK1MFOPHNjb2RtDCuD_6XSmyIHlXdSAbbpc-NHH58yEqyZxWKdGmBWLslfepg7Ecmjnw1IbbA96-mUlj1d24UHapR6YS386tdvohhZGgSntPvmFus0h8fpJxacsC7TEqU4-HEPNTiK1mmT2-1o"
LOLZTEAM_API_URL = "https://api.zelenka.guru"

# Crypto Bot
CRYPTO_BOT_TOKEN = "572563:AA3hmr9NaieDjw50EYp6RjoyMJe2SL7cCFW"
CRYPTO_BOT_API = "https://pay.crypt.bot/api"

# Настройки
MIN_DEPOSIT = 50
MAX_DEPOSIT = 50000
MARKUP_PERCENT = 3
MIN_ACCOUNT_PRICE = 50
MIN_STOCK = 5

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_client = None
user_states = {}
temp_clients = {}
pending_pages = {}

# ==================== БАЗА ДАННЫХ ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect("shop.db", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                username TEXT,
                first_name TEXT,
                total_bought INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                level TEXT DEFAULT 'Новичок',
                discount REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lolz_item_id INTEGER,
                lolz_thread_id INTEGER,
                session_string TEXT,
                phone TEXT,
                country TEXT,
                age_days INTEGER DEFAULT 0,
                price REAL NOT NULL,
                original_price REAL NOT NULL,
                status TEXT DEFAULT 'available',
                buyer_id INTEGER,
                sold_at TEXT,
                is_valid INTEGER DEFAULT 1,
                last_check TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                account_id INTEGER,
                amount REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_invoices (
                invoice_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount_rub REAL,
                status TEXT DEFAULT 'pending',
                pay_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS star_deposits (
                gift_id TEXT PRIMARY KEY,
                user_id INTEGER,
                stars_count INTEGER,
                from_id INTEGER,
                processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS stars_receiver (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                session_string TEXT,
                phone TEXT,
                username TEXT,
                has_2fa INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS lolz_sync (
                id INTEGER PRIMARY KEY,
                thread_id INTEGER,
                last_sync TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        self.conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('stars_rate', '1.0')")
        self.conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('markup_percent', '3')")
        self.conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_price', '50')")
        self.conn.commit()
    
    def add_user(self, user_id, username=None, first_name=None):
        self.conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))
        self.conn.commit()
    
    def get_balance(self, user_id):
        row = self.conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row['balance'] if row else 0
    
    def add_balance(self, user_id, amount):
        self.conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
    
    def get_available_accounts(self, limit=50):
        return self.conn.execute("SELECT * FROM accounts WHERE status = 'available' AND is_valid = 1 ORDER BY price LIMIT ?", (limit,)).fetchall()
    
    def get_accounts_count(self):
        row = self.conn.execute("SELECT COUNT(*) FROM accounts WHERE status = 'available' AND is_valid = 1").fetchone()
        return row[0] if row else 0
    
    def add_account(self, session_string, phone, price, original_price, lolz_item_id=None, lolz_thread_id=None):
        cursor = self.conn.execute("""
            INSERT INTO accounts (session_string, phone, price, original_price, lolz_item_id, lolz_thread_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_string, phone, price, original_price, lolz_item_id, lolz_thread_id))
        self.conn.commit()
        return cursor.lastrowid
    
    def buy_account(self, account_id, user_id):
        account = self.conn.execute("SELECT * FROM accounts WHERE id = ? AND status = 'available' AND is_valid = 1", (account_id,)).fetchone()
        if not account:
            return None
        
        balance = self.get_balance(user_id)
        if balance < account['price']:
            return None
        
        self.conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (account['price'], user_id))
        self.conn.execute("UPDATE accounts SET status = 'sold', buyer_id = ?, sold_at = ? WHERE id = ?", 
                         (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), account_id))
        
        order_id = hashlib.md5(f"{user_id}{account_id}{datetime.now()}".encode()).hexdigest()[:16]
        self.conn.execute("INSERT INTO orders (order_id, user_id, account_id, amount) VALUES (?, ?, ?, ?)", 
                         (order_id, user_id, account_id, account['price']))
        self.conn.commit()
        
        result = dict(account)
        result['order_id'] = order_id
        return result
    
    def mark_account_invalid(self, account_id, reason=""):
        self.conn.execute("UPDATE accounts SET is_valid = 0, status = 'banned' WHERE id = ?", (account_id,))
        self.conn.commit()
        logger.info(f"Аккаунт #{account_id} помечен как невалидный: {reason}")
    
    def get_account_by_id(self, account_id):
        return self.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    
    def get_all_accounts(self, status=None):
        if status:
            return self.conn.execute("SELECT * FROM accounts WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        return self.conn.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
    
    def delete_account(self, account_id):
        self.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()
    
    def get_stars_receiver(self):
        return self.conn.execute("SELECT * FROM stars_receiver WHERE id = 1").fetchone()
    
    def set_stars_receiver(self, session_string, phone, username, has_2fa=0, is_active=1):
        self.conn.execute("INSERT OR REPLACE INTO stars_receiver (id, session_string, phone, username, has_2fa, is_active, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?)", 
                         (session_string, phone, username, has_2fa, is_active, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.conn.commit()
    
    def update_stars_receiver_active(self, is_active):
        self.conn.execute("UPDATE stars_receiver SET is_active = ? WHERE id = 1", (is_active,))
        self.conn.commit()
    
    def star_gift_exists(self, gift_id):
        row = self.conn.execute("SELECT * FROM star_deposits WHERE gift_id = ?", (gift_id,)).fetchone()
        return row is not None
    
    def add_star_deposit(self, gift_id, user_id, stars_count, from_id):
        self.conn.execute("INSERT INTO star_deposits (gift_id, user_id, stars_count, from_id, processed) VALUES (?, ?, ?, ?, 1)", 
                         (gift_id, user_id, stars_count, from_id))
        self.conn.commit()
    
    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else default
    
    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()
    
    def get_lolz_sync(self):
        return self.conn.execute("SELECT * FROM lolz_sync WHERE id = 1").fetchone()
    
    def update_lolz_sync(self, thread_id, last_sync):
        self.conn.execute("INSERT OR REPLACE INTO lolz_sync (id, thread_id, last_sync) VALUES (1, ?, ?)", (thread_id, last_sync))
        self.conn.commit()

db = Database()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
def get_country_from_phone(phone):
    try:
        if not phone.startswith('+'):
            phone = '+' + phone
        parsed = phonenumbers.parse(phone, None)
        code = parsed.country_code
        if code == 7: return 'RU'
        if code == 375: return 'BY'
        if code == 77: return 'KZ'
        if code == 380: return 'UA'
        if code == 1: return 'US'
        return 'EU'
    except:
        return 'RU'

def get_price_with_markup(original_price):
    markup = int(db.get_setting('markup_percent', str(MARKUP_PERCENT)))
    min_price = int(db.get_setting('min_price', str(MIN_ACCOUNT_PRICE)))
    price = original_price * (1 + markup / 100)
    return max(price, min_price)

def extract_session_from_text(text):
    patterns = [
        r'1[A-Za-z0-9+=\/]+',
        r'<code>(.*?)<\/code>',
        r'`(.*?)`',
        r'session[:=]\s*["\']?(.+?)["\']?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None

def extract_price_from_text(text):
    patterns = [r'(\d+)\s*₽', r'(\d+)\s*руб', r'price:?\s*(\d+)', r'цена:?\s*(\d+)']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return 0

# ==================== ПРОВЕРКА АККАУНТА ====================
async def validate_account(session_string: str) -> Dict:
    client = None
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            return {'valid': False, 'reason': 'Сессия не авторизована'}
        
        me = await client.get_me()
        phone = me.phone or "неизвестно"
        country = get_country_from_phone(phone)
        
        age_days = 30
        try:
            full_user = await client.get_entity(me.id)
            if hasattr(full_user, 'date') and full_user.date:
                age_days = (datetime.now() - full_user.date).days
        except:
            pass
        
        await client.disconnect()
        return {
            'valid': True,
            'phone': phone,
            'country': country,
            'age_days': age_days,
            'session_string': session_string
        }
    except RPCError as e:
        return {'valid': False, 'reason': f'Ошибка API: {e}'}
    except Exception as e:
        if client:
            await client.disconnect()
        return {'valid': False, 'reason': str(e)}

# ==================== LOLZTEAM API ====================
class LolzTeamAPI:
    def __init__(self, token):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    async def _request(self, method, endpoint, data=None):
        if not self.token or self.token == "твой_токен_из_лолзтим":
            return None
        url = f"{LOLZTEAM_API_URL}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=self.headers, json=data, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except:
            return None
    
    async def get_thread_messages(self, thread_id, limit=50):
        return await self._request("GET", f"threads/{thread_id}/messages?limit={limit}")

lolz = LolzTeamAPI(LOLZTEAM_TOKEN)

# ==================== СИНХРОНИЗАЦИЯ ====================
async def sync_from_lolz_thread(thread_id):
    if not lolz:
        return 0
    
    try:
        result = await lolz.get_thread_messages(thread_id, limit=100)
        if not result or 'messages' not in result:
            return 0
        
        new_count = 0
        for msg in result['messages']:
            text = msg.get('text', '')
            session = extract_session_from_text(text)
            if not session:
                continue
            
            existing = db.conn.execute("SELECT id FROM accounts WHERE session_string = ?", (session,)).fetchone()
            if existing:
                continue
            
            validation = await validate_account(session)
            if not validation['valid']:
                logger.warning(f"Невалидный аккаунт: {validation.get('reason')}")
                continue
            
            price = extract_price_from_text(text)
            if price == 0:
                price = 100
            
            our_price = get_price_with_markup(price)
            
            db.add_account(
                session_string=session,
                phone=validation['phone'],
                price=our_price,
                original_price=price,
                lolz_thread_id=thread_id
            )
            new_count += 1
        
        db.update_lolz_sync(thread_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"🔄 Синхронизировано {new_count} аккаунтов из темы {thread_id}")
        return new_count
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}")
        return 0

async def auto_replenish():
    count = db.get_accounts_count()
    if count < MIN_STOCK:
        sync_data = db.get_lolz_sync()
        if sync_data and sync_data['thread_id']:
            await sync_from_lolz_thread(sync_data['thread_id'])

# ==================== CRYPTO BOT ====================
async def create_crypto_invoice(amount_rub, user_id):
    if not CRYPTO_BOT_TOKEN:
        return None
    url = f"{CRYPTO_BOT_API}/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_rub), "description": f"Пополнение на {amount_rub} ₽"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=10) as resp:
                result = await resp.json()
                if result.get('ok'):
                    invoice = result['result']
                    db.conn.execute("INSERT INTO crypto_invoices (invoice_id, user_id, amount_rub, pay_url) VALUES (?, ?, ?, ?)", 
                                   (invoice['invoice_id'], user_id, amount_rub, invoice['pay_url']))
                    db.conn.commit()
                    return invoice
                return None
    except:
        return None

async def check_crypto_invoice(invoice_id):
    if not CRYPTO_BOT_TOKEN:
        return False
    url = f"{CRYPTO_BOT_API}/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    params = {"invoice_ids": invoice_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=params, timeout=10) as resp:
                result = await resp.json()
                if result.get('ok') and result['result']['items']:
                    return result['result']['items'][0].get('status') == 'paid'
                return False
    except:
        return False

# ==================== STARS ПРИЁМНИК ====================
stars_receiver_client = None

async def run_stars_receiver():
    global stars_receiver_client
    receiver = db.get_stars_receiver()
    if not receiver or not receiver['is_active'] or not receiver['session_string']:
        return
    
    try:
        stars_receiver_client = TelegramClient(StringSession(receiver['session_string']), API_ID, API_HASH)
        await stars_receiver_client.connect()
        if not await stars_receiver_client.is_user_authorized():
            db.update_stars_receiver_active(0)
            return
        
        logger.info("⭐ Stars приёмник запущен")
        
        @stars_receiver_client.on(events.NewMessage)
        async def stars_handler(event):
            try:
                stars_count = None
                from_id = None
                gift_id = None
                
                if event.message.action and hasattr(event.message.action, 'count'):
                    stars_count = event.message.action.count
                    from_id = event.message.sender_id
                    gift_id = f"action_{event.message.id}_{event.chat_id}"
                
                if not stars_count:
                    return
                
                if db.star_gift_exists(gift_id):
                    return
                
                rate = float(db.get_setting('stars_rate', '1.0'))
                amount_rub = stars_count * rate
                
                db.add_balance(from_id, amount_rub)
                db.add_star_deposit(gift_id, from_id, stars_count, from_id)
                
                await bot_client.send_message(from_id, f"⭐ Пополнение! Зачислено: {amount_rub:.0f} ₽", parse_mode='html')
            except Exception as e:
                logger.error(f"Stars ошибка: {e}")
        
        await stars_receiver_client.run_until_disconnected()
    except Exception as e:
        logger.error(f"Stars приёмник умер: {e}")

# ==================== WEBAPP HTML ====================
WEBAPP_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Физ-Шоп</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0a0a; min-height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: white; overflow-x: hidden; }
        .stars-container { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: hidden; }
        .star { position: absolute; background: white; border-radius: 50%; opacity: 0.8; animation: fall linear infinite; }
        @keyframes fall { from { transform: translateY(-10vh) rotate(0deg); opacity: 1; } to { transform: translateY(100vh) rotate(360deg); opacity: 0; } }
        .container { position: relative; z-index: 1; padding: 20px 16px 80px; max-width: 600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 24px; }
        .logo { font-size: 48px; margin-bottom: 8px; }
        .title { font-size: 24px; font-weight: 700; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .balance { background: rgba(255,255,255,0.1); border-radius: 20px; padding: 12px 20px; margin: 16px 0; text-align: center; backdrop-filter: blur(10px); }
        .balance-amount { font-size: 28px; font-weight: 700; color: #667eea; }
        .card { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border-radius: 20px; padding: 16px; margin-bottom: 12px; border: 1px solid rgba(255, 255, 255, 0.1); transition: transform 0.2s; cursor: pointer; }
        .card:active { transform: scale(0.98); }
        .card-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
        .card-price { font-size: 20px; font-weight: 700; color: #667eea; }
        .card-phone { font-size: 14px; color: rgba(255,255,255,0.6); font-family: monospace; margin-top: 8px; }
        .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; border-radius: 14px; padding: 14px 24px; color: white; font-weight: 600; font-size: 16px; cursor: pointer; transition: opacity 0.2s; width: 100%; text-align: center; }
        .btn:active { opacity: 0.8; }
        .tab-bar { position: fixed; bottom: 0; left: 0; right: 0; display: flex; background: rgba(10, 10, 10, 0.95); backdrop-filter: blur(10px); padding: 12px; gap: 12px; justify-content: space-around; border-top: 1px solid rgba(255,255,255,0.1); z-index: 2; }
        .tab { text-align: center; padding: 8px; border-radius: 12px; flex: 1; cursor: pointer; transition: background 0.2s; }
        .tab.active { background: rgba(102, 126, 234, 0.2); }
        .tab-icon { font-size: 24px; margin-bottom: 4px; }
        .tab-label { font-size: 12px; }
        .loading, .empty { text-align: center; padding: 40px; color: rgba(255,255,255,0.5); }
    </style>
</head>
<body>
    <div class="stars-container" id="stars"></div>
    <div class="container" id="app"></div>
    <div class="tab-bar">
        <div class="tab" data-tab="shop"><div class="tab-icon">🛒</div><div class="tab-label">Магазин</div></div>
        <div class="tab" data-tab="profile"><div class="tab-icon">👤</div><div class="tab-label">Профиль</div></div>
        <div class="tab" data-tab="support"><div class="tab-icon">🆘</div><div class="tab-label">Поддержка</div></div>
    </div>
    
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();
        tg.enableClosingConfirmation();
        
        let currentTab = 'shop';
        
        function createStars() {
            const container = document.getElementById('stars');
            for (let i = 0; i < 100; i++) {
                const star = document.createElement('div');
                star.className = 'star';
                star.style.left = Math.random() * 100 + '%';
                star.style.width = (Math.random() * 3 + 1) + 'px';
                star.style.height = star.style.width;
                star.style.animationDuration = (Math.random() * 3 + 2) + 's';
                star.style.animationDelay = Math.random() * 5 + 's';
                container.appendChild(star);
            }
        }
        createStars();
        
        async function callBot(action, data = {}) {
            tg.sendData(JSON.stringify({ action, ...data }));
            return { ok: true };
        }
        
        async function loadShop() {
            const app = document.getElementById('app');
            app.innerHTML = '<div class="loading">⭐ Загрузка товаров...</div>';
            
            const response = await fetch('/api/catalog');
            const catalog = await response.json();
            
            if (!catalog.items || catalog.items.length === 0) {
                app.innerHTML = '<div class="empty">📭 Нет доступных аккаунтов</div>';
                return;
            }
            
            let html = '<div class="header"><div class="logo">⚡</div><div class="title">PHYS-SHOP</div></div>';
            html += `<div class="balance">💰 Баланс: <span class="balance-amount">${catalog.balance} ₽</span></div>`;
            
            for (const item of catalog.items) {
                html += `
                    <div class="card" onclick="buyAccount(${item.id})">
                        <div class="card-title">📱 Аккаунт #${item.id}</div>
                        <div class="card-phone">${item.phone || 'Номер скрыт'}</div>
                        <div class="card-price">💰 ${item.price} ₽</div>
                    </div>
                `;
            }
            app.innerHTML = html;
        }
        
        async function buyAccount(id) {
            tg.showPopup({
                title: 'Подтверждение',
                message: 'Купить этот аккаунт?',
                buttons: [{type: 'ok'}, {type: 'cancel'}]
            }, async (buttonId) => {
                if (buttonId === 0) {
                    const result = await callBot('buy', { account_id: id });
                    if (result.success) {
                        tg.showPopup({title: 'Успех', message: 'Аккаунт куплен!', buttons: [{type: 'ok'}]});
                        loadShop();
                    } else {
                        tg.showAlert(result.error || 'Ошибка при покупке');
                    }
                }
            });
        }
        
        async function loadProfile() {
            const app = document.getElementById('app');
            app.innerHTML = '<div class="loading">⭐ Загрузка...</div>';
            const response = await fetch('/api/profile');
            const profile = await response.json();
            let html = `
                <div class="header"><div class="logo">👤</div><div class="title">ПРОФИЛЬ</div></div>
                <div class="balance"><div>💰 Баланс</div><div class="balance-amount">${profile.balance} ₽</div></div>
                <div style="margin-bottom:12px;">🆔 ID: ${profile.user_id}</div>
                <div style="margin-bottom:12px;">🎯 Скидка: ${profile.discount}%</div>
                <div style="margin-bottom:12px;">🛒 Куплено: ${profile.total_bought} шт.</div>
                <button class="btn" onclick="deposit()">💳 Пополнить баланс</button>
            `;
            app.innerHTML = html;
        }
        
        function deposit() {
            tg.showPopup({
                title: 'Пополнение баланса',
                message: 'Выберите способ',
                buttons: [{type: 'default', text: '⭐ Stars'}, {type: 'default', text: '💎 Crypto'}, {type: 'cancel'}]
            }, async (buttonId) => {
                if (buttonId === 0) await callBot('deposit_stars');
                else if (buttonId === 1) await callBot('deposit_crypto');
            });
        }
        
        async function loadSupport() {
            const app = document.getElementById('app');
            app.innerHTML = `
                <div class="header"><div class="logo">🆘</div><div class="title">ПОДДЕРЖКА</div></div>
                <div class="balance">Менеджер: @oxatov</div>
                <div style="margin-bottom:20px;">По вопросам обращайтесь к менеджеру</div>
                <button class="btn" onclick="tg.openTelegramLink('https://t.me/oxatov')">📞 Связаться</button>
            `;
        }
        
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                currentTab = tab.dataset.tab;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                if (currentTab === 'shop') loadShop();
                if (currentTab === 'profile') loadProfile();
                if (currentTab === 'support') loadSupport();
            });
        });
        
        loadShop();
    </script>
</body>
</html>
'''

# ==================== ОСНОВНОЙ БОТ ====================
async def start_bot():
    global bot_client
    
    bot_client = TelegramClient('bot_session', API_ID, API_HASH)
    await bot_client.start(bot_token=BOT_TOKEN)
    
    asyncio.create_task(run_stars_receiver())
    asyncio.create_task(auto_replenish())
    
    logger.info("🚀 Бот запущен!")
    
    @bot_client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        user_id = event.sender_id
        db.add_user(user_id, event.sender.username, event.sender.first_name)
        await event.respond(
            "⚡ <b>PHYS-SHOP</b>\n\nДобро пожаловать!\n\n"
            "🛒 /shop - открыть магазин\n"
            "👤 /balance - баланс\n"
            "⭐ /stars - пополнить Stars\n"
            "💎 /crypto - пополнить Crypto\n"
            "🆘 /support - помощь\n"
            "⚙️ /admin - админ-панель",
            parse_mode='html'
        )
    
    @bot_client.on(events.NewMessage(pattern='/shop'))
    async def webapp_handler(event):
        bot_username = (await bot_client.get_me()).username
        await event.respond(
            "🛒 <b>Открой магазин в приложении:</b>",
            buttons=[[Button.url("⭐ Открыть магазин", f"https://t.me/{bot_username}/shop")]],
            parse_mode='html'
        )
    
    @bot_client.on(events.NewMessage(pattern='/balance'))
    async def balance_handler(event):
        balance = db.get_balance(event.sender_id)
        await event.respond(f"💰 Ваш баланс: <b>{balance:.0f} ₽</b>", parse_mode='html')
    
    @bot_client.on(events.NewMessage(pattern='/support'))
    async def support_handler(event):
        await event.respond(f"🆘 Поддержка: @{MANAGER_USERNAME}", parse_mode='html')
    
    @bot_client.on(events.NewMessage(pattern='/admin'))
    async def admin_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        await event.respond(
            "⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            "📋 /accounts - список аккаунтов\n"
            "➕ /add - добавить аккаунт\n"
            "🔄 /sync {thread_id} - синхронизация с LolzTeam\n"
            "❌ /remove {id} - удалить аккаунт\n"
            "✅ /verify {id} - проверить аккаунт\n"
            "⭐ /stars_setup - настройка Stars приёмника\n"
            "💰 /add_balance {user_id} {sum} - добавить баланс",
            parse_mode='html'
        )
    
    @bot_client.on(events.NewMessage(pattern='/accounts'))
    async def list_accounts_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        accounts = db.get_all_accounts()
        if not accounts:
            await event.respond("📭 Нет аккаунтов")
            return
        text = "📋 <b>СПИСОК АККАУНТОВ</b>\n\n"
        for acc in accounts[:20]:
            status = "🟢" if acc['status'] == 'available' and acc['is_valid'] else "🔴"
            text += f"{status} #{acc['id']} | {acc['phone'][:10] if acc['phone'] else '?'} | {acc['price']:.0f} ₽\n"
        await event.respond(text, parse_mode='html')
    
    @bot_client.on(events.NewMessage(pattern='/sync (.+)'))
    async def sync_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        thread_id = int(event.pattern_match.group(1))
        await event.respond(f"🔄 Синхронизация темы {thread_id}...")
        count = await sync_from_lolz_thread(thread_id)
        await event.respond(f"✅ Синхронизировано {count} аккаунтов")
    
    @bot_client.on(events.NewMessage(pattern='/remove (\d+)'))
    async def remove_account_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        account_id = int(event.pattern_match.group(1))
        db.delete_account(account_id)
        await event.respond(f"✅ Аккаунт #{account_id} удалён")
    
    @bot_client.on(events.NewMessage(pattern='/verify (\d+)'))
    async def verify_account_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        account_id = int(event.pattern_match.group(1))
        acc = db.get_account_by_id(account_id)
        if not acc:
            await event.respond(f"❌ Аккаунт #{account_id} не найден")
            return
        await event.respond(f"🔄 Проверка аккаунта #{account_id}...")
        validation = await validate_account(acc['session_string'])
        if validation['valid']:
            await event.respond(f"✅ Аккаунт #{account_id} валиден!\n📱 {validation['phone']}")
        else:
            db.mark_account_invalid(account_id, validation.get('reason'))
            await event.respond(f"❌ Аккаунт #{account_id} невалиден!\n{validation.get('reason')}")
    
    @bot_client.on(events.NewMessage(pattern='/add_balance (\d+) (\d+)'))
    async def add_balance_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        user_id = int(event.pattern_match.group(1))
        amount = float(event.pattern_match.group(2))
        db.add_balance(user_id, amount)
        await event.respond(f"✅ Пользователю {user_id} добавлено {amount:.0f} ₽")
    
    @bot_client.on(events.NewMessage(pattern='/stars_setup'))
    async def stars_setup_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        user_states[event.sender_id] = {'action': 'stars_setup', 'step': 'phone'}
        await event.respond(
            "⭐ <b>НАСТРОЙКА STARS ПРИЁМНИКА</b>\n\n"
            "Введите номер телефона аккаунта (например: +79123456789):\n"
            "/cancel - отмена",
            parse_mode='html'
        )
    
    # ========== API ДЛЯ WEBAPP ==========
    @bot_client.on(events.NewMessage)
    async def api_handler(event):
        if not event.message.text or not event.message.text.startswith('/api/'):
            return
        
        user_id = event.sender_id
        
        if event.message.text == '/api/catalog':
            balance = db.get_balance(user_id)
            accounts = db.get_available_accounts(20)
            items = [{"id": a['id'], "phone": a['phone'] or f"Аккаунт #{a['id']}", "price": a['price']} for a in accounts]
            await event.respond(json.dumps({"balance": balance, "items": items}))
            return
        
        if event.message.text == '/api/profile':
            balance = db.get_balance(user_id)
            await event.respond(json.dumps({"balance": balance, "user_id": user_id, "discount": 0, "total_bought": 0}))
            return
    
    # ========== WEBAPP DATA ==========
    @bot_client.on(events.NewMessage)
    async def webapp_data_handler(event):
        if not event.message.web_app_data:
            return
        
        data = json.loads(event.message.web_app_data.data)
        action = data.get('action')
        user_id = event.sender_id
        
        if action == 'buy':
            account_id = data.get('account_id')
            result = db.buy_account(account_id, user_id)
            if result:
                await event.respond(
                    f"✅ <b>ПОКУПКА УСПЕШНА!</b>\n\n"
                    f"📱 Номер: {result['phone']}\n"
                    f"💰 Сумма: {result['price']:.0f} ₽\n\n"
                    f"📁 <b>String Session:</b>\n<code>{result['session_string']}</code>",
                    parse_mode='html'
                )
                await event.respond(json.dumps({"success": True, "session": result['session_string']}))
            else:
                await event.respond(json.dumps({"success": False, "error": "Ошибка покупки или недостаточно средств"}))
        
        elif action == 'deposit_stars':
            receiver = db.get_stars_receiver()
            if not receiver or not receiver['is_active']:
                await event.respond(json.dumps({"success": False, "error": "Stars приёмник не настроен"}))
            else:
                await event.respond(json.dumps({"success": True, "message": f"Отправьте звёзды на аккаунт @{receiver['username'] if receiver['username'] else receiver['phone']}"}))
        
        elif action == 'deposit_crypto':
            invoice = await create_crypto_invoice(100, user_id)
            if invoice:
                await event.respond(json.dumps({"success": True, "pay_url": invoice['pay_url']}))
            else:
                await event.respond(json.dumps({"success": False, "error": "Ошибка создания счёта"}))
    
    # ========== ОБРАБОТЧИК СТЕЙТОВ (STARS SETUP) ==========
    @bot_client.on(events.NewMessage)
    async def state_handler(event):
        user_id = event.sender_id
        if user_id not in user_states:
            return
        
        state = user_states[user_id]
        text = event.message.text.strip()
        
        if text == '/cancel':
            del user_states[user_id]
            await event.respond("❌ Отменено")
            return
        
        if state.get('action') == 'stars_setup':
            if state['step'] == 'phone':
                phone = text.strip()
                if not phone.startswith('+'):
                    phone = '+' + phone
                state['phone'] = phone
                state['step'] = 'code'
                temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
                await temp_client.connect()
                await temp_client.send_code_request(phone)
                temp_clients[user_id] = temp_client
                await event.respond(f"🔐 Код отправлен на {phone}\nВведите код:")
            
            elif state['step'] == 'code':
                temp_client = temp_clients.get(user_id)
                if not temp_client:
                    await event.respond("❌ Ошибка, начните заново")
                    del user_states[user_id]
                    return
                try:
                    await temp_client.sign_in(state['phone'], text)
                    me = await temp_client.get_me()
                    username = me.username if me.username else None
                    session_string = temp_client.session.save()
                    await temp_client.disconnect()
                    del temp_clients[user_id]
                    
                    db.set_stars_receiver(session_string, state['phone'], username, 0, 1)
                    asyncio.create_task(run_stars_receiver())
                    
                    await event.respond(f"✅ Аккаунт-приёмник настроен!\n📱 {state['phone']}\n👤 @{username if username else 'нет'}")
                    del user_states[user_id]
                    
                except SessionPasswordNeededError:
                    state['step'] = '2fa'
                    await event.respond("🔐 Требуется пароль 2FA!\nВведите пароль:")
                except PhoneCodeInvalidError:
                    await event.respond("❌ Неверный код")
                except Exception as e:
                    await event.respond(f"❌ Ошибка: {e}")
                    try:
                        await temp_client.disconnect()
                    except:
                        pass
                    del temp_clients[user_id]
                    del user_states[user_id]
            
            elif state['step'] == '2fa':
                temp_client = temp_clients.get(user_id)
                if not temp_client:
                    await event.respond("❌ Ошибка, начните заново")
                    del user_states[user_id]
                    return
                try:
                    await temp_client.sign_in(password=text)
                    me = await temp_client.get_me()
                    username = me.username if me.username else None
                    session_string = temp_client.session.save()
                    await temp_client.disconnect()
                    del temp_clients[user_id]
                    
                    db.set_stars_receiver(session_string, state['phone'], username, 1, 1)
                    asyncio.create_task(run_stars_receiver())
                    
                    await event.respond(f"✅ Аккаунт-приёмник настроен (с 2FA)!\n📱 {state['phone']}\n👤 @{username if username else 'нет'}")
                    del user_states[user_id]
                    
                except Exception as e:
                    await event.respond(f"❌ Ошибка: {e}")
                    try:
                        await temp_client.disconnect()
                    except:
                        pass
                    del temp_clients[user_id]
                    del user_states[user_id]
    
    await bot_client.run_until_disconnected()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Физ-Шоп v17.0 - ПОЛНАЯ ВЕРСИЯ")
    print("=" * 60)
    print(f"👑 Админ: {ADMIN_IDS}")
    print(f"💰 Наценка: {MARKUP_PERCENT}% (минимум {MIN_ACCOUNT_PRICE} ₽)")
    print(f"🔄 Авто-синхронизация при остатке < {MIN_STOCK} шт.")
    print("=" * 60)
    
    asyncio.run(start_bot())