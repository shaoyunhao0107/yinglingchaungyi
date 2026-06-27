# Monica Chat UI

一个对接 [monica-proxy](../) 的聊天界面：React + TypeScript + Tailwind + shadcn 风格组件，底层走代理的 OpenAI 兼容接口（`/v1/chat/completions`、`/v1/models`）。

## 功能（v1）

- 流式聊天（SSE，实时输出 + 停止生成）
- 模型下拉选择（从 `/v1/models` 动态拉取，可搜索）
- Markdown 渲染 + 代码高亮 + 代码块一键复制
- 推理模型的 `<think>...</think>` 渲染为可折叠"思考过程"
- 连接设置（Base URL + Bearer Token，仅存本地 localStorage）

> 单会话、内存保存，刷新即清空。多会话历史 / System Prompt / 图片生成留作后续版本。

## 开发运行

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

首次打开会弹出「连接设置」，填写：

- **Base URL**：`http://localhost:8080/v1`（你的 monica-proxy 地址，需以 `/v1` 结尾）
- **Bearer Token**：代理配置里的 `BEARER_TOKEN`

> 代理已开启 CORS，开发服务器（5173）可直接跨域调用 8080，无需额外配置。

## 构建 / 测试

```bash
npm run build        # 类型检查 + 生产构建到 dist/
npm run preview      # 本地预览构建产物
npm test             # 运行单元测试（vitest）
```

## 目录结构

```
src/
├─ App.tsx                 顶部栏（模型下拉 + 设置）+ 布局
├─ components/
│  ├─ ChatView.tsx         消息区 + 输入区 + 自动滚动
│  ├─ MessageList.tsx      消息列表
│  ├─ MessageBubble.tsx    气泡：用户 / 助手 / 错误 / think 折叠
│  ├─ Markdown.tsx         react-markdown + 高亮 + 复制
│  ├─ Composer.tsx         输入框（Enter 发送、Shift+Enter 换行、IME 友好）
│  ├─ ModelSelector.tsx    模型下拉（Popover + Command 搜索）
│  ├─ SettingsDialog.tsx   连接设置弹窗
│  └─ ui/                  shadcn 风格基础组件
├─ hooks/useChat.ts        会话状态 + 流式累加 + AbortController 停止
└─ lib/
   ├─ client.ts            openai SDK 流式 + 模型列表 fetch
   ├─ settings.ts          localStorage 读写
   ├─ think.ts             <think> 片段拆分（含单测）
   └─ utils.ts             cn()
```
