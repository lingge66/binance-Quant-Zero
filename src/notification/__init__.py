"""
通知集成层模块 - 负责交易信号、风险警报、系统状态的多渠道通知

模块组成：
1. notification_manager - 通知调度与管理
2. telegram_notifier - Telegram机器人通知
3. email_notifier - 邮件通知（SMTP）
4. webhook_notifier - Webhook回调通知
5. message_formatter - 消息格式化与模板
6. notification_queue - 异步通知队列

设计原则：
- 多渠道支持：Telegram、Email、Webhook等
- 异步发送：非阻塞通知，避免影响主循环
- 消息队列：失败重试、优先级处理
- 模板系统：统一消息格式化
- 降级策略：主渠道失败时自动切换备用渠道

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

__version__ = '1.0.0'
__author__ = 'Coder'

# 将在后续开发中逐步实现各模块