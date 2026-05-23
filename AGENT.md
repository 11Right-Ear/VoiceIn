# AGENT.md — AI 协作指南

## 项目简介

**VoiceIn** — 极简中文语音输入工具。Windows 系统托盘应用，按全局热键开始/停止录音，本地 Sherpa-ONNX 引擎识别中文语音，自动将文字粘贴到光标处。

**核心原则：极简第一。任何增量的复杂度必须有 10 倍的用户价值回报。**

---

## 技术栈

| 层 | 技术 | 版本要求 |
|------|------|----------|
| 音频采集 | C++ / WASAPI (Windows SDK) | MSVC 2022, CMake ≥3.16 |
| 语音识别 | Python `sherpa-onnx` | Python ≥3.10 |
| 系统托盘 | Python `pystray` + `Pillow` | 最新稳定版 |
| 全局热键 | Python `ctypes` → Win32 `RegisterHotKey` | 系统自带 |
| 剪贴板 | Python `pyperclip` | 最新稳定版 |
| 模拟按键 | Python `pyautogui` | 最新稳定版 |
| 打包 | PyInstaller | 最新稳定版 |

---

## 项目结构

```
VoiceIn/
├── AGENT.md                   # 本文件 — AI 协作指南
├── PRODUCT_SENSE.md           # 产品定义、用户画像、功能边界
├── DESIGN.md                  # 架构设计、组件接口、线程模型
├── FRONTEND.md                # 托盘 UI、交互流程、视觉设计
├── PLAN.md                    # 实施步骤、里程碑、验证标准
├── src/
│   ├── native/                # C++ WASAPI DLL
│   │   ├── CMakeLists.txt
│   │   ├── audio_capture.h
│   │   ├── audio_capture.cpp
│   │   └── ring_buffer.h       # 无锁 SPSC 环形缓冲区
│   ├── app/                   # Python 主程序
│   │   ├── main.py            # 入口
│   │   ├── orchestrator.py    # 主流程状态机
│   │   ├── audio_capture.py   # C++ DLL 的 Python 封装
│   │   ├── recognizer.py      # Sherpa-ONNX 封装
│   │   ├── hotkey.py          # 全局热键
│   │   ├── tray.py            # 托盘图标
│   │   ├── output.py          # 剪贴板 + 粘贴
│   │   └── config.py          # 配置管理
│   └── requirements.txt
├── models/                    # ASR 模型（.gitignore，首次运行下载）
├── build.py                   # 构建脚本
└── .gitignore
```

---

## 代码规范

### Python
- 类型注解：所有公开函数必须有完整的类型注解
- 命名：`snake_case` 函数和变量，`PascalCase` 类名
- 不写 docstring（类名和类型注解已足够说明）
- 仅在有跨线程通信的模块中使用 `logging`，不可用 `print`
- 错误处理：只在系统边界（文件 IO、网络请求、DLL 调用）处 try/except
- 配置由 `config.py` 统一管理，其他模块不直接读环境变量和文件

### C++
- C 风格导出接口（`extern "C"`），方便 ctypes 调用
- 所有导出的结构体固定大小（无 STL 容器）
- 命名：`snake_case` 函数，`PascalCase` 类型
- 非导出函数放在匿名命名空间或 `static`
- 编译目标：`Release`，`/MT` 静态链接 CRT
- 不抛异常跨 DLL 边界，用返回码

### 通用
- **v1 不允许增加新的第三方依赖**（pip 包或 C++ 库），除非先在 PLAN.md 中更新
- 不写注释解释"做了什么"，代码应该自解释。只在有非显而易见的约束或 workaround 时写一行注释
- 不创建独立的设计文档、分析文档、README——所有工程信息在 AGENT.md、DESIGN.md、PLAN.md 三份文件中

---

## 关键架构约束

### 线程模型（不可随意更改）

1. **主线程** = pystray 消息循环（tkinter 事件循环，不处理 Win32 消息）
2. **热键线程** = `RegisterHotKey` + `GetMessageW` 循环，收到 `WM_HOTKEY` 后通过回调通知 orchestrator
3. **音频消费线程** = 从 queue.Queue 取数据 → 喂 Sherpa-ONNX
4. **WASAPI 回调线程** = C++ 层系统驱动，只做环形缓冲区写入

跨线程通信统一用 `queue.Queue`（SPSC 场景）。不用裸锁、不用 Condition。

### 状态机

```
IDLE → RECORDING → FINALIZING → PASTING → IDLE
```

状态转换只能由 `orchestrator.py` 触发。其他模块只管自己的事，不关心全局状态。

### 配置

- 位置：`~/.voicein/config.json`
- 运行时只读
- 格式版本化（`version: 1`），方便未来迁移
- 修改配置 = 用户手动编辑 JSON 文件

---

## 常用命令

```bash
# 编译 C++ DLL
cmake -B src/native/build -S src/native
cmake --build src/native/build --config Release

# 安装 Python 依赖
pip install -r src/requirements.txt

# 运行开发模式
python src/app/main.py

# 打包
python build.py

# 清理
rm -rf src/native/build dist
```

---

## 文档体系

| 文档 | 面向读者 | 回答的问题 |
|------|----------|-----------|
| AGENT.md | AI 助手 | 如何理解项目？如何写代码？约束是什么？ |
| PRODUCT_SENSE.md | 产品/设计 | 为什么做？给谁做？不做什么？ |
| DESIGN.md | 开发者 | 架构长什么样？组件怎么通信？为什么这样设计？ |
| FRONTEND.md | 前端/UX | 用户看到什么？状态如何变化？交互怎么设计？ |
| PLAN.md | 项目管理 | 按什么顺序做？每步验证什么？风险在哪？ |

---

## v1 红线（不可越过的约束）

1. **不引入新的第三方依赖**，除非在 PLAN.md 中更新并说明理由
2. **不弹窗口**（About 窗口除外）— 所有反馈通过托盘图标和通知气泡
3. **不存储任何用户数据**——不存录音、不存识别历史、不存日志
4. **安装包 < 50MB**（不含模型文件）
5. **运行时内存 < 200MB**
6. **不修改除了 ~/.voicein/ 以外的任何文件**

---

## 当被要求做改动时

### 优先查阅顺序
1. `PRODUCT_SENSE.md` — 这个改动应该做吗？
2. `DESIGN.md` — 这个改动放在哪里？
3. `FRONTEND.md` — 这个改动影响用户交互吗？
4. `PLAN.md` — 现在该做这个吗？在哪个 Step 里？

### 改动检查清单
- [ ] 是否与产品定位一致（极简、中文语音输入）？
- [ ] 是否增加了 v1 不该有的依赖？
- [ ] 是否破坏了四线程模型？
- [ ] 是否需要在 AGENT.md 更新约束？
- [ ] 是否需要更新 PLAN.md 的验证步骤？
- [ ] 用户没有明确要求的功能不该加
