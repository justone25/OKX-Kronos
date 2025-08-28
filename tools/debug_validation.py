#!/usr/bin/env python3
"""
调试验证程序 - 检查为什么验证没有运行
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def debug_validation():
    """调试验证逻辑"""
    print("🔍 调试验证程序")
    print("=" * 60)
    
    # 连接数据库
    conn = sqlite3.connect('./data/predictions.db')
    
    # 1. 检查最近的预测
    print("\n📊 最近的预测:")
    recent_predictions = pd.read_sql_query('''
        SELECT id, instrument, timestamp, pred_hours,
               datetime(timestamp, '+' || pred_hours || ' hours') as target_time
        FROM predictions 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''', conn)
    
    current_time = datetime.now()
    print(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    for _, row in recent_predictions.iterrows():
        pred_time = datetime.fromisoformat(row['timestamp'])
        target_time = datetime.fromisoformat(row['target_time'])
        
        # 计算验证窗口
        validation_start = target_time
        validation_end = target_time + timedelta(minutes=30)
        
        # 判断状态
        if current_time < validation_start:
            status = f"等待验证 (还需 {(validation_start - current_time).total_seconds()/60:.0f} 分钟)"
        elif validation_start <= current_time <= validation_end:
            status = "可以验证"
        else:
            status = f"已过期 (过期 {(current_time - validation_end).total_seconds()/60:.0f} 分钟)"
        
        print(f"ID {row['id']:3d}: {row['instrument']:<15} "
              f"预测:{pred_time.strftime('%H:%M')} "
              f"目标:{target_time.strftime('%H:%M')} "
              f"窗口:{validation_start.strftime('%H:%M')}-{validation_end.strftime('%H:%M')} "
              f"状态:{status}")
    
    # 2. 检查验证窗口逻辑
    print(f"\n🔍 当前验证窗口逻辑分析:")
    validation_window_start = (current_time - timedelta(minutes=30)).isoformat()
    validation_window_end = current_time.isoformat()
    
    print(f"验证窗口开始: {validation_window_start}")
    print(f"验证窗口结束: {validation_window_end}")
    print(f"窗口长度: 30分钟")
    
    # 3. 使用当前验证逻辑查询
    print(f"\n📋 使用当前验证逻辑查询:")
    current_validation_query = '''
        SELECT p.id, p.timestamp, p.pred_hours,
               datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
        FROM predictions p
        LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
        WHERE pv.prediction_id IS NULL
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') <= ?
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') >= ?
        ORDER BY p.timestamp ASC
    '''
    
    current_results = pd.read_sql_query(
        current_validation_query, 
        conn, 
        params=(validation_window_end, validation_window_start)
    )
    
    print(f"当前逻辑找到 {len(current_results)} 个待验证预测")
    
    # 4. 修正的验证逻辑
    print(f"\n🔧 修正的验证逻辑:")
    corrected_query = '''
        SELECT p.id, p.timestamp, p.pred_hours,
               datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
        FROM predictions p
        LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
        WHERE pv.prediction_id IS NULL
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') <= ?
        AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') >= ?
        ORDER BY p.timestamp ASC
    '''
    
    # 修正的窗口：当前时间往前推30分钟到当前时间
    corrected_start = (current_time - timedelta(minutes=30)).isoformat()
    corrected_end = current_time.isoformat()
    
    corrected_results = pd.read_sql_query(
        corrected_query,
        conn,
        params=(corrected_end, corrected_start)
    )
    
    print(f"修正逻辑找到 {len(corrected_results)} 个待验证预测")
    
    if not corrected_results.empty:
        print("修正逻辑找到的预测:")
        for _, row in corrected_results.iterrows():
            target_time = datetime.fromisoformat(row['target_time'])
            print(f"  ID {row['id']}: 目标时间 {target_time.strftime('%H:%M:%S')}")
    
    # 5. 检查已验证的预测
    validated_count = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM prediction_validations", 
        conn
    ).iloc[0]['count']
    
    print(f"\n📊 验证统计:")
    print(f"已验证预测: {validated_count} 个")
    print(f"总预测数: {len(recent_predictions)} 个")
    
    conn.close()
    
    # 6. 建议
    print(f"\n💡 问题分析:")
    print(f"1. 验证窗口逻辑可能有问题")
    print(f"2. 预测时长为2小时，验证窗口为30分钟")
    print(f"3. 需要检查预测是否在正确的时间窗口内")
    
    return corrected_results

if __name__ == "__main__":
    debug_validation()
