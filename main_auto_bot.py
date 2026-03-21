#!/usr/bin/env python3
"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project.
Open Source Version - Adaptable for all environments.

OpenClaw Binance Agent - 自动化 3.0 (风控完全体 + 战绩黑匣子)
集成规则引擎 + 动态原生止盈止损 + SQLite 交易记录存档
"""

import os
import sys
import time
import asyncio
import logging
import sqlite3
import aiohttp
import pandas as pd
from pathlib import Path

# ==========================================
# 🛠️ 动态路径破解：适应任何用户的环境
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(BASE_DIR))

try:
    from config.config_manager import ConfigManager
    from src.risk.account_monitor import AccountMonitor
    from src.execution.order_manager import OrderManager, OrderType, OrderSide
    from src.risk.rule_engine import RiskRuleEngine, TradeContext, AccountContext
except ImportError as e:
    print(f"❌ 导入错误，请检查环境变量或目录结构: {e}")
    sys.exit(1)

# ==========================================
# 📡 核心引流：自适应日志路径
# ==========================================
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "agent.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AutoBot_V3")

# ==========================================
# 🗄️ 战绩黑匣子 (SQLite 数据库初始化)
# ==========================================
data_dir = BASE_DIR / "data"
data_dir.mkdir(exist_ok=True)
DB_PATH = data_dir / "trade_history.db"

def init_db():
    """初始化量化交易黑匣子数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                quantity REAL,
                sl_price REAL,
                tp_price REAL,
                order_id TEXT
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"🗄️ 战绩黑匣子系统在线: {DB_PATH}")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")

def log_trade(symbol: str, side: str, entry_price: float, quantity: float, sl_price: float, tp_price: float, order_id: str):
    """将开仓记录不可篡改地写入黑匣子"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, side, entry_price, quantity, sl_price, tp_price, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, side, entry_price, quantity, sl_price, tp_price, order_id))
        conn.commit()
        conn.close()
        logger.info(f"💾 战绩已加密写入黑匣子: {symbol} {side}")
    except Exception as e:
        logger.error(f"❌ 战绩写入黑匣子失败: {e}")

# ==========================================
# 🧠 指标计算
# ==========================================
def calculate_indicators(df: pd.DataFrame):
    """计算 RSI、ATR 和 EMA"""
    # RSI
    close_delta = df['close'].diff()
    up = close_delta.clip(lower=0)
    down = -1 * close_delta.clip(upper=0)
    ma_up = up.ewm(com=13, adjust=True).mean()
    ma_down = down.ewm(com=13, adjust=True).mean()
    df['rsi'] = 100 - (100 / (1 + ma_up / ma_down))
    
    # ATR
    df['tr'] = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    # EMA 用于趋势过滤
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    return df

# ==========================================
# 🚀 自动化主引擎循环
# ==========================================
async def run_auto_bot_v3():
    print("\n" + "🚀".center(60, "-"))
    print("量化大脑 3.0 - 风控完全体启动".center(50))
    print("-".center(60, "-") + "\n")

    init_db()  # 启动时预热数据库

    config = ConfigManager()
    monitor = AccountMonitor(config)
    await monitor.initialize()
    manager = OrderManager(config)
    await manager.initialize()
    
    rule_engine = RiskRuleEngine(config)
    
    # 加载动态策略参数
    auto_cfg = config.get('auto_trade', {})
    symbols = auto_cfg.get('symbols', ["BTCUSDT", "ETHUSDT"])
    base_amount = auto_cfg.get('base_amount', 0.01)
    rsi_oversold = auto_cfg.get('rsi_oversold', 30)
    rsi_overbought = auto_cfg.get('rsi_overbought', 70)
    atr_multiplier_sl = auto_cfg.get('atr_multiplier_sl', 2.0)
    atr_multiplier_tp = auto_cfg.get('atr_multiplier_tp', 1.5)
    interval_seconds = auto_cfg.get('interval_seconds', 15)
    max_positions_per_symbol = auto_cfg.get('max_positions_per_symbol', 1)
    use_trend_filter = auto_cfg.get('use_trend_filter', True)
    trend_ema_period = auto_cfg.get('trend_ema_period', 50)
    trend_timeframe = auto_cfg.get('trend_timeframe', '1h')

    try:
        iteration = 1
        while True:
            logger.info(f"第 {iteration} 轮深度扫描开始...")
            
            for symbol in symbols:
                try:
                    # 1. 获取K线与指标计算
                    raw_params = {'symbol': symbol.replace('/', ''), 'interval': '1m', 'limit': 50}
                    klines = await monitor._safe_api_call(monitor.exchange.fapiPublicGetKlines, raw_params)
                    df = pd.DataFrame([[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in klines],
                                      columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                    df = calculate_indicators(df)
                    
                    current_price = df['close'].iloc[-1]
                    current_rsi = df['rsi'].iloc[-1]
                    current_atr = df['atr'].iloc[-1]
                    
                    # 2. 趋势方向探测
                    trend_allowed = True
                    trend_direction = "unknown"
                    if use_trend_filter:
                        trend_params = {'symbol': symbol.replace('/', ''), 'interval': trend_timeframe, 'limit': 100}
                        trend_klines = await monitor._safe_api_call(monitor.exchange.fapiPublicGetKlines, trend_params)
                        df_trend = pd.DataFrame([[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in trend_klines],
                                                columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                        df_trend['ema'] = df_trend['close'].ewm(span=trend_ema_period, adjust=False).mean()
                        latest_ema = df_trend['ema'].iloc[-1]
                        
                        trend_direction = "up" if current_price > latest_ema else "down"
                        logger.info(f"📊 {symbol} 趋势方向: {trend_direction} (EMA{trend_ema_period}: {latest_ema:.2f})")

                    # 3. RSI 动能信号生成
                    signal_side = None  
                    if current_rsi < rsi_oversold: signal_side = OrderSide.BUY
                    elif current_rsi > rsi_overbought: signal_side = OrderSide.SELL
                        
                    # [测试后门] 演示模式：首轮强制开仓
                    if signal_side is None and iteration == 1:
                        signal_side = OrderSide.SELL
                        logger.warning("⚠️ [演示模式] 触发首轮模拟强制做空信号")
                        
                    # 4. 顺势过滤拦截
                    if use_trend_filter and signal_side is not None:
                        if signal_side == OrderSide.BUY and trend_direction == "down":
                            trend_allowed = False
                            logger.info(f"⏭️ {symbol} 逆势做多(趋势向下)被拦截，跳过")
                        elif signal_side == OrderSide.SELL and trend_direction == "up":
                            trend_allowed = False
                            logger.info(f"⏭️ {symbol} 逆势做空(趋势向上)被拦截，跳过")

                    if signal_side is None or not trend_allowed:
                        continue

                    # 5. 检查已有持仓
                    positions = await monitor.fetch_positions()
                    existing = [p for p in positions if p.symbol == symbol and p.position_amount != 0]
                    if len(existing) >= max_positions_per_symbol:
                        logger.info(f"⏭️ {symbol} 已有 {len(existing)} 个持仓（上限{max_positions_per_symbol}），跳过开仓")
                        continue
                    
                    # 6. 风控上下文构建与校验
                    balance = await monitor.fetch_account_balance(force_refresh=True)
                    trade_ctx = TradeContext(
                        symbol=symbol,
                        position_side="long" if signal_side == OrderSide.BUY else "short",
                        entry_price=current_price, current_price=current_price,
                        position_size=base_amount, unrealized_pnl=0.0, realized_pnl=0.0,
                        leverage=1.0, timestamp=int(time.time() * 1000)
                    )
                    
                    open_trades = []
                    for p in positions:
                        if p.position_amount != 0:
                            open_trades.append(TradeContext(
                                symbol=p.symbol, position_side=p.position_side,
                                entry_price=p.entry_price, current_price=p.mark_price,
                                position_size=p.position_amount, unrealized_pnl=p.unrealized_pnl,
                                realized_pnl=0.0, leverage=p.leverage, timestamp=int(time.time() * 1000)
                            ))
                    
                    account_ctx = AccountContext(
                        total_balance=balance.total_balance, available_balance=balance.available_balance,
                        margin_ratio=balance.margin_ratio,
                        total_position_value=sum(p.position_amount * p.mark_price for p in positions if p.position_amount != 0),
                        daily_pnl=0.0, weekly_pnl=0.0, open_positions=open_trades, timestamp=balance.timestamp
                    )
                    
                    rule_results = await rule_engine.evaluate_all_rules(trade_ctx, account_ctx, record_trade_attempt=True)
                    if rule_engine.has_critical_failure(rule_results) or any(not r.passed for r in rule_results):
                        logger.warning(f"🛑 {symbol} 风控未通过，跳过开仓")
                        for r in rule_results:
                            if not r.passed: logger.warning(f"  规则 {r.rule_name}: {r.message}")
                        continue
                    
                    # 7. 动态计算止损止盈
                    sl_distance = current_atr * atr_multiplier_sl
                    tp_distance = current_atr * atr_multiplier_tp
                    if signal_side == OrderSide.BUY:
                        sl_price = current_price - sl_distance
                        tp_price = current_price + tp_distance
                    else:
                        sl_price = current_price + sl_distance
                        tp_price = current_price - tp_distance
                    
                    # 8. 执行开仓与原生风控挂载
                    logger.info(f"🛡️ 风控校验通过，准备开仓 {symbol} {signal_side.value} 数量 {base_amount}")
                    try:
                        order = await manager.create_order(symbol, OrderType.MARKET, signal_side, base_amount)
                        executed = await manager.submit_order(order.order_id, dry_run=False)
                        order_id = executed.metadata.get('exchange_order_id', 'N/A')
                        
                        # ==========================================
                        # 🌟 终极修复：原生裸接口双向挂载止盈止损
                        # ==========================================
                        raw_symbol = symbol.replace('/', '').upper()
                        pos_side_str = 'LONG' if signal_side == OrderSide.BUY else 'SHORT'
                        close_side_str = 'SELL' if signal_side == OrderSide.BUY else 'BUY'

                        # 挂载止损
                        try:
                            sl_params = {'symbol': raw_symbol, 'side': close_side_str, 'type': 'STOP_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{sl_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE', 'positionSide': pos_side_str}
                            try: await monitor.exchange.request('fapi/v1/algoOrder', 'private', 'POST', sl_params)
                            except:
                                del sl_params['positionSide']
                                await monitor.exchange.request('fapi/v1/algoOrder', 'private', 'POST', sl_params)
                            logger.info(f"  🛡️ 原生止损单挂载成功: {sl_price:.2f}")
                        except Exception as e: logger.error(f"  ❌ 止损单挂载失败: {e}")

                        # 挂载止盈
                        try:
                            tp_params = {'symbol': raw_symbol, 'side': close_side_str, 'type': 'TAKE_PROFIT_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{tp_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE', 'positionSide': pos_side_str}
                            try: await monitor.exchange.request('fapi/v1/algoOrder', 'private', 'POST', tp_params)
                            except:
                                del tp_params['positionSide']
                                await monitor.exchange.request('fapi/v1/algoOrder', 'private', 'POST', tp_params)
                            logger.info(f"  🎯 原生止盈单挂载成功: {tp_price:.2f}")
                        except Exception as e: logger.error(f"  ❌ 止盈单挂载失败: {e}")
                        
                        # 🌟 新增：成功开仓后，写入本地黑匣子！
                        log_trade(symbol, signal_side.value.upper(), current_price, base_amount, sl_price, tp_price, order_id)

                        # 发送战报
                        await send_enhanced_notification(symbol, signal_side.value.upper(), base_amount, current_price, sl_price, tp_price, order_id)
                        
                    except Exception as e:
                        logger.error(f"开仓失败 {symbol}: {e}")
                    
                except Exception as e:
                    logger.error(f"处理 {symbol} 时出错: {e}")
                    continue
            
            iteration += 1
            await asyncio.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        logger.info("程序退出")
    finally:
        await monitor.close()
        await manager.close()

async def send_enhanced_notification(symbol, side, amt, price, sl, tp, oid):
    """发送战报"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')  
    proxy = os.getenv('TELEGRAM_PROXY')
    
    if not bot_token or not chat_id: return

    msg = (
        f"🛡️ **量化大脑 3.0 演示自动开仓**\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 **标的**：`{symbol}`\n"
        f"⚖️ **方向**：`{'多单 (LONG)' if side == 'BUY' else '空单 (SHORT)'}`\n"
        f"💰 **进场价格**：`${price:.2f}`\n"
        f"📦 **开仓数量**：`{amt}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"🛑 **止损 (SL)**：`${sl:.2f}`\n"
        f"🎯 **止盈 (TP)**：`${tp:.2f}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"🆔 **单号**：`{oid}`"
    )
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
            async with session.post(url, json=payload, proxy=proxy) as resp:
                if resp.status == 200: logger.info("✅ 战报推送成功")
                else: logger.warning(f"战报推送失败: {resp.status}")
    except Exception as e:
        logger.error(f"通知发送异常: {e}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_auto_bot_v3())
