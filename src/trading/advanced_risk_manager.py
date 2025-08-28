#!/usr/bin/env python3
"""
高级风险管理器
解决双重止损冲突、移动止损、分批止盈等问题
"""
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from .trade_executor import PositionInfo
from ..common.signals import TradingSignal, SignalType

class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

class StopLossType(Enum):
    """止损类型"""
    FIXED = "fixed"           # 固定止损
    TRAILING = "trailing"     # 移动止损
    ATR_BASED = "atr_based"   # ATR基础止损
    VOLATILITY = "volatility" # 波动率止损

class TakeProfitMode(Enum):
    """止盈模式"""
    SINGLE = "single"         # 单次止盈
    PARTIAL = "partial"       # 分批止盈
    TRAILING = "trailing"     # 移动止盈
    LADDER = "ladder"         # 阶梯止盈

@dataclass
class RiskMetrics:
    """风险指标"""
    position_risk: float = 0.0      # 持仓风险
    portfolio_risk: float = 0.0     # 组合风险
    var_1d: float = 0.0            # 1日VaR
    max_drawdown: float = 0.0       # 最大回撤
    sharpe_ratio: float = 0.0       # 夏普比率
    risk_level: RiskLevel = RiskLevel.LOW

@dataclass
class StopLossConfig:
    """止损配置"""
    type: StopLossType = StopLossType.FIXED
    initial_pct: float = 0.02       # 初始止损比例
    trailing_distance: float = 0.01  # 移动止损距离
    atr_multiplier: float = 2.0     # ATR倍数
    min_profit_for_trail: float = 0.005  # 开始移动止损的最小盈利

@dataclass
class TakeProfitConfig:
    """止盈配置"""
    mode: TakeProfitMode = TakeProfitMode.PARTIAL
    targets: List[Tuple[float, float]] = None  # [(价格比例, 平仓比例)]
    trailing_distance: float = 0.01   # 移动止盈距离
    
    def __post_init__(self):
        if self.targets is None:
            # 默认分批止盈配置
            self.targets = [
                (0.01, 0.3),   # 1%盈利时平30%
                (0.02, 0.5),   # 2%盈利时平50%
                (0.03, 1.0)    # 3%盈利时全平
            ]

@dataclass
class PositionRisk:
    """持仓风险管理"""
    position_id: str
    entry_price: float
    current_price: float
    size: float
    side: str
    stop_loss_price: float = 0.0
    take_profit_targets: List[Tuple[float, float]] = None
    trailing_stop: float = 0.0
    highest_price: float = 0.0  # 最高价（多头）
    lowest_price: float = 0.0   # 最低价（空头）
    partial_profits_taken: float = 0.0  # 已止盈数量
    last_update: datetime = None
    
    def __post_init__(self):
        if self.last_update is None:
            self.last_update = datetime.now()
        if self.take_profit_targets is None:
            self.take_profit_targets = []
        if self.side == "long":
            self.highest_price = max(self.entry_price, self.current_price)
        else:
            self.lowest_price = min(self.entry_price, self.current_price)

class AdvancedRiskManager:
    """高级风险管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 配置
        self.stop_loss_config = StopLossConfig()
        self.take_profit_config = TakeProfitConfig()
        
        # 风险限制
        self.max_position_risk = 0.02    # 单仓位最大风险2%
        self.max_portfolio_risk = 0.05   # 组合最大风险5%
        self.max_daily_loss = 0.03       # 日最大亏损3%
        self.max_correlation = 0.7       # 最大相关性
        
        # 持仓风险跟踪
        self.position_risks: Dict[str, PositionRisk] = {}
        self.daily_pnl = 0.0
        self.daily_trades = 0
        
        # 市场状态
        self.market_volatility = 0.02    # 市场波动率
        self.current_risk_level = RiskLevel.LOW
        
        # 统计信息
        self.stats = {
            'total_positions': 0,
            'stop_losses_triggered': 0,
            'take_profits_triggered': 0,
            'trailing_stops_activated': 0,
            'risk_limits_hit': 0,
            'emergency_exits': 0
        }
    
    def assess_position_risk(self, position: PositionInfo, signal: TradingSignal) -> RiskMetrics:
        """评估持仓风险"""
        # 计算持仓风险
        position_value = abs(position.size * position.avg_price)
        unrealized_pnl_pct = position.unrealized_pnl / position.margin if position.margin > 0 else 0
        
        # 计算VaR（简化版）
        var_1d = position_value * self.market_volatility * 2.33  # 99%置信度
        
        # 评估风险等级
        risk_level = self._calculate_risk_level(unrealized_pnl_pct, position_value)
        
        return RiskMetrics(
            position_risk=abs(unrealized_pnl_pct),
            portfolio_risk=self._calculate_portfolio_risk(),
            var_1d=var_1d,
            max_drawdown=self._calculate_max_drawdown(),
            risk_level=risk_level
        )
    
    def create_position_risk(self, position: PositionInfo, signal: TradingSignal) -> PositionRisk:
        """创建持仓风险管理"""
        position_id = f"{position.inst_id}_{position.side}_{int(time.time())}"
        
        # 计算初始止损价格
        stop_loss_price = self._calculate_initial_stop_loss(
            position.avg_price, position.side, signal
        )
        
        # 设置止盈目标
        take_profit_targets = self._calculate_take_profit_targets(
            position.avg_price, position.side
        )
        
        position_risk = PositionRisk(
            position_id=position_id,
            entry_price=position.avg_price,
            current_price=position.mark_price,
            size=position.size,
            side=position.side,
            stop_loss_price=stop_loss_price,
            take_profit_targets=take_profit_targets
        )
        
        self.position_risks[position_id] = position_risk
        self.stats['total_positions'] += 1
        
        self.logger.info(f"创建持仓风险管理: {position_id}")
        self.logger.info(f"  止损价格: ${stop_loss_price:,.2f}")
        self.logger.info(f"  止盈目标: {len(take_profit_targets)}个")
        
        return position_risk
    
    def update_position_risk(self, position_id: str, current_price: float) -> List[str]:
        """
        更新持仓风险管理
        
        Returns:
            需要执行的操作列表
        """
        if position_id not in self.position_risks:
            return []
        
        position_risk = self.position_risks[position_id]
        position_risk.current_price = current_price
        position_risk.last_update = datetime.now()
        
        actions = []
        
        # 更新最高/最低价
        if position_risk.side == "long":
            if current_price > position_risk.highest_price:
                position_risk.highest_price = current_price
                # 检查是否需要更新移动止损
                if self.stop_loss_config.type == StopLossType.TRAILING:
                    new_stop = self._update_trailing_stop_loss(position_risk)
                    if new_stop:
                        actions.append(f"update_stop_loss:{new_stop}")
        else:
            if current_price < position_risk.lowest_price:
                position_risk.lowest_price = current_price
                if self.stop_loss_config.type == StopLossType.TRAILING:
                    new_stop = self._update_trailing_stop_loss(position_risk)
                    if new_stop:
                        actions.append(f"update_stop_loss:{new_stop}")
        
        # 检查止损触发
        if self._should_trigger_stop_loss(position_risk):
            actions.append("trigger_stop_loss")
            self.stats['stop_losses_triggered'] += 1
        
        # 检查分批止盈
        profit_actions = self._check_partial_take_profits(position_risk)
        actions.extend(profit_actions)
        
        # 检查紧急风险
        if self._check_emergency_risk(position_risk):
            actions.append("emergency_exit")
            self.stats['emergency_exits'] += 1
        
        return actions
    
    def _calculate_initial_stop_loss(self, entry_price: float, side: str, signal: TradingSignal) -> float:
        """计算初始止损价格"""
        if self.stop_loss_config.type == StopLossType.FIXED:
            if side == "long":
                return entry_price * (1 - self.stop_loss_config.initial_pct)
            else:
                return entry_price * (1 + self.stop_loss_config.initial_pct)
        
        elif self.stop_loss_config.type == StopLossType.ATR_BASED:
            # 简化的ATR计算（实际应该使用历史数据）
            atr = entry_price * 0.01  # 假设ATR为价格的1%
            if side == "long":
                return entry_price - (atr * self.stop_loss_config.atr_multiplier)
            else:
                return entry_price + (atr * self.stop_loss_config.atr_multiplier)
        
        # 默认固定止损
        if side == "long":
            return entry_price * (1 - self.stop_loss_config.initial_pct)
        else:
            return entry_price * (1 + self.stop_loss_config.initial_pct)
    
    def _calculate_take_profit_targets(self, entry_price: float, side: str) -> List[Tuple[float, float]]:
        """计算止盈目标"""
        targets = []
        
        for profit_pct, close_pct in self.take_profit_config.targets:
            if side == "long":
                target_price = entry_price * (1 + profit_pct)
            else:
                target_price = entry_price * (1 - profit_pct)
            
            targets.append((target_price, close_pct))
        
        return targets
    
    def _update_trailing_stop_loss(self, position_risk: PositionRisk) -> Optional[float]:
        """更新移动止损"""
        current_price = position_risk.current_price
        entry_price = position_risk.entry_price
        
        # 检查是否达到开始移动止损的条件
        if position_risk.side == "long":
            profit_pct = (current_price - entry_price) / entry_price
            if profit_pct >= self.stop_loss_config.min_profit_for_trail:
                new_stop = current_price * (1 - self.stop_loss_config.trailing_distance)
                if new_stop > position_risk.stop_loss_price:
                    position_risk.stop_loss_price = new_stop
                    self.stats['trailing_stops_activated'] += 1
                    return new_stop
        else:
            profit_pct = (entry_price - current_price) / entry_price
            if profit_pct >= self.stop_loss_config.min_profit_for_trail:
                new_stop = current_price * (1 + self.stop_loss_config.trailing_distance)
                if new_stop < position_risk.stop_loss_price:
                    position_risk.stop_loss_price = new_stop
                    self.stats['trailing_stops_activated'] += 1
                    return new_stop
        
        return None
    
    def _should_trigger_stop_loss(self, position_risk: PositionRisk) -> bool:
        """检查是否应该触发止损"""
        current_price = position_risk.current_price
        stop_loss_price = position_risk.stop_loss_price
        
        if position_risk.side == "long":
            return current_price <= stop_loss_price
        else:
            return current_price >= stop_loss_price
    
    def _check_partial_take_profits(self, position_risk: PositionRisk) -> List[str]:
        """检查分批止盈"""
        actions = []
        current_price = position_risk.current_price
        
        for i, (target_price, close_pct) in enumerate(position_risk.take_profit_targets):
            # 检查是否达到止盈目标
            should_take_profit = False
            
            if position_risk.side == "long":
                should_take_profit = current_price >= target_price
            else:
                should_take_profit = current_price <= target_price
            
            if should_take_profit:
                # 计算需要平仓的数量
                remaining_size = position_risk.size - position_risk.partial_profits_taken
                close_size = remaining_size * close_pct
                
                if close_size > 0.001:  # 最小平仓数量
                    actions.append(f"partial_take_profit:{close_size}:{target_price}")
                    position_risk.partial_profits_taken += close_size
                    self.stats['take_profits_triggered'] += 1
                    
                    # 移除已执行的止盈目标
                    position_risk.take_profit_targets.pop(i)
                    break
        
        return actions
    
    def _check_emergency_risk(self, position_risk: PositionRisk) -> bool:
        """检查紧急风险"""
        current_price = position_risk.current_price
        entry_price = position_risk.entry_price
        
        # 计算当前亏损
        if position_risk.side == "long":
            loss_pct = (entry_price - current_price) / entry_price
        else:
            loss_pct = (current_price - entry_price) / entry_price
        
        # 紧急止损阈值（比正常止损更严格）
        emergency_threshold = self.stop_loss_config.initial_pct * 1.5
        
        return loss_pct >= emergency_threshold
    
    def _calculate_risk_level(self, unrealized_pnl_pct: float, position_value: float) -> RiskLevel:
        """计算风险等级"""
        if abs(unrealized_pnl_pct) < 0.01:
            return RiskLevel.LOW
        elif abs(unrealized_pnl_pct) < 0.02:
            return RiskLevel.MEDIUM
        elif abs(unrealized_pnl_pct) < 0.05:
            return RiskLevel.HIGH
        else:
            return RiskLevel.EXTREME
    
    def _calculate_portfolio_risk(self) -> float:
        """计算组合风险"""
        total_risk = 0.0
        for position_risk in self.position_risks.values():
            entry_price = position_risk.entry_price
            current_price = position_risk.current_price
            
            if position_risk.side == "long":
                risk = (entry_price - current_price) / entry_price
            else:
                risk = (current_price - entry_price) / entry_price
            
            total_risk += max(0, risk)  # 只计算亏损风险
        
        return total_risk
    
    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤（简化版）"""
        # 这里应该基于历史数据计算，简化为当前组合风险
        return self._calculate_portfolio_risk()
    
    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        active_positions = len(self.position_risks)
        portfolio_risk = self._calculate_portfolio_risk()
        
        return {
            'active_positions': active_positions,
            'portfolio_risk': portfolio_risk,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'current_risk_level': self.current_risk_level.value,
            'market_volatility': self.market_volatility,
            'statistics': self.stats.copy()
        }
    
    def cleanup_closed_positions(self):
        """清理已关闭的持仓"""
        closed_positions = []
        
        for position_id, position_risk in self.position_risks.items():
            # 如果持仓已完全平仓
            if position_risk.partial_profits_taken >= position_risk.size * 0.99:
                closed_positions.append(position_id)
        
        for position_id in closed_positions:
            del self.position_risks[position_id]
        
        if closed_positions:
            self.logger.info(f"清理了{len(closed_positions)}个已关闭持仓")

# 全局高级风险管理器实例
global_risk_manager = AdvancedRiskManager()
