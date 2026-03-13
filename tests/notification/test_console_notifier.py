#!/usr/bin/env python3
"""
控制台通知器单元测试
"""
import sys
import asyncio
import time
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.notification.console_notifier import ConsoleNotifier, create_console_notifier
from src.notification.notification_manager import Notification, NotificationResult, NotificationPriority, NotificationType


class TestConsoleNotifier(unittest.TestCase):
    """控制台通知器测试"""
    
    def setUp(self):
        """测试准备"""
        self.config = {
            'console': {
                'enabled': True,
                'colors': True,
                'timestamp': True,
                'debug_mode': False
            }
        }
        
        # 创建控制台通知器实例
        self.notifier = ConsoleNotifier(self.config)
    
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
        # 检查颜色配置
        self.assertTrue(self.config['console']['colors'])
    
    def test_create_console_notifier(self):
        """测试工厂函数"""
        notifier = create_console_notifier(self.config)
        self.assertIsInstance(notifier, ConsoleNotifier)
        self.assertEqual(notifier.config, self.config)
    
    @patch('builtins.print')
    def test_send_notification_success(self, mock_print):
        """测试发送通知成功"""
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_001",
            notification_type=NotificationType.SIGNAL,
            priority=NotificationPriority.HIGH,
            title="测试信号",
            message="这是一个测试信号通知",
            metadata={"symbol": "BTC/USDT", "signal_type": "BUY", "confidence": 0.75}
        )
        
        # 发送通知
        result = self._run_async(self.notifier.send(notification))
        
        # 验证结果
        self.assertIsInstance(result, NotificationResult)
        self.assertTrue(result.success)
        self.assertEqual(result.notification_id, notification.notification_id)
        self.assertIsNotNone(result.timestamp)
        
        # 验证print被调用（控制台输出）
        mock_print.assert_called()
    
    @patch('builtins.print')
    def test_send_notification_without_colors(self, mock_print):
        """测试无颜色模式发送通知"""
        # 修改配置为无颜色模式
        config_no_colors = self.config.copy()
        config_no_colors['console']['colors'] = False
        
        notifier = ConsoleNotifier(config_no_colors)
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_002",
            notification_type=NotificationType.SYSTEM_STATUS,
            priority=NotificationPriority.MEDIUM,
            title="系统状态",
            message="系统运行正常",
            metadata={"status": "running", "uptime": 3600}
        )
        
        # 发送通知
        result = self._run_async(notifier.send(notification))
        
        # 验证结果
        self.assertTrue(result.success)
        mock_print.assert_called()
    
    def test_send_invalid_notification(self):
        """测试发送无效通知"""
        # 创建无效通知（无id）
        notification = Notification(
            notification_id="",
            notification_type=NotificationType.SIGNAL,
            priority=NotificationPriority.HIGH,
            title="无效通知",
            message="这是一个无效通知",
            metadata={}
        )
        
        # 发送通知
        result = self._run_async(self.notifier.send(notification))
        
        # 应该仍然成功（控制台通知器总是成功，即使通知内容不完整）
        self.assertIsInstance(result, NotificationResult)
        self.assertTrue(result.success)
    
    def test_close(self):
        """测试关闭通知器"""
        # 关闭应该是异步的
        result = self._run_async(self.notifier.close())
        
        # 关闭方法应该不抛出异常
        self.assertIsNone(result)
    
    def test_colorize_method(self):
        """测试颜色化方法"""
        # 测试带颜色的文本
        colored_text = self.notifier._colorize("测试文本", "red")
        self.assertIsInstance(colored_text, str)
        self.assertIn("测试文本", colored_text)
        
        # 测试无颜色
        plain_text = self.notifier._colorize("测试文本", None)
        self.assertEqual(plain_text, "测试文本")
        
        # 测试无效颜色
        default_text = self.notifier._colorize("测试文本", "invalid_color")
        self.assertEqual(default_text, "测试文本")
    
    def test_format_timestamp(self):
        """测试时间戳格式化"""
        import time
        
        # 测试当前时间戳
        timestamp = time.time()
        formatted = self.notifier._format_timestamp(timestamp)
        
        self.assertIsInstance(formatted, str)
        self.assertGreater(len(formatted), 0)
        
        # 应该包含日期和时间
        self.assertIn(":", formatted)  # 时间分隔符
    
    @patch('builtins.print')
    def test_notification_types(self, mock_print):
        """测试不同类型的通知"""
        notification_types = [
            (NotificationType.SIGNAL, "信号通知"),
            (NotificationType.RISK_ALERT, "风险警报"),
            (NotificationType.TRADE_EXECUTION, "交易执行"),
            (NotificationType.SYSTEM_STATUS, "系统状态"),
            (NotificationType.ERROR, "错误报告"),
            (NotificationType.DEBUG, "调试信息")
        ]
        
        for notif_type, expected_prefix in notification_types:
            # 为每个类型创建通知
            notification = Notification(
                notification_id=f"test_{notif_type.value}",
                notification_type=notif_type,
                priority=NotificationPriority.MEDIUM,
                title=f"{expected_prefix}标题",
                message=f"{expected_prefix}消息",
                metadata={"test": "data"}
            )
            
            result = self._run_async(self.notifier.send(notification))
            self.assertTrue(result.success)


if __name__ == '__main__':
    unittest.main()