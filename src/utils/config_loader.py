#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器
负责加载和验证配置文件
"""
import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """
        加载YAML配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML解析错误
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
            
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        logger.info(f"配置文件加载成功: {config_path}")
        return config or {}
    
    @staticmethod
    def load_env_config() -> Dict[str, str]:
        """
        加载环境变量配置
        
        Returns:
            Dict[str, str]: 环境变量配置
        """
        env_config = {}
        
        # 币安API配置
        env_config['BINANCE_API_KEY'] = os.getenv('BINANCE_API_KEY', '')
        env_config['BINANCE_SECRET_KEY'] = os.getenv('BINANCE_SECRET_KEY', '')
        env_config['BINANCE_TESTNET'] = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
        
        # Telegram配置
        env_config['TELEGRAM_BOT_TOKEN'] = os.getenv('TELEGRAM_BOT_TOKEN', '')
        env_config['TELEGRAM_CHAT_ID'] = os.getenv('TELEGRAM_CHAT_ID', '')
        
        # 检查必要环境变量
        required_envs = ['BINANCE_API_KEY', 'BINANCE_SECRET_KEY']
        missing_envs = [env for env in required_envs if not env_config.get(env)]
        
        if missing_envs:
            logger.warning(f"缺少必要环境变量: {missing_envs}")
        
        return env_config
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        """
        验证配置完整性
        
        Args:
            config: 配置字典
            
        Returns:
            bool: 配置是否有效
        """
        try:
            # 检查必需配置项
            required_sections = ['binance', 'data', 'signals', 'risk', 'execution', 'logging']
            for section in required_sections:
                if section not in config:
                    logger.error(f"缺少必需配置节: {section}")
                    return False
            
            # 检查数据配置
            data_config = config['data']
            if 'symbols' not in data_config or not data_config['symbols']:
                logger.error("数据配置中缺少交易对列表")
                return False
            
            if 'intervals' not in data_config or not data_config['intervals']:
                logger.error("数据配置中缺少K线间隔列表")
                return False
            
            # 检查WebSocket配置
            if 'websocket' not in data_config:
                logger.error("数据配置中缺少WebSocket配置")
                return False
            
            ws_config = data_config['websocket']
            required_ws_params = ['max_reconnect_attempts', 'reconnect_base_delay', 'max_reconnect_delay']
            for param in required_ws_params:
                if param not in ws_config:
                    logger.error(f"WebSocket配置中缺少参数: {param}")
                    return False
            
            logger.info("配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    @staticmethod
    def merge_configs(file_config: Dict[str, Any], env_config: Dict[str, str]) -> Dict[str, Any]:
        """
        合并文件配置和环境变量配置
        
        Args:
            file_config: 文件配置
            env_config: 环境变量配置
            
        Returns:
            Dict[str, Any]: 合并后的配置
        """
        # 创建配置副本
        merged = file_config.copy()
        
        # 合并币安配置
        if 'binance' not in merged:
            merged['binance'] = {}
        
        # 设置环境变量
        merged['binance']['api_key'] = env_config.get('BINANCE_API_KEY', '')
        merged['binance']['secret_key'] = env_config.get('BINANCE_SECRET_KEY', '')
        
        # 如果环境变量设置了testnet，覆盖配置文件
        if 'BINANCE_TESTNET' in env_config:
            merged['binance']['environment'] = 'testnet' if env_config['BINANCE_TESTNET'] else 'mainnet'
        
        # 合并Telegram配置
        if 'notification' in merged and 'telegram' in merged['notification']:
            merged['notification']['telegram']['bot_token'] = env_config.get('TELEGRAM_BOT_TOKEN', '')
            merged['notification']['telegram']['chat_id'] = env_config.get('TELEGRAM_CHAT_ID', '')
            
            # 如果没有配置token，则禁用Telegram
            if not merged['notification']['telegram']['bot_token']:
                merged['notification']['telegram']['enabled'] = False
        
        return merged
    
    @staticmethod
    def get_full_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        获取完整配置（文件 + 环境变量）
        
        Args:
            config_path: 配置文件路径，默认为 config/config.yaml
            
        Returns:
            Dict[str, Any]: 完整配置
        """
        try:
            # 加载文件配置
            if config_path is None:
                config_path = "config/config.yaml"
            
            file_config = ConfigLoader.load_config(config_path)
            
            # 加载环境变量配置
            env_config = ConfigLoader.load_env_config()
            
            # 合并配置
            merged_config = ConfigLoader.merge_configs(file_config, env_config)
            
            # 验证配置
            if not ConfigLoader.validate_config(merged_config):
                logger.warning("配置验证失败，可能影响系统正常运行")
            
            return merged_config
            
        except Exception as e:
            logger.error(f"获取完整配置失败: {e}")
            # 返回默认配置
            return ConfigLoader.get_default_config()
    
    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        """
        获取默认配置
        
        Returns:
            Dict[str, Any]: 默认配置
        """
        return {
            'binance': {
                'environment': 'testnet',
                'api_key': '',
                'secret_key': ''
            },
            'data': {
                'symbols': ['BTCUSDT'],
                'intervals': ['1m', '5m'],
                'websocket': {
                    'max_reconnect_attempts': 10,
                    'reconnect_base_delay': 1,
                    'max_reconnect_delay': 64
                }
            },
            'signals': {
                'indicators': {
                    'ma_periods': [5, 10, 20],
                    'rsi_period': 14
                }
            },
            'risk': {
                'account': {
                    'margin_ratio_warning': 1.5,
                    'daily_loss_limit': 5
                }
            },
            'execution': {
                'mode': 'simulation'
            },
            'logging': {
                'level': 'INFO',
                'console': True
            }
        }
    
    @staticmethod
    def save_config(config: Dict[str, Any], config_path: str):
        """
        保存配置到文件
        
        Args:
            config: 配置字典
            config_path: 配置文件路径
        """
        try:
            path = Path(config_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"配置已保存到: {config_path}")
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")