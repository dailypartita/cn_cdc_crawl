#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国疾控中心监测数据自动更新 DAG
每周定时执行数据抓取、转换、提取和合并流程
"""

from datetime import datetime, timedelta
from pathlib import Path
import os
import sys
import logging
from typing import List, Set
import requests
from bs4 import BeautifulSoup

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable

# 默认配置
DEFAULT_ARGS = {
    'owner': 'cdc_data_team',
    'depends_on_past': False,
    'email': ['yang_kaixin@gzlab.ac.cn'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# 从 Airflow Variables 获取配置，如果不存在则使用默认值
PROJECT_ROOT = Variable.get("cdc_project_root", "/data/ykx/covid19/get_data/cn_cdc_data")
PDF_SERVER = Variable.get("cdc_pdf_server", "http://10.22.16.132:8011")
URL_FILE = Variable.get("cdc_url_file", "config/url_surveillance_new.txt")
HISTORY_URL_FILE = Variable.get("cdc_history_url_file", "config/url_surveillance_history.txt")
CDC_MONITORING_URL = Variable.get("cdc_monitoring_url", "https://www.chinacdc.cn/jksj/jksj04_14275/")
FIRECRAWL_API_KEY = Variable.get("firecrawl_api_key", "fc-1070b8415da9472c87f06cfd01cf0ecf")
UPDATE_DIR = Variable.get("cdc_update_dir", "update")
ALL_CSV = Variable.get("cdc_all_csv", "data/cncdc_surveillance_all.csv")
COVID_CSV = Variable.get("cdc_covid_csv", "data/cncdc_surveillance_covid19.csv")


# ==================== 爬虫辅助函数 ====================

def fetch_surveillance_links_firecrawl(url: str, api_key: str) -> List[str]:
    """
    使用 Firecrawl API v2 爬取链接
    
    Args:
        url: 目标URL
        api_key: Firecrawl API密钥
        
    Returns:
        链接列表
    """
    # Firecrawl v2 API - 使用 map 接口获取网站所有链接
    api_url = "https://api.firecrawl.dev/v2/map"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": url,
        "limit": 5000,
        "includeSubdomains": True,
        "sitemap": "include"
    }
    
    try:
        print(f"🔥 使用 Firecrawl API v2 爬取: {url}")
        print(f"⏱️  请求超时设置: 90秒")
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=90)
        
        # 检查响应状态
        if response.status_code == 408:
            print(f"⚠️  Firecrawl 超时 (408)，CDC网站响应较慢")
            return []
        
        response.raise_for_status()
        data = response.json()
        
        # v2 API 响应格式: { "success": true, "links": [...] }
        if data.get('success'):
            all_links = data.get('links', [])
            
            if isinstance(all_links, list):
                print(f"✅ Firecrawl 返回 {len(all_links)} 个链接")
                
                # 过滤出监测报告链接
                links = []
                for link in all_links:
                    # v2 API links 可能是字符串或对象
                    if isinstance(link, str):
                        link_url = link
                    elif isinstance(link, dict):
                        link_url = link.get('url', '')
                    else:
                        continue
                    
                    # 匹配监测报告链接模式
                    # 排除索引页面（包含 index_）
                    if ('/jksj/jksj04_14275/' in link_url and 
                        link_url.endswith('.html') and 
                        'index_' not in link_url):
                        # 确保是完整URL
                        if not link_url.startswith('http'):
                            link_url = 'https://www.chinacdc.cn' + link_url
                        links.append(link_url)
                
                # 去重并排序
                links = sorted(list(set(links)))
                print(f"✅ 过滤后得到 {len(links)} 个监测报告链接")
                
                if len(links) > 0:
                    print(f"📋 示例链接（前3个）:")
                    for link in links[:3]:
                        print(f"  - {link}")
                    return links
                else:
                    print(f"⚠️  未找到匹配的监测报告链接")
                    return []
            else:
                print(f"⚠️  Firecrawl 返回数据格式异常: {type(all_links)}")
                return []
        else:
            error_msg = data.get('error', data.get('message', 'Unknown error'))
            logging.error(f"Firecrawl API 返回失败: {error_msg}")
            return []
            
    except requests.exceptions.Timeout:
        logging.warning("Firecrawl API 请求超时（90秒），CDC网站可能响应较慢")
        return []
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 408:
            logging.warning("Firecrawl 服务超时，这是正常的（CDC网站响应慢）")
        else:
            logging.error(f"Firecrawl API HTTP错误: {e.response.status_code} - {e}")
        return []
    except Exception as e:
        logging.error(f"Firecrawl API 调用失败: {e}")
        # 不打印完整堆栈，避免日志过长
        return []


def fetch_surveillance_links_bs4(url: str) -> List[str]:
    """
    使用 BeautifulSoup 备用方案爬取链接
    
    Args:
        url: 监测数据页面URL
        
    Returns:
        链接列表
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        print(f"🌐 使用 BeautifulSoup 备用方案爬取: {url}")
        response = requests.get(url, headers=headers, timeout=30, verify=True)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        print(f"✅ 响应状态码: {response.status_code}")
        print(f"✅ 响应内容长度: {len(response.text)} 字符")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找所有可能的链接
        all_links = soup.find_all('a', href=True)
        print(f"🔍 页面中找到 {len(all_links)} 个链接标签")
        
        # 查找监测报告链接
        links = []
        for a_tag in all_links:
            href = a_tag['href']
            
            # 匹配监测报告链接模式
            # 排除索引页面（包含 index_）
            if ('/jksj/jksj04_14275/' in href and 
                href.endswith('.html') and 
                'index_' not in href):
                # 转换为完整URL
                if href.startswith('http'):
                    full_url = href
                else:
                    base_url = 'https://www.chinacdc.cn'
                    full_url = base_url + href if href.startswith('/') else base_url + '/' + href
                
                links.append(full_url)
        
        # 去重并排序
        links = sorted(list(set(links)))
        
        print(f"✅ BeautifulSoup 爬取到 {len(links)} 个监测报告链接")
        
        if len(links) > 0:
            print(f"📋 示例链接（前3个）:")
            for link in links[:3]:
                print(f"  - {link}")
        
        return links
        
    except Exception as e:
        logging.error(f"BeautifulSoup 爬取失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_surveillance_links(url: str = "https://www.chinacdc.cn/jksj/jksj04_14275/") -> List[str]:
    """
    从中国疾控中心网站爬取哨点监测报告链接
    优先使用 Firecrawl API，失败时回退到 BeautifulSoup
    
    Args:
        url: 监测数据页面URL
        
    Returns:
        链接列表
    """
    # 方法1: 尝试使用 Firecrawl API
    if FIRECRAWL_API_KEY and FIRECRAWL_API_KEY != "":
        links = fetch_surveillance_links_firecrawl(url, FIRECRAWL_API_KEY)
        if links:
            return links
        logging.warning("Firecrawl API 失败，尝试备用方案...")
    
    # 方法2: 备用方案 - BeautifulSoup
    links = fetch_surveillance_links_bs4(url)
    if links:
        return links
    
    logging.error("所有爬取方法都失败了")
    return []


def read_existing_links(file_path: str) -> Set[str]:
    """
    读取本地已记录的链接
    
    Args:
        file_path: 链接文件路径
        
    Returns:
        链接集合
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"⚠️  链接文件不存在: {file_path}")
        return set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            links = set(line.strip() for line in f if line.strip() and line.strip().startswith('http'))
        
        print(f"✅ 读取到 {len(links)} 个已有链接")
        return links
                
    except Exception as e:
        logging.error(f"读取链接文件失败: {e}")
        return set()


def find_new_links(fetched_links: List[str], existing_links: Set[str]) -> List[str]:
    """
    找出新的链接
    
    Args:
        fetched_links: 爬取到的链接列表
        existing_links: 本地已有的链接集合
        
    Returns:
        新链接列表（按日期排序，最新的在前）
    """
    new_links = [link for link in fetched_links if link not in existing_links]
    
    # 按URL中的日期排序（降序，最新的在前）
    new_links.sort(reverse=True)
    
    print(f"✅ 发现 {len(new_links)} 个新链接")
    return new_links


def append_links_to_file(file_path: str, new_links: List[str]):
    """
    将新链接追加到文件
    
    Args:
        file_path: 链接文件路径
        new_links: 新链接列表
    """
    if not new_links:
        print("⚠️  没有新链接需要写入")
        return
    
    file_path = Path(file_path)
    
    try:
        # 读取现有内容
        existing_content = []
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_content = [line.rstrip('\n') for line in f]
        
        # 移除末尾的空行
        while existing_content and not existing_content[-1]:
            existing_content.pop()
        
        # 追加新链接
        with open(file_path, 'w', encoding='utf-8') as f:
            # 写入现有内容
            for line in existing_content:
                f.write(line + '\n')
            
            # 写入新链接
            for link in new_links:
                f.write(link + '\n')
        
        print(f"✅ 已将 {len(new_links)} 个新链接写入文件: {file_path}")
                
    except Exception as e:
        logging.error(f"写入链接文件失败: {e}")
        raise


# ==================== DAG 任务函数 ====================

def fetch_new_links_task(**context):
    """
    爬取新的监测报告链接
    从 CDC 网站爬取链接，与本地历史记录对比，找出新链接
    """
    import sys
    sys.path.insert(0, PROJECT_ROOT)
    
    print(f"🌐 开始爬取监测报告链接: {CDC_MONITORING_URL}")
    
    # 爬取链接
    fetched_links = fetch_surveillance_links(CDC_MONITORING_URL)
    
    # 读取本地历史记录
    history_file_path = Path(PROJECT_ROOT) / HISTORY_URL_FILE
    existing_links = read_existing_links(str(history_file_path))
    
    if not fetched_links:
        print("⚠️  未能从网站爬取到链接")
        
        # 如果历史记录存在，不算错误，只是没有新链接
        if existing_links:
            print(f"✅ 使用历史记录: {len(existing_links)} 个已知链接")
            print("✅ 本次运行：没有新链接需要处理")
            context['task_instance'].xcom_push(key='new_links', value=[])
            context['task_instance'].xcom_push(key='link_count', value=0)
            context['task_instance'].xcom_push(key='has_new_links', value=False)
            context['task_instance'].xcom_push(key='crawl_failed', value=True)
            return 0
        else:
            # 历史记录也不存在，尝试从备用文件读取
            print("⚠️  历史记录不存在，尝试从备用配置文件读取")
            url_file_path = Path(PROJECT_ROOT) / URL_FILE
            if url_file_path.exists():
                with open(url_file_path, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                if urls:
                    print(f"✅ 从备用文件读取到 {len(urls)} 个链接")
                    context['task_instance'].xcom_push(key='new_links', value=urls)
                    context['task_instance'].xcom_push(key='link_count', value=len(urls))
                    context['task_instance'].xcom_push(key='has_new_links', value=True)
                    context['task_instance'].xcom_push(key='crawl_failed', value=True)
                    return len(urls)
                    
                    # 所有方式都失败
                    logging.error("无法获取任何链接（爬取失败、历史记录不存在、备用文件不存在或为空）")
                    logging.info("💡 建议: 请手动在 config/url_surveillance_new.txt 中添加链接，或等待网站恢复")
                    context['task_instance'].xcom_push(key='new_links', value=[])
                    context['task_instance'].xcom_push(key='link_count', value=0)
                    context['task_instance'].xcom_push(key='has_new_links', value=False)
                    context['task_instance'].xcom_push(key='crawl_failed', value=True)
                    return 0
    
    # 成功爬取到链接
    print(f"✅ 从网站成功爬取 {len(fetched_links)} 个链接")
    
    # 找出新链接
    new_links = find_new_links(fetched_links, existing_links)
    
    if not new_links:
        print("⚠️  没有发现新链接（所有链接都已在历史记录中）")
        context['task_instance'].xcom_push(key='new_links', value=[])
        context['task_instance'].xcom_push(key='link_count', value=0)
        context['task_instance'].xcom_push(key='has_new_links', value=False)
        context['task_instance'].xcom_push(key='crawl_failed', value=False)
        return 0
    
    print(f"✅ 发现 {len(new_links)} 个新链接:")
    for link in new_links[:10]:  # 只打印前10个
        print(f"  - {link}")
    if len(new_links) > 10:
        print(f"  ... 还有 {len(new_links) - 10} 个链接")
    
    # 将新链接推送到 XCom
    context['task_instance'].xcom_push(key='new_links', value=new_links)
    context['task_instance'].xcom_push(key='link_count', value=len(new_links))
    context['task_instance'].xcom_push(key='has_new_links', value=True)
    context['task_instance'].xcom_push(key='crawl_failed', value=False)
    
    return len(new_links)


def check_new_links(**context):
    """
    检查是否有新链接需要处理
    如果没有新链接，提前结束流程（返回 False）
    如果有新链接，继续处理（返回 True）
    """
    has_new_links = context['task_instance'].xcom_pull(
        key='has_new_links', 
        task_ids='fetch_new_links'
    )
    
    link_count = context['task_instance'].xcom_pull(
        key='link_count', 
        task_ids='fetch_new_links'
    )
    
    if not has_new_links or link_count == 0:
        print("⚠️  没有新链接需要处理，终止后续流程")
        return False  # 返回 False 将跳过所有下游任务
    
    print(f"✅ 有 {link_count} 个新链接需要处理，继续执行流程")
    
    # 将新链接传递给后续任务
    new_links = context['task_instance'].xcom_pull(
        key='new_links', 
        task_ids='fetch_new_links'
    )
    
    context['task_instance'].xcom_push(key='url_list', value=new_links)
    context['task_instance'].xcom_push(key='url_count', value=link_count)
    
    return True  # 返回 True 继续执行下游任务


def download_web_to_pdf(**context):
    """下载网页并保存为 PDF"""
    import sys
    import subprocess
    sys.path.insert(0, PROJECT_ROOT)
    
    os.chdir(PROJECT_ROOT)
    
    urls = context['task_instance'].xcom_pull(key='url_list', task_ids='check_new_links')
    temp_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "pdf"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📥 开始下载 {len(urls)} 个网页为 PDF...")
    
    # 使用当前 Python 解释器（Airflow 的 Python）
    python_exe = sys.executable
    
    for idx, url in enumerate(urls, 1):
        print(f"\n处理 {idx}/{len(urls)}: {url}")
        
        cmd = [
            python_exe, "src/save_web_to_pdf.py",
            url,
            "-o", str(temp_dir),
            "--format", "A1",
            "--margin", "10mm",
            "-c", "6",
            "--wait-until", "load"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(result.stdout)
            print(f"✅ 下载成功: {url}")
        except subprocess.CalledProcessError as e:
            logging.error(f"下载失败: {url}")
            logging.error(f"错误信息: {e.stderr}")
            # 继续处理下一个 URL，不中断整个任务
            continue
    
    print(f"\n✅ PDF 下载任务完成")
    return str(temp_dir)


def convert_pdf_to_md(**context):
    """将 PDF 转换为 Markdown"""
    import sys
    import subprocess
    sys.path.insert(0, PROJECT_ROOT)
    
    os.chdir(PROJECT_ROOT)
    
    pdf_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "pdf"
    md_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("⚠️ 没有找到 PDF 文件")
        return str(md_dir)
    
    print(f"📝 开始转换 {len(pdf_files)} 个 PDF 文件为 Markdown...")
    
    # 使用当前 Python 解释器（Airflow 的 Python）
    python_exe = sys.executable
    
    for pdf_file in pdf_files:
        print(f"\n转换: {pdf_file.name}")
        
        cmd = [
            python_exe, "src/convert_pdf_to_md.py",
            str(pdf_file),
            "-o", str(md_dir),
            "--server", PDF_SERVER,
            "--lang", "ch",
            "--backend", "pipeline",
            "--parse-method", "auto",
            "--formula-enable", "true",
            "--table-enable", "true",
            "--workers", "6",
            "--timeout", "180"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(result.stdout)
            print(f"✅ 转换成功: {pdf_file.name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"转换失败: {pdf_file.name}")
            logging.error(f"错误信息: {e.stderr}")
            continue
    
    print(f"\n✅ PDF 转换任务完成")
    return str(md_dir)


def extract_data_from_md(**context):
    """从 Markdown 提取结构化数据"""
    import sys
    import subprocess
    sys.path.insert(0, PROJECT_ROOT)
    
    os.chdir(PROJECT_ROOT)
    
    md_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "md"
    csv_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    
    md_files = list(md_dir.glob("*.md"))
    
    if not md_files:
        print("⚠️ 没有找到 Markdown 文件")
        return str(csv_dir)
    
    print(f"📊 开始从 {len(md_files)} 个 Markdown 文件提取数据...")
    
    # 使用当前 Python 解释器（Airflow 的 Python）
    python_exe = sys.executable
    
    for md_file in md_files:
        csv_file = csv_dir / f"{md_file.stem}.csv"
        print(f"\n提取: {md_file.name}")
        
        cmd = [
            python_exe, "src/extract_surveillance_data.py",
            str(md_file),
            "-o", str(csv_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(result.stdout)
            print(f"✅ 提取成功: {md_file.name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"提取失败: {md_file.name}")
            logging.error(f"错误信息: {e.stderr}")
            continue
    
    print(f"\n✅ 数据提取任务完成")
    return str(csv_dir)


def organize_and_merge_data(**context):
    """整理数据到目标目录并合并到主文件"""
    import sys
    import shutil
    import re
    import pandas as pd
    sys.path.insert(0, PROJECT_ROOT)
    
    os.chdir(PROJECT_ROOT)
    
    csv_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "csv"
    pdf_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "pdf"
    md_dir = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp" / "md"
    
    csv_files = list(csv_dir.glob("*.csv"))
    
    if not csv_files:
        print("⚠️ 没有找到 CSV 文件，无法进行数据合并")
        return
    
    print(f"🗂️ 开始整理和合并 {len(csv_files)} 个数据文件...")
    
    all_csv_path = Path(PROJECT_ROOT) / ALL_CSV
    covid_csv_path = Path(PROJECT_ROOT) / COVID_CSV
    
    for csv_file in csv_files:
        file_id = csv_file.stem  # 例如: t20251015_312973
        
        # 读取 CSV 提取 reference_date
        try:
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            if 'reference_date' in df.columns and len(df) > 0:
                ref_date = str(df['reference_date'].iloc[0])
                target_dir_name = ref_date
            else:
                target_dir_name = file_id
        except Exception as e:
            print(f"⚠️ 读取 CSV 失败: {csv_file.name}, 使用文件ID作为目录名")
            target_dir_name = file_id
        
        # 创建目标目录结构
        target_dir = Path(PROJECT_ROOT) / UPDATE_DIR / target_dir_name
        target_pdf_dir = target_dir / "pdf"
        target_md_dir = target_dir / "md"
        target_csv_dir = target_dir / "csv"
        
        target_pdf_dir.mkdir(parents=True, exist_ok=True)
        target_md_dir.mkdir(parents=True, exist_ok=True)
        target_csv_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📁 处理文件: {file_id} -> {target_dir_name}")
        
        # 复制文件到目标目录
        pdf_file = pdf_dir / f"{file_id}.pdf"
        md_file = md_dir / f"{file_id}.md"
        
        if pdf_file.exists():
            target_pdf = target_pdf_dir / f"{file_id}.pdf"
            if not target_pdf.exists():
                shutil.copy2(pdf_file, target_pdf)
                print(f"  ✓ 复制 PDF: {pdf_file.name}")
        
        if md_file.exists():
            target_md = target_md_dir / f"{file_id}.md"
            if not target_md.exists():
                shutil.copy2(md_file, target_md)
                print(f"  ✓ 复制 MD: {md_file.name}")
        
        target_csv = target_csv_dir / f"{file_id}.csv"
        if not target_csv.exists():
            shutil.copy2(csv_file, target_csv)
            print(f"  ✓ 复制 CSV: {csv_file.name}")
        
        # 合并数据到主文件
        print(f"  📊 合并数据到主文件...")
        try:
            merge_csv_to_main(target_csv, all_csv_path, covid_csv_path)
        except Exception as e:
            logging.error(f"合并失败: {e}")
            continue
    
    # 清理临时目录
    temp_root = Path(PROJECT_ROOT) / UPDATE_DIR / "tmp"
    if temp_root.exists():
        shutil.rmtree(temp_root)
        print(f"\n🧹 清理临时目录: {temp_root}")
    
    print(f"\n✅ 数据整理和合并任务完成")


def merge_csv_to_main(new_csv, all_csv_path, covid_csv_path):
    """合并新数据到主数据文件"""
    import pandas as pd
    
    # 读取新数据
    new_df = pd.read_csv(new_csv, encoding='utf-8-sig')
    
    # 合并到全部数据文件
    if all_csv_path.exists():
        all_df = pd.read_csv(all_csv_path, encoding='utf-8-sig')
        combined_df = pd.concat([new_df, all_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(
            subset=['reference_date', 'target_end_date', 'pathogen'],
            keep='first'
        )
        combined_df['_sort_date'] = pd.to_datetime(combined_df['reference_date'], errors='coerce')
        combined_df = combined_df.sort_values(
            ['_sort_date', 'pathogen'], 
            ascending=[False, True]
        ).drop(columns=['_sort_date'])
        combined_df.to_csv(all_csv_path, index=False, encoding='utf-8-sig')
        print(f"    ✓ 更新全部数据: {len(combined_df)} 行")
    else:
        new_df['_sort_date'] = pd.to_datetime(new_df['reference_date'], errors='coerce')
        new_df = new_df.sort_values(
            ['_sort_date', 'pathogen'], 
            ascending=[False, True]
        ).drop(columns=['_sort_date'])
        new_df.to_csv(all_csv_path, index=False, encoding='utf-8-sig')
        print(f"    ✓ 创建全部数据: {len(new_df)} 行")
    
    # 合并到新冠数据文件
    covid_new_df = new_df[new_df['pathogen'].str.contains('新型冠状病毒', na=False)]
    
    if len(covid_new_df) > 0:
        if covid_csv_path.exists():
            covid_df = pd.read_csv(covid_csv_path, encoding='utf-8-sig')
            combined_covid_df = pd.concat([covid_new_df, covid_df], ignore_index=True)
            combined_covid_df = combined_covid_df.drop_duplicates(
                subset=['reference_date', 'target_end_date', 'pathogen'],
                keep='first'
            )
            combined_covid_df['_sort_date'] = pd.to_datetime(combined_covid_df['reference_date'], errors='coerce')
            combined_covid_df = combined_covid_df.sort_values(
                '_sort_date', 
                ascending=False
            ).drop(columns=['_sort_date'])
            combined_covid_df.to_csv(covid_csv_path, index=False, encoding='utf-8-sig')
            print(f"    ✓ 更新新冠数据: {len(combined_covid_df)} 行")
        else:
            covid_new_df['_sort_date'] = pd.to_datetime(covid_new_df['reference_date'], errors='coerce')
            covid_new_df = covid_new_df.sort_values(
                '_sort_date', 
                ascending=False
            ).drop(columns=['_sort_date'])
            covid_new_df.to_csv(covid_csv_path, index=False, encoding='utf-8-sig')
            print(f"    ✓ 创建新冠数据: {len(covid_new_df)} 行")


def update_history_file(**context):
    """
    将处理过的新链接写回历史记录文件
    """
    import sys
    sys.path.insert(0, PROJECT_ROOT)
    
    # 获取新链接
    new_links = context['task_instance'].xcom_pull(
        key='new_links', 
        task_ids='fetch_new_links'
    )
    
    if not new_links:
        print("⚠️  没有新链接需要写入历史文件")
        return 0
    
    # 写入历史文件
    history_file_path = Path(PROJECT_ROOT) / HISTORY_URL_FILE
    
    try:
        append_links_to_file(str(history_file_path), new_links)
        print(f"✅ 已将 {len(new_links)} 个新链接写入历史文件")
        return len(new_links)
    except Exception as e:
        logging.error(f"写入历史文件失败: {e}")
        raise


def send_completion_notification(**context):
    """发送完成通知"""
    import pandas as pd
    
    all_csv_path = Path(PROJECT_ROOT) / ALL_CSV
    covid_csv_path = Path(PROJECT_ROOT) / COVID_CSV
    
    # 获取执行时间（兼容新旧版本）
    logical_date = context.get('logical_date') or context.get('execution_date')
    execution_time = logical_date.strftime('%Y-%m-%d %H:%M:%S') if logical_date else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 获取新链接数量和爬取状态
    new_links_count = context['task_instance'].xcom_pull(
        key='link_count', 
        task_ids='fetch_new_links'
    )
    
    crawl_failed = context['task_instance'].xcom_pull(
        key='crawl_failed', 
        task_ids='fetch_new_links'
    )
    
    # 统计数据
    stats = {
        "execution_date": execution_time,
        "dag_run_id": context['dag_run'].run_id,
        "new_links_count": new_links_count or 0,
        "crawl_failed": crawl_failed or False,
    }
    
    if all_csv_path.exists():
        all_df = pd.read_csv(all_csv_path, encoding='utf-8-sig')
        stats['total_records'] = len(all_df)
        stats['latest_date'] = all_df['reference_date'].iloc[0] if len(all_df) > 0 else "N/A"
    
    if covid_csv_path.exists():
        covid_df = pd.read_csv(covid_csv_path, encoding='utf-8-sig')
        stats['covid_records'] = len(covid_df)
    
    print("\n" + "="*60)
    print("✅ 数据更新任务全部完成!")
    print("="*60)
    print(f"📅 执行时间: {stats['execution_date']}")
    print(f"🆔 运行ID: {stats['dag_run_id']}")
    
    # 爬取状态提示
    if stats['crawl_failed']:
        print(f"⚠️  网站爬取: 失败（使用历史数据或备用文件）")
    else:
        print(f"✅ 网站爬取: 成功")
    
    print(f"🔗 处理新链接: {stats['new_links_count']} 个")
    print(f"📊 总数据量: {stats.get('total_records', 0)} 行")
    print(f"🦠 新冠数据量: {stats.get('covid_records', 0)} 行")
    print(f"📆 最新日期: {stats.get('latest_date', 'N/A')}")
    
    # 添加建议
    if stats['crawl_failed'] and stats['new_links_count'] == 0:
        print("\n💡 建议:")
        print("  - 检查 CDC 网站是否可访问")
        print("  - 检查网络连接")
        print("  - 或在 config/url_surveillance_new.txt 中手动添加链接")
    
    print("="*60)
    
    return stats


# 创建 DAG
with DAG(
    dag_id='cdc_covid19_data_update',
    default_args=DEFAULT_ARGS,
    description='自动更新中国疾控中心COVID-19监测数据',
    schedule='0 0 * * 0',  # 每周日0点执行
    start_date=datetime(2025, 10, 1),
    catchup=False,
    tags=['cdc', 'covid19', 'data_pipeline'],
) as dag:
    
    # 任务1: 爬取新链接
    task_fetch_links = PythonOperator(
        task_id='fetch_new_links',
        python_callable=fetch_new_links_task,
    )
    
    # 任务2: 检查新链接（使用 ShortCircuitOperator 实现条件终止）
    task_check_links = ShortCircuitOperator(
        task_id='check_new_links',
        python_callable=check_new_links,
    )
    
    # 任务3: 下载网页为 PDF
    task_download_pdf = PythonOperator(
        task_id='download_web_to_pdf',
        python_callable=download_web_to_pdf,
    )
    
    # 任务4: 转换 PDF 为 Markdown
    task_convert_md = PythonOperator(
        task_id='convert_pdf_to_md',
        python_callable=convert_pdf_to_md,
    )
    
    # 任务5: 从 Markdown 提取数据
    task_extract_data = PythonOperator(
        task_id='extract_data_from_md',
        python_callable=extract_data_from_md,
    )
    
    # 任务6: 整理和合并数据
    task_merge_data = PythonOperator(
        task_id='organize_and_merge_data',
        python_callable=organize_and_merge_data,
    )
    
    # 任务7: 更新历史记录文件（只在所有前置任务成功时执行）
    task_update_history = PythonOperator(
        task_id='update_history_file',
        python_callable=update_history_file,
        trigger_rule='all_success',  # 明确指定：只有所有上游任务成功才执行
    )
    
    # 任务8: 发送完成通知（无论是否有新链接都会执行）
    task_notify = PythonOperator(
        task_id='send_completion_notification',
        python_callable=send_completion_notification,
        trigger_rule='all_done',  # 无论上游任务成功、失败或跳过，都会执行
    )
    
    # 任务9: 自动推送到 GitHub（只在有数据更新时执行）
    task_git_push = BashOperator(
        task_id='git_push_to_github',
        bash_command=f"""
        cd {PROJECT_ROOT} && \
        git add data/ update/ config/url_surveillance_history.txt && \
        git diff --cached --quiet || (git commit -m "自动更新: $(date '+%Y-%m-%d %H:%M:%S') CDC监测数据" && git push)
        """,
        trigger_rule='all_success',  # 只有所有上游任务成功才执行 push
    )
    
    # 定义任务依赖关系
    # 主流程：爬取 -> 检查 -> 下载 -> 转换 -> 提取 -> 合并 -> 更新历史
    task_fetch_links >> task_check_links >> task_download_pdf >> task_convert_md >> task_extract_data >> task_merge_data >> task_update_history
    
    # 通知任务：无论数据处理是否成功都会执行
    [task_fetch_links, task_update_history] >> task_notify
    
    # Git Push 任务：只有数据处理成功后才执行
    task_update_history >> task_git_push

