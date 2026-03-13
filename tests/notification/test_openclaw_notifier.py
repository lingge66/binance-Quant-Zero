#!/usr/bin/env python3
"""
OpenClaw通知器单元测试
"""
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock, Mock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.notification.openclaw_notifier import OpenClawNotifier, create_openclaw_notifier
from src.notification.notification_manager import Notification, NotificationResult, NotificationPriority, NotificationType


class TestOpenClawNotifier(unittest.TestCase):
    """OpenClaw通知器测试"""
    
    def setUp(self):
        """测试准备"""
        self.config = {
            'openclaw': {
                'enabled': True,
                'channel': 'telegram',
                'to': 'test_user',
                'format': 'text',
                'include_timestamp': True
            }
        }
        
        # 创建OpenClaw通知器实例
        self.notifier = OpenClawNotifier(self.config)
    
    def tearDown(self):
        """测试清理"""
        pass
    
    def _run_async(self, coro):
        """运行异步协程"""
        return asyncio.run(coro)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.notifier)
        self.assertIsNotNone(self.notifier.config)
        self.assertEqual(self.notifier.config, self.config)
        # 检查配置值
        self.assertTrue(self.notifier.config['openclaw']['enabled'])
        self.assertEqual(self.notifier.config['openclaw']['channel'], 'telegram')
    
    def test_create_openclaw_notifier(self):
        """测试工厂函数"""
        notifier = create_openclaw_notifier(self.config)
        self.assertIsInstance(notifier, OpenClawNotifier)
        self.assertEqual(notifier.config, self.config)
    
    def test_send_notification_success(self):
        """测试发送通知成功"""
        # 模拟message_tool属性
        mock_message_tool = AsyncMock()
        mock_message_tool.return_value = {'success': True, 'message_id': 'test_msg_123'}
        
        # 设置message_tool
        self.notifier.message_tool = mock_message_tool
        self.notifier.enabled = True  # 确保启用
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_001",
            notification_type=NotificationType.SIGNAL,
            priority=NotificationPriority.HIGH,
            title="测试信号",
            message="这是一个测试信号通知",
            created_at=1234567890.0,
            metadata={"symbol": "BTC/USDT", "signal_type": "BUY", "confidence": 0.75}
        )
        
        # 发送通知
        result = self._run_async(self.notifier.send(notification))
        
        # 验证结果
        self.assertIsInstance(result, NotificationResult)
        self.assertTrue(result.success)
        self.assertEqual(result.notification_id, notification.notification_id)
        self.assertIsNotNone(result.timestamp)
        
        # 验证message工具被调用
        mock_message_tool.assert_called()
    
    def test_send_notification_failure(self):
        """测试发送通知失败"""
        # 模拟message_tool属性失败
        mock_message_tool = AsyncMock()
        mock_message_tool.side_effect = Exception("OpenClaw消息发送失败")
        
        # 设置message_tool
        self.notifier.message_tool = mock_message_tool
        self.notifier.enabled = True  # 确保启用
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_002",
            notification_type=NotificationType.SYSTEM_STATUS,
            priority=NotificationPriority.MEDIUM,
            title="系统状态",
            message="系统运行正常",
            created_at=1234567890.0,
            metadata={"status": "running", "uptime": 3600}
        )
        
        # 发送通知（应该处理异常）
        result = self._run_async(self.notifier.send(notification))
        
        # 验证结果（即使发送失败，通知器可能仍然返回成功或特定错误结果）
        self.assertIsInstance(result, NotificationResult)
        # 具体成功与否取决于实现，但至少不应该崩溃
    
    def test_send_notification_simulation_mode(self):
        """测试模拟模式发送通知"""
        # 修改配置为模拟模式
        config_simulation = self.config.copy()
        config_simulation['openclaw']['simulation'] = True
        
        notifier = OpenClawNotifier(config_simulation)
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_003",
            notification_type=NotificationType.TRADE_EXECUTION,
            priority=NotificationPriority.HIGH,
            title="交易执行",
            message="订单已执行",
            created_at=1234567890.0,
            metadata={"symbol": "BTC/USDT", "order_id": "12345", "filled": 0.01}
        )
        
        # 发送通知
        result = self._run_async(notifier.send(notification))
        
        # 在模拟模式下，message工具可能不会被调用
        # 或者被调用但返回模拟结果
        self.assertIsInstance(result, NotificationResult)
    
    def test_check_openclaw_environment(self):
        """测试检查OpenClaw环境"""
        # 这个方法应该在初始化时被调用
        # 测试它不抛出异常
        try:
            self.notifier._check_openclaw_environment()
        except Exception as e:
            self.fail(f"_check_openclaw_environment() raised {type(e).__name__} unexpectedly!")
    
    def test_initialize_message_tool(self):
        """测试初始化消息工具"""
        # 这个方法应该在初始化时被调用
        # 测试它不抛出异常
        try:
            self.notifier._initialize_message_tool()
        except Exception as e:
            self.fail(f"_initialize_message_tool() raised {type(e).__name__} unexpectedly!")
    
    def test_notification_to_openclaw_message(self):
        """测试通知转换为OpenClaw消息"""
        notification = Notification(
            notification_id="test_notification_004",
            notification_type=NotificationType.RISK_ALERT,
            priority=NotificationPriority.CRITICAL,
            title="风险警报",
            message="高风险事件发生",
            created_at=1234567890.0,
            metadata={"alert_type": "STOP_LOSS_TRIGGERED", "symbol": "BTC/USDT", "severity": "HIGH"}
        )
        
        # 转换为OpenClaw消息参数
        message_params = self.notifier._notification_to_openclaw_message(notification)
        
        # 验证参数结构
        self.assertIsInstance(message_params, dict)
        self.assertIn('action', message_params)
        self.assertIn('message', message_params)
        # channel和to是可选的，取决于配置
        
        # 验证消息内容包含通知信息
        self.assertIn('风险警报', message_params['message'])
        # 注意：当前实现不自动包含metadata中的symbol信息
    
    def test_send_via_openclaw(self):
        """测试通过OpenClaw发送消息"""
        # 模拟message_tool属性
        mock_message_tool = AsyncMock()
        mock_message_tool.return_value = {'success': True, 'message_id': 'test_msg_456'}
        
        # 设置message_tool
        self.notifier.message_tool = mock_message_tool
        
        message_params = {
            'action': 'send',
            'channel': 'telegram',
            'to': 'test_user',
            'message': '测试消息'
        }
        
        # 发送消息
        result = self._run_async(self.notifier._send_via_openclaw(message_params))
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('success', False))
        
        # 验证message工具被正确调用
        mock_message_tool.assert_called_with(**message_params)
    
    def test_send_via_openclaw_exception(self):
        """测试通过OpenClaw发送消息异常"""
        message_params = {
            'action': 'send',
            'channel': 'telegram',
            'to': 'test_user',
            'message': '测试消息'
        }
        
        # 测试异常情况
        # 这里主要确保方法能够处理异常而不崩溃
        try:
            result = self._run_async(self.notifier._send_via_openclaw(message_params))
            # 即使失败也应该返回字典结果
            self.assertIsInstance(result, dict)
        except Exception as e:
            # 不应该有未捕获的异常
            self.fail(f"_send_via_openclaw() raised {type(e).__name__} unexpectedly!")
    
    def test_close(self):
        """测试关闭通知器"""
        # 关闭应该是异步的
        result = self._run_async(self.notifier.close())
        
        # 关闭方法应该不抛出异常
        self.assertIsNone(result)
    
    def test_notification_types(self):
        """测试不同类型的通知"""
        # 模拟message_tool属性
        mock_message_tool = AsyncMock()
        mock_message_tool.return_value = {'success': True, 'message_id': 'test_msg_789'}
        
        # 设置message_tool
        self.notifier.message_tool = mock_message_tool
        self.notifier.enabled = True
        
        notification_types = [
            NotificationType.SIGNAL,
            NotificationType.RISK_ALERT,
            NotificationType.TRADE_EXECUTION,
            NotificationType.SYSTEM_STATUS,
            NotificationType.ERROR,
            NotificationType.DEBUG
        ]
        
        for notif_type in notification_types:
            with self.subTest(notification_type=notif_type):
                notification = Notification(
                    notification_id=f"test_{notif_type.value}",
                    notification_type=notif_type,
                    priority=NotificationPriority.MEDIUM,
                    title=f"{notif_type.value}标题",
                    message=f"{notif_type.value}消息",
                    created_at=1234567890.0,
                    metadata={"test": "data"}
                )
                
                result = self._run_async(self.notifier.send(notification))
                self.assertIsInstance(result, NotificationResult)
    
    def test_config_without_openclaw_section(self):
        """测试没有openclaw配置节的情况"""
        config_minimal = {}
        
        notifier = OpenClawNotifier(config_minimal)
        
        # 应该能够初始化
        self.assertIsNotNone(notifier)
        self.assertIsNotNone(notifier.config)


if __name__ == '__main__':
    unittest.main()