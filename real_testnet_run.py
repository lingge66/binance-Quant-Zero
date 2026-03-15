"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


import os
import json
import traceback
import ccxt
from dotenv import load_dotenv

# ==========================================
# 🛡️ 稳如老狗的 SOCKS5 代理
# ==========================================
os.environ['HTTP_PROXY'] = 'socks5h://127.0.0.1:10808'
os.environ['HTTPS_PROXY'] = 'socks5h://127.0.0.1:10808'

load_dotenv(override=True)
API_KEY = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

def run_pure_demo_sync():
    print("==================================================")
    print("🚀 领哥专属：抛弃所有框架，底层裸接口直接开炮！")
    print("==================================================")

    exchange = ccxt.binanceusdm({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True,
        'proxies': {
            'http': 'socks5h://127.0.0.1:10808',
            'https': 'socks5h://127.0.0.1:10808'
        }
    })

    # 全局替换 URL 为 Demo 盘
    urls_json = json.dumps(exchange.urls)
    urls_json = urls_json.replace('fapi.binance.com', 'demo-fapi.binance.com')
    exchange.urls = json.loads(urls_json)

    try:
        print("\n[INFO] 正在敲门 demo-fapi.binance.com ...")
        server_time = exchange.fapiPublicGetTime()
        print(f"✅ 大门已开！服务器时间戳: {server_time['serverTime']}")

        print("\n[INFO] 正在绕开底层拦截，直接抓取 Demo 盘资金...")
        # 🗡️ 核心秘籍：直接调用币安底层 V2 余额接口，不再触发 load_markets！
        balances = exchange.fapiPrivateV2GetBalance()
        
        # 遍历数组，找到 USDT 的余额
        total_usdt = 0
        free_usdt = 0
        for asset in balances:
            if asset['asset'] == 'USDT':
                total_usdt = asset['balance']
                free_usdt = asset['availableBalance']
                break
                
        print(f"💰 【Demo模拟盘】账户总资产: {total_usdt} USDT")
        print(f"🟢 【Demo模拟盘】可用保证金: {free_usdt} USDT")

        print("\n[INFO] 正在执行实盘级测试：市价买入 0.01 BTC...")
        # 🗡️ 核心秘籍：直接调用币安底层下单接口！(注意交易对不用斜杠)
        order_params = {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'type': 'MARKET',
            'quantity': 0.01,
        }
        order = exchange.fapiPrivatePostOrder(order_params)
        
        print("\n🎉🎉🎉 【操作大获成功】 🎉🎉🎉")
        print(f"🚀 订单号: {order['orderId']}")
        print(f"🛒 状态: {order['status']} (已成交: {order['executedQty']})")
        print("👉 领哥大虾，这回连老天爷都拦不住了！赶紧去网页截图领奖吧！")

    except Exception as e:
        print("\n❌ 发生异常：")
        traceback.print_exc()

if __name__ == "__main__":
    run_pure_demo_sync()