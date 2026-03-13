"""
高级规则引擎测试 - 验证时间窗口、相关性风险、市场自适应规则

测试内容：
1. 时间窗口交易频率规则
2. 相关性风险暴露规则
3. 市场波动自适应规则
4. 流动性风险控制规则
5. 配置文件动态加载

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import sys
import time
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from binance_ai_agent.src.risk.rule_engine import (
    RiskRuleEngine, RuleType, RulePriority, RiskRule, 
    TradeContext, AccountContext, RuleResult
)
from binance_ai_agent.config.config_manager import ConfigManager


class TestAdvancedRules(unittest.TestCase):
    """高级规则测试"""
    
    def setUp(self):
        """测试准备"""
        self.config = ConfigManager()
        self.engine = RiskRuleEngine(self.config, skip_default_rules=True)
        
        # 确保规则引擎为空状态
        self.engine.rules.clear()
        self.engine._trade_history.clear()
        self.engine._evaluation_cache.clear()
        
        # 调试输出
        print(f"[DEBUG] setUp: 规则数量 = {len(self.engine.rules)}")
        
    async def test_trading_frequency_rule(self):
        """测试交易频率规则"""
        # 添加交易频率规则
        frequency_rule = RiskRule(
            rule_id="test_frequency",
            rule_name="测试频率规则",
            rule_type=RuleType.TRADING_FREQUENCY,
            priority=RulePriority.MEDIUM,
            parameters={
                "max_trades_per_hour": 2,
                "window_hours": 1
            },
            description="测试交易频率限制"
        )
        self.engine.add_rule(frequency_rule)
        
        # 创建交易上下文
        trade_context = TradeContext(
            symbol="BTC/USDT",
            position_side="long",
            entry_price=50000.0,
            current_price=51000.0,
            position_size=0.1,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            leverage=3.0,
            timestamp=int(time.time() * 1000)
        )
        
        account_context = AccountContext(
            total_balance=10000.0,
            available_balance=5000.0,
            margin_ratio=0.5,
            total_position_value=3000.0,
            daily_pnl=200.0,
            weekly_pnl=500.0,
            open_positions=[trade_context],
            timestamp=int(time.time() * 1000)
        )
        
        # 第一次评估应该通过
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=True
        )
        
        # 检查结果
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed, "第一次评估应该通过")
        
        # 第二次评估应该通过
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=True
        )
        self.assertTrue(results[0].passed, "第二次评估应该通过")
        
        # 第三次评估应该失败（超过2次限制）
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=True
        )
        self.assertFalse(results[0].passed, "第三次评估应该失败（超过限制）")
        self.assertIn("超限", results[0].message)
        
        print("✅ 交易频率规则测试通过")
    
    async def test_correlation_risk_rule(self):
        """测试相关性风险规则"""
        # 添加相关性风险规则
        correlation_rule = RiskRule(
            rule_id="correlation_risk_exposure",
            rule_name="相关性风险暴露",
            rule_type=RuleType.RISK_EXPOSURE,
            priority=RulePriority.MEDIUM,
            parameters={
                "max_correlated_exposure": 0.3,
                "correlation_threshold": 0.7
            },
            description="测试相关性风险限制"
        )
        self.engine.add_rule(correlation_rule)
        
        # 创建交易上下文（BTC/USDT）
        trade_context = TradeContext(
            symbol="BTC/USDT",
            position_side="long",
            entry_price=50000.0,
            current_price=51000.0,
            position_size=0.1,  # 价值约5000 USDT
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            leverage=3.0,
            timestamp=int(time.time() * 1000)
        )
        
        # 创建已有持仓（ETH/USDT，与BTC高度相关）
        existing_position = TradeContext(
            symbol="ETH/USDT",
            position_side="long",
            entry_price=3000.0,
            current_price=3100.0,
            position_size=1.0,  # 价值约3100 USDT
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            leverage=2.0,
            timestamp=int(time.time() * 1000)
        )
        
        account_context = AccountContext(
            total_balance=10000.0,
            available_balance=5000.0,
            margin_ratio=0.5,
            total_position_value=8100.0,  # BTC 5000 + ETH 3100
            daily_pnl=200.0,
            weekly_pnl=500.0,
            open_positions=[existing_position],
            timestamp=int(time.time() * 1000)
        )
        
        # 评估规则
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=False
        )
        
        # 相关性仓位占比 = (5000 + 3100) / 10000 = 0.81 > 0.3，应该失败
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed, "相关性风险应该触发")
        self.assertIn("相关性风险", results[0].message)
        
        print("✅ 相关性风险规则测试通过")
    
    async def test_market_volatility_rule(self):
        """测试市场波动自适应规则"""
        # 添加市场波动规则
        volatility_rule = RiskRule(
            rule_id="market_volatility_adaptive",
            rule_name="市场波动自适应",
            rule_type=RuleType.CUSTOM,
            priority=RulePriority.MEDIUM,
            parameters={
                "high_volatility_threshold": 0.15,
                "position_reduction_percent": 0.5
            },
            description="测试市场波动自适应"
        )
        self.engine.add_rule(volatility_rule)
        
        # 创建交易上下文
        trade_context = TradeContext(
            symbol="BTC/USDT",
            position_side="long",
            entry_price=50000.0,
            current_price=51000.0,
            position_size=0.2,  # 较大仓位
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            leverage=3.0,
            timestamp=int(time.time() * 1000)
        )
        
        account_context = AccountContext(
            total_balance=10000.0,
            available_balance=5000.0,
            margin_ratio=0.5,
            total_position_value=5000.0,
            daily_pnl=200.0,
            weekly_pnl=500.0,
            open_positions=[trade_context],
            timestamp=int(time.time() * 1000)
        )
        
        # 评估规则（简化实现中市场波动率固定为0.1）
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=False
        )
        
        # 由于简化实现中市场波动率固定为0.1 < 0.15，应该通过
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed, "市场波动正常时应通过")
        self.assertIn("市场波动正常", results[0].message)
        
        print("✅ 市场波动自适应规则测试通过")
    
    async def test_config_file_loading(self):
        """测试配置文件加载"""
        # 创建测试规则文件
        test_rules = [
            {
                "rule_id": "test_loaded_rule",
                "rule_name": "测试加载规则",
                "rule_type": "stop_loss",
                "priority": 75,
                "enabled": True,
                "parameters": {"stop_loss_percent": 0.03},
                "description": "从文件加载的测试规则"
            }
        ]
        
        import json
        import tempfile
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_rules, f)
            temp_file = f.name
        
        try:
            # 加载规则
            success = self.engine.load_rules_from_file(temp_file)
            self.assertTrue(success, "规则加载应该成功")
            
            # 验证规则已加载
            rule = self.engine.get_rule("test_loaded_rule")
            self.assertIsNotNone(rule, "规则应该被加载")
            self.assertEqual(rule.rule_name, "测试加载规则")
            self.assertEqual(rule.parameters["stop_loss_percent"], 0.03)
            
            print("✅ 配置文件加载测试通过")
        finally:
            # 清理临时文件
            os.unlink(temp_file)
    
    async def test_performance_optimization(self):
        """测试性能优化"""
        # 添加多个规则
        for i in range(10):
            rule = RiskRule(
                rule_id=f"test_rule_{i}",
                rule_name=f"测试规则{i}",
                rule_type=RuleType.STOP_LOSS,
                priority=RulePriority.MEDIUM,
                parameters={"stop_loss_percent": 0.02 + i*0.001},
                description=f"性能测试规则{i}"
            )
            self.engine.add_rule(rule)
        
        # 创建交易上下文
        trade_context = TradeContext(
            symbol="BTC/USDT",
            position_side="long",
            entry_price=50000.0,
            current_price=49000.0,  # 亏损2%
            position_size=0.1,
            unrealized_pnl=-100.0,
            realized_pnl=0.0,
            leverage=5.0,
            timestamp=int(time.time() * 1000)
        )
        
        account_context = AccountContext(
            total_balance=10000.0,
            available_balance=5000.0,
            margin_ratio=0.5,
            total_position_value=5000.0,
            daily_pnl=-200.0,
            weekly_pnl=500.0,
            open_positions=[trade_context],
            timestamp=int(time.time() * 1000)
        )
        
        # 评估所有规则并计时
        import time as time_module
        start_time = time_module.time()
        
        results = await self.engine.evaluate_all_rules(
            trade_context, account_context, record_trade_attempt=False
        )
        
        end_time = time_module.time()
        evaluation_time = end_time - start_time
        
        # 验证评估时间在合理范围内（10个规则应该<0.1秒）
        self.assertLess(evaluation_time, 0.5, f"评估时间过长: {evaluation_time:.3f}秒")
        self.assertEqual(len(results), 10, "应该评估10个规则")
        
        print(f"✅ 性能测试通过: 评估10个规则耗时{evaluation_time:.3f}秒")


async def run_all_tests():
    """运行所有测试"""
    print("开始高级规则引擎测试...")
    print("=" * 80)
    
    tester = TestAdvancedRules()
    tester.setUp()
    
    # 运行测试
    test_methods = [
        tester.test_trading_frequency_rule,
        tester.test_correlation_risk_rule,
        tester.test_market_volatility_rule,
        tester.test_config_file_loading,
        tester.test_performance_optimization
    ]
    
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        test_name = test_method.__name__
        print(f"\n运行测试: {test_name}...")
        
        try:
            await test_method()
            print(f"  ✅ {test_name} 通过")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_name} 失败: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"测试完成: {passed}通过, {failed}失败")
    
    return failed == 0


if __name__ == "__main__":
    """主入口"""
    success = asyncio.run(run_all_tests())
    
    # 退出码
    sys.exit(0 if success else 1)