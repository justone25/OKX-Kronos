// Kronos Dashboard JavaScript

class KronosDashboard {
    constructor() {
        this.chart = null;
        this.currentPage = 1;
        this.totalPages = 1;
        this.refreshInterval = null;
        this.positionsRefreshInterval = null;
        this.predictionsRefreshInterval = null;

        this.init();
    }
    
    init() {
        // 初始化图表
        this.initChart();

        // 加载初始数据
        this.loadSystemStatus();
        this.loadLatestPrediction();
        this.loadChartData(24);
        this.loadPredictions(1);
        this.loadPositions();

        // 设置自动刷新
        this.startAutoRefresh();

        console.log('Kronos Dashboard initialized');
    }
    
    initChart() {
        const ctx = document.getElementById('priceChart').getContext('2d');
        
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: '当前价格',
                        data: [],
                        borderColor: '#007bff',
                        backgroundColor: 'rgba(0, 123, 255, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: '预测价格',
                        data: [],
                        borderColor: '#28a745',
                        backgroundColor: 'rgba(40, 167, 69, 0.1)',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': $' + 
                                       context.parsed.y.toLocaleString('en-US', {
                                           minimumFractionDigits: 2,
                                           maximumFractionDigits: 2
                                       });
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: {
                                minute: 'HH:mm',
                                hour: 'HH:mm',
                                day: 'MM-DD HH:mm'
                            },
                            tooltipFormat: 'YYYY-MM-DD HH:mm'
                        },
                        title: {
                            display: true,
                            text: '时间'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: '价格 (USDT)'
                        },
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }
    
    async loadSystemStatus() {
        try {
            const response = await fetch('/api/system_status');
            const result = await response.json();
            
            if (result.success) {
                const { status, metrics } = result.data;
                
                // 更新系统状态 - 纯文字显示，与其他卡片一致
                const statusElement = document.getElementById('system-status');
                if (status.is_active) {
                    statusElement.innerHTML = '运行中';
                    statusElement.parentElement.parentElement.parentElement.className =
                        'card status-card bg-success text-white';
                } else {
                    statusElement.innerHTML = '离线';
                    statusElement.parentElement.parentElement.parentElement.className =
                        'card status-card bg-danger text-white';
                }
                
                // 更新最后更新时间
                if (status.last_prediction) {
                    const lastUpdate = new Date(status.last_prediction);
                    document.getElementById('last-update').innerHTML = 
                        '<i class="fas fa-clock me-1"></i>最后更新: ' + 
                        lastUpdate.toLocaleString('zh-CN');
                }
            }
        } catch (error) {
            console.error('Error loading system status:', error);
        }
    }
    
    async loadLatestPrediction() {
        try {
            const response = await fetch('/api/latest_prediction');
            const result = await response.json();
            
            if (result.success && result.data) {
                const data = result.data;
                
                // 更新价格显示
                document.getElementById('current-price').textContent = 
                    '$' + data.current_price.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    });
                
                document.getElementById('predicted-price').textContent = 
                    '$' + data.predicted_price.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    });
                
                // 更新趋势显示
                const trendCard = document.getElementById('trend-card');
                const trendElement = document.getElementById('price-trend');
                const trendIcon = document.getElementById('trend-icon');
                
                const changeText = (data.price_change_pct >= 0 ? '+' : '') + 
                                 data.price_change_pct.toFixed(2) + '%';
                
                trendElement.textContent = changeText;
                
                if (data.trend_direction === 'UP') {
                    trendCard.className = 'card status-card text-white trend-up';
                    trendIcon.className = 'fas fa-arrow-up fa-2x';
                } else if (data.trend_direction === 'DOWN') {
                    trendCard.className = 'card status-card text-white trend-down';
                    trendIcon.className = 'fas fa-arrow-down fa-2x';
                } else {
                    trendCard.className = 'card status-card text-white trend-neutral';
                    trendIcon.className = 'fas fa-arrow-right fa-2x';
                }
            }
        } catch (error) {
            console.error('Error loading latest prediction:', error);
        }
    }
    
    async loadChartData(hours = 24) {
        try {
            const response = await fetch(`/api/chart_data?hours=${hours}`);
            const result = await response.json();
            
            if (result.success) {
                const data = result.data;
                
                // 更新图表数据
                this.chart.data.labels = data.timestamps.map(ts => new Date(ts));
                this.chart.data.datasets[0].data = data.current_prices;
                this.chart.data.datasets[1].data = data.predicted_prices;
                
                this.chart.update();
            }
        } catch (error) {
            console.error('Error loading chart data:', error);
        }
    }
    
    async loadPredictions(page = 1) {
        try {
            const response = await fetch(`/api/predictions?page=${page}&per_page=10`);
            const result = await response.json();
            
            if (result.success) {
                const { predictions, pagination } = result.data;
                
                this.currentPage = pagination.page;
                this.totalPages = pagination.pages;
                
                // 更新表格
                this.updatePredictionsTable(predictions);
                
                // 更新分页
                this.updatePagination(pagination);
            }
        } catch (error) {
            console.error('Error loading predictions:', error);
        }
    }
    
    updatePredictionsTable(predictions) {
        const tbody = document.getElementById('predictions-table');
        
        if (predictions.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted">
                        <i class="fas fa-inbox me-2"></i>
                        暂无预测数据
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = predictions.map(pred => {
            const timestamp = new Date(pred.timestamp).toLocaleString('zh-CN');
            const currentPrice = '$' + pred.current_price.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
            const predictedPrice = '$' + pred.predicted_price.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
            
            const changeClass = pred.price_change_pct >= 0 ? 'price-change-positive' : 'price-change-negative';
            const changeText = (pred.price_change_pct >= 0 ? '+' : '') + pred.price_change_pct.toFixed(2) + '%';
            
            const trendClass = pred.trend_direction === 'UP' ? 'trend-up-indicator' : 
                              pred.trend_direction === 'DOWN' ? 'trend-down-indicator' : 'trend-neutral-indicator';
            
            const params = `
                <span class="param-badge">T:${pred.temperature}</span>
                <span class="param-badge">P:${pred.top_p}</span>
                <span class="param-badge">N:${pred.sample_count}</span>
            `;
            
            return `
                <tr class="fade-in">
                    <td>${timestamp}</td>
                    <td>${currentPrice}</td>
                    <td>${predictedPrice}</td>
                    <td class="${changeClass}">${changeText}</td>
                    <td><span class="trend-indicator ${trendClass}">${pred.trend_direction}</span></td>
                    <td>${pred.volatility.toFixed(2)}</td>
                    <td>${params}</td>
                </tr>
            `;
        }).join('');
    }
    
    updatePagination(pagination) {
        const paginationElement = document.getElementById('pagination');
        
        if (pagination.pages <= 1) {
            paginationElement.innerHTML = '';
            return;
        }
        
        let paginationHTML = '';
        
        // 上一页
        if (pagination.page > 1) {
            paginationHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" onclick="dashboard.loadPredictions(${pagination.page - 1})">
                        <i class="fas fa-chevron-left"></i>
                    </a>
                </li>
            `;
        }
        
        // 页码
        const startPage = Math.max(1, pagination.page - 2);
        const endPage = Math.min(pagination.pages, pagination.page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            const activeClass = i === pagination.page ? 'active' : '';
            paginationHTML += `
                <li class="page-item ${activeClass}">
                    <a class="page-link" href="#" onclick="dashboard.loadPredictions(${i})">${i}</a>
                </li>
            `;
        }
        
        // 下一页
        if (pagination.page < pagination.pages) {
            paginationHTML += `
                <li class="page-item">
                    <a class="page-link" href="#" onclick="dashboard.loadPredictions(${pagination.page + 1})">
                        <i class="fas fa-chevron-right"></i>
                    </a>
                </li>
            `;
        }
        
        paginationElement.innerHTML = paginationHTML;
    }
    
    startAutoRefresh() {
        // 每30秒刷新持仓信息
        this.positionsRefreshInterval = setInterval(() => {
            this.loadPositions();
        }, 30000);

        // 每10分钟刷新预测信息
        this.predictionsRefreshInterval = setInterval(() => {
            this.loadSystemStatus();
            this.loadLatestPrediction();
            this.loadChartData(24);
            this.loadPredictions(1);
        }, 600000); // 10分钟 = 600000毫秒

        console.log('自动刷新已启动: 持仓30秒, 预测10分钟');
    }

    stopAutoRefresh() {
        if (this.positionsRefreshInterval) {
            clearInterval(this.positionsRefreshInterval);
            this.positionsRefreshInterval = null;
        }
        if (this.predictionsRefreshInterval) {
            clearInterval(this.predictionsRefreshInterval);
            this.predictionsRefreshInterval = null;
        }
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        console.log('自动刷新已停止');
    }

    // 持仓信息相关方法
    loadPositions() {
        fetch('/api/positions')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.updatePositionsDisplay(data.data);
                } else {
                    console.error('获取持仓信息失败:', data.error);
                    this.showPositionsError(data.error);
                }
            })
            .catch(error => {
                console.error('获取持仓信息异常:', error);
                this.showPositionsError('网络连接失败');
            });
    }

    updatePositionsDisplay(data) {
        const positions = data.positions || [];
        const timestamp = data.timestamp;

        // 更新持仓数量
        document.getElementById('positions-count').textContent = positions.length;

        // 更新最后更新时间
        const lastUpdateElement = document.getElementById('positions-last-update');
        if (timestamp) {
            const updateTime = new Date(timestamp).toLocaleTimeString();
            lastUpdateElement.innerHTML = `<i class="fas fa-clock me-1"></i>最后更新: ${updateTime}`;
        }

        // 计算总计数据
        let totalUpl = 0;
        let totalMargin = 0;
        let totalNotional = 0;

        positions.forEach(pos => {
            totalUpl += pos.upl || 0;
            totalMargin += pos.imr || 0;
            totalNotional += (pos.pos || 0) * (pos.markPx || pos.avgPx || 0);
        });

        const totalUplRatio = totalNotional > 0 ? (totalUpl / totalNotional) * 100 : 0;

        // 更新概览卡片
        document.getElementById('total-positions').textContent = positions.length;
        document.getElementById('total-upl').textContent = this.formatCurrency(totalUpl);
        document.getElementById('total-upl').className = totalUpl >= 0 ? 'text-success' : 'text-danger';
        document.getElementById('total-margin').textContent = this.formatCurrency(totalMargin);
        document.getElementById('total-upl-ratio').textContent = this.formatPercentage(totalUplRatio);
        document.getElementById('total-upl-ratio').className = totalUplRatio >= 0 ? 'text-success' : 'text-danger';

        // 更新持仓表格
        this.updatePositionsTable(positions);
    }

    updatePositionsTable(positions) {
        const tbody = document.getElementById('positions-tbody');

        if (positions.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center text-muted">
                        <i class="fas fa-inbox me-2"></i>
                        暂无持仓
                    </td>
                </tr>
            `;
            return;
        }

        const rows = positions.map(pos => {
            const sideDisplay = {
                'long': '<span class="badge bg-success">多头</span>',
                'short': '<span class="badge bg-danger">空头</span>',
                'net': '<span class="badge bg-info">净持仓</span>'
            }[pos.posSide] || pos.posSide;

            const uplClass = (pos.upl || 0) >= 0 ? 'text-success' : 'text-danger';
            const uplRatioClass = (pos.uplRatio || 0) >= 0 ? 'text-success' : 'text-danger';

            return `
                <tr>
                    <td><strong>${pos.instId}</strong></td>
                    <td>${sideDisplay}</td>
                    <td>${this.formatNumber(pos.pos)}</td>
                    <td>$${this.formatNumber(pos.avgPx)}</td>
                    <td>$${this.formatNumber(pos.markPx || pos.last)}</td>
                    <td class="${uplClass}">$${this.formatNumber(pos.upl)}</td>
                    <td class="${uplRatioClass}">${this.formatPercentage((pos.uplRatio || 0) * 100)}</td>
                    <td>$${this.formatNumber(pos.imr)}</td>
                    <td><span class="badge bg-secondary">${pos.lever}x</span></td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rows;
    }

    showPositionsError(error) {
        const tbody = document.getElementById('positions-tbody');
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    获取持仓信息失败: ${error}
                </td>
            </tr>
        `;

        // 重置概览数据
        document.getElementById('positions-count').textContent = '0';
        document.getElementById('total-positions').textContent = '0';
        document.getElementById('total-upl').textContent = '$0.00';
        document.getElementById('total-margin').textContent = '$0.00';
        document.getElementById('total-upl-ratio').textContent = '0.00%';
    }

    // 工具方法
    formatCurrency(value) {
        if (value === null || value === undefined) return '$0.00';
        return '$' + Number(value).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    formatNumber(value) {
        if (value === null || value === undefined) return '0.00';
        return Number(value).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 4
        });
    }

    formatPercentage(value) {
        if (value === null || value === undefined) return '0.00%';
        return Number(value).toFixed(2) + '%';
    }
}

// 全局函数
function refreshPositions() {
    if (window.dashboard) {
        window.dashboard.loadPositions();
    }
}

function updateChart(hours) {
    // 更新按钮状态
    document.querySelectorAll('.btn-group .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // 加载新数据
    dashboard.loadChartData(hours);
}

// 初始化仪表板
let dashboard;
document.addEventListener('DOMContentLoaded', function() {
    dashboard = new KronosDashboard();
    window.dashboard = dashboard; // 设置为全局变量
});

// 页面卸载时停止自动刷新
window.addEventListener('beforeunload', function() {
    if (dashboard) {
        dashboard.stopAutoRefresh();
    }
});
