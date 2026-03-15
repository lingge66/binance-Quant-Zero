"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


import asyncio
import os
import json

# ==========================================
# 1. 代理与密钥配置 (保持与之前成功时一致)
# ==========================================
PROXY_URL = 'http://127.0.0.1:10808'
os.environ['HTTP_PROXY'] = PROXY_URL
os.environ['HTTPS_PROXY'] = PROXY_URL

# 填入你昨晚测试成功的合约测试网密钥
MY_KEY = 'h6S0mg2T6fJtkw7CKX3QDKbCzoCAmZx7IIIojHuAHkePclCCgcTc4CuiJ77CBCX2'
MY_SECRET = 'yzQVJ5kMsKP1sdq6EDBSQGnC5TuJ4KHwym6uUh1NRbePrmz17TvNH1C2pFUyJ1Vl'

os.environ['BINANCE_API_KEY'] = MY_KEY
os.environ['BINANCE_API_SECRET'] = MY_SECRET
os.environ['BINANCE_TESTNET'] = 'true'

# ==========================================
# 2. 注入上帝模式补丁 (确保直连合约测试网)
# ==========================================
import ccxt.async_support as ccxt
original_binanceusdm_init = ccxt.binanceusdm.__init__

def god_mode_ccxt_init(self, config=None, *args, **kwargs):
    if config is None: config = {}
    config['apiKey'] = MY_KEY
    config['secret'] = MY_SECRET
    config['proxies'] = {'http': PROXY_URL, 'https': PROXY_URL}
    config['urls'] = {
        'api': {
            'public': 'https://testnet.binancefuture.com',
            'private': 'https://testnet.binancefuture.com',
        }
    }
    config.setdefault('options', {})['defaultType'] = 'future'
    original_binanceusdm_init(self, config, *args, **kwargs)

ccxt.binanceusdm.__init__ = god_mode_ccxt_init
ccxt.binance.__init__ = god_mode_ccxt_init

# ==========================================
# 3. 导入技能模块并执行测试
# ==========================================
from openclaw_skills import get_account_status, get_market_quote, get_current_positions, execute_smart_trade

async def run_sandbox_test():
    print("\n" + "="*50)
    print("🚀 开始本地核心技能沙盒测试")
    print("="*50)

    print("\n[测试 1] 查资金...")
    res = await get_account_status()
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))

    print("\n[测试 2] 查 BTC 行情...")
    res = await get_market_quote("BTC/USDT")
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))

    print("\n[测试 3] 查当前持仓 (看看之前买的 0.01 BTC 在不在)...")
    res = await get_current_positions()
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))

    print("\n[测试 4] 测试平仓/反向开单 (做空 0.01 BTC)...")
    res = await execute_smart_trade("BTC/USDT", "sell", "market", 0.01)
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))

    print("\n[测试 5] 再次查持仓 (确认仓位变化)...")
    res = await get_current_positions()
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))
    
    print("\n✅ 所有本地测试执行完毕！")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_sandbox_test())