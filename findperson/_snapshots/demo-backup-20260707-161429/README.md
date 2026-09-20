# 首问责任平台 Demo

这是一个可直接打开的静态前端 Demo，用来演示首问责任平台的核心交互。

## 快速开始

直接打开 `index.html` 即可，也可以在项目根目录启动本地服务：

```bash
python3 -m http.server 8000
```

然后访问 `http://127.0.0.1:8000/`。

## 当前能力

- 智能问答：输入问题后返回推荐人员、推荐理由和相关内容。
- 名片库：支持按关键词和三级部门筛选人员，并进入人员主页。
- 个人中心：支持维护个人资料、发布内容、查看操作手册。
- 内容管理：支持新增内容、查看内容详情、置顶和删除本人内容。
- 后台看板：展示人员规模、内容规模、推荐热度和活跃趋势。

## 项目结构

- `index.html`：页面结构入口
- `assets/main.css`：样式文件
- `assets/main.js`：交互逻辑与本地模拟数据

## 协作说明

- 当前数据来自前端内置模拟数据和 `localStorage`。
- `window.FirstResponsibilityDemo.setAnalyzer()` 可以替换问题分析逻辑。
- `window.FirstResponsibilityDemo.runMatch()` 可以作为后续前后端联调时的匹配基线。
