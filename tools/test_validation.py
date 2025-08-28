#!/usr/bin/env python3
"""
测试验证程序 - 手动运行一次验证
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.validation.prediction_validator import PredictionValidator
from src.utils.config import OKXConfig

def test_validation():
    """测试验证程序"""
    print("🔍 测试验证程序")
    print("=" * 50)
    
    try:
        # 初始化配置
        config = OKXConfig()
        
        # 创建验证器
        validator = PredictionValidator(config)
        
        # 运行验证周期
        result = validator.run_validation_cycle()
        
        print(f"\n✅ 验证完成:")
        print(f"验证数量: {result['validated_count']}")
        print(f"结果数量: {len(result.get('results', []))}")
        
        if result.get('results'):
            print(f"\n📊 验证结果:")
            for i, validation_result in enumerate(result['results'][:3]):
                print(f"  {i+1}. 预测ID: {validation_result.prediction_id}")
                print(f"     价格误差: {validation_result.price_error_pct:.2f}%")
                print(f"     方向正确: {validation_result.direction_correct}")
                print(f"     状态: {validation_result.validation_status.value}")
        
        return result
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_validation()
