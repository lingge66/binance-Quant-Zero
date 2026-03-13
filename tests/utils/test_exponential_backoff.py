#!/usr/bin/env python3
"""
指数退避算法单元测试
"""
import sys
import time
import random
import asyncio
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.exponential_backoff import ExponentialBackoff


class TestExponentialBackoff(unittest.TestCase):
    """指数退避算法测试"""
    
    def test_initialization(self):
        """测试初始化参数"""
        # 测试默认参数
        backoff = ExponentialBackoff()
        self.assertEqual(backoff.base_delay, 1.0)
        self.assertEqual(backoff.max_delay, 64.0)
        self.assertEqual(backoff.max_attempts, 10)
        self.assertTrue(backoff.jitter)
        self.assertEqual(backoff.attempts, 0)
        
        # 测试自定义参数
        backoff = ExponentialBackoff(base_delay=2.0, max_delay=128.0, max_attempts=5, jitter=False)
        self.assertEqual(backoff.base_delay, 2.0)
        self.assertEqual(backoff.max_delay, 128.0)
        self.assertEqual(backoff.max_attempts, 5)
        self.assertFalse(backoff.jitter)
    
    def test_next_delay_without_jitter(self):
        """测试无抖动延迟计算"""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=64.0, max_attempts=5, jitter=False)
        
        # 第一次重试: 1 * 2^(1-1) = 1
        delay1 = backoff.next_delay()
        self.assertEqual(delay1, 1.0)
        self.assertEqual(backoff.attempts, 1)
        
        # 第二次重试: 1 * 2^(2-1) = 2
        delay2 = backoff.next_delay()
        self.assertEqual(delay2, 2.0)
        self.assertEqual(backoff.attempts, 2)
        
        # 第三次重试: 1 * 2^(3-1) = 4
        delay3 = backoff.next_delay()
        self.assertEqual(delay3, 4.0)
        self.assertEqual(backoff.attempts, 3)
        
        # 检查最大延迟限制
        backoff = ExponentialBackoff(base_delay=32.0, max_delay=64.0, max_attempts=5, jitter=False)
        delay = backoff.next_delay()  # 32 * 2^(1-1) = 32
        self.assertEqual(delay, 32.0)
        delay = backoff.next_delay()  # 32 * 2^(2-1) = 64
        self.assertEqual(delay, 64.0)
        delay = backoff.next_delay()  # 32 * 2^(3-1) = 128, 但限制为64
        self.assertEqual(delay, 64.0)
    
    @patch('random.uniform')
    def test_next_delay_with_jitter(self, mock_uniform):
        """测试有抖动延迟计算"""
        # 模拟随机抖动因子
        mock_uniform.return_value = 1.1  # 固定抖动因子
        
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=64.0, max_attempts=3, jitter=True)
        
        # 第一次重试: 1 * 2^(1-1) * 1.1 = 1.1
        delay1 = backoff.next_delay()
        self.assertEqual(delay1, 1.1)
        mock_uniform.assert_called_once_with(0.75, 1.25)
        
        # 重置mock调用计数
        mock_uniform.reset_mock()
        mock_uniform.return_value = 0.8
        
        # 第二次重试: 1 * 2^(2-1) * 0.8 = 1.6
        delay2 = backoff.next_delay()
        self.assertEqual(delay2, 1.6)
    
    def test_max_attempts(self):
        """测试最大重试次数"""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=64.0, max_attempts=3, jitter=False)
        
        # 前三次应该成功
        self.assertTrue(backoff.can_retry())
        backoff.next_delay()
        self.assertTrue(backoff.can_retry())
        backoff.next_delay()
        self.assertTrue(backoff.can_retry())
        backoff.next_delay()
        
        # 第四次应该达到最大重试次数
        self.assertFalse(backoff.can_retry())
        delay = backoff.next_delay()  # 应该返回最大延迟
        self.assertEqual(delay, 64.0)
    
    def test_reset(self):
        """测试重置功能"""
        backoff = ExponentialBackoff(jitter=False)
        
        # 进行几次重试
        backoff.next_delay()
        backoff.next_delay()
        self.assertEqual(backoff.attempts, 2)
        
        # 重置
        backoff.reset()
        self.assertEqual(backoff.attempts, 0)
        self.assertEqual(backoff.last_delay, 0.0)
        
        # 重置后可以重新开始
        delay = backoff.next_delay()
        self.assertEqual(delay, 1.0)
        self.assertEqual(backoff.attempts, 1)
    
    @patch('time.sleep')
    def test_wait_sync(self, mock_sleep):
        """测试同步等待"""
        backoff = ExponentialBackoff()
        
        # 先计算一个延迟
        delay = backoff.next_delay()
        
        # 调用等待
        backoff.wait()
        
        # 验证sleep被调用，参数是延迟时间
        mock_sleep.assert_called_once_with(delay)
    
    @patch('asyncio.sleep')
    def test_wait_async(self, mock_sleep):
        """测试异步等待"""
        backoff = ExponentialBackoff()
        
        # 先计算一个延迟
        delay = backoff.next_delay()
        
        # 异步等待
        async def test_async_wait():
            await backoff.wait_async()
        
        asyncio.run(test_async_wait())
        
        # 验证asyncio.sleep被调用
        mock_sleep.assert_called_once_with(delay)
    
    def test_get_attempts(self):
        """测试获取重试次数"""
        backoff = ExponentialBackoff()
        
        self.assertEqual(backoff.get_attempts(), 0)
        
        backoff.next_delay()
        self.assertEqual(backoff.get_attempts(), 1)
        
        backoff.next_delay()
        self.assertEqual(backoff.get_attempts(), 2)
    
    def test_min_base_delay(self):
        """测试最小基础延迟限制"""
        # 基础延迟小于0.1，应该被限制为0.1
        backoff = ExponentialBackoff(base_delay=0.05)
        self.assertEqual(backoff.base_delay, 0.1)
        
        # 基础延迟大于0.1，保持不变
        backoff = ExponentialBackoff(base_delay=0.2)
        self.assertEqual(backoff.base_delay, 0.2)
    
    def test_max_delay_constraint(self):
        """测试最大延迟约束"""
        # 最大延迟小于基础延迟，应该被调整为至少等于基础延迟
        backoff = ExponentialBackoff(base_delay=2.0, max_delay=1.0)
        self.assertEqual(backoff.max_delay, 2.0)  # 调整为2.0
        
        # 最大延迟大于基础延迟，保持不变
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=10.0)
        self.assertEqual(backoff.max_delay, 10.0)


if __name__ == '__main__':
    unittest.main()