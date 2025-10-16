# 🚀 交互式图表快速启动

## ⚡ 3 分钟部署交互式图表

### 第 1 步：本地预览（可选但推荐）

```bash
# 快速预览（会自动在浏览器打开）
./preview_interactive.sh

# 或手动生成
uv run python generate_interactive_plot.py
```

### 第 2 步：推送到 GitHub

```bash
git add .
git commit -m "添加交互式 COVID-19 监测图表"
git push origin main
```

### 第 3 步：启用 GitHub Pages

1. 打开 GitHub 仓库 → **Settings** → **Pages**
2. **Source** 选择 `GitHub Actions`
3. 点击保存

### 第 4 步：等待部署（1-2分钟）

访问 **Actions** 标签，等待绿色 ✓ 出现

### 第 5 步：查看你的图表 🎉

```
https://<你的用户名>.github.io/<仓库名>/covid19_interactive.html
```

## 📝 记得更新 README

将 README 中的示例链接替换为你的实际链接：

```markdown
**[🔗 点击查看实时交互式图表](https://<你的用户名>.github.io/<仓库名>/covid19_interactive.html)** ✨
```

## 🔄 日常更新流程

```bash
# 1. 更新数据
uv run python extract_surveillance_data.py ...

# 2. 重新生成图表
uv run python generate_interactive_plot.py

# 3. 提交推送
git add covid_only_updated_surveillance_data.csv docs/covid19_interactive.html
git commit -m "更新 $(date +%Y-%m-%d) 数据"
git push

# GitHub Actions 会自动部署！
```

## 📚 详细文档

- **完整指南**: [INTERACTIVE_CHART_GUIDE.md](INTERACTIVE_CHART_GUIDE.md)
- **详细设置**: [docs/SETUP.md](docs/SETUP.md)
- **主 README**: [README.md](README.md)

---

就这么简单！享受你的交互式数据可视化吧！ 🎊

