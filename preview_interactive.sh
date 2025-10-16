#!/bin/bash
# 本地预览交互式图表

# 切换到项目根目录
cd "$(dirname "$0")" || exit 1

echo "🚀 正在生成交互式图表..."
uv run python generate_interactive_plot.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 图表生成成功！"
    echo ""
    echo "📂 文件位置: docs/covid19_interactive.html"
    echo ""
    echo "🌐 在浏览器中打开预览..."
    
    # 根据操作系统打开文件
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        open docs/covid19_interactive.html
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        xdg-open docs/covid19_interactive.html
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        # Windows
        start docs/covid19_interactive.html
    else
        echo "⚠️  无法自动打开浏览器，请手动打开 docs/covid19_interactive.html"
    fi
else
    echo "❌ 生成失败，请检查错误信息"
    exit 1
fi

