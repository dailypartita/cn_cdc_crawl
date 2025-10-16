# 交互式图表部署指南

## 📊 概述

你的 COVID-19 监测数据交互式图表已经准备就绪！这份指南将帮助你将它部署到 GitHub Pages，让任何人都能在浏览器中查看。

## ✅ 已完成的工作

1. ✅ 创建了 `generate_interactive_plot.py` 脚本
2. ✅ 生成了交互式 HTML 图表 (`docs/covid19_interactive.html`)
3. ✅ 创建了 GitHub Pages 配置文件
4. ✅ 创建了自动部署工作流 (`.github/workflows/deploy-docs.yml`)
5. ✅ 更新了 README，添加了交互图表链接
6. ✅ 创建了本地预览脚本 (`preview_interactive.sh`)

## 🎯 图表功能特性

你的交互式图表包含以下功能：

- **📈 双指标展示**：同时显示 ILI（流感样病例）和 SARI（严重急性呼吸道感染）阳性率
- **🔄 多窗口平滑**：可切换 1周/3周/5周/7周 的移动平均
- **📅 时间范围选择**：快速选择近4周、近13周、近6月或全部数据
- **🖱️ 交互操作**：
  - 缩放：鼠标滚轮或框选区域
  - 平移：拖动图表
  - 悬停：显示精确数值
  - 重置：双击图表恢复默认视图
- **💾 导出功能**：可导出为高分辨率 PNG 图片
- **📱 响应式设计**：自动适应不同屏幕尺寸

## 🚀 部署到 GitHub Pages

### 步骤 1: 查看本地预览

在推送到 GitHub 之前，先在本地预览图表：

```bash
# 方法 1: 使用预览脚本（会自动在浏览器中打开）
./preview_interactive.sh

# 方法 2: 手动生成并打开
uv run python generate_interactive_plot.py
open docs/covid19_interactive.html  # macOS
# 或在文件管理器中双击打开 docs/covid19_interactive.html
```

### 步骤 2: 推送到 GitHub

```bash
# 添加所有新文件
git add .

# 提交更改
git commit -m "添加 COVID-19 监测数据交互式图表和 GitHub Pages 配置"

# 推送到远程仓库
git push origin main
```

### 步骤 3: 启用 GitHub Pages

1. 打开你的 GitHub 仓库页面
2. 点击顶部的 **Settings** （设置）标签
3. 在左侧菜单中找到 **Pages**
4. 在 **Source** 下拉菜单中选择 `GitHub Actions`
5. 保存设置

### 步骤 4: 等待部署完成

1. 进入仓库的 **Actions** 标签
2. 你会看到 "部署交互式图表到 GitHub Pages" 工作流正在运行
3. 等待工作流完成（通常 1-2 分钟），直到显示绿色的 ✓

### 步骤 5: 访问你的交互式图表

部署成功后，你的图表将在以下地址可访问：

```
https://<你的GitHub用户名>.github.io/<仓库名>/covid19_interactive.html
```

例如：
- 用户名：`dailypartita`
- 仓库名：`cn_cdc_data`
- 完整 URL：`https://dailypartita.github.io/cn_cdc_data/covid19_interactive.html`

**记得更新 README 中的链接为你的实际 URL！**

## 🔄 更新图表流程

当你有新的监测数据时，按以下步骤更新图表：

```bash
# 1. 更新数据文件（通常是通过运行数据提取脚本）
uv run python extract_surveillance_data.py ...

# 2. 重新生成交互式图表
uv run python generate_interactive_plot.py

# 3. 提交并推送更改
git add covid_only_updated_surveillance_data.csv docs/covid19_interactive.html
git commit -m "更新 $(date +%Y-%m-%d) 监测数据"
git push origin main

# 4. GitHub Actions 会自动重新部署（无需手动操作）
```

## 📂 文件结构说明

```
cn_cdc_data/
├── generate_interactive_plot.py    # 生成交互图表的主脚本
├── preview_interactive.sh          # 本地预览脚本
├── covid_only_updated_surveillance_data.csv  # 数据源
├── 
├── docs/                           # GitHub Pages 根目录
│   ├── covid19_interactive.html    # 主交互图表
│   ├── index.html                  # 首页（重定向到主图表）
│   └── SETUP.md                    # 详细设置文档
├── 
└── .github/workflows/
    └── deploy-docs.yml             # 自动部署工作流
```

## 🎨 自定义图表

### 修改颜色和样式

编辑 `generate_interactive_plot.py`，在 `fig.add_trace()` 部分添加：

```python
fig.add_trace(go.Scatter(
    ...
    line=dict(color='#FF6B6B', width=3),  # 自定义颜色和线宽
    marker=dict(size=8, color='#4ECDC4')  # 自定义标记
))
```

### 添加更多平滑窗口

修改 `windows` 列表：

```python
windows = [1, 2, 3, 5, 7, 14, 21]  # 添加2周、14周、21周选项
```

### 更改图表尺寸

修改 `update_layout()` 中的 `height` 参数：

```python
fig.update_layout(
    height=800,  # 默认是 600
    ...
)
```

## 🔍 故障排查

### 问题 1：GitHub Actions 部署失败

**可能原因：**
- Pages 未启用
- 工作流权限不足

**解决方案：**
1. 检查 Settings → Pages 是否选择了 "GitHub Actions"
2. 检查 Settings → Actions → General → Workflow permissions
   - 选择 "Read and write permissions"
   - 勾选 "Allow GitHub Actions to create and approve pull requests"

### 问题 2：图表显示空白或错误

**可能原因：**
- 数据文件格式问题
- Plotly 库版本不兼容

**解决方案：**
```bash
# 检查数据文件
head -n 10 covid_only_updated_surveillance_data.csv

# 重新生成图表
rm docs/covid19_interactive.html
uv run python generate_interactive_plot.py

# 检查生成的文件
ls -lh docs/covid19_interactive.html
```

### 问题 3：链接无法访问（404）

**可能原因：**
- GitHub Pages 未完全部署
- URL 拼写错误

**解决方案：**
1. 等待 5-10 分钟让 DNS 传播
2. 确认 URL 格式：`https://用户名.github.io/仓库名/covid19_interactive.html`
3. 检查 Actions 标签确认部署成功
4. 尝试访问 `https://用户名.github.io/仓库名/` 查看是否能重定向

## 💡 最佳实践

1. **定期更新**：建议每周更新一次数据和图表
2. **备份数据**：在 git 中保留历史数据文件
3. **版本标注**：在提交信息中包含日期，便于追踪
4. **测试验证**：每次更新后在本地预览，确认无误再推送
5. **文档同步**：保持 README 和实际链接一致

## 📚 相关资源

- **Plotly 文档**: https://plotly.com/python/
- **GitHub Pages 文档**: https://docs.github.com/en/pages
- **GitHub Actions 文档**: https://docs.github.com/en/actions
- **详细设置指南**: [docs/SETUP.md](docs/SETUP.md)

## 🎉 完成！

恭喜！你现在拥有一个功能完整的交互式 COVID-19 监测数据可视化平台，可以与任何人分享，而且会随着你的数据更新自动同步。

---

如有问题，请查看 [docs/SETUP.md](docs/SETUP.md) 获取更详细的说明，或提交 GitHub Issue。

