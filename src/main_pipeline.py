#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国疾控中心监测数据自动化处理流程
从URL列表自动下载、转换、提取数据并更新到主数据文件
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import re


def run_command(cmd, description=""):
    """运行命令并检查结果"""
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ 错误: {description} 失败")
        print(f"错误信息:\n{result.stderr}")
        return False
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    print(f"✅ {description} 完成")
    return True


def extract_reference_date_from_csv(csv_path):
    """从CSV文件中提取reference_date"""
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        if 'reference_date' in df.columns and len(df) > 0:
            # 获取第一行的reference_date
            ref_date = df['reference_date'].iloc[0]
            if pd.notna(ref_date):
                return str(ref_date)
    except Exception as e:
        print(f"⚠️  从CSV提取日期失败: {e}")
    return None


def get_file_id_from_url(url):
    """从URL中提取文件ID（如t20251015_312973）"""
    match = re.search(r'(t\d{8}_\d+)', url)
    if match:
        return match.group(1)
    return None


def merge_to_main_data(new_csv, all_csv, covid_csv):
    """合并新数据到主数据文件，并按日期降序排列"""
    try:
        # 读取新数据
        new_df = pd.read_csv(new_csv, encoding='utf-8-sig')
        print(f"📊 新数据: {len(new_df)} 行")
        
        # 处理主数据文件
        if os.path.exists(all_csv):
            all_df = pd.read_csv(all_csv, encoding='utf-8-sig')
            print(f"📊 现有全部数据: {len(all_df)} 行")
            
            # 合并数据（新数据在前）
            combined_df = pd.concat([new_df, all_df], ignore_index=True)
            
            # 去重（保留第一次出现的，即新数据优先）
            combined_df = combined_df.drop_duplicates(
                subset=['reference_date', 'target_end_date', 'pathogen'],
                keep='first'
            )
            
            # 按日期降序排列
            combined_df['_sort_date'] = pd.to_datetime(combined_df['reference_date'], errors='coerce')
            combined_df = combined_df.sort_values(
                ['_sort_date', 'pathogen'], 
                ascending=[False, True]
            ).drop(columns=['_sort_date'])
            
            # 保存
            combined_df.to_csv(all_csv, index=False, encoding='utf-8-sig')
            print(f"✅ 更新全部数据: {len(combined_df)} 行 -> {all_csv}")
        else:
            # 如果主文件不存在，直接保存新数据
            new_df['_sort_date'] = pd.to_datetime(new_df['reference_date'], errors='coerce')
            new_df = new_df.sort_values(
                ['_sort_date', 'pathogen'], 
                ascending=[False, True]
            ).drop(columns=['_sort_date'])
            new_df.to_csv(all_csv, index=False, encoding='utf-8-sig')
            print(f"✅ 创建全部数据: {len(new_df)} 行 -> {all_csv}")
        
        # 处理新冠数据文件
        covid_new_df = new_df[new_df['pathogen'].str.contains('新型冠状病毒', na=False)]
        print(f"📊 新冠病毒新数据: {len(covid_new_df)} 行")
        
        if os.path.exists(covid_csv):
            covid_df = pd.read_csv(covid_csv, encoding='utf-8-sig')
            print(f"📊 现有新冠数据: {len(covid_df)} 行")
            
            # 合并数据
            combined_covid_df = pd.concat([covid_new_df, covid_df], ignore_index=True)
            
            # 去重
            combined_covid_df = combined_covid_df.drop_duplicates(
                subset=['reference_date', 'target_end_date', 'pathogen'],
                keep='first'
            )
            
            # 按日期降序排列
            combined_covid_df['_sort_date'] = pd.to_datetime(combined_covid_df['reference_date'], errors='coerce')
            combined_covid_df = combined_covid_df.sort_values(
                '_sort_date', 
                ascending=False
            ).drop(columns=['_sort_date'])
            
            # 保存
            combined_covid_df.to_csv(covid_csv, index=False, encoding='utf-8-sig')
            print(f"✅ 更新新冠数据: {len(combined_covid_df)} 行 -> {covid_csv}")
        else:
            # 如果主文件不存在，直接保存新数据
            if len(covid_new_df) > 0:
                covid_new_df['_sort_date'] = pd.to_datetime(covid_new_df['reference_date'], errors='coerce')
                covid_new_df = covid_new_df.sort_values(
                    '_sort_date', 
                    ascending=False
                ).drop(columns=['_sort_date'])
                covid_new_df.to_csv(covid_csv, index=False, encoding='utf-8-sig')
                print(f"✅ 创建新冠数据: {len(covid_new_df)} 行 -> {covid_csv}")
        
        return True
        
    except Exception as e:
        print(f"❌ 合并数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="中国疾控中心监测数据自动化处理流程")
    parser.add_argument(
        "--url-file",
        default="config/url_surveillance_new.txt",
        help="URL列表文件路径"
    )
    parser.add_argument(
        "--pdf-server",
        default="http://10.22.16.132:8011",
        help="PDF转Markdown服务器地址"
    )
    parser.add_argument(
        "--update-dir",
        default="update",
        help="更新文件存放目录"
    )
    parser.add_argument(
        "--all-csv",
        default="data/cncdc_surveillance_all.csv",
        help="全部数据CSV文件路径"
    )
    parser.add_argument(
        "--covid-csv",
        default="data/cncdc_surveillance_covid19.csv",
        help="新冠数据CSV文件路径"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过下载和转换步骤（仅用于测试）"
    )
    
    args = parser.parse_args()
    
    # 获取项目根目录
    root_dir = Path(__file__).parent.parent.absolute()
    os.chdir(root_dir)
    print(f"📁 工作目录: {root_dir}")
    
    # 读取URL文件
    url_file = Path(args.url_file)
    if not url_file.exists():
        print(f"❌ URL文件不存在: {url_file}")
        return 1
    
    with open(url_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    if not urls:
        print(f"❌ URL文件为空: {url_file}")
        return 1
    
    print(f"📋 找到 {len(urls)} 个URL")
    
    # 处理每个URL
    for idx, url in enumerate(urls, 1):
        print(f"\n{'#'*60}")
        print(f"处理 URL {idx}/{len(urls)}: {url}")
        print(f"{'#'*60}")
        
        # 提取文件ID
        file_id = get_file_id_from_url(url)
        if not file_id:
            print(f"⚠️  无法从URL提取文件ID，跳过: {url}")
            continue
        
        print(f"📝 文件ID: {file_id}")
        
        # 创建临时目录
        update_dir = Path(args.update_dir)
        temp_pdf_dir = update_dir / "pdf"
        temp_md_dir = update_dir / "md"
        temp_data_dir = update_dir / "data"
        
        temp_pdf_dir.mkdir(parents=True, exist_ok=True)
        temp_md_dir.mkdir(parents=True, exist_ok=True)
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_file = temp_pdf_dir / f"{file_id}.pdf"
        md_file = temp_md_dir / f"{file_id}.md"
        csv_file = temp_data_dir / f"{file_id}.csv"
        
        if not args.skip_download:
            # 步骤1: 下载网页为PDF
            if not pdf_file.exists():
                cmd = [
                    "uv", "run", "python", "src/save_web_to_pdf.py",
                    url,
                    "-o", str(temp_pdf_dir),
                    "--format", "A1",
                    "--margin", "10mm",
                    "-c", "6",
                    "--wait-until", "load"
                ]
                if not run_command(cmd, "下载网页为PDF"):
                    print(f"⚠️  跳过URL: {url}")
                    continue
            else:
                print(f"✓ PDF文件已存在: {pdf_file}")
            
            # 步骤2: 转换PDF为Markdown
            if not md_file.exists():
                cmd = [
                    "uv", "run", "python", "src/convert_pdf_to_md.py",
                    str(pdf_file),
                    "-o", str(temp_md_dir),
                    "--server", args.pdf_server,
                    "--lang", "ch",
                    "--backend", "pipeline",
                    "--parse-method", "auto",
                    "--formula-enable", "true",
                    "--table-enable", "true",
                    "--workers", "6",
                    "--timeout", "180"
                ]
                if not run_command(cmd, "转换PDF为Markdown"):
                    print(f"⚠️  跳过URL: {url}")
                    continue
            else:
                print(f"✓ Markdown文件已存在: {md_file}")
            
            # 步骤3: 提取数据为CSV
            if not csv_file.exists():
                cmd = [
                    "uv", "run", "python", "src/extract_surveillance_data.py",
                    str(md_file),
                    "-o", str(csv_file)
                ]
                if not run_command(cmd, "提取监测数据"):
                    print(f"⚠️  跳过URL: {url}")
                    continue
            else:
                print(f"✓ CSV文件已存在: {csv_file}")
        else:
            print("⏭️  跳过下载和转换步骤")
        
        # 步骤4: 提取reference_date并创建目标目录
        print(f"\n📅 提取参考日期...")
        ref_date = extract_reference_date_from_csv(csv_file)
        
        if not ref_date:
            print(f"⚠️  无法提取reference_date，使用文件ID作为目录名")
            target_dir_name = file_id
        else:
            print(f"✅ 参考日期: {ref_date}")
            target_dir_name = ref_date
        
        # 创建目标目录结构
        target_dir = update_dir / target_dir_name
        target_pdf_dir = target_dir / "pdf"
        target_md_dir = target_dir / "md"
        target_csv_dir = target_dir / "csv"
        
        target_pdf_dir.mkdir(parents=True, exist_ok=True)
        target_md_dir.mkdir(parents=True, exist_ok=True)
        target_csv_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 创建目录结构: {target_dir}")
        
        # 步骤5: 移动文件到目标目录
        target_pdf = target_pdf_dir / f"{file_id}.pdf"
        target_md = target_md_dir / f"{file_id}.md"
        target_csv = target_csv_dir / f"{file_id}.csv"
        
        if pdf_file.exists() and not target_pdf.exists():
            shutil.copy2(pdf_file, target_pdf)
            print(f"✅ 复制: {pdf_file.name} -> {target_pdf}")
        
        if md_file.exists() and not target_md.exists():
            shutil.copy2(md_file, target_md)
            print(f"✅ 复制: {md_file.name} -> {target_md}")
        
        if csv_file.exists() and not target_csv.exists():
            shutil.copy2(csv_file, target_csv)
            print(f"✅ 复制: {csv_file.name} -> {target_csv}")
        
        # 步骤6: 合并数据到主文件
        print(f"\n📊 合并数据到主文件...")
        if not merge_to_main_data(target_csv, args.all_csv, args.covid_csv):
            print(f"⚠️  数据合并失败")
            continue
        
        print(f"\n✅ URL {idx}/{len(urls)} 处理完成!")
    
    print(f"\n{'='*60}")
    print(f"🎉 全部处理完成!")
    print(f"{'='*60}")
    print(f"📁 更新目录: {update_dir}")
    print(f"📊 全部数据: {args.all_csv}")
    print(f"📊 新冠数据: {args.covid_csv}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

