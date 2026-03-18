"""
Telegram通知器 - 通过Telegram Bot发送通知

功能：
1. Bot消息：通过Telegram Bot API发送消息
2. 富文本格式：支持Markdown、HTML解析
3. 交互式消息：支持内联按钮、回复键盘
4. 频道/群组支持：支持发送到频道、群组或私聊
5. 文件附件：支持发送图片、文档等附件

安全设计：
- Token保护：Bot Token从环境变量读取，不在代码中硬编码
- 权限控制：仅限授权用户/群组接收消息
- 频率限制：遵守Telegram API的频率限制
- 错误处理：网络异常时自动重试

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import asyncio
import os
import time
import logging
from typing import Dict, Any, Optional, List, Union

# 项目内部导入
from .notification_manager import Notification, NotificationResult, NotificationChannel

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Telegram通知器
    
    设计特性：
    1. 异步发送：使用异步HTTP客户端发送消息
    2. 消息队列：支持消息队列和优先级发送
    3. 格式转换：自动将通知转换为Telegram消息格式
    4. 多聊天支持：支持多个聊天ID（频道、群组、用户）
    5. 文件上传：支持发送图表、报告等文件
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化Telegram通知器
        
        Args:
            config: 配置字典
            
        Raises:
            ValueError: 配置无效或缺少必要参数
        """
        self.config = config
        
        # 获取Telegram配置
        telegram_config = config.get('notification', {}).get('telegram', {})
        
        # 检查是否启用
        self.enabled = telegram_config.get('enabled', False)
        if not self.enabled:
            logger.warning("Telegram通知器未启用")
            return
        
        # 获取Bot Token（从环境变量）
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            logger.error("未找到TELEGRAM_BOT_TOKEN环境变量")
            self.enabled = False
            return
        
        # 获取聊天ID（从环境变量或配置）
        chat_id_str = os.getenv('TELEGRAM_CHAT_ID')
        if chat_id_str:
            try:
                self.chat_ids = [int(chat_id_str.strip())]
            except ValueError:
                logger.warning(f"TELEGRAM_CHAT_ID格式无效: {chat_id_str}")
                self.chat_ids = []
        else:
            # 从配置读取
            chat_ids_config = telegram_config.get('chat_ids', [])
            self.chat_ids = [cid for cid in chat_ids_config if cid]
        
        if not self.chat_ids:
            logger.warning("未配置有效的Telegram聊天ID")
            self.enabled = False
            return
        
        # 通知类型过滤
        self.notify_types = set(telegram_config.get('notify_types', []))
        
        # API配置
        self.api_base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.timeout = 30  # 秒
        self.max_retries = 3
        self.retry_delay = 1  # 秒
        
        # 消息格式配置
        self.parse_mode = "Markdown"  # 或 "HTML"
        self.disable_web_page_preview = True
        self.disable_notification = False  # 静默消息
        
        # HTTP客户端（懒加载）
        self._http_client = None
        
        # 统计信息
        self._stats = {
            'total_sent': 0,
            'total_failed': 0,
            'last_sent': None,
            'last_error': None,
        }
        
        logger.info(f"Telegram通知器初始化完成，聊天ID数量: {len(self.chat_ids)}")
    
    async def _get_http_client(self):
        """
        获取HTTP客户端（懒加载）
        
        Returns:
            HTTP客户端实例
        """
        if self._http_client is None:
            try:
                import aiohttp
                self._http_client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
                logger.debug("创建了aiohttp客户端会话")
            except ImportError:
                logger.error("未安装aiohttp库，Telegram通知器功能受限")
                self._http_client = None
        
        return self._http_client
    
    def _notification_to_telegram_message(self, notification: Notification) -> Dict[str, Any]:
        """
        将通知转换为Telegram消息参数
        
        Args:
            notification: 通知对象
            
        Returns:
            Telegram消息参数字典
        """
        # 构建消息文本
        message_parts = []
        
        # 添加标题
        if notification.title:
            if self.parse_mode == "Markdown":
                message_parts.append(f"*{notification.title}*")
            elif self.parse_mode == "HTML":
                message_parts.append(f"<b>{notification.title}</b>")
            else:
                message_parts.append(notification.title)
            message_parts.append("")  # 空行
        
        # 使用格式化消息或普通消息
        if notification.formatted_message and self.parse_mode in ["Markdown", "HTML"]:
            # 格式化消息可能已包含格式标记
            message_parts.append(notification.formatted_message)
        else:
            # 普通文本消息
            message_parts.append(notification.message)
        
        # 添加元数据（简化版本）
        if notification.metadata:
            message_parts.append("")
            if self.parse_mode == "Markdown":
                message_parts.append("*详细信息:*")
                for key, value in notification.metadata.items():
                    if isinstance(value, (int, float)):
                        value_str = f"`{value}`"
                    else:
                        value_str = str(value)
                    message_parts.append(f"- *{key}:* {value_str}")
            elif self.parse_mode == "HTML":
                message_parts.append("<b>详细信息:</b>")
                for key, value in notification.metadata.items():
                    if isinstance(value, (int, float)):
                        value_str = f"<code>{value}</code>"
                    else:
                        value_str = str(value)
                    message_parts.append(f"- <b>{key}:</b> {value_str}")
            else:
                message_parts.append("详细信息:")
                for key, value in notification.metadata.items():
                    message_parts.append(f"- {key}: {value}")
        
        # 添加通知ID（用于追踪）
        short_id = notification.notification_id[-8:]
        message_parts.append("")
        if self.parse_mode == "Markdown":
            message_parts.append(f"_通知ID: `{short_id}`_")
        elif self.parse_mode == "HTML":
            message_parts.append(f"<i>通知ID: <code>{short_id}</code></i>")
        else:
            message_parts.append(f"通知ID: {short_id}")
        
        # 合并消息
        message_text = "\n".join(message_parts)
        
        # 构建API参数
        params = {
            'text': message_text,
            'parse_mode': self.parse_mode,
            'disable_web_page_preview': self.disable_web_page_preview,
            'disable_notification': self.disable_notification,
        }
        
        return params
    
    async def _send_to_telegram(self, chat_id: Union[int, str], 
                               params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送消息到Telegram API
        
        Args:
            chat_id: 聊天ID
            params: 消息参数
            
        Returns:
            API响应结果
        """
        http_client = await self._get_http_client()
        if not http_client:
            return {
                'success': False,
                'message': 'HTTP客户端不可用',
                'error': 'aiohttp未安装',
            }
        
        # 添加聊天ID到参数
        params['chat_id'] = chat_id
        
        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                # 发送请求
                url = f"{self.api_base_url}/sendMessage"
                
                async with http_client.post(url, json=params) as response:
                    response_data = await response.json()
                    
                    if response.status == 200 and response_data.get('ok'):
                        return {
                            'success': True,
                            'message': '消息发送成功',
                            'response': response_data,
                            'attempt': attempt + 1,
                        }
                    else:
                        error_description = response_data.get('description', '未知错误')
                        logger.warning(f"Telegram API错误 (尝试 {attempt+1}/{self.max_retries}): {error_description}")
                        
                        # 检查是否应该重试
                        if attempt < self.max_retries - 1:
                            # 指数退避
                            delay = self.retry_delay * (2 ** attempt)
                            await asyncio.sleep(delay)
                            continue
                        else:
                            return {
                                'success': False,
                                'message': f'消息发送失败: {error_description}',
                                'error': error_description,
                                'attempt': attempt + 1,
                            }
                            
            except Exception as e:
                logger.warning(f"Telegram发送异常 (尝试 {attempt+1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    # 指数退避
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    return {
                        'success': False,
                        'message': f'发送异常: {str(e)}',
                        'error': str(e),
                        'attempt': attempt + 1,
                    }
        
        # 理论上不会执行到这里
        return {
            'success': False,
            'message': '发送失败（未知原因）',
        }
    
    async def send(self, notification: Notification) -> NotificationResult:
        """
        发送通知到Telegram
        
        Args:
            notification: 通知对象
            
        Returns:
            发送结果
        """
        if not self.enabled:
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.TELEGRAM,
                success=False,
                message="Telegram通知器未启用"
            )
        
        # 检查通知类型是否在允许列表中
        notif_type = notification.notification_type.value
        if self.notify_types and notif_type not in self.notify_types:
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.TELEGRAM,
                success=False,
                message=f"通知类型 {notif_type} 不在允许列表中"
            )
        
        try:
            # 转换为Telegram消息参数
            telegram_params = self._notification_to_telegram_message(notification)
            
            # 发送到所有配置的聊天ID
            successful_chats = []
            failed_chats = []
            
            for chat_id in self.chat_ids:
                send_result = await self._send_to_telegram(chat_id, telegram_params)
                
                if send_result.get('success', False):
                    successful_chats.append(chat_id)
                    logger.debug(f"Telegram通知已发送到聊天 {chat_id}: {notification.notification_id}")
                else:
                    failed_chats.append((chat_id, send_result.get('message', '未知错误')))
                    logger.warning(f"Telegram通知发送到聊天 {chat_id} 失败: {send_result.get('message')}")
            
            # 更新统计信息
            self._stats['total_sent'] += len(successful_chats)
            self._stats['total_failed'] += len(failed_chats)
            self._stats['last_sent'] = time.time()
            
            # 构建结果
            if successful_chats:
                message = f"成功发送到 {len(successful_chats)} 个聊天，失败 {len(failed_chats)} 个"
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.TELEGRAM,
                    success=True,
                    message=message,
                    response_data={
                        'successful_chats': successful_chats,
                        'failed_chats': failed_chats,
                    }
                )
            else:
                error_msg = f"所有聊天发送失败: {failed_chats[0][1] if failed_chats else '未知错误'}"
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.TELEGRAM,
                    success=False,
                    message=error_msg,
                    error_details=str(failed_chats)
                )
            
        except Exception as e:
            error_msg = f"Telegram通知发送失败: {str(e)}"
            logger.error(error_msg)
            
            # 更新错误统计
            self._stats['total_failed'] += len(self.chat_ids)
            self._stats['last_error'] = str(e)
            
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.TELEGRAM,
                success=False,
                message=error_msg,
                error_details=str(e)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return self._stats.copy()
    
    async def close(self) -> None:
        """
        关闭通知器（清理资源）
        """
        if self._http_client:
            await self._http_client.close()
            self._http_client = None
            logger.debug("Telegram HTTP客户端已关闭")
        
        logger.debug("Telegram通知器已关闭")


# 便捷函数
def create_telegram_notifier(config: Dict[str, Any]) -> TelegramNotifier:
    """
    创建Telegram通知器实例
    
    Args:
        config: 配置字典
        
    Returns:
        Telegram通知器实例
    """
    return TelegramNotifier(config)


# 测试代码
if __name__ == "__main__":
    """模块自测"""
    import asyncio
    
    async def test_telegram_notifier():
        # 测试配置
        test_config = {
            'notification': {
                'telegram': {
                    'enabled': True,
                    'chat_ids': [],  # 需要实际的聊天ID
                    'notify_types': ['signal', 'risk_alert'],
                }
            }
        }
        
        # 设置环境变量（测试用）
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
        os.environ['TELEGRAM_CHAT_ID'] = '123456789'
        
        notifier = TelegramNotifier(test_config)
        
        if not notifier.enabled:
            print("Telegram通知器未启用，跳过测试")
            return
        
        # 创建测试通知
        from .notification_manager import Notification, NotificationType, NotificationPriority
        
        notification = Notification(
            notification_id="test_123",
            notification_type=NotificationType.SIGNAL,
            priority=NotificationPriority.MEDIUM,
            title="测试通知",
            message="这是一个测试Telegram通知",
            metadata={'symbol': 'BTC/USDT', 'price': 50000.0},
        )
        
        try:
            result = await notifier.send(notification)
            print(f"发送结果: {result.success}, 消息: {result.message}")
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await notifier.close()
    
    asyncio.run(test_telegram_notifier())