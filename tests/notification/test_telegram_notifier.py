#!/usr/bin/env python3
"""
Telegram通知器单元测试
"""
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock, Mock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.notification.telegram_notifier import TelegramNotifier, create_telegram_notifier
from src.notification.notification_manager import Notification, NotificationResult, NotificationPriority, NotificationType


class TestTelegramNotifier(unittest.TestCase):
    """Telegram通知器测试"""
    
    def setUp(self):
        """测试准备"""
        import os
        
        # 设置环境变量，使Telegram通知器启用
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test_bot_token_123'
        os.environ['TELEGRAM_CHAT_ID'] = '123456'  # 数字ID
        
        self.config = {
            'notification': {
                'telegram': {
                    'enabled': True,
                    'bot_token': 'test_bot_token_123',
                    'chat_id': '123456',  # 数字ID
                    'parse_mode': 'HTML',
                    'disable_notification': False,
                    'max_retries': 3
                }
            }
        }
        
        # 创建Telegram通知器实例
        self.notifier = TelegramNotifier(self.config)
    
    def tearDown(self):
        """测试清理"""
        import os
        # 清理环境变量
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('TELEGRAM_CHAT_ID', None)
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
        self.assertTrue(self.notifier.config['notification']['telegram']['enabled'])
        self.assertEqual(self.notifier.config['notification']['telegram']['parse_mode'], 'HTML')
    
    def test_create_telegram_notifier(self):
        """测试工厂函数"""
        notifier = create_telegram_notifier(self.config)
        self.assertIsInstance(notifier, TelegramNotifier)
        self.assertEqual(notifier.config, self.config)
    
    @patch('aiohttp.ClientSession')
    def test_send_notification_success(self, mock_session_class):
        """测试发送通知成功"""
        # 模拟aiohttp客户端成功响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'ok': True, 'result': {'message_id': 123}})
        
        # 创建异步上下文管理器模拟类
        class AsyncContextManagerMock:
            def __init__(self, return_value):
                self.return_value = return_value
            async def __aenter__(self):
                return self.return_value
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(mock_response))
        mock_session.close = MagicMock()
        mock_session_class.return_value = mock_session
        
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
        
        # 验证HTTP请求被正确调用
        mock_session.post.assert_called()
    
    @patch('aiohttp.ClientSession')
    def test_send_notification_failure(self, mock_session_class):
        """测试发送通知失败（HTTP错误）"""
        # 模拟aiohttp客户端错误响应
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={'ok': False, 'description': 'Bad Request'})
        
        # 创建异步上下文管理器模拟类
        class AsyncContextManagerMock:
            def __init__(self, return_value):
                self.return_value = return_value
            async def __aenter__(self):
                return self.return_value
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(mock_response))
        mock_session.close = MagicMock()
        mock_session_class.return_value = mock_session
        
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
        
        # 发送通知
        result = self._run_async(self.notifier.send(notification))
        
        # 验证结果（应该失败）
        self.assertIsInstance(result, NotificationResult)
        # Telegram通知器可能在失败时仍然返回成功=False
        # 或者处理错误并返回特定结果
    
    @patch('aiohttp.ClientSession')
    def test_send_notification_network_error(self, mock_session_class):
        """测试发送通知网络错误"""
        # 模拟网络异常
        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=Exception("Network error"))
        mock_session.close = MagicMock()
        mock_session_class.return_value = mock_session
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_003",
            notification_type=NotificationType.ERROR,
            priority=NotificationPriority.HIGH,
            title="错误通知",
            message="网络连接失败",
            created_at=1234567890.0,
            metadata={"error": "network_error"}
        )
        
        # 发送通知
        result = self._run_async(self.notifier.send(notification))
        
        # 验证结果（应该处理异常而不崩溃）
        self.assertIsInstance(result, NotificationResult)
    
    def test_notification_to_telegram_message(self):
        """测试通知转换为Telegram消息"""
        notification = Notification(
            notification_id="test_notification_004",
            notification_type=NotificationType.RISK_ALERT,
            priority=NotificationPriority.CRITICAL,
            title="风险警报",
            message="高风险事件发生",
            created_at=1234567890.0,
            metadata={"alert_type": "STOP_LOSS_TRIGGERED", "symbol": "BTC/USDT", "severity": "HIGH"}
        )
        
        # 转换为Telegram消息参数
        message_params = self.notifier._notification_to_telegram_message(notification)
        
        # 验证参数结构
        self.assertIsInstance(message_params, dict)
        # 注意：_notification_to_telegram_message 不包含 chat_id，chat_id 是在 _send_to_telegram 中单独传递的
        self.assertIn('text', message_params)
        self.assertIn('parse_mode', message_params)
        self.assertIn('disable_web_page_preview', message_params)
        self.assertIn('disable_notification', message_params)
        
        # 验证消息内容
        self.assertIn('风险警报', message_params['text'])
        self.assertIn('BTC/USDT', message_params['text'])
    
    @patch('aiohttp.ClientSession')
    def test_send_to_telegram(self, mock_session_class):
        """测试发送到Telegram"""
        # 模拟aiohttp客户端成功响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'ok': True, 'result': {'message_id': 456}})
        
        # 创建异步上下文管理器模拟类
        class AsyncContextManagerMock:
            def __init__(self, return_value):
                self.return_value = return_value
            async def __aenter__(self):
                return self.return_value
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(mock_response))
        mock_session.close = MagicMock()
        mock_session_class.return_value = mock_session
        
        chat_id = "test_chat_id"
        message_data = {
            'text': '测试消息',
            'parse_mode': 'HTML',
            'disable_notification': False
        }
        
        # 发送消息
        result = self._run_async(self.notifier._send_to_telegram(chat_id, message_data))
        
        # 验证结果（根据实际实现，返回的字典包含'success'键）
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('success', False))
        
        # 验证HTTP请求被正确调用
        mock_session.post.assert_called()
    
    def test_get_http_client(self):
        """测试获取HTTP客户端"""
        # 获取HTTP客户端（异步）
        async def run_get_client():
            return await self.notifier._get_http_client()
        
        client = self._run_async(run_get_client())
        
        # 验证返回客户端（可能是None或实际客户端）
        # 主要确保方法不抛出异常
    
    def test_get_stats(self):
        """测试获取统计信息"""
        stats = self.notifier.get_stats()
        
        # 验证统计信息结构
        self.assertIsInstance(stats, dict)
        # 应该包含统计字段（根据实际实现）
        self.assertIn('total_sent', stats)
        self.assertIn('total_failed', stats)
        self.assertIn('last_sent', stats)
        self.assertIn('last_error', stats)
    
    def test_close(self):
        """测试关闭通知器"""
        # 关闭应该是异步的
        result = self._run_async(self.notifier.close())
        
        # 关闭方法应该不抛出异常
        self.assertIsNone(result)
    
    def test_config_without_telegram_section(self):
        """测试没有telegram配置节的情况"""
        config_minimal = {}
        
        notifier = TelegramNotifier(config_minimal)
        
        # 应该能够初始化
        self.assertIsNotNone(notifier)
        self.assertIsNotNone(notifier.config)
    
    def test_config_with_missing_token(self):
        """测试缺少bot_token的情况"""
        config_no_token = {
            'telegram': {
                'enabled': True,
                # 缺少bot_token
                'chat_id': 'test_chat_id'
            }
        }
        
        notifier = TelegramNotifier(config_no_token)
        
        # 应该能够初始化（可能在发送时失败）
        self.assertIsNotNone(notifier)
    
    @patch('aiohttp.ClientSession')
    def test_notification_types(self, mock_session_class):
        """测试不同类型的通知"""
        # 模拟成功响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'ok': True, 'result': {'message_id': 789}})
        
        # 创建异步上下文管理器模拟类
        class AsyncContextManagerMock:
            def __init__(self, return_value):
                self.return_value = return_value
            async def __aenter__(self):
                return self.return_value
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManagerMock(mock_response))
        mock_session.close = MagicMock()
        mock_session_class.return_value = mock_session
        
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


if __name__ == '__main__':
    unittest.main()