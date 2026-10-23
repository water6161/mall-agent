# 小水 · 出行决策助手 — 部署说明

支持三种部署方式：Docker（推荐）、宝塔面板、Linux 直跑。

## 0. 准备配置

项目根目录需要 `.env` 文件（可复制 `.env.example` 修改）：

```env
OPENAI_API_KEY=你的大模型Key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-turbo
AMAP_KEY=你的高德Web服务Key
# 可选：交互地图
# AMAP_JS_KEY=高德JS_Key
# AMAP_SECURITY_CODE=高德安全密钥
# 可选：图片识别
# VISION_MODEL=qwen3-vl-plus
# 可选：视觉模型独立网关（EdgeOne 部署时必配，让识图直连百炼）
# VISION_BASE_URL=https://llm-xxxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
# VISION_API_KEY=你的百炼APIKey
```

---

## 方式一：Docker Compose（推荐）

服务器装好 Docker + Docker Compose 插件后：

```bash
# 1. 上传代码到服务器（含 .env）
cd /opt/xiaotu

# 2. 构建并后台启动
docker compose up -d --build

# 3. 查看日志
docker compose logs -f
```

访问 `http://服务器IP:7860` 即可。

常用命令：

```bash
docker compose restart      # 重启
docker compose down         # 停止
docker compose up -d --build  # 更新代码后重新构建
```

对话历史存在宿主机 `./data/chat.db`，生成图片在 `./generated/`，容器重建不丢失，注意定期备份。

---

## 方式二：宝塔面板部署

### A. 用 Docker（最简单）

1. 宝塔面板 → 「Docker」菜单（未安装则按提示安装）
2. 「Compose」→「添加 Compose」：
   - 名称：`xiaotu`
   - 路径：`/opt/xiaotu`
   - 把本项目全部文件上传到该目录（`.env` 也要传）
   - 用默认的 `docker-compose.yml`，点「确定 / 启动」
3. 防火墙 / 安全组放行 **7860** 端口
4. 浏览器访问 `http://服务器IP:7860`

### B. 用 Python 项目管理器（不用 Docker）

1. 软件商店安装：**Python 项目管理器**、**Nginx**
2. 「Python 项目管理器」→「项目」→「添加项目」：
   - 项目名称：xiaotu
   - 路径：上传代码的目录，如 `/www/wwwroot/xiaotu`
   - Python 版本：**3.10 及以上**
   - 框架：`其他`
   - 启动方式：`python app.py`
   - 端口：`7860`
   - 安装依赖：在项目终端里执行
     ```bash
     pip install -r requirements-local.txt -i https://mirrors.aliyun.com/pypi/simple/
     ```
3. 网站 → 添加站点（绑定你的域名，如 `xiaotu.example.com`），不要创建数据库
4. 进入该站点设置 →「反向代理」→「添加反向代理」：
   - 代理名称：xiaotu
   - 目标URL：`http://127.0.0.1:7860`
   - 发送域名：`$host`
5. SSL：站点设置 → Let's Encrypt 申请免费证书，开启「强制 HTTPS」
6. 云服务器安全组和宝塔防火墙都要放行 80 / 443（7860 不用对外开）

访问域名即可使用。

---

## 方式三：Linux 直跑（systemd 常驻）

适合不想装 Docker / 宝塔的干净系统（Ubuntu / Debian）：

```bash
# 1. 安装 Python（3.10+）
apt update && apt install -y python3 python3-pip python3-venv

# 2. 放置代码
mkdir -p /opt/xiaotu && cd /opt/xiaotu
# （把项目文件传到这里，包含 .env）

# 3. 虚拟环境 + 依赖
python3 -m venv venv
./venv/bin/pip install -r requirements-local.txt -i https://mirrors.aliyun.com/pypi/simple/
```

创建服务文件 `/etc/systemd/system/xiaotu.service`：

```ini
[Unit]
Description=Xiaotu Travel Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/xiaotu
ExecStart=/opt/xiaotu/venv/bin/python app.py
Restart=always
RestartSec=5
Environment=DEV_MODE=0

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启：

```bash
systemctl daemon-reload
systemctl enable --now xiaotu
systemctl status xiaotu
journalctl -u xiaotu -f   # 看日志
```

再用 Nginx 反代到 80/443（参考方式二第 4、5 步）。

---

## 运维提示

| 事项 | 说明 |
|---|---|
| 备份 | 备份 `.env`、`data/chat.db`、`generated/` 即可 |
| 修改 Key | 改 `.env` 后 `docker compose restart` 或 `systemctl restart xiaotu` |
| 升级代码 | Docker：`docker compose up -d --build`；直跑：替换文件后重启服务 |
| 日志位置 | Docker：`docker compose logs`；systemd：`journalctl -u xiaotu` |
| 端口冲突 | 修改 `.env` 里的 `PORT`（Docker 同时改 compose 的端口映射） |
| 安全建议 | 生产环境务必 `DEV_MODE=0`，并通过 Nginx + HTTPS 访问，不要裸露 7860 |
