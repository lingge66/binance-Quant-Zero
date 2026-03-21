"""
OpenClaw 原生技能包：Binance Quant Agent (全量解封核武版 + 原生 UI 丝滑渲染)
功能：全维度暴露量化底座能力（风控试算、本地预测、执行单、极速查账 UI）。
"""
import os
import json
import logging
import re
import asyncio
from typing import Dict, Any, Optional

# ==========================================
# 🛠️ 绝对路径导入 (专为单体运行与开源适配)
# ==========================================
from config.config_manager import ConfigManager
from src.risk.account_monitor import AccountMonitor
from src.execution.order_manager import OrderManager, OrderType, OrderSide
from src.risk.rule_engine import RiskRuleEngine

logger = logging.getLogger("Skill_BinanceQuant_Ultra")

class QuantArsenal:
    """航母级量化引擎单例，统管所有子系统"""
    def __init__(self):
        self.config = ConfigManager()
        self.monitor = AccountMonitor(self.config)
        self.manager = OrderManager(self.config)
        self.rule_engine = RiskRuleEngine(self.config)
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            await self.monitor.initialize()
            await self.manager.initialize()
            self._initialized = True
            logger.info("✅ 航母级原生技能 [Binance Quant Ultra] 全系统预热完毕！")

arsenal = QuantArsenal()

# ==========================================
# 🛡️ 第一层：极速查账与 UI 渲染 (彭博终端级进化版)
# ==========================================
async def get_quant_account_status() -> str:
    await arsenal.initialize()
    try:
        balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)
        positions = await arsenal.monitor.fetch_positions()

        assets_lines = []
        real_total_usd = 0.0  

        if hasattr(balance, 'assets') and balance.assets:
            for asset, amount in balance.assets.items():
                if amount > 0:
                    assets_lines.append(f"{asset}: {amount:.2f}")
                    if 'USD' in asset:
                        real_total_usd += amount
        else:
            assets_lines = [f"总资产折合: {balance.total_balance:.2f} USDT (资产明细未提供)"]
            real_total_usd = balance.total_balance

        assets_str = " · ".join(assets_lines) if assets_lines else "无资产"
        final_total = max(real_total_usd, balance.total_balance)
        margin_ratio = balance.margin_ratio * 100

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
                
                pnl = float(getattr(p, 'unrealized_pnl', getattr(p, 'unrealizedProfit', 0)))
                pnl_str = f"+{pnl:.2f}" if pnl > 0 else f"{pnl:.2f}"
                pnl_icon = "🟩" if pnl > 0 else "🟥" if pnl < 0 else "⬜️"
                entry_price = float(getattr(p, 'entry_price', 0))
                
                pos_list.append(f"• {dir_icon} `{p.symbol}` : {abs(p_amt):g}\n  └─ {pnl_icon} 浮盈: `{pnl_str} U` | 均价: ${entry_price:.2f}")

        pos_str = "\n".join(pos_list) if pos_list else "> 🈳 **当前空仓，雷达待命。**"
        
        total_pnl = balance.unrealized_pnl
        pnl_header_icon = "🚀" if total_pnl > 0 else "📉" if total_pnl < 0 else "⚖️"

        report = f"""# 🔶 币安领哥金库终端 (Account Status)

💰 **总净资产:** `{final_total:.2f} USD`
{pnl_header_icon} **未实现盈亏:** `{total_pnl:+.2f} USDT`
🛡️ **风控使用率:** `{margin_ratio:.2f}%`

---
## 🪙 保证金金库 (Spot & Wallet)
> {assets_str}

---
## 📦 合约战阵 (Active Positions)
{pos_str}
"""
        return report

    except Exception as e:
        return f"❌ 查账失败: {str(e)}"

async def emergency_close_all_positions() -> str:
    """
    极速并发版熔断引擎 (Ultra-Fast Concurrent Close)
    """
    await arsenal.initialize()
    exchange = arsenal.monitor.exchange
    
    try:
        positions = await arsenal.monitor.fetch_positions()
        # 筛选出有实际仓位的币种
        active_positions = [p for p in positions if float(p.position_amount) != 0]

        if not active_positions:
            return "🟢 雷达扫描完毕，当前无持仓，无需平仓。"

        # ==========================================
        # 🚀 阶段 1：并发齐射撤销所有相关挂单 (释放保证金)
        # ==========================================
        cancel_tasks = []
        for p in active_positions:
            raw_symbol = p.symbol.split(':')[0].replace('/', '').upper()
            # 仅调用币安原生接口，速度最快
            cancel_tasks.append(exchange.fapiPrivateDeleteAllOpenOrders({'symbol': raw_symbol}))
            
        # 并发执行撤单，忽略个别没有挂单的报错
        await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        # 全局仅需等待 0.3 秒，确保币安底层保证金已释放 (切勿在循环内 sleep)
        await asyncio.sleep(0.3)

        # ==========================================
        # 💥 阶段 2：定义单币种极速平仓任务 (完美修复方向判定)
        # ==========================================
        async def close_single_position(p):
            amt_float = float(p.position_amount)
            raw_symbol = p.symbol.split(':')[0].replace('/', '').upper()
            amt = abs(amt_float)
            amt_str = f"{amt:.8f}".rstrip('0').rstrip('.') if '.' in f"{amt:.8f}" else f"{amt:.8f}"
            
            entry_price = float(getattr(p, 'entry_price', 0))
            pnl = float(getattr(p, 'unrealized_pnl', getattr(p, 'unrealizedProfit', 0)))
            
            # 🌟 终极修复：准确提取真实持仓方向，绝不依赖数量正负号！
            p_side_attr = str(getattr(p, 'position_side', getattr(p, 'positionSide', getattr(p, 'side', '')))).upper()
            
            if p_side_attr in ['SHORT', 'SELL']:
                is_long = False
            elif p_side_attr in ['LONG', 'BUY']:
                is_long = True
            else:
                is_long = (amt_float > 0)
                
            # 决定开平仓动作：多单用 SELL 平，空单用 BUY 平
            close_side_str = 'SELL' if is_long else 'BUY'
            # 决定持仓方向参数：保留原有的方向标记
            target_pos_side = p_side_attr if p_side_attr in ['LONG', 'SHORT'] else ('LONG' if is_long else 'SHORT')

            success = False
            last_error = ""

            for attempt in range(3):
                try:
                    await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': close_side_str, 'type': 'MARKET', 'quantity': amt_str, 'positionSide': target_pos_side})
                    success = True
                    break
                except Exception as e:
                    try: # 降级尝试 reduceOnly
                        await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': close_side_str, 'type': 'MARKET', 'quantity': amt_str, 'reduceOnly': 'true'})
                        success = True
                        break
                    except Exception as e2:
                        try: # 降级尝试单向持仓模式
                            await exchange.fapiPrivatePostOrder({'symbol': raw_symbol, 'side': close_side_str, 'type': 'MARKET', 'quantity': amt_str})
                            success = True
                            break
                        except Exception as e3:
                            last_error = str(e3)
                
                if not success:
                    await asyncio.sleep(0.5)

            return {
                "success": success, "symbol": raw_symbol, "amt_str": amt_str, 
                "pnl": pnl, "entry_price": entry_price, "error": last_error, 
                "is_long": is_long # 传递真实方向给 UI 渲染
            }

        # ==========================================
        # ⚡️ 阶段 3：全军出击！并发执行所有平仓任务
        # ==========================================
        close_tasks = [close_single_position(p) for p in active_positions]
        results_data = await asyncio.gather(*close_tasks, return_exceptions=True)

        # ==========================================
        # 📊 阶段 4：清算战损与 UI 渲染
        # ==========================================
        results, errors = [], []
        total_realized_pnl = 0.0

        for res in results_data:
            if isinstance(res, Exception):
                errors.append(f"❌ 系统级异常: {str(res)}")
                continue

            pnl_str = f"+{res['pnl']:.2f}" if res['pnl'] > 0 else f"{res['pnl']:.2f}"
            pnl_icon = "🟩" if res['pnl'] > 0 else "🟥" if res['pnl'] < 0 else "⬜️"
            # 🌟 使用真实方向渲染 UI，告别颠倒黑白
            dir_icon = "🟢多单" if res['is_long'] else "🔴空单"

            if res['success']:
                total_realized_pnl += res['pnl']
                results.append(f"• {dir_icon} `{res['symbol']}` | 平仓数量: {res['amt_str']}\n  └─ {pnl_icon} 结算盈亏: `{pnl_str} U` | 原开仓均价: ${res['entry_price']:.2f}")
            else:
                errors.append(f"❌ `{res['symbol']}`: 历经3轮强制平仓仍被币安拒绝 - {res['error']}")

        balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)

        msg_parts = []
        if results:
            total_pnl_icon = "💰" if total_realized_pnl >= 0 else "🩸"
            header = "🚨 **极速熔断指令执行完毕 (ALL POSITIONS CLOSED)**\n━━━━━━━━━━━━━━\n"
            body = "\n".join(results)
            footer = f"\n━━━━━━━━━━━━━━\n{total_pnl_icon} **本次平仓总盈亏 (估)**: `{total_realized_pnl:+.2f} USDT`\n🏦 **清算后净资产**: `{balance.total_balance:.2f} USD`"
            msg_parts.append(header + body + footer)
            
        if errors:
            msg_parts.append("\n⚠️ **【严重警报】以下仓位未能平掉，请立即登入交易所人工接管：**\n" + "\n".join(errors))

        return "".join(msg_parts)

    except Exception as e:
        return f"❌ 紧急平仓遭遇全局崩溃: {str(e)}"
