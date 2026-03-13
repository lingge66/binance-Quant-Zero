#!/usr/bin/env python3
"""
订单管理器单元测试
"""
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.execution.order_manager import OrderManager, Order, OrderType, OrderSide, OrderStatus


class TestOrderManager(unittest.TestCase):
    """订单管理器测试"""
    
    def setUp(self):
        """测试准备"""
        # 模拟配置管理器
        self.config_patcher = patch('src.execution.order_manager.ConfigManager')
        self.mock_config_class = self.config_patcher.start()
        self.mock_config = MagicMock()
        
        # 模拟get_all方法
        self.mock_config.get_all.return_value = {
            'binance': {
                'environment': 'testnet',
                'api_key': 'test_key',
                'secret_key': 'test_secret'
            },
            'execution': {
                'order_types': {
                    'default': 'limit',
                    'allowed': ['limit', 'market']
                },
                'simulation': True
            }
        }
        
        # 模拟get方法 - 用于获取特定配置项
        def get_side_effect(key, default=None):
            if key == 'environment':
                return 'testnet'
            elif key == 'execution.order_types.default':
                return 'limit'
            elif key == 'execution.simulation':
                return True
            elif key == 'binance.environment':
                return 'testnet'
            else:
                return default
        
        self.mock_config.get.side_effect = get_side_effect
        
        self.mock_config_class.return_value = self.mock_config
        
        # 创建订单管理器实例
        self.order_manager = OrderManager(self.mock_config)
    
    def tearDown(self):
        """测试清理"""
        self.config_patcher.stop()
    
    def _run_async(self, coro):
        """运行异步协程"""
        return asyncio.run(coro)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.order_manager)
        self.assertEqual(self.order_manager.environment, 'testnet')
        # 检查基本属性是否存在
        self.assertIsNotNone(self.order_manager.config)
        self.assertIsInstance(self.order_manager.orders, dict)
        self.assertIsInstance(self.order_manager.client_order_map, dict)
        self.assertIsNotNone(self.order_manager.api_key)
        self.assertIsNotNone(self.order_manager.api_secret)
    
    def test_create_order(self):
        """测试创建订单"""
        # 异步方法需要使用asyncio.run运行
        order = self._run_async(
            self.order_manager.create_order(
                symbol='BTC/USDT',
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=0.01,
                price=50000.0
            )
        )
        
        self.assertIsInstance(order, Order)
        self.assertEqual(order.symbol, 'BTC/USDT')
        self.assertEqual(order.side, OrderSide.BUY)
        self.assertEqual(order.order_type, OrderType.LIMIT)
        self.assertEqual(order.amount, 0.01)
        self.assertEqual(order.price, 50000.0)
        self.assertIsNotNone(order.order_id)
        self.assertEqual(order.status, OrderStatus.NEW)  # 注意：应该是NEW，不是CREATED
    
    def test_submit_order_simulation(self):
        """测试提交订单（模拟模式）"""
        # 先创建订单
        order = self._run_async(
            self.order_manager.create_order(
                symbol='BTC/USDT',
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=0.01,
                price=50000.0
            )
        )
        
        # 在模拟模式下提交订单
        result = self._run_async(
            self.order_manager.submit_order(order.order_id, dry_run=True)
        )
        
        # submit_order返回Order对象，不是布尔值
        self.assertIsInstance(result, Order)
        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertIsNotNone(result.updated_at)
        
        # 验证原始订单也被更新
        updated_order = self._run_async(self.order_manager.get_order(order.order_id))
        self.assertEqual(updated_order.status, OrderStatus.SUBMITTED)
    
    def test_cancel_order(self):
        """测试取消订单"""
        # 先创建订单
        order = self._run_async(
            self.order_manager.create_order(
                symbol='BTC/USDT',
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=0.01,
                price=50000.0
            )
        )
        
        # 提交订单
        submitted_order = self._run_async(
            self.order_manager.submit_order(order.order_id, dry_run=True)
        )
        
        # 取消订单
        cancelled_order = self._run_async(
            self.order_manager.cancel_order(order.order_id)
        )
        
        self.assertIsInstance(cancelled_order, Order)
        self.assertEqual(cancelled_order.status, OrderStatus.CANCELLED)
        
        # 验证订单状态
        retrieved_order = self._run_async(self.order_manager.get_order(order.order_id))
        self.assertEqual(retrieved_order.status, OrderStatus.CANCELLED)
    
    def test_get_order(self):
        """测试获取订单"""
        # 先创建订单
        order = self._run_async(
            self.order_manager.create_order(
                symbol='BTC/USDT',
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=0.01,
                price=50000.0
            )
        )
        
        # 获取订单
        retrieved_order = self._run_async(self.order_manager.get_order(order.order_id))
        
        self.assertIsNotNone(retrieved_order)
        self.assertEqual(retrieved_order.order_id, order.order_id)
        self.assertEqual(retrieved_order.symbol, 'BTC/USDT')
        self.assertEqual(retrieved_order.side, OrderSide.BUY)
        self.assertEqual(retrieved_order.order_type, OrderType.LIMIT)
        self.assertEqual(retrieved_order.amount, 0.01)
        self.assertEqual(retrieved_order.price, 50000.0)
    
    def test_order_status_enum(self):
        """测试订单状态枚举"""
        self.assertEqual(OrderStatus.NEW.value, 'new')
        self.assertEqual(OrderStatus.PENDING.value, 'pending')
        self.assertEqual(OrderStatus.SUBMITTED.value, 'submitted')
        self.assertEqual(OrderStatus.OPEN.value, 'open')
        self.assertEqual(OrderStatus.PARTIALLY_FILLED.value, 'partially_filled')
        self.assertEqual(OrderStatus.FILLED.value, 'filled')
        self.assertEqual(OrderStatus.CANCELLED.value, 'cancelled')
        self.assertEqual(OrderStatus.EXPIRED.value, 'expired')
        self.assertEqual(OrderStatus.REJECTED.value, 'rejected')
        self.assertEqual(OrderStatus.ERROR.value, 'error')
    
    def test_order_type_enum(self):
        """测试订单类型枚举"""
        self.assertEqual(OrderType.LIMIT.value, 'limit')
        self.assertEqual(OrderType.MARKET.value, 'market')
        self.assertEqual(OrderType.STOP_LOSS.value, 'stop_loss')
        self.assertEqual(OrderType.STOP_LOSS_LIMIT.value, 'stop_loss_limit')
        self.assertEqual(OrderType.TAKE_PROFIT.value, 'take_profit')
        self.assertEqual(OrderType.TAKE_PROFIT_LIMIT.value, 'take_profit_limit')
    
    def test_order_side_enum(self):
        """测试订单方向枚举"""
        self.assertEqual(OrderSide.BUY.value, 'buy')
        self.assertEqual(OrderSide.SELL.value, 'sell')


if __name__ == '__main__':
    unittest.main()