#!/usr/bin/env python3
"""
交易信号通用定义
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradingSignal:
    """交易信号"""
    signal_type: SignalType
    strength: float  # 0-1
    confidence: float  # 0-1
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
