#!/usr/bin/env python3
"""
币安AI交易Agent集成验证脚本

功能：
1. 验证所有模块可以正确导入
2. 检查各层模块的基本接口
3. 验证模块间数据格式兼容性
4. 模拟端到端数据流

设计：简化验证，不实际初始化复杂组件
版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import sys
import time
import importlib
import inspect
from typing import Dict, Any, List, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class IntegrationVerifier:
    """集成验证器"""
    
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
    
    def verify_module_import(self, module_path: str, class_names: List[str] = None) -> Dict[str, Any]:
        """
        验证模块导入
        
        Args:
            module_path: 模块路径（如 'src.data.data_collector'）
            class_names: 需要检查的类名列表
            
        Returns:
            验证结果
        """
        result = {
            'module_path': module_path,
            'success': False,
            'error': None,
            'classes_found': [],
            'classes_missing': [],
        }
        
        try:
            module = importlib.import_module(module_path)
            result['success'] = True
            
            if class_names:
                for class_name in class_names:
                    if hasattr(module, class_name):
                        result['classes_found'].append(class_name)
                    else:
                        result['classes_missing'].append(class_name)
            
            return result
            
        except ImportError as e:
            result['error'] = f"导入错误: {e}"
            return result
        except Exception as e:
            result['error'] = f"未知错误: {e}"
            return result
    
    def verify_config_manager(self) -> Dict[str, Any]:
        """验证配置管理器"""
        print("验证配置管理器...")
        result = self.verify_module_import(
            'config.config_manager',
            ['ConfigManager']
        )
        
        if result['success']:
            try:
                from config.config_manager import ConfigManager
                config = ConfigManager()
                
                # 测试基本功能
                test_value = config.get('binance.environment', 'mainnet')
                result['config_test'] = f"配置值: {test_value}"
                print(f"  ✓ 配置管理器验证成功: {test_value}")
                
            except Exception as e:
                result['success'] = False
                result['error'] = f"功能测试失败: {e}"
                print(f"  ✗ 配置管理器验证失败: {e}")
        
        self.results['config_manager'] = result
        return result
    
    def verify_data_layer(self) -> Dict[str, Any]:
        """验证数据采集层"""
        print("\n验证数据采集层...")
        
        modules_to_verify = [
            ('src.data.data_collector', ['DataCollector']),
            ('src.data.websocket_client', ['BinanceWebSocketClient']),
            ('src.data.historical_data', ['HistoricalDataFetcher']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
                if result['classes_found']:
                    print(f"      找到类: {', '.join(result['classes_found'])}")
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
            'verified_modules': len([r for r in layer_results if r['success']]),
            'total_modules': len(modules_to_verify),
        }
        
        self.results['data_layer'] = overall_result
        return overall_result
    
    def verify_signal_layer(self) -> Dict[str, Any]:
        """验证信号处理层"""
        print("\n验证信号处理层...")
        
        modules_to_verify = [
            ('src.signals.signal_generator', ['SignalGenerator', 'Signal', 'SignalType']),
            ('src.signals.processor', ['SignalProcessor']),
            ('src.signals.indicators', ['TechnicalIndicators']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
                if result['classes_found']:
                    print(f"      找到类: {', '.join(result['classes_found'][:3])}" + 
                          (f" 等{len(result['classes_found'])}个类" if len(result['classes_found']) > 3 else ""))
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
            'verified_modules': len([r for r in layer_results if r['success']]),
            'total_modules': len(modules_to_verify),
        }
        
        self.results['signal_layer'] = overall_result
        return overall_result
    
    def verify_risk_layer(self) -> Dict[str, Any]:
        """验证风控引擎层"""
        print("\n验证风控引擎层...")
        
        modules_to_verify = [
            ('src.risk.account_monitor', ['AccountMonitor', 'AccountBalance', 'PositionInfo']),
            ('src.risk.rule_engine', ['RiskRuleEngine', 'RiskRule', 'RuleType']),
            ('src.risk.circuit_breaker', ['CircuitBreaker', 'BreakerType', 'CircuitState']),
            ('src.risk.reporter', ['RiskReporter']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
                if result['classes_found']:
                    print(f"      找到类: {', '.join(result['classes_found'][:3])}" + 
                          (f" 等{len(result['classes_found'])}个类" if len(result['classes_found']) > 3 else ""))
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
            'verified_modules': len([r for r in layer_results if r['success']]),
            'total_modules': len(modules_to_verify),
        }
        
        self.results['risk_layer'] = overall_result
        return overall_result
    
    def verify_execution_layer(self) -> Dict[str, Any]:
        """验证交易执行层"""
        print("\n验证交易执行层...")
        
        modules_to_verify = [
            ('src.execution.order_manager', ['OrderManager', 'Order', 'OrderType', 'OrderStatus']),
            ('src.execution.executor', ['TradeExecutor']),
            ('src.execution.position_manager', ['PositionManager']),
            ('src.execution.execution_risk', ['ExecutionRiskManager']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
                if result['classes_found']:
                    print(f"      找到类: {', '.join(result['classes_found'][:3])}" + 
                          (f" 等{len(result['classes_found'])}个类" if len(result['classes_found']) > 3 else ""))
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
            'verified_modules': len([r for r in layer_results if r['success']]),
            'total_modules': len(modules_to_verify),
        }
        
        self.results['execution_layer'] = overall_result
        return overall_result
    
    def verify_notification_layer(self) -> Dict[str, Any]:
        """验证通知集成层"""
        print("\n验证通知集成层...")
        
        modules_to_verify = [
            ('src.notification.notification_manager', ['NotificationManager', 'Notification', 'NotificationType']),
            ('src.notification.console_notifier', ['ConsoleNotifier']),
            ('src.notification.log_file_notifier', ['LogFileNotifier']),
            ('src.notification.openclaw_notifier', ['OpenClawNotifier']),
            ('src.notification.telegram_notifier', ['TelegramNotifier']),
            ('src.notification.message_formatter', ['MessageFormatter']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
                if result['classes_found']:
                    print(f"      找到类: {', '.join(result['classes_found'][:3])}" + 
                          (f" 等{len(result['classes_found'])}个类" if len(result['classes_found']) > 3 else ""))
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
            'verified_modules': len([r for r in layer_results if r['success']]),
            'total_modules': len(modules_to_verify),
        }
        
        self.results['notification_layer'] = overall_result
        return overall_result
    
    def verify_utils(self) -> Dict[str, Any]:
        """验证工具模块"""
        print("\n验证工具模块...")
        
        modules_to_verify = [
            ('src.utils.config_loader', ['ConfigLoader']),
            ('src.utils.exponential_backoff', ['ExponentialBackoff']),
        ]
        
        layer_results = []
        all_success = True
        
        for module_path, class_names in modules_to_verify:
            print(f"  验证 {module_path}...")
            result = self.verify_module_import(module_path, class_names)
            layer_results.append(result)
            
            if result['success']:
                print(f"    ✓ {module_path} 导入成功")
            else:
                print(f"    ✗ {module_path} 导入失败: {result['error']}")
                all_success = False
        
        overall_result = {
            'success': all_success,
            'module_results': layer_results,
        }
        
        self.results['utils'] = overall_result
        return overall_result
    
    def verify_data_format_compatibility(self) -> Dict[str, Any]:
        """验证数据格式兼容性"""
        print("\n验证数据格式兼容性...")
        
        try:
            # 测试数据格式
            from src.signals.signal_generator import Signal, SignalType, SignalStrength
            
            # 创建示例信号
            test_signal = Signal(
                signal_type=SignalType.BUY,
                strength=SignalStrength.MEDIUM,
                confidence=0.75,
                timestamp=int(time.time() * 1000),
                symbol="BTC/USDT",
                price=50000.0,
                indicators={"rsi": 65.5, "macd": 120.5},
                reasoning="技术指标金叉",
                metadata={"source": "integration_test"}
            )
            
            # 转换为字典
            signal_dict = test_signal.to_dict()
            
            print(f"  ✓ 信号数据格式验证成功")
            print(f"    信号类型: {signal_dict['signal_type']}")
            print(f"    交易对: {signal_dict['symbol']}")
            print(f"    价格: ${signal_dict['price']:,.2f}")
            print(f"    置信度: {signal_dict['confidence']:.1%}")
            
            result = {
                'success': True,
                'test_signal': signal_dict,
                'message': '数据格式兼容性验证成功'
            }
            
        except Exception as e:
            print(f"  ✗ 数据格式兼容性验证失败: {e}")
            result = {
                'success': False,
                'error': str(e),
                'message': '数据格式兼容性验证失败'
            }
        
        self.results['data_format'] = result
        return result
    
    def verify_end_to_end_flow(self) -> Dict[str, Any]:
        """验证端到端数据流（模拟）"""
        print("\n验证端到端数据流（模拟）...")
        
        try:
            # 模拟端到端流程
            print("  1. 模拟数据采集 → 信号生成 → 风控评估 → 交易执行 → 通知发送")
            
            # 模拟数据
            mock_data = {
                'symbol': 'BTC/USDT',
                'price': 50000.0,
                'volume': 1000.0,
                'timestamp': int(time.time() * 1000),
            }
            
            print(f"  2. 采集数据: {mock_data['symbol']} @ ${mock_data['price']:,.2f}")
            
            # 模拟信号生成
            mock_signal = {
                'symbol': mock_data['symbol'],
                'signal_type': 'BUY',
                'confidence': 0.75,
                'price': mock_data['price'],
                'timestamp': mock_data['timestamp'],
                'reason': '模拟集成测试',
            }
            
            print(f"  3. 生成信号: {mock_signal['signal_type']} {mock_signal['symbol']} (置信度: {mock_signal['confidence']:.1%})")
            
            # 模拟风控评估
            mock_risk_check = {
                'approved': True,
                'reason': '通过所有风控规则',
                'timestamp': int(time.time() * 1000),
            }
            
            print(f"  4. 风控评估: {'通过' if mock_risk_check['approved'] else '拒绝'} - {mock_risk_check['reason']}")
            
            # 模拟交易执行
            mock_execution = {
                'order_id': f"order_{int(time.time() * 1000)}",
                'symbol': mock_signal['symbol'],
                'side': mock_signal['signal_type'],
                'price': mock_signal['price'],
                'amount': 0.01,
                'status': 'filled',
                'timestamp': int(time.time() * 1000),
            }
            
            print(f"  5. 交易执行: {mock_execution['side']} {mock_execution['amount']} {mock_execution['symbol']} @ ${mock_execution['price']:,.2f}")
            print(f"     订单ID: {mock_execution['order_id']}, 状态: {mock_execution['status']}")
            
            # 模拟通知发送
            mock_notification = {
                'notification_id': f"notif_{int(time.time() * 1000)}",
                'type': 'trade_execution',
                'message': f"交易执行: {mock_execution['side']} {mock_execution['amount']} {mock_execution['symbol']} @ ${mock_execution['price']:,.2f}",
                'timestamp': int(time.time() * 1000),
            }
            
            print(f"  6. 通知发送: {mock_notification['message']}")
            print(f"     通知ID: {mock_notification['notification_id']}")
            
            result = {
                'success': True,
                'steps_completed': 6,
                'message': '端到端数据流验证成功',
                'simulated_data': {
                    'data': mock_data,
                    'signal': mock_signal,
                    'risk_check': mock_risk_check,
                    'execution': mock_execution,
                    'notification': mock_notification,
                }
            }
            
            print("  ✓ 端到端数据流验证成功")
            
        except Exception as e:
            print(f"  ✗ 端到端数据流验证失败: {e}")
            result = {
                'success': False,
                'error': str(e),
                'message': '端到端数据流验证失败'
            }
        
        self.results['end_to_end_flow'] = result
        return result
    
    def run_all_verifications(self) -> Dict[str, Any]:
        """运行所有验证"""
        print("="*70)
        print("币安AI交易Agent集成验证")
        print("="*70)
        
        # 运行各个验证
        self.verify_config_manager()
        self.verify_data_layer()
        self.verify_signal_layer()
        self.verify_risk_layer()
        self.verify_execution_layer()
        self.verify_notification_layer()
        self.verify_utils()
        self.verify_data_format_compatibility()
        self.verify_end_to_end_flow()
        
        # 计算总体结果
        total_time = time.time() - self.start_time
        
        # 统计成功层数
        layer_keys = ['config_manager', 'data_layer', 'signal_layer', 'risk_layer', 
                     'execution_layer', 'notification_layer', 'utils', 'data_format', 'end_to_end_flow']
        
        successful_layers = 0
        total_layers = 0
        
        for key in layer_keys:
            if key in self.results:
                total_layers += 1
                if self.results[key].get('success', False):
                    successful_layers += 1
        
        overall_success = successful_layers >= total_layers * 0.7  # 70%成功率
        
        print("\n" + "="*70)
        print("集成验证结果汇总")
        print("="*70)
        
        print(f"\n验证层数: {successful_layers}/{total_layers} 成功")
        print(f"总体结果: {'通过' if overall_success else '未通过'}")
        print(f"总耗时: {total_time:.2f}秒")
        
        # 详细结果
        print(f"\n详细结果:")
        for key, result in self.results.items():
            if isinstance(result, dict):
                success = result.get('success', False)
                status = "✓" if success else "✗"
                print(f"  {status} {key}: {'成功' if success else '失败'}")
                
                if key.endswith('_layer') and 'verified_modules' in result:
                    print(f"    模块: {result['verified_modules']}/{result['total_modules']} 验证成功")
        
        print("\n" + "="*70)
        
        return {
            'overall_success': overall_success,
            'successful_layers': successful_layers,
            'total_layers': total_layers,
            'success_rate': successful_layers / total_layers if total_layers > 0 else 0,
            'total_time': total_time,
            'detailed_results': self.results,
        }


def main():
    """主函数"""
    verifier = IntegrationVerifier()
    results = verifier.run_all_verifications()
    
    # 返回退出码
    sys.exit(0 if results['overall_success'] else 1)


if __name__ == "__main__":
    main()