"""
风险报告模块 - 风险监控、报告与可视化

核心功能：
1. 实时风险仪表盘：关键风险指标实时监控
2. 风险事件日志：记录所有风险事件与决策
3. 风险评估报告：定期生成风险评估报告
4. 风险预警通知：触发风险阈值时发送通知
5. 历史数据分析：风险趋势与模式识别

设计特性：
- 多格式输出：控制台、文件、WebHook、消息推送
- 实时更新：秒级更新关键风险指标
- 分级预警：信息/警告/错误/关键四级预警
- 审计追踪：完整可追溯的风险事件链

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import csv
from pathlib import Path

# 第三方库
import pandas as pd
import numpy as np

# 项目内部导入
from config.config_manager import ConfigManager
from .account_monitor import AccountMonitor, AccountBalance
from .rule_engine import RiskRuleEngine, RuleResult
from .circuit_breaker import CircuitBreaker, BreakerEvent

logger = logging.getLogger(__name__)


class ReportLevel(Enum):
    """报告级别枚举"""
    DEBUG = "debug"        # 调试信息
    INFO = "info"          # 一般信息
    WARNING = "warning"    # 警告信息
    ERROR = "error"        # 错误信息
    CRITICAL = "critical"  # 关键信息


class OutputFormat(Enum):
    """输出格式枚举"""
    CONSOLE = "console"    # 控制台输出
    JSON = "json"          # JSON格式
    CSV = "csv"            # CSV格式
    HTML = "html"          # HTML格式
    MARKDOWN = "markdown"  # Markdown格式
    TELEGRAM = "telegram"  # Telegram消息
    EMAIL = "email"        # 电子邮件


@dataclass
class RiskMetric:
    """风险指标数据类"""
    name: str                           # 指标名称
    value: float                        # 指标值
    unit: str                           # 单位
    threshold: float                    # 阈值
    status: str                         # 状态（normal/warning/error/critical）
    trend: str                          # 趋势（up/down/stable）
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))  # 时间戳


@dataclass
class RiskEvent:
    """风险事件数据类"""
    event_id: str                       # 事件ID
    event_type: str                     # 事件类型
    level: ReportLevel                  # 事件级别
    title: str                          # 事件标题
    description: str                    # 事件描述
    source: str                         # 事件来源
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))  # 时间戳


@dataclass
class RiskReport:
    """风险报告数据类"""
    report_id: str                      # 报告ID
    report_type: str                    # 报告类型（实时/日报/周报/月报）
    period_start: int                   # 报告期开始时间
    period_end: int                     # 报告期结束时间
    summary: Dict[str, Any]             # 报告摘要
    metrics: List[RiskMetric]           # 风险指标
    events: List[RiskEvent]             # 风险事件
    recommendations: List[str]          # 风险建议
    generated_at: int = field(default_factory=lambda: int(time.time() * 1000))  # 生成时间


class RiskReporter:
    """
    风险报告器 - 风险监控与报告系统
    
    设计原则：
    1. 实时性：秒级更新关键风险指标
    2. 全面性：覆盖所有风险维度
    3. 可操作性：提供具体风险建议
    4. 可追溯性：完整事件链与审计日志
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化风险报告器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.metrics_history: Dict[str, List[RiskMetric]] = {}
        self.events_history: List[RiskEvent] = []
        self.reports_history: List[RiskReport] = []
        
        # 历史记录限制
        self.max_metrics_history = 10000  # 每个指标最多保存10000条记录
        self.max_events_history = 5000    # 最多保存5000个事件
        self.max_reports_history = 1000   # 最多保存1000份报告
        
        # 输出配置
        self.output_formats = [OutputFormat.CONSOLE]
        self.output_path = "./reports"
        self.enable_telegram = False
        self.enable_email = False
        
        # 预警配置
        self.warning_thresholds = {}
        self.alert_cooldown = {}  # 预警冷却时间
        
        # 初始化日志
        self._setup_logging()
        
        # 加载配置
        self._load_config()
        
        # 确保输出目录存在
        self._ensure_output_directory()
    
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
    
    def _load_config(self) -> None:
        """加载配置"""
        try:
            reporter_config = self.config.get('risk.reporter', {})
            
            if reporter_config:
                # 输出格式
                format_strs = reporter_config.get('output_formats', ['console'])
                self.output_formats = [OutputFormat(f) for f in format_strs]
                
                # 输出路径
                self.output_path = reporter_config.get('output_path', './reports')
                
                # 通信渠道
                self.enable_telegram = reporter_config.get('enable_telegram', False)
                self.enable_email = reporter_config.get('enable_email', False)
                
                # 预警阈值
                self.warning_thresholds = reporter_config.get('warning_thresholds', {})
                
                logger.info(f"风险报告器配置加载: 输出格式={[f.value for f in self.output_formats]}")
        except Exception as e:
            logger.warning(f"加载风险报告器配置失败，使用默认值: {e}")
    
    def _ensure_output_directory(self) -> None:
        """确保输出目录存在"""
        try:
            Path(self.output_path).mkdir(parents=True, exist_ok=True)
            logger.debug(f"输出目录已确保: {self.output_path}")
        except Exception as e:
            logger.error(f"创建输出目录失败: {e}")
    
    def add_metric(self, metric: RiskMetric) -> None:
        """
        添加风险指标
        
        Args:
            metric: 风险指标
        """
        # 初始化指标历史记录
        if metric.name not in self.metrics_history:
            self.metrics_history[metric.name] = []
        
        # 添加新指标
        self.metrics_history[metric.name].append(metric)
        
        # 限制历史记录大小
        if len(self.metrics_history[metric.name]) > self.max_metrics_history:
            self.metrics_history[metric.name] = self.metrics_history[metric.name][-self.max_metrics_history:]
        
        # 检查预警阈值
        self._check_metric_threshold(metric)
        
        logger.debug(f"风险指标添加: {metric.name}={metric.value} {metric.unit} ({metric.status})")
    
    def _check_metric_threshold(self, metric: RiskMetric) -> None:
        """
        检查指标阈值并触发预警
        
        Args:
            metric: 风险指标
        """
        try:
            # 检查是否有配置阈值
            if metric.name in self.warning_thresholds:
                threshold_config = self.warning_thresholds[metric.name]
                warning_level = threshold_config.get('warning', None)
                error_level = threshold_config.get('error', None)
                critical_level = threshold_config.get('critical', None)
                
                # 检查冷却时间
                current_time = time.time()
                last_alert_time = self.alert_cooldown.get(metric.name, 0)
                alert_interval = threshold_config.get('alert_interval', 300)  # 默认5分钟
                
                if current_time - last_alert_time < alert_interval:
                    return  # 仍在冷却期
                
                # 检查阈值
                actual_value = abs(metric.value) if threshold_config.get('absolute', False) else metric.value
                
                if critical_level is not None and actual_value >= critical_level:
                    self.trigger_alert(
                        level=ReportLevel.CRITICAL,
                        title=f"关键风险预警: {metric.name}",
                        description=f"{metric.name} 达到关键阈值: {actual_value} {metric.unit} ≥ {critical_level} {metric.unit}",
                        source="threshold_monitor"
                    )
                    self.alert_cooldown[metric.name] = current_time
                
                elif error_level is not None and actual_value >= error_level:
                    self.trigger_alert(
                        level=ReportLevel.ERROR,
                        title=f"风险错误预警: {metric.name}",
                        description=f"{metric.name} 达到错误阈值: {actual_value} {metric.unit} ≥ {error_level} {metric.unit}",
                        source="threshold_monitor"
                    )
                    self.alert_cooldown[metric.name] = current_time
                
                elif warning_level is not None and actual_value >= warning_level:
                    self.trigger_alert(
                        level=ReportLevel.WARNING,
                        title=f"风险警告预警: {metric.name}",
                        description=f"{metric.name} 达到警告阈值: {actual_value} {metric.unit} ≥ {warning_level} {metric.unit}",
                        source="threshold_monitor"
                    )
                    self.alert_cooldown[metric.name] = current_time
                    
        except Exception as e:
            logger.error(f"检查指标阈值失败 {metric.name}: {e}")
    
    def add_event(self, event: RiskEvent) -> None:
        """
        添加风险事件
        
        Args:
            event: 风险事件
        """
        self.events_history.append(event)
        
        # 限制历史记录大小
        if len(self.events_history) > self.max_events_history:
            self.events_history = self.events_history[-self.max_events_history:]
        
        # 根据事件级别输出
        if event.level == ReportLevel.CRITICAL:
            logger.critical(f"关键风险事件: {event.title} - {event.description}")
        elif event.level == ReportLevel.ERROR:
            logger.error(f"风险错误事件: {event.title} - {event.description}")
        elif event.level == ReportLevel.WARNING:
            logger.warning(f"风险警告事件: {event.title} - {event.description}")
        else:
            logger.info(f"风险信息事件: {event.title} - {event.description}")
        
        # 输出到其他格式
        self._output_event(event)
    
    def add_report(self, report: RiskReport) -> None:
        """
        添加风险报告
        
        Args:
            report: 风险报告
        """
        self.reports_history.append(report)
        
        # 限制历史记录大小
        if len(self.reports_history) > self.max_reports_history:
            self.reports_history = self.reports_history[-self.max_reports_history:]
        
        logger.info(f"风险报告生成: {report.report_type} (ID: {report.report_id})")
        
        # 输出报告
        self._output_report(report)
    
    def _output_event(self, event: RiskEvent) -> None:
        """
        输出风险事件到配置的格式
        
        Args:
            event: 风险事件
        """
        for output_format in self.output_formats:
            try:
                if output_format == OutputFormat.CONSOLE:
                    self._output_event_to_console(event)
                elif output_format == OutputFormat.JSON:
                    self._output_event_to_json(event)
                elif output_format == OutputFormat.CSV:
                    self._output_event_to_csv(event)
                elif output_format == OutputFormat.TELEGRAM and self.enable_telegram:
                    self._output_event_to_telegram(event)
                elif output_format == OutputFormat.EMAIL and self.enable_email:
                    self._output_event_to_email(event)
            except Exception as e:
                logger.error(f"输出事件到 {output_format.value} 失败: {e}")
    
    def _output_report(self, report: RiskReport) -> None:
        """
        输出风险报告到配置的格式
        
        Args:
            report: 风险报告
        """
        for output_format in self.output_formats:
            try:
                if output_format == OutputFormat.CONSOLE:
                    self._output_report_to_console(report)
                elif output_format == OutputFormat.JSON:
                    self._output_report_to_json(report)
                elif output_format == OutputFormat.HTML:
                    self._output_report_to_html(report)
                elif output_format == OutputFormat.MARKDOWN:
                    self._output_report_to_markdown(report)
            except Exception as e:
                logger.error(f"输出报告到 {output_format.value} 失败: {e}")
    
    def _output_event_to_console(self, event: RiskEvent) -> None:
        """输出事件到控制台"""
        # 根据级别选择颜色（简化实现）
        level_colors = {
            ReportLevel.CRITICAL: "\033[91m",  # 红色
            ReportLevel.ERROR: "\033[91m",     # 红色
            ReportLevel.WARNING: "\033[93m",   # 黄色
            ReportLevel.INFO: "\033[92m",      # 绿色
            ReportLevel.DEBUG: "\033[90m",     # 灰色
        }
        
        reset_color = "\033[0m"
        color = level_colors.get(event.level, reset_color)
        
        timestamp = datetime.fromtimestamp(event.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"{color}[{timestamp}] [{event.level.value.upper()}] {event.title}{reset_color}")
        print(f"   来源: {event.source}")
        print(f"   描述: {event.description}")
        if event.metadata:
            print(f"   元数据: {json.dumps(event.metadata, ensure_ascii=False, indent=2)}")
        print()
    
    def _output_event_to_json(self, event: RiskEvent) -> None:
        """输出事件到JSON文件"""
        try:
            # 准备事件数据
            event_data = {
                'event_id': event.event_id,
                'event_type': event.event_type,
                'level': event.level.value,
                'title': event.title,
                'description': event.description,
                'source': event.source,
                'metadata': event.metadata,
                'timestamp': event.timestamp,
                'formatted_time': datetime.fromtimestamp(event.timestamp / 1000).isoformat()
            }
            
            # 写入文件
            filename = f"risk_events_{datetime.now().strftime('%Y%m%d')}.json"
            filepath = Path(self.output_path) / filename
            
            # 读取现有数据或创建新文件
            events_list = []
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        events_list = json.load(f)
                        if not isinstance(events_list, list):
                            events_list = []
                except:
                    events_list = []
            
            # 添加新事件
            events_list.append(event_data)
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(events_list, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"事件已保存到JSON文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存事件到JSON失败: {e}")
    
    def _output_event_to_csv(self, event: RiskEvent) -> None:
        """输出事件到CSV文件"""
        try:
            filename = f"risk_events_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = Path(self.output_path) / filename
            
            # 准备行数据
            row = {
                'timestamp': event.timestamp,
                'formatted_time': datetime.fromtimestamp(event.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                'event_id': event.event_id,
                'event_type': event.event_type,
                'level': event.level.value,
                'title': event.title,
                'description': event.description,
                'source': event.source
            }
            
            # 添加元数据字段
            for key, value in event.metadata.items():
                # 简化复杂值为字符串
                if isinstance(value, (dict, list)):
                    row[f'metadata_{key}'] = json.dumps(value, ensure_ascii=False)
                else:
                    row[f'metadata_{key}'] = str(value)
            
            # 写入CSV
            file_exists = filepath.exists()
            
            with open(filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(row)
            
            logger.debug(f"事件已保存到CSV文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存事件到CSV失败: {e}")
    
    def _output_event_to_telegram(self, event: RiskEvent) -> None:
        """输出事件到Telegram（占位符）"""
        # 实际实现需要Telegram Bot API
        logger.debug(f"Telegram通知: {event.title} - {event.description}")
        # 这里可以集成实际的Telegram发送逻辑
    
    def _output_event_to_email(self, event: RiskEvent) -> None:
        """输出事件到电子邮件（占位符）"""
        # 实际实现需要SMTP配置
        logger.debug(f"邮件通知: {event.title} - {event.description}")
        # 这里可以集成实际的邮件发送逻辑
    
    def _output_report_to_console(self, report: RiskReport) -> None:
        """输出报告到控制台"""
        print("\n" + "="*80)
        print(f"风险报告: {report.report_type}")
        print(f"报告ID: {report.report_id}")
        print(f"报告期间: {datetime.fromtimestamp(report.period_start/1000)} 至 {datetime.fromtimestamp(report.period_end/1000)}")
        print(f"生成时间: {datetime.fromtimestamp(report.generated_at/1000)}")
        print("="*80)
        
        # 摘要
        print("\n📊 报告摘要:")
        for key, value in report.summary.items():
            if isinstance(value, float):
                if 'rate' in key.lower() or 'ratio' in key.lower() or 'percent' in key.lower():
                    print(f"  {key}: {value:.2%}")
                else:
                    print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        
        # 关键指标
        print("\n📈 关键风险指标:")
        for metric in report.metrics[:10]:  # 显示前10个关键指标
            status_icon = {
                'normal': '✅',
                'warning': '⚠️',
                'error': '❌',
                'critical': '🔥'
            }.get(metric.status, '❓')
            
            print(f"  {status_icon} {metric.name}: {metric.value:.4f} {metric.unit} ({metric.status}, 趋势: {metric.trend})")
        
        # 关键事件
        if report.events:
            print("\n⚠️ 关键风险事件:")
            critical_events = [e for e in report.events if e.level in [ReportLevel.CRITICAL, ReportLevel.ERROR]]
            for event in critical_events[:5]:  # 显示前5个关键事件
                print(f"  • [{event.level.value}] {event.title}")
        
        # 建议
        if report.recommendations:
            print("\n💡 风险建议:")
            for i, rec in enumerate(report.recommendations[:5], 1):  # 显示前5个建议
                print(f"  {i}. {rec}")
        
        print("="*80 + "\n")
    
    def _output_report_to_json(self, report: RiskReport) -> None:
        """输出报告到JSON文件"""
        try:
            # 准备报告数据
            report_data = {
                'report_id': report.report_id,
                'report_type': report.report_type,
                'period_start': report.period_start,
                'period_end': report.period_end,
                'period_start_formatted': datetime.fromtimestamp(report.period_start/1000).isoformat(),
                'period_end_formatted': datetime.fromtimestamp(report.period_end/1000).isoformat(),
                'summary': report.summary,
                'metrics': [
                    {
                        'name': m.name,
                        'value': m.value,
                        'unit': m.unit,
                        'threshold': m.threshold,
                        'status': m.status,
                        'trend': m.trend,
                        'timestamp': m.timestamp
                    }
                    for m in report.metrics
                ],
                'events': [
                    {
                        'event_id': e.event_id,
                        'event_type': e.event_type,
                        'level': e.level.value,
                        'title': e.title,
                        'description': e.description,
                        'source': e.source,
                        'metadata': e.metadata,
                        'timestamp': e.timestamp
                    }
                    for e in report.events
                ],
                'recommendations': report.recommendations,
                'generated_at': report.generated_at,
                'generated_at_formatted': datetime.fromtimestamp(report.generated_at/1000).isoformat()
            }
            
            # 生成文件名
            filename = f"risk_report_{report.report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = Path(self.output_path) / filename
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"风险报告已保存到JSON文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存报告到JSON失败: {e}")
    
    def _output_report_to_html(self, report: RiskReport) -> None:
        """输出报告到HTML文件（简化实现）"""
        try:
            # 生成HTML内容（简化版）
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>风险报告 - {report.report_type}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                    .metric {{ margin: 10px 0; padding: 10px; border-left: 4px solid #007bff; }}
                    .critical {{ border-left-color: #dc3545; }}
                    .warning {{ border-left-color: #ffc107; }}
                    .normal {{ border-left-color: #28a745; }}
                    .event {{ margin: 10px 0; padding: 10px; background-color: #f8f9fa; border-radius: 3px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>风险报告: {report.report_type}</h1>
                    <p>报告ID: {report.report_id}</p>
                    <p>报告期间: {datetime.fromtimestamp(report.period_start/1000)} 至 {datetime.fromtimestamp(report.period_end/1000)}</p>
                    <p>生成时间: {datetime.fromtimestamp(report.generated_at/1000)}</p>
                </div>
                
                <h2>报告摘要</h2>
                <ul>
            """
            
            for key, value in report.summary.items():
                html_content += f"<li><strong>{key}:</strong> {value}</li>\n"
            
            html_content += """
                </ul>
                
                <h2>风险指标</h2>
            """
            
            for metric in report.metrics:
                status_class = metric.status
                html_content += f"""
                <div class="metric {status_class}">
                    <h3>{metric.name}</h3>
                    <p>值: {metric.value} {metric.unit} | 状态: {metric.status} | 趋势: {metric.trend}</p>
                </div>
                """
            
            if report.events:
                html_content += "<h2>风险事件</h2>\n"
                for event in report.events:
                    html_content += f"""
                    <div class="event">
                        <h3>[{event.level.value}] {event.title}</h3>
                        <p>{event.description}</p>
                        <p><small>来源: {event.source} | 时间: {datetime.fromtimestamp(event.timestamp/1000)}</small></p>
                    </div>
                    """
            
            if report.recommendations:
                html_content += "<h2>风险建议</h2>\n<ul>\n"
                for rec in report.recommendations:
                    html_content += f"<li>{rec}</li>\n"
                html_content += "</ul>\n"
            
            html_content += """
            </body>
            </html>
            """
            
            # 生成文件名
            filename = f"risk_report_{report.report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            filepath = Path(self.output_path) / filename
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"风险报告已保存到HTML文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存报告到HTML失败: {e}")
    
    def _output_report_to_markdown(self, report: RiskReport) -> None:
        """输出报告到Markdown文件"""
        try:
            # 生成Markdown内容
            md_content = f"""# 风险报告: {report.report_type}

## 报告信息
- **报告ID**: {report.report_id}
- **报告期间**: {datetime.fromtimestamp(report.period_start/1000)} 至 {datetime.fromtimestamp(report.period_end/1000)}
- **生成时间**: {datetime.fromtimestamp(report.generated_at/1000)}

## 报告摘要

"""
            
            for key, value in report.summary.items():
                if isinstance(value, float):
                    if 'rate' in key.lower() or 'ratio' in key.lower() or 'percent' in key.lower():
                        md_content += f"- **{key}**: {value:.2%}\n"
                    else:
                        md_content += f"- **{key}**: {value:.2f}\n"
                else:
                    md_content += f"- **{key}**: {value}\n"
            
            md_content += "\n## 风险指标\n\n"
            md_content += "| 指标名称 | 值 | 单位 | 状态 | 趋势 |\n"
            md_content += "|----------|-----|------|------|------|\n"
            
            for metric in report.metrics:
                status_icon = {
                    'normal': '✅',
                    'warning': '⚠️',
                    'error': '❌',
                    'critical': '🔥'
                }.get(metric.status, '❓')
                
                md_content += f"| {metric.name} | {metric.value:.4f} | {metric.unit} | {status_icon} {metric.status} | {metric.trend} |\n"
            
            if report.events:
                md_content += "\n## 风险事件\n\n"
                for event in report.events:
                    level_icon = {
                        ReportLevel.CRITICAL: '🔥',
                        ReportLevel.ERROR: '❌',
                        ReportLevel.WARNING: '⚠️',
                        ReportLevel.INFO: 'ℹ️',
                        ReportLevel.DEBUG: '🔍'
                    }.get(event.level, '•')
                    
                    md_content += f"### {level_icon} {event.title}\n\n"
                    md_content += f"{event.description}\n\n"
                    md_content += f"*来源: {event.source}*  \n"
                    md_content += f"*时间: {datetime.fromtimestamp(event.timestamp/1000)}*\n\n"
            
            if report.recommendations:
                md_content += "## 风险建议\n\n"
                for i, rec in enumerate(report.recommendations, 1):
                    md_content += f"{i}. {rec}\n"
            
            # 生成文件名
            filename = f"risk_report_{report.report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = Path(self.output_path) / filename
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            logger.info(f"风险报告已保存到Markdown文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存报告到Markdown失败: {e}")
    
    def trigger_alert(self, level: ReportLevel, title: str, description: str, 
                     source: str = "risk_reporter", metadata: Dict[str, Any] = None) -> RiskEvent:
        """
        触发风险预警
        
        Args:
            level: 预警级别
            title: 预警标题
            description: 预警描述
            source: 预警来源
            metadata: 额外元数据
            
        Returns:
            创建的风险事件
        """
        event_id = f"alert_{int(time.time() * 1000)}_{level.value}"
        
        event = RiskEvent(
            event_id=event_id,
            event_type="alert",
            level=level,
            title=title,
            description=description,
            source=source,
            metadata=metadata or {},
            timestamp=int(time.time() * 1000)
        )
        
        self.add_event(event)
        return event
    
    async def generate_realtime_report(self, account_monitor: AccountMonitor,
                                      rule_engine: RiskRuleEngine,
                                      circuit_breaker: CircuitBreaker) -> RiskReport:
        """
        生成实时风险报告
        
        Args:
            account_monitor: 账户监控器
            rule_engine: 规则引擎
            circuit_breaker: 熔断器
            
        Returns:
            实时风险报告
        """
        try:
            # 获取账户信息
            account_balance = await account_monitor.fetch_account_balance()
            risk_metrics = await account_monitor.calculate_risk_metrics()
            liquidation_risk = await account_monitor.check_liquidation_risk()
            
            # 获取规则评估结果（简化，使用模拟交易上下文）
            trade_context = None  # 实际使用中应从交易引擎获取
            account_context = None  # 实际使用中应从账户监控器构建
            
            # 获取熔断器状态
            breaker_status = circuit_breaker.get_status()
            
            # 生成报告ID
            report_id = f"realtime_{int(time.time() * 1000)}"
            
            # 构建风险指标
            metrics = [
                RiskMetric(
                    name="总余额",
                    value=account_balance.total_balance,
                    unit="USDT",
                    threshold=0.0,
                    status="normal",
                    trend="stable"
                ),
                RiskMetric(
                    name="可用余额",
                    value=account_balance.available_balance,
                    unit="USDT",
                    threshold=account_balance.total_balance * 0.1,  # 至少10%
                    status="warning" if account_balance.available_balance < account_balance.total_balance * 0.1 else "normal",
                    trend="stable"
                ),
                RiskMetric(
                    name="保证金率",
                    value=account_balance.margin_ratio,
                    unit="ratio",
                    threshold=0.5,  # 安全阈值50%
                    status="critical" if account_balance.margin_ratio > 0.8 else 
                           "warning" if account_balance.margin_ratio > 0.5 else "normal",
                    trend="stable"
                ),
                RiskMetric(
                    name="杠杆倍数",
                    value=account_balance.leverage,
                    unit="x",
                    threshold=10.0,  # 最大10倍
                    status="warning" if account_balance.leverage > 10.0 else "normal",
                    trend="stable"
                ),
                RiskMetric(
                    name="未实现盈亏",
                    value=account_balance.unrealized_pnl,
                    unit="USDT",
                    threshold=account_balance.total_balance * -0.05,  # 最大亏损5%
                    status="warning" if account_balance.unrealized_pnl < account_balance.total_balance * -0.05 else "normal",
                    trend="stable"
                )
            ]
            
            # 添加熔断器指标
            metrics.append(RiskMetric(
                name="熔断器状态",
                value=0 if breaker_status['state'] == 'normal' else 
                      1 if breaker_status['state'] == 'warning' else
                      2 if breaker_status['state'] == 'tripped' else 3,
                unit="level",
                threshold=1,  # 警告级别
                status="warning" if breaker_status['state'] != 'normal' else "normal",
                trend="stable"
            ))
            
            # 构建报告摘要
            summary = {
                '总余额_USDT': account_balance.total_balance,
                '可用余额_USDT': account_balance.available_balance,
                '仓位占比': risk_metrics.get('position_ratio', 0.0),
                '盈亏占比': risk_metrics.get('pnl_ratio', 0.0),
                '熔断器状态': breaker_status['state'],
                '连续亏损次数': breaker_status['consecutive_losses'],
                '单日盈亏_USDT': breaker_status['daily_pnl'],
                '活跃熔断器数量': len(breaker_status['active_breakers']),
                '强平风险': "有" if liquidation_risk['has_risk'] else "无"
            }
            
            # 构建风险事件
            events = []
            if liquidation_risk['has_risk']:
                events.append(RiskEvent(
                    event_id=f"liquidation_risk_{int(time.time() * 1000)}",
                    event_type="liquidation_risk",
                    level=ReportLevel.CRITICAL,
                    title="强平风险预警",
                    description=f"检测到 {len(liquidation_risk['high_risk_positions'])} 个高风险持仓",
                    source="account_monitor",
                    metadata=liquidation_risk
                ))
            
            if breaker_status['state'] != 'normal':
                events.append(RiskEvent(
                    event_id=f"breaker_status_{int(time.time() * 1000)}",
                    event_type="breaker_status",
                    level=ReportLevel.WARNING if breaker_status['state'] == 'warning' else ReportLevel.ERROR,
                    title=f"熔断器{breaker_status['state']}",
                    description=f"熔断器状态: {breaker_status['state']}, 严重度: {breaker_status['severity']}",
                    source="circuit_breaker",
                    metadata=breaker_status
                ))
            
            # 构建风险建议
            recommendations = []
            
            if account_balance.available_balance < account_balance.total_balance * 0.1:
                recommendations.append("可用余额过低，建议充值或减少持仓")
            
            if account_balance.margin_ratio > 0.5:
                recommendations.append("保证金率过高，建议追加保证金或减仓")
            
            if liquidation_risk['has_risk']:
                recommendations.append("检测到强平风险，建议立即减仓或追加保证金")
            
            if breaker_status['state'] != 'normal':
                recommendations.append(f"熔断器处于{breaker_status['state']}状态，请注意风险控制")
            
            if not recommendations:
                recommendations.append("风险状况良好，继续保持当前风控策略")
            
            # 创建报告
            report = RiskReport(
                report_id=report_id,
                report_type="realtime",
                period_start=int(time.time() * 1000) - 300000,  # 过去5分钟
                period_end=int(time.time() * 1000),
                summary=summary,
                metrics=metrics,
                events=events,
                recommendations=recommendations
            )
            
            self.add_report(report)
            return report
            
        except Exception as e:
            logger.error(f"生成实时风险报告失败: {e}")
            
            # 返回错误报告
            return RiskReport(
                report_id=f"error_{int(time.time() * 1000)}",
                report_type="realtime",
                period_start=int(time.time() * 1000) - 300000,
                period_end=int(time.time() * 1000),
                summary={'error': str(e)},
                metrics=[],
                events=[
                    RiskEvent(
                        event_id=f"report_error_{int(time.time() * 1000)}",
                        event_type="report_error",
                        level=ReportLevel.ERROR,
                        title="风险报告生成失败",
                        description=f"生成实时风险报告时发生错误: {str(e)}",
                        source="risk_reporter"
                    )
                ],
                recommendations=["检查风险报告系统配置", "查看错误日志获取详细信息"]
            )
    
    def get_recent_metrics(self, metric_name: str, limit: int = 100) -> List[RiskMetric]:
        """
        获取最近的风险指标
        
        Args:
            metric_name: 指标名称
            limit: 限制返回数量
            
        Returns:
            风险指标列表
        """
        if metric_name in self.metrics_history:
            return self.metrics_history[metric_name][-limit:] if self.metrics_history[metric_name] else []
        return []
    
    def get_recent_events(self, level: Optional[ReportLevel] = None, limit: int = 50) -> List[RiskEvent]:
        """
        获取最近的风险事件
        
        Args:
            level: 可选，过滤事件级别
            limit: 限制返回数量
            
        Returns:
            风险事件列表
        """
        filtered_events = self.events_history
        
        if level:
            filtered_events = [e for e in filtered_events if e.level == level]
        
        return filtered_events[-limit:] if filtered_events else []
    
    def get_recent_reports(self, report_type: Optional[str] = None, limit: int = 10) -> List[RiskReport]:
        """
        获取最近的风险报告
        
        Args:
            report_type: 可选，过滤报告类型
            limit: 限制返回数量
            
        Returns:
            风险报告列表
        """
        filtered_reports = self.reports_history
        
        if report_type:
            filtered_reports = [r for r in filtered_reports if r.report_type == report_type]
        
        return filtered_reports[-limit:] if filtered_reports else []


# 便捷函数
def create_risk_reporter(config_path: Optional[str] = None) -> RiskReporter:
    """
    创建风险报告器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        风险报告器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    return RiskReporter(config)


if __name__ == "__main__":
    """模块自测"""
    async def test_risk_reporter():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        reporter = RiskReporter(config)
        
        # 测试添加指标
        metric = RiskMetric(
            name="测试指标",
            value=75.5,
            unit="%",
            threshold=80.0,
            status="warning",
            trend="up"
        )
        reporter.add_metric(metric)
        
        # 测试添加事件
        event = RiskEvent(
            event_id="test_event_001",
            event_type="test",
            level=ReportLevel.WARNING,
            title="测试风险事件",
            description="这是一个测试风险事件",
            source="test_suite"
        )
        reporter.add_event(event)
        
        # 测试触发预警
        alert = reporter.trigger_alert(
            level=ReportLevel.ERROR,
            title="测试预警",
            description="这是一个测试风险预警",
            source="test_alert"
        )
        
        print(f"测试完成: 添加了1个指标，2个事件")
        print(f"最近事件: {len(reporter.get_recent_events())} 个")
        
        # 测试生成报告（需要其他模块，这里简化）
        from .account_monitor import AccountMonitor
        from .rule_engine import RiskRuleEngine
        from .circuit_breaker import CircuitBreaker
        
        account_monitor = AccountMonitor(config)
        rule_engine = RiskRuleEngine(config)
        circuit_breaker = CircuitBreaker(config)
        
        # 由于需要异步初始化，这里简化测试
        print("\n风险报告器测试完成。实际使用需要完整的环境初始化。")
    
    asyncio.run(test_risk_reporter())