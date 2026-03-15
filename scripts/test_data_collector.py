"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据采集层测试脚本
测试WebSocket连接和历史数据获取功能
"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.data_collector import DataCollector
from src.utils.config_loader import ConfigLoader


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/test_data_collector.log')
    ]
)
logger = logging.getLogger(__name__)


async def test_config_loader():
    """测试配置加载器"""
    logger.info("=== 测试配置加载器 ===")
    
    try:
        # 加载配置
        config = ConfigLoader.get_full_config("config/config.yaml")
        
        # 验证配置
        required_keys = ['binance', 'data', 'signals', 'risk', 'execution', 'logging']
        for key in required_keys:
            if key in config:
                logger.info(f"✓ 配置节 '{key}' 存在")
            else:
                logger.error(f"✗ 配置节 '{key}' 缺失")
                return False
        
        # 检查数据配置
        data_config = config['data']
        symbols = data_config.get('symbols', [])
        intervals = data_config.get('intervals', [])
        
        logger.info(f"交易对配置: {symbols}")
        logger.info(f"K线间隔配置: {intervals}")
        
        if not symbols:
            logger.error("✗ 未配置交易对")
            return False
        
        if not intervals:
            logger.error("✗ 未配置K线间隔")
            return False
        
        logger.info("✓ 配置加载器测试通过")
        return True
        
    except Exception as e:
        logger.error(f"配置加载器测试失败: {e}", exc_info=True)
        return False


async def test_historical_data():
    """测试历史数据获取"""
    logger.info("=== 测试历史数据获取 ===")
    
    try:
        # 加载配置
        config = ConfigLoader.get_full_config("config/config.yaml")
        
        # 创建历史数据获取器
        from src.data.historical_data import HistoricalDataFetcher
        fetcher = HistoricalDataFetcher(config)
        
        # 初始化
        if not await fetcher.initialize():
            logger.error("✗ 历史数据获取器初始化失败")
            return False
        
        logger.info("✓ 历史数据获取器初始化成功")
        
        # 测试获取少量数据
        test_symbol = config['data']['symbols'][0]  # 第一个交易对
        test_interval = config['data']['intervals'][0]  # 第一个间隔
        
        logger.info(f"测试获取 {test_symbol} {test_interval} 历史数据...")
        
        # 获取最近1小时数据（减少测试时间）
        data = await fetcher.fetch_klines(
            symbol=test_symbol,
            interval=test_interval,
            days=1,  # 只获取1天数据加速测试
            limit=100  # 限制数量
        )
        
        if not data:
            logger.error(f"✗ 未获取到 {test_symbol} 历史数据")
            return False
        
        logger.info(f"✓ 获取到 {test_symbol} 历史数据: {len(data)} 条记录")
        
        # 检查数据格式
        sample = data[0]
        required_fields = ['symbol', 'interval', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        for field in required_fields:
            if field not in sample:
                logger.error(f"✗ 数据缺少字段: {field}")
                return False
        
        logger.info(f"✓ 数据格式正确，示例: {sample['timestamp']} - 收盘价: {sample['close']}")
        
        # 测试缓存功能
        cached_data = fetcher.get_data(test_symbol, test_interval)
        if cached_data and len(cached_data) == len(data):
            logger.info("✓ 缓存功能正常")
        else:
            logger.warning("缓存功能异常")
        
        # 关闭资源
        await fetcher.close()
        
        logger.info("✓ 历史数据获取测试通过")
        return True
        
    except Exception as e:
        logger.error(f"历史数据获取测试失败: {e}", exc_info=True)
        return False


async def test_websocket_connection():
    """测试WebSocket连接（简短测试）"""
    logger.info("=== 测试WebSocket连接 ===")
    
    try:
        # 加载配置
        config = ConfigLoader.get_full_config("config/config.yaml")
        
        # 创建WebSocket客户端
        from src.data.websocket_client import BinanceWebSocketClient
        ws_client = BinanceWebSocketClient(config)
        
        # 初始化
        await ws_client.initialize()
        
        logger.info("✓ WebSocket客户端初始化成功")
        
        # 连接测试（短暂连接）
        logger.info("测试WebSocket连接...")
        
        connect_task = asyncio.create_task(ws_client.connect())
        
        # 等待连接完成或超时
        try:
            await asyncio.wait_for(connect_task, timeout=10.0)
            
            if ws_client.is_connected:
                logger.info("✓ WebSocket连接成功")
                
                # 短暂测试后立即关闭
                await ws_client.close()
                logger.info("✓ WebSocket连接测试通过")
                return True
            else:
                logger.error("✗ WebSocket连接失败")
                return False
                
        except asyncio.TimeoutError:
            logger.error("✗ WebSocket连接超时")
            await ws_client.close()
            return False
        
    except Exception as e:
        logger.error(f"WebSocket连接测试失败: {e}", exc_info=True)
        return False


async def test_data_collector_integration():
    """测试数据采集器集成"""
    logger.info("=== 测试数据采集器集成 ===")
    
    collector = None
    
    try:
        # 创建数据采集器
        collector = DataCollector("config/config.yaml")
        
        # 初始化
        if not await collector.initialize():
            logger.error("✗ 数据采集器初始化失败")
            return False
        
        logger.info("✓ 数据采集器初始化成功")
        
        # 获取健康状态
        health_status = collector.get_health_status()
        logger.info(f"健康状态: {health_status['collector_status']}")
        
        # 测试启动（短暂运行）
        logger.info("测试数据采集器启动...")
        
        if not await collector.start():
            logger.error("✗ 数据采集器启动失败")
            return False
        
        logger.info("✓ 数据采集器启动成功")
        
        # 等待几秒让数据开始流动
        logger.info("等待数据采集...")
        await asyncio.sleep(5)
        
        # 检查状态
        health_status = collector.get_health_status()
        logger.info(f"运行状态: {health_status}")
        
        # 测试数据获取接口
        test_symbol = collector.config['data']['symbols'][0]
        
        # 获取历史数据
        historical_data = collector.get_historical_data(test_symbol, '1m')
        if historical_data:
            logger.info(f"✓ 获取到历史数据: {len(historical_data)} 条记录")
        else:
            logger.warning("未获取到历史数据（可能需要首次获取）")
        
        # 停止采集器
        await collector.stop()
        
        logger.info("✓ 数据采集器集成测试通过")
        return True
        
    except Exception as e:
        logger.error(f"数据采集器集成测试失败: {e}", exc_info=True)
        return False
    finally:
        if collector and collector.is_running:
            await collector.stop()


async def run_all_tests():
    """运行所有测试"""
    logger.info("=" * 50)
    logger.info("开始数据采集层测试")
    logger.info("=" * 50)
    
    test_results = []
    
    # 运行测试
    tests = [
        ("配置加载器", test_config_loader),
        ("历史数据获取", test_historical_data),
        ("WebSocket连接", test_websocket_connection),
        ("数据采集器集成", test_data_collector_integration)
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
    logger.info("\n" + "=" * 50)
    logger.info("测试结果汇总")
    logger.info("=" * 50)
    
    passed_tests = [name for name, result in test_results if result]
    failed_tests = [name for name, result in test_results if not result]
    
    logger.info(f"通过测试: {len(passed_tests)}/{len(test_results)}")
    for name in passed_tests:
        logger.info(f"  ✓ {name}")
    
    if failed_tests:
        logger.info(f"失败测试: {len(failed_tests)}/{len(test_results)}")
        for name in failed_tests:
            logger.info(f"  ✗ {name}")
    
    # 总体结果
    all_passed = len(failed_tests) == 0
    
    if all_passed:
        logger.info("\n🎉 所有测试通过！数据采集层功能正常。")
    else:
        logger.warning("\n⚠️  部分测试失败，请检查日志。")
    
    return all_passed


if __name__ == "__main__":
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 运行测试
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试运行异常: {e}", exc_info=True)
        sys.exit(1)