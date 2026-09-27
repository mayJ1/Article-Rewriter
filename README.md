# Article Rewriter｜文章深度改写 Skill

一个面向主流 AI Agent 的文章改写 Skill。支持直接粘贴文字，以及读取 TXT、Markdown、DOCX 文档，通过小猫零AI的付费 API 完成整篇改写。

> 本项目不是独立改写模型，也不是小猫零AI官方产品。核心改写结果由小猫零AI API 生成；本项目负责文件读取、参数配置、异步任务处理、多 Agent 适配和结果交付。

项目重点优化文章的自然表达、句式变化和可读性，适用于 AI 文章、文案及合规的论文语言润色，并面向朱雀等 AI 内容检测场景进行优化。

> 检测平台的模型和规则会持续变化，实际结果也会受到原文质量、文章长度和改写强度影响。本项目不承诺每篇内容都能 100% 通过任何检测工具。

## 功能特点

- 支持聊天框直接提交文字
- 支持 `.txt`、`.md`、`.docx` 文档
- 改写强度支持 `0–9`，默认强度为 `5`
- 一篇文章作为一个完整任务提交，不自动分段
- 支持异步任务轮询、恢复和取消
- DOCX 输入可生成新的 DOCX 文件，不覆盖原文件
- 首次使用自动生成 `config.yaml`
- 检测乱码和异常 Markdown，减少损坏结果直接交付
- 改写成功后只输出文章正文，不附加无关说明

## 支持的平台

本项目采用通用的 `SKILL.md + scripts + references` 目录结构，适合具备本地 Skill、Python 脚本执行、文件访问和 HTTPS 请求能力的 Agent。

| 平台 | 支持情况 | 安装说明 |
| --- | --- | --- |
| [Codex](https://developers.openai.com/docs/build-skills) | 支持 | 将项目目录放入 Codex 用户级 Skills 目录 |
| [Claude Code](https://code.claude.com/docs/zh-CN/skills) | 支持 | 放入用户级或项目级 `.claude/skills/` 目录 |
| [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market) | 支持 | 在技能页面选择“上传技能”，导入本地 Skill ZIP 包 |
| 豆包电脑版 | 条件支持 | 当前版本需支持导入本地 Skill，并允许执行 Python 和访问外部接口 |
| 其他 Agent | 条件支持 | 满足下方运行条件即可适配 |

不同 Agent 版本的能力可能不同。若平台不支持本地脚本、文件访问或外部 HTTPS 请求，仅复制本项目目录无法增加这些底层能力，需要按照对应平台的插件、MCP 或扩展机制进行适配。

## 运行条件

- Python 3.10 或更高版本
- 可以访问云端改写接口
- 拥有有效的改写 API Key
- Agent 已获得读取输入文件、运行 Python 和联网请求的权限

脚本仅使用 Python 标准库，不需要安装额外的 Python 依赖。

## 安装方法

### Codex

克隆仓库：

```bash
git clone https://github.com/mayJ1/Article-Rewriter.git
```

将仓库目录复制到 Codex 的用户级 Skills 目录，并确保最终结构类似：

```text
~/.codex/skills/article-rewriter/SKILL.md
```

重新开始一个 Codex 对话后，可以使用：

```text
$article-rewriter
```

### Claude Code

将项目复制到用户级目录：

```text
~/.claude/skills/article-rewriter/
```

或者放进当前项目：

```text
项目目录/.claude/skills/article-rewriter/
```

之后通过 `/article-rewriter` 调用，或直接向 Claude 描述文章改写需求。

### WorkBuddy

1. 下载本仓库代码。
2. 将包含 `SKILL.md` 的项目目录压缩为 ZIP。
3. 打开 WorkBuddy 的技能页面。
4. 选择“上传技能”，导入 ZIP 包。
5. 检查并授权文件读取、Python 执行和网络访问权限。

### 豆包电脑版及其他 Agent

如果当前版本提供本地 Skill 导入功能，可导入完整项目目录。平台还必须允许 Skill 调用 Python 3、读取用户文件并访问外部 HTTPS 接口；缺少任意一项时，需要制作该平台专用适配版本。

## 配置 API Key

本 Skill 使用小猫零AI的付费 API，使用前需要自行购买并配置有效的 API Key：

**购买与创建 API Key：** [https://www.qqat.cn?agent=N3K4ZWWE](https://www.qqat.cn?agent=N3K4ZWWE)

配置步骤：

1. 打开上方链接，注册或登录小猫零AI。
2. 在 API 控制台购买适合自己的 API 套餐。
3. 创建 API Key，并立即妥善保存完整密钥；完整密钥可能只显示一次。
4. 首次运行本 Skill，让脚本自动生成本机的 `config.yaml`。
5. 打开配置文件，将密钥填写到 `api_key` 后保存。

首次调用时，脚本会自动生成配置文件：

- Windows：`%APPDATA%\article-rewriter\config.yaml`
- macOS / Linux：`~/.config/article-rewriter/config.yaml`
- 设置了 `XDG_CONFIG_HOME` 时：`$XDG_CONFIG_HOME/article-rewriter/config.yaml`

打开文件并填写：

```yaml
api_key: "在这里填写购买的 API Key"
```

请勿把自己的 API Key 提交到 GitHub、发到公开聊天或交给他人共享使用。

## 使用示例

直接提交文章并指定强度：

```text
使用 article-rewriter，把下面这篇文章按强度 5 改写：
……文章正文……
```

提交文档：

```text
使用 article-rewriter，把 article.docx 按强度 7 改写。
```

没有指定强度时，Agent 会询问使用 `0–9` 中的哪个等级，默认值为 `5`。

## 接口与计费说明

- 改写由小猫零AI的付费云端 API 完成，并非本地免费模型或本项目自研模型。
- 输入和输出会按照接口实际计费规则产生费用。
- Skill 不包含任何公共或共享 API Key，每位用户都应通过上方链接自行购买并配置自己的 Key。
- 文章正文会发送到第三方改写服务处理，请勿提交没有处理权限的敏感、机密或个人隐私内容。
- 网络中断后可使用任务 ID 恢复查询；不会自动创建第二个付费任务。

## 适用内容

- AI 生成文章的自然化改写
- 自媒体文章、公众号文章和营销文案
- 小说、故事及其他长文本
- 经作者或权利人授权的内容改写
- 论文措辞、语法和可读性润色

论文相关用途仅限合法合规的语言润色，不得用于代写、伪造研究成果、隐瞒 AI 使用情况或规避学校和期刊的学术诚信要求。

## 远程部署与技术支持

API Key 请通过 [小猫零AI购买页面](https://www.qqat.cn?agent=N3K4ZWWE)自行购买和配置。

如果需要付费远程协助部署、安装、配置，可以添加微信：

```text
mayj4895126
```

添加时可以备注：`文章改写 Skill 远程部署`。

微信仅提供部署、安装、配置和平台适配服务，不再代售 API Key。远程协助前请自行准备有效的 API Key；请勿通过微信或普通聊天消息发送完整密钥。

## 项目结构

```text
Article-Rewriter/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── api-behavior.md
│   └── compatibility.md
└── scripts/
    └── rewrite_article.py
```

## 开源许可

本项目采用 [MIT License](LICENSE) 开源。开源许可仅覆盖本仓库代码，不包含第三方改写接口、API 余额或付费服务。
