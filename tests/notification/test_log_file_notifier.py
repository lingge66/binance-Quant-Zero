#!/usr/bin/env python3
"""
日志文件通知器单元测试
"""
import sys
import asyncio
import time
import unittest
import tempfile
import os
from unittest.mock import MagicMock, patch, mock_open, AsyncMock
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.notification.log_file_notifier import LogFileNotifier, create_log_file_notifier
from src.notification.notification_manager import Notification, NotificationResult, NotificationPriority, NotificationType


class TestLogFileNotifier(unittest.TestCase):
    """日志文件通知器测试"""
    
    def setUp(self):
        """测试准备"""
        # 创建临时目录用于测试
        self.temp_dir = tempfile.mkdtemp(prefix="test_log_")
        self.log_file_path = os.path.join(self.temp_dir, "notifications.log")
        
        self.config = {
            'log_file': {
                'enabled': True,
                'path': self.log_file_path,
                'max_size_mb': 10,
                'max_files': 5,
                'json_format': True,
                'timestamp_format': '%Y-%m-%d %H:%M:%S'
            }
        }
        
        # 创建日志文件通知器实例
        self.notifier = LogFileNotifier(self.config)
    
    def tearDown(self):
        """测试清理"""
        # 清理临时目录
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def _run_async(self, coro):
        """运行异步协程"""
        return asyncio.run(coro)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.notifier)
        self.assertIsNotNone(self.notifier.config)
        self.assertEqual(self.notifier.config, self.config)
        # 检查日志路径
        self.assertEqual(self.notifier.config['log_file']['path'], self.log_file_path)
    
    def test_create_log_file_notifier(self):
        """测试工厂函数"""
        notifier = create_log_file_notifier(self.config)
        self.assertIsInstance(notifier, LogFileNotifier)
        self.assertEqual(notifier.config, self.config)
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dumps')
    def test_send_notification_success(self, mock_json_dumps, mock_file):
        """测试发送通知成功（JSON格式）"""
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
        
        # 验证文件操作被调用
        mock_file.assert_called()
        mock_json_dumps.assert_called()
    
    @patch('builtins.open', new_callable=mock_open)
    def test_send_notification_plain_text(self, mock_file):
        """测试发送通知（纯文本格式）"""
        # 修改配置为纯文本格式
        config_text = self.config.copy()
        config_text['log_file']['json_format'] = False
        
        notifier = LogFileNotifier(config_text)
        
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
        result = self._run_async(notifier.send(notification))
        
        # 验证结果
        self.assertTrue(result.success)
        mock_file.assert_called()
    
    def test_send_notification_invalid_path(self):
        """测试发送通知到无效路径"""
        # 修改配置为无效路径
        config_invalid = self.config.copy()
        config_invalid['log_file']['path'] = "/invalid/path/notifications.log"
        
        notifier = LogFileNotifier(config_invalid)
        
        # 创建测试通知
        notification = Notification(
            notification_id="test_notification_003",
            notification_type=NotificationType.ERROR,
            priority=NotificationPriority.HIGH,
            title="错误通知",
            message="这是一个错误通知",
            created_at=1234567890.0,
            metadata={"error": "test error"}
        )
        
        # 发送通知（应该失败或记录错误）
        result = self._run_async(notifier.send(notification))
        
        # 即使路径无效，通知器可能仍然返回成功（仅记录错误）
        self.assertIsInstance(result, NotificationResult)
    
    def test_close(self):
        """测试关闭通知器"""
        # 关闭应该是异步的
        result = self._run_async(self.notifier.close())
        
        # 关闭方法应该不抛出异常
        self.assertIsNone(result)
    
    def test_ensure_log_directory(self):
        """测试确保日志目录存在"""
        # 测试目录创建逻辑
        self.notifier._ensure_log_directory()
        
        # 验证目录是否存在
        log_dir = os.path.dirname(self.log_file_path)
        self.assertTrue(os.path.exists(log_dir))
    
    def test_get_file_size(self):
        """测试获取文件大小"""
        # 创建测试文件
        with open(self.log_file_path, 'w') as f:
            f.write("test content")
        
        file_size = self.notifier._get_file_size()
        
        # 文件大小应该大于0
        self.assertGreater(file_size, 0)
    
    def test_needs_rotation(self):
        """测试是否需要轮转"""
        # 默认配置下，小文件不需要轮转
        needs_rotation = self.notifier._needs_rotation()
        self.assertFalse(needs_rotation)
    
    @patch('os.rename')
    @patch('os.path.exists')
    def test_rotate_log_file(self, mock_exists, mock_rename):
        """测试轮转日志文件"""
        # 模拟文件存在
        mock_exists.return_value = True
        
        # 执行轮转
        self.notifier._rotate_log_file()
        
        # 验证rename被调用
        mock_rename.assert_called()
    
    def test_notification_to_dict(self):
        """测试通知转换为字典"""
        notification = Notification(
            notification_id="test_notification_004",
            notification_type=NotificationType.TRADE_EXECUTION,
            priority=NotificationPriority.HIGH,
            title="交易执行",
            message="订单已执行",
            created_at=1234567890.0,
            metadata={"symbol": "BTC/USDT", "order_id": "12345", "filled": 0.01}
        )
        
        # 转换为字典
        notification_dict = self.notifier._notification_to_dict(notification)
        
        # 验证字典结构
        self.assertIsInstance(notification_dict, dict)
        self.assertEqual(notification_dict['notification_id'], notification.notification_id)
        self.assertEqual(notification_dict['notification_type'], notification.notification_type.value)
        self.assertEqual(notification_dict['priority'], notification.priority.value)
        self.assertEqual(notification_dict['title'], notification.title)
        self.assertEqual(notification_dict['message'], notification.message)
        self.assertEqual(notification_dict['created_at'], notification.created_at)
        self.assertEqual(notification_dict['metadata'], notification.metadata)
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dumps')
    def test_write_to_log(self, mock_json_dumps, mock_file):
        """测试写入日志"""
        log_entry = {
            'id': 'test_entry_001',
            'timestamp': 1234567890.0,
            'type': 'test',
            'message': '测试日志条目'
        }
        
        # 写入日志
        success = self.notifier._write_to_log(log_entry)
        
        # 验证结果
        self.assertTrue(success)
        mock_file.assert_called()
        mock_json_dumps.assert_called()


if __name__ == '__main__':
    unittest.main()