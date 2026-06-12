VoiceIn v1.0 — 极简中文语音输入工具
======================================

VoiceIn 是一个 Windows 系统托盘应用，按 Ctrl+Alt+S 开始说话，
文字自动粘贴到当前光标位置。

=== 安装 ===

1. 解压 VoiceIn-windows-amd64.zip
2. 双击 VoiceIn.exe
3. 首次运行会自动下载语音模型（约 900MB，仅一次）
4. 托盘出现灰色麦克风图标 → 气泡提示"已就绪"

=== 使用 ===

在任何应用（终端、记事本、浏览器...）：

  按 Ctrl+Alt+S → 托盘变红 → 说话 → 说完（停顿）自动粘贴文字
  按 Ctrl+Alt+S → 停止录音

  可以连续说多句，每句自动粘贴。

  右键托盘图标 → 退出

=== 修改快捷键 / 配置 ===

编辑配置文件：
  C:\Users\<用户名>\.voicein\config.json

主要配置项：
  hotkey_modifiers: 热键组合键（1=Alt, 2=Ctrl, 4=Shift, 8=Win）
  hotkey_vk: 按键码（0x53=S键）
  device_id: 麦克风设备ID（-1=默认, 0/1=第一个/第二个设备）
  engine: 识别引擎（sensevoice）
  vad_threshold: 语音检测灵敏度（0.006，环境嘈杂可调至 0.015）

=== 命令行模式（终端实时显示） ===

  cd 到程序目录，运行：
    VoiceIn.exe --cli

  说话时文字实时显示在终端，Ctrl+C 退出。

  也可查看设备列表：
    VoiceIn.exe --cli --list-devices

=== 故障排查 ===

Q: 按热键无反应？
A: 检查热键是否被其他软件占用。

Q: 识别效果差？
A: 1) 检查麦克风是否选对（config.json 的 device_id）
   2) 确保 Windows 麦克风音量够高
   3) 降低 vad_threshold 到 0.003

Q: 首次运行下载模型失败？
A: 检查网络连接，确保能访问 modelscope.cn

Q: 托盘图标无反应？
A: 尝试右键任务栏 → 任务栏设置 → 选择哪些图标显示在任务栏上 → 打开 VoiceIn

=== 技术信息 ===

  本地引擎: FunASR + SenseVoiceSmall (SenseVoice)
  识别语言: 中文
  采样率: 16000Hz
  CPU 推理: RTF ≈ 0.06（比实时快15倍）
  内存占用: ~2GB（含模型）
  磁盘占用: ~1.2GB（含运行库）
