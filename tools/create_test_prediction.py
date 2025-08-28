#!/usr/bin/env python3
"""
创建测试预测 - 用于快速验证测试
"""
import sqlite3
from datetime import datetime, timedelta
import random

def create_test_prediction():
    """创建一个30分钟的测试预测"""
    print("🎯 创建测试预测")
    print("=" * 40)
    
    try:
        conn = sqlite3.connect('./data/predictions.db')
        cursor = conn.cursor()
        
        # 创建一个30分钟前的预测，这样现在就可以验证了
        prediction_time = datetime.now() - timedelta(minutes=35)
        current_price = 113000.0
        predicted_price = current_price * (1 + random.uniform(-0.02, 0.02))  # ±2%变化
        price_change = predicted_price - current_price
        price_change_pct = (price_change / current_price) * 100
        
        # 确定趋势方向
        if price_change_pct > 0.1:
            trend_direction = 'up'
        elif price_change_pct < -0.1:
            trend_direction = 'down'
        else:
            trend_direction = 'sideways'
        
        # 插入测试预测
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
            predicted_price * 1.01,
            predicted_price * 0.99,
            random.uniform(50.0, 150.0),
            trend_direction,
            24,  # lookback_hours
            0.5, # pred_hours (30分钟)
            0.8, # temperature
            0.9, # top_p
            1,   # sample_count
            "{}"  # prediction_data
        ))
        
        test_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        target_time = prediction_time + timedelta(hours=0.5)
        
        print(f"✅ 测试预测已创建:")
        print(f"   ID: {test_id}")
        print(f"   预测时间: {prediction_time.strftime('%H:%M:%S')}")
        print(f"   目标时间: {target_time.strftime('%H:%M:%S')}")
        print(f"   当前价格: ${current_price:,.2f}")
        print(f"   预测价格: ${predicted_price:,.2f}")
        print(f"   价格变化: {price_change_pct:+.2f}%")
        print(f"   趋势方向: {trend_direction}")
        print(f"   预测时长: 30分钟")
        
        # 检查是否可以立即验证
        current_time = datetime.now()
        if current_time >= target_time:
            print(f"\n🎯 此预测现在可以验证！")
            validation_window_end = target_time + timedelta(minutes=30)
            if current_time <= validation_window_end:
                print(f"   验证窗口: {target_time.strftime('%H:%M:%S')} - {validation_window_end.strftime('%H:%M:%S')}")
                print(f"   状态: 可以验证")
            else:
                print(f"   状态: 已过验证窗口")
        else:
            wait_minutes = (target_time - current_time).total_seconds() / 60
            print(f"\n⏰ 还需等待 {wait_minutes:.0f} 分钟才能验证")
        
        return test_id
        
    except Exception as e:
        print(f"❌ 创建测试预测失败: {e}")
        return None

if __name__ == "__main__":
    create_test_prediction()
