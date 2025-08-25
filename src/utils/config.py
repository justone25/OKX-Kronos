"""
配置管理模块
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('config/.env')

@dataclass
class OKXConfig:
    """OKX API配置"""
    api_key: str = os.getenv('OKX_API_KEY', '')
    secret_key: str = os.getenv('OKX_SECRET_KEY', '')
    passphrase: str = os.getenv('OKX_PASSPHRASE', '')
    base_url: str = "https://www.okx.com"
    ws_public_url: str = "wss://ws.okx.com:8443/ws/v5/public"

@dataclass
class TradingConfig:
    """交易配置"""
    instrument: str = os.getenv('INSTRUMENT', 'BTC-USDT-SWAP')
    bar_size: str = os.getenv('BAR_SIZE', '5m')
    lookback_days: int = int(os.getenv('LOOKBACK_DAYS', '15'))
    pred_length: int = int(os.getenv('PRED_LENGTH', '48'))
    max_context: int = int(os.getenv('MAX_CONTEXT', '512'))
    temperature: float = float(os.getenv('TEMPERATURE', '1.0'))
    top_p: float = float(os.getenv('TOP_P', '0.9'))
    sample_count: int = int(os.getenv('SAMPLE_COUNT', '3'))

@dataclass
class SystemConfig:
    """系统配置"""
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    database_path: str = os.getenv('DATABASE_PATH', './data/okx_btc_data.db')
    models_dir: str = './models'
