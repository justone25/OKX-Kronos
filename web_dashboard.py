#!/usr/bin/env python3
"""
Kronos Web Dashboard
精美的Web界面展示预测趋势和历史记录
"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
from flask import Flask, render_template, jsonify, request

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.monitor.dashboard import PredictionDashboard


class KronosWebDashboard:
    """Kronos Web仪表板"""
    
    def __init__(self, db_path: str = "./data/predictions.db"):
        """初始化Web仪表板"""
        self.db_path = Path(db_path)
        self.dashboard = PredictionDashboard(str(self.db_path))
        
        # 创建Flask应用
        self.app = Flask(__name__, 
                        template_folder='templates',
                        static_folder='static')
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册路由"""
        
        @self.app.route('/')
        def index():
            """首页"""
            return render_template('index.html')
        
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
                
                # 获取预测数据
                predictions = self._get_paginated_predictions(page, per_page)
                total_count = self._get_total_predictions_count()
                
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
        
        @self.app.route('/api/latest_prediction')
        def api_latest_prediction():
            """获取最新预测API"""
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT timestamp, current_price, predicted_price, price_change_pct,
                           trend_direction, volatility
                    FROM predictions 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                ''')
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    data = {
                        'timestamp': result[0],
                        'current_price': result[1],
                        'predicted_price': result[2],
                        'price_change_pct': result[3],
                        'trend_direction': result[4],
                        'volatility': result[5]
                    }
                else:
                    data = None
                
                return jsonify({
                    'success': True,
                    'data': data
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
    
    def _get_paginated_predictions(self, page: int, per_page: int) -> List[Dict]:
        """获取分页的预测数据"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            offset = (page - 1) * per_page
            
            query = '''
                SELECT timestamp, current_price, predicted_price, price_change,
                       price_change_pct, trend_direction, volatility,
                       lookback_hours, pred_hours, temperature, top_p, sample_count
                FROM predictions 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            '''
            
            cursor = conn.cursor()
            cursor.execute(query, (per_page, offset))
            results = cursor.fetchall()
            conn.close()
            
            predictions = []
            for row in results:
                predictions.append({
                    'timestamp': row[0],
                    'current_price': row[1],
                    'predicted_price': row[2],
                    'price_change': row[3],
                    'price_change_pct': row[4],
                    'trend_direction': row[5],
                    'volatility': row[6],
                    'lookback_hours': row[7],
                    'pred_hours': row[8],
                    'temperature': row[9],
                    'top_p': row[10],
                    'sample_count': row[11]
                })
            
            return predictions
            
        except Exception as e:
            print(f"Error getting paginated predictions: {e}")
            return []
    
    def _get_total_predictions_count(self) -> int:
        """获取预测总数"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM predictions")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            print(f"Error getting total count: {e}")
            return 0
    
    def run(self, host: str = '127.0.0.1', port: int = 5000, debug: bool = True):
        """运行Web应用"""
        print(f"🚀 启动Kronos Web Dashboard")
        print(f"📊 访问地址: http://{host}:{port}")
        print(f"💾 数据库路径: {self.db_path}")
        
        # 检查数据库是否存在
        if not self.db_path.exists():
            print(f"⚠️ 数据库文件不存在: {self.db_path}")
            print("请先运行预测系统生成数据")
            return
        
        self.app.run(host=host, port=port, debug=debug)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kronos Web Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", type=int, default=5000, help="端口号")
    parser.add_argument("--db-path", default="./data/predictions.db", help="数据库路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    
    args = parser.parse_args()
    
    # 创建Web仪表板
    dashboard = KronosWebDashboard(args.db_path)
    
    # 运行应用
    dashboard.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
