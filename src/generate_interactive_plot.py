#!/usr/bin/env python3
"""
生成 COVID-19 监测数据的交互式 Plotly 图表（独立 HTML 文件）
用于在 GitHub Pages 上展示
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import date
import plotly.graph_objects as go

try:
    from config.paths import COVID_ONLY_DATA, INTERACTIVE_HTML
except ImportError:
    # 如果导入失败，使用相对路径
    COVID_ONLY_DATA = None
    INTERACTIVE_HTML = None

def generate_interactive_plot(csv_path, output_html):
    """
    生成交互式 Plotly 图表并保存为独立的 HTML 文件
    
    Args:
        csv_path: CSV 数据文件路径
        output_html: 输出 HTML 文件路径
    """
    # 读取数据
    df = pd.read_csv(csv_path)
    
    # --- 时间列规范 ---
    df["report_date"] = pd.to_datetime(df.get("target_end_date"), errors="coerce")
    
    def week_to_monday(s):
        if pd.isna(s): 
            return pd.NaT
        try:
            y, w = map(int, str(s).split("-"))
            return pd.to_datetime(date.fromisocalendar(y, w, 1))
        except Exception:
            return pd.NaT
    
    df["week_monday"] = df.get("report_week", pd.Series([None]*len(df))).apply(week_to_monday)
    df["time"] = df["report_date"].fillna(df["week_monday"])
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    
    # --- 只保留新冠数据 ---
    covid_patterns = r"(?:新型冠状病毒|新冠|SARS[-\s]?CoV[-\s]?2|2019[-\s]?nCoV)"
    df = df[df["pathogen"].astype(str).str.contains(covid_patterns, case=False, regex=True, na=False)].copy()
    
    # 数值列转换
    for c in ["ili_percent", "sari_percent"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    
    # 同一天多条 -> 取均值
    df = (df.dropna(subset=["time"])
            .groupby("time", as_index=False)
            .agg({"ili_percent":"mean","sari_percent":"mean"}))
    df = df.sort_values("time")
    
    if df.empty:
        raise ValueError("CSV 里没找到新型冠状病毒的记录")
    
    # --- 预计算不同平滑窗口（周）的序列 ---
    windows = [1, 3, 5, 7]
    series = {}
    for w in windows:
        s = df.copy()
        if w > 1:
            s["ili_s"]  = s["ili_percent"].rolling(w, min_periods=1).mean()
            s["sari_s"] = s["sari_percent"].rolling(w, min_periods=1).mean()
        else:
            s["ili_s"]  = s["ili_percent"]
            s["sari_s"] = s["sari_percent"]
        series[w] = s
    
    # --- 创建图表 ---
    fig = go.Figure()
    traces_per_window = 2
    
    # 为每个窗口添加两条线（ILI 和 SARI）
    for w in windows:
        s = series[w]
        fig.add_trace(go.Scatter(
            x=s["time"], y=s["ili_s"], mode="lines+markers",
            name=f"ILI%（滑动{w}周）",
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>ILI: %{y:.2f}%<extra></extra>",
            visible=True if w == windows[0] else False,
            line=dict(width=2),
            marker=dict(size=6)
        ))
        fig.add_trace(go.Scatter(
            x=s["time"], y=s["sari_s"], mode="lines+markers",
            name=f"SARI%（滑动{w}周）",
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>SARI: %{y:.2f}%<extra></extra>",
            visible=True if w == windows[0] else False,
            line=dict(width=2),
            marker=dict(size=6)
        ))
    
    # 按钮：切换平滑窗口
    buttons = []
    for idx, w in enumerate(windows):
        vis = [False] * (len(windows) * traces_per_window)
        vis[idx*2] = True
        vis[idx*2 + 1] = True
        buttons.append(dict(
            label=f"{w}周", 
            method="update", 
            args=[{"visible": vis}]
        ))
    
    # 按钮：点位开关
    buttons_markers = [
        dict(label="显示点", method="restyle", args=[{"mode":"lines+markers"}]),
        dict(label="不显示点", method="restyle", args=[{"mode":"lines"}]),
    ]
    
    # 布局设置
    fig.update_layout(
        title={
            'text': "新型冠状病毒（COVID-19）监测阳性率 | ILI 与 SARI（交互）",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20}
        },
        xaxis_title="日期", 
        yaxis_title="阳性率（%）",
        hovermode="x unified", 
        template="plotly_white", 
        height=600,
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            x=0
        ),
        updatemenus=[
            dict(
                type="buttons", 
                direction="right", 
                x=0, 
                y=1.15, 
                buttons=buttons, 
                showactive=True, 
                pad={"r":8,"t":0}
            ),
            dict(
                type="buttons", 
                direction="right", 
                x=0.62, 
                y=1.15, 
                buttons=buttons_markers, 
                showactive=False, 
                pad={"r":8,"t":0}
            ),
        ]
    )
    
    # 添加时间范围选择器
    fig.update_xaxes(
        type="date",
        rangeslider=dict(visible=True),
        rangeselector=dict(
            buttons=[
                dict(count=28, label="近4周",  step="day",   stepmode="backward"),
                dict(count=91, label="近13周", step="day",   stepmode="backward"),
                dict(count=6,  label="近6月",  step="month", stepmode="backward"),
                dict(step="all", label="全部"),
            ]
        )
    )
    
    # 保存为独立的 HTML 文件
    fig.write_html(
        output_html,
        include_plotlyjs='cdn',
        full_html=True,
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'covid19_surveillance',
                'height': 800,
                'width': 1200,
                'scale': 2
            }
        }
    )
    
    print(f"✅ 交互式图表已生成：{output_html}")
    print(f"📊 数据点数：{len(df)} 条")
    print(f"📅 时间范围：{df['time'].min().date()} 至 {df['time'].max().date()}")


if __name__ == "__main__":
    # 使用配置的路径
    try:
        csv_path = COVID_ONLY_DATA
        output_html = INTERACTIVE_HTML
        
        # 确保输出目录存在
        output_html.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成图表
        generate_interactive_plot(str(csv_path), str(output_html))
    except Exception as e:
        # 如果路径配置失败，使用相对路径
        print(f"⚠️  使用默认路径配置")
        import os
        csv_path = "data/covid_only_updated_surveillance_data.csv"
        output_html = "docs/covid19_interactive.html"
        os.makedirs(os.path.dirname(output_html), exist_ok=True)
        generate_interactive_plot(csv_path, output_html)

