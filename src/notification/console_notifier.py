"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


"""
控制台通知器 - 将通知输出到控制台

功能：
1. 彩色输出：根据通知类型和优先级使用不同颜色
2. 格式化显示：结构化显示通知内容
3. 时间戳：包含精确的发送时间
4. 调试模式：可选的详细输出

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# 项目内部导入
from .notification_manager import Notification, NotificationResult, NotificationChannel

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    """
    控制台通知器
    
    设计特性：
    1. 彩色输出：使用ANSI颜色代码增强可读性
    2. 分级显示：不同优先级使用不同格式
    3. 非阻塞：快速输出，不阻塞主循环
    4. 可配置：支持配置输出详细程度
    """
    
    # ANSI颜色代码
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        
        # 前景色
        'black': '\033[30m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        
        # 背景色
        'bg_black': '\033[40m',
        'bg_red': '\033[41m',
        'bg_green': '\033[42m',
        'bg_yellow': '\033[43m',
        'bg_blue': '\033[44m',
        'bg_magenta': '\033[45m',
        'bg_cyan': '\033[46m',
        'bg_white': '\033[47m',
    }
    
    # 通知类型颜色映射
    TYPE_COLORS = {
        'signal': 'green',
        'risk_alert': 'red',
        'trade_execution': 'blue',
        'system_status': 'cyan',
        'daily_report': 'magenta',
        'weekly_report': 'magenta',
        'error': 'red',
        'debug': 'yellow',
    }
    
    # 优先级颜色映射
    PRIORITY_COLORS = {
        'critical': ('red', 'bg_white'),
        'high': ('red', None),
        'medium': ('yellow', None),
        'low': ('blue', None),
        'background': ('dim', None),
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化控制台通知器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.enabled = True  # 控制台通知总是启用
        
        # 输出配置
        self.show_timestamp = True
        self.show_priority = True
        self.show_type = True
        self.use_colors = True  # 是否使用彩色输出
        self.verbose = False   # 详细模式（显示所有字段）
        
        logger.debug("控制台通知器初始化完成")
    
    def _colorize(self, text: str, color: Optional[str] = None, 
                 bg_color: Optional[str] = None, bold: bool = False) -> str:
        """
        为文本添加颜色
        
        Args:
            text: 要着色的文本
            color: 前景色名称
            bg_color: 背景色名称
            bold: 是否加粗
            
        Returns:
            着色后的文本（如果不启用颜色则返回原文本）
        """
        if not self.use_colors or not color:
            return text
        
        color_codes = []
        
        if bold:
            color_codes.append(self.COLORS['bold'])
        
        if color in self.COLORS:
            color_codes.append(self.COLORS[color])
        
        if bg_color and bg_color in self.COLORS:
            color_codes.append(self.COLORS[bg_color])
        
        if not color_codes:
            return text
        
        return f"{''.join(color_codes)}{text}{self.COLORS['reset']}"
    
    def _format_timestamp(self, timestamp: float) -> str:
        """
        格式化时间戳
        
        Args:
            timestamp: Unix时间戳
            
        Returns:
            格式化后的时间字符串
        """
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 保留毫秒
    
    def _format_notification(self, notification: Notification) -> str:
        """
        格式化通知消息
        
        Args:
            notification: 通知对象
            
        Returns:
            格式化后的消息字符串
        """
        lines = []
        
        # 构建标题行
        title_parts = []
        
        # 时间戳
        if self.show_timestamp:
            timestamp_str = self._format_timestamp(time.time())
            title_parts.append(f"[{timestamp_str}]")
        
        # 通知类型
        if self.show_type:
            notif_type = notification.notification_type.value
            type_color = self.TYPE_COLORS.get(notif_type, 'white')
            type_str = self._colorize(f"[{notif_type.upper()}]", type_color)
            title_parts.append(type_str)
        
        # 优先级
        if self.show_priority:
            priority = notification.priority.value
            priority_colors = self.PRIORITY_COLORS.get(priority, ('white', None))
            priority_str = self._colorize(f"[{priority.upper()}]", 
                                         priority_colors[0], priority_colors[1])
            title_parts.append(priority_str)
        
        # 通知ID（简短版本）
        short_id = notification.notification_id[-8:]
        id_str = self._colorize(f"[{short_id}]", 'dim')
        title_parts.append(id_str)
        
        # 标题
        title_parts.append(notification.title)
        
        # 合并标题行
        lines.append(' '.join(title_parts))
        
        # 消息内容
        lines.append('')
        lines.append(notification.message)
        
        # 元数据（详细模式）
        if self.verbose and notification.metadata:
            lines.append('')
            lines.append(self._colorize("元数据:", 'cyan'))
            for key, value in notification.metadata.items():
                if isinstance(value, float):
                    value_str = f"{value:.6f}"
                else:
                    value_str = str(value)
                lines.append(f"  {key}: {value_str}")
        
        # 格式化消息（如果存在）
        if notification.formatted_message and self.verbose:
            lines.append('')
            lines.append(self._colorize("格式化内容:", 'cyan'))
            lines.append(notification.formatted_message)
        
        return '\n'.join(lines)
    
    async def send(self, notification: Notification) -> NotificationResult:
        """
        发送通知到控制台
        
        Args:
            notification: 通知对象
            
        Returns:
            发送结果
        """
        if not self.enabled:
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.CONSOLE,
                success=False,
                message="控制台通知器未启用"
            )
        
        try:
            # 格式化消息
            formatted_message = self._format_notification(notification)
            
            # 输出到控制台
            print(formatted_message)
            
            # 记录到日志
            logger.debug(f"控制台通知已发送: {notification.notification_id}")
            
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.CONSOLE,
                success=True,
                message="控制台通知发送成功"
            )
            
        except Exception as e:
            error_msg = f"控制台通知发送失败: {str(e)}"
            logger.error(error_msg)
            
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.CONSOLE,
                success=False,
                message=error_msg,
                error_details=str(e)
            )
    
    async def close(self) -> None:
        """
        关闭通知器（清理资源）
        """
        # 控制台通知器无需特殊清理
        logger.debug("控制台通知器已关闭")


# 便捷函数
def create_console_notifier(config: Dict[str, Any]) -> ConsoleNotifier:
    """
    创建控制台通知器实例
    
    Args:
        config: 配置字典
        
    Returns:
        控制台通知器实例
    """
    return ConsoleNotifier(config)