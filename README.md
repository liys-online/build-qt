# build-qt-ohos (Qt for OHOS 一键构建脚本)

一个用于在 Windows/Linux/macOS 上自动化构建 Qt for OpenHarmony（OHOS）的工具集：
- 自动克隆 Qt 源码和 OHOS 补丁仓库，并应用补丁
- 自动检查/安装构建依赖（Windows 下可自动下载 Perl、MinGW；各平台可自动下载 OHOS SDK）
- 一条命令完成 configure/build/install，并可打包产物
- 支持 Qt 5.15.12 ，支持 arm64-v8a/armeabi-v7a/x86_64

本文档依据仓库代码与 `configure.json` 整理，覆盖从准备环境到产物打包的完整流程。

---

## 功能简介
本项目通过 `build-qt-ohos.py` 提供以下能力：
- init：
  - 克隆 Qt 源码仓库（可选浅克隆/指定分支或 tag）
  - 克隆 Qt for OHOS 补丁仓库
  - 自动应用对应版本的补丁（并复制 qtohextras 模块）
- env_check：
  - 自动检测 Perl/MinGW（Windows）、make/Perl（Linux/macOS）
  - 自动下载/解压缺失组件（Windows：Perl/MinGW；各平台：OHOS SDK native 包）
  - 设置 `OHOS_SDK_PATH` 环境变量
- 构建阶段：configure/build/install/clean/all/print_build_info
- 打包：将安装前缀目录打包为 zip（Windows）或 tar.gz（Linux/macOS）

核心模块：
- `build_qt/qt_repo.py`：Git 操作与补丁应用
- `build_qt/config.py`：配置、环境检测与依赖下载
- `build_qt/qt_build.py`：调用 Qt configure/make/make install
- `build_qt/utils.py`：下载、校验、解压与打包
- `build_qt/ohos_sdk_downloader.py`：从官方接口拉取并下载 OHOS SDK


## 支持平台
- Windows 10/11（推荐）
- Linux 发行版（需编译工具链）
- macOS（需 Xcode/Command Line Tools）

脚本会根据平台选择合适的 `make` 工具：
- Windows：`mingw32-make`
- Linux/macOS：`make`


## 先决条件
- Python 3.8+（建议 3.10+）
- Git 命令行（脚本通过 GitPython/系统 git 调用）
- 网络可访问以下源：
  - Qt 源码与补丁仓库（默认 GitCode 镜像）
  - 依赖组件下载（Perl/MinGW 预编译包、OHOS SDK 官方接口）
- 充足磁盘空间：
  - Qt 源码 + 构建中间文件 + 安装产物，建议预留 20GB 以上


## 安装依赖
在项目根目录执行：

```cmd
python -m pip install -r requirements.txt
```

包含：requests、GitPython、questionary、rich、py7zr。


## 快速上手
以下以 Windows cmd 为例（Linux/macOS 命令相同，仅输出格式略有差异）：

1) 初始化仓库并应用补丁（首次执行会创建/询问用户配置）
```cmd
python build-qt-ohos.py --init
```

2) 检查并准备开发环境（Windows 会自动下载 Perl/MinGW；任何平台会下载 OHOS SDK native 包）
```cmd
python build-qt-ohos.py --env_check
```

3) 一条命令完成配置、编译、安装，并打包产物
```cmd
python build-qt-ohos.py --exe_stage all --with_pack
```

构建完成的安装目录和压缩包位置见下文“构建输出与打包”。


## 详细命令
`build-qt-ohos.py` 支持以下参数（来自脚本源码）：
- `--init`：初始化 Qt 仓库并应用补丁
- `--env_check`：检查并准备开发环境
- `--reset_repo`：重置 Qt 源码与所有子模块（git reset --hard/clean），并重新应用补丁
- `--update_commit_hash`：更新 commit_hash 文件，获取 Build 仓库的最新提交 hash
- `--exe_stage {configure|build|install|clean|all|print_build_info}`：执行指定阶段
  - `configure`：调用 Qt 的 `configure(.bat)` 生成构建配置
  - `build`：调用 `make -jN` 或 `mingw32-make -jN`
  - `install`：`make install`
  - `clean`：仅删除构建目录（不触碰源码）
  - `all`：依次执行 configure/build/install
  - `print_build_info`：打印当前构建参数与路径
- `--with_pack`：在安装完成后打包产物
- `--use_github`：使用 GitHub 地址（默认使用 GitCode 地址）

常用组合示例：
```cmd
:: 更新 commit_hash 文件（获取 Build 仓库最新提交）
python build-qt-ohos.py --update_commit_hash --use_github

:: 配置
python build-qt-ohos.py --exe_stage configure

:: 构建（使用配置中的并行任务数）
python build-qt-ohos.py --exe_stage build

:: 安装
python build-qt-ohos.py --exe_stage install

:: 打包
python build-qt-ohos.py --exe_stage install --with_pack

:: 一次性构建 + 打包
python build-qt-ohos.py --exe_stage all --with_pack

:: 查看当前构建信息
python build-qt-ohos.py --exe_stage print_build_info

:: 清理构建目录
python build-qt-ohos.py --exe_stage clean

:: 重置源码并重新应用补丁（会丢弃未提交修改）
python build-qt-ohos.py --reset_repo
```


## 配置说明
项目提供两级配置：
- 全局配置：`configure.json`（随仓库提供，不要直接改动默认值，除非知道自己在做什么）
- 用户配置：`configure.json.user`（首次交互式生成；如需修改，建议编辑此文件）

首次运行时，如果终端为交互模式，脚本会通过 questionary 弹出问答，生成 `configure.json.user`。

关键配置项（位于 `config` 段，用户配置会覆盖全局配置）：
- `working_dir`：工作目录，默认 `${pwd}/work`（`${pwd}` 为本仓库根）
- `perl`（Windows 默认会自动下载到 `${pwd}/work/perl/bin`）
- `mingw`（Windows 默认会自动下载到 `${pwd}/work/mingw/bin`）
- `ohos_sdk`：OHOS SDK 解压目标目录，支持 `${ohos_version}` 占位
- `ohos_version`：OHOS SDK 的 apiVersion（例如 15）
- `build_type`：`release` 或 `debug`
- `build_ohos_abi`：`arm64-v8a`、`armeabi-v7a`、`x86_64`
- `build_qt_tag`：支持 `v5.15.12-lts-lgpl` 或 `v6.5.6-lts-lgpl`
- `clone_depth`：源码浅克隆深度，建议 1（0 为完整克隆）
- `jobs`：并行编译任务数，建议不超过 CPU 物理核心数
- `verbose`：是否在 Qt configure 中开启 `-verbose`

仓库/依赖（来自 `repositories` 与 `dependencies` 段）：
- Qt 源码：`https://gitcode.com/qtforohos/qt5.git`
- Qt OHOS 补丁：`https://gitcode.com/openharmony-sig/qt.git`
- Perl/MinGW（Windows 预编译包，托管于 GitCode Releases）
- OHOS SDK 列表接口：`https://repo.harmonyos.com/sdkmanager/v5/ohos/getSdkList`

Qt configure 选项（来自 `qt-config` 段，脚本自动拼装）：
- `-opensource -confirm-license`（或 `-commercial`）
- `-platform <win32-g++|linux-g++|macx-clang>`（按宿主系统自动选择）
- `-xplatform oh-clang`（面向 OHOS 交叉编译）
- OpenGL：`-opengl es2`，可选附加 `-opengles3`
- 其他：`-no-dbus`、`-disable-rpath`、`-nomake tests -nomake examples`
- 每个受支持 Qt 版本还会附带相应 `-skip` 模块列表（详见 `configure.json`）


## 构建输出与打包
目录约定（均可从 `print_build_info` 查看）：
- Qt 源码目录：`{working_dir}/qt5`
- 构建目录：`{working_dir}/qt5/build/{release|debug}`
- 安装前缀（prefix）：`{working_dir}/output/Qt{QtVer}-ohos{OHOSVer}-{ABI}`
- 打包位置：`{working_dir}/output/Qt{QtVer}_OHOS{OHOSVer}_{ABI}_{os}.{zip|tar.gz}`
  - Windows 打包为 `.zip`
  - Linux/macOS 打包为 `.tar.gz`

示例：`output/Qt5.15.12-ohos15-arm64-v8a/` 与 `output/Qt5.15.12_OHOS15_arm64-v8a_windows.zip`


## 常见问题与排查
- Git 不可用/未安装
  - 请先安装 Git，并确保 `git --version` 正常。
- Windows 自动安装 Perl/MinGW 失败
  - 检查网络与磁盘空间；删除 `work/.temp` 后重试 `--env_check`。
- OHOS SDK 下载失败或校验失败
  - 接口访问可能受网络限制；重试或更换网络。
- `--reset_repo` 会清除本地改动
  - 该命令执行 `git reset --hard` + `git clean -fdx`，请谨慎使用。
- 补丁应用失败
  - 脚本会先对主仓库与子模块执行 reset/clean，然后按版本目录（例如 `patch/v5.15.12`）依次 `git apply`。若仓库状态异常，建议先 `--reset_repo` 再 `--init`。
- Linux/macOS 缺少构建工具
  - Linux：`sudo apt-get update && sudo apt-get install build-essential`
  - macOS：从 App Store 安装 Xcode 或安装 Command Line Tools
- Windows 路径过长
  - 建议将 `working_dir` 配置到路径较短的位置，例如 `D:\qt-work`。


## 致谢
- 本项目依赖的python开源库：GitPython、Requests、Questionary、Rich、py7zr
- 本项目应用的的第三方python代码：[ziptools](https://learning-python.com/ziptools/ziptools/_README.html)

### 反馈与建议

#### Bug报告

请通过以下方式报告问题：

- **OpenHarmony SIG Qt Issues**：[Qt OpenHarmony Issues](https://gitcode.com/openharmony-sig/qt/issues)

报告模板：

```markdown
## Bug描述
简要描述遇到的问题

## 复现步骤
1. 步骤一
2. 步骤二
3. 步骤三

## 期望行为
描述期望的正确行为

## 实际行为
描述实际发生的行为

## 环境信息
- Qt版本：
- OpenHarmony版本：

## 附加信息
- 错误日志
- 截图（如适用）
```

#### 功能建议

欢迎提交功能建议和改进建议：

#### BUG反馈

如果您发现该项目中的错误或有改进建议：

- 欢迎在OpenHarmony SIG Qt社区提交Issue，本项目仓库只做更新不处理Issue

---

## 附录

---

*本项目将持续更新。*

#### 免责说明

- 使用 OpenHarmony SIG Qt 提供的补丁编译的SDK 产生的任何问题，请通过 [OpenHarmony SIG Qt](https://gitcode.com/openharmony-sig/qt) 社区寻求帮助
- 建议在生产环境使用前进行充分测试验证

**最后更新**: 2025年10月14日  

**适用版本**: Qt for OpenHarmony (基于Qt 5.15) & OpenHarmony API 15 (5.0.3)+

