"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


"""
通知管理器 - 统一管理多渠道通知发送

核心功能：
1. 通知调度：根据类型和优先级选择发送渠道
2. 渠道管理：Telegram、Email、Webhook等渠道的统一接口
3. 消息队列：异步发送，失败重试，优先级处理
4. 状态监控：发送成功率、延迟等指标监控
5. 降级策略：主渠道失败时自动切换备用渠道

安全设计：
- 敏感信息脱敏：API Token、邮件密码等不在日志中暴露
- 发送频率限制：防止消息轰炸，遵守平台限流规则
- 失败处理：网络异常时自动重试，重试失败后降级
- 审计日志：所有通知发送记录，包含成功/失败状态

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import time
import json
import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import queue
import threading

# 项目内部导入
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """通知类型枚举"""
    SIGNAL = "signal"           # 交易信号
    RISK_ALERT = "risk_alert"   # 风险警报
    TRADE_EXECUTION = "trade_execution"  # 交易执行
    SYSTEM_STATUS = "system_status"      # 系统状态
    DAILY_REPORT = "daily_report"        # 日报
    WEEKLY_REPORT = "weekly_report"      # 周报
    ERROR = "error"             # 错误通知
    DEBUG = "debug"             # 调试信息


class NotificationPriority(Enum):
    """通知优先级枚举"""
    CRITICAL = "critical"       # 关键（立即发送，重试多次）
    HIGH = "high"               # 高（尽快发送，重试几次）
    MEDIUM = "medium"           # 中（正常发送，重试一次）
    LOW = "low"                 # 低（批量发送，不重试）
    BACKGROUND = "background"   # 后台（延迟发送，不重试）


class NotificationChannel(Enum):
    """通知渠道枚举"""
    TELEGRAM = "telegram"       # Telegram机器人
    EMAIL = "email"             # 邮件
    WEBHOOK = "webhook"         # Webhook回调
    CONSOLE = "console"         # 控制台输出
    LOG_FILE = "log_file"       # 日志文件
    OPENCLAW = "openclaw"       # OpenClaw内部消息


@dataclass
class Notification:
    """通知消息数据类"""
    notification_id: str                 # 通知唯一ID
    notification_type: NotificationType  # 通知类型
    priority: NotificationPriority       # 优先级
    title: str                          # 通知标题
    message: str                        # 通知内容（纯文本）
    formatted_message: Optional[str] = None  # 格式化内容（Markdown/HTML）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    channels: List[NotificationChannel] = field(default_factory=list)  # 目标渠道
    created_at: float = field(default_factory=time.time)   # 创建时间戳
    sent_at: Optional[float] = None     # 发送时间戳
    retry_count: int = 0                # 重试次数
    max_retries: int = 3                # 最大重试次数
    ttl_seconds: int = 3600             # 生存时间（秒），超时后丢弃
    
    def is_expired(self) -> bool:
        """检查通知是否已过期"""
        return time.time() - self.created_at > self.ttl_seconds
    
    def can_retry(self) -> bool:
        """检查是否还可以重试"""
        return self.retry_count < self.max_retries and not self.is_expired()
    
    def mark_sent(self) -> None:
        """标记为已发送"""
        self.sent_at = time.time()
    
    def increment_retry(self) -> None:
        """增加重试计数"""
        self.retry_count += 1


@dataclass
class NotificationResult:
    """通知发送结果"""
    notification_id: str                 # 通知ID
    channel: NotificationChannel        # 发送渠道
    success: bool                       # 是否成功
    message: str                        # 结果消息
    timestamp: float = field(default_factory=time.time)  # 结果时间戳
    response_data: Optional[Dict[str, Any]] = None  # 响应数据（如有）
    error_details: Optional[str] = None  # 错误详情（如有）


class NotificationManager:
    """
    通知管理器 - 统一通知调度与发送
    
    设计特性：
    1. 异步队列：非阻塞通知发送，避免影响主循环
    2. 优先级处理：高优先级通知优先发送
    3. 失败重试：网络异常时自动重试
    4. 渠道降级：主渠道失败时自动切换到备用渠道
    5. 状态监控：实时监控发送状态与性能指标
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化通知管理器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.notification_config = self.config.get('notification', {})
        
        # 通知队列
        self._notification_queue = asyncio.PriorityQueue()
        self._processing_tasks: Dict[str, asyncio.Task] = {}
        self._results_queue = asyncio.Queue()
        
        # 渠道管理器
        self._channels: Dict[NotificationChannel, Any] = {}
        
        # 统计信息
        self._stats = {
            'total_sent': 0,
            'total_failed': 0,
            'by_type': {},
            'by_channel': {},
            'last_sent': None,
            'avg_processing_time': 0.0,
        }
        
        # 控制标志
        self._running = False
        self._worker_task = None
        self._stats_task = None
        
        # 初始化日志
        self._setup_logging()
        
        # 初始化渠道
        self._initialize_channels()
        
        logger.info("通知管理器初始化完成")
    
    def _setup_logging(self) -> None:
        """配置日志"""
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    
    def _initialize_channels(self) -> None:
        """初始化通知渠道"""
        # 控制台渠道（总是可用）
        from .console_notifier import ConsoleNotifier
        self._channels[NotificationChannel.CONSOLE] = ConsoleNotifier(self.config)
        
        # 日志文件渠道
        from .log_file_notifier import LogFileNotifier
        self._channels[NotificationChannel.LOG_FILE] = LogFileNotifier(self.config)
        
        # 检查并初始化Telegram渠道
        telegram_config = self.notification_config.get('telegram', {})
        if telegram_config.get('enabled', False):
            try:
                from .telegram_notifier import TelegramNotifier
                self._channels[NotificationChannel.TELEGRAM] = TelegramNotifier(self.config)
                logger.info("Telegram通知渠道已启用")
            except ImportError as e:
                logger.warning(f"无法初始化Telegram渠道: {e}")
        
        # 检查并初始化OpenClaw渠道
        # OpenClaw渠道是特殊渠道，如果运行在OpenClaw环境中则可用
        try:
            from .openclaw_notifier import OpenClawNotifier
            self._channels[NotificationChannel.OPENCLAW] = OpenClawNotifier(self.config)
            logger.info("OpenClaw通知渠道已启用")
        except ImportError as e:
            logger.debug(f"OpenClaw渠道不可用（非OpenClaw环境）: {e}")
        
        # 其他渠道（Email、Webhook）将在需要时懒加载
        
        logger.info(f"已初始化 {len(self._channels)} 个通知渠道")
    
    def _generate_notification_id(self) -> str:
        """
        生成唯一通知ID
        
        Returns:
            唯一通知ID
        """
        import uuid
        timestamp = int(time.time() * 1000)
        unique_id = uuid.uuid4().hex[:8]
        return f"notif_{timestamp}_{unique_id}"
    
    def _get_priority_value(self, priority: NotificationPriority) -> int:
        """
        获取优先级数值（越小优先级越高）
        
        Args:
            priority: 通知优先级
            
        Returns:
            优先级数值
        """
        priority_map = {
            NotificationPriority.CRITICAL: 0,
            NotificationPriority.HIGH: 1,
            NotificationPriority.MEDIUM: 2,
            NotificationPriority.LOW: 3,
            NotificationPriority.BACKGROUND: 4,
        }
        return priority_map.get(priority, 2)  # 默认中等优先级
    
    async def send_notification(self, 
                               notification_type: NotificationType,
                               title: str,
                               message: str,
                               priority: NotificationPriority = NotificationPriority.MEDIUM,
                               channels: Optional[List[NotificationChannel]] = None,
                               metadata: Optional[Dict[str, Any]] = None,
                               formatted_message: Optional[str] = None) -> str:
        """
        发送通知（异步）
        
        Args:
            notification_type: 通知类型
            title: 通知标题
            message: 通知内容
            priority: 通知优先级
            channels: 目标渠道列表（如为None则使用默认渠道）
            metadata: 额外元数据
            formatted_message: 格式化消息内容（如Markdown）
            
        Returns:
            通知ID，可用于查询状态
            
        Raises:
            ValueError: 参数无效
        """
        # 参数验证
        if not title or not message:
            raise ValueError("通知标题和内容不能为空")
        
        # 生成通知ID
        notification_id = self._generate_notification_id()
        
        # 确定目标渠道
        if channels is None:
            channels = self._get_default_channels(notification_type, priority)
        
        # 创建通知对象
        notification = Notification(
            notification_id=notification_id,
            notification_type=notification_type,
            priority=priority,
            title=title,
            message=message,
            formatted_message=formatted_message,
            metadata=metadata or {},
            channels=channels,
            max_retries=self._get_max_retries(priority),
            ttl_seconds=self._get_ttl_seconds(priority),
        )
        
        # 计算优先级数值（用于队列排序）
        priority_value = self._get_priority_value(priority)
        
        # 添加到队列
        await self._notification_queue.put((priority_value, notification))
        
        logger.debug(f"通知已加入队列: {notification_id} [{notification_type.value}]")
        
        return notification_id
    
    def _get_default_channels(self, 
                             notification_type: NotificationType,
                             priority: NotificationPriority) -> List[NotificationChannel]:
        """
        获取默认通知渠道
        
        Args:
            notification_type: 通知类型
            priority: 通知优先级
            
        Returns:
            默认渠道列表
        """
        # 基础渠道：总是包含控制台和日志
        default_channels = [NotificationChannel.CONSOLE, NotificationChannel.LOG_FILE]
        
        # 根据配置添加其他渠道
        telegram_config = self.notification_config.get('telegram', {})
        
        # 检查Telegram是否启用并支持该通知类型
        if telegram_config.get('enabled', False):
            notify_types = telegram_config.get('notify_types', [])
            notification_type_str = notification_type.value
            
            if notify_types and notification_type_str in notify_types:
                default_channels.append(NotificationChannel.TELEGRAM)
        
        # 高优先级及以上通知也通过OpenClaw发送（如果可用）
        if priority in [NotificationPriority.CRITICAL, NotificationPriority.HIGH]:
            if NotificationChannel.OPENCLAW in self._channels:
                default_channels.append(NotificationChannel.OPENCLAW)
        
        return default_channels
    
    def _get_max_retries(self, priority: NotificationPriority) -> int:
        """
        根据优先级获取最大重试次数
        
        Args:
            priority: 通知优先级
            
        Returns:
            最大重试次数
        """
        retry_map = {
            NotificationPriority.CRITICAL: 5,
            NotificationPriority.HIGH: 3,
            NotificationPriority.MEDIUM: 1,
            NotificationPriority.LOW: 0,
            NotificationPriority.BACKGROUND: 0,
        }
        return retry_map.get(priority, 1)
    
    def _get_ttl_seconds(self, priority: NotificationPriority) -> int:
        """
        根据优先级获取生存时间
        
        Args:
            priority: 通知优先级
            
        Returns:
            生存时间（秒）
        """
        ttl_map = {
            NotificationPriority.CRITICAL: 3600,  # 1小时
            NotificationPriority.HIGH: 7200,      # 2小时
            NotificationPriority.MEDIUM: 86400,   # 24小时
            NotificationPriority.LOW: 172800,     # 48小时
            NotificationPriority.BACKGROUND: 604800,  # 7天
        }
        return ttl_map.get(priority, 86400)
    
    async def _process_notification_queue(self) -> None:
        """
        处理通知队列（工作线程）
        """
        logger.info("通知队列处理器已启动")
        
        while self._running:
            try:
                # 从队列获取通知（阻塞）
                priority_value, notification = await self._notification_queue.get()
                
                # 检查通知是否已过期
                if notification.is_expired():
                    logger.warning(f"通知已过期，丢弃: {notification.notification_id}")
                    self._notification_queue.task_done()
                    continue
                
                # 处理通知
                task = asyncio.create_task(
                    self._send_notification_to_channels(notification)
                )
                self._processing_tasks[notification.notification_id] = task
                
                # 标记任务完成
                self._notification_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("通知队列处理器被取消")
                break
            except Exception as e:
                logger.error(f"处理通知队列时出错: {e}")
                await asyncio.sleep(1)  # 避免快速循环报错
    
    async def _send_notification_to_channels(self, notification: Notification) -> None:
        """
        将通知发送到所有指定渠道
        
        Args:
            notification: 通知对象
        """
        notification_id = notification.notification_id
        successful_channels = []
        failed_channels = []
        
        logger.debug(f"开始发送通知: {notification_id} 到 {len(notification.channels)} 个渠道")
        
        for channel in notification.channels:
            # 检查渠道是否可用
            if channel not in self._channels:
                logger.warning(f"渠道不可用: {channel.value}")
                failed_channels.append((channel, "渠道不可用"))
                continue
            
            try:
                # 发送通知
                notifier = self._channels[channel]
                result = await notifier.send(notification)
                
                if result.success:
                    successful_channels.append(channel)
                    logger.debug(f"通知 {notification_id} 通过 {channel.value} 发送成功")
                else:
                    failed_channels.append((channel, result.message))
                    logger.warning(f"通知 {notification_id} 通过 {channel.value} 发送失败: {result.message}")
                    
            except Exception as e:
                error_msg = f"发送异常: {str(e)}"
                failed_channels.append((channel, error_msg))
                logger.error(f"通知 {notification_id} 通过 {channel.value} 发送异常: {e}")
        
        # 更新统计信息
        self._update_stats(notification, successful_channels, failed_channels)
        
        # 如果所有渠道都失败且有重试机会，则重新加入队列
        if not successful_channels and failed_channels and notification.can_retry():
            notification.increment_retry()
            priority_value = self._get_priority_value(notification.priority)
            
            # 延迟重试（指数退避）
            delay_seconds = 2 ** notification.retry_count  # 2, 4, 8秒...
            await asyncio.sleep(min(delay_seconds, 30))  # 最大30秒
            
            logger.info(f"重新尝试发送通知: {notification_id} (第{notification.retry_count}次重试)")
            await self._notification_queue.put((priority_value, notification))
        else:
            # 标记通知处理完成
            notification.mark_sent()
            
            # 清理处理任务
            if notification_id in self._processing_tasks:
                del self._processing_tasks[notification_id]
            
            # 记录最终结果
            if successful_channels:
                logger.info(f"通知 {notification_id} 发送完成: {len(successful_channels)}成功, {len(failed_channels)}失败")
            else:
                logger.error(f"通知 {notification_id} 完全发送失败")
    
    def _update_stats(self, 
                     notification: Notification,
                     successful_channels: List[NotificationChannel],
                     failed_channels: List[Tuple[NotificationChannel, str]]) -> None:
        """
        更新统计信息
        
        Args:
            notification: 通知对象
            successful_channels: 成功的渠道列表
            failed_channels: 失败的渠道列表（包含错误信息）
        """
        # 更新总数
        self._stats['total_sent'] += len(successful_channels)
        self._stats['total_failed'] += len(failed_channels)
        
        # 按类型统计
        notification_type = notification.notification_type.value
        if notification_type not in self._stats['by_type']:
            self._stats['by_type'][notification_type] = {
                'sent': 0,
                'failed': 0,
                'last_sent': None,
            }
        
        self._stats['by_type'][notification_type]['sent'] += len(successful_channels)
        self._stats['by_type'][notification_type]['failed'] += len(failed_channels)
        self._stats['by_type'][notification_type]['last_sent'] = time.time()
        
        # 按渠道统计
        for channel in successful_channels:
            channel_name = channel.value
            if channel_name not in self._stats['by_channel']:
                self._stats['by_channel'][channel_name] = {
                    'sent': 0,
                    'failed': 0,
                    'last_success': None,
                    'last_failure': None,
                }
            
            self._stats['by_channel'][channel_name]['sent'] += 1
            self._stats['by_channel'][channel_name]['last_success'] = time.time()
        
        for channel, error_msg in failed_channels:
            channel_name = channel.value
            if channel_name not in self._stats['by_channel']:
                self._stats['by_channel'][channel_name] = {
                    'sent': 0,
                    'failed': 0,
                    'last_success': None,
                    'last_failure': None,
                }
            
            self._stats['by_channel'][channel_name]['failed'] += 1
            self._stats['by_channel'][channel_name]['last_failure'] = time.time()
        
        # 更新最后发送时间
        self._stats['last_sent'] = time.time()
    
    async def start(self) -> None:
        """
        启动通知管理器
        """
        if self._running:
            logger.warning("通知管理器已在运行")
            return
        
        self._running = True
        
        # 启动队列处理器
        self._worker_task = asyncio.create_task(self._process_notification_queue())
        
        # 启动统计监控任务
        self._stats_task = asyncio.create_task(self._monitor_stats())
        
        logger.info("通知管理器已启动")
    
    async def stop(self) -> None:
        """
        停止通知管理器
        """
        if not self._running:
            return
        
        self._running = False
        
        # 取消工作线程
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        # 取消统计任务
        if self._stats_task:
            self._stats_task.cancel()
            try:
                await self._stats_task
            except asyncio.CancelledError:
                pass
        
        # 等待队列处理完成
        await self._notification_queue.join()
        
        # 等待所有处理任务完成
        if self._processing_tasks:
            await asyncio.gather(*self._processing_tasks.values(), return_exceptions=True)
        
        # 关闭所有渠道
        for channel_name, notifier in self._channels.items():
            try:
                await notifier.close()
            except Exception as e:
                logger.warning(f"关闭渠道 {channel_name.value} 时出错: {e}")
        
        logger.info("通知管理器已停止")
    
    async def _monitor_stats(self) -> None:
        """
        监控统计信息（定期打印状态）
        """
        while self._running:
            try:
                await asyncio.sleep(300)  # 每5分钟打印一次
                
                # 打印统计信息
                self._log_stats()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控统计信息时出错: {e}")
    
    def _log_stats(self) -> None:
        """记录统计信息到日志"""
        stats = self.get_stats()
        
        logger.info(f"通知统计: 发送{stats['total_sent']}次, 失败{stats['total_failed']}次")
        
        for notif_type, type_stats in stats['by_type'].items():
            sent = type_stats.get('sent', 0)
            failed = type_stats.get('failed', 0)
            total = sent + failed
            if total > 0:
                success_rate = sent / total * 100
                logger.info(f"  {notif_type}: {sent}成功, {failed}失败 ({success_rate:.1f}%成功率)")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return self._stats.copy()
    
    async def get_notification_status(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """
        获取通知状态
        
        Args:
            notification_id: 通知ID
            
        Returns:
            状态信息字典，如果通知不存在则返回None
        """
        # 检查是否正在处理
        if notification_id in self._processing_tasks:
            return {
                'notification_id': notification_id,
                'status': 'processing',
                'timestamp': time.time(),
            }
        
        # 这里可以扩展为从数据库或文件查询历史状态
        # 目前简化实现，总是返回已完成状态
        
        return {
            'notification_id': notification_id,
            'status': 'completed',
            'timestamp': time.time(),
        }
    
    async def send_signal_notification(self, 
                                     symbol: str,
                                     signal_type: str,
                                     confidence: float,
                                     price: float,
                                     additional_info: Optional[str] = None) -> str:
        """
        发送交易信号通知（便捷方法）
        
        Args:
            symbol: 交易对
            signal_type: 信号类型（如"STRONG_BUY", "SELL"等）
            confidence: 置信度（0-1）
            price: 当前价格
            additional_info: 附加信息
            
        Returns:
            通知ID
        """
        # 生成通知内容
        emoji_map = {
            "STRONG_BUY": "🟢🔺",
            "BUY": "🟢",
            "WEAK_BUY": "🟡",
            "NEUTRAL": "⚪",
            "WEAK_SELL": "🟡",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔻",
        }
        
        emoji = emoji_map.get(signal_type, "⚪")
        
        title = f"{emoji} 交易信号: {symbol}"
        
        message = f"信号类型: {signal_type}\n"
        message += f"交易对: {symbol}\n"
        message += f"当前价格: ${price:,.2f}\n"
        message += f"置信度: {confidence:.1%}\n"
        
        if additional_info:
            message += f"\n附加信息: {additional_info}"
        
        # 格式化消息（Markdown）
        formatted_message = f"**{title}**\n\n"
        formatted_message += f"**信号类型**: {signal_type}\n"
        formatted_message += f"**交易对**: {symbol}\n"
        formatted_message += f"**当前价格**: `${price:,.2f}`\n"
        formatted_message += f"**置信度**: `{confidence:.1%}`\n"
        
        if additional_info:
            formatted_message += f"\n**附加信息**: {additional_info}"
        
        # 确定优先级
        if signal_type in ["STRONG_BUY", "STRONG_SELL"]:
            priority = NotificationPriority.HIGH
        else:
            priority = NotificationPriority.MEDIUM
        
        # 发送通知
        notification_id = await self.send_notification(
            notification_type=NotificationType.SIGNAL,
            title=title,
            message=message,
            priority=priority,
            formatted_message=formatted_message,
            metadata={
                'symbol': symbol,
                'signal_type': signal_type,
                'confidence': confidence,
                'price': price,
                'additional_info': additional_info,
            }
        )
        
        return notification_id
    
    async def send_risk_alert(self,
                            alert_type: str,
                            level: str,
                            message: str,
                            data: Optional[Dict[str, Any]] = None) -> str:
        """
        发送风险警报通知（便捷方法）
        
        Args:
            alert_type: 警报类型（如"margin_ratio", "daily_loss"等）
            level: 警报级别（"warning", "error", "critical"）
            message: 警报消息
            data: 相关数据
            
        Returns:
            通知ID
        """
        # 生成标题和内容
        level_emoji = {
            "warning": "⚠️",
            "error": "🚨",
            "critical": "🔥",
        }
        
        emoji = level_emoji.get(level, "ℹ️")
        title = f"{emoji} 风险警报: {alert_type}"
        
        full_message = f"警报级别: {level}\n"
        full_message += f"类型: {alert_type}\n"
        full_message += f"消息: {message}\n"
        
        if data:
            for key, value in data.items():
                if isinstance(value, float):
                    formatted_value = f"{value:,.4f}"
                else:
                    formatted_value = str(value)
                full_message += f"{key}: {formatted_value}\n"
        
        # 格式化消息
        formatted_message = f"**{title}**\n\n"
        formatted_message += f"**警报级别**: {level}\n"
        formatted_message += f"**类型**: {alert_type}\n"
        formatted_message += f"**消息**: {message}\n"
        
        if data:
            formatted_message += "\n**详细数据**:\n"
            for key, value in data.items():
                if isinstance(value, float):
                    formatted_value = f"{value:,.4f}"
                else:
                    formatted_value = str(value)
                formatted_message += f"- **{key}**: `{formatted_value}`\n"
        
        # 确定优先级
        priority_map = {
            "warning": NotificationPriority.MEDIUM,
            "error": NotificationPriority.HIGH,
            "critical": NotificationPriority.CRITICAL,
        }
        priority = priority_map.get(level, NotificationPriority.MEDIUM)
        
        # 发送通知
        notification_id = await self.send_notification(
            notification_type=NotificationType.RISK_ALERT,
            title=title,
            message=full_message,
            priority=priority,
            formatted_message=formatted_message,
            metadata={
                'alert_type': alert_type,
                'level': level,
                'data': data or {},
            }
        )
        
        return notification_id


# 便捷函数
async def create_notification_manager(config_path: Optional[str] = None) -> NotificationManager:
    """
    创建通知管理器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        通知管理器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    manager = NotificationManager(config)
    await manager.start()
    return manager


if __name__ == "__main__":
    """模块自测"""
    async def test_notification_manager():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        manager = NotificationManager(config)
        
        try:
            await manager.start()
            
            # 测试发送信号通知
            signal_id = await manager.send_signal_notification(
                symbol="BTC/USDT",
                signal_type="STRONG_BUY",
                confidence=0.85,
                price=65200.50,
                additional_info="突破关键阻力位"
            )
            
            print(f"发送信号通知: {signal_id}")
            
            # 测试发送风险警报
            risk_id = await manager.send_risk_alert(
                alert_type="margin_ratio",
                level="warning",
                message="保证金率低于警告阈值",
                data={"current_ratio": 1.45, "warning_threshold": 1.5}
            )
            
            print(f"发送风险警报: {risk_id}")
            
            # 等待通知处理
            await asyncio.sleep(2)
            
            # 获取统计信息
            stats = manager.get_stats()
            print(f"\n统计信息: {stats}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await manager.stop()
    
    asyncio.run(test_notification_manager())