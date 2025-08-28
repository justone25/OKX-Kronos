#!/usr/bin/env python3
"""
检查Kronos预测验证时机
"""
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def check_validation_timing():
    """检查验证时机"""
    print("🕐 Kronos预测验证时机检查")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect('../data/predictions.db')
        
        # 获取当前时间
        current_time = datetime.now()
        print(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 查询最近的预测
        query = '''
            SELECT p.id, p.timestamp, p.pred_hours,
                   datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time,
                   p.current_price, p.predicted_price, p.trend_direction
            FROM predictions p
            LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
            WHERE pv.prediction_id IS NULL
            ORDER BY p.timestamp DESC
            LIMIT 10
        '''
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            print("❌ 没有找到未验证的预测")
            return
        
        print(f"\n📊 未验证预测列表 (共 {len(df)} 个):")
        print("-" * 100)
        print(f"{'ID':<4} {'预测时间':<20} {'目标时间':<20} {'状态':<20} {'等待时间':<15}")
        print("-" * 100)
        
        validation_count = 0
        next_validation = None
        
        for _, row in df.iterrows():
            pred_id = row['id']
            pred_time = datetime.fromisoformat(row['timestamp'])
            target_time = datetime.fromisoformat(row['target_time'])
            
            # 验证窗口：目标时间到目标时间+30分钟
            validation_start = target_time
            validation_end = target_time + timedelta(minutes=30)
            
            if current_time >= validation_start and current_time <= validation_end:
                status = "✅ 可验证"
                wait_time = "现在"
                validation_count += 1
            elif current_time < validation_start:
                wait_minutes = (validation_start - current_time).total_seconds() / 60
                wait_hours = wait_minutes / 60
                
                if wait_hours >= 1:
                    wait_time = f"{wait_hours:.1f}小时"
                else:
                    wait_time = f"{wait_minutes:.0f}分钟"
                
                status = "⏳ 等待中"
                
                if next_validation is None:
                    next_validation = {
                        'id': pred_id,
                        'time': validation_start,
                        'wait_minutes': wait_minutes
                    }
            else:
                status = "❌ 已过期"
                wait_time = "已过期"
            
            print(f"{pred_id:<4} {pred_time.strftime('%m-%d %H:%M'):<20} "
                  f"{target_time.strftime('%m-%d %H:%M'):<20} {status:<20} {wait_time:<15}")
        
        print("-" * 100)
        
        # 总结
        if validation_count > 0:
            print(f"🎯 当前有 {validation_count} 个预测可以验证")
        elif next_validation:
            print(f"📅 下次验证: ID {next_validation['id']} "
                  f"在 {next_validation['time'].strftime('%H:%M:%S')} "
                  f"(还需等待 {next_validation['wait_minutes']:.0f} 分钟)")
        else:
            print("ℹ️ 所有预测都已过验证窗口或已验证")
        
        # 显示验证逻辑说明
        print(f"\n💡 验证逻辑说明:")
        print(f"   • 预测时长: 2小时")
        print(f"   • 验证窗口: 预测到期后30分钟内")
        print(f"   • 例如: 08:00预测 → 10:00-10:30验证窗口")
        
        # 检查是否有已验证的预测
        conn = sqlite3.connect('./data/predictions.db')
        validated_count = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM prediction_validations", 
            conn
        ).iloc[0]['count']
        conn.close()
        
        print(f"\n📊 历史验证统计:")
        print(f"   • 已验证预测: {validated_count} 个")
        print(f"   • 待验证预测: {len(df)} 个")
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_validation_timing()
