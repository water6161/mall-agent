# 🧳 小水 · 出行购物智能体（mall-agent）

一个基于大模型 API 编排的出行决策智能体：上传照片认景点、一句话排行程、按预算找门店、A vs B 地点对比，全部基于高德地图真实数据，绝不编造。

> 🌐 **在线体验**：部署于腾讯云 EdgeOne Pages，push 即自动构建
> 🎓 本项目为课程实践作品，欢迎交流

---

## ✨ 核心功能

| 功能 | 说明 |
|---|---|
| 📷 **景点识别** | 上传照片 → 视觉大模型（qwen3-vl-plus）识别地标 → 自动附上实时天气与周边推荐 |
| 🗓️ **行程规划** | 「帮我安排北京一日游」→ 按上午→中午→晚上生成时间轴 → 地图虚线路线 → 📅 一键导出 .ics 到手机日历（每站前 30 分钟提醒） |
| 🛍️ **购物决策** | 说需求 + 预算（如「5000 以内买个相机」）→ 高德搜真实门店 → 选购要点 + 推荐购买地点 + 加入购物清单 |
| ⚖️ **对比模式** | 「万象城和卓悦中心哪个好」→ 两列数据对比表（类型/评分/地址）+ AI 结论点评 |
| 💬 **多轮问答** | 上下文记忆的多轮对话，追问不丢信息 |

**辅助能力**：美食/酒店/景点分类搜索 · 天气联动（回复附天气 + 背景随天气变化）· 收藏夹 · 购物清单 · Leaflet 地图可视化 · Canvas 分享卡片 · 成就徽章系统 · 语音输入 · 每日运势签 · Q 版桌宠 · 首次访问新手引导 · 深色模式 · IP 限流

## 🛠️ 技术栈

```
前端：HTML + CSS + 原生 JavaScript（单文件应用，零框架）
地图：Leaflet.js（高德瓦片数据）
后端：Python 3 边缘函数（EdgeOne Pages Functions）
大模型：阿里云百炼 qwen3-vl-plus（视觉）+ 文本模型
数据源：高德 Web 服务 API（POI / 地理编码 / 天气）
        Open-Meteo（免费天气兜底）
存储：localStorage（会话 / 收藏 / 清单 / 统计，无需数据库）
部署：GitHub → EdgeOne Pages 自动构建
```

### 🏗️ 架构一句话

用户消息 → **意图识别**（大模型 JSON 分类：shopping / hotel / sightseeing / food / plan / compare / buy / spot / discover）→ 路由到对应处理器 → 高德 API 拉取真实地点数据 → 大模型基于**真实数据约束**生成回复（Prompt 中明确禁止编造数据外的地点）→ 前端渲染文本 / 表格 / 地图 / 日历文件。

> 💡 设计要点：**不训练模型、不建数据库**，通过 API 编排（Orchestration）+ 结构化意图路由 + 数据约束 Prompt，让通用大模型在真实数据上可靠工作——这是当前 LLM Agent 开发的主流范式。

## 🚀 快速开始

### 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `AMAP_KEY` | ✅ | 高德 Web 服务 API Key（[申请地址](https://console.amap.com/dev/key/app)，类型选「Web服务」） |
| `MODEL_BASE_URL` | ✅ | 文本模型 API 地址（OpenAI 兼容格式） |
| `MODEL_API_KEY` | ✅ | 文本模型 API Key |
| `MODEL_NAME` | ✅ | 文本模型名称 |
| `VISION_BASE_URL` | ⭕ | 视觉模型 API 地址（独立配置，推荐直连百炼 `https://dashscope.aliyuncs.com/compatible-mode/v1`） |
| `VISION_API_KEY` | ⭕ | 视觉模型 API Key |
| `VISION_MODEL` | ⭕ | 视觉模型名称（如 `qwen3-vl-plus`） |

### 本地运行

```bash
pip install -r requirements-local.txt
cp .env.example .env   # 填入上面的密钥
python app.py          # 打开 http://localhost:8000
```

### 部署到 EdgeOne Pages

1. Fork / Push 本仓库到 GitHub
2. 在 [腾讯云 EdgeOne Pages](https://console.cloud.tencent.com/edgeone/pages) 导入仓库
3. 在环境变量中配置上表中的 Key
4. 之后每次 `git push` 自动触发部署

详细部署说明见 [DEPLOY.md](DEPLOY.md)。

## 📁 项目结构

```
mall-agent/
├── public/index.html        # 单文件前端应用（CSS/JS/地图全部内联）
├── agents/mall-agent/
│   ├── index.py             # EdgeOne 边缘函数入口（含 IP 限流）
│   └── _core.py             # 核心逻辑：意图路由 / 高德搜索 / 天气 / 行程 / 对比 / 购物导购
├── mall_agent/              # LangGraph 框架版本（本地 Docker 运行用）
├── app.py                   # 本地 Flask 服务入口
├── edgeone.json             # EdgeOne 部署配置
└── DEPLOY.md                # 部署文档
```

## 🔒 安全设计

- 所有 API 密钥通过**环境变量**注入，代码与提交历史中不含任何真实凭据
- 后端对用户上传图片与Prompt 输出做数据约束，模型回复仅基于 API 返回的真实地点
- 内置 IP 限流（20 次 / 10 分钟），防止接口被刷

## ⚡ 性能与可靠性优化

| 优化项 | 做法 | 效果 |
|---|---|---|
| **POI 查询缓存** | 按「城市+关键词」缓存 10 分钟（进程内 TTL） | 重复提问不再打高德，省配额、降延迟 |
| **天气缓存** | 按城市缓存 30 分钟 | 一次回答里多处引用天气不重复请求 |
| **意图判定缓存** | 同一句无上下文的话 1 小时内命中缓存 | 少一次 LLM 调用 |
| **并发检索** | 「随便逛逛」这类多品类查询用线程池并发打高德 | 4 次串行外部调用 → 1 轮往返 |
| **识图置信度** | 视觉模型额外输出 `confidence`，低于 0.6 时回复里主动说明并给纠错入口 | 降低误识别被当成结论的风险 |
| **请求分级提示** | 识图请求显示「正在识别照片，通常需要 5～15 秒」+ 失败一键重试 | 长请求不再像卡死；失败无需重输 |
| **图片体验** | 上传前压缩到 1280px / JPEG 0.85，气泡图可点击放大 | 减小传输体积，看清细节 |
| **可观测性** | 关键阶段耗时打到 stderr（`[mall-agent] intent 320ms ...`） | 线上排查慢请求有据可查 |

> 说明：缓存为进程内实现，边缘函数实例复用期间有效、重启即失效，不引入额外存储依赖；
> 若后续多实例部署，可平滑替换为 Redis。

## 📌 Roadmap

- [ ] 行程分享链接（生成只读快照页）
- [ ] 公交/地铁路线接入
- [ ] 语音播报回复
- [ ] 识图链路异步化（提交任务后继续对话，完成后回填结果）
- [ ] 源码按模块拆分 + Vite 构建回单文件产物

---

⭐ 觉得不错的话欢迎点个 Star！
