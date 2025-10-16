"""
项目路径配置文件
统一管理所有路径，便于维护和更新
"""
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置目录
CONFIG_DIR = PROJECT_ROOT / "config"
URL_COVID19 = CONFIG_DIR / "url_covid19.txt"
URL_SURVEILLANCE_HISTORY = CONFIG_DIR / "url_surveillance_history.txt"
URL_SURVEILLANCE_NEW = CONFIG_DIR / "url_surveillance_new.txt"

# 数据目录（简化后）
DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = PROJECT_ROOT / "pdf"
MD_DIR = PROJECT_ROOT / "md"

# 处理后的数据文件
COVID_ONLY_DATA = DATA_DIR / "covid_only_updated_surveillance_data.csv"
SURVEILLANCE_DATA = DATA_DIR / "updated_surveillance_data.csv"
ALL_SURVEILLANCE_DATA = DATA_DIR / "cn_cdc_surveillance.csv"

# 文档和可视化
DOCS_DIR = PROJECT_ROOT / "docs"
INTERACTIVE_HTML = DOCS_DIR / "covid19_interactive.html"

# 模型和笔记本
MODEL_DIR = PROJECT_ROOT / "model"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"


def ensure_dirs():
    """确保所有必要的目录存在"""
    dirs = [
        DATA_DIR, PDF_DIR, MD_DIR,
        DOCS_DIR, MODEL_DIR, NOTEBOOKS_DIR, CONFIG_DIR
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    # 测试路径配置
    print("项目路径配置:")
    print(f"  根目录: {PROJECT_ROOT}")
    print(f"  配置目录: {CONFIG_DIR}")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  PDF目录: {PDF_DIR}")
    print(f"  Markdown目录: {MD_DIR}")
    print(f"  文档目录: {DOCS_DIR}")
    print("\n创建必要的目录...")
    ensure_dirs()
    print("✓ 完成")
