# 飞跃视频工具（Feiyue Video Tool）

面向投放与素材包装的 **本地视频批处理工作台**：批处理、规范命名、批量裂变。无需上传素材到云端。

## 功能

| 模块 | 说明 |
|------|------|
| **视频批处理** | 比例、水印、落版、字幕等按方案模板批量出片 |
| **规范命名** | 按品牌/语言/标签/日期等字段统一改名；日期支持 4 / 6 / 8 位与自定义；对照改名左右双栏 |
| **批量裂变** | 单源或多源，一素材挂多方案，自动建输出子文件夹 |

## 下载安装包（推荐）

在 [Releases](https://github.com/jingwenliu123456-coder/feiyue-video-tools/releases) 下载，不要从仓库里找 zip（安装包不进 git）。

### macOS（Apple Silicon / M 系列）

1. 下载 `HabiVideoTool_macOS.zip` 并解压  
2. **右键** `飞跃视频工具.app` → **打开** → 再点 **打开**（首次勿直接双击）  
3. 若被拦截：系统设置 → 隐私与安全性 → 仍要打开  

当前 Mac 包为 **arm64**，适用于 M 系列 Mac / Mac Studio / 近年 iMac。Intel Mac 需另行构建 universal 或 x64 包。

### Windows

Windows 安装包见 Releases 中的 Windows 附件（若有）。也可在 Windows 上自行打包：

```bat
build_windows.bat
```

## 从源码构建（macOS）

```bash
chmod +x build_mac.sh prepare_mac_icons.sh
./build_mac.sh
```

产物：`dist/HabiVideoTool_macOS/飞跃视频工具.app`

需本机 Python 3.10+、`.venv`、FFmpeg（脚本会检查依赖）。详见 `README_V24_Mac打包.md`。

## 字幕（可选）

- **外部 SRT 烧录**：无需额外环境（剪映/PR 导出 SRT 即可）  
- **AI 识别（Whisper）**：运行 `setup_subtitle_env_mac.sh` 一次，需联网下载模型  

## 方案模板说明

`templates/` 内 JSON 可能含开发机上的绝对路径，**仅作参数示例**。在新电脑加载后请重新选择本机水印/片尾素材路径，或另存为自己的方案。

## 开源许可

本仓库源码以 **[MIT License](LICENSE)** 发布。

- 可自由使用、修改、分发（保留版权声明）  
- 内置 **FFmpeg** 等第三方组件另有各自许可证，分发安装包时请保留其说明  

**团队定制**（字段规则、流程微调、私有化部署等）不在 MIT 自动覆盖范围内，欢迎通过 GitHub Issues 联系洽谈。

## 仓库结构（简要）

- `video_batch_tool_v24.py` — 主程序入口（V24 工作台）  
- `naming_tool.py` — 规范命名（内嵌于主程序）  
- `ui/`、`modules/`、`core/` — 界面与处理逻辑  
- `build_mac.sh`、`video_batch_tool_v24_mac.spec` — macOS 打包  

## 反馈

问题与建议：[GitHub Issues](https://github.com/jingwenliu123456-coder/feiyue-video-tools/issues)
