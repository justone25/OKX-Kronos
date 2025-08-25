"""
OKX数据获取模块
"""
from okx.api import Market
import pandas as pd
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from ..utils.config import OKXConfig

class OKXDataFetcher:
    """OKX数据获取器"""

    def __init__(self, config: OKXConfig):
        self.config = config
        self.market_api = Market(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag='0'  # 0: 实盘, 1: 模拟盘
        )
        self.logger = logging.getLogger(__name__)

    def test_connection(self) -> bool:
        """测试API连接"""
        try:
            # 获取一条测试数据
            response = self.market_api.get_candles(
                instId='BTC-USDT-SWAP',
                bar='5m',
                limit='1'
            )

            if response['code'] == '0':
                self.logger.info("✅ OKX API连接成功")
                return True
            else:
                self.logger.error(f"❌ OKX API连接失败: {response['msg']}")
                return False

        except Exception as e:
            self.logger.error(f"❌ OKX API连接异常: {e}")
            return False

    def get_historical_klines(self, instrument: str, bar: str,
                            start_time: str = None, end_time: str = None,
                            limit: int = 300) -> pd.DataFrame:
        """获取历史K线数据"""
        try:
            params = {
                'instId': instrument,
                'bar': bar,
                'limit': str(limit)
            }

            if start_time:
                params['after'] = str(int(pd.Timestamp(start_time).timestamp() * 1000))
            if end_time:
                params['before'] = str(int(pd.Timestamp(end_time).timestamp() * 1000))

            response = self.market_api.get_candles(**params)

            if response['code'] == '0':
                data = response['data']
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close',
                    'volume', 'amount', 'volCcyQuote', 'confirm'
                ])

                # 数据类型转换
                df['timestamps'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
                # 转换为北京时间 (UTC+8)
                df['timestamps'] = df['timestamps'].dt.tz_convert('Asia/Shanghai')
                for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                    df[col] = df[col].astype(float)

                # 按时间排序（OKX返回的是倒序）
                df = df.sort_values('timestamps').reset_index(drop=True)

                return df[['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']]
            else:
                raise Exception(f"API Error: {response['msg']}")

        except Exception as e:
            self.logger.error(f"Failed to fetch historical data: {e}")
            raise

    def get_multiple_periods_data(self, instrument: str, bar: str, days: int) -> pd.DataFrame:
        """获取多个周期的历史数据"""
        all_data = []
        end_time = datetime.now()

        # 计算需要的请求次数
        bar_minutes = self._get_bar_minutes(bar)
        total_bars = (days * 24 * 60) // bar_minutes
        requests_needed = (total_bars + 299) // 300  # 向上取整

        self.logger.info(f"需要获取 {days} 天的数据，预计需要 {requests_needed} 次API请求")

        for i in range(requests_needed):
            start_time = end_time - timedelta(minutes=300 * bar_minutes)

            try:
                df_chunk = self.get_historical_klines(
                    instrument=instrument,
                    bar=bar,
                    start_time=start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    end_time=end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    limit=300
                )

                if not df_chunk.empty:
                    all_data.append(df_chunk)
                    end_time = df_chunk['timestamps'].min() - timedelta(minutes=bar_minutes)
                    self.logger.info(f"✅ 已获取数据块 {i+1}/{requests_needed}")

                # API限制：每秒最多10次请求
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"❌ 获取数据块 {i+1} 失败: {e}")
                break

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            final_df = final_df.sort_values('timestamps').reset_index(drop=True)
            final_df = final_df.drop_duplicates(subset=['timestamps']).reset_index(drop=True)
            self.logger.info(f"✅ 总共获取到 {len(final_df)} 条历史数据")
            return final_df
        else:
            self.logger.warning("❌ 未获取到任何历史数据")
            return pd.DataFrame()

    def _get_bar_minutes(self, bar: str) -> int:
        """获取K线周期对应的分钟数"""
        bar_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1H': 60, '2H': 120, '4H': 240, '6H': 360, '12H': 720, '1D': 1440
        }
        return bar_map.get(bar, 5)
