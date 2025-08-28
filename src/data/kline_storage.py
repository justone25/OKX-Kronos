#!/usr/bin/env python3
"""
历史K线数据存储服务
实时存储OKX API获取的K线数据，用于验证预测准确性
"""
import sqlite3
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path

from src.utils.config import OKXConfig
from src.data.okx_fetcher import OKXDataFetcher


class KlineStorageService:
    """历史K线数据存储服务"""
    
    def __init__(self, config: OKXConfig, db_path: str = "./data/predictions.db"):
        """
        初始化K线存储服务
        
        Args:
            config: OKX配置
            db_path: 数据库路径
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.db_path = db_path
        self.data_fetcher = OKXDataFetcher(config)
        
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库表
        self._init_database()
        
        self.logger.info("K线存储服务初始化完成")
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建历史K线表（如果不存在）
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
            
            conn.commit()
            conn.close()
            
            self.logger.info("K线存储数据库表初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化K线存储数据库失败: {e}")
            raise
    
    def store_current_kline(self, instrument: str, bar_size: str = "1m") -> bool:
        """
        存储当前K线数据
        
        Args:
            instrument: 交易对
            bar_size: K线周期
            
        Returns:
            是否存储成功
        """
        try:
            # 获取最新的K线数据
            df = self.data_fetcher.get_historical_klines(
                instrument=instrument,
                bar=bar_size,
                limit=1,
                validate_quality=False
            )
            
            if df.empty:
                self.logger.warning(f"未获取到K线数据: {instrument}")
                return False
            
            # 存储到数据库
            return self._store_klines_to_db(df, instrument, bar_size)
            
        except Exception as e:
            self.logger.error(f"存储当前K线数据失败: {e}")
            return False
    
    def store_historical_klines(self, instrument: str, bar_size: str = "1m", 
                               hours: int = 24) -> bool:
        """
        批量存储历史K线数据
        
        Args:
            instrument: 交易对
            bar_size: K线周期
            hours: 存储多少小时的历史数据
            
        Returns:
            是否存储成功
        """
        try:
            # 计算需要的K线数量
            bar_minutes = self._get_bar_minutes(bar_size)
            limit = min(hours * 60 // bar_minutes, 1000)  # 限制最大请求数量
            
            # 获取历史K线数据
            df = self.data_fetcher.get_historical_klines(
                instrument=instrument,
                bar=bar_size,
                limit=limit,
                validate_quality=False
            )
            
            if df.empty:
                self.logger.warning(f"未获取到历史K线数据: {instrument}")
                return False
            
            # 存储到数据库
            return self._store_klines_to_db(df, instrument, bar_size)
            
        except Exception as e:
            self.logger.error(f"存储历史K线数据失败: {e}")
            return False
    
    def _store_klines_to_db(self, df: pd.DataFrame, instrument: str, bar_size: str) -> bool:
        """
        将K线数据存储到数据库
        
        Args:
            df: K线数据DataFrame
            instrument: 交易对
            bar_size: K线周期
            
        Returns:
            是否存储成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            stored_count = 0
            
            for _, row in df.iterrows():
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO historical_klines (
                            instrument, timestamp, open_price, high_price, low_price,
                            close_price, volume, amount, bar_size
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        instrument,
                        row['timestamps'].isoformat(),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        float(row['volume']),
                        float(row['amount']),
                        bar_size
                    ))
                    stored_count += 1
                    
                except Exception as row_error:
                    self.logger.warning(f"存储单条K线数据失败: {row_error}")
                    continue
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"成功存储 {stored_count} 条K线数据: {instrument} {bar_size}")
            return stored_count > 0
            
        except Exception as e:
            self.logger.error(f"存储K线数据到数据库失败: {e}")
            return False
    
    def get_historical_kline_at_time(self, instrument: str, target_time: datetime, 
                                   bar_size: str = "1m", tolerance_minutes: int = 5) -> Optional[Dict]:
        """
        获取指定时间点的历史K线数据
        
        Args:
            instrument: 交易对
            target_time: 目标时间
            bar_size: K线周期
            tolerance_minutes: 时间容差（分钟）
            
        Returns:
            K线数据字典，如果没有找到则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 计算时间范围
            start_time = (target_time - timedelta(minutes=tolerance_minutes)).isoformat()
            end_time = (target_time + timedelta(minutes=tolerance_minutes)).isoformat()
            
            query = '''
                SELECT timestamp, open_price, high_price, low_price, close_price, volume, amount
                FROM historical_klines
                WHERE instrument = ? AND bar_size = ?
                AND timestamp >= ? AND timestamp <= ?
                ORDER BY ABS(julianday(timestamp) - julianday(?)) ASC
                LIMIT 1
            '''
            
            cursor = conn.cursor()
            cursor.execute(query, (instrument, bar_size, start_time, end_time, target_time.isoformat()))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'timestamp': result[0],
                    'open': result[1],
                    'high': result[2],
                    'low': result[3],
                    'close': result[4],
                    'volume': result[5],
                    'amount': result[6]
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"获取历史K线数据失败: {e}")
            return None
    
    def _get_bar_minutes(self, bar_size: str) -> int:
        """获取K线周期对应的分钟数"""
        bar_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1H': 60, '2H': 120, '4H': 240, '6H': 360, '12H': 720,
            '1D': 1440, '1W': 10080, '1M': 43200
        }
        return bar_map.get(bar_size, 1)
    
    def cleanup_old_data(self, days: int = 30):
        """
        清理旧的K线数据
        
        Args:
            days: 保留多少天的数据
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
            
            cursor.execute('''
                DELETE FROM historical_klines 
                WHERE timestamp < ?
            ''', (cutoff_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            self.logger.info(f"清理了 {deleted_count} 条过期K线数据")
            
        except Exception as e:
            self.logger.error(f"清理旧K线数据失败: {e}")
