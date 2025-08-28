#!/usr/bin/env python3
"""
Kronos Web Dashboard
精美的Web界面展示预测趋势和历史记录
支持SQLite和PostgreSQL数据库
"""
import sys
import os
import json
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
from flask import Flask, render_template, jsonify, request

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.monitor.dashboard import PredictionDashboard
from src.utils.config import OKXConfig
from src.utils.database import db_config, get_db_connection, execute_query
from okx.api import Account, Trade


class KronosWebDashboard:
    """Kronos Web仪表板"""
    
    def __init__(self, db_path: str = None):
        """初始化Web仪表板"""
        # 保存数据库路径
        self.db_path = db_path or "./data/predictions.db"

        # 设置数据库路径（如果提供且没有DATABASE_URL）
        if db_path and not os.getenv('DATABASE_URL'):
            os.environ['SQLITE_DB_PATH'] = str(Path(db_path).absolute())

        # 初始化PredictionDashboard，如果数据库不存在则创建一个空的
        try:
            self.dashboard = PredictionDashboard(self.db_path)
        except FileNotFoundError:
            print(f"⚠️ 数据库文件不存在: {self.db_path}")
            print("📁 创建数据库目录...")
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            # 创建一个临时的空数据库文件
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
            self.dashboard = PredictionDashboard(self.db_path)
        
        # 创建Flask应用
        self.app = Flask(__name__,
                        template_folder=str(project_root / 'templates'),
                        static_folder=str(project_root / 'static'))

        # 配置Flask应用
        self.app.config['SECRET_KEY'] = 'kronos-dashboard-secret-key'
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用缓存
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True

        # 初始化OKX API客户端
        try:
            self.okx_config = OKXConfig()
            self.account_api = Account(
                key=self.okx_config.api_key,
                secret=self.okx_config.secret_key,
                passphrase=self.okx_config.passphrase,
                flag='0'  # 0: 实盘, 1: 模拟盘
            )
            self.trade_api = Trade(
                key=self.okx_config.api_key,
                secret=self.okx_config.secret_key,
                passphrase=self.okx_config.passphrase,
                flag='0'  # 0: 实盘, 1: 模拟盘
            )
            self.okx_enabled = True
            print("✅ OKX API初始化成功")
        except Exception as e:
            print(f"⚠️ OKX API初始化失败: {e}")
            self.okx_enabled = False

        # 注册路由
        self._register_routes()

    def safe_float(self, value, default=0.0):
        """安全转换为浮点数"""
        try:
            if value is None or value == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_current_btc_price(self) -> float:
        """获取BTC当前实时价格"""
        try:
            # 优先使用实时API获取最新价格
            print("Debug: 尝试从实时API获取BTC价格...")

            # 1. 尝试使用Binance API获取价格（通常最稳定）
            try:
                response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    price = self.safe_float(data.get('price', 0))
                    print(f"Debug: 从Binance获取到实时价格: {price}")
                    if price > 0:
                        return price
            except Exception as binance_error:
                print(f"Debug: Binance API调用失败: {binance_error}")

            # 2. 尝试OKX API
            if self.okx_enabled:
                try:
                    from okx import PublicData
                    public_api = PublicData(flag='0')
                    response = public_api.get_tickers(instType='SWAP', instId='BTC-USDT-SWAP')
                    print(f"Debug: OKX API响应码: {response.get('code')}")

                    if response.get('code') == '0' and response.get('data'):
                        ticker = response['data'][0]
                        price = self.safe_float(ticker.get('last', 0))
                        print(f"Debug: 从OKX获取到实时价格: {price}")
                        if price > 0:
                            return price
                except Exception as okx_error:
                    print(f"Debug: OKX API调用失败: {okx_error}")

            # 3. 如果实时API都失败，才从数据库获取历史价格作为备用
            print(f"Debug: 实时API失败，尝试从数据库获取历史价格...")
            if Path(self.db_path).exists():
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT current_price, timestamp FROM predictions
                    WHERE instrument = 'BTC-USDT-SWAP'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()
                conn.close()

                if result and result[0]:
                    price = self.safe_float(result[0])
                    timestamp = result[1]
                    print(f"Debug: 从数据库获取到历史价格: {price} (时间: {timestamp})")
                    if price > 0:
                        return price
                else:
                    print("Debug: 数据库中没有找到BTC价格数据")
            else:
                print("Debug: 数据库文件不存在")

            print("Debug: 所有价格获取方式都失败，返回0")
            return 0.0

        except Exception as e:
            print(f"获取BTC价格失败: {e}")
            return 0.0

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        if not self.okx_enabled:
            return []

        try:
            response = self.account_api.get_positions()

            if response.get('code') == '0':
                positions = response.get('data', [])
                # 只返回有持仓的记录
                active_positions = []
                for pos in positions:
                    if self.safe_float(pos.get('pos', 0)) != 0:
                        # 格式化持仓数据
                        formatted_pos = {
                            'instId': pos.get('instId', 'N/A'),
                            'posSide': pos.get('posSide', 'N/A'),
                            'pos': self.safe_float(pos.get('pos', 0)),
                            'avgPx': self.safe_float(pos.get('avgPx', 0)),
                            'markPx': self.safe_float(pos.get('markPx', 0)),
                            'upl': self.safe_float(pos.get('upl', 0)),
                            'uplRatio': self.safe_float(pos.get('uplRatio', 0)),
                            'imr': self.safe_float(pos.get('imr', 0)),
                            'lever': pos.get('lever', 'N/A'),
                            'last': self.safe_float(pos.get('last', 0))
                        }
                        active_positions.append(formatted_pos)

                return active_positions
            else:
                print(f"获取持仓失败: {response.get('msg')}")
                return []

        except Exception as e:
            print(f"获取持仓异常: {e}")
            return []

    def _register_routes(self):
        """注册路由"""
        
        @self.app.route('/')
        def index():
            """首页"""
            try:
                return render_template('index.html')
            except Exception as e:
                return f"模板渲染错误: {e}", 500

        @self.app.route('/health')
        def health_check():
            """健康检查"""
            return jsonify({
                'status': 'ok',
                'message': 'Kronos Web Dashboard is running',
                'db_path': str(self.db_path),
                'db_exists': Path(self.db_path).exists()
            })
        
        @self.app.route('/api/system_status')
        def api_system_status():
            """获取系统状态API"""
            try:
                status = self.dashboard.get_system_status()
                metrics = self.dashboard.get_accuracy_metrics(24)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'status': status,
                        'metrics': metrics
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
        
        @self.app.route('/api/chart_data')
        def api_chart_data():
            """获取图表数据API"""
            try:
                hours = request.args.get('hours', 24, type=int)
                df = self.dashboard.get_prediction_history(hours)
                
                if df.empty:
                    return jsonify({
                        'success': True,
                        'data': {
                            'timestamps': [],
                            'current_prices': [],
                            'predicted_prices': [],
                            'price_changes': []
                        }
                    })
                
                # 转换数据格式
                data = {
                    'timestamps': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist(),
                    'current_prices': df['current_price'].tolist(),
                    'predicted_prices': df['predicted_price'].tolist(),
                    'price_changes': df['price_change_pct'].tolist()
                }
                
                return jsonify({
                    'success': True,
                    'data': data
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
        
        @self.app.route('/api/predictions')
        def api_predictions():
            """获取预测记录API（分页）"""
            try:
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 10, type=int)
                instrument = request.args.get('instrument', '', type=str)

                # 获取预测数据
                predictions = self._get_paginated_predictions(page, per_page, instrument)
                total_count = self._get_total_predictions_count(instrument)

                return jsonify({
                    'success': True,
                    'data': {
                        'predictions': predictions,
                        'pagination': {
                            'page': page,
                            'per_page': per_page,
                            'total': total_count,
                            'pages': (total_count + per_page - 1) // per_page
                        }
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })

        @self.app.route('/api/instruments')
        def api_instruments():
            """获取所有交易对列表API"""
            try:
                instruments = self._get_available_instruments()
                return jsonify({
                    'success': True,
                    'data': instruments
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
        
        @self.app.route('/api/latest_prediction')
        def api_latest_prediction():
            """获取最新预测API - 获取BTC的最新预测和实时价格"""
            try:
                # 获取实时BTC价格
                current_price = self.get_current_btc_price()
                print(f"Debug: 获取到的BTC当前价格: {current_price}")

                # 从数据库获取最新预测
                prediction_data = None
                prediction_age_hours = None

                if Path(self.db_path).exists():
                    # 构建查询SQL（兼容PostgreSQL和SQLite）
                    if db_config.db_type == 'postgresql':
                        query = '''
                            SELECT instrument, timestamp, current_price, predicted_price, price_change_pct,
                                   trend_direction, volatility
                            FROM predictions
                            WHERE instrument = %s
                            ORDER BY timestamp DESC
                            LIMIT 1
                        '''
                        params = ('BTC-USDT-SWAP',)
                    else:
                        query = '''
                            SELECT instrument, timestamp, current_price, predicted_price, price_change_pct,
                                   trend_direction, volatility
                            FROM predictions
                            WHERE instrument = ?
                            ORDER BY timestamp DESC
                            LIMIT 1
                        '''
                        params = ('BTC-USDT-SWAP',)

                    result = execute_query(query, params, fetch=True)

                    if result:
                        row = result[0]
                        prediction_timestamp = row[1]

                        # 计算预测数据的年龄
                        try:
                            pred_time = datetime.fromisoformat(prediction_timestamp)
                            prediction_age_hours = (datetime.now() - pred_time).total_seconds() / 3600
                            print(f"Debug: 预测数据年龄: {prediction_age_hours:.1f}小时")
                        except:
                            prediction_age_hours = 999  # 如果解析失败，认为很旧

                        prediction_data = {
                            'instrument': row[0],
                            'timestamp': row[1],
                            'predicted_price': row[3],
                            'price_change_pct': row[4],
                            'trend_direction': row[5],
                            'volatility': row[6],
                            'age_hours': prediction_age_hours
                        }

                # 合并实时价格和预测数据
                data = {
                    'instrument': 'BTC-USDT-SWAP',
                    'current_price': current_price,
                    'timestamp': datetime.now().isoformat(),
                }
                print(f"Debug: 预测数据: {prediction_data}")

                if prediction_data and prediction_age_hours is not None and prediction_age_hours < 24:
                    # 预测数据不超过24小时，使用预测数据
                    data.update(prediction_data)
                    # 重新计算价格变化百分比（基于实时价格）
                    if current_price and prediction_data.get('predicted_price'):
                        price_diff = prediction_data['predicted_price'] - current_price
                        data['price_change_pct'] = (price_diff / current_price) * 100
                    data['prediction_status'] = 'recent'
                    data['prediction_age_hours'] = prediction_age_hours
                elif prediction_data:
                    # 预测数据太旧，标记为过期但仍显示
                    data.update(prediction_data)
                    if current_price and prediction_data.get('predicted_price'):
                        price_diff = prediction_data['predicted_price'] - current_price
                        data['price_change_pct'] = (price_diff / current_price) * 100
                    data['prediction_status'] = 'outdated'
                    data['prediction_age_hours'] = prediction_age_hours
                else:
                    # 没有预测数据时的默认值
                    data.update({
                        'predicted_price': current_price,
                        'price_change_pct': 0.0,
                        'trend_direction': 'unknown',
                        'volatility': 0.0,
                        'prediction_status': 'none',
                        'prediction_age_hours': None
                    })

                return jsonify({
                    'success': True,
                    'data': data
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })

        @self.app.route('/api/positions')
        def api_positions():
            """获取持仓信息API"""
            try:
                positions = self.get_positions()

                return jsonify({
                    'success': True,
                    'data': {
                        'positions': positions,
                        'count': len(positions),
                        'timestamp': datetime.now().isoformat()
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'data': {
                        'positions': [],
                        'count': 0,
                        'timestamp': datetime.now().isoformat()
                    }
                })

    def _get_paginated_predictions(self, page: int, per_page: int, instrument: str = '') -> List[Dict]:
        """获取分页的预测数据，包含验证结果"""
        try:
            conn = sqlite3.connect(self.db_path)

            offset = (page - 1) * per_page

            # 构建查询条件，LEFT JOIN验证结果表
            if instrument:
                query = '''
                    SELECT p.instrument, p.timestamp, p.current_price, p.predicted_price, p.price_change,
                           p.price_change_pct, p.trend_direction, p.volatility,
                           p.lookback_hours, p.pred_hours, p.temperature, p.top_p, p.sample_count,
                           pv.actual_price, pv.price_error_pct, pv.direction_correct, pv.validation_status,
                           pv.validation_timestamp
                    FROM predictions p
                    LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
                    WHERE p.instrument = ?
                    ORDER BY p.timestamp DESC
                    LIMIT ? OFFSET ?
                '''
                params = (instrument, per_page, offset)
            else:
                query = '''
                    SELECT p.instrument, p.timestamp, p.current_price, p.predicted_price, p.price_change,
                           p.price_change_pct, p.trend_direction, p.volatility,
                           p.lookback_hours, p.pred_hours, p.temperature, p.top_p, p.sample_count,
                           pv.actual_price, pv.price_error_pct, pv.direction_correct, pv.validation_status,
                           pv.validation_timestamp
                    FROM predictions p
                    LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
                    ORDER BY p.timestamp DESC
                    LIMIT ? OFFSET ?
                '''
                params = (per_page, offset)

            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()

            predictions = []
            for row in results:
                # 处理验证结果
                validation_result = None
                if row[13] is not None:  # actual_price存在，说明有验证结果
                    validation_result = {
                        'actual_price': row[13],
                        'price_error_pct': row[14],
                        'direction_correct': bool(row[15]) if row[15] is not None else None,
                        'validation_status': row[16],
                        'validation_timestamp': row[17]
                    }

                predictions.append({
                    'instrument': row[0],
                    'timestamp': row[1],
                    'current_price': row[2],
                    'predicted_price': row[3],
                    'price_change': row[4],
                    'price_change_pct': row[5],
                    'trend_direction': row[6],
                    'volatility': row[7],
                    'lookback_hours': row[8],
                    'pred_hours': row[9],
                    'temperature': row[10],
                    'top_p': row[11],
                    'sample_count': row[12],
                    'validation_result': validation_result
                })

            return predictions

        except Exception as e:
            print(f"Error getting paginated predictions: {e}")
            return []
    
    def _get_total_predictions_count(self, instrument: str = '') -> int:
        """获取预测总数"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if instrument:
                cursor.execute("SELECT COUNT(*) FROM predictions WHERE instrument = ?", (instrument,))
            else:
                cursor.execute("SELECT COUNT(*) FROM predictions")

            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            print(f"Error getting total count: {e}")
            return 0

    def _get_available_instruments(self) -> List[str]:
        """获取所有可用的交易对"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT instrument FROM predictions ORDER BY instrument")
            instruments = [row[0] for row in cursor.fetchall()]
            conn.close()
            return instruments
        except Exception as e:
            print(f"Error getting instruments: {e}")
            return []
    
    def run(self, host: str = '127.0.0.1', port: int = 5000, debug: bool = True):
        """运行Web应用"""
        print(f"🚀 启动Kronos Web Dashboard")
        print(f"📊 访问地址: http://{host}:{port}")
        print(f"💾 数据库路径: {self.db_path}")

        # 检查数据库是否存在
        db_path_obj = Path(self.db_path)
        if not db_path_obj.exists():
            print(f"⚠️ 数据库文件不存在: {self.db_path}")
            print("请先运行预测系统生成数据")
            # 创建数据库目录
            db_path_obj.parent.mkdir(parents=True, exist_ok=True)
            print("📁 已创建数据库目录，Web面板将等待数据生成")

        # 检查模板和静态文件目录
        template_dir = Path(self.app.template_folder)
        static_dir = Path(self.app.static_folder)
        print(f"📁 模板目录: {template_dir} (存在: {template_dir.exists()})")
        print(f"📁 静态文件目录: {static_dir} (存在: {static_dir.exists()})")

        # 添加错误处理
        @self.app.errorhandler(403)
        def forbidden(error):
            return jsonify({'error': 'Forbidden', 'message': str(error)}), 403

        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': 'Not Found', 'message': str(error)}), 404

        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({'error': 'Internal Server Error', 'message': str(error)}), 500

        try:
            self.app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)
        except Exception as e:
            print(f"❌ Flask应用启动失败: {e}")
            raise


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kronos Web Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", type=int, default=8801, help="端口号")
    parser.add_argument("--db-path", default="./data/predictions.db", help="数据库路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    
    args = parser.parse_args()
    
    # 创建Web仪表板
    dashboard = KronosWebDashboard(args.db_path)
    
    # 运行应用
    dashboard.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
