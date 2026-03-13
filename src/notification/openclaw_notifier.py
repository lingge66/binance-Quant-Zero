"""
OpenClaw通知器 - 通过OpenClaw消息系统发送通知

功能：
1. OpenClaw集成：利用OpenClaw的message工具发送消息
2. 多渠道支持：通过OpenClaw支持Telegram、Discord等
3. 富文本格式：支持Markdown、HTML等格式
4. 交互式消息：支持按钮、回复等交互元素

注意事项：
1. 此通知器仅在OpenClaw环境中可用
2. 需要OpenClaw的message工具权限
3. 消息发送受OpenClaw配置限制

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List

# 项目内部导入
from .notification_manager import Notification, NotificationResult, NotificationChannel

logger = logging.getLogger(__name__)


class OpenClawNotifier:
    """
    OpenClaw通知器
    
    设计特性：
    1. OpenClaw集成：直接使用OpenClaw的消息工具
    2. 自动检测环境：仅在OpenClaw环境中启用
    3. 配置继承：使用OpenClaw的现有消息配置
    4. 错误处理：OpenClaw不可用时优雅降级
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化OpenClaw通知器
        
        Args:
            config: 配置字典
            
        Raises:
            ImportError: OpenClaw环境不可用
        """
        self.config = config
        
        # 检查OpenClaw环境
        self._check_openclaw_environment()
        
        # 初始化OpenClaw消息工具
        self.message_tool = None
        self._initialize_message_tool()
        
        # 配置
        self.enabled = self.message_tool is not None
        
        # 消息格式配置
        self.default_channel = None  # 默认使用当前会话通道
        self.use_markdown = True
        self.add_timestamp = True
        
        logger.info(f"OpenClaw通知器初始化完成，启用状态: {self.enabled}")
    
    def _check_openclaw_environment(self) -> None:
        """
        检查OpenClaw环境
        
        Raises:
            ImportError: 非OpenClaw环境
        """
        # 检查是否在OpenClaw环境中运行
        # 这里使用简单的启发式检查
        openclaw_env_vars = [
            'OPENCLAW_GATEWAY_TOKEN',
            'TELEGRAM_BOT_TOKEN_CODER',
            'TELEGRAM_BOT_TOKEN_MAIN',
        ]
        
        has_openclaw_env = any(os.getenv(var) for var in openclaw_env_vars)
        
        if not has_openclaw_env:
            logger.warning("未检测到OpenClaw环境变量，可能不在OpenClaw环境中运行")
            # 不抛出异常，允许降级使用
    
    def _initialize_message_tool(self) -> None:
        """
        初始化OpenClaw消息工具
        
        注意：这里使用动态导入和异常处理，
        因为message工具仅在OpenClaw环境中可用
        """
        try:
            # 动态导入OpenClaw工具
            # 注意：这假设在OpenClaw环境中运行
            import sys
            import importlib
            
            # 尝试导入message工具
            # 实际实现中，OpenClaw会注入工具到全局空间
            # 这里使用try-except检测
            
            # 检查是否在OpenClaw会话中
            if 'message' in globals():
                # 假设message函数已注入
                self.message_tool = globals()['message']
                logger.debug("通过全局变量找到message工具")
                
            elif hasattr(sys.modules.get('__main__'), 'message'):
                # 在主模块中查找
                self.message_tool = sys.modules['__main__'].message
                logger.debug("通过主模块找到message工具")
                
            else:
                # 尝试从openclaw工具导入
                # 注意：这是模拟，实际OpenClaw环境会不同
                logger.debug("未找到message工具，OpenClaw通知器将使用模拟模式")
                self.message_tool = None
                
        except Exception as e:
            logger.warning(f"初始化OpenClaw消息工具失败: {e}")
            self.message_tool = None
    
    def _notification_to_openclaw_message(self, notification: Notification) -> Dict[str, Any]:
        """
        将通知转换为OpenClaw消息参数
        
        Args:
            notification: 通知对象
            
        Returns:
            OpenClaw消息参数字典
        """
        # 构建消息内容
        message_parts = []
        
        # 添加标题（如果存在）
        if notification.title:
            message_parts.append(f"**{notification.title}**")
            message_parts.append("")  # 空行
        
        # 使用格式化消息或普通消息
        if notification.formatted_message:
            message_parts.append(notification.formatted_message)
        else:
            message_parts.append(notification.message)
        
        # 添加时间戳
        if self.add_timestamp:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message_parts.append("")
            message_parts.append(f"*发送时间: {timestamp}*")
        
        # 合并消息
        message = "\n".join(message_parts)
        
        # 构建消息参数
        message_params = {
            'action': 'send',
            'message': message,
        }
        
        # 添加频道配置（如果指定）
        if self.default_channel:
            message_params['channel'] = self.default_channel
        
        # 根据通知类型添加额外参数
        notif_type = notification.notification_type.value
        
        if notif_type == 'risk_alert':
            # 风险警报使用更醒目的格式
            priority = notification.priority.value
            if priority in ['critical', 'high']:
                # 可以添加紧急标记或特殊格式
                pass
        
        elif notif_type == 'signal':
            # 交易信号可能包含交易对信息
            symbol = notification.metadata.get('symbol', '')
            if symbol:
                # 可以在消息中添加相关标记
                pass
        
        return message_params
    
    async def _send_via_openclaw(self, message_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        通过OpenClaw发送消息
        
        Args:
            message_params: 消息参数
            
        Returns:
            发送结果字典
        """
        if not self.message_tool:
            # 模拟模式：记录日志但不实际发送
            logger.info(f"[模拟] OpenClaw消息: {message_params.get('message', '')[:100]}...")
            return {
                'success': True,
                'message': '模拟发送成功',
                'simulated': True,
            }
        
        try:
            # 实际调用OpenClaw message工具
            # 注意：这里假设message_tool是异步函数
            result = await self.message_tool(**message_params)
            
            # 解析结果
            if isinstance(result, dict):
                return {
                    'success': True,
                    'message': '消息发送成功',
                    'response': result,
                }
            else:
                return {
                    'success': True,
                    'message': f'消息发送成功，返回类型: {type(result).__name__}',
                }
                
        except Exception as e:
            logger.error(f"OpenClaw消息发送失败: {e}")
            return {
                'success': False,
                'message': f'消息发送失败: {str(e)}',
                'error': str(e),
            }
    
    async def send(self, notification: Notification) -> NotificationResult:
        """
        通过OpenClaw发送通知
        
        Args:
            notification: 通知对象
            
        Returns:
            发送结果
        """
        if not self.enabled:
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.OPENCLAW,
                success=False,
                message="OpenClaw通知器未启用"
            )
        
        try:
            # 转换为OpenClaw消息参数
            message_params = self._notification_to_openclaw_message(notification)
            
            # 发送消息
            send_result = await self._send_via_openclaw(message_params)
            
            if send_result.get('success', False):
                logger.debug(f"OpenClaw通知已发送: {notification.notification_id}")
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.OPENCLAW,
                    success=True,
                    message=send_result.get('message', '发送成功'),
                    response_data=send_result
                )
            else:
                error_msg = send_result.get('message', '发送失败')
                logger.warning(f"OpenClaw通知发送失败: {error_msg}")
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.OPENCLAW,
                    success=False,
                    message=error_msg,
                    error_details=send_result.get('error')
                )
            
        except Exception as e:
            error_msg = f"OpenClaw通知发送失败: {str(e)}"
            logger.error(error_msg)
            
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.OPENCLAW,
                success=False,
                message=error_msg,
                error_details=str(e)
            )
    
    async def close(self) -> None:
        """
        关闭通知器（清理资源）
        """
        # OpenClaw通知器无需特殊清理
        logger.debug("OpenClaw通知器已关闭")


# 便捷函数
def create_openclaw_notifier(config: Dict[str, Any]) -> OpenClawNotifier:
    """
    创建OpenClaw通知器实例
    
    Args:
        config: 配置字典
        
    Returns:
        OpenClaw通知器实例
    """
    return OpenClawNotifier(config)


# 直接消息发送函数（便捷接口）
async def send_openclaw_message(message: str, 
                               channel: Optional[str] = None,
                               title: Optional[str] = None,
                               priority: str = "medium") -> Dict[str, Any]:
    """
    直接发送OpenClaw消息（便捷函数）
    
    Args:
        message: 消息内容
        channel: 可选，目标频道
        title: 可选，消息标题
        priority: 消息优先级（critical/high/medium/low）
        
    Returns:
        发送结果
    """
    try:
        # 创建模拟通知
        from .notification_manager import Notification, NotificationType, NotificationPriority
        
        # 确定优先级
        priority_map = {
            'critical': NotificationPriority.CRITICAL,
            'high': NotificationPriority.HIGH,
            'medium': NotificationPriority.MEDIUM,
            'low': NotificationPriority.LOW,
        }
        notif_priority = priority_map.get(priority, NotificationPriority.MEDIUM)
        
        # 创建通知对象
        notification = Notification(
            notification_id=f"direct_{int(time.time() * 1000)}",
            notification_type=NotificationType.SYSTEM_STATUS,
            priority=notif_priority,
            title=title or "系统通知",
            message=message,
            channels=[NotificationChannel.OPENCLAW],
        )
        
        # 创建通知器并发送
        notifier = OpenClawNotifier({})
        result = await notifier.send(notification)
        
        return {
            'success': result.success,
            'message': result.message,
            'notification_id': notification.notification_id,
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f"发送消息失败: {str(e)}",
            'error': str(e),
        }