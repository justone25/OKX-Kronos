#!/usr/bin/env python3
"""
市场扫描器 - 获取和管理交易对列表
"""
import logging
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from okx.api import Market
from ..utils.config import OKXConfig

@dataclass
class TradingPair:
    """交易对信息"""
    symbol: str
    volume_24h: float
    price: float
    price_change_24h: float
    market_cap_rank: int = 0
    is_active: bool = True

class MarketScanner:
    """市场扫描器 - 获取前N个交易对"""
    
    def __init__(self, config: OKXConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.market_api = Market()
        
        # 缓存
        self._top_pairs_cache = None
        self._cache_time = 0
        self._cache_ttl = 300  # 5分钟缓存
        
    def get_top_trading_pairs(self, count: int = 24, inst_type: str = "SWAP") -> List[TradingPair]:
        """
        获取前N个交易对（按24小时交易量排序）
        
        Args:
            count: 返回的交易对数量
            inst_type: 产品类型 (SWAP, SPOT等)
            
        Returns:
            交易对列表
        """
        # 检查缓存
        if (self._top_pairs_cache and 
            time.time() - self._cache_time < self._cache_ttl and
            len(self._top_pairs_cache) >= count):
            self.logger.debug(f"使用缓存的交易对数据")
            return self._top_pairs_cache[:count]
        
        try:
            self.logger.info(f"获取前{count}个{inst_type}交易对...")
            
            # 获取所有交易对的ticker数据
            tickers = self._get_all_tickers(inst_type)
            
            if not tickers:
                self.logger.error("未获取到任何ticker数据")
                return []
            
            # 过滤和排序
            trading_pairs = self._process_tickers(tickers, inst_type)
            
            # 按24小时交易量排序
            trading_pairs.sort(key=lambda x: x.volume_24h, reverse=True)
            
            # 缓存结果
            self._top_pairs_cache = trading_pairs
            self._cache_time = time.time()
            
            self.logger.info(f"✅ 成功获取{len(trading_pairs)}个交易对，返回前{count}个")
            
            # 记录前几个交易对信息
            for i, pair in enumerate(trading_pairs[:min(5, count)], 1):
                self.logger.info(f"   {i}. {pair.symbol}: 24h成交量 ${pair.volume_24h:,.0f}")
            
            return trading_pairs[:count]
            
        except Exception as e:
            self.logger.error(f"获取交易对失败: {e}")
            return []
    
    def _get_all_tickers(self, inst_type: str) -> List[Dict]:
        """获取所有ticker数据"""
        try:
            # 直接获取所有ticker数据
            response = self.market_api.get_tickers(instType=inst_type)

            if response.get('code') == '0':
                tickers = response.get('data', [])
                self.logger.info(f"成功获取{len(tickers)}个{inst_type}交易对的ticker数据")
                return tickers
            else:
                self.logger.error(f"获取ticker失败: {response.get('msg')}")
                return []

        except Exception as e:
            self.logger.error(f"获取ticker异常: {e}")
            return []
    
    def _process_tickers(self, tickers: List[Dict], inst_type: str) -> List[TradingPair]:
        """处理ticker数据"""
        trading_pairs = []
        
        for ticker in tickers:
            try:
                symbol = ticker.get('instId', '')
                
                # 过滤条件
                if not self._should_include_pair(symbol, ticker, inst_type):
                    continue
                
                # 创建交易对对象
                pair = TradingPair(
                    symbol=symbol,
                    volume_24h=float(ticker.get('volCcy24h', 0)),  # 24小时成交额
                    price=float(ticker.get('last', 0)),
                    price_change_24h=float(ticker.get('sodUtc8', 0))  # 24小时涨跌幅
                )
                
                trading_pairs.append(pair)
                
            except (ValueError, TypeError) as e:
                self.logger.debug(f"跳过无效ticker数据: {ticker.get('instId', 'unknown')} - {e}")
                continue
        
        return trading_pairs
    
    def _should_include_pair(self, symbol: str, ticker: Dict, inst_type: str) -> bool:
        """判断是否应该包含该交易对"""
        try:
            # 基本过滤条件
            if not symbol:
                return False
            
            # 只要USDT永续合约
            if inst_type == "SWAP" and not symbol.endswith("-USDT-SWAP"):
                return False
            
            # 检查交易量
            volume_24h = float(ticker.get('volCcy24h', 0))
            if volume_24h < 1000000:  # 24小时成交额至少100万USDT
                return False
            
            # 检查价格
            price = float(ticker.get('last', 0))
            if price <= 0:
                return False
            
            # 排除一些特殊的交易对
            excluded_patterns = ['TEST', 'DEMO', '1000']
            if any(pattern in symbol for pattern in excluded_patterns):
                return False
            
            return True
            
        except (ValueError, TypeError):
            return False
    
    def get_pair_details(self, symbol: str) -> Optional[Dict]:
        """获取单个交易对的详细信息"""
        try:
            response = self.market_api.get_ticker(instId=symbol)

            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                self.logger.error(f"获取{symbol}详情失败: {response.get('msg')}")
                return None

        except Exception as e:
            self.logger.error(f"获取{symbol}详情异常: {e}")
            return None
    
    def validate_trading_pairs(self, pairs: List[TradingPair]) -> List[TradingPair]:
        """验证交易对是否仍然有效"""
        valid_pairs = []
        
        for pair in pairs:
            try:
                details = self.get_pair_details(pair.symbol)
                if details:
                    # 更新数据
                    pair.volume_24h = float(details.get('volCcy24h', 0))
                    pair.price = float(details.get('last', 0))
                    pair.price_change_24h = float(details.get('sodUtc8', 0))
                    
                    # 检查是否仍然满足条件
                    if pair.volume_24h >= 1000000:  # 至少100万USDT成交额
                        valid_pairs.append(pair)
                    else:
                        self.logger.info(f"移除低流动性交易对: {pair.symbol}")
                else:
                    self.logger.warning(f"无法验证交易对: {pair.symbol}")
                    
            except Exception as e:
                self.logger.error(f"验证交易对{pair.symbol}失败: {e}")
        
        return valid_pairs
    
    def clear_cache(self):
        """清空缓存"""
        self._top_pairs_cache = None
        self._cache_time = 0
        self.logger.info("市场扫描器缓存已清空")
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        return {
            'cached_pairs': len(self._top_pairs_cache) if self._top_pairs_cache else 0,
            'cache_age': time.time() - self._cache_time if self._cache_time > 0 else 0,
            'cache_ttl': self._cache_ttl
        }
