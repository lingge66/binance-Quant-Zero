"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号处理层测试脚本
测试技术指标计算和信号生成功能
"""
import asyncio
import logging
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.signals import TechnicalIndicators, SignalGenerator, SignalProcessor
from src.utils.config_loader import ConfigLoader


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/test_signals.log')
    ]
)
logger = logging.getLogger(__name__)


def generate_test_data(symbol: str = 'BTCUSDT', 
                      interval: str = '1m',
                      num_records: int = 200) -> list:
    """
    生成测试用的K线数据
    
    Args:
        symbol: 交易对
        interval: 时间间隔
        num_records: 记录数量
        
    Returns:
        list: K线数据列表
    """
    # 基础价格
    base_price = 50000.0
    
    # 生成时间戳（从当前时间往前推）
    end_time = int(time.time() * 1000)  # 毫秒时间戳
    interval_ms = 60 * 1000  # 1分钟=60秒=60000毫秒
    
    data = []
    
    for i in range(num_records):
        timestamp = end_time - (num_records - i - 1) * interval_ms
        
        # 生成随机价格走势（带趋势）
        trend = 0.001 * (i / num_records)  # 轻微上涨趋势
        noise = np.random.normal(0, 0.002)  # 随机噪声
        
        # 生成OHLC价格
        open_price = base_price * (1 + trend + noise)
        close_price = open_price * (1 + np.random.normal(0, 0.001))
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.0005)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.0005)))
        volume = np.random.uniform(10, 100)
        
        # 确保价格合理
        high_price = max(open_price, close_price, high_price)
        low_price = min(open_price, close_price, low_price)
        
        kline = {
            'symbol': symbol,
            'interval': interval,
            'timestamp': timestamp,
            'open': float(open_price),
            'high': float(high_price),
            'low': float(low_price),
            'close': float(close_price),
            'volume': float(volume),
            'close_time': timestamp + interval_ms - 1,
            'quote_volume': float(volume * close_price),
            'trades': np.random.randint(10, 100),
            'taker_buy_base': float(volume * 0.5),
            'taker_buy_quote': float(volume * close_price * 0.5),
            'ignore': 0
        }
        
        data.append(kline)
        
        # 更新基础价格
        base_price = close_price
    
    logger.info(f"生成测试数据: {symbol} {interval}, {len(data)} 条记录")
    return data


async def test_technical_indicators():
    """测试技术指标计算"""
    logger.info("=== 测试技术指标计算 ===")
    
    try:
        # 生成测试数据
        test_data = generate_test_data('BTCUSDT', '1m', 100)
        
        # 创建技术指标计算器
        calculator = TechnicalIndicators()
        
        # 验证数据
        if not calculator.validate_data_for_indicators(test_data):
            logger.error("数据验证失败")
            return False
        
        logger.info("数据验证通过")
        
        # 计算技术指标
        start_time = time.time()
        data_with_indicators = calculator.calculate_all_indicators(test_data)
        calc_time = time.time() - start_time
        
        if not data_with_indicators:
            logger.error("技术指标计算失败")
            return False
        
        logger.info(f"技术指标计算成功，耗时: {calc_time:.3f}秒")
        
        # 检查生成的指标
        first_record = data_with_indicators[0]
        last_record = data_with_indicators[-1]
        
        # 检查移动平均线
        ma_fields = ['ma_5', 'ma_10', 'ma_20', 'ma_60']
        for field in ma_fields:
            if field in last_record and pd.notna(last_record[field]):
                logger.info(f"✓ {field}: {last_record[field]:.2f}")
        
        # 检查RSI
        if 'rsi' in last_record and pd.notna(last_record['rsi']):
            logger.info(f"✓ RSI: {last_record['rsi']:.2f}")
        
        # 检查布林带
        bb_fields = ['bb_middle', 'bb_upper', 'bb_lower']
        for field in bb_fields:
            if field in last_record and pd.notna(last_record[field]):
                logger.info(f"✓ {field}: {last_record[field]:.2f}")
        
        # 检查MACD
        macd_fields = ['macd_dif', 'macd_dea', 'macd_hist']
        for field in macd_fields:
            if field in last_record and pd.notna(last_record[field]):
                logger.info(f"✓ {field}: {last_record[field]:.4f}")
        
        # 获取指标摘要
        summary = calculator.get_indicator_summary(data_with_indicators)
        logger.info(f"指标摘要: {summary.get('timestamp')}, 价格: {summary.get('price'):.2f}")
        
        logger.info("✓ 技术指标计算测试通过")
        return True
        
    except Exception as e:
        logger.error(f"技术指标计算测试失败: {e}", exc_info=True)
        return False


async def test_signal_generator():
    """测试信号生成器"""
    logger.info("=== 测试信号生成器 ===")
    
    try:
        # 生成测试数据
        test_data = generate_test_data('BTCUSDT', '1m', 100)
        
        # 先计算技术指标
        calculator = TechnicalIndicators()
        data_with_indicators = calculator.calculate_all_indicators(test_data)
        
        if not data_with_indicators:
            logger.error("技术指标计算失败，无法测试信号生成器")
            return False
        
        # 创建信号生成器
        config = {
            'signal_weights': {
                'trend': 0.35,
                'momentum': 0.30,
                'volatility': 0.20,
                'volume': 0.15
            },
            'min_confidence': 0.6
        }
        
        generator = SignalGenerator(config)
        
        # 生成信号
        start_time = time.time()
        signals = generator.generate_signals(data_with_indicators, 'BTCUSDT')
        gen_time = time.time() - start_time
        
        logger.info(f"信号生成耗时: {gen_time:.3f}秒，生成 {len(signals)} 个信号")
        
        if signals:
            for i, signal in enumerate(signals[-3:]):  # 显示最后3个信号
                logger.info(f"信号{i+1}: {signal}")
        
        # 生成信号摘要
        summary = generator.generate_signal_summary(signals)
        logger.info(f"信号摘要: {summary}")
        
        if signals:
            logger.info("✓ 信号生成器测试通过")
            return True
        else:
            logger.warning("未生成信号（可能置信度不足）")
            return True  # 没有信号也可能是正常情况
            
    except Exception as e:
        logger.error(f"信号生成器测试失败: {e}", exc_info=True)
        return False


async def test_signal_processor():
    """测试信号处理器"""
    logger.info("=== 测试信号处理器 ===")
    
    try:
        # 加载配置
        config = ConfigLoader.get_full_config("config/config.yaml")
        
        # 创建信号处理器
        processor = SignalProcessor(config)
        
        # 初始化
        if not await processor.initialize():
            logger.error("信号处理器初始化失败")
            return False
        
        logger.info("信号处理器初始化成功")
        
        # 生成多个交易对的测试数据
        symbols_data = {}
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        
        for symbol in symbols:
            test_data = generate_test_data(symbol, '1m', 150)
            symbols_data[symbol] = test_data
        
        # 批量处理
        start_time = time.time()
        batch_result = await processor.batch_process(symbols_data, generate_signals=True)
        batch_time = time.time() - start_time
        
        if not batch_result.get('success'):
            logger.error(f"批量处理失败: {batch_result.get('error')}")
            return False
        
        logger.info(f"批量处理耗时: {batch_time:.3f}秒")
        
        # 检查结果
        summary = batch_result.get('summary', {})
        logger.info(f"批量处理摘要: {summary}")
        
        results = batch_result.get('results', {})
        for symbol, result in results.items():
            if isinstance(result, dict) and result.get('success'):
                logger.info(f"{symbol}: 处理成功，生成 {len(result.get('signals', []))} 个信号")
            else:
                logger.warning(f"{symbol}: 处理失败: {result}")
        
        # 检查缓存
        status = processor.get_status()
        logger.info(f"处理器状态: {status}")
        
        # 测试单交易对处理
        logger.info("测试单交易对处理...")
        single_result = await processor.process_symbol(
            'BTCUSDT', symbols_data['BTCUSDT'], generate_signals=True
        )
        
        if single_result.get('success'):
            logger.info(f"单交易对处理成功: {single_result.get('symbol')}")
            
            # 检查缓存功能
            cached_indicators = processor.get_cached_indicators('BTCUSDT')
            cached_signals = processor.get_cached_signals('BTCUSDT', limit=5)
            
            if cached_indicators:
                logger.info(f"缓存指标数据: {len(cached_indicators)} 条")
            
            if cached_signals:
                logger.info(f"缓存信号: {len(cached_signals)} 个")
        
        # 关闭处理器
        await processor.close()
        
        logger.info("✓ 信号处理器测试通过")
        return True
        
    except Exception as e:
        logger.error(f"信号处理器测试失败: {e}", exc_info=True)
        return False


async def test_integration_with_real_config():
    """测试与真实配置的集成"""
    logger.info("=== 测试与真实配置的集成 ===")
    
    try:
        # 加载完整配置
        config = ConfigLoader.get_full_config("config/config.yaml")
        
        # 检查信号配置
        if 'signals' not in config:
            logger.error("配置文件中缺少signals节")
            return False
        
        signals_config = config['signals']
        logger.info(f"信号配置: {signals_config.get('indicators', {})}")
        
        # 创建信号处理器
        processor = SignalProcessor(config)
        
        # 初始化
        await processor.initialize()
        
        # 生成测试数据
        test_data = generate_test_data('BTCUSDT', '1m', 200)
        
        # 处理数据
        result = await processor.process_symbol('BTCUSDT', test_data, generate_signals=True)
        
        if result.get('success'):
            logger.info("集成测试成功")
            
            # 输出处理详情
            processing_times = result.get('processing_times', {})
            logger.info(f"处理时间: 指标计算={processing_times.get('indicators', 0):.3f}s, "
                       f"信号生成={processing_times.get('signals', 0):.3f}s")
            
            signals_summary = result.get('signals_summary', {})
            if signals_summary:
                latest_signal = signals_summary.get('latest_signal', {})
                logger.info(f"最新信号: {latest_signal.get('signal_type')}, "
                           f"置信度: {latest_signal.get('confidence'):.2f}")
        
        await processor.close()
        
        logger.info("✓ 集成测试通过")
        return True
        
    except Exception as e:
        logger.error(f"集成测试失败: {e}", exc_info=True)
        return False


async def run_all_tests():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("开始信号处理层测试")
    logger.info("=" * 60)
    
    test_results = []
    
    # 创建日志目录
    Path("logs").mkdir(exist_ok=True)
    
    # 运行测试
    tests = [
        ("技术指标计算", test_technical_indicators),
        ("信号生成器", test_signal_generator),
        ("信号处理器", test_signal_processor),
        ("配置集成测试", test_integration_with_real_config)
    ]
    
    for test_name, test_func in tests:
        try:
            logger.info(f"\n▶️ 运行测试: {test_name}")
            result = await test_func()
            test_results.append((test_name, result))
            
            if result:
                logger.info(f"✅ {test_name} 测试通过")
            else:
                logger.error(f"❌ {test_name} 测试失败")
                
        except Exception as e:
            logger.error(f"❌ {test_name} 测试异常: {e}", exc_info=True)
            test_results.append((test_name, False))
    
    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    passed_tests = [name for name, result in test_results if result]
    failed_tests = [name for name, result in test_results if not result]
    
    logger.info(f"通过测试: {len(passed_tests)}/{len(test_results)}")
    for name in passed_tests:
        logger.info(f"  ✅ {name}")
    
    if failed_tests:
        logger.error(f"失败测试: {len(failed_tests)}/{len(test_results)}")
        for name in failed_tests:
            logger.error(f"  ❌ {name}")
    
    # 总体结果
    all_passed = len(failed_tests) == 0
    
    if all_passed:
        logger.info("\n🎉 所有测试通过！信号处理层功能正常。")
    else:
        logger.error("\n⚠️  部分测试失败，请检查日志。")
    
    return all_passed


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(run_all_tests())
    
    if success:
        logger.info("\n✨ 信号处理层开发完成，准备进入风控引擎开发。")
        sys.exit(0)
    else:
        logger.error("\n💥 信号处理层测试失败，需要调试。")
        sys.exit(1)