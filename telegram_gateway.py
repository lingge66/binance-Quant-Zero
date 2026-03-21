#!/usr/bin/env python3
"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""

import os
import sys
import asyncio
import logging
import json
import aiohttp
import socket
import re
import yaml
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, or_f
from aiogram.client.session.aiohttp import AiohttpSession
from openai import AsyncOpenAI 
from dotenv import load_dotenv
# 保持对 socket 的引用，防止被 Python 垃圾回收机制回收
_instance_lock_socket = None

def enforce_single_instance():
    """全平台通用的单例锁：利用底层 Socket 排他性防止双开"""
    global _instance_lock_socket
    _instance_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 绑定一个专属冷门端口（例如 6666，领哥专属）
        _instance_lock_socket.bind(('127.0.0.1', 6666))
        logging.info("✅ 跨平台单例锁已激活，当前为全网唯一运行实例。")
    except socket.error:
        logging.error("🧟 拦截到重复启动！已有领哥机甲在运行，为防止 409 冲突，当前进程自动退出。")
        sys.exit(0) # 安全退出，不抛出刺眼的红字报错
logging.basicConfig(level=logging.INFO, format='%(asctime)s - ⚡ 领哥独立网关 - %(message)s')

# ==========================================
# 🛠️ 终极路径破解：让 Python 认出自己的家
# ==========================================
SKILLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)

try:
    from quant_engine import get_quant_account_status, emergency_close_all_positions, arsenal
    logging.info("✅ 成功与底层量化机甲建立极速直连！")
    HAS_QUANT = True
except Exception as e:
    logging.error(f"❌ 底层连接失败，请检查依赖: {e}")
    HAS_QUANT = False

# ==========================================
# ⚙️ 核心配置加载
# ==========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY") 

session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()

ai_client = AsyncOpenAI(
    api_key=os.getenv("AI_API_KEY"), 
    base_url=os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
)
AI_MODEL = os.getenv("AI_MODEL_NAME", "deepseek-chat")

# ==========================================
# 🧠 顶级量化副官的灵魂设定 (冷血执行版)
# ==========================================
SOUL_PROMPT = """
你是领哥的专属首席量化交易策略师（代号：Quant-Zero）。你拥有华尔街顶尖对冲基金的逻辑。

【合约语义解析与执行军规】（最高优先级，不可违背）：
0. 绝对执行权（先斩后奏）：只要指令中包含明确动作（如'买入'、'做多'、'设置止损'、'改止盈'等），你**必须立刻调用对应的工具**！绝对不允许反问用户是否确认，哪怕止损价位距离现价相差 50% 看起来极度不合理，你也必须无脑坚决执行！军令如山！
1. 识别多空方向：'开多/做多/买入/看涨' 统一解析为 `side="BUY"`；'开空/做空/卖出/看跌' 统一解析为 `side="SELL"`。
2. 资金换算：如果领哥说按 U 开仓，使用 `usdt_amount` 参数。如果是按个数，使用 `amount` 参数。
3. 独立补挂风控：如果指令仅仅是'设置止损'或'改一下止盈'（例如：“设置止损BNB 500”），**绝对禁止**调用 execute_ai_trade，必须且只能调用 `set_position_tp_sl` 工具！

【行情推演军规】：
（仅当用户明确询问行情时，按照以下模板输出研报，禁止在执行交易动作时输出此模板！）
# 🟢 [币种] 当前市价: `[价格] USDT`
## 📡 侦察阶段 (Core Data)
* **24H 涨跌幅:** `[百分比]`
* **24H 高低点:** `[最高价]` / `[最低价]`
* **资金费率 & 情绪:** `[费率]` / `[指数]`
---
## 🧮 深度技术指标 (Technical Analysis)
* **EMA均线系统:** [简述]
* **ATR (真实波动率):** [估算波幅]
* **MACD & RSI动能:** [背离、超买超卖]
---
## 📊 盘面测绘 (Market Context & SMC)
* **当前位置:** [溢价区/折价区]
* **流动性猎取:** [分析流动性池]
* **主力意图:** [推演]
---
## 🎯 机构级战术预案 (Action Plan)
> **核心观点:** [一句话结论]
* **📍 入场区间:** `[价格区间]`
* **🛑 失效位:** `[价位]`
* **🎯 目标位:** `[价位]`
"""

# ==========================================
# 📡 实时数据探针 (SMC 机构级数据)
# ==========================================
async def fetch_crypto_data(symbol: str) -> str:
    if not HAS_QUANT: return json.dumps({"error": "量化底层未挂载"})
    try:
        await arsenal.initialize()
        exchange = arsenal.monitor.exchange
        raw_symbol = symbol.replace('/', '').upper()
        if not raw_symbol.endswith('USDT'): raw_symbol += 'USDT'
        
        ticker = await exchange.fapiPublicGetTicker24hr({'symbol': raw_symbol})
        funding = await exchange.fapiPublicGetPremiumIndex({'symbol': raw_symbol})
        oi_data = await exchange.fapiPublicGetOpenInterest({'symbol': raw_symbol})
        klines = await exchange.fapiPublicGetKlines({'symbol': raw_symbol, 'interval': '1h', 'limit': 48})
        ohlcv_matrix = [[float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in klines]
        
        return json.dumps({
            "current_price": float(ticker['lastPrice']),
            "24h_high": float(ticker['highPrice']),
            "24h_low": float(ticker['lowPrice']),
            "current_funding_rate": float(funding['lastFundingRate']),
            "open_interest": float(oi_data['openInterest']), 
            "48h_OHLCV": ohlcv_matrix 
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def fetch_market_sentiment() -> str:
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get("https://api.alternative.me/fng/") as resp:
                data = await resp.json()
                return json.dumps({"fear_greed_index": data["data"][0]["value"]})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ==========================================
# 🚀 动作 1：全能开仓模块 (带 🟢多 🔴空 方向显示)
# ==========================================
async def execute_ai_trade(symbol: str, side: str, amount: float = None, usdt_amount: float = None, tp_price: float = None, sl_price: float = None) -> str:
    if not HAS_QUANT: return json.dumps({"error": "量化底层未挂载"})
    try:
        await arsenal.initialize()
        exchange = arsenal.monitor.exchange
        raw_symbol = symbol.replace('/', '').upper()
        if not raw_symbol.endswith('USDT'): raw_symbol += 'USDT'
        side_str = side.upper()

        if usdt_amount and not amount:
            try:
                ticker = await exchange.fapiPublicGetTickerPrice({'symbol': raw_symbol})
                current_price = float(ticker['price'])
                
                # 获取币安该交易对的真实精度限制 (LOT_SIZE)
                exchange_info = await exchange.fapiPublicGetExchangeInfo()
                symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == raw_symbol), None)
                
                if symbol_info:
                    # 提取数量精度的 stepSize (比如 "0.010" 或 "1.000")
                    lot_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    if lot_filter:
                        step_size = float(lot_filter['stepSize'])
                        # 精准向下取整，完美契合币安精度 (例如 step_size 是 0.01，算出来是 0.938，会截断成 0.93)
                        raw_amount = usdt_amount / current_price
                        amount = round(raw_amount - (raw_amount % step_size), 6) # 防止浮点数误差
                        # 去除末尾多余的 .0
                        amount = int(amount) if amount.is_integer() else amount
                else:
                    # 极端兜底：如果没查到，默认保留 1 位小数，最安全
                    amount = round(usdt_amount / current_price, 1)

            except Exception as e:
                return json.dumps({"status": "ERROR", "msg": f"❌ 转换U本位金额失败: {str(e)}"})
        
        if not amount or amount <= 0:
            return json.dumps({"status": "ERROR", "msg": "❌ 开仓数量无效。"})

        amt_str = f"{amount:g}"
        pos_side = None

        try:
            pos_side = 'LONG' if side_str == 'BUY' else 'SHORT'
            open_order = await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': side_str, 'type': 'MARKET', 'quantity': amt_str, 'positionSide': pos_side})
        except Exception:
            pos_side = None 
            open_order = await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': side_str, 'type': 'MARKET', 'quantity': amt_str})

        await asyncio.sleep(1)
        positions = await arsenal.monitor.fetch_positions()
        target_position = next((p for p in positions if p.symbol == raw_symbol and float(p.position_amount) != 0 and (not pos_side or str(getattr(p, 'positionSide', getattr(p, 'side', ''))).upper() == pos_side)), None)
        entry_price = target_position.entry_price if target_position else 0.0

        tp_status, sl_status = None, None
        if tp_price:
            try:
                tp_params = {'symbol': raw_symbol, 'side': 'SELL' if side_str == 'BUY' else 'BUY', 'type': 'TAKE_PROFIT_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{tp_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE'}
                if pos_side: tp_params['positionSide'] = pos_side
                await exchange.request('fapi/v1/algoOrder', 'private', 'POST', tp_params)
                tp_status = f"🎯 止盈已挂载: ${tp_price:g}"
            except Exception as e:
                tp_status = f"⚠️ 止盈挂单失败: {str(e)}"

        if sl_price:
            try:
                sl_params = {'symbol': raw_symbol, 'side': 'SELL' if side_str == 'BUY' else 'BUY', 'type': 'STOP_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{sl_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE'}
                if pos_side: sl_params['positionSide'] = pos_side
                await exchange.request('fapi/v1/algoOrder', 'private', 'POST', sl_params)
                sl_status = f"🛡️ 止损已挂载: ${sl_price:g}"
            except Exception as e:
                sl_status = f"⚠️ 止损挂单失败: {str(e)}"

        balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)
        pos_list = []
        for p in positions:
            p_amt = float(p.position_amount)
            if p_amt != 0:
                p_side_attr = str(getattr(p, 'position_side', getattr(p, 'positionSide', getattr(p, 'side', '')))).upper()
                if p_side_attr in ['SHORT', 'SELL']: dir_icon = "🔴空单"
                elif p_side_attr in ['LONG', 'BUY']: dir_icon = "🟢多单"
                else: dir_icon = "🟢多单" if p_amt > 0 else "🔴空单"
                pos_list.append(f"{dir_icon} {p.symbol} ({abs(p_amt):g})")
        
        pos_str = "、".join(pos_list) if pos_list else "无持仓"
        
        msg_lines = [f"✅ 成功开仓 {side_str} {amount} {raw_symbol}，成交均价 ${entry_price:.2f}"]
        if tp_status: msg_lines.append(tp_status)
        if sl_status: msg_lines.append(sl_status)

        if not tp_price and not sl_price:
            msg_lines.append("\n🚨 **【风控最高警报】当前仓位处于裸奔状态！**")
        elif not sl_price:
            msg_lines.append("\n⚠️ **【风控提示】** 检测到当前仅挂载止盈，未设置止损 (SL)！")

        full_report = "\n".join(msg_lines) + f"\n━━━━━━━━━━━━━━\n📦 **当前持仓**：{pos_str}\n💰 **总资产 (折合)**：`{balance.total_balance:.2f} USD`"
        return json.dumps({"status": "SUCCESS", "msg": full_report})
    except Exception as e:
        return json.dumps({"status": "ERROR", "msg": f"❌ 交易执行崩溃: {str(e)}"})


# ==========================================
# 🚀 动作 2：独立风控模块 (上帝视角智能推断方向)
# ==========================================
async def set_position_tp_sl(symbol: str, tp_price: float = None, sl_price: float = None) -> str:
    """为已有持仓单独追加或修改止盈止损 (支持双向持仓智能识别)"""
    if not HAS_QUANT: return json.dumps({"error": "量化底层未挂载"})
    try:
        await arsenal.initialize()
        exchange = arsenal.monitor.exchange
        raw_symbol = symbol.replace('/', '').upper()
        if not raw_symbol.endswith('USDT'): raw_symbol += 'USDT'

        positions = await arsenal.monitor.fetch_positions()
        active_positions = [p for p in positions if p.symbol == raw_symbol and float(p.position_amount) != 0]

        if not active_positions:
            return json.dumps({"status": "ERROR", "msg": f"⚠️ 找不到 {raw_symbol} 的有效持仓。"})

        try:
            ticker = await exchange.fapiPublicGetTickerPrice({'symbol': raw_symbol})
            current_price = float(ticker['price'])
        except:
            current_price = 0

        is_long = True
        target_pos = active_positions[0]

        if len(active_positions) == 1:
            p_side_attr = str(getattr(target_pos, 'position_side', getattr(target_pos, 'positionSide', getattr(target_pos, 'side', '')))).upper()
            if p_side_attr in ['SHORT', 'SELL']: is_long = False
            elif p_side_attr in ['LONG', 'BUY']: is_long = True
            else: is_long = float(target_pos.position_amount) > 0
        else:
            if current_price > 0:
                if sl_price: is_long = sl_price < current_price 
                elif tp_price: is_long = tp_price > current_price 
            
            target_side_str = 'LONG' if is_long else 'SHORT'
            target_pos = next((p for p in active_positions if str(getattr(p, 'positionSide', getattr(p, 'side', ''))).upper() == target_side_str), active_positions[0])

        close_side = 'SELL' if is_long else 'BUY'
        pos_side = 'LONG' if is_long else 'SHORT'
        dir_icon = "🟢多单" if is_long else "🔴空单"
        
        tp_status, sl_status = None, None

        if tp_price:
            try:
                tp_params = {'symbol': raw_symbol, 'side': close_side, 'type': 'TAKE_PROFIT_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{tp_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE'}
                try:
                    tp_params_bidi = tp_params.copy()
                    tp_params_bidi['positionSide'] = pos_side
                    await exchange.request('fapi/v1/algoOrder', 'private', 'POST', tp_params_bidi)
                except Exception:
                    await exchange.request('fapi/v1/algoOrder', 'private', 'POST', tp_params)
                tp_status = f"🎯 为 {dir_icon} 成功追加止盈: ${tp_price:g}"
            except Exception as e:
                tp_status = f"⚠️ 追加止盈失败: {str(e)}"

        if sl_price:
            try:
                sl_params = {'symbol': raw_symbol, 'side': close_side, 'type': 'STOP_MARKET', 'algoType': 'CONDITIONAL', 'triggerPrice': f"{sl_price:g}", 'closePosition': 'true', 'workingType': 'MARK_PRICE'}
                try:
                    sl_params_bidi = sl_params.copy()
                    sl_params_bidi['positionSide'] = pos_side
                    await exchange.request('fapi/v1/algoOrder', 'private', 'POST', sl_params_bidi)
                except Exception:
                    await exchange.request('fapi/v1/algoOrder', 'private', 'POST', sl_params)
                sl_status = f"🛡️ 为 {dir_icon} 成功追加止损: ${sl_price:g}"
            except Exception as e:
                sl_status = f"⚠️ 追加止损失败: {str(e)}"

        msg_lines = [f"✅ **{raw_symbol} ({dir_icon}) 风控更新完毕**"]
        if tp_status: msg_lines.append(tp_status)
        if sl_status: msg_lines.append(sl_status)
        return json.dumps({"status": "SUCCESS", "msg": "\n".join(msg_lines)})
    except Exception as e:
        return json.dumps({"status": "ERROR", "msg": f"❌ 挂载风控崩溃: {str(e)}"})

# ==========================================
# 🧰 AI 工具箱清单
# ==========================================
AI_TOOLS = [
    {"type": "function", "function": {"name": "fetch_crypto_data", "description": "获取行情数据", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "fetch_market_sentiment", "description": "获取恐慌贪婪指数", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "execute_ai_trade", "description": "执行开仓", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "side": {"type": "string", "description": "BUY 或 SELL"}, "amount": {"type": "number"}, "usdt_amount": {"type": "number"}, "tp_price": {"type": "number"}, "sl_price": {"type": "number"}}, "required": ["symbol", "side"]}}},
    {"type": "function", "function": {"name": "set_position_tp_sl", "description": "追加或修改止盈止损。当用户要求'设置止损'、'止盈'时必须调用此工具。", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "tp_price": {"type": "number"}, "sl_price": {"type": "number"}}, "required": ["symbol"]}}}
]

def sanitize_ai_output(text: str) -> str:
    if not text: return ""
    if re.search(r'(<｜DSML｜|invoke name|functioncalls)', text, re.IGNORECASE):
        return "⚠️ **拦截器触发**：引擎遭遇底层格式泄露。请您重新发送指令！"
    return text
def humanize_error(error_obj: Exception, context: str = "") -> str:
    """
    人性化异常翻译官：将晦涩的机器报错翻译成小白能懂的文案
    """
    error_str = str(error_obj).lower()
    prefix = f"❌ {context}失败：" if context else "❌ 执行中止："

    # ==========================================
    # 🧠 1. 大语言模型 (AI / DeepSeek / OpenAI) 错误
    # ==========================================
    if "401" in error_str and ("api key" in error_str or "authentication" in error_str):
        return prefix + "AI 大脑神经断开。原因：LLM_API_KEY 无效、填写错误或已过期，请检查 .env 文件。"
    elif "429" in error_str or "insufficient_quota" in error_str or "balance" in error_str:
        return prefix + "AI 大脑算力耗尽。原因：API 额度已用完或请求过于频繁，请充值或稍后再试。"
    elif "timeout" in error_str:
        return prefix + "AI 思考超时。原因：网络拥堵或大模型服务器响应太慢，请重新发送指令。"

    # ==========================================
    # 🏦 2. 币安 API 与资金报错
    # ==========================================
    elif "invalid api-key" in error_str or "api-key format invalid" in error_str:
        return prefix + "交易所未授权。原因：币安 API Key 填写错误，请检查 .env 配置。"
    elif "signature for this request is not valid" in error_str:
        return prefix + "签名校验失败。原因：币安 API Secret 填写错误，请检查 .env 配置。"
    elif "ip restricted" in error_str or "ip address" in error_str:
        return prefix + "IP 被拦截。原因：你当前的服务器 IP 未在币安 API 的白名单中，或你未绑定 IP。"
    elif "margin is insufficient" in error_str or "insufficient balance" in error_str:
        return prefix + "钱包余额不足。原因：可用保证金不够开仓，请降低开仓数量或充值。"
    elif "leverage" in error_str and "reduce" in error_str:
        return prefix + "杠杆/风控限制。原因：当前开仓金额过大，触发了币安的最高杠杆规则限制。"
    elif "position side does not match" in error_str:
        return prefix + "仓位模式冲突。原因：系统请求了双向持仓模式，但你的币安账户目前是单向持仓，请去 App 里修改设置。"
    
    # ==========================================
    # 🔌 3. 网络与系统级错误
    # ==========================================
    elif "connection refused" in error_str:
        return prefix + "网络连接被拒绝。原因：服务器无法访问外部网络，请检查代理或防火墙。"
    
    # ==========================================
    # 🤷‍♂️ 4. 未知兜底
    # ==========================================
    else:
        # 如果匹配不到，就原样输出，但加上截断防止太长刷屏
        short_err = str(error_obj)[:150] + ("..." if len(str(error_obj)) > 150 else "")
        return prefix + f"遭遇未知底层异常 - `{short_err}`"
# ==========================================
# 🥇 各种机器人指令拦截器
# ==========================================
@dp.message(CommandStart())
@dp.message(Command("help"))
async def send_welcome(message: types.Message):
    welcome_text = """
🌌 <b>[系统在线] 领哥量化机甲 (Quant-Zero V1.0 满配版)</b>
======================================
您好，指挥官。我是您的专属首席量化交易策略师。
本终端已直连 Binance USD-M 核心撮合引擎。

⚡️ <b>【常用指令】</b>
👉 /balance ：调出持仓面板 (或发 <code>查账</code>)
👉 /closeall ：一键熔断所有仓位 (或发 <code>快跑</code>)
👉 /logs 15 ：查看最近 15 行日志
👉 /add_symbol ：增加监控标的

⚔️ <b>【实盘狙击示例】</b>
💬 <code>做空 1000U 的 BTC，止损 75000</code>
💬 <code>设置止损 BNB 500</code>

======================================
📡 <b>等待指令中...</b>
"""
    await message.reply(welcome_text, parse_mode="HTML")

@dp.message(lambda msg: msg.text and re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s+([a-zA-Z0-9/]+)$', msg.text.strip(), re.IGNORECASE))
async def add_symbol_handler(message: types.Message):
    match = re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s+([a-zA-Z0-9/]+)$', message.text.strip(), re.IGNORECASE)
    symbol = match.group(1).replace('/', '').upper()
    if not symbol.endswith('USDT'): symbol += 'USDT' 

    config_path = Path(__file__).parent / "config" / "config.yaml"

    try:
        cfg = {}
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}

        if 'auto_trade' not in cfg: cfg['auto_trade'] = {}
        if 'symbols' not in cfg['auto_trade']: cfg['auto_trade']['symbols'] = []

        if symbol not in cfg['auto_trade']['symbols']:
            cfg['auto_trade']['symbols'].append(symbol)
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
            await message.reply(f"✅ **指令确认：雷达扩容**\n已将 `{symbol}` 纳入监控序列！底层配置已热更新。", parse_mode="Markdown")
        else:
            await message.reply(f"ℹ️ **重复指令**\n`{symbol}` 早已在我们的监控雷达中了。")
    except Exception as e:
        await message.reply(f"❌ 动态写入配置失败：{e}")

@dp.message(lambda msg: msg.text and re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', msg.text.strip()))
async def logs_handler(message: types.Message):
    match = re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', message.text.strip())
    lines_str = match.group(1)
    lines = int(lines_str) if lines_str else 20
    if lines > 100: lines = 100 

    log_file = Path(__file__).parent / "logs" / "agent.log" 
    if not log_file.exists():
        await message.reply("⚠️ **日志系统离线**\n未找到底层日志文件。")
        return

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
            text = "".join(last_lines)
            if not text.strip():
                await message.reply("📭 当前日志文件为空。")
                return
            if len(text) > 3800:
                text = text[-3800:]
            await message.reply(f"🖥️ **底层引擎实时日志:**\n```text\n{text}\n```", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ 读取日志失败：{e}")

@dp.message(or_f(Command("balance"), F.text.in_({"查账", "余额", "查余额", "资产", "持仓"})))
async def fast_balance(message: types.Message):
    if HAS_QUANT:
        try:
            ui_text = await get_quant_account_status()
            try: await message.reply(ui_text, parse_mode="Markdown")
            except: await message.reply(ui_text) 
        except Exception as e:
            await message.reply(f"❌ 查账执行异常: {e}")

@dp.message(or_f(Command("closeall"), F.text.in_({"快跑", "一键平仓", "清仓", "平仓"})))
async def fast_emergency_close(message: types.Message):
    if HAS_QUANT:
        # 🌟 核心补丁：熔断前，先强行熄火 PM2 自动化引擎，防止它瞬间重新建仓！
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        # 静默执行关闭命令
        os.system(f"cd {CURRENT_DIR} && pm2 stop Quant-AutoTrader > /dev/null 2>&1")
        
        # 给用户一个安心的提示
        await message.reply("⚡ 正在强行切断后台自动化引擎，并执行全量平仓...", parse_mode="Markdown")
        
        ui_text = await emergency_close_all_positions()
        try: 
            await message.reply(ui_text, parse_mode="Markdown")
        except: 
            await message.reply(ui_text)

@dp.message(or_f(Command("start_auto"), F.text.in_({"开启自动交易", "出海", "开启航母"})))
async def start_auto_trading(message: types.Message):
    thinking_msg = await message.reply("⚙️ *点火中...*", parse_mode="Markdown")
    try:
        # 获取底层配置
        if HAS_QUANT:
            await arsenal.initialize()
            auto_cfg = arsenal.config.get('auto_trade', {})
        else:
            auto_cfg = {}

        # 精准锁定路径并启动 PM2
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        
        # 🌟 核心修复：每次点火前，先无情斩杀可能存在的所有历史克隆进程！
        os.system("pm2 delete Quant-AutoTrader > /dev/null 2>&1") 
        
        # 重新启动唯一的干净实例
        result = os.system(f"cd {CURRENT_DIR} && pm2 start main_auto_bot.py --name Quant-AutoTrader")
        
        if result == 0:
            # 读取配置详情用于UI展示
            symbols = auto_cfg.get('symbols', ["BTCUSDT"])
            base_amount = auto_cfg.get('base_amount', 0.01)
            rsi_oversold = auto_cfg.get('rsi_oversold', 30)
            rsi_overbought = auto_cfg.get('rsi_overbought', 70)
            atr_multiplier_sl = auto_cfg.get('atr_multiplier_sl', 2.0)
            atr_multiplier_tp = auto_cfg.get('atr_multiplier_tp', 1.5)
            interval = auto_cfg.get('interval_seconds', 15)
            use_trend_filter = auto_cfg.get('use_trend_filter', True)
            trend_ema = auto_cfg.get('trend_ema_period', 50)
            trend_tf = auto_cfg.get('trend_timeframe', '1h')
            
            # 组装帅气的战术面板
            report = (
                f"🚀 **航母已出港！自动化引擎启动**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"**策略配置**\n"
                f"• 💰监控币种: `{', '.join(symbols)}`\n"
                f"• 📚开仓数量: `{base_amount}`\n"
                f"• RSI阈值: 超卖 `{rsi_oversold}` / 超买 `{rsi_overbought}`\n"
                f"• 止损ATR倍数: `{atr_multiplier_sl}`\n"
                f"• 止盈ATR倍数: `{atr_multiplier_tp}`\n"
                f"• ⌛️扫描间隔: `{interval}` 秒\n"
                f"• 趋势过滤: `{'启用' if use_trend_filter else '禁用'}`\n"
                f"{f'  ├─ EMA周期: `{trend_ema}`' if use_trend_filter else ''}\n"
                f"{f'  └─ 时间框架: `{trend_tf}`' if use_trend_filter else ''}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📡 **实时日志**：发送 `/logs` 或 `pm2 logs Quant-AutoTrader`\n"
                f"🛡️ **风控规则**：已集成规则引擎（仓位限制、每日亏损熔断等）"
            )
            await thinking_msg.edit_text(report, parse_mode="Markdown")
        else:
            await thinking_msg.edit_text(f"❌ 点火失败，PM2 返回码: {result}", parse_mode="Markdown")
    except Exception as e:
        await thinking_msg.edit_text(f"❌ 点火失败: {e}")

@dp.message(or_f(Command("stop_auto"), F.text.in_({"停止自动交易", "返航", "关闭航母", "关闭自动交易"})))
async def stop_auto_trading(message: types.Message):
    thinking_msg = await message.reply("⚙️ *返航中...*", parse_mode="Markdown")
    try:
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        result = os.system(f"cd {CURRENT_DIR} && pm2 stop Quant-AutoTrader")
        if result == 0: 
            await thinking_msg.edit_text("⚓ **航母已熄火。** 自动交易已切断。", parse_mode="Markdown")
        else: 
            await thinking_msg.edit_text(f"❌ 熄火失败，PM2 返回码: {result}", parse_mode="Markdown")
    except Exception as e:
        await thinking_msg.edit_text(f"❌ 熄火失败: {e}")

import sqlite3

# ==========================================
# 🧠 参谋部核心逻辑：黑匣子数据提取与 AI 诊断
# ==========================================
async def generate_ai_trade_analysis() -> str:
    """读取 SQLite 黑匣子，并调用 LLM 生成专业的策略诊断研报"""
    db_path = Path(__file__).parent / "data" / "trade_history.db"
    has_real_data = False
    trade_data_str = ""
    
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # 提取最近的 30 笔交易记录用于分析
            cursor.execute("SELECT timestamp, symbol, side, entry_price, quantity, sl_price, tp_price FROM trades ORDER BY timestamp DESC LIMIT 30")
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                has_real_data = True
                for r in rows:
                    trade_data_str += f"时间:{r[0]}, 标的:{r[1]}, 方向:{r[2]}, 入场价:{r[3]:.4f}, 数量:{r[4]}, 止损价:{r[5]:.4f}, 止盈价:{r[6]:.4f}\n"
        except Exception as e:
            logging.error(f"读取数据库失败: {e}")
            
    if not has_real_data:
        # 🧪 伪造一份逼真的演示数据喂给 AI
        trade_data_str = """
[演示数据1] 时间:昨日, 标的:BTCUSDT, 方向:SELL, 入场:71000, 止损:72000, 止盈:69000 (结果:触及止损,亏损)
[演示数据2] 时间:昨日, 标的:ETHUSDT, 方向:BUY, 入场:2150, 止损:2100, 止盈:2225 (结果:触及止盈,盈利)
[演示数据3] 时间:今日, 标的:BTCUSDT, 方向:BUY, 入场:68000, 止损:67000, 止盈:69500 (结果:触及止损,亏损)
"""
        prompt_context = f"以下是【虚拟演示数据】。请你在报告开头明确标注【🧪 演示模式诊断】，然后基于这些虚拟数据，评估系统采用的(EMA50顺势+RSI30/70+ATR止盈止损)策略，指出可能存在的问题，并给出具体的参数优化建议：\n{trade_data_str}"
    else:
        prompt_context = f"以下是领哥机甲真实的近期开仓记录。请作为顶尖量化策略师，分析这些开仓位置的合理性，评估(EMA50顺势+RSI30/70+ATR止盈止损)策略在当前行情下的表现，必须给出【具体的参数调整建议】（如：建议将RSI超买改至75，ATR止损调至2.5等）：\n{trade_data_str}"

    messages = [
        {"role": "system", "content": "你是一位拥有十年华尔街对冲基金经验的首席高频量化分析师。你的回答必须极度专业、一针见血。请使用清晰的 Markdown 格式输出研报。"},
        {"role": "user", "content": prompt_context}
    ]
    
    try:
        response = await ai_client.chat.completions.create(model=AI_MODEL, messages=messages)
        analysis_text = sanitize_ai_output(response.choices[0].message.content)
        prefix = "🧪 **[系统演示] 历史战绩策略检诊报告**\n" if not has_real_data else "📈 **[实盘复盘] 策略运行深度诊断报告**\n"
        return prefix + "\n" + analysis_text
    except Exception as e:
        return f"❌ AI 策略诊断生成失败: {e}"

# ==========================================
# 🥇 新增指令：独立的策略复盘与优化触发器
# ==========================================
@dp.message(or_f(Command("analyze"), F.text.in_({"分析交易", "分析交易记录", "策略优化", "复盘", "复盘分析"})))
async def analyze_trades_handler(message: types.Message):
    thinking_msg = await message.reply("🧠 *参谋部正在调取历史战绩黑匣子，生成策略诊断报告...*", parse_mode="Markdown")
    try:
        ai_analysis_report = await generate_ai_trade_analysis()
        try:
            await thinking_msg.edit_text(ai_analysis_report, parse_mode="Markdown")
        except:
            await thinking_msg.edit_text(ai_analysis_report)
    except Exception as e:
        friendly_err = humanize_error(e, context="生成诊断报告")
        await thinking_msg.edit_text(friendly_err)
# ==========================================
@dp.message()
async def smart_ai_chat(message: types.Message):
    if not message.text: return
    thinking_msg = await message.reply("🧠 *参谋部推演中...*", parse_mode="Markdown")
    messages = [{"role": "system", "content": SOUL_PROMPT}, {"role": "user", "content": message.text}]
    
    try:
        response = await ai_client.chat.completions.create(model=AI_MODEL, messages=messages, tools=AI_TOOLS, tool_choice="auto")
        response_msg = response.choices[0].message
        
        clean_initial_text = sanitize_ai_output(response_msg.content)
        if "拦截器触发" in clean_initial_text:
            await thinking_msg.edit_text(clean_initial_text, parse_mode="Markdown")
            return

        trade_reports = [] 
        non_trade_results = []
        has_trade = False
        has_non_trade = False

        if response_msg.tool_calls:
            if not response_msg.content: response_msg.content = ""
            messages.append(response_msg) 
            
            for tool_call in response_msg.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                if func_name == "execute_ai_trade":
                    has_trade = True
                    symbol = func_args.get("symbol", "BTC")
                    side = func_args.get("side", "BUY")
                    amount = func_args.get("amount")
                    usdt_amount = func_args.get("usdt_amount")
                    tp_price = func_args.get("tp_price")
                    sl_price = func_args.get("sl_price")
                    
                    action_str = f"按 {usdt_amount} USDT" if usdt_amount else f"{amount} 个"
                    await thinking_msg.edit_text(f"⚔️ *正在为领哥执行 {side} {symbol} ({action_str}) 指令...*", parse_mode="Markdown")
                    
                    func_result = await execute_ai_trade(symbol, side, amount, usdt_amount, tp_price, sl_price)
                    try: trade_reports.append(json.loads(func_result).get("msg", "✅ 开仓完成"))
                    except Exception as e: trade_reports.append(f"❌ 开仓异常：{str(e)}")

                elif func_name == "set_position_tp_sl":
                    has_trade = True
                    symbol = func_args.get("symbol", "BTC")
                    tp_price = func_args.get("tp_price")
                    sl_price = func_args.get("sl_price")
                    
                    await thinking_msg.edit_text(f"🛡️ *正在为领哥的 {symbol} 仓位追加风控挂单...*", parse_mode="Markdown")
                    
                    func_result = await set_position_tp_sl(symbol, tp_price, sl_price)
                    try: trade_reports.append(json.loads(func_result).get("msg", "✅ 风控更新完成"))
                    except Exception as e: trade_reports.append(f"❌ 风控更新异常：{str(e)}")
                
                elif func_name == "fetch_crypto_data":
                    has_non_trade = True
                    await thinking_msg.edit_text("📡 *抓取盘口数据中...*", parse_mode="Markdown")
                    func_result = await fetch_crypto_data(func_args.get("symbol", "BTC"))
                    non_trade_results.append(f"📊 数据: {func_result}")
                elif func_name == "fetch_market_sentiment":
                    has_non_trade = True
                    func_result = await fetch_market_sentiment()
                    non_trade_results.append(f"📈 情绪: {func_result}")
                else:
                    func_result = "{}"
                    
                messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": func_result})

            if has_trade and not has_non_trade:
                final_content = "\n\n━━━━━━━━━━━━━━\n".join(trade_reports)
                try: await thinking_msg.edit_text(final_content, parse_mode="Markdown")
                except: await thinking_msg.edit_text(final_content)
                return

            elif has_non_trade:
                summary_prompt = "全维度数据已获取。现在，你必须结合这些数据，严格按照模板输出专业研报！"
                messages.append({"role": "user", "content": summary_prompt})
                final_response = await ai_client.chat.completions.create(model=AI_MODEL, messages=messages)
                final_content = sanitize_ai_output(final_response.choices[0].message.content)
                
                if trade_reports:
                    report_section = "\n\n━━━━━━━━━━━━━━\n".join(trade_reports)
                    final_content += f"\n\n━━━━━━━━━━━━━━\n**📋 交易战报**\n{report_section}"
                
                try: await thinking_msg.edit_text(final_content, parse_mode="Markdown")
                except: await thinking_msg.edit_text(final_content)
                return

            else:
                final_content = sanitize_ai_output(response_msg.content) or "⚠️ 未输出内容。"
                try: await thinking_msg.edit_text(final_content, parse_mode="Markdown")
                except: await thinking_msg.edit_text(final_content)
                return

        else:
            final_content = sanitize_ai_output(response_msg.content) or "⚠️ 未输出内容。"
            try: await thinking_msg.edit_text(final_content, parse_mode="Markdown")
            except: await thinking_msg.edit_text(final_content)

    except Exception as e:
        friendly_msg = humanize_error(e, context="参谋部推演")
        await thinking_msg.edit_text(friendly_msg)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 领哥机甲·独立网关点火起飞，独占电报频段！")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # 1. 启动前先上锁，全平台适用！
    enforce_single_instance()
    
    # 2. 正常点火
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🛑 收到本地退出指令，机甲已安全下线。")
