"""
数据库配置和连接管理
支持SQLite和PostgreSQL
"""

import os
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """数据库配置类"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.db_type = self._detect_db_type()
        
    def _detect_db_type(self) -> str:
        """检测数据库类型"""
        if not self.database_url:
            return 'sqlite'
        
        if self.database_url.startswith('postgresql://') or self.database_url.startswith('postgres://'):
            return 'postgresql'
        elif self.database_url.startswith('sqlite://'):
            return 'sqlite'
        else:
            # 默认为SQLite
            return 'sqlite'
    
    def get_connection_params(self) -> Dict[str, Any]:
        """获取数据库连接参数"""
        if self.db_type == 'postgresql':
            return self._get_postgresql_params()
        else:
            return self._get_sqlite_params()
    
    def _get_postgresql_params(self) -> Dict[str, Any]:
        """获取PostgreSQL连接参数"""
        if not self.database_url:
            raise ValueError("PostgreSQL需要DATABASE_URL环境变量")
        
        parsed = urlparse(self.database_url)
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # 去掉开头的 /
            'user': parsed.username,
            'password': parsed.password
        }
    
    def _get_sqlite_params(self) -> Dict[str, Any]:
        """获取SQLite连接参数"""
        if self.database_url and self.database_url.startswith('sqlite://'):
            db_path = self.database_url.replace('sqlite://', '')
        else:
            # 默认SQLite路径
            db_path = os.getenv('SQLITE_DB_PATH', 'data/predictions.db')
        
        return {
            'database': db_path
        }
    
    def get_connection_string(self) -> str:
        """获取连接字符串"""
        if self.db_type == 'postgresql':
            return self.database_url
        else:
            params = self._get_sqlite_params()
            return f"sqlite:///{params['database']}"

# 全局数据库配置实例
db_config = DatabaseConfig()

def get_db_connection():
    """获取数据库连接"""
    if db_config.db_type == 'postgresql':
        import psycopg2
        params = db_config.get_connection_params()
        return psycopg2.connect(**params)
    else:
        import sqlite3
        params = db_config.get_connection_params()
        return sqlite3.connect(params['database'])

def execute_query(query: str, params: tuple = None, fetch: bool = False):
    """执行数据库查询"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch:
            result = cursor.fetchall()
        else:
            result = cursor.rowcount

        conn.commit()
        return result

    except Exception as e:
        conn.rollback()
        logger.error(f"数据库查询失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def execute_script(script: str):
    """执行多条SQL语句的脚本"""
    conn = get_db_connection()

    try:
        if db_config.db_type == 'postgresql':
            cursor = conn.cursor()
            cursor.execute(script)
            cursor.close()
        else:
            # SQLite支持executescript
            conn.executescript(script)

        conn.commit()

    except Exception as e:
        conn.rollback()
        logger.error(f"数据库脚本执行失败: {e}")
        raise
    finally:
        conn.close()

def get_table_schema() -> Dict[str, str]:
    """获取表结构定义"""
    if db_config.db_type == 'postgresql':
        return {
            'predictions': '''
                CREATE TABLE IF NOT EXISTS predictions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    instrument VARCHAR(50) NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    current_price DECIMAL(20, 8) NOT NULL,
                    predicted_price DECIMAL(20, 8) NOT NULL,
                    price_change DECIMAL(20, 8) NOT NULL,
                    price_change_pct DECIMAL(10, 4) NOT NULL,
                    trend_direction VARCHAR(10) NOT NULL,
                    volatility DECIMAL(10, 4) NOT NULL,
                    lookback_hours INTEGER NOT NULL,
                    pred_hours INTEGER NOT NULL,
                    temperature DECIMAL(3, 2) NOT NULL,
                    top_p DECIMAL(3, 2) NOT NULL,
                    sample_count INTEGER NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_predictions_instrument ON predictions(instrument);
                CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_predictions_instrument_timestamp ON predictions(instrument, timestamp DESC);
            '''
        }
    else:
        return {
            'predictions': '''
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instrument TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    current_price REAL NOT NULL,
                    predicted_price REAL NOT NULL,
                    price_change REAL NOT NULL,
                    price_change_pct REAL NOT NULL,
                    predicted_high REAL,
                    predicted_low REAL,
                    trend_direction TEXT NOT NULL,
                    volatility REAL NOT NULL,
                    lookback_hours INTEGER NOT NULL,
                    pred_hours INTEGER NOT NULL,
                    temperature REAL NOT NULL,
                    top_p REAL NOT NULL,
                    sample_count INTEGER NOT NULL,
                    prediction_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_predictions_instrument ON predictions(instrument);
                CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_predictions_instrument_timestamp ON predictions(instrument, timestamp DESC);
            ''',
            'historical_klines': '''
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

                CREATE INDEX IF NOT EXISTS idx_klines_instrument_timestamp ON historical_klines(instrument, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_klines_timestamp ON historical_klines(timestamp DESC);
            '''
        }

def init_database():
    """初始化数据库表"""
    logger.info(f"初始化数据库 ({db_config.db_type})...")

    schemas = get_table_schema()

    for table_name, schema in schemas.items():
        try:
            execute_script(schema)
            logger.info(f"✅ 表 {table_name} 初始化完成")
        except Exception as e:
            logger.error(f"❌ 表 {table_name} 初始化失败: {e}")
            raise

if __name__ == "__main__":
    # 测试数据库连接
    print(f"数据库类型: {db_config.db_type}")
    print(f"连接参数: {db_config.get_connection_params()}")
    
    try:
        conn = get_db_connection()
        print("✅ 数据库连接成功")
        conn.close()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
