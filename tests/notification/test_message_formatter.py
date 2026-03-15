"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
消息格式化器单元测试
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.notification.message_formatter import MessageFormatter, create_message_formatter


class TestMessageFormatter(unittest.TestCase):
    """消息格式化器测试"""
    
    def setUp(self):
        """测试准备"""
        self.config = {
            'message_format': {
                'default_format': 'text',
                'max_length': 2000,
                'emoji_enabled': True,
                'timestamp_format': '%Y-%m-%d %H:%M:%S'
            }
        }
        
        # 创建消息格式化器实例
        self.formatter = MessageFormatter(self.config)
    
    def tearDown(self):
        """测试清理"""
        pass
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.formatter)
        self.assertIsNotNone(self.formatter.config)
        self.assertEqual(self.formatter.config, self.config)
        # 检查配置值
        self.assertEqual(self.formatter.config['message_format']['default_format'], 'text')
        self.assertTrue(self.formatter.config['message_format']['emoji_enabled'])
    
    def test_create_message_formatter(self):
        """测试工厂函数"""
        formatter = create_message_formatter(self.config)
        self.assertIsInstance(formatter, MessageFormatter)
        self.assertEqual(formatter.config, self.config)
    
    def test_create_message_formatter_default(self):
        """测试默认工厂函数"""
        formatter = create_message_formatter()
        self.assertIsInstance(formatter, MessageFormatter)
        # 默认配置应该存在
        self.assertIsNotNone(formatter.config)
    
    def test_format_signal(self):
        """测试格式化信号消息"""
        # 根据实际API，format_signal接受多个单独参数
        symbol = 'BTC/USDT'
        signal_type = 'BUY'
        confidence = 0.85
        price = 50000.0
        timestamp = 1234567890.0
        additional_info = {
            'reason': '技术指标金叉，趋势看涨',
            'indicators': {'rsi': 65.5, 'macd': 120.5, 'ma': 'bullish'}
        }
        
        # 测试纯文本格式
        text_result_dict = self.formatter.format_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            timestamp=timestamp,
            format_type='plain',
            additional_info=additional_info
        )
        
        # format_signal返回一个字典，包含不同格式的消息
        self.assertIsInstance(text_result_dict, dict)
        self.assertIn('plain', text_result_dict)
        text_result = text_result_dict.get('plain', '')
        
        self.assertIsInstance(text_result, str)
        self.assertGreater(len(text_result), 0)
        self.assertIn('BTC/USDT', text_result)
        self.assertIn('BUY', text_result)
        self.assertIn('85.0%', text_result)  # 置信度应该显示为百分比（包含小数）
        
        # 测试Markdown格式
        markdown_result_dict = self.formatter.format_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            timestamp=timestamp,
            format_type='markdown',
            additional_info=additional_info
        )
        
        self.assertIsInstance(markdown_result_dict, dict)
        self.assertIn('markdown', markdown_result_dict)
        markdown_result = markdown_result_dict.get('markdown', '')
        self.assertIsInstance(markdown_result, str)
        self.assertGreater(len(markdown_result), 0)
        
        # 测试HTML格式
        html_result_dict = self.formatter.format_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            timestamp=timestamp,
            format_type='html',
            additional_info=additional_info
        )
        
        self.assertIsInstance(html_result_dict, dict)
        self.assertIn('html', html_result_dict)
        html_result = html_result_dict.get('html', '')
        self.assertIsInstance(html_result, str)
        self.assertGreater(len(html_result), 0)
    
    def test_format_risk_alert(self):
        """测试格式化风险警报消息"""
        # 根据实际API，format_risk_alert接受多个单独参数
        alert_type = 'STOP_LOSS_TRIGGERED'
        message = '止损触发，建议平仓'
        timestamp = 1234567890.0
        data = {
            'symbol': 'BTC/USDT',
            'current_price': 49000.0,
            'stop_loss_price': 49500.0,
            'position_size': 0.1,
            'estimated_loss': 500.0
        }
        
        # 测试不同严重度的警报
        severities = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        for severity in severities:
            with self.subTest(severity=severity):
                result_dict = self.formatter.format_risk_alert(
                    alert_type=alert_type,
                    level=severity,
                    message=message,
                    timestamp=timestamp,
                    format_type='plain',
                    data=data
                )
                
                # format_risk_alert返回一个字典，包含不同格式的消息
                self.assertIsInstance(result_dict, dict)
                self.assertIn('plain', result_dict)
                result = result_dict.get('plain', '')
                
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)
                self.assertIn(severity, result)
                self.assertIn('STOP_LOSS_TRIGGERED', result)
                self.assertIn('止损触发', result)
    
    def test_format_trade_execution(self):
        """测试格式化交易执行消息"""
        # 根据实际API，format_trade_execution接受多个单独参数
        symbol = 'BTC/USDT'
        action = 'BUY'
        amount = 0.01
        price = 50000.0
        timestamp = 1234567890.0
        metadata = {
            'order_type': 'LIMIT',
            'filled': 0.01,
            'order_id': '123456789',
            'fee': 2.5,
            'total': 500.0
        }
        
        # 测试不同订单状态
        statuses = ['PENDING', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED']
        for status in statuses:
            with self.subTest(status=status):
                result_dict = self.formatter.format_trade_execution(
                    symbol=symbol,
                    action=action,
                    amount=amount,
                    price=price,
                    status=status,
                    timestamp=timestamp,
                    format_type='plain',
                    metadata=metadata
                )
                
                # format_trade_execution返回一个字典，包含不同格式的消息
                self.assertIsInstance(result_dict, dict)
                self.assertIn('plain', result_dict)
                result = result_dict.get('plain', '')
                
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)
                self.assertIn(status, result)
                self.assertIn('BTC/USDT', result)
    
    def test_format_system_status(self):
        """测试格式化系统状态消息"""
        # 根据实际API，format_system_status接受多个单独参数
        status = 'RUNNING'
        message = '系统运行正常'
        timestamp = 1234567890.0
        details = {
            'system': 'binance_ai_agent',
            'uptime_seconds': 86400,  # 24小时
            'metrics': {
                'total_signals': 150,
                'total_trades': 25,
                'success_rate': 0.72,
                'current_balance': 10500.0,
                'total_pnl': 500.0
            },
            'warnings': [],
            'errors': []
        }
        
        # 测试不同系统状态
        statuses = ['STARTING', 'RUNNING', 'STOPPING', 'STOPPED', 'ERROR']
        for status in statuses:
            with self.subTest(status=status):
                result_dict = self.formatter.format_system_status(
                    status=status,
                    message=message,
                    timestamp=timestamp,
                    format_type='plain',
                    details=details
                )
                
                # format_system_status返回一个字典，包含不同格式的消息
                self.assertIsInstance(result_dict, dict)
                self.assertIn('plain', result_dict)
                result = result_dict.get('plain', '')
                
                self.assertIsInstance(result, str)
                self.assertGreater(len(result), 0)
                self.assertIn(status, result)
    
    def test_get_emoji(self):
        """测试获取表情符号"""
        # 测试存在的键
        emoji = self.formatter._get_emoji('buy')
        self.assertIsInstance(emoji, str)
        self.assertGreater(len(emoji), 0)  # 应该返回有效的表情符号
        
        # 测试不存在的键（返回默认值）
        default_emoji = self.formatter._get_emoji('nonexistent_key', default='📝')
        self.assertEqual(default_emoji, '📝')
        
        # 测试不存在的键（使用空字符串默认值）
        empty_emoji = self.formatter._get_emoji('nonexistent_key')
        self.assertEqual(empty_emoji, '')  # 默认返回空字符串
    
    def test_format_timestamp(self):
        """测试格式化时间戳"""
        # 测试提供时间戳
        timestamp = 1234567890.0
        formatted = self.formatter._format_timestamp(timestamp)
        self.assertIsInstance(formatted, str)
        self.assertGreater(len(formatted), 0)
        
        # 测试默认时间戳（当前时间）
        formatted_now = self.formatter._format_timestamp()
        self.assertIsInstance(formatted_now, str)
        self.assertGreater(len(formatted_now), 0)
    
    def test_truncate_message(self):
        """测试截断消息"""
        long_message = "这是一个非常长的消息，需要被截断以避免超过长度限制。" * 100
        
        # 测试截断
        truncated = self.formatter._truncate_message(long_message, max_length=100)
        self.assertIsInstance(truncated, str)
        self.assertLessEqual(len(truncated), 100)
        
        # 测试不需要截断的情况
        short_message = "短消息"
        not_truncated = self.formatter._truncate_message(short_message, max_length=100)
        self.assertEqual(not_truncated, short_message)
    
    def test_escape_markdown(self):
        """测试转义Markdown特殊字符"""
        text_with_markdown = "这是一个*加粗*和_斜体_的文本，还有`代码`和[链接](http://example.com)"
        escaped = self.formatter._escape_markdown(text_with_markdown)
        
        self.assertIsInstance(escaped, str)
        # 检查特殊字符被转义
        self.assertIn(r'\*', escaped)  # 星号被转义
        self.assertIn(r'\_', escaped)  # 下划线被转义
    
    def test_escape_html(self):
        """测试转义HTML特殊字符"""
        text_with_html = "<div>这是一个<b>加粗</b>文本 & 符号</div>"
        escaped = self.formatter._escape_html(text_with_html)
        
        self.assertIsInstance(escaped, str)
        # 检查HTML字符被转义
        self.assertIn('&lt;', escaped)  # < 被转义
        self.assertIn('&gt;', escaped)  # > 被转义
        self.assertIn('&amp;', escaped)  # & 被转义
    
    def test_invalid_format(self):
        """测试无效格式"""
        # 根据实际API，format_signal接受多个单独参数
        symbol = 'BTC/USDT'
        signal_type = 'BUY'
        confidence = 0.85
        price = 50000.0
        timestamp = 1234567890.0
        additional_info = {'reason': '测试', 'indicators': {}}
        
        # 无效格式应该回退到默认格式
        result_dict = self.formatter.format_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            timestamp=timestamp,
            format_type='invalid_format',
            additional_info=additional_info
        )
        
        # format_signal返回一个字典，包含不同格式的消息
        self.assertIsInstance(result_dict, dict)
        # 即使格式无效，也应该返回某种格式的消息
        self.assertGreater(len(result_dict), 0)
    
    def test_missing_data(self):
        """测试缺失数据"""
        # 测试缺失必要字段的信号数据
        symbol = 'BTC/USDT'
        signal_type = 'BUY'  # 提供必要字段
        confidence = 0.5  # 提供必要字段
        price = 50000.0  # 提供必要字段
        timestamp = 1234567890.0
        
        # 应该能够处理缺失额外数据
        result_dict = self.formatter.format_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            timestamp=timestamp,
            format_type='plain',
            additional_info=None  # 不提供额外信息
        )
        
        # format_signal返回一个字典，包含不同格式的消息
        self.assertIsInstance(result_dict, dict)
        self.assertIn('plain', result_dict)
        result = result_dict.get('plain', '')
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()