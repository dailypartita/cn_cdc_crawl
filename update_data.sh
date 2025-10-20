#!/bin/bash

# 中国疾控中心监测数据自动更新脚本
# 使用方法：./update_data.sh

set -e  # 遇到错误立即退出

echo "============================================"
echo "中国疾控中心监测数据自动更新"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# 进入脚本所在目录
cd "$(dirname "$0")"

# 显示当前工作目录
echo "📁 工作目录: $(pwd)"

# 检查URL文件是否存在
if [ ! -f "config/url_surveillance_new.txt" ]; then
    echo "❌ 错误: 找不到 config/url_surveillance_new.txt"
    exit 1
fi

# 显示要处理的URL数量
url_count=$(grep -v '^#' config/url_surveillance_new.txt | grep -v '^$' | wc -l | tr -d ' ')
echo "📋 找到 $url_count 个URL待处理"

# 运行自动化流水线
echo ""
echo "🚀 开始运行自动化流水线..."
uv run python src/main_pipeline.py

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo "✅ 数据更新成功！"
    echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================"
    
    # 显示数据统计
    echo ""
    echo "📊 数据统计:"
    all_count=$(wc -l < data/cncdc_surveillance_all.csv)
    covid_count=$(wc -l < data/cncdc_surveillance_covid19.csv)
    echo "  - 全部数据: $((all_count - 1)) 行"
    echo "  - 新冠数据: $((covid_count - 1)) 行"
    
    # 显示最新日期
    latest_date=$(tail -n +2 data/cncdc_surveillance_all.csv | head -1 | cut -d',' -f1)
    echo "  - 最新日期: $latest_date"
    
    exit 0
else
    echo ""
    echo "============================================"
    echo "❌ 数据更新失败！"
    echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================"
    exit 1
fi

