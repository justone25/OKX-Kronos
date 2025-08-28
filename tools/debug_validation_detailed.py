#!/usr/bin/env python3
"""
详细调试验证程序 - 逐步检查验证逻辑
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def debug_validation_detailed():
    """详细调试验证逻辑"""
    print("🔍 详细调试验证程序")
    print("=" * 60)
    
    conn = sqlite3.connect('./data/predictions.db')
    current_time = datetime.now()
    
    print(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 检查测试预测
    print(f"\n📊 检查测试预测 (ID 343):")
    test_pred = pd.read_sql_query('''
        SELECT id, instrument, timestamp, pred_hours,
               datetime(timestamp, '+' || pred_hours || ' hours') as target_time
        FROM predictions 
        WHERE id = 343
    ''', conn)
    
    if not test_pred.empty:
        row = test_pred.iloc[0]
        pred_time = datetime.fromisoformat(row['timestamp'])
        target_time = datetime.fromisoformat(row['target_time'])
        
        print(f"预测时间: {pred_time.strftime('%H:%M:%S')}")
        print(f"目标时间: {target_time.strftime('%H:%M:%S')}")
        print(f"预测时长: {row['pred_hours']} 小时")
        
        # 计算验证窗口
        validation_start = target_time
        validation_end = target_time + timedelta(minutes=30)
        
        print(f"验证窗口: {validation_start.strftime('%H:%M:%S')} - {validation_end.strftime('%H:%M:%S')}")
        
        # 判断当前状态
        if current_time < validation_start:
            status = f"等待验证 (还需 {(validation_start - current_time).total_seconds()/60:.0f} 分钟)"
        elif validation_start <= current_time <= validation_end:
            status = "可以验证"
        else:
            status = f"已过期 (过期 {(current_time - validation_end).total_seconds()/60:.0f} 分钟)"
        
        print(f"状态: {status}")
    else:
        print("测试预测不存在")
    
    # 2. 检查验证记录
    print(f"\n📋 检查验证记录:")
    validation_record = pd.read_sql_query('''
        SELECT * FROM prediction_validations WHERE prediction_id = 343
    ''', conn)
    
    if not validation_record.empty:
        print("已有验证记录:")
        print(validation_record.to_string())
    else:
        print("无验证记录")
    
    # 3. 测试验证查询
    print(f"\n🔍 测试验证查询:")
    
    # 当前验证窗口
    validation_window_start = (current_time - timedelta(minutes=30)).isoformat()
    validation_window_end = current_time.isoformat()
    
    print(f"验证窗口开始: {validation_window_start}")
    print(f"验证窗口结束: {validation_window_end}")
    
    # 执行验证查询
    query = '''
        SELECT p.id, p.instrument, p.timestamp, p.current_price, p.predicted_price,
               p.price_change_pct, p.trend_direction, p.pred_hours,
               p.volatility,
               datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
        FROM predictions p
        LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
        WHERE pv.prediction_id IS NULL
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') <= ?
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') >= ?
        ORDER BY p.timestamp ASC
    '''
    
    results = pd.read_sql_query(query, conn, params=(validation_window_end, validation_window_start))
    
    print(f"查询结果: {len(results)} 个预测")
    
    if not results.empty:
        print("找到的预测:")
        for _, row in results.iterrows():
            target_time = datetime.fromisoformat(row['target_time'])
            print(f"  ID {row['id']}: {row['instrument']} 目标时间 {target_time.strftime('%H:%M:%S')}")
    
    # 4. 检查所有未验证的预测
    print(f"\n📊 所有未验证的预测:")
    all_unvalidated = pd.read_sql_query('''
        SELECT p.id, p.instrument, p.timestamp, p.pred_hours,
               datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
        FROM predictions p
        LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
        WHERE pv.prediction_id IS NULL
        ORDER BY p.timestamp DESC
        LIMIT 10
    ''', conn)
    
    print(f"未验证预测数量: {len(all_unvalidated)}")
    
    for _, row in all_unvalidated.iterrows():
        target_time = datetime.fromisoformat(row['target_time'])
        if current_time < target_time:
            status = f"等待 {(target_time - current_time).total_seconds()/60:.0f}分钟"
        elif current_time <= target_time + timedelta(minutes=30):
            status = "可验证"
        else:
            status = f"过期 {(current_time - target_time - timedelta(minutes=30)).total_seconds()/60:.0f}分钟"
        
        print(f"  ID {row['id']}: {row['instrument']:<15} "
              f"目标:{target_time.strftime('%H:%M')} {status}")
    
    conn.close()

if __name__ == "__main__":
    debug_validation_detailed()
