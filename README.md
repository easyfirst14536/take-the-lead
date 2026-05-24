# SmartOffice AI - 一键语义碎纸机

智能办公原型，源于中小企业文员真实调研：文员被微信群通知、纸质记录和会议笔记中的非结构化数据淹没，需要一个简洁、一键式的归整工具。

## 项目结构

- `backend/`
  - `server.js` - Node.js 后端代理，将 Coze Agent 的流式输出转发到前端。
  - `package.json` - 后端依赖和启动脚本。
  - `.env.example` - Coze API 密钥和 Bot ID 示例。
- `frontend/`
  - `index.html` - 单页前端，使用 Tailwind CSS、原生 JS 和 marked.js 实现深蓝商务风界面。

## 智能体工作流说明

1. 前端接收用户粘贴的混乱文本。
2. 点击“语义碎纸机”按钮，前端向后端 `/api/shred` 发起请求。
3. 后端将请求转发给 Coze Agent（`https://api.coze.com/open_api/v2/chat`），并开启 `stream: true`。
4. 后端读取 Coze 返回的 SSE 分块流，提取 `type == "answer"` 中的 `content`，并通过 SSE 推送给前端。
5. 前端实时渲染 Markdown 表格草稿，完成后再生成可编辑 HTML 表格，形成“AI 生成 + 人工确认”的闭环。

## 本地运行命令

```bash
cd backend
npm install
```

创建 `.env` 文件：

```env
COZE_API_KEY=your_coze_api_key_here
COZE_BOT_ID=your_coze_bot_id_here
```

启动后端并同时提供前端静态页面：

```bash
npm start
```

打开浏览器访问：

```text
http://localhost:4000
```

## 部署上线流程

### Railway

1. 将项目仓库连接到 Railway。
2. 指定根目录为 `backend`。
3. 设置环境变量：`COZE_API_KEY`、`COZE_BOT_ID`。
4. 部署后，访问 Railway 给出的公网 URL 即可。

### Vercel

1. 在 Vercel 项目中选择部署目录为 `backend`。
2. 添加环境变量 `COZE_API_KEY` 和 `COZE_BOT_ID`。
3. 部署完成后，访问 Vercel 生成的 URL 即可。

该方案将前端静态页面与后端同一应用一起发布，方便给助教和同学直接访问。

## 关键价值点

- 降低使用门槛：用户只需粘贴文本、点击按钮，无需撰写 Prompt。
- 提升效率：实时流式展示 AI 输出，避免等待黑屏效果。
- 人机闭环：AI 生成后再由用户编辑确认，减少办公场景下的错误风险。
- 业务展示：页面预留“灯光反馈”按钮，展示未来物理世界联动的扩展构想。

## 说明

- 后端直接代理 Coze Agent 的流式 SSE 输出，前端无需直接暴露 API Key。
- 当前版本仅演示确认功能，确认后会将表格数据输出到浏览器控制台，并显示成功提示。
- 如果需要上线演示，可直接将 `backend` 目录部署到支持 Node.js 的平台。
