"""
预测服务模块
整合OKX数据获取和Kronos预测功能
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns
import platform

# 配置matplotlib使用默认字体，避免中文字体问题
matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

from ..data.okx_fetcher import OKXDataFetcher
from ..models.kronos_model import KronosPredictor
from ..utils.config import OKXConfig, TradingConfig


class PredictionService:
    """预测服务类，整合数据获取和预测功能"""
    
    def __init__(self, okx_config: OKXConfig, trading_config: TradingConfig, device: str = "cpu"):
        """
        初始化预测服务
        
        Args:
            okx_config: OKX API配置
            trading_config: 交易配置
            device: 计算设备
        """
        self.logger = logging.getLogger(__name__)
        self.okx_config = okx_config
        self.trading_config = trading_config
        self.device = device
        
        # 初始化数据获取器
        self.data_fetcher = OKXDataFetcher(okx_config)
        
        # 初始化Kronos预测器
        self.predictor = KronosPredictor(device=device)
        
        self.logger.info("✅ 预测服务初始化完成")
    
    def get_prediction(self, lookback_hours: int = 24, pred_hours: int = 6,
                      temperature: float = 1.0, top_p: float = 0.9,
                      sample_count: int = 1, seed: Optional[int] = None,
                      deterministic: bool = False) -> Dict[str, Any]:
        """
        获取价格预测
        
        Args:
            lookback_hours: 历史数据回看小时数
            pred_hours: 预测小时数
            temperature: 采样温度
            top_p: nucleus采样参数
            sample_count: 采样次数
            
        Returns:
            包含预测结果的字典
        """
        try:
            self.logger.info(f"开始获取预测，回看{lookback_hours}小时，预测{pred_hours}小时")
            
            # 1. 获取历史数据
            historical_data = self._get_historical_data(lookback_hours)
            if historical_data.empty:
                raise ValueError("无法获取历史数据")
            
            # 2. 准备预测时间戳
            last_time = historical_data['timestamps'].iloc[-1]
            pred_timestamps = self._generate_prediction_timestamps(last_time, pred_hours)
            
            # 3. 进行预测
            prediction_df = self.predictor.predict(
                df=historical_data[['open', 'high', 'low', 'close', 'volume', 'amount']],
                x_timestamp=historical_data['timestamps'],
                y_timestamp=pred_timestamps,
                pred_len=len(pred_timestamps),
                temperature=temperature,
                top_p=top_p,
                sample_count=sample_count,
                verbose=True,
                seed=seed,
                deterministic=deterministic
            )
            
            # 4. 计算预测统计信息
            stats = self._calculate_prediction_stats(historical_data, prediction_df)
            
            # 5. 生成预测报告
            report = {
                'timestamp': datetime.now(),
                'instrument': self.trading_config.instrument,
                'lookback_hours': lookback_hours,
                'pred_hours': pred_hours,
                'historical_data': historical_data,
                'prediction_data': prediction_df,
                'statistics': stats,
                'parameters': {
                    'temperature': temperature,
                    'top_p': top_p,
                    'sample_count': sample_count
                }
            }
            
            self.logger.info("✅ 预测完成")
            return report
            
        except Exception as e:
            self.logger.error(f"❌ 预测失败: {e}")
            raise
    
    def _get_historical_data(self, hours: int) -> pd.DataFrame:
        """获取历史数据"""
        try:
            # 计算需要的K线数量（5分钟K线）
            bars_needed = hours * 12  # 每小时12根5分钟K线
            
            # 获取历史数据
            df = self.data_fetcher.get_historical_klines(
                instrument=self.trading_config.instrument,
                bar=self.trading_config.bar_size,
                limit=min(bars_needed, 300)  # OKX API限制
            )
            
            self.logger.info(f"获取到 {len(df)} 条历史数据")
            return df
            
        except Exception as e:
            self.logger.error(f"获取历史数据失败: {e}")
            raise
    
    def _generate_prediction_timestamps(self, last_time: pd.Timestamp, hours: int) -> pd.Series:
        """生成预测时间戳"""
        # 根据bar_size计算时间间隔
        if self.trading_config.bar_size == '5m':
            interval = timedelta(minutes=5)
        elif self.trading_config.bar_size == '1H':
            interval = timedelta(hours=1)
        else:
            # 默认5分钟
            interval = timedelta(minutes=5)
        
        # 生成预测时间戳
        timestamps = []
        current_time = last_time + interval
        
        bars_needed = hours * 12 if self.trading_config.bar_size == '5m' else hours
        
        for i in range(bars_needed):
            timestamps.append(current_time)
            current_time += interval
        
        return pd.Series(timestamps)
    
    def _calculate_prediction_stats(self, historical_df: pd.DataFrame, 
                                  prediction_df: pd.DataFrame) -> Dict[str, Any]:
        """计算预测统计信息"""
        try:
            current_price = historical_df['close'].iloc[-1]
            pred_prices = prediction_df['close']
            
            stats = {
                'current_price': float(current_price),
                'predicted_price_start': float(pred_prices.iloc[0]),
                'predicted_price_end': float(pred_prices.iloc[-1]),
                'predicted_high': float(pred_prices.max()),
                'predicted_low': float(pred_prices.min()),
                'price_change': float(pred_prices.iloc[-1] - current_price),
                'price_change_pct': float((pred_prices.iloc[-1] - current_price) / current_price * 100),
                'volatility': float(pred_prices.std()),
                'trend_direction': 'up' if pred_prices.iloc[-1] > current_price else 'down'
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"计算统计信息失败: {e}")
            return {}
    
    def visualize_prediction(self, report: Dict[str, Any], save_path: str = None) -> None:
        """可视化预测结果"""
        try:
            historical_df = report['historical_data']
            prediction_df = report['prediction_data']

            # 使用英文标签避免字体问题
            labels = {
                'historical_price': 'Historical Price',
                'predicted_price': 'Predicted Price',
                'price_label': 'Price (USDT)',
                'title': f'{report["instrument"]} Price Prediction',
                'historical_volume': 'Historical Volume',
                'predicted_volume': 'Predicted Volume',
                'volume_label': 'Volume',
                'time_label': 'Time'
            }

            # 创建图表
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

            # 绘制价格预测
            ax1.plot(historical_df['timestamps'], historical_df['close'],
                    label=labels['historical_price'], color='blue', linewidth=2)
            ax1.plot(prediction_df.index, prediction_df['close'],
                    label=labels['predicted_price'], color='red', linewidth=2, linestyle='--')

            ax1.set_ylabel(labels['price_label'], fontsize=12)
            ax1.set_title(labels['title'], fontsize=14, fontweight='bold')
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # 绘制成交量
            ax2.bar(historical_df['timestamps'], historical_df['volume'],
                   label=labels['historical_volume'], color='blue', alpha=0.6, width=0.001)
            ax2.bar(prediction_df.index, prediction_df['volume'],
                   label=labels['predicted_volume'], color='red', alpha=0.6, width=0.001)

            ax2.set_ylabel(labels['volume_label'], fontsize=12)
            ax2.set_xlabel(labels['time_label'], fontsize=12)
            ax2.legend()
            ax2.grid(True, alpha=0.3)

            # 添加统计信息（使用英文避免字体问题）
            stats = report['statistics']
            info_text = f"""Current Price: ${stats.get('current_price', 0):,.2f}
Predicted Price: ${stats.get('predicted_price_end', 0):,.2f}
Price Change: {stats.get('price_change_pct', 0):+.2f}%
Trend: {stats.get('trend_direction', 'unknown').upper()}"""

            ax1.text(0.02, 0.98, info_text, transform=ax1.transAxes,
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                self.logger.info(f"预测图表已保存到: {save_path}")

            plt.show()

        except Exception as e:
            self.logger.error(f"可视化失败: {e}")
    
    def print_prediction_report(self, report: Dict[str, Any]) -> None:
        """打印预测报告"""
        try:
            print("\n" + "="*60)
            print("🔮 KRONOS BTC-USDT 永续合约预测报告")
            print("="*60)
            
            stats = report['statistics']
            
            print(f"📊 交易对: {report['instrument']}")
            print(f"⏰ 预测时间: {report['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📈 回看时长: {report['lookback_hours']} 小时")
            print(f"🔮 预测时长: {report['pred_hours']} 小时")
            
            print(f"\n💰 价格信息:")
            print(f"   当前价格: ${stats.get('current_price', 0):,.2f}")
            print(f"   预测价格: ${stats.get('predicted_price_end', 0):,.2f}")
            print(f"   价格变化: {stats.get('price_change', 0):+.2f} USDT ({stats.get('price_change_pct', 0):+.2f}%)")
            print(f"   预测最高: ${stats.get('predicted_high', 0):,.2f}")
            print(f"   预测最低: ${stats.get('predicted_low', 0):,.2f}")
            
            print(f"\n📊 技术指标:")
            print(f"   波动率: {stats.get('volatility', 0):.2f}")
            print(f"   趋势方向: {stats.get('trend_direction', 'unknown').upper()}")
            
            print(f"\n⚙️ 模型参数:")
            params = report['parameters']
            print(f"   温度参数: {params.get('temperature', 0)}")
            print(f"   Top-p: {params.get('top_p', 0)}")
            print(f"   采样次数: {params.get('sample_count', 0)}")
            
            print("="*60)
            
        except Exception as e:
            self.logger.error(f"打印报告失败: {e}")


def create_prediction_service(okx_config: OKXConfig, trading_config: TradingConfig, 
                            device: str = "cpu") -> PredictionService:
    """创建预测服务实例"""
    return PredictionService(okx_config, trading_config, device)
