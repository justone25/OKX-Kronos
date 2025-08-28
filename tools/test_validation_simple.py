#!/usr/bin/env python3
"""
简化验证测试 - 使用当前价格进行验证
"""
import sys
import os
from pathlib import Path
import sqlite3
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig
from src.data.okx_fetcher import OKXDataFetcher

def test_simple_validation():
    """简化的验证测试"""
    print("🔍 简化验证测试")
    print("=" * 50)
    
    try:
        # 初始化配置和数据获取器
        config = OKXConfig()
        fetcher = OKXDataFetcher(config)
        
        # 连接数据库
        conn = sqlite3.connect('./data/predictions.db')
        cursor = conn.cursor()
        
        # 获取测试预测
        cursor.execute("""
            SELECT id, instrument, timestamp, current_price, predicted_price,
                   price_change_pct, trend_direction, pred_hours
            FROM predictions 
            WHERE id = 343
        """)
        
        prediction = cursor.fetchone()
        if not prediction:
            print("❌ 测试预测不存在")
            return
        
        pred_id, instrument, timestamp, current_price, predicted_price, price_change_pct, trend_direction, pred_hours = prediction
        
        print(f"📊 测试预测信息:")
        print(f"   ID: {pred_id}")
        print(f"   交易对: {instrument}")
        print(f"   预测时间: {timestamp}")
        print(f"   预测价格: ${predicted_price:,.2f}")
        print(f"   当时价格: ${current_price:,.2f}")
        print(f"   预测变化: {price_change_pct:+.2f}%")
        print(f"   预测方向: {trend_direction}")
        print(f"   预测时长: {pred_hours} 小时")
        
        # 获取当前实际价格（作为验证价格）
        print(f"\n🔍 获取当前价格进行验证:")
        try:
            actual_price = fetcher.get_current_price_with_fallback(instrument)
            if actual_price:
                print(f"   当前价格: ${actual_price:,.2f}")
                
                # 计算验证结果
                price_error = actual_price - predicted_price
                price_error_pct = (price_error / predicted_price) * 100
                
                # 计算实际方向
                actual_change_pct = ((actual_price - current_price) / current_price) * 100
                if actual_change_pct > 0.1:
                    actual_direction = 'up'
                elif actual_change_pct < -0.1:
                    actual_direction = 'down'
                else:
                    actual_direction = 'sideways'
                
                direction_correct = (trend_direction == actual_direction)
                
                print(f"\n📈 验证结果:")
                print(f"   价格误差: ${price_error:+,.2f} ({price_error_pct:+.2f}%)")
                print(f"   实际变化: {actual_change_pct:+.2f}%")
                print(f"   实际方向: {actual_direction}")
                print(f"   方向正确: {'✅' if direction_correct else '❌'}")
                
                # 保存验证结果
                validation_status = 'SUCCESS'
                if abs(price_error_pct) <= 2.0:
                    validation_status = 'EXCELLENT'
                elif abs(price_error_pct) <= 5.0:
                    validation_status = 'GOOD'
                elif abs(price_error_pct) <= 10.0:
                    validation_status = 'FAIR'
                else:
                    validation_status = 'POOR'
                
                print(f"   验证状态: {validation_status}")
                
                # 插入验证记录
                cursor.execute('''
                    INSERT INTO prediction_validations (
                        prediction_id, validation_timestamp, predicted_price, actual_price,
                        price_error, price_error_pct, predicted_direction, actual_direction,
                        direction_correct, validation_status, mae, rmse, mape,
                        directional_accuracy, confidence_calibration
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pred_id,
                    datetime.now().isoformat(),
                    predicted_price,
                    actual_price,
                    price_error,
                    price_error_pct,
                    trend_direction,
                    actual_direction,
                    direction_correct,
                    validation_status,
                    abs(price_error),
                    price_error ** 2,
                    abs(price_error_pct),
                    1.0 if direction_correct else 0.0,
                    0.8  # 简化的置信度校准
                ))
                
                conn.commit()
                print(f"\n✅ 验证结果已保存到数据库")
                
            else:
                print("❌ 无法获取当前价格")
                
        except Exception as price_error:
            print(f"❌ 获取价格失败: {price_error}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 验证测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_validation()
