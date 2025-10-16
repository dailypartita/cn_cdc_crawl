# GitHub Pages 设置指南

本文档说明如何启用 GitHub Pages 来展示交互式 COVID-19 监测图表。

## 🚀 快速设置步骤

### 1. 推送代码到 GitHub

首先，确保你已经将代码推送到 GitHub 仓库：

```bash
git add .
git commit -m "添加交互式图表和 GitHub Pages 配置"
git push origin main
```

### 2. 启用 GitHub Pages

1. 进入你的 GitHub 仓库页面
2. 点击 **Settings**（设置）标签
3. 在左侧菜单中找到 **Pages**
4. 在 **Build and deployment** 部分：
   - **Source**：选择 `GitHub Actions`
5. 保存设置

### 3. 触发部署

启用 GitHub Pages 后，有两种方式触发部署：

#### 方式 A：自动部署（推荐）
当你推送包含以下内容的更新时，会自动触发部署：
- `docs/` 目录中的文件
- `covid_only_updated_surveillance_data.csv` 数据文件
- `generate_interactive_plot.py` 脚本

#### 方式 B：手动部署
1. 进入 **Actions** 标签
2. 选择 "部署交互式图表到 GitHub Pages" 工作流
3. 点击 **Run workflow** 按钮
4. 选择 `main` 分支
5. 点击 **Run workflow** 确认

### 4. 查看部署状态

1. 在 **Actions** 标签中查看工作流运行状态
2. 等待绿色的 ✓ 标记出现（通常需要 1-2 分钟）
3. 部署成功后，访问以下地址：
   ```
   https://<你的GitHub用户名>.github.io/<仓库名>/covid19_interactive.html
   ```

## 📝 访问链接格式

根据你的 GitHub 仓库信息，交互式图表的 URL 格式为：

```
https://<GitHub用户名>.github.io/<仓库名>/covid19_interactive.html
```

例如：
- 用户名：`dailypartita`
- 仓库名：`cn_cdc_data`
- 完整链接：`https://dailypartita.github.io/cn_cdc_data/covid19_interactive.html`

## 🔄 更新图表

每当你更新 `covid_only_updated_surveillance_data.csv` 数据文件后：

1. 运行脚本重新生成 HTML：
   ```bash
   uv run python generate_interactive_plot.py
   ```

2. 提交并推送更改：
   ```bash
   git add docs/covid19_interactive.html covid_only_updated_surveillance_data.csv
   git commit -m "更新 COVID-19 监测数据"
   git push origin main
   ```

3. GitHub Actions 会自动重新部署更新后的图表

## ⚙️ 自定义配置

### 修改图表样式

编辑 `generate_interactive_plot.py` 文件，修改以下部分：

```python
# 修改图表标题
title="新型冠状病毒（COVID-19）监测阳性率 | ILI 与 SARI（交互）"

# 修改图表高度
height=600

# 修改平滑窗口
windows = [1, 3, 5, 7]  # 可以添加更多窗口，如 [1, 2, 3, 5, 7, 14]
```

### 添加更多页面

在 `docs/` 目录中添加其他 HTML 文件，它们都会自动部署到 GitHub Pages。

## 🐛 常见问题

### Q1: 部署失败怎么办？

**检查事项：**
1. 确认 GitHub Pages 已在仓库设置中启用
2. 检查 Actions 权限：Settings → Actions → General → Workflow permissions → 选择 "Read and write permissions"
3. 查看 Actions 标签中的错误日志

### Q2: 图表显示不正常？

**解决方案：**
1. 清除浏览器缓存后重新访问
2. 确认 `docs/covid19_interactive.html` 文件存在且完整
3. 在本地运行 `generate_interactive_plot.py` 检查是否有错误

### Q3: 链接无法访问？

**检查事项：**
1. 确认 GitHub Pages 部署完成（查看 Actions 标签）
2. 等待 DNS 传播（首次启用可能需要几分钟）
3. 检查 URL 格式是否正确

### Q4: 想要自定义域名？

在仓库设置的 Pages 部分，可以配置自定义域名。详见 [GitHub 官方文档](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site)。

## 📚 更多资源

- [GitHub Pages 官方文档](https://docs.github.com/en/pages)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Plotly Python 文档](https://plotly.com/python/)

## 💡 提示

- 首次部署后，建议在 README 中更新链接为你的实际 GitHub Pages URL
- 可以在 `docs/` 目录中添加更多可视化页面
- 考虑使用 GitHub Actions 定期自动更新数据和图表

