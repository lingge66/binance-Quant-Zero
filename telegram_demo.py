"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


import asyncio
import sys
import os
import json
import re
import nest_asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# ==========================================
# 🛡️ 统一代理配置
# ==========================================
PROXY_PORT = os.environ.get('PROXY_PORT', '10808')
PROXY_URL = f'http://127.0.0.1:{PROXY_PORT}'
os.environ['HTTP_PROXY'] = PROXY_URL
os.environ['HTTPS_PROXY'] = PROXY_URL

# ==========================================
# 🔑 暴力注入测试网密钥（强制覆盖一切配置）
# ==========================================
MY_KEY = 'h6S0mg2T6fJtkw7CKX3QDKbCzoCAmZx7IIIojHuAHkePclCCgcTc4CuiJ77CBCX2'
MY_SECRET = 'yzQVJ5kMsKP1sdq6EDBSQGnC5TuJ4KHwym6uUh1NRbePrmz17TvNH1C2pFUyJ1Vl'

# 预设到环境变量供其他模块读取
os.environ['BINANCE_API_KEY'] = MY_KEY
os.environ['BINANCE_API_SECRET'] = MY_SECRET
os.environ['BINANCE_TESTNET'] = 'true'

import ccxt.async_support as ccxt

# 保存原始初始化方法
original_binanceusdm_init = ccxt.binanceusdm.__init__

def god_mode_ccxt_init(self, config=None, *args, **kwargs):
    if config is None:
        config = {}
    
    # ⚡ 核心修复：强制注入身份凭证
    config['apiKey'] = MY_KEY
    config['secret'] = MY_SECRET
    
    # 注入代理
    config['proxies'] = {
        'http': PROXY_URL,
        'https': PROXY_URL,
    }
    
    # 强制设置测试网地址
    config['urls'] = {
        'api': {
            'public': 'https://testnet.binancefuture.com',
            'private': 'https://testnet.binancefuture.com',
        }
    }
    
    # 确保使用合约模式
    config.setdefault('options', {})['defaultType'] = 'future'
    
    # 调用原始初始化
    original_binanceusdm_init(self, config, *args, **kwargs)

# 应用猴子补丁
ccxt.binanceusdm.__init__ = god_mode_ccxt_init
ccxt.binance.__init__ = god_mode_ccxt_init

# ==========================================
# 导入业务模块（必须在补丁之后）
# ==========================================
from openclaw_skills import get_account_status, get_market_quote, execute_smart_trade

nest_asyncio.apply()
load_dotenv(override=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text.strip()
    chat_id = update.effective_chat.id
    print(f"\n[收到指令] {user_text}")

    # 场景 1：查资金与风控
    if any(k in user_text for k in ["余额", "资金", "风控", "账户", "钱"]):
        await context.bot.send_message(chat_id=chat_id, text="🤖 OpenClaw 收到！正在穿透防火墙直连测试网...")
        res_json = await get_account_status()
        data = json.loads(res_json)
        
        reply = (
            f"📊 **【测试网账户报告】**\n\n"
            f"💰 **总资产**：`{data.get('total_usdt', 0)} USDT`\n"
            f"🟢 **可用保证金**：`{data.get('available_usdt', 0)} USDT`\n"
            f"📈 **未实现盈亏**：`{data.get('unrealized_pnl', 0)} USDT`\n"
            f"🛡️ **保证金率**：`{data.get('margin_ratio', '0%')}`\n"
            f"⚠️ **系统状态**：{'🟢 正常' if data.get('account_health') == 'SAFE' else '🔴 异常'}"
        )
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode='Markdown')

    # 场景 2：查行情
    elif "行情" in user_text or "价格" in user_text:
        symbol = "BTC/USDT"
        if "ETH" in user_text.upper(): symbol = "ETH/USDT"
        await context.bot.send_message(chat_id=chat_id, text=f"🤖 正在调取 {symbol} 模拟盘数据...")
        res_json = await get_market_quote(symbol)
        data = json.loads(res_json)
        
        if "error" in data:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ 查价失败: {data['error']}")
            return
            
        trend = "🚀" if data['price_change_percent'] > 0 else "📉"
        reply = (
            f"💹 **【{data['symbol']} 实时数据】**\n\n"
            f"💲 **现价**：`${data['current_price']}`\n"
            f"📊 **24h涨跌**：`{data['price_change_percent']}%` {trend}\n"
        )
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode='Markdown')

    # 场景 3：下单
    elif any(k in user_text for k in ["买", "卖", "做多", "做空"]):
        await context.bot.send_message(chat_id=chat_id, text="🤖 正在向测试网发送指令...")
        
        symbol, side, amount = "BTC/USDT", "buy", 0.01
        if "卖" in user_text or "做空" in user_text: side = "sell"
        if "ETH" in user_text.upper(): symbol = "ETH/USDT"
        amt_match = re.search(r'([0-9.]+)\s*个', user_text)
        if amt_match: amount = float(amt_match.group(1))

        res_json = await execute_smart_trade(symbol, side, "market", amount)
        data = json.loads(res_json)
        
        if data.get("status") == "SUCCESS":
            reply = f"🎉 **【模拟盘成交】**\n🆔 单号: `{data['order_id']}`\n🛒 动作: `{data['side'].upper()}` `{data['amount']}` `{data['symbol']}`"
        else:
            reply = f"❌ **【下单失败】**\n原因：`{data.get('error', '未知错误')}`"
            
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode='Markdown')

def main():
    if not TELEGRAM_TOKEN:
        print("❌ 致命错误：请在 .env 中配置 TELEGRAM_BOT_TOKEN")
        return

    print("🚀 OpenClaw 模拟盘机器人启动中...")
    proxy_request = HTTPXRequest(proxy=PROXY_URL)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(proxy_request).get_updates_request(proxy_request).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == '__main__':
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()