#!/usr/bin/env python3
"""
测试增强的验证系统 - 使用历史K线数据进行准确验证
"""
import sys
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig
from src.data.kline_storage import KlineStorageService
from src.validation.prediction_validator import PredictionValidator

def test_enhanced_validation():
    """测试增强的验证系统"""
    print("🚀 测试增强的验证系统")
    print("=" * 60)
    
    try:
        # 初始化配置和服务
        config = OKXConfig()
        kline_service = KlineStorageService(config)
        validator = PredictionValidator(config)
        
        print("✅ 服务初始化完成")
        
        # 1. 测试K线数据存储
        print(f"\n📈 测试K线数据存储:")
        instruments = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
        
        for instrument in instruments:
            print(f"   存储 {instrument} 的历史K线数据...")
            success = kline_service.store_historical_klines(
                instrument=instrument,
                bar_size="1m",
                hours=2  # 存储2小时的数据
            )
            
            if success:
                print(f"   ✅ {instrument} K线数据存储成功")
            else:
                print(f"   ⚠️ {instrument} K线数据存储失败")
        
        # 2. 创建测试预测（包含高低价预测）
        print(f"\n🎯 创建增强测试预测:")
        
        conn = sqlite3.connect('./data/predictions.db')
        cursor = conn.cursor()
        
        # 创建一个5分钟前的预测，现在就可以验证
        prediction_time = datetime.now() - timedelta(minutes=10)
        current_price = 113000.0
        predicted_price = current_price * 1.002  # 预测上涨0.2%
        predicted_high = predicted_price * 1.005  # 预测最高价
        predicted_low = current_price * 0.998     # 预测最低价
        
        price_change = predicted_price - current_price
        price_change_pct = (price_change / current_price) * 100
        
        # 插入增强测试预测
        cursor.execute('''
            INSERT INTO predictions (
                timestamp, instrument, current_price, predicted_price,
                price_change, price_change_pct, predicted_high, predicted_low,
                volatility, trend_direction, lookback_hours, pred_hours,
                temperature, top_p, sample_count, prediction_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            prediction_time.isoformat(),
            'BTC-USDT-SWAP',
            current_price,
            predicted_price,
            price_change,
            price_change_pct,
            predicted_high,
            predicted_low,
            80.0,  # volatility
            'up',  # trend_direction
            24,    # lookback_hours
            0.17,  # pred_hours (10分钟)
            0.8,   # temperature
            0.9,   # top_p
            1,     # sample_count
            '{"enhanced": true}'  # prediction_data
        ))
        
        test_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        target_time = prediction_time + timedelta(hours=0.17)
        
        print(f"✅ 增强测试预测已创建:")
        print(f"   ID: {test_id}")
        print(f"   预测时间: {prediction_time.strftime('%H:%M:%S')}")
        print(f"   目标时间: {target_time.strftime('%H:%M:%S')}")
        print(f"   当前价格: ${current_price:,.2f}")
        print(f"   预测价格: ${predicted_price:,.2f}")
        print(f"   预测高价: ${predicted_high:,.2f}")
        print(f"   预测低价: ${predicted_low:,.2f}")
        print(f"   价格变化: {price_change_pct:+.2f}%")
        
        # 3. 测试K线数据获取
        print(f"\n🔍 测试K线数据获取:")
        kline_data = kline_service.get_historical_kline_at_time(
            instrument='BTC-USDT-SWAP',
            target_time=target_time,
            bar_size='1m',
            tolerance_minutes=10
        )
        
        if kline_data:
            print(f"✅ 成功获取K线数据:")
            print(f"   时间: {kline_data['timestamp']}")
            print(f"   开盘: ${kline_data['open']:,.2f}")
            print(f"   最高: ${kline_data['high']:,.2f}")
            print(f"   最低: ${kline_data['low']:,.2f}")
            print(f"   收盘: ${kline_data['close']:,.2f}")
        else:
            print(f"⚠️ 未能获取K线数据")
        
        # 4. 运行增强验证
        print(f"\n🔬 运行增强验证:")
        
        # 获取测试预测
        conn = sqlite3.connect('./data/predictions.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, instrument, timestamp, current_price, predicted_price,
                   price_change_pct, trend_direction, pred_hours, volatility,
                   predicted_high, predicted_low
            FROM predictions 
            WHERE id = ?
        """, (test_id,))
        
        prediction_data = cursor.fetchone()
        conn.close()
        
        if prediction_data:
            prediction = {
                'id': prediction_data[0],
                'instrument': prediction_data[1],
                'timestamp': prediction_data[2],
                'current_price': prediction_data[3],
                'predicted_price': prediction_data[4],
                'price_change_pct': prediction_data[5],
                'trend_direction': prediction_data[6],
                'pred_hours': prediction_data[7],
                'volatility': prediction_data[8],
                'predicted_high': prediction_data[9],
                'predicted_low': prediction_data[10]
            }
            
            # 执行验证
            result = validator.validate_prediction(prediction)
            
            if result:
                print(f"✅ 增强验证完成:")
                print(f"   预测ID: {result.prediction_id}")
                print(f"   实际价格: ${result.actual_price:,.2f}")
                print(f"   实际最高: ${result.actual_high:,.2f}")
                print(f"   实际最低: ${result.actual_low:,.2f}")
                print(f"   价格误差: {result.price_error_pct:+.2f}%")
                print(f"   方向正确: {'✅' if result.direction_correct else '❌'}")
                print(f"   高价预测: {'✅' if result.high_prediction_correct else '❌'}")
                print(f"   低价预测: {'✅' if result.low_prediction_correct else '❌'}")
                print(f"   验证状态: {result.validation_status.value}")
                print(f"   置信度校准: {result.confidence_calibration:.3f}")
            else:
                print(f"❌ 验证失败")
        else:
            print(f"❌ 未找到测试预测")
        
        # 5. 检查验证结果是否正确保存
        print(f"\n💾 检查验证结果保存:")
        conn = sqlite3.connect('./data/predictions.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prediction_id, actual_price, actual_high, actual_low,
                   price_error_pct, direction_correct, high_prediction_correct,
                   low_prediction_correct, validation_status
            FROM prediction_validations 
            WHERE prediction_id = ?
        """, (test_id,))
        
        validation_record = cursor.fetchone()
        conn.close()
        
        if validation_record:
            print(f"✅ 验证结果已保存:")
            print(f"   预测ID: {validation_record[0]}")
            print(f"   实际价格: ${validation_record[1]:,.2f}")
            print(f"   实际最高: ${validation_record[2]:,.2f}")
            print(f"   实际最低: ${validation_record[3]:,.2f}")
            print(f"   价格误差: {validation_record[4]:+.2f}%")
            print(f"   方向正确: {validation_record[5]}")
            print(f"   高价预测: {validation_record[6]}")
            print(f"   低价预测: {validation_record[7]}")
            print(f"   验证状态: {validation_record[8]}")
        else:
            print(f"❌ 验证结果未保存")
        
        print(f"\n🎉 增强验证系统测试完成！")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_enhanced_validation()
