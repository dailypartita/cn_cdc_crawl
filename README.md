# 中国疾控中心数据爬取与处理工具

[![Python](https://img.shields.io/badge/Python->=3.10-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

本项目是一个专门用于爬取、处理和分析中国疾控中心（CDC）发布的传染病监测数据的自动化工具。该工具可以从中国CDC官网批量下载并处理新冠疫情数据和急性呼吸道传染病监测报告，将其转换为结构化数据用于后续分析。

**本项目主要为 [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) 项目提供标准化的疫情监测数据**，确保预测模型能够获得及时、准确、格式统一的COVID-19监测数据。

![fig1](model/2025-09-02.jpg)

### 📈 交互式数据可视化

**[🔗 点击查看实时交互式图表](https://dailypartita.github.io/cn_cdc_data/covid19_interactive.html)** ✨

> 注：上方的交互式图表支持：
> - 🖱️ 缩放、平移、悬停查看详细数据
> - 📊 切换不同的平滑窗口（1周/3周/5周/7周）
> - 📅 快速选择时间范围（近4周/近13周/近6月/全部）
> - 💾 导出为高分辨率 PNG 图片

## 📊 项目概述

本项目主要处理两类数据：
- **新冠疫情数据** (`xgbdyq`)：新型冠状病毒肺炎疫情相关报告
- **急性呼吸道传染病监测数据** (`jksj04_14275`)：全国哨点监测情况报告

## 🚀 主要功能

1. **批量网页抓取**：自动从中国CDC官网批量下载指定页面并保存为PDF
2. **PDF转Markdown**：利用MinerU等OCR服务将PDF文件转换为结构化的Markdown格式
3. **数据提取**：从Markdown文件中智能提取病原体检测数据，输出结构化CSV
4. **可选LLM增强**：支持使用大语言模型提升数据提取的准确性

## 🛠 系统要求

- Python 3.10 或更高版本
- uv 包管理器（推荐）或 pip
- MinerU API 服务器（用于PDF转换）
- OpenRouter API 密钥（可选，用于LLM增强）

## 📦 安装依赖

本项目使用 `uv` 进行依赖管理：

```bash
# 克隆项目
git clone <repository-url>
cd cn_cdc_data

# 安装依赖
uv install
```

如果使用 pip：

```bash
pip install -r requirements.txt
```

主要依赖包括：
- `beautifulsoup4`：HTML解析
- `langchain` & `langchain-openai`：LLM处理
- `pandas`：数据处理
- `playwright`：浏览器自动化
- `requests`：HTTP请求
- `tqdm`：进度条显示

## 🔧 配置说明

### 1. MinerU 服务器配置

本项目需要MinerU API服务器进行PDF到Markdown的转换。默认配置：
```
默认服务器：http://10.22.16.132:8011
支持的格式：PDF → Markdown
```

### 2. OpenRouter API配置（可选）

如需使用LLM增强数据提取准确性：
```bash
export OPENROUTER_API_KEY="your-api-key-here"
```

## 📝 使用方法

### 完整工作流

项目提供了完整的数据处理流水线，可以通过 `run.sh` 脚本查看标准工作流：

#### 1. 急性呼吸道传染病监测数据处理

```bash
# 步骤1: 爬取网页并保存为PDF
uv run save_web_to_pdf.py \
    config/url_surveillance_new.txt -o pdf \
    --format A1 --margin 10mm \
    -c 6 --wait-until load

# 步骤2: 转换PDF为Markdown
uv run convert_pdf_to_md.py pdf -o md \
  --server http://10.22.16.132:8011 \
  --lang ch --backend pipeline --parse-method auto \
  --formula-enable true --table-enable true \
  --workers 6 --timeout 180 

# 步骤3: 提取结构化数据
export OPENROUTER_API_KEY="your-api-key"
uv run python extract_surveillance_data.py md -o data/updated_surveillance_data.csv --no-llm --debug
```

#### 2. 新冠疫情数据处理

```bash
# 爬取并保存PDF
uv run save_web_to_pdf.py \
    config/url_covid19.txt -o pdf \
    --format A1 --margin 10mm \
    -c 6 --wait-until load

# 转换为Markdown
uv run convert_pdf_to_md.py pdf -o md \
  --server http://10.22.16.132:8011 \
  --lang ch --backend pipeline --parse-method auto \
  --formula-enable true --table-enable true \
  --workers 6 --timeout 180 
```

### 各工具详细说明

#### 1. `save_web_to_pdf.py` - 网页转PDF工具

```bash
uv run save_web_to_pdf.py [URL文件] -o [输出目录] [选项]
```

**主要参数：**
- `input`：URL列表文件（每行一个URL）或逗号分隔的URL字符串
- `-o, --output`：输出目录，默认 `pdf_out`
- `--format`：纸张格式（A4/A1/Letter等），默认 A4
- `--margin`：页边距，默认 10mm
- `-c, --concurrency`：并发数，默认 4
- `-t, --timeout`：单页超时时间（秒），默认 45
- `--wait-until`：页面加载等待策略（load/networkidle/domcontentloaded）

**特色功能：**
- 中文字体优化支持
- 打印友好的页面样式调整
- 自动处理粘性导航栏
- 智能文件命名和去重

#### 2. `convert_pdf_to_md.py` - PDF转Markdown工具

```bash
uv run convert_pdf_to_md.py [PDF路径] -o [输出目录] [选项]
```

**主要参数：**
- `input`：PDF文件、目录或通配符模式
- `-o, --out`：输出目录，默认 `md_out`
- `--server`：MinerU服务器地址
- `--lang`：语言设置，默认 `ch`（中文）
- `--backend`：后端类型，默认 `pipeline`
- `--parse-method`：解析方法，默认 `auto`
- `--formula-enable`：启用公式识别，默认 true
- `--table-enable`：启用表格识别，默认 true
- `--workers`：并发工作线程数，默认 4

#### 3. `extract_data_from_md.py` - 数据提取工具

```bash
uv run python extract_data_from_md.py [Markdown目录] -o [CSV输出] [选项]
```

**主要参数：**
- `input`：Markdown文件目录
- `-o, --output`：输出CSV文件路径
- `--no-llm`：禁用LLM增强（使用基于规则的提取）
- `--debug`：启用调试输出
- `--model`：指定LLM模型，默认 `deepseek/deepseek-chat`
- `--workers`：并发处理数，默认 4

**数据提取规则：**
- 自动识别报告日期和周次信息
- 解析"表1"病原体检测数据
- 支持门急诊流感样病例（ILI）和住院严重急性呼吸道感染（SARI）两类数据
- 智能处理百分比和病例数数据

#### 4. `generate_interactive_plot.py` - 生成交互式图表

```bash
uv run python generate_interactive_plot.py
```

**功能说明：**
- 从 `data/covid_only_updated_surveillance_data.csv` 读取COVID-19监测数据
- 生成包含 ILI 和 SARI 阳性率的 Plotly 交互式图表
- 支持多个平滑窗口（1周/3周/5周/7周）切换
- 输出独立的 HTML 文件到 `docs/covid19_interactive.html`
- 适用于 GitHub Pages 托管展示

**交互功能：**
- 🖱️ 鼠标悬停显示详细数据点信息
- 📊 点击按钮切换不同的数据平滑窗口
- 🔍 缩放和平移查看特定时间段
- 📅 快速选择预设时间范围
- 💾 导出为高分辨率 PNG 图片

## 📁 项目结构

```
cn_cdc_data/
├── README.md                        # 项目文档
├── pyproject.toml                  # 项目配置和依赖
├── requirements.txt                # Python依赖列表
├── .gitignore                      # Git忽略配置
│
├── 核心脚本
├── save_web_to_pdf.py              # 网页批量保存为PDF
├── convert_pdf_to_md.py            # PDF转Markdown转换器
├── extract_data_from_md.py         # 结构化数据提取工具
├── extract_surveillance_data.py    # 专用监测数据提取工具
├── generate_interactive_plot.py    # 生成交互式Plotly图表
├── preview_interactive.sh          # 本地预览脚本
├── run.sh                          # 完整工作流示例
│
├── config/                         # 配置文件
│   ├── paths.py                        # 路径配置
│   ├── url_covid19.txt                 # 新冠疫情数据URL列表
│   ├── url_surveillance_history.txt    # 历史监测数据URL
│   └── url_surveillance_new.txt        # 最新监测数据URL
│
├── data/                           # 处理后的数据
│   ├── covid_only_updated_surveillance_data.csv  # COVID-19专用数据
│   ├── updated_surveillance_data.csv             # 完整监测数据
│   └── cn_cdc_surveillance.csv                   # 综合监测数据
│
├── pdf/                            # 所有PDF文件（原始数据）
├── md/                             # 所有Markdown文件（转换后）
│
├── notebooks/                      # Jupyter笔记本
│   ├── cn_cdc_covid19_model.ipynb      # COVID-19数据分析模型
│   └── test.ipynb                      # 测试笔记本
│
├── model/                          # 模型和图表
│   └── 2025-09-02.jpg                 # 示例图片
│
├── docs/                           # 文档和GitHub Pages
│   ├── covid19_interactive.html        # 交互式图表页面
│   ├── index.html                      # 首页
│   ├── SETUP.md                        # GitHub Pages设置指南
│   ├── INTERACTIVE_CHART_GUIDE.md      # 交互图表完整指南
│   └── QUICKSTART_INTERACTIVE.md       # 快速启动指南
│
└── .github/                        # GitHub Actions
    └── workflows/
        └── deploy-docs.yml             # 自动部署工作流
```

## 📋 COVID-19专用数据文件说明

### `covid_only_updated_surveillance_data.csv` 

此文件是专门为 [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) 项目定制的COVID-19监测数据文件，包含按周汇总的新冠病毒监测数据。该文件采用标准化的时间序列格式，便于疫情预测模型使用。

**关于China-COVID-19-Forecast-Hub项目**：
- 这是一个协作预测中心，专门收集和评估中国哨点医院流感样病例(ILI)中SARS-CoV-2阳性率的实时预测
- 项目于2025年8月21日开始运行，参与者需要在每周三北京时间23:59前提交预测
- 该平台为比较预测模型和为公共卫生决策提供循证见解提供服务
- 项目联系邮箱：yang_kaixin@gzlab.ac.cn

#### 数据列详细说明

| 列名 | 数据类型 | 描述 | 示例值 | 备注 |
|------|----------|------|--------|------|
| `reference_date` | 日期 (YYYY-MM-DD) | 监测周的起始日期（周一） | 2025-09-01 | 每个监测周的参考起点 |
| `target_end_date` | 日期 (YYYY-MM-DD) | 监测周的结束日期（周日） | 2025-09-07 | 与reference_date构成完整的监测周 |
| `report_week` | 整数 | 年度报告周次 | 36 | 按照ISO周历系统计算的周次 |
| `pathogen` | 文本 | 病原体名称 | 新型冠状病毒 | 目前专门针对COVID-19，统一为"新型冠状病毒" |
| `ili_percent` | 浮点数 | 门急诊流感样病例(ILI)阳性率 | 6.8 | 单位：百分比(%)，表示门急诊就诊的流感样病例中新冠阳性的比例 |
| `sari_percent` | 浮点数 | 住院严重急性呼吸道感染(SARI)病例阳性率 | 3.7 | 单位：百分比(%)，表示住院SARI病例中新冠阳性的比例 |

#### 数据特点

- **时间覆盖范围**：从2024年11月开始的连续监测数据
- **更新频率**：每周更新，通常在监测周结束后3-7天发布
- **数据来源**：基于全国哨点医院的监测网络
- **质量控制**：所有数据均经过中国CDC的标准化验证流程
- **格式标准**：严格按照 China-COVID-19-Forecast-Hub 项目的数据规范设计

#### 使用说明

1. **时间序列分析**：可以使用 `reference_date` 作为时间索引进行趋势分析
2. **预测模型输入**：`ili_percent` 和 `sari_percent` 是预测模型的核心输入特征  
3. **周次对齐**：`report_week` 可用于与其他数据源的周度数据进行对齐
4. **数据验证**：建议使用前检查日期连续性和数值合理性
5. **Forecast Hub对接**：
   - 数据格式完全符合China-COVID-19-Forecast-Hub的输入要求
   - `reference_date`对应预测的基准日期（每周六）
   - `target_end_date`对应预测目标周的结束日期  
   - 数据每周更新，支持实时预测和回顾性分析（nowcasting）
   - 如需将此数据用于其他研究或发表，请联系 yang_kaixin@gzlab.ac.cn 获取数据源归属信息

## 📊 输出数据格式

除了上述COVID-19专用文件外，系统还可以输出包含多种病原体的综合监测数据CSV文件，包含以下字段：

| 字段名 | 描述 | 示例 |
|--------|------|------|
| `report_date` | 报告发布日期 | 2025-08-28 |
| `report_week` | 报告周次 | 2025-34 |
| `pathogen` | 病原体名称 | 新型冠状病毒 |
| `ili_percent` | 门急诊流感样病例阳性率(%) | 10.5 |
| `sari_percent` | 住院严重急性呼吸道感染病例阳性率(%) | 4.3 |

支持的病原体包括：
- 新型冠状病毒
- 流感病毒
- 呼吸道合胞病毒
- 腺病毒
- 人偏肺病毒
- 副流感病毒
- 普通冠状病毒
- 博卡病毒
- 鼻病毒
- 肠道病毒
- 肺炎支原体

## ⚙️ 高级配置

### 自定义MinerU服务器

如果你有自己的MinerU部署：

```bash
# 方法1：环境变量
export MINERU_API="http://your-mineru-server:port"

# 方法2：命令行参数
uv run convert_pdf_to_md.py input.pdf --server http://your-mineru-server:port
```

### 批处理优化

对于大批量数据处理，建议：

1. **调整并发数**：根据服务器性能调整 `--workers` 和 `--concurrency` 参数
2. **增加超时时间**：复杂PDF可能需要更长处理时间 `--timeout 300`
3. **分批处理**：将大量URL分成小批次处理，避免资源耗尽

### 错误处理和重试

所有工具都支持自动重试机制：
- PDF转换支持失败重试（默认3次）
- 网页抓取支持多种等待策略回退
- 数据提取支持跳过损坏文件继续处理

## 🐛 常见问题

### 1. MinerU连接失败

**问题**：无法连接到MinerU服务器
**解决**：
- 确认MinerU服务正在运行
- 检查防火墙设置
- 验证API端点地址是否正确

### 2. PDF转换质量差

**问题**：转换后的Markdown文件表格混乱
**解决**：
- 启用表格识别：`--table-enable true`
- 调整解析方法：`--parse-method ocr` 或 `--parse-method txt`
- 检查原始PDF质量

### 3. 数据提取不完整

**问题**：CSV输出缺少某些数据行
**解决**：
- 启用调试模式：`--debug`
- 检查Markdown文件中表格格式
- 尝试启用LLM增强提取

### 4. 内存不足

**问题**：处理大量文件时内存耗尽
**解决**：
- 减少并发数：`--workers 2`
- 分批处理文件
- 增加系统虚拟内存

## 🌐 启用交互式图表（GitHub Pages）

要在你的 GitHub 仓库中展示交互式图表，请按照以下步骤操作：

### 快速启用

1. **推送代码到 GitHub**：
   ```bash
   git add .
   git commit -m "添加交互式图表"
   git push origin main
   ```

2. **在 GitHub 仓库设置中启用 Pages**：
   - 进入仓库的 **Settings** → **Pages**
   - **Source** 选择 `GitHub Actions`
   - 保存设置

3. **访问交互式图表**：
   - 部署完成后（约1-2分钟），访问：
   - `https://<你的用户名>.github.io/<仓库名>/covid19_interactive.html`

详细设置说明请查看 [docs/SETUP.md](docs/SETUP.md)

### 更新图表

当数据更新后，重新生成并推送：

```bash
# 生成新的交互式图表
uv run python generate_interactive_plot.py

# 提交更改
git add docs/covid19_interactive.html data/covid_only_updated_surveillance_data.csv
git commit -m "更新监测数据"
git push origin main
```

GitHub Actions 会自动重新部署更新后的图表。

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/AmazingFeature`
3. 提交修改：`git commit -m 'Add some AmazingFeature'`
4. 推送分支：`git push origin feature/AmazingFeature`
5. 提交Pull Request

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [MinerU](https://github.com/opendatalab/MinerU) - 强大的PDF解析工具
- [Playwright](https://playwright.dev/) - 现代浏览器自动化
- [LangChain](https://python.langchain.com/) - LLM应用开发框架
- 中国疾病预防控制中心 - 数据源

## 📮 联系方式

如有问题或建议，请通过以下方式联系：

- 提交GitHub Issue
- 发送邮件至：[yang_kaixin@gzlab.ac.cn]

---

**免责声明**：本工具仅用于学术研究和个人学习目的。使用时请遵守中国疾控中心网站的使用条款和相关法律法规。请合理使用爬虫工具，避免对目标网站造成过大负担。
