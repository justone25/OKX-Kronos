#!/usr/bin/env python3
"""
数据库迁移脚本 - 更新数据库结构以支持增强的验证功能
"""
import sqlite3
import logging
from pathlib import Path

def migrate_database(db_path: str = "./data/predictions.db"):
    """迁移数据库结构"""
    print("🔄 开始数据库迁移...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. 检查并添加predictions表的新字段
        print("📊 检查predictions表结构...")
        
        # 获取现有列
        cursor.execute("PRAGMA table_info(predictions)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # 添加缺失的列
        new_columns = [
            ('predicted_high', 'REAL'),
            ('predicted_low', 'REAL'),
            ('prediction_data', 'TEXT')
        ]
        
        for column_name, column_type in new_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE predictions ADD COLUMN {column_name} {column_type}")
                    print(f"✅ 添加列: {column_name}")
                except Exception as e:
                    print(f"⚠️ 添加列 {column_name} 失败: {e}")
        
        # 2. 创建历史K线表
        print("📈 创建历史K线表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historical_klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume REAL NOT NULL,
                amount REAL NOT NULL,
                bar_size TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(instrument, timestamp, bar_size)
            );
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_klines_instrument_timestamp 
            ON historical_klines(instrument, timestamp DESC);
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_klines_timestamp 
            ON historical_klines(timestamp DESC);
        ''')
        
        print("✅ 历史K线表创建完成")
        
        # 3. 更新验证表结构
        print("🔍 更新验证表结构...")
        
        # 检查验证表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_validations'")
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # 获取现有验证表列
            cursor.execute("PRAGMA table_info(prediction_validations)")
            validation_columns = [row[1] for row in cursor.fetchall()]
            
            # 添加新的验证字段
            new_validation_columns = [
                ('actual_high', 'REAL'),
                ('actual_low', 'REAL'),
                ('high_prediction_correct', 'BOOLEAN'),
                ('low_prediction_correct', 'BOOLEAN')
            ]
            
            for column_name, column_type in new_validation_columns:
                if column_name not in validation_columns:
                    try:
                        cursor.execute(f"ALTER TABLE prediction_validations ADD COLUMN {column_name} {column_type}")
                        print(f"✅ 添加验证列: {column_name}")
                    except Exception as e:
                        print(f"⚠️ 添加验证列 {column_name} 失败: {e}")
        else:
            # 创建新的验证表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id INTEGER,
                    validation_timestamp TEXT,
                    predicted_price REAL,
                    actual_price REAL,
                    actual_high REAL,
                    actual_low REAL,
                    price_error REAL,
                    price_error_pct REAL,
                    predicted_direction TEXT,
                    actual_direction TEXT,
                    direction_correct BOOLEAN,
                    high_prediction_correct BOOLEAN,
                    low_prediction_correct BOOLEAN,
                    validation_status TEXT,
                    mae REAL,
                    rmse REAL,
                    mape REAL,
                    directional_accuracy REAL,
                    confidence_calibration REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (prediction_id) REFERENCES predictions (id)
                );
            ''')
            print("✅ 验证表创建完成")
        
        # 4. 提交更改
        conn.commit()
        conn.close()
        
        print("🎉 数据库迁移完成！")
        
        # 5. 显示迁移后的表结构
        print("\n📋 迁移后的表结构:")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 显示predictions表结构
        cursor.execute("PRAGMA table_info(predictions)")
        predictions_columns = cursor.fetchall()
        print("\n📊 predictions表:")
        for col in predictions_columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # 显示historical_klines表结构
        cursor.execute("PRAGMA table_info(historical_klines)")
        klines_columns = cursor.fetchall()
        print("\n📈 historical_klines表:")
        for col in klines_columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # 显示prediction_validations表结构
        cursor.execute("PRAGMA table_info(prediction_validations)")
        validations_columns = cursor.fetchall()
        print("\n🔍 prediction_validations表:")
        for col in validations_columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ 数据库迁移失败: {e}")
        return False

def test_migration():
    """测试迁移后的数据库"""
    print("\n🧪 测试迁移后的数据库...")
    
    try:
        from src.data.kline_storage import KlineStorageService
        from src.utils.config import OKXConfig
        
        config = OKXConfig()
        kline_service = KlineStorageService(config)
        
        print("✅ K线存储服务初始化成功")
        
        # 测试存储一条K线数据
        success = kline_service.store_current_kline("BTC-USDT-SWAP", "1m")
        if success:
            print("✅ K线数据存储测试成功")
        else:
            print("⚠️ K线数据存储测试失败")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据库测试失败: {e}")
        return False

if __name__ == "__main__":
    # 确保数据目录存在
    Path("./data").mkdir(exist_ok=True)
    
    # 执行迁移
    success = migrate_database()
    
    if success:
        # 测试迁移结果
        test_migration()
    else:
        print("❌ 迁移失败，跳过测试")
