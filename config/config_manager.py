"""
配置管理器 - 读取和管理YAML配置文件

功能：
1. 加载YAML配置文件
2. 提供配置项访问接口
3. 支持环境变量覆盖
4. 配置验证与默认值

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union


class ConfigManager:
    """
    配置管理器
    
    设计特性：
    1. 单例模式：确保全局配置一致性
    2. 懒加载：首次访问时加载配置
    3. 环境变量覆盖：支持通过环境变量覆盖配置
    4. 类型安全：提供类型转换接口
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 可选，配置文件路径，默认使用 config/config.yaml
        """
        self._config_path = config_path or str(Path(__file__).parent / "config.yaml")
        self._config: Dict[str, Any] = {}
        self._loaded = False
        
    def _load_config(self) -> None:
        """
        加载配置文件
        
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML解析错误
        """
        if self._loaded:
            return
            
        try:
            # 检查文件是否存在
            if not Path(self._config_path).exists():
                raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
            
            # 读取YAML文件
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            
            # 应用环境变量覆盖
            self._apply_environment_overrides()
            
            self._loaded = True
            print(f"配置已加载: {self._config_path}")
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML解析错误: {e}")
        except Exception as e:
            raise RuntimeError(f"加载配置失败: {e}")
    
    def _apply_environment_overrides(self) -> None:
        """
        应用环境变量覆盖
        
        环境变量格式: BINANCE_AI_<SECTION>_<KEY>=value
        例如: BINANCE_AI_BINANCE_ENVIRONMENT=testnet
        """
        prefix = "BINANCE_AI_"
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # 转换环境变量名为配置路径
                config_path = key[len(prefix):].lower().split('_')
                
                # 遍历配置路径
                current = self._config
                for i, part in enumerate(config_path[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # 设置值（简单字符串转换）
                last_part = config_path[-1]
                try:
                    # 尝试转换为适当类型
                    if value.lower() in ['true', 'false']:
                        current[last_part] = value.lower() == 'true'
                    elif value.isdigit():
                        current[last_part] = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        current[last_part] = float(value)
                    else:
                        current[last_part] = value
                except (ValueError, AttributeError):
                    current[last_part] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔（如 'binance.environment'）
            default: 默认值（如果键不存在）
            
        Returns:
            配置值
        """
        if not self._loaded:
            self._load_config()
        
        # 分割键路径
        parts = key.split('.')
        current = self._config
        
        # 遍历路径
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        
        return current
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值（内存中，不持久化）
        
        Args:
            key: 配置键，支持点号分隔
            value: 配置值
        """
        if not self._loaded:
            self._load_config()
        
        # 分割键路径
        parts = key.split('.')
        current = self._config
        
        # 遍历路径（除最后一部分外）
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        
        # 设置值
        current[parts[-1]] = value
    
    def save(self, filepath: Optional[str] = None) -> bool:
        """
        保存配置到文件
        
        Args:
            filepath: 可选，文件路径，默认使用原始路径
            
        Returns:
            是否成功保存
        """
        try:
            save_path = filepath or self._config_path
            
            # 确保目录存在
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 写入YAML文件
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            print(f"配置已保存: {save_path}")
            return True
            
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def reload(self) -> None:
        """
        重新加载配置
        """
        self._loaded = False
        self._config = {}
        self._load_config()
    
    def get_all(self) -> Dict[str, Any]:
        """
        获取所有配置
        
        Returns:
            完整配置字典
        """
        if not self._loaded:
            self._load_config()
        
        return self._config.copy()
    
    def __getitem__(self, key: str) -> Any:
        """
        支持字典式访问
        
        Args:
            key: 配置键
            
        Returns:
            配置值
            
        Raises:
            KeyError: 键不存在
        """
        value = self.get(key)
        if value is None:
            raise KeyError(f"配置键不存在: {key}")
        return value
    
    def __contains__(self, key: str) -> bool:
        """
        检查配置键是否存在
        
        Args:
            key: 配置键
            
        Returns:
            是否存在
        """
        return self.get(key) is not None


# 全局配置实例
_default_config: Optional[ConfigManager] = None


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """
    获取全局配置实例（单例模式）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        配置管理器实例
    """
    global _default_config
    
    if _default_config is None:
        _default_config = ConfigManager(config_path)
    
    return _default_config


if __name__ == "__main__":
    """模块自测"""
    # 测试配置加载
    config = ConfigManager()
    
    # 获取配置值
    env = config.get("binance.environment", "mainnet")
    print(f"币安环境: {env}")
    
    # 获取所有配置
    all_config = config.get_all()
    print(f"配置项数量: {len(str(all_config))} 字符")
    
    # 测试设置与保存
    config.set("test.key", "test_value")
    test_value = config.get("test.key")
    print(f"测试键值: {test_value}")
    
    # 测试保存（注释掉以避免覆盖实际配置）
    # config.save("config/test_config.yaml")
    # print("测试配置已保存")