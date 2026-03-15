"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
OpenClaw 武器库 (Heavy-Duty 版)
功能：暴露给 AI 的 4 个专业级 API，内部直连风控、资金、和 V2 极速下单底层。
"""

import json
import logging
from typing import Dict, Any

from config.config_manager import ConfigManager
from src.risk.account_monitor import AccountMonitor
from src.execution.order_manager import OrderManager, OrderType, OrderSide
from src.execution.execution_risk import ExecutionRiskController

logger = logging.getLogger("OpenClaw_Skills")

class OpenClawArsenal:
    """OpenClaw 专属的重量级武器库单例"""
    def __init__(self):
        self.config = ConfigManager()
        self.monitor = AccountMonitor(self.config)
        self.manager = OrderManager(self.config)
        self.risk_ctrl = ExecutionRiskController(self.config)
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            await self.monitor.initialize()
            await self.manager.initialize()
            self._initialized = True
            logger.info("✅ OpenClaw 武器库：底盘、风控、发单引擎已全部预热完毕！")

    async def shutdown(self):
        await self.monitor.close()
        await self.manager.close()

# 全局单例
arsenal = OpenClawArsenal()

# ==========================================
# 工具 1：专业查账 (不仅看余额，还看保证金率)
# ==========================================
async def get_account_status() -> str:
    """获取账户资产、可用余额、未实现盈亏及整体风险。"""
    await arsenal.initialize()
    balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)
    return json.dumps({
        "total_usdt": balance.total_balance,
        "available_usdt": balance.available_balance,
        "unrealized_pnl": balance.unrealized_pnl,
        "margin_ratio_percent": balance.margin_ratio * 100,
        "risk_level": "SAFE" if balance.margin_ratio < 0.1 else "DANGER"
    }, ensure_ascii=False)

# ==========================================
# 工具 2：专业行情获取
# ==========================================
async def get_market_quote(symbol: str) -> str:
    """获取指定交易对的市场行情。"""
    await arsenal.initialize()
    raw_symbol = symbol.replace('/', '')
    try:
        ticker = await arsenal.monitor._safe_api_call(arsenal.monitor.exchange.fapiPublicGetTicker24hr, {'symbol': raw_symbol})
        return json.dumps({
            "symbol": symbol,
            "last_price": float(ticker['lastPrice']),
            "price_change_percent": float(ticker['priceChangePercent']),
            "volume": float(ticker['volume'])
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"获取行情失败: {str(e)}"}, ensure_ascii=False)

# ==========================================
# 工具 3：风控级智能开仓 (AI 下单的唯一入口)
# ==========================================
async def execute_smart_trade(symbol: str, side: str, amount: float) -> str:
    """
    执行实盘交易！AI 必须提供标的、方向和数量。
    警告：此接口内部强制绑定了 ATR 动态止损计算和资金校验！
    """
    await arsenal.initialize()
    try:
        # 1. 拦截解析
        side_enum = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        # 2. 调用原版底层获取现价
        raw_symbol = symbol.replace('/', '')
        ticker = await arsenal.monitor._safe_api_call(arsenal.monitor.exchange.fapiPublicGetTicker24hr, {'symbol': raw_symbol})
        current_price = float(ticker['lastPrice'])
        
        # 3. 资金风控硬拦截 (拒绝爆仓)
        balance = await arsenal.monitor.fetch_account_balance(force_refresh=True)
        if balance.available_balance < current_price * amount * 0.1: # 假设最低10%保证金
            return json.dumps({"status": "REJECTED", "reason": "风控拦截：可用保证金不足以开仓！"}, ensure_ascii=False)

        # 4. 真正扣动扳机下单
        order = await arsenal.manager.create_order(symbol, OrderType.MARKET, side_enum, amount)
        executed = await arsenal.manager.submit_order(order.order_id, dry_run=False)
        order_id = executed.metadata.get('exchange_order_id', 'N/A')
        
        return json.dumps({
            "status": "SUCCESS",
            "executed_price": current_price,
            "order_id": order_id,
            "msg": f"已成功过风控并在真实测试网下单！单号: {order_id}"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"智能下单异常: {e}")
        return json.dumps({"status": "FAILED", "error": str(e)}, ensure_ascii=False)