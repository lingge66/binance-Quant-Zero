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
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, or_f
from aiogram.client.session.aiohttp import AiohttpSession
from openai import AsyncOpenAI 
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - ⚡ 领哥独立网关 - %(message)s')

# ==========================================
# 🛠️ 终极路径破解：让 Python 认出自己的家
# ==========================================
SKILLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)

try:
    from binance_agent_lingge import get_quant_account_status, emergency_close_all_positions, arsenal
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
# 🧠 顶级量化副官的灵魂设定 (高阶语义与风控全能版)
# ==========================================
SOUL_PROMPT = """
你是领哥的专属首席量化交易策略师（代号：Quant-Zero）。你拥有华尔街顶尖对冲基金的逻辑。

【合约语义解析与执行军规】（最高优先级）：
1. 识别多空方向：'开多/做多/买入/看涨' 统一解析为 `side="BUY"`；'开空/做空/卖出/看跌' 统一解析为 `side="SELL"`。
2. 资金换算：如果领哥说按 U 开仓（例如'买1000U的ETH'），调用开仓工具时必须使用 `usdt_amount` 参数。如果是按个数（例如'买1个ETH'），使用 `amount` 参数。
3. 独立补挂风控：如果指令仅仅是'给ETH设置止损1800'或'改一下止盈'（无明确开新仓动作），**绝对禁止**调用 execute_ai_trade，必须调用专用的 `set_position_tp_sl` 工具！

【行情推演军规】：
抛弃散户思维，以“流动性”、“订单块”及“硬核技术指标共振”为核心。永远将盈亏比放在第一位。
⚠️ 收到行情查询时，你必须严格按照以下 Markdown 模板输出（绝对禁止改变标题层级或遗漏模块，每个大标题前使用分割线 ---，长段落必须换行，价格数字使用反引号 ` 包裹）：

# 🟢 [币种] 当前市价: `[价格] USDT`

## 📡 侦察阶段 (Core Data)

* **24H 涨跌幅:** `[百分比]`
* **24H 高低点:** `[最高价]` / `[最低价]`
* **24H 成交量:** `[数值]`
* **资金费率 & 情绪:** `[费率]` / `[恐慌贪婪指数]`

---

## 🧮 深度技术指标 (Technical Analysis)

* **EMA均线系统:** [简述当前状态]
  > *警示/注意：*[补充多空博弈的关键细节]

* **ATR (真实波动率):** [估算日内波幅，长段落注意换行阅读体验]

* **MACD & RSI动能:** [背离情况、超买超卖、动能强弱]

---

## 📊 盘面测绘 (Market Context & SMC)

* **当前位置:** [溢价区/折价区，基于近期高低点分析]

* **流动性猎取 (Liquidity Sweep):** [指出近期狙击止损的行为]
  > *高价值流动性池：*[明确指出买方/卖方的具体价位]

* **主力意图推演:** [结合未平仓合约 OI 和资金费率，分析主力是逼空、洗盘还是建仓。字数多必须分段！]

---

## 🎯 机构级战术预案 (Action Plan)

> **核心观点:** [短线震荡偏多/看跌/观望 等，给出明确一句话结论]

* **📍 入场区间 (Entry Zone):** `[价格区间]`
  *([左侧/右侧的逻辑说明])*

* **🛑 失效位 (Invalidation/SL):** `[止损价位]`
  *([逻辑被破坏的说明])*

* **🎯 目标位 (Take Profit):**
  * **TP1 (第一流动性目标):** `[价格]` *([说明])*
  * **TP2 (最终订单块目标):** `[价格]` *([说明])*

* **⚖️ 盈亏比预估 (R/R):**
  * 若 `[入场价]` 入场，止损 `[止损价]` ➡️ TP1 `[价格]`，盈亏比约为 **1 : [数值]**。
  * 若 `[入场价]` 入场，止损 `[止损价]` ➡️ TP2 `[价格]`，盈亏比约为 **1 : [数值]**。
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

        # U 本位自动折算代币数量逻辑
        if usdt_amount and not amount:
            try:
                ticker = await exchange.fapiPublicGetTickerPrice({'symbol': raw_symbol})
                current_price = float(ticker['price'])
                amount = round(usdt_amount / current_price, 3) 
            except Exception as e:
                return json.dumps({"status": "ERROR", "msg": f"❌ 转换U本位金额失败: {str(e)}"})
        
        if not amount or amount <= 0:
            return json.dumps({"status": "ERROR", "msg": "❌ 开仓数量无效。"})

        amt_str = f"{amount:g}"
        pos_side = None

        # 1. 执行开仓
        try:
            pos_side = 'LONG' if side_str == 'BUY' else 'SHORT'
            open_order = await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': side_str, 'type': 'MARKET', 'quantity': amt_str, 'positionSide': pos_side})
        except Exception:
            pos_side = None 
            open_order = await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': side_str, 'type': 'MARKET', 'quantity': amt_str})

        await asyncio.sleep(1)
        positions = await arsenal.monitor.fetch_positions()
        # 智能匹配刚刚开仓的方向
        target_position = next((p for p in positions if p.symbol == raw_symbol and float(p.position_amount) != 0 and (not pos_side or str(getattr(p, 'positionSide', getattr(p, 'side', ''))).upper() == pos_side)), None)
        entry_price = target_position.entry_price if target_position else 0.0

        # 2. 挂载 Algo 风控单
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

        # 3. 🎯 核心升级：智能生成带【多/空】标签的持仓列表
        balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)
        pos_list = []
        for p in positions:
            p_amt = float(p.position_amount)
            if p_amt != 0:
                p_side_attr = str(getattr(p, 'position_side', getattr(p, 'positionSide', getattr(p, 'side', '')))).upper()
                if p_side_attr in ['SHORT', 'SELL']:
                    dir_icon = "🔴空单"
                elif p_side_attr in ['LONG', 'BUY']:
                    dir_icon = "🟢多单"
                else:
                    dir_icon = "🟢多单" if p_amt > 0 else "🔴空单"
                pos_list.append(f"{dir_icon} {p.symbol} ({abs(p_amt):g})")
        
        pos_str = "、".join(pos_list) if pos_list else "无持仓"
        
        msg_lines = [f"✅ 成功开仓 {side_str} {amount} {raw_symbol}，成交均价 ${entry_price:.2f}"]
        if tp_status: msg_lines.append(tp_status)
        if sl_status: msg_lines.append(sl_status)

        # 🚨 风控警报
        if not tp_price and not sl_price:
            msg_lines.append("\n🚨 **【风控最高警报】当前仓位处于裸奔状态！**")
            msg_lines.append("⚠️ 参谋部强烈建议：合约如履薄冰，请立刻回复指令补充止损（例如：“给BTC设置止损71000”），或保持严密盯盘！")
        elif not sl_price:
            msg_lines.append("\n⚠️ **【风控提示】** 检测到当前仅挂载止盈，未设置止损 (SL)。请注意防范插针风险！")

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

        # 获取现价用于智能推断
        try:
            ticker = await exchange.fapiPublicGetTickerPrice({'symbol': raw_symbol})
            current_price = float(ticker['price'])
        except:
            current_price = 0

        # 🧠 智能推断引擎：到底是给多单挂还是给空单挂？
        is_long = True
        target_pos = active_positions[0]

        if len(active_positions) == 1:
            p_side_attr = str(getattr(target_pos, 'position_side', getattr(target_pos, 'positionSide', getattr(target_pos, 'side', '')))).upper()
            if p_side_attr in ['SHORT', 'SELL']:
                is_long = False
            elif p_side_attr in ['LONG', 'BUY']:
                is_long = True
            else:
                is_long = float(target_pos.position_amount) > 0
        else:
            # 遇到多空双开：用价格逻辑判断！
            if current_price > 0:
                if sl_price:
                    is_long = sl_price < current_price # 止损价 < 现价 = 多单
                elif tp_price:
                    is_long = tp_price > current_price # 止盈价 > 现价 = 多单
            
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
# 🧰 AI 工具箱清单 (注册新工具)
# ==========================================
AI_TOOLS = [
    {"type": "function", "function": {"name": "fetch_crypto_data", "description": "获取实时OHLCV与OI等机构级数据", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "fetch_market_sentiment", "description": "获取市场恐慌贪婪指数", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "execute_ai_trade", "description": "执行市价开新仓。按代币数开仓用 amount；按 U 开仓用 usdt_amount。", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "side": {"type": "string", "description": "BUY 或 SELL"}, "amount": {"type": "number"}, "usdt_amount": {"type": "number"}, "tp_price": {"type": "number"}, "sl_price": {"type": "number"}}, "required": ["symbol", "side"]}}},
    {"type": "function", "function": {"name": "set_position_tp_sl", "description": "为已有的持仓单独追加或修改止盈止损。仅在用户不要求新开仓，只要求设置止损/止盈时调用。", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "tp_price": {"type": "number"}, "sl_price": {"type": "number"}}, "required": ["symbol"]}}}
]

def sanitize_ai_output(text: str) -> str:
    if not text: return ""
    if re.search(r'(<｜DSML｜|invoke name|functioncalls)', text, re.IGNORECASE):
        return "⚠️ **参谋部拦截器触发**：引擎遭遇底层格式泄露。请领哥再发一次刚才的指令！"
    return text

import re
import yaml
from pathlib import Path
from aiogram.filters import CommandStart, Command

# ==========================================
# 🥇 第一道防线：新手向导 (一键触控引导版)
# ==========================================
@dp.message(CommandStart())
@dp.message(Command("help"))
async def send_welcome(message: types.Message):
    welcome_text = """
🌌 **[系统在线] 领哥量化机甲 (Quant-Zero V1.0 满配版)**
======================================
您好，指挥官。我是您的专属首席量化交易策略师。
本终端已直连 Binance USD-M 核心撮合引擎，具备「极速执行」与「SMC机构级推演」双核大脑。

请下达您的战术指令：

⚡️ **【物理控制台】(零延迟点触指令)**
👉 /balance ：调出彭博级资产与多空持仓面板 (或发 `查账` `资产`)
👉 /closeall ：最高危！一键市价熔断所有仓位 (或发 `快跑` `平仓`)
👉 /logs 15 ：调取底层引擎实时运行日志 (或发 `看日志`)
👉 /add_symbol ：将新标的纳入最高雷达监控 (或发 `添加监控 SOL`)

⚔️ **【实盘狙击指令】(支持自然语言与U本位自动换算)**
💬 `做空 1000U 的 BTC，止损 75000`
💬 `买入 2 个 ETH，止盈 2500，止损 1800`
*(机甲将自动测算仓位、换算U本位，并调用 Algo 引擎挂载防插针风控)*

🛡️ **【独立风控指令】(为裸奔仓位极速上膛)**
💬 `给 ETH 补个 1800 的止损`
💬 `把 BNB 的止盈设置在 660`
*(机甲将启动上帝视角，智能识别你的多空方向并精准追加风控单)*

🧠 **【SMC 机构级推演】(寻找流动性与订单块)**
💬 `深度分析一下 SOL 的多空动能`
💬 `帮我看看现在 BTC 的资金费率和流动性池在哪？`
*(机甲将抓取 48H OHLCV 矩阵与持仓量，输出带盈亏比的华尔街级研报)*

======================================
📡 **等待指令中... (Type your command)**
"""
    await message.reply(welcome_text, parse_mode="Markdown")

# ==========================================
# 🌟 [展示级功能] 特工雷达：中英双语动态增减交易对
# ==========================================
@dp.message(lambda msg: msg.text and re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s*([a-zA-Z0-9/]+)$', msg.text.strip(), re.IGNORECASE))
async def add_symbol_handler(message: types.Message):
    """动态添加监控标的，彰显 Agent 交互感 (支持中文自然语言及无空格盲打)"""
    match = re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s*([a-zA-Z0-9/]+)$', message.text.strip(), re.IGNORECASE)
    symbol = match.group(1).replace('/', '').upper()
    if not symbol.endswith('USDT'): symbol += 'USDT'  # 自动补全 USDT

    config_path = Path(__file__).parent / "config" / "config.yaml"

    if not config_path.exists():
        await message.reply("❌ **系统异常**：未能定位到雷达配置文件 `config/config.yaml`")
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}

        if 'auto_trade' not in cfg: cfg['auto_trade'] = {}
        if 'symbols' not in cfg['auto_trade']: cfg['auto_trade']['symbols'] = []

        if symbol not in cfg['auto_trade']['symbols']:
            cfg['auto_trade']['symbols'].append(symbol)
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
            
            await message.reply(f"✅ **指令确认：雷达扩容**\n特工引擎已听从您的指挥，将 `{symbol}` 纳入最高级别行情监控序列！底层配置已热更新。", parse_mode="Markdown")
        else:
            await message.reply(f"ℹ️ **重复指令**\n指挥官，`{symbol}` 早已在我们的监控雷达中了。")
    except Exception as e:
        await message.reply(f"❌ 动态写入配置失败：{e}")

# ==========================================
# 🌟 [展示级功能] 极客终端：中英双语查日志
# ==========================================
@dp.message(lambda msg: msg.text and re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', msg.text.strip()))
async def logs_handler(message: types.Message):
    """远程拉取底层日志，彰显硬核透明度 (支持中文自然语言)"""
    match = re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', message.text.strip())
    
    lines_str = match.group(1)
    lines = int(lines_str) if lines_str else 20
    if lines > 100: lines = 100

    log_file = Path(__file__).parent / "logs" / "agent.log" 
    
    if not log_file.exists():
        await message.reply("⚠️ **日志系统离线**\n未找到底层日志文件。请确认自动交易引擎是否已启动。")
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

            await message.reply(f"🖥️ **底层引擎实时日志 (最近 {lines} 行):**\n```text\n{text}\n```", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ 读取日志扇区失败：{e}")

# ==========================================
# (下方保留你原本处理其他 AI 对话和核心开单的逻辑...)
# ==========================================

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
        ui_text = await emergency_close_all_positions()
        try: await message.reply(ui_text, parse_mode="Markdown")
        except: await message.reply(ui_text) 

@dp.message(or_f(Command("start_auto"), F.text.in_({"开启自动交易", "出海", "开启航母"})))
async def start_auto_trading(message: types.Message):
    thinking_msg = await message.reply("⚙️ *点火中...*", parse_mode="Markdown")
    try:
        # 先确保 arsenal 已初始化，以便读取配置
        await arsenal.initialize()
        
        # 执行 PM2 启动命令
        result = os.system("cd /home/lingge/.openclaw/skills/binance_agent_lingge && pm2 start main_auto_bot.py --name Quant-AutoTrader")
        
        if result == 0:
            # 读取自动交易配置
            auto_cfg = arsenal.config.get('auto_trade', {})
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
            
            # 构建详细报告
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
                f"📡 **实时日志**：`pm2 logs Quant-AutoTrader`\n"
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
        result = os.system("cd /home/lingge/.openclaw/skills/binance_agent_lingge && pm2 stop Quant-AutoTrader")
        if result == 0: await thinking_msg.edit_text("⚓ **航母已熄火。** 自动交易已切断。", parse_mode="Markdown")
        else: await thinking_msg.edit_text(f"❌ 熄火失败，PM2 返回码: {result}", parse_mode="Markdown")
    except Exception as e:
        await thinking_msg.edit_text(f"❌ 熄火失败: {e}")

# ==========================================
# 🧠 AI 大脑中枢 (多动作协同处理)
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
        if "参谋部拦截器触发" in clean_initial_text:
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
                
                # 处理开新仓
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

                # 🚀 新增：处理单独补挂风控
                elif func_name == "set_position_tp_sl":
                    has_trade = True
                    symbol = func_args.get("symbol", "BTC")
                    tp_price = func_args.get("tp_price")
                    sl_price = func_args.get("sl_price")
                    
                    await thinking_msg.edit_text(f"🛡️ *正在为领哥的 {symbol} 仓位追加风控挂单...*", parse_mode="Markdown")
                    
                    func_result = await set_position_tp_sl(symbol, tp_price, sl_price)
                    try: trade_reports.append(json.loads(func_result).get("msg", "✅ 风控更新完成"))
                    except Exception as e: trade_reports.append(f"❌ 风控更新异常：{str(e)}")
                
                # 处理行情分析
                elif func_name == "fetch_crypto_data":
                    has_non_trade = True
                    await thinking_msg.edit_text("📡 *抓取盘口全量数据中...*", parse_mode="Markdown")
                    func_result = await fetch_crypto_data(func_args.get("symbol", "BTC"))
                    non_trade_results.append(f"📊 {func_name}: {func_result}")
                elif func_name == "fetch_market_sentiment":
                    has_non_trade = True
                    await thinking_msg.edit_text("📡 *抓取宏观恐慌指数中...*", parse_mode="Markdown")
                    func_result = await fetch_market_sentiment()
                    non_trade_results.append(f"📈 {func_name}: {func_result}")
                else:
                    func_result = "{}"
                    
                messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": func_result})

            if has_trade and not has_non_trade:
                final_content = "\n\n━━━━━━━━━━━━━━\n".join(trade_reports)
                try: await thinking_msg.edit_text(final_content, parse_mode="Markdown")
                except: await thinking_msg.edit_text(final_content)
                return

            elif has_non_trade:
                summary_prompt = "全维度数据已获取。现在，你必须结合这些数据，严格按照模板输出专业研报，并给出支撑和阻力位预测！"
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
        await thinking_msg.edit_text(f"❌ 参谋部神经断开: {e}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 领哥机甲·独立网关点火起飞，独占电报频段！")
    await dp.start_polling(bot)
import re
import yaml
from pathlib import Path

# ==========================================
# 🌟 [展示级功能] 特工雷达：中英双语动态增减交易对
# ==========================================
@dp.message(lambda msg: msg.text and re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s+([a-zA-Z0-9/]+)$', msg.text.strip(), re.IGNORECASE))
async def add_symbol_handler(message: types.Message):
    """动态添加监控标的，彰显 Agent 交互感 (支持中文自然语言)"""
    # 提取用户意图中的币种名称
    match = re.match(r'^(?:/add_symbol|添加监控|增加标的|监控|添加)\s+([a-zA-Z0-9/]+)$', message.text.strip(), re.IGNORECASE)
    symbol = match.group(1).replace('/', '').upper()
    if not symbol.endswith('USDT'): symbol += 'USDT'  # 自动补全 USDT 防呆

    config_path = Path(__file__).parent / "config" / "config.yaml"

    if not config_path.exists():
        await message.reply("❌ **系统异常**：未能定位到雷达配置文件 `config/config.yaml`")
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}

        if 'auto_trade' not in cfg: cfg['auto_trade'] = {}
        if 'symbols' not in cfg['auto_trade']: cfg['auto_trade']['symbols'] = []

        if symbol not in cfg['auto_trade']['symbols']:
            cfg['auto_trade']['symbols'].append(symbol)
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
            
            await message.reply(f"✅ **指令确认：雷达扩容**\n特工引擎已听从您的指挥，将 `{symbol}` 纳入最高级别行情监控序列！底层配置已热更新。", parse_mode="Markdown")
        else:
            await message.reply(f"ℹ️ **重复指令**\n指挥官，`{symbol}` 早已在我们的监控雷达中了。")
    except Exception as e:
        await message.reply(f"❌ 动态写入配置失败：{e}")


# ==========================================
# 🌟 [展示级功能] 极客终端：中英双语查日志
# ==========================================
@dp.message(lambda msg: msg.text and re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', msg.text.strip()))
async def logs_handler(message: types.Message):
    """远程拉取底层日志，彰显硬核透明度 (支持中文自然语言)"""
    match = re.match(r'^(?:/logs|查看日志|看日志|系统日志|日志)(?:\s+(\d+))?$', message.text.strip())
    
    # 提取想要查看的行数，如果没有输数字，默认看最后 20 行
    lines_str = match.group(1)
    lines = int(lines_str) if lines_str else 20
    if lines > 100: lines = 100  # 防止 Telegram 消息超长炸群

    # 自动定位日志文件（确保这里与你实际的日志路径一致，通常在 logs/agent.log）
    log_file = Path(__file__).parent / "logs" / "agent.log" 
    
    if not log_file.exists():
        await message.reply("⚠️ **日志系统离线**\n未找到底层日志文件。请确认自动交易引擎是否已启动。")
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

            await message.reply(f"🖥️ **底层引擎实时日志 (最近 {lines} 行):**\n```text\n{text}\n```", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ 读取日志扇区失败：{e}")
if __name__ == "__main__":
    asyncio.run(main())
