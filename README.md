# 🏢 AI 人设剧情生成器

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Streamlit-1.30+-red.svg" alt="Streamlit Version">
  <img src="https://img.shields.io/badge/通义千问-API-yellow.svg" alt="Tongyi Qwen">
</div>

<br>

一个基于大模型的 AI 工具，支持角色人设创建、剧情大纲生成、多章节内容自动续写。

## ✨ 项目简介
这是一个 Streamlit 应用，你可以：
- 🧑‍🎭 创建自定义角色档案，设定性格、背景故事
- 📖 自动生成角色的开场问候、故事大纲和章节内容
- 🖼️ 支持图片输入，生成和角色匹配的互动内容

## 🚀 快速开始

### 1. 环境准备
#### 安装 Python 3.10+
1.官网下载：https://www.python.org/downloads/windows/
  选择 Python 3.10 及以上（推荐 3.10/3.11）64 位离线安装包。
2.运行安装程序，务必勾选：
   - ✅ Add Python to PATH（加到系统环境变量）
   - ✅ Install pip（包管理工具）
3.建议选择 Customize Installation，安装路径选：
  D:\Python310
4.安装完成后，打开 CMD 验证：
```bash
  python --version
```

#### 安装 PyCharm（推荐社区版）
1.官网下载：https://www.jetbrains.com/pycharm/download/
  下载 PyCharm Community Edition（免费）
2.安装时勾选（关键）：
   - ✅ Create Desktop Shortcut（桌面快捷方式）
   - ✅ Update PATH variable（加到环境变量）
   - ✅ Associate .py files（关联 Python 文件）
3.安装路径建议：
D:\JetBrains\PyCharmCommunity
4.首次打开选择 Do not import settings 即可。
  
#### 阿里云 DashScope 通义千问 API 密钥（需自行申请：[阿里云百炼](https://dashscope.console.aliyun.com/)）

### 2. API 密钥配置
#### Windows 系统配置步骤
1. 右键桌面「此电脑」→ 选择「属性」；
2. 点击左侧「高级系统设置」→ 弹出「系统属性」窗口，切换到「高级」标签；
3. 点击「环境变量」→ 在「用户变量」区域（仅当前用户生效，推荐）点击「新建」；
4. 「变量名」输入：`DASHSCOPE_API_KEY`（必须完全一致，大小写敏感）；
5. 「变量值」输入：你的阿里云通义千问 API 密钥（从阿里云百炼控制台获取）；
6. 点击「确定」保存所有窗口，**重启你的终端/IDE**（如 PyCharm、VS Code）；
7. 验证：打开新终端，输入 `echo %DASHSCOPE_API_KEY%`，能看到密钥则配置成功。

#### Mac/Linux 系统配置步骤
1. 打开终端（Terminal）；
2. 编辑环境变量配置文件（根据你的 Shell 选择，Mac 新版默认 zsh）：
   - zsh 用户：`vi ~/.zshrc`
   - bash 用户：`vi ~/.bashrc`
3. 在文件末尾新增一行（替换为你的密钥）：
   ```bash
   export DASHSCOPE_API_KEY=你的阿里云通义千问API密钥
   ```
4. 保存并退出 vi 编辑器：按 Esc → 输入 :wq → 回车；
5. 让配置生效：
   - zsh 用户：source ~/.zshrc
   - bash 用户：source ~/.bashrc
6. 验证：终端输入 echo $DASHSCOPE_API_KEY，能看到密钥则配置成功；
7. 重启 IDE / 终端，即可正常运行项目。
### 3. 安装依赖
```bash
# 克隆仓库
git clone https://github.com/LXingzhao/RAG-Langchain.git
cd RAG-Langchain

# 安装项目所有依赖
pip install -r requirements.txt 
```
### 4. 项目运行
#### 启动文件上传界面（构建知识库）
上传相关文档（PDF/Word/TXT），系统自动解析并入库
单次只能上传一份文件，若有多份文件需上传，请上传多次。
```bash
streamlit run app_file_uploader.py
```
![文件上传到数据库](images/上传文件到数据库.jpg)

#### 启动问答界面
```bash
streamlit run app_qa.py
```
![智能顾问运行示例](images/智能顾问运行示例.jpg)

## 📁 项目结构
```
Character_Agent/
├── app.py               # 主界面入口
├── functions.py         # 核心功能函数
├── prompts.py           # 大模型提示词模板
├── requirements.txt     # 依赖列表
├── .gitignore           # Git忽略配置
└── LICENSE              # 开源协议
```
## 🧩 核心流程
1. 文字描述或上传图片 
2. 生成人设、开场白、剧情

## ⚠️ 注意事项
1. 确保 API 密钥配置后重启终端 / IDE，否则项目无法读取环境变量。  
