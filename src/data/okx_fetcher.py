"""
OKX数据获取模块
"""
from okx.api import Market
import pandas as pd
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from ..utils.config import OKXConfig
from .data_quality_checker import DataQualityChecker, DataQualityReport
from .api_retry_handler import APIRetryHandler, RetryConfig, retry_on_api_error

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

        # 初始化数据质量检查器和重试处理器
        self.quality_checker = DataQualityChecker()
        self.retry_handler = APIRetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0
        ))

        # 数据缓存
        self._price_cache = {}
        self._kline_cache = {}
        self._cache_ttl = 30  # 缓存30秒

    @retry_on_api_error(max_attempts=3, base_delay=1.0)
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
                error_msg = f"OKX API连接失败: {response['msg']}"
                self.logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)

        except Exception as e:
            self.logger.error(f"❌ OKX API连接异常: {e}")
            raise e

    def get_historical_klines(self, instrument: str, bar: str,
                            start_time: str = None, end_time: str = None,
                            limit: int = 300, validate_quality: bool = True) -> pd.DataFrame:
        """
        获取历史K线数据（增强版）

        Args:
            instrument: 交易对
            bar: K线周期
            start_time: 开始时间
            end_time: 结束时间
            limit: 数据条数限制
            validate_quality: 是否验证数据质量

        Returns:
            K线数据DataFrame
        """
        # 检查缓存
        cache_key = f"{instrument}_{bar}_{start_time}_{end_time}_{limit}"
        if cache_key in self._kline_cache:
            cache_data, cache_time = self._kline_cache[cache_key]
            if time.time() - cache_time < self._cache_ttl:
                self.logger.debug(f"使用缓存的K线数据: {instrument}")
                return cache_data

        # 使用重试机制获取数据
        return self._fetch_klines_with_retry(
            instrument, bar, start_time, end_time, limit, validate_quality, cache_key
        )

    @retry_on_api_error(max_attempts=3, base_delay=2.0)
    def _fetch_klines_with_retry(self, instrument: str, bar: str, start_time: str,
                               end_time: str, limit: int, validate_quality: bool,
                               cache_key: str) -> pd.DataFrame:
        """带重试的K线数据获取"""
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

            self.logger.debug(f"获取K线数据: {instrument} {bar} limit={limit}")
            response = self.market_api.get_candles(**params)

            if response['code'] == '0':
                raw_data = response['data']

                # 数据质量检查
                if validate_quality and raw_data:
                    quality_report = self.quality_checker.validate_kline_data(raw_data)
                    self.quality_checker.log_quality_report(quality_report, instrument)

                    if not quality_report.is_valid:
                        self.logger.warning(f"K线数据质量不合格: {instrument}, 分数: {quality_report.quality_score:.1f}")
                        # 如果数据质量太差，抛出异常触发重试
                        if quality_report.quality_score < 30.0:
                            raise Exception(f"数据质量过低: {quality_report.quality_score:.1f}/100")

                # 转换为DataFrame
                df = pd.DataFrame(raw_data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close',
                    'volume', 'amount', 'volCcyQuote', 'confirm'
                ])

                if df.empty:
                    self.logger.warning(f"获取到空数据: {instrument}")
                    return pd.DataFrame()

                # 数据类型转换
                df['timestamps'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True)
                # 转换为北京时间 (UTC+8)
                df['timestamps'] = df['timestamps'].dt.tz_convert('Asia/Shanghai')
                for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                    df[col] = df[col].astype(float)

                # 按时间排序（OKX返回的是倒序）
                df = df.sort_values('timestamps').reset_index(drop=True)

                result_df = df[['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']]

                # 缓存结果
                self._kline_cache[cache_key] = (result_df.copy(), time.time())

                self.logger.debug(f"成功获取K线数据: {instrument}, {len(result_df)}条记录")
                return result_df
            else:
                error_msg = f"OKX API错误: {response['msg']}"
                self.logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            self.logger.error(f"获取历史数据失败: {e}")
            raise

    @retry_on_api_error(max_attempts=3, base_delay=0.5)
    def get_current_price(self, instrument: str, validate_quality: bool = True) -> float:
        """
        获取当前价格（增强版）

        Args:
            instrument: 交易对
            validate_quality: 是否验证价格质量

        Returns:
            当前价格
        """
        # 检查缓存
        cache_key = f"price_{instrument}"
        if cache_key in self._price_cache:
            price, cache_time = self._price_cache[cache_key]
            if time.time() - cache_time < 5:  # 价格缓存5秒
                return price

        try:
            response = self.market_api.get_ticker(instId=instrument)

            if response['code'] == '0' and response['data']:
                ticker_data = response['data'][0]
                current_price = float(ticker_data['last'])

                # 数据质量检查
                if validate_quality:
                    if not self.quality_checker.validate_price_data(current_price, instrument):
                        raise Exception(f"价格数据质量检查失败: {current_price}")

                # 缓存价格
                self._price_cache[cache_key] = (current_price, time.time())

                self.logger.debug(f"获取当前价格: {instrument} = ${current_price:,.2f}")
                return current_price
            else:
                error_msg = f"获取价格失败: {response.get('msg', '未知错误')}"
                self.logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            self.logger.error(f"获取当前价格异常: {instrument} - {e}")
            raise

    def get_current_price_with_fallback(self, instrument: str) -> Optional[float]:
        """
        获取当前价格（带备用方案）

        Args:
            instrument: 交易对

        Returns:
            当前价格，失败时返回None
        """
        try:
            # 主要方案：获取ticker价格
            price = self.get_current_price(instrument, validate_quality=True)
            self.logger.debug(f"[{instrument}] 主要方案获取价格成功: ${price:,.8f}")
            return price
        except Exception as e:
            self.logger.warning(f"[{instrument}] 主要价格获取失败: {e}")

            try:
                # 备用方案：从最新K线获取价格
                self.logger.info(f"[{instrument}] 尝试从K线数据获取价格")
                df = self.get_historical_klines(instrument, '1m', limit=1, validate_quality=False)
                if not df.empty:
                    fallback_price = float(df.iloc[-1]['close'])
                    self.logger.info(f"[{instrument}] 备用方案获取价格成功: ${fallback_price:,.8f}")
                    return fallback_price
                else:
                    self.logger.error(f"[{instrument}] K线数据为空")
            except Exception as fallback_error:
                self.logger.error(f"[{instrument}] 备用价格获取也失败: {fallback_error}")

            self.logger.error(f"[{instrument}] 所有价格获取方案都失败")
            return None

    def clear_cache(self):
        """清空缓存"""
        self._price_cache.clear()
        self._kline_cache.clear()
        self.logger.info("数据缓存已清空")

    def get_cache_statistics(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        return {
            'price_cache_size': len(self._price_cache),
            'kline_cache_size': len(self._kline_cache),
            'cache_ttl': self._cache_ttl
        }

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
