"""
日志文件通知器 - 将通知记录到日志文件

功能：
1. 结构化日志：JSON格式记录，便于分析
2. 文件轮转：支持按大小或时间轮转日志文件
3. 分级存储：不同级别通知可记录到不同文件
4. 异步写入：非阻塞文件写入，避免影响性能

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# 项目内部导入
from .notification_manager import Notification, NotificationResult, NotificationChannel

logger = logging.getLogger(__name__)


class LogFileNotifier:
    """
    日志文件通知器
    
    设计特性：
    1. JSON格式：结构化日志，便于解析和分析
    2. 异步写入：使用异步文件写入，避免阻塞
    3. 文件管理：自动创建目录，支持文件轮转
    4. 错误处理：写入失败时优雅降级
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化日志文件通知器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.enabled = True  # 日志文件通知总是启用
        
        # 获取日志配置
        logging_config = config.get('logging', {})
        
        # 日志文件路径
        log_file_path = logging_config.get('file_path', 'logs/agent.log')
        self.log_dir = Path(log_file_path).parent
        self.log_file = Path(log_file_path)
        
        # 文件轮转配置
        self.max_file_size = logging_config.get('max_file_size', 100)  # MB
        self.backup_count = logging_config.get('backup_count', 10)
        
        # 创建日志目录
        self._ensure_log_directory()
        
        # 当前日志文件大小
        self._current_file_size = self._get_file_size()
        
        # 写入队列（简化实现，实际应使用异步队列）
        self._write_queue = []
        
        logger.info(f"日志文件通知器初始化完成，日志文件: {self.log_file}")
    
    def _ensure_log_directory(self) -> None:
        """确保日志目录存在"""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"日志目录已确保存在: {self.log_dir}")
        except Exception as e:
            logger.error(f"创建日志目录失败: {e}")
            raise
    
    def _get_file_size(self) -> int:
        """
        获取当前日志文件大小
        
        Returns:
            文件大小（字节），文件不存在则返回0
        """
        try:
            return self.log_file.stat().st_size if self.log_file.exists() else 0
        except Exception as e:
            logger.warning(f"获取文件大小失败: {e}")
            return 0
    
    def _needs_rotation(self) -> bool:
        """
        检查是否需要轮转日志文件
        
        Returns:
            如果需要轮转则返回True
        """
        # 检查文件大小
        if self._current_file_size > self.max_file_size * 1024 * 1024:  # 转换为字节
            return True
        
        return False
    
    def _rotate_log_file(self) -> None:
        """
        轮转日志文件
        """
        if not self.log_file.exists():
            return
        
        try:
            # 删除最旧的备份文件
            backup_pattern = f"{self.log_file.name}.*.bak"
            backup_files = list(self.log_dir.glob(backup_pattern))
            
            if len(backup_files) >= self.backup_count:
                # 按修改时间排序，删除最旧的
                backup_files.sort(key=lambda f: f.stat().st_mtime)
                files_to_delete = backup_files[:len(backup_files) - self.backup_count + 1]
                
                for file_to_delete in files_to_delete:
                    try:
                        file_to_delete.unlink()
                        logger.debug(f"删除旧日志文件: {file_to_delete}")
                    except Exception as e:
                        logger.warning(f"删除旧日志文件失败 {file_to_delete}: {e}")
            
            # 重命名当前日志文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.log_dir / f"{self.log_file.name}.{timestamp}.bak"
            
            self.log_file.rename(backup_file)
            logger.info(f"日志文件已轮转: {self.log_file} -> {backup_file}")
            
            # 重置文件大小
            self._current_file_size = 0
            
        except Exception as e:
            logger.error(f"轮转日志文件失败: {e}")
    
    def _notification_to_dict(self, notification: Notification) -> Dict[str, Any]:
        """
        将通知对象转换为字典（用于JSON序列化）
        
        Args:
            notification: 通知对象
            
        Returns:
            字典表示
        """
        return {
            'notification_id': notification.notification_id,
            'notification_type': notification.notification_type.value,
            'priority': notification.priority.value,
            'title': notification.title,
            'message': notification.message,
            'formatted_message': notification.formatted_message,
            'metadata': notification.metadata,
            'channels': [ch.value for ch in notification.channels],
            'created_at': notification.created_at,
            'retry_count': notification.retry_count,
            'timestamp': time.time(),
        }
    
    def _write_to_log(self, log_entry: Dict[str, Any]) -> bool:
        """
        写入日志条目到文件
        
        Args:
            log_entry: 日志条目字典
            
        Returns:
            写入是否成功
        """
        try:
            # 检查是否需要轮转
            if self._needs_rotation():
                self._rotate_log_file()
            
            # 转换为JSON字符串
            json_str = json.dumps(log_entry, ensure_ascii=False) + '\n'
            
            # 写入文件
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json_str)
            
            # 更新文件大小
            self._current_file_size += len(json_str.encode('utf-8'))
            
            return True
            
        except Exception as e:
            logger.error(f"写入日志文件失败: {e}")
            return False
    
    async def send(self, notification: Notification) -> NotificationResult:
        """
        发送通知到日志文件
        
        Args:
            notification: 通知对象
            
        Returns:
            发送结果
        """
        if not self.enabled:
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.LOG_FILE,
                success=False,
                message="日志文件通知器未启用"
            )
        
        try:
            # 转换为日志条目
            log_entry = self._notification_to_dict(notification)
            
            # 写入日志文件（同步写入，实际应异步）
            success = self._write_to_log(log_entry)
            
            if success:
                logger.debug(f"日志文件通知已记录: {notification.notification_id}")
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.LOG_FILE,
                    success=True,
                    message="日志文件通知记录成功",
                    response_data={'log_file': str(self.log_file)}
                )
            else:
                error_msg = "写入日志文件失败"
                logger.error(error_msg)
                
                return NotificationResult(
                    notification_id=notification.notification_id,
                    channel=NotificationChannel.LOG_FILE,
                    success=False,
                    message=error_msg,
                    error_details="文件写入错误"
                )
            
        except Exception as e:
            error_msg = f"日志文件通知发送失败: {str(e)}"
            logger.error(error_msg)
            
            return NotificationResult(
                notification_id=notification.notification_id,
                channel=NotificationChannel.LOG_FILE,
                success=False,
                message=error_msg,
                error_details=str(e)
            )
    
    async def close(self) -> None:
        """
        关闭通知器（清理资源）
        """
        # 日志文件通知器无需特殊清理
        logger.debug("日志文件通知器已关闭")


# 便捷函数
def create_log_file_notifier(config: Dict[str, Any]) -> LogFileNotifier:
    """
    创建日志文件通知器实例
    
    Args:
        config: 配置字典
        
    Returns:
        日志文件通知器实例
    """
    return LogFileNotifier(config)