"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


"""
消息格式化器 - 统一格式化通知消息

功能：
1. 模板系统：支持多种消息模板
2. 格式转换：纯文本、Markdown、HTML、Telegram格式
3. 变量替换：动态替换模板中的变量
4. 样式适配：根据不同渠道适配消息样式
5. 表情符号：自动添加相关表情符号

设计原则：
- 可配置性：通过配置文件定义模板
- 可扩展性：支持自定义模板和格式化器
- 一致性：不同渠道保持一致的风格
- 本地化：支持多语言消息（中英文）

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import re
from typing import Dict, Any, Optional, List, Union
from datetime import datetime


class MessageFormatter:
    """
    消息格式化器
    
    设计特性：
    1. 模板引擎：支持变量替换、条件逻辑
    2. 多渠道适配：为不同渠道生成适当格式
    3. 表情符号映射：根据内容自动添加表情
    4. 长度控制：自动截断过长的消息
    5. 链接处理：正确格式化URL链接
    """
    
    # 表情符号映射
    EMOJI_MAP = {
        # 信号类型
        'STRONG_BUY': '🟢🔺',
        'BUY': '🟢',
        'WEAK_BUY': '🟡',
        'NEUTRAL': '⚪',
        'WEAK_SELL': '🟡',
        'SELL': '🔴',
        'STRONG_SELL': '🔴🔻',
        
        # 风险级别
        'critical': '🔥',
        'error': '🚨',
        'warning': '⚠️',
        'info': 'ℹ️',
        'success': '✅',
        'failure': '❌',
        
        # 系统状态
        'starting': '🚀',
        'running': '🟢',
        'stopped': '🛑',
        'error': '💥',
        'reconnecting': '🔄',
        
        # 交易动作
        'buy': '📈',
        'sell': '📉',
        'hold': '📊',
        'cancel': '✖️',
    }
    
    # 默认模板
    DEFAULT_TEMPLATES = {
        'signal': {
            'plain': """{emoji} 交易信号: {symbol}
信号类型: {signal_type}
当前价格: ${price:,.2f}
置信度: {confidence:.1%}
时间: {timestamp}""",
            
            'markdown': """**{emoji} 交易信号: {symbol}**

**信号类型**: {signal_type}
**当前价格**: `${price:,.2f}`
**置信度**: `{confidence:.1%}`
**时间**: {timestamp}""",
            
            'html': """<b>{emoji} 交易信号: {symbol}</b>

<b>信号类型</b>: {signal_type}
<b>当前价格</b>: <code>${price:,.2f}</code>
<b>置信度</b>: <code>{confidence:.1%}</code>
<b>时间</b>: {timestamp}""",
        },
        
        'risk_alert': {
            'plain': """{emoji} 风险警报: {alert_type}
警报级别: {level}
消息: {message}
时间: {timestamp}""",
            
            'markdown': """**{emoji} 风险警报: {alert_type}**

**警报级别**: {level}
**消息**: {message}
**时间**: {timestamp}""",
            
            'html': """<b>{emoji} 风险警报: {alert_type}</b>

<b>警报级别</b>: {level}
<b>消息</b>: {message}
<b>时间</b>: {timestamp}""",
        },
        
        'trade_execution': {
            'plain': """{emoji} 交易执行: {symbol}
动作: {action}
数量: {amount}
价格: ${price:,.2f}
状态: {status}
时间: {timestamp}""",
            
            'markdown': """**{emoji} 交易执行: {symbol}**

**动作**: {action}
**数量**: {amount}
**价格**: `${price:,.2f}`
**状态**: {status}
**时间**: {timestamp}""",
            
            'html': """<b>{emoji} 交易执行: {symbol}</b>

<b>动作</b>: {action}
<b>数量</b>: {amount}
<b>价格</b>: <code>${price:,.2f}</code>
<b>状态</b>: {status}
<b>时间</b>: {timestamp}""",
        },
        
        'system_status': {
            'plain': """{emoji} 系统状态: {status}
消息: {message}
时间: {timestamp}""",
            
            'markdown': """**{emoji} 系统状态: {status}**

**消息**: {message}
**时间**: {timestamp}""",
            
            'html': """<b>{emoji} 系统状态: {status}</b>

<b>消息</b>: {message}
<b>时间</b>: {timestamp}""",
        },
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化消息格式化器
        
        Args:
            config: 可选，配置字典
        """
        self.config = config or {}
        
        # 加载模板
        self.templates = self.DEFAULT_TEMPLATES.copy()
        
        # 加载自定义模板（如果配置中有）
        custom_templates = self.config.get('templates', {})
        self.templates.update(custom_templates)
        
        # 格式化配置
        self.default_format = self.config.get('default_format', 'markdown')
        self.max_length = self.config.get('max_length', 4000)  # Telegram消息长度限制
        
        # 时间格式
        self.time_format = self.config.get('time_format', '%Y-%m-%d %H:%M:%S')
    
    def _get_emoji(self, key: str, default: str = '') -> str:
        """
        获取表情符号
        
        Args:
            key: 表情符号键
            default: 默认表情符号
            
        Returns:
            表情符号字符串
        """
        return self.EMOJI_MAP.get(key, default)
    
    def _format_timestamp(self, timestamp: Optional[float] = None) -> str:
        """
        格式化时间戳
        
        Args:
            timestamp: 可选，Unix时间戳，默认为当前时间
            
        Returns:
            格式化后的时间字符串
        """
        if timestamp is None:
            dt = datetime.now()
        else:
            dt = datetime.fromtimestamp(timestamp)
        
        return dt.strftime(self.time_format)
    
    def _truncate_message(self, message: str, max_length: Optional[int] = None) -> str:
        """
        截断消息到指定长度
        
        Args:
            message: 原始消息
            max_length: 最大长度，如为None则使用默认值
            
        Returns:
            截断后的消息
        """
        if max_length is None:
            max_length = self.max_length
        
        if len(message) <= max_length:
            return message
        
        # 在句子边界处截断
        truncated = message[:max_length - 3] + "..."
        
        # 尝试在段落边界截断
        last_paragraph = truncated.rfind('\n\n')
        if last_paragraph > max_length // 2:
            truncated = truncated[:last_paragraph] + "\n\n..."
        
        # 尝试在句子边界截断
        last_sentence = max(
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? '),
        )
        if last_sentence > max_length // 2:
            truncated = truncated[:last_sentence + 1] + ".."
        
        return truncated
    
    def _escape_markdown(self, text: str) -> str:
        """
        转义Markdown特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            转义后的文本
        """
        # Markdown需要转义的字符
        markdown_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        escaped_text = text
        for char in markdown_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        
        return escaped_text
    
    def _escape_html(self, text: str) -> str:
        """
        转义HTML特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            转义后的文本
        """
        html_escapes = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }
        
        escaped_text = text
        for char, escape in html_escapes.items():
            escaped_text = escaped_text.replace(char, escape)
        
        return escaped_text
    
    def format_signal(self, 
                     symbol: str,
                     signal_type: str,
                     confidence: float,
                     price: float,
                     timestamp: Optional[float] = None,
                     format_type: Optional[str] = None,
                     additional_info: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        格式化交易信号消息
        
        Args:
            symbol: 交易对
            signal_type: 信号类型
            confidence: 置信度 (0-1)
            price: 当前价格
            timestamp: 可选，时间戳
            format_type: 可选，格式类型 (plain/markdown/html)
            additional_info: 可选，附加信息
            
        Returns:
            包含不同格式消息的字典
        """
        if format_type is None:
            format_type = self.default_format
        
        # 获取表情符号
        emoji = self._get_emoji(signal_type, '⚪')
        
        # 准备变量
        variables = {
            'emoji': emoji,
            'symbol': symbol,
            'signal_type': signal_type,
            'confidence': confidence,
            'price': price,
            'timestamp': self._format_timestamp(timestamp),
        }
        
        # 添加附加信息
        if additional_info:
            variables.update(additional_info)
        
        # 获取模板
        template_group = self.templates.get('signal', {})
        
        # 生成各种格式的消息
        formatted_messages = {}
        
        for fmt in ['plain', 'markdown', 'html']:
            template = template_group.get(fmt)
            if not template:
                # 使用默认模板
                if fmt == 'plain':
                    template = self.DEFAULT_TEMPLATES['signal']['plain']
                elif fmt == 'markdown':
                    template = self.DEFAULT_TEMPLATES['signal']['markdown']
                elif fmt == 'html':
                    template = self.DEFAULT_TEMPLATES['signal']['html']
            
            # 应用模板
            try:
                message = template.format(**variables)
                
                # 转义特殊字符
                if fmt == 'markdown':
                    # 不需要额外转义，因为模板已经使用了Markdown格式
                    pass
                elif fmt == 'html':
                    # 对用户提供的变量进行HTML转义
                    for var_name, var_value in variables.items():
                        if isinstance(var_value, str) and var_name not in ['emoji']:
                            variables[var_name] = self._escape_html(var_value)
                    message = template.format(**variables)
                
                # 截断消息
                message = self._truncate_message(message)
                
                formatted_messages[fmt] = message
                
            except Exception as e:
                # 模板格式化失败，使用简单格式
                simple_message = f"{emoji} 交易信号: {symbol} - {signal_type} @ ${price:,.2f}"
                formatted_messages[fmt] = simple_message
        
        return formatted_messages
    
    def format_risk_alert(self,
                         alert_type: str,
                         level: str,
                         message: str,
                         timestamp: Optional[float] = None,
                         format_type: Optional[str] = None,
                         data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        格式化风险警报消息
        
        Args:
            alert_type: 警报类型
            level: 警报级别
            message: 警报消息
            timestamp: 可选，时间戳
            format_type: 可选，格式类型
            data: 可选，相关数据
            
        Returns:
            包含不同格式消息的字典
        """
        if format_type is None:
            format_type = self.default_format
        
        # 获取表情符号
        emoji = self._get_emoji(level, 'ℹ️')
        
        # 准备变量
        variables = {
            'emoji': emoji,
            'alert_type': alert_type,
            'level': level,
            'message': message,
            'timestamp': self._format_timestamp(timestamp),
        }
        
        # 添加数据到消息
        if data:
            # 将数据格式化为字符串
            data_lines = []
            for key, value in data.items():
                if isinstance(value, float):
                    value_str = f"{value:,.4f}"
                elif isinstance(value, int):
                    value_str = f"{value:,}"
                else:
                    value_str = str(value)
                data_lines.append(f"{key}: {value_str}")
            
            variables['data'] = "\n".join(data_lines)
        else:
            variables['data'] = "无"
        
        # 获取模板
        template_group = self.templates.get('risk_alert', {})
        
        # 生成各种格式的消息
        formatted_messages = {}
        
        for fmt in ['plain', 'markdown', 'html']:
            template = template_group.get(fmt)
            if not template:
                # 使用默认模板
                if fmt == 'plain':
                    template = self.DEFAULT_TEMPLATES['risk_alert']['plain']
                elif fmt == 'markdown':
                    template = self.DEFAULT_TEMPLATES['risk_alert']['markdown']
                elif fmt == 'html':
                    template = self.DEFAULT_TEMPLATES['risk_alert']['html']
            
            # 应用模板
            try:
                formatted_message = template.format(**variables)
                
                # 转义特殊字符
                if fmt == 'markdown':
                    # 对消息内容进行Markdown转义
                    variables['message'] = self._escape_markdown(message)
                    formatted_message = template.format(**variables)
                elif fmt == 'html':
                    # 对消息内容进行HTML转义
                    variables['message'] = self._escape_html(message)
                    formatted_message = template.format(**variables)
                
                # 截断消息
                formatted_message = self._truncate_message(formatted_message)
                
                formatted_messages[fmt] = formatted_message
                
            except Exception as e:
                # 模板格式化失败，使用简单格式
                simple_message = f"{emoji} 风险警报: {alert_type} - {message}"
                formatted_messages[fmt] = simple_message
        
        return formatted_messages
    
    def format_trade_execution(self,
                              symbol: str,
                              action: str,
                              amount: float,
                              price: float,
                              status: str,
                              timestamp: Optional[float] = None,
                              format_type: Optional[str] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        格式化交易执行消息
        
        Args:
            symbol: 交易对
            action: 交易动作 (buy/sell)
            amount: 交易数量
            price: 交易价格
            status: 交易状态
            timestamp: 可选，时间戳
            format_type: 可选，格式类型
            metadata: 可选，元数据
            
        Returns:
            包含不同格式消息的字典
        """
        if format_type is None:
            format_type = self.default_format
        
        # 获取表情符号
        action_emoji = self._get_emoji(action, '📊')
        status_emoji = self._get_emoji(status, '⚪')
        emoji = f"{action_emoji}{status_emoji}"
        
        # 准备变量
        variables = {
            'emoji': emoji,
            'symbol': symbol,
            'action': action,
            'amount': amount,
            'price': price,
            'status': status,
            'timestamp': self._format_timestamp(timestamp),
        }
        
        # 添加元数据
        if metadata:
            variables.update(metadata)
        
        # 获取模板
        template_group = self.templates.get('trade_execution', {})
        
        # 生成各种格式的消息
        formatted_messages = {}
        
        for fmt in ['plain', 'markdown', 'html']:
            template = template_group.get(fmt)
            if not template:
                # 使用默认模板
                if fmt == 'plain':
                    template = self.DEFAULT_TEMPLATES['trade_execution']['plain']
                elif fmt == 'markdown':
                    template = self.DEFAULT_TEMPLATES['trade_execution']['markdown']
                elif fmt == 'html':
                    template = self.DEFAULT_TEMPLATES['trade_execution']['html']
            
            # 应用模板
            try:
                formatted_message = template.format(**variables)
                
                # 截断消息
                formatted_message = self._truncate_message(formatted_message)
                
                formatted_messages[fmt] = formatted_message
                
            except Exception as e:
                # 模板格式化失败，使用简单格式
                simple_message = f"{emoji} 交易: {symbol} {action} {amount} @ ${price:,.2f} ({status})"
                formatted_messages[fmt] = simple_message
        
        return formatted_messages
    
    def format_system_status(self,
                           status: str,
                           message: str,
                           timestamp: Optional[float] = None,
                           format_type: Optional[str] = None,
                           details: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        格式化系统状态消息
        
        Args:
            status: 系统状态
            message: 状态消息
            timestamp: 可选，时间戳
            format_type: 可选，格式类型
            details: 可选，详细信息
            
        Returns:
            包含不同格式消息的字典
        """
        if format_type is None:
            format_type = self.default_format
        
        # 获取表情符号
        emoji = self._get_emoji(status, '⚪')
        
        # 准备变量
        variables = {
            'emoji': emoji,
            'status': status,
            'message': message,
            'timestamp': self._format_timestamp(timestamp),
        }
        
        # 添加详细信息
        if details:
            variables.update(details)
        
        # 获取模板
        template_group = self.templates.get('system_status', {})
        
        # 生成各种格式的消息
        formatted_messages = {}
        
        for fmt in ['plain', 'markdown', 'html']:
            template = template_group.get(fmt)
            if not template:
                # 使用默认模板
                if fmt == 'plain':
                    template = self.DEFAULT_TEMPLATES['system_status']['plain']
                elif fmt == 'markdown':
                    template = self.DEFAULT_TEMPLATES['system_status']['markdown']
                elif fmt == 'html':
                    template = self.DEFAULT_TEMPLATES['system_status']['html']
            
            # 应用模板
            try:
                formatted_message = template.format(**variables)
                
                # 转义特殊字符
                if fmt == 'markdown':
                    variables['message'] = self._escape_markdown(message)
                    formatted_message = template.format(**variables)
                elif fmt == 'html':
                    variables['message'] = self._escape_html(message)
                    formatted_message = template.format(**variables)
                
                # 截断消息
                formatted_message = self._truncate_message(formatted_message)
                
                formatted_messages[fmt] = formatted_message
                
            except Exception as e:
                # 模板格式化失败，使用简单格式
                simple_message = f"{emoji} 系统状态: {status} - {message}"
                formatted_messages[fmt] = simple_message
        
        return formatted_messages


# 便捷函数
def create_message_formatter(config: Optional[Dict[str, Any]] = None) -> MessageFormatter:
    """
    创建消息格式化器实例
    
    Args:
        config: 可选，配置字典
        
    Returns:
        消息格式化器实例
    """
    return MessageFormatter(config)


# 测试代码
if __name__ == "__main__":
    """模块自测"""
    formatter = MessageFormatter()
    
    # 测试交易信号格式化
    signal_messages = formatter.format_signal(
        symbol="BTC/USDT",
        signal_type="STRONG_BUY",
        confidence=0.85,
        price=65200.50,
        additional_info={"reason": "突破关键阻力位"}
    )
    
    print("交易信号格式化测试:")
    print("Plain:", signal_messages['plain'][:100] + "...")
    print("Markdown:", signal_messages['markdown'][:100] + "...")
    print("HTML:", signal_messages['html'][:100] + "...")
    print()
    
    # 测试风险警报格式化
    risk_messages = formatter.format_risk_alert(
        alert_type="margin_ratio",
        level="warning",
        message="保证金率低于警告阈值",
        data={"current_ratio": 1.45, "warning_threshold": 1.5}
    )
    
    print("风险警报格式化测试:")
    print("Plain:", risk_messages['plain'][:100] + "...")
    print()
    
    # 测试交易执行格式化
    trade_messages = formatter.format_trade_execution(
        symbol="ETH/USDT",
        action="buy",
        amount=0.5,
        price=3500.25,
        status="filled"
    )
    
    print("交易执行格式化测试:")
    print("Markdown:", trade_messages['markdown'][:100] + "...")