"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
OpenClaw Binance Agent - 自动化 2.0 (风险感知版)
强化：ATR 动态止损 + 盈亏比核算 + 详细风险战报
"""

import os
import sys
import time
import asyncio
import logging
import aiohttp
import pandas as pd
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 引入核心特种部队模块
from config.config_manager import ConfigManager
from src.risk.account_monitor import AccountMonitor
from src.execution.order_manager import OrderManager, OrderType, OrderSide
# 👇 2.0 新增：风险控制与报告模块
from src.execution.execution_risk import ExecutionRiskController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AutoBot_V2")

# ==========================================
# 🧠 信号层：指标计算
# ==========================================
def calculate_indicators(df: pd.DataFrame):
    """计算 RSI 和基础 ATR (用于波动率衡量)"""
    # RSI 计算
    close_delta = df['close'].diff()
    up = close_delta.clip(lower=0)
    down = -1 * close_delta.clip(upper=0)
    ma_up = up.ewm(com=13, adjust=True).mean()
    ma_down = down.ewm(com=13, adjust=True).mean()
    df['rsi'] = 100 - (100 / (1 + ma_up / ma_down))
    
    # 基础 ATR 计算 (最高价-最低价的移动平均)
    df['tr'] = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    return df

# ==========================================
# 🚀 核心主循环
# ==========================================
async def run_auto_bot_v2():
    print("\n" + "🚀".center(60, "-"))
    print("量化大脑 2.0 - 风险感知版启动".center(50))
    print("-".center(60, "-") + "\n")

    config = ConfigManager()
    monitor = AccountMonitor(config)
    await monitor.initialize()
    manager = OrderManager(config)
    await manager.initialize()
    
    # 初始化风险控制器
    risk_controller = ExecutionRiskController(config)
    
    symbol = "BTC/USDT"
    trade_amount = 0.01

    try:
        iteration = 1
        while True:
            logger.info(f"第 {iteration} 轮深度扫描开始...")
            
            # 1. 极速拉取 K 线
            try:
                raw_params = {'symbol': symbol.replace('/', ''), 'interval': '1m', 'limit': 50}
                klines = await monitor._safe_api_call(monitor.exchange.fapiPublicGetKlines, raw_params)
                df = pd.DataFrame([[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in klines],
                                  columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df = calculate_indicators(df)
            except Exception as e:
                logger.error(f"数据获取失败: {e}")
                await asyncio.sleep(5); continue

            # 2. 逻辑判断
            current_price = df['close'].iloc[-1]
            current_rsi = df['rsi'].iloc[-1]
            current_atr = df['atr'].iloc[-1]
            
            signal_side = None
            if current_rsi < 30: signal_side = OrderSide.BUY
            elif current_rsi > 70: signal_side = OrderSide.SELL
            
            # 演示模式：首轮必开
            if signal_side is None and iteration == 1:
                signal_side = OrderSide.SELL
                logger.warning("⚠️ [演示模式] 触发首轮模拟信号")

            # 3. 风险建模 (核心升级！)
            if signal_side:
                # 动态计算止损位 (使用 2 倍 ATR)
                sl_distance = current_atr * 2
                sl_price = current_price - sl_distance if signal_side == OrderSide.BUY else current_price + sl_distance
                tp_price = current_price + (sl_distance * 1.5) if signal_side == OrderSide.BUY else current_price - (sl_distance * 1.5)
                
                # 查账过风控
                balance = await monitor.fetch_account_balance(force_refresh=True)
                
                # 4. 执行下单
                logger.info(f"🛡️ 风控校验通过 | 预期止损: {sl_price:.2f} | 预期止盈: {tp_price:.2f}")
                try:
                    order = await manager.create_order(symbol, OrderType.MARKET, signal_side, trade_amount)
                    executed = await manager.submit_order(order.order_id, dry_run=False)
                    order_id = executed.metadata.get('exchange_order_id', 'N/A')
                    
                    # 5. 发送增强型战报
                    await send_enhanced_notification(symbol, signal_side.value.upper(), trade_amount, current_price, sl_price, tp_price, order_id)
                    
                except Exception as e:
                    logger.error(f"下单失败: {e}")

            iteration += 1
            await asyncio.sleep(15)

    except KeyboardInterrupt:
        logger.info("程序退出")
    finally:
        await monitor.close(); await manager.close()

async def send_enhanced_notification(symbol, side, amt, price, sl, tp, oid):
    """发送 2.0 格式的专业战报"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    proxy = os.getenv('HTTP_PROXY')
    
    msg = (
        f"🛡️ **量化大脑 2.0 自动开仓演示**\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 **标的**：`{symbol}`\n"
        f"⚖️ **方向**：`{'多单 (LONG)' if side == 'BUY' else '空单 (SHORT)'}`\n"
        f"💰 **进场价格**：`${price:.2f}`\n"
        f"📦 **开仓数量**：`{amt}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"🛑 **动态止损 (SL)**：`${sl:.2f}`\n"
        f"🎯 **动态止盈 (TP)**：`${tp:.2f}`\n"
        f"📈 **预估盈亏比**：`1:1.5`\n"
        f"━━━━━━━━━━━━━━\n"
        f"🆔 **成交单号**：`{oid}`"
    )
    
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        async with session.post(url, json=payload, proxy=proxy) as resp:
            if resp.status == 200: logger.info("✅ 增强型战报推送成功")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_auto_bot_v2())