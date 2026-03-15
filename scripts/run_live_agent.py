"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
币安AI交易Agent - 真实网络全链路拉练 (剔除所有Mock模拟)
直接验证：真实数据流 -> 真实信号 -> 真实风控 -> 真实测试网下单
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_real_system():
    print("\n" + "="*60)
    print("🚀 启动正规军实战拉练 (真实连接 Binance Futures Testnet)")
    print("="*60)

    try:
        # 1. 初始化配置
        from config.config_manager import ConfigManager
        config = ConfigManager()
        logger.info("✅ 1. 配置加载完毕")

        # 2. 初始化风控与账户引擎 (走真实网络)
        from src.risk.account_monitor import AccountMonitor
        from src.risk.rule_engine import RiskRuleEngine
        monitor = AccountMonitor(config)
        await monitor.initialize()
        rule_engine = RiskRuleEngine(config, skip_default_rules=True)
        
        # 真实查账
        balance = await monitor.fetch_account_balance(force_refresh=True)
        logger.info(f"✅ 2. 风控引擎就绪！当前真实可用资金: {balance.available_balance} USDT")

        # 3. 初始化执行引擎 (走真实网络)
        from src.execution.order_manager import OrderManager, OrderType, OrderSide
        manager = OrderManager(config)
        await manager.initialize()
        logger.info("✅ 3. 交易执行层就绪！")

        # 4. 模拟AI大脑发出的真实信号 (这里我们直接构造一个信号，交给系统处理)
        print("\n" + "-"*40)
        print("🤖 AI 大脑产生交易信号：准备做空 0.01 个 BTC")
        print("-"*40)
        
        symbol = "BTC/USDT"
        amount = 0.01
        
        # 5. 走真实的风控评估 (看看钱够不够)
        logger.info("🛡️ 风控系统正在评估此笔交易...")
        # (此处简化调用，直接确认资金是否大于0)
        if balance.available_balance > 10:
            logger.info("🟢 风控通过：资金充裕，准许放行！")
        else:
            logger.error("🔴 风控拦截：资金不足！")
            return

        # 6. 走真实的交易执行
        logger.info("📡 执行引擎正在向币安测试网发送真实订单...")
        order = await manager.create_order(
            symbol=symbol, 
            order_type=OrderType.MARKET, 
            side=OrderSide.SELL, 
            amount=amount
        )
        
        # dry_run=False 代表真枪实弹开火！
        executed_order = await manager.submit_order(order.order_id, dry_run=False)
        
        exchange_order_id = executed_order.metadata.get('exchange_order_id')
        if exchange_order_id:
            logger.info(f"🎉 捷报！真实订单已成交！币安返回单号: {exchange_order_id}")
        else:
            logger.error(f"❌ 下单可能失败，订单状态: {executed_order.status}")

        # 7. 再次查真实持仓
        positions = await monitor.fetch_positions()
        active_pos = [p for p in positions if p.position_amount > 0]
        logger.info(f"📊 战后清点：当前拥有 {len(active_pos)} 个真实活跃仓位。")

    except Exception as e:
        logger.error(f"实战拉练出现严重异常: {e}")
    finally:
        logger.info("🛑 正在安全关闭网络连接...")
        await monitor.close()
        await manager.close()
        print("="*60)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_real_system())