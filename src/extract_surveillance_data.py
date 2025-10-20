#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, argparse, concurrent.futures, io
from io import StringIO
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from datetime import date, datetime
from tqdm import tqdm

def extract_week_info_from_title(text: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    从标题和正文中提取周信息，支持多种格式
    返回 (reference_date, target_end_date, report_week)
    """
    
    # 格式1: 2024年第46周（11月11日 11月17日）
    pattern1 = r"(\d{4})年第(\d{1,2})周[（\(](\d{1,2})⽉(\d{1,2})⽇\s*[-–—\s]\s*(\d{1,2})⽉(\d{1,2})⽇[）\)]"
    match = re.search(pattern1, text)
    
    if match:
        year, week, start_month, start_day, end_month, end_day = match.groups()
        year = int(year)
        week = int(week)
        start_month = int(start_month)
        start_day = int(start_day)
        end_month = int(end_month)
        end_day = int(end_day)
        
        reference_date = f"{year}-{start_month:02d}-{start_day:02d}"
        target_end_date = f"{year}-{end_month:02d}-{end_day:02d}"
        
        return reference_date, target_end_date, week
    
    # 格式2: 2025年第1周（2024年12月30日 2025年1月5日）- 跨年
    pattern2 = r"(\d{4})年第(\d{1,2})周[（\(](\d{4})年(\d{1,2})⽉(\d{1,2})⽇\s*[-–—\s]\s*(\d{4})年(\d{1,2})⽉(\d{1,2})⽇[）\)]"
    match = re.search(pattern2, text)
    
    if match:
        report_year, week, start_year, start_month, start_day, end_year, end_month, end_day = match.groups()
        report_year = int(report_year)
        week = int(week)
        start_year = int(start_year)
        start_month = int(start_month)
        start_day = int(start_day)
        end_year = int(end_year)
        end_month = int(end_month)
        end_day = int(end_day)
        
        reference_date = f"{start_year}-{start_month:02d}-{start_day:02d}"
        target_end_date = f"{end_year}-{end_month:02d}-{end_day:02d}"
        
        return reference_date, target_end_date, week
    
    # 格式3: 2025年第6周（2025年2月3日 2月9日）- 同年
    pattern3 = r"(\d{4})年第(\d{1,2})周[（\(](\d{4})年(\d{1,2})⽉(\d{1,2})⽇\s*[-–—\s]\s*(\d{1,2})⽉(\d{1,2})⽇[）\)]"
    match = re.search(pattern3, text)
    
    if match:
        report_year, week, start_year, start_month, start_day, end_month, end_day = match.groups()
        week = int(week)
        start_year = int(start_year)
        start_month = int(start_month)
        start_day = int(start_day)
        end_month = int(end_month)
        end_day = int(end_day)
        
        reference_date = f"{start_year}-{start_month:02d}-{start_day:02d}"
        target_end_date = f"{start_year}-{end_month:02d}-{end_day:02d}"
        
        return reference_date, target_end_date, week
    
    # 格式4: 从月度报告中提取，如"2025年5月（第19周 22周，5月5日 6月1日）"
    pattern4 = r"(\d{4})年(\d{1,2})⽉[（\(]第(\d{1,2})周\s*[-–—\s]\s*(\d{1,2})周[，,]\s*(\d{1,2})⽉(\d{1,2})⽇\s*[-–—\s]\s*(\d{1,2})⽉(\d{1,2})⽇[）\)]"
    match = re.search(pattern4, text)
    
    if match:
        year, month, start_week, end_week, start_month, start_day, end_month, end_day = match.groups()
        year = int(year)
        start_week = int(start_week)
        start_month = int(start_month)
        start_day = int(start_day)
        end_month = int(end_month)
        end_day = int(end_day)
        
        reference_date = f"{year}-{start_month:02d}-{start_day:02d}"
        target_end_date = f"{year}-{end_month:02d}-{end_day:02d}"
        
        return reference_date, target_end_date, start_week
    
    # 如果以上都不匹配，尝试从标题中提取年份和周次，使用文件名推断日期
    pattern5 = r"(\d{4})年第(\d{1,2})周"
    match = re.search(pattern5, text)
    
    if match:
        year, week = match.groups()
        year = int(year)
        week = int(week)
        
        # 根据ISO周计算日期
        try:
            from datetime import date
            # ISO周的周一
            monday = date.fromisocalendar(year, week, 1)
            # 周日
            sunday = date.fromisocalendar(year, week, 7)
            
            reference_date = monday.strftime("%Y-%m-%d")
            target_end_date = sunday.strftime("%Y-%m-%d")
            
            return reference_date, target_end_date, week
        except Exception:
            return None, None, week
    
    return None, None, None

def extract_table_from_html(html_text: str) -> Optional[pd.DataFrame]:
    """从HTML表格文本中提取DataFrame"""
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return None
            
        # 寻找包含病原体数据的表格（主要是表1）
        for table in tables:
            table_text = table.get_text()
            # 检查是否是主要的病原体阳性率表格
            if ('病原体' in table_text and 
                ('门急诊' in table_text or '流感样' in table_text) and
                ('住院' in table_text or '严重急性' in table_text) and
                '新型冠状病毒' in table_text):
                
                # 手动解析表格，处理复杂的表头结构
                rows = table.find_all('tr')
                if len(rows) < 3:
                    continue
                
                # 第一行通常是主表头（病原体，门急诊流感样病例，住院严重急性呼吸道感染病例）
                # 第二行是子表头（第xx周，较上周等）
                # 第三行开始是数据
                
                # 构建简化的列名
                columns = ['pathogen', 'ili_current', 'ili_change', 'sari_current', 'sari_change']
                
                # 提取数据行（跳过前两行表头）
                data_rows = []
                for row in rows[2:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 5:  # 确保有足够的列
                        row_data = [cell.get_text().strip() for cell in cells[:5]]
                        data_rows.append(row_data)
                
                if data_rows:
                    df = pd.DataFrame(data_rows, columns=columns)
                    return df
        
        return None
    except Exception as e:
        print(f"提取表格时出错: {e}")
        return None

def parse_pathogen_data(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """解析病原体数据"""
    if df is None or df.empty:
        return []
    
    results = []
    
    print(f"表格列名: {list(df.columns)}")
    print(f"表格前几行数据:")
    print(df.head())
    
    # 使用预定义的列名
    pathogen_col = 'pathogen'
    ili_col = 'ili_current' 
    sari_col = 'sari_current'
    
    if pathogen_col not in df.columns:
        print("未找到病原体列")
        return []
    
    # 提取数据
    for _, row in df.iterrows():
        pathogen = str(row.get(pathogen_col, '')).strip()
        
        # 跳过无效行
        if (not pathogen or 
            pathogen in ['合计', '总计', '病原体', ''] or
            pathogen.startswith('第') or  # 跳过"第xx周"
            '岁' in pathogen or  # 跳过年龄组
            pathogen.startswith('①') or pathogen.startswith('②') or pathogen.startswith('③')):
            continue
        
        def extract_numeric(val):
            if val is None or pd.isna(val):
                return None
            val_str = str(val).replace('%', '').replace('％', '').replace(',', '').strip()
            # 移除加号和减号，但保留数字和小数点
            val_str = re.sub(r'[^\d\.]', '', val_str)
            if val_str == '' or val_str == '.':
                return None
            try:
                return float(val_str)
            except:
                return None
        
        ili_val = extract_numeric(row.get(ili_col)) if ili_col in df.columns else None
        sari_val = extract_numeric(row.get(sari_col)) if sari_col in df.columns else None
        
        # 只添加至少有一个有效数值的记录
        if ili_val is not None or sari_val is not None:
            results.append({
                'pathogen': pathogen,
                'ili_percent': ili_val,
                'sari_percent': sari_val
            })
    
    print(f"提取到 {len(results)} 个有效病原体记录")
    return results

def process_surveillance_file(file_path: Path, debug: bool = False) -> List[Dict[str, Any]]:
    """处理单个监测文件"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        # 提取周信息
        reference_date, target_end_date, report_week = extract_week_info_from_title(content)
        
        if debug:
            print(f"处理文件: {file_path.name}")
            print(f"提取到的周信息: {reference_date}, {target_end_date}, {report_week}")
        
        # 查找表格
        # 首先查找HTML表格
        html_pattern = r'<table.*?</table>'
        tables = re.findall(html_pattern, content, re.DOTALL | re.IGNORECASE)
        
        all_results = []
        
        for table_html in tables:
            df = extract_table_from_html(table_html)
            if df is not None:
                pathogen_data = parse_pathogen_data(df)
                if pathogen_data:
                    for data in pathogen_data:
                        data.update({
                            'reference_date': reference_date,
                            'target_end_date': target_end_date,
                            'report_week': report_week
                        })
                        all_results.append(data)
                    if debug:
                        print(f"从表格中提取到 {len(pathogen_data)} 行数据")
        
        return all_results
        
    except Exception as e:
        if debug:
            print(f"处理文件 {file_path.name} 时出错: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="从监测数据markdown文件中提取病原体检测数据")
    parser.add_argument("input", help="输入目录或文件路径")
    parser.add_argument("-o", "--output", default="extracted_surveillance_data.csv", help="输出CSV文件路径")
    parser.add_argument("--covid-only", action="store_true", help="只输出新冠病毒数据")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    parser.add_argument("--max-workers", type=int, default=4, help="并发处理线程数")
    
    args = parser.parse_args()
    
    # 查找所有markdown文件
    input_path = Path(args.input)
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(list(input_path.glob("*.md")))
    else:
        files = []
    
    if not files:
        print("未找到任何markdown文件")
        return
    
    print(f"找到 {len(files)} 个文件")
    
    # 并发处理文件
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(process_surveillance_file, f, args.debug) for f in files]
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="处理文件"):
            results = future.result()
            all_results.extend(results)
    
    if not all_results:
        print("未提取到任何数据")
        return
    
    # 转换为DataFrame
    df = pd.DataFrame(all_results)
    
    # 确保列的顺序
    columns = ['reference_date', 'target_end_date', 'report_week', 'pathogen', 'ili_percent', 'sari_percent']
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[columns]
    
    # 数据清理
    df['ili_percent'] = pd.to_numeric(df['ili_percent'], errors='coerce')
    df['sari_percent'] = pd.to_numeric(df['sari_percent'], errors='coerce')
    
    # 按日期排序
    df['reference_date'] = pd.to_datetime(df['reference_date'], errors='coerce')
    df = df.sort_values(['reference_date', 'pathogen'], ascending=[False, True])
    df['reference_date'] = df['reference_date'].dt.strftime('%Y-%m-%d')
    
    # 保存完整数据
    output_path = Path(args.output)
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ 提取完成！共 {len(df)} 行数据 -> {output_path}")
    
    # 如果需要，创建只包含新冠病毒的数据
    if args.covid_only:
        covid_df = df[df['pathogen'].str.contains('新型冠状病毒', na=False)]
        covid_output = output_path.parent / f"covid_only_{output_path.name}"
        covid_df.to_csv(covid_output, index=False, encoding='utf-8-sig')
        print(f"✅ 新冠病毒数据：{len(covid_df)} 行数据 -> {covid_output}")
    
    # 显示数据预览
    print("\n数据预览:")
    print(df.head(10))
    
    # 显示统计信息
    print(f"\n数据统计:")
    print(f"总行数: {len(df)}")
    print(f"病原体种类: {df['pathogen'].nunique()}")
    
    # 过滤掉空的日期值来计算范围
    valid_dates = df['reference_date'].dropna()
    if len(valid_dates) > 0:
        print(f"日期范围: {valid_dates.min()} 到 {valid_dates.max()}")
    else:
        print("日期范围: 无有效日期")
    print("\n各病原体数据量:")
    print(df['pathogen'].value_counts())

if __name__ == "__main__":
    main()
