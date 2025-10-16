# 项目结构说明

## 📂 目录结构

```
cn_cdc_data/
├── 配置和文档
│   ├── README.md                   # 主要文档
│   ├── pyproject.toml             # 项目配置
│   ├── requirements.txt           # 依赖列表
│   └── .gitignore                 # Git 忽略规则
│
├── 核心脚本
│   ├── save_web_to_pdf.py         # 网页→PDF
│   ├── convert_pdf_to_md.py       # PDF→Markdown
│   ├── extract_surveillance_data.py  # Markdown→数据
│   ├── extract_data_from_md.py    # 数据提取（通用）
│   ├── generate_interactive_plot.py  # 生成交互图表
│   ├── preview_interactive.sh     # 本地预览
│   └── run.sh                     # 完整工作流
│
├── config/                         # 配置文件
│   ├── paths.py                   # 路径配置
│   └── url_*.txt                  # URL 列表
│
├── data/                           # 处理后的数据
│   ├── covid_only_updated_surveillance_data.csv  # COVID-19 数据
│   └── updated_surveillance_data.csv             # 完整监测数据
│
├── pdf/                            # 原始 PDF 文件
├── md/                             # 转换后的 Markdown
│
├── docs/                           # GitHub Pages
│   ├── covid19_interactive.html   # 交互图表
│   └── *.md                       # 文档
│
├── notebooks/                      # Jupyter 笔记本
├── model/                          # 模型文件
└── .github/                        # GitHub Actions
```

## 🔄 数据处理流程

```
网页 URL → PDF → Markdown → 结构化数据 → 交互图表
   ↓         ↓       ↓           ↓           ↓
config/   pdf/    md/       data/       docs/
url_*.txt
```

## 🎯 主要变更（整理后）

### 简化的目录结构

**之前**：
- `pdf_covid19/` 和 `pdf_surveillance/` 分开
- `md_covid19/` 和 `md_surveillance/` 分开
- `data/raw/` 和 `data/processed/` 分开
- `scripts/` 目录存放所有脚本

**现在**：
- 统一到 `pdf/` 和 `md/` 目录
- 简化为单一的 `data/` 目录
- 脚本直接放在根目录，更易访问

### 移除的复杂工具

- ❌ `Makefile` - 不需要 make 工具
- ❌ `cli.py` - 不需要复杂的 CLI
- ✅ 保持简单的 shell 脚本和 Python 脚本

## 📝 快速开始

### 1. 抓取和处理数据

```bash
# 抓取网页
uv run save_web_to_pdf.py config/url_surveillance_new.txt -o pdf

# 转换为 Markdown
uv run convert_pdf_to_md.py pdf -o md

# 提取数据
uv run python extract_surveillance_data.py md -o data/updated_surveillance_data.csv
```

### 2. 生成交互图表

```bash
# 生成
uv run python generate_interactive_plot.py

# 或者生成并预览
./preview_interactive.sh
```

### 3. 查看项目状态

```bash
# 查看目录大小
du -sh data/ pdf/ md/

# 查看文件数量
ls -l data/*.csv
ls pdf/*.pdf | wc -l
ls md/*.md | wc -l
```

## 🗂️ 文件命名规范

- PDF 文件：`t{日期}_{ID}.pdf`
- Markdown 文件：`t{日期}_{ID}.md`
- 数据文件：`{描述}_data.csv`

## 💡 使用建议

1. **定期清理**：PDF 和 MD 文件可能很大，定期清理旧文件
2. **备份数据**：`data/` 目录中的 CSV 是最重要的，定期备份
3. **版本控制**：只提交代码和小文件，大文件添加到 `.gitignore`

## 📌 重要提示

- 所有脚本都支持 `--help` 查看详细参数
- 路径配置统一在 `config/paths.py` 中管理
- GitHub Actions 会自动部署 `docs/` 目录到 GitHub Pages

