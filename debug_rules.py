"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
调试规则引擎
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from config.config_manager import ConfigManager
from src.risk.rule_engine import RiskRuleEngine

def test_skip_default_rules():
    """测试skip_default_rules参数"""
    print("测试1: 不使用skip_default_rules")
    config = ConfigManager()
    engine1 = RiskRuleEngine(config)
    print(f"  规则数量: {len(engine1.rules)}")
    print(f"  规则IDs: {list(engine1.rules.keys())}")
    
    print("\n测试2: 使用skip_default_rules=True")
    engine2 = RiskRuleEngine(config, skip_default_rules=True)
    print(f"  规则数量: {len(engine2.rules)}")
    print(f"  规则IDs: {list(engine2.rules.keys())}")
    
    print("\n测试3: 添加自定义规则后")
    from src.risk.rule_engine import RiskRule, RuleType, RulePriority
    engine3 = RiskRuleEngine(config, skip_default_rules=True)
    test_rule = RiskRule(
        rule_id="test_rule",
        rule_name="测试规则",
        rule_type=RuleType.STOP_LOSS,
        priority=RulePriority.HIGH,
        parameters={"stop_loss_percent": 0.02}
    )
    engine3.add_rule(test_rule)
    print(f"  规则数量: {len(engine3.rules)}")
    print(f"  规则IDs: {list(engine3.rules.keys())}")

if __name__ == "__main__":
    test_skip_default_rules()