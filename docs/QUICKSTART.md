# 快速开始指南

## 🚀 一键完整流程

### 1. 准备工作

确保已安装所有依赖：
```bash
uv install
```

### 2. 配置URL列表

编辑 `config/url_surveillance_new.txt`，添加要处理的网页URL：
```
https://www.chinacdc.cn/jksj/jksj04_14275/202510/t20251015_312973.html
```

### 3. 运行自动化流水线

```bash
# 基本使用（使用默认配置）
uv run python src/main_pipeline.py

# 自定义配置
uv run python src/main_pipeline.py \
    --url-file config/url_surveillance_new.txt \
    --pdf-server http://10.22.16.132:8011 \
    --update-dir update \
    --all-csv data/cncdc_surveillance_all.csv \
    --covid-csv data/cncdc_surveillance_covid19.csv
```

### 4. 查看结果

完成后，数据将自动更新到：

#### 主数据文件
- `data/cncdc_surveillance_all.csv` - 所有病原体的监测数据
- `data/cncdc_surveillance_covid19.csv` - 新冠病毒专项数据

#### 增量更新目录
```
update/
├── 2025-10-06/           # 按参考日期组织
│   ├── pdf/              # 原始PDF文件
│   │   └── t20251015_312973.pdf
│   ├── md/               # 转换后的Markdown
│   │   └── t20251015_312973.md
│   └── csv/              # 提取的数据
│       └── t20251015_312973.csv
└── ...
```

## 📊 验证数据

### 查看最新数据
```bash
# 查看全部病原体数据的前20行
head -20 data/cncdc_surveillance_all.csv

# 查看新冠数据的前10行
head -10 data/cncdc_surveillance_covid19.csv

# 统计数据行数
wc -l data/cncdc_surveillance_all.csv
wc -l data/cncdc_surveillance_covid19.csv
```

### 使用Python查看数据
```python
import pandas as pd

# 读取全部数据
df_all = pd.read_csv('data/cncdc_surveillance_all.csv')
print(f"总数据量: {len(df_all)} 行")
print(f"病原体种类: {df_all['pathogen'].nunique()}")
print(f"日期范围: {df_all['reference_date'].min()} 到 {df_all['reference_date'].max()}")

# 读取新冠数据
df_covid = pd.read_csv('data/cncdc_surveillance_covid19.csv')
print(f"\n新冠数据量: {len(df_covid)} 行")

# 查看最新一周的数据
print("\n最新一周数据:")
print(df_all[df_all['reference_date'] == df_all['reference_date'].max()])
```

## 🔄 定期更新流程

### 方法1：手动更新
1. 访问中国CDC网站，找到最新的监测报告URL
2. 将URL添加到 `config/url_surveillance_new.txt`
3. 运行 `uv run python src/main_pipeline.py`
4. 提交更新后的数据文件到Git仓库

### 方法2：脚本化更新
创建一个更新脚本 `update.sh`:
```bash
#!/bin/bash

# 进入项目目录
cd /path/to/cn_cdc_data

# 运行自动化流水线
uv run python src/main_pipeline.py

# 提交更新（可选）
git add data/*.csv update/
git commit -m "Update surveillance data $(date +%Y-%m-%d)"
git push
```

设置定时任务（crontab）：
```bash
# 每周三上午9点自动更新
0 9 * * 3 /path/to/update.sh
```

## ⚠️ 常见问题

### 1. PDF转换失败
**问题**：`convert_pdf_to_md.py` 报错
**解决**：
- 检查MinerU服务器是否运行：`curl http://10.22.16.132:8011`
- 确认网络连接正常
- 调整 `--timeout` 参数增加超时时间

### 2. 数据提取不完整
**问题**：提取的数据行数少于预期
**解决**：
- 使用 `--debug` 参数查看详细日志
- 检查Markdown文件中的表格格式是否正确
- 手动检查原始PDF文件的内容

### 3. 重复数据
**问题**：运行多次后数据重复
**解决**：自动化流水线会自动去重，保留最新的数据。如果仍有问题：
```bash
# 手动去重
uv run python -c "
import pandas as pd
df = pd.read_csv('data/cncdc_surveillance_all.csv')
df = df.drop_duplicates(subset=['reference_date', 'pathogen'], keep='first')
df.to_csv('data/cncdc_surveillance_all.csv', index=False, encoding='utf-8-sig')
print(f'去重后: {len(df)} 行')
"
```

## 📈 下一步

- 查看 [README.md](README.md) 了解更多功能
- 查看 [notebooks/cn_cdc_covid19_model.ipynb](notebooks/cn_cdc_covid19_model.ipynb) 学习数据分析
- 访问 [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) 了解如何使用这些数据进行预测

## 📞 联系方式

如有问题，请联系：yang_kaixin@gzlab.ac.cn

