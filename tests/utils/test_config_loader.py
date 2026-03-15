"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
配置加载器单元测试
"""
import os
import sys
import unittest
from unittest.mock import mock_open, patch
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import ConfigLoader


class TestConfigLoader(unittest.TestCase):
    """配置加载器测试"""
    
    def test_load_config_success(self):
        """测试成功加载配置文件"""
        mock_yaml_content = """
        binance:
          environment: testnet
          api_key: test_key
          secret_key: test_secret
        
        data:
          symbols:
            - BTC/USDT
            - ETH/USDT
        """
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_yaml_content)):
                with patch('yaml.safe_load') as mock_load:
                    mock_load.return_value = {
                        'binance': {'environment': 'testnet'},
                        'data': {'symbols': ['BTC/USDT', 'ETH/USDT']}
                    }
                    
                    config = ConfigLoader.load_config('/fake/path/config.yaml')
                    
                    # 验证yaml.safe_load被调用
                    mock_load.assert_called_once()
                    # 验证返回的配置
                    self.assertIn('binance', config)
                    self.assertIn('data', config)
                    self.assertEqual(config['binance']['environment'], 'testnet')
    
    def test_load_config_file_not_found(self):
        """测试配置文件不存在"""
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = False
            
            with self.assertRaises(FileNotFoundError) as context:
                ConfigLoader.load_config('/fake/path/config.yaml')
            
            self.assertIn('配置文件不存在', str(context.exception))
    
    def test_load_env_config(self):
        """测试加载环境变量配置"""
        test_env_vars = {
            'BINANCE_API_KEY': 'test_key_123',
            'BINANCE_SECRET_KEY': 'test_secret_456',
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'TELEGRAM_CHAT_ID': 'test_chat_id',
            'BINANCE_TESTNET': 'true'
        }
        
        with patch.dict('os.environ', test_env_vars, clear=True):
            env_config = ConfigLoader.load_env_config()
            
            self.assertEqual(env_config['BINANCE_API_KEY'], 'test_key_123')
            self.assertEqual(env_config['BINANCE_SECRET_KEY'], 'test_secret_456')
            self.assertEqual(env_config['TELEGRAM_BOT_TOKEN'], 'test_token')
            self.assertEqual(env_config['TELEGRAM_CHAT_ID'], 'test_chat_id')
            self.assertTrue(env_config['BINANCE_TESTNET'])
    
    def test_validate_config_valid(self):
        """测试验证有效配置"""
        valid_config = {
            'binance': {},
            'data': {
                'symbols': ['BTC/USDT'],
                'intervals': ['1m', '5m'],
                'websocket': {
                    'max_reconnect_attempts': 10,
                    'reconnect_base_delay': 1,
                    'max_reconnect_delay': 64
                }
            },
            'signals': {},
            'risk': {},
            'execution': {},
            'logging': {}
        }
        
        result = ConfigLoader.validate_config(valid_config)
        self.assertTrue(result)
    
    def test_validate_config_invalid_missing_section(self):
        """测试验证无效配置 - 缺少必需节"""
        invalid_config = {
            'binance': {},
            'data': {},  # 缺少必需字段
            'signals': {},
            'risk': {},
            'execution': {},
            'logging': {}
        }
        
        result = ConfigLoader.validate_config(invalid_config)
        self.assertFalse(result)
    
    def test_merge_configs(self):
        """测试合并配置"""
        file_config = {
            'binance': {
                'environment': 'mainnet',
                'api_key': 'file_key',
                'secret_key': 'file_secret'
            },
            'notification': {
                'telegram': {
                    'enabled': True,
                    'chat_id': 'file_chat_id'
                }
            }
        }
        
        env_config = {
            'BINANCE_API_KEY': 'env_key',
            'BINANCE_SECRET_KEY': 'env_secret',
            'BINANCE_TESTNET': True,
            'TELEGRAM_BOT_TOKEN': 'env_token',
            'TELEGRAM_CHAT_ID': 'env_chat_id'
        }
        
        merged = ConfigLoader.merge_configs(file_config, env_config)
        
        # 检查合并结果
        self.assertEqual(merged['binance']['api_key'], 'env_key')
        self.assertEqual(merged['binance']['secret_key'], 'env_secret')
        self.assertEqual(merged['binance']['environment'], 'testnet')
        self.assertEqual(merged['notification']['telegram']['bot_token'], 'env_token')
        self.assertEqual(merged['notification']['telegram']['chat_id'], 'env_chat_id')
    
    def test_get_full_config(self):
        """测试获取完整配置"""
        mock_file_config = {
            'binance': {'environment': 'mainnet'},
            'data': {
                'symbols': ['BTC/USDT'],
                'intervals': ['1m'],
                'websocket': {
                    'max_reconnect_attempts': 10,
                    'reconnect_base_delay': 1,
                    'max_reconnect_delay': 64
                }
            },
            'signals': {},
            'risk': {},
            'execution': {},
            'logging': {}
        }
        
        mock_env_config = {
            'BINANCE_API_KEY': 'env_key',
            'BINANCE_SECRET_KEY': 'env_secret',
            'BINANCE_TESTNET': 'false',
            'TELEGRAM_BOT_TOKEN': '',
            'TELEGRAM_CHAT_ID': ''
        }
        
        with patch.object(ConfigLoader, 'load_config', return_value=mock_file_config):
            with patch.object(ConfigLoader, 'load_env_config', return_value=mock_env_config):
                with patch.object(ConfigLoader, 'validate_config', return_value=True):
                    
                    full_config = ConfigLoader.get_full_config('/fake/path/config.yaml')
                    
                    self.assertIn('binance', full_config)
                    self.assertIn('data', full_config)
                    # 环境变量应被合并
                    self.assertEqual(full_config['binance']['api_key'], 'env_key')
    
    def test_get_default_config(self):
        """测试获取默认配置"""
        default_config = ConfigLoader.get_default_config()
        
        # 检查默认配置结构
        self.assertIn('binance', default_config)
        self.assertIn('data', default_config)
        self.assertIn('signals', default_config)
        self.assertIn('risk', default_config)
        self.assertIn('execution', default_config)
        self.assertIn('logging', default_config)
        
        # 检查具体值
        self.assertEqual(default_config['binance']['environment'], 'testnet')
        self.assertEqual(default_config['data']['symbols'], ['BTCUSDT'])
        self.assertEqual(default_config['execution']['mode'], 'simulation')
    
    def test_save_config(self):
        """测试保存配置"""
        config = {
            'binance': {
                'environment': 'testnet',
                'api_key': 'test_key'
            }
        }
        
        mock_yaml_dump = None
        
        def mock_yaml_dump_func(data, stream, **kwargs):
            nonlocal mock_yaml_dump
            mock_yaml_dump = data
        
        with patch('pathlib.Path.mkdir'):
            with patch('builtins.open', mock_open()):
                with patch('yaml.dump', side_effect=mock_yaml_dump_func):
                    ConfigLoader.save_config(config, '/fake/path/config.yaml')
                    
                    # 验证yaml.dump被调用
                    self.assertIsNotNone(mock_yaml_dump)
                    self.assertEqual(mock_yaml_dump['binance']['environment'], 'testnet')


if __name__ == '__main__':
    unittest.main()