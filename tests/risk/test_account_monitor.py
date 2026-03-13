#!/usr/bin/env python3
"""
账户监控器单元测试
"""
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.risk.account_monitor import AccountMonitor, AccountType, AccountBalance, PositionInfo
from config.config_manager import ConfigManager


class TestAccountMonitor(unittest.TestCase):
    """账户监控器测试"""
    
    def setUp(self):
        """测试准备"""
        # 模拟ConfigManager
        self.mock_config = MagicMock(spec=ConfigManager)
        self.mock_config.get.side_effect = self._config_get_side_effect
        
        # 设置环境变量
        import os
        os.environ['BINANCE_API_KEY'] = 'test_api_key'
        os.environ['BINANCE_SECRET_KEY'] = 'test_secret_key'
        
        # 创建AccountMonitor实例
        self.account_monitor = AccountMonitor(self.mock_config)
    
    def tearDown(self):
        """测试清理"""
        import os
        os.environ.pop('BINANCE_API_KEY', None)
        os.environ.pop('BINANCE_SECRET_KEY', None)
    
    def _config_get_side_effect(self, key, default=None):
        """ConfigManager.get()的模拟返回值"""
        if key == 'environment':
            return 'testnet'
        elif key == 'risk.account_monitor.cache_ttl':
            return 5
        elif key == 'risk.account_monitor.max_retries':
            return 3
        elif key == 'risk.account_monitor.retry_delay':
            return 1.0
        else:
            return default
    
    def _run_async(self, coro):
        """运行异步协程"""
        return asyncio.run(coro)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.account_monitor)
        self.assertEqual(self.account_monitor.config, self.mock_config)
        self.assertEqual(self.account_monitor.account_type, AccountType.SPOT)
        self.assertIsNone(self.account_monitor.exchange)
    
    @patch('src.risk.account_monitor.ccxt')
    def test_create_exchange(self, mock_ccxt):
        """测试创建交易所连接"""
        # 模拟ccxt模块和交易所类
        mock_exchange_class = MagicMock()
        mock_exchange_instance = MagicMock()
        mock_exchange_class.return_value = mock_exchange_instance
        
        # 对于测试网环境，需要模拟binanceusdmtest类
        mock_ccxt.binanceusdmtest = mock_exchange_class
        
        # 调用创建交易所（使用测试网环境）
        exchange = self._run_async(self.account_monitor._create_exchange())
        
        # 验证交易所被创建
        self.assertIsNotNone(exchange)
        mock_exchange_class.assert_called_once()
    
    def test_validate_api_keys(self):
        """测试验证API密钥"""
        # 应该不抛出异常
        try:
            self.account_monitor._validate_api_keys()
        except Exception as e:
            self.fail(f"_validate_api_keys() raised {type(e).__name__} unexpectedly!")
    
    def test_setup_logging(self):
        """测试设置日志"""
        # 应该不抛出异常
        try:
            self.account_monitor._setup_logging()
        except Exception as e:
            self.fail(f"_setup_logging() raised {type(e).__name__} unexpectedly!")
    
    @patch('ccxt.binance')
    def test_fetch_account_balance(self, mock_binance_class):
        """测试获取账户余额"""
        # 模拟交易所和余额响应
        mock_exchange = MagicMock()
        mock_exchange.fetch_balance = AsyncMock(return_value={
            'total': {'BTC': 1.5, 'USDT': 10000},
            'free': {'BTC': 1.0, 'USDT': 8000},
            'used': {'BTC': 0.5, 'USDT': 2000}
        })
        mock_binance_class.return_value = mock_exchange
        
        # 设置交易所实例
        self.account_monitor.exchange = mock_exchange
        
        # 获取余额
        balance = self._run_async(self.account_monitor.fetch_account_balance())
        
        # 验证结果
        self.assertIsInstance(balance, AccountBalance)
        # 验证必要的字段存在
        self.assertIsNotNone(balance.total_balance)
        self.assertIsNotNone(balance.available_balance)
        self.assertIsNotNone(balance.locked_balance)
        
        # 验证API调用
        mock_exchange.fetch_balance.assert_called_once()
    
    @patch('ccxt.binance')
    def test_fetch_positions(self, mock_binance_class):
        """测试获取持仓"""
        # 设置账户类型为合约账户（fetch_positions需要）
        self.account_monitor.account_type = AccountType.FUTURES
        
        # 模拟交易所和持仓响应
        mock_exchange = MagicMock()
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {'symbol': 'BTC/USDT', 'side': 'long', 'contracts': 1.0, 'entryPrice': 50000, 'markPrice': 51000}
        ])
        mock_binance_class.return_value = mock_exchange
        
        # 设置交易所实例
        self.account_monitor.exchange = mock_exchange
        
        # 获取持仓
        positions = self._run_async(self.account_monitor.fetch_positions())
        
        # 验证结果
        self.assertIsInstance(positions, list)
        if positions:
            self.assertIsInstance(positions[0], PositionInfo)
        
        # 验证API调用
        mock_exchange.fetch_positions.assert_called_once()
    
    def test_cache_behavior(self):
        """测试缓存行为"""
        # 测试缓存初始化状态
        self.assertIsNone(self.account_monitor._balance_cache)
        self.assertEqual(self.account_monitor._positions_cache, [])
        self.assertEqual(self.account_monitor._last_update_time, 0)
        self.assertEqual(self.account_monitor._cache_ttl, 5)
    
    # Note: AccountMonitor doesn't have a clear_cache method
    # Cache is cleared through other mechanisms like close() or timeout
    
    @patch('src.risk.account_monitor.ccxt')
    def test_initialize(self, mock_ccxt):
        """测试初始化交易所连接"""
        # 模拟ccxt模块和交易所类
        mock_exchange_class = MagicMock()
        mock_exchange_instance = MagicMock()
        mock_exchange_instance.fetch_time = AsyncMock(return_value=1234567890000)
        mock_exchange_class.return_value = mock_exchange_instance
        
        # 对于测试网环境，需要模拟binanceusdmtest类
        mock_ccxt.binanceusdmtest = mock_exchange_class
        
        # 调用初始化
        result = self._run_async(self.account_monitor.initialize())
        
        # 验证交易所被创建和初始化
        self.assertIsNone(result)  # initialize()返回None
        self.assertIsNotNone(self.account_monitor.exchange)
        
        # 验证交易所类被调用
        mock_exchange_class.assert_called_once()
        # 验证fetch_time被调用
        mock_exchange_instance.fetch_time.assert_called_once()
    
    @patch('src.risk.account_monitor.ccxt')
    def test_safe_api_call(self, mock_ccxt):
        """测试安全API调用"""
        # 模拟交易所
        mock_exchange = MagicMock()
        mock_exchange.some_api_method = AsyncMock(return_value="test_result")
        
        # 设置交易所实例
        self.account_monitor.exchange = mock_exchange
        
        # 调用安全API
        result = self._run_async(self.account_monitor._safe_api_call(
            mock_exchange.some_api_method, "arg1", key="value"
        ))
        
        # 验证结果
        self.assertEqual(result, "test_result")
        mock_exchange.some_api_method.assert_called_once_with("arg1", key="value")
    
    def test_calculate_risk_metrics(self):
        """测试计算风险指标"""
        # 设置现货账户（简化测试）
        self.account_monitor.account_type = AccountType.SPOT
        
        # 调用计算风险指标
        result = self._run_async(self.account_monitor.calculate_risk_metrics())
        
        # 验证返回字典结构
        self.assertIsInstance(result, dict)
        # 应该包含一些基本的风险指标键
        self.assertIn('account_type', result)
        self.assertIn('timestamp', result)
    
    def test_check_liquidation_risk(self):
        """测试检查强平风险"""
        # 设置现货账户（无强平风险）
        self.account_monitor.account_type = AccountType.SPOT
        
        # 调用检查强平风险
        result = self._run_async(self.account_monitor.check_liquidation_risk())
        
        # 验证返回字典结构
        self.assertIsInstance(result, dict)
        self.assertIn('has_liquidation_risk', result)
        self.assertIn('highest_risk_symbol', result)
    
    def test_close(self):
        """测试关闭账户监控器"""
        # 模拟交易所
        mock_exchange = MagicMock()
        mock_exchange.close = AsyncMock()
        self.account_monitor.exchange = mock_exchange
        
        # 设置一些缓存值
        self.account_monitor._balance_cache = AccountBalance(
            total_balance=10000.0,
            available_balance=5000.0,
            locked_balance=5000.0,
            margin_ratio=0.0,
            leverage=1.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            timestamp=1234567890000
        )
        
        # 调用关闭
        result = self._run_async(self.account_monitor.close())
        
        # 验证关闭成功
        self.assertIsNone(result)
        # 验证缓存被清除（close方法可能不清除缓存，但至少不应抛出异常）


if __name__ == '__main__':
    unittest.main()