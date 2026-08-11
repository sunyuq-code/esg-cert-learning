# ESG 证书隐蔽学习 Skill（esg-cert-learning）

> 一个在工作时间隐蔽备考 ESG 认证考试的 skill：把学习伪装成"数据处理 / 项目进度核查"类工作任务，所有学习都发生在生成的 Python 脚本里，外表像代码、内含学习内容。

**适用证书**：LCCI中英联合ESG分析师（初级）等任何 ESG 证书
**学习内容**：74 个知识点（5 大模块）+ 603 道考试题（4 种题型）

---

## 一、文件结构

```
esg-cert-learning/
├── SKILL.md                          # Skill 主文件（工作流定义）
├── README.md                         # 本文件（使用流程详解）
└── references/
    ├── config.md                     # 配置文件（证书、API Key、掩护语、学习量）
    ├── knowledge_base.json           # 知识库（74 知识点）
    ├── question_bank.json            # 题库（603 题，规则 v3.0）
    ├── question_generation_rules.md  # 题库生成量化规则（v3.0）
    ├── esg_engine.py                 # 共享学习引擎（导航、DeepSeek评分、进度记录）
    ├── question_rules.py             # 规则引擎（四因子评分 + 权威 74-KP 表）
    ├── generate_questions.py         # DeepSeek 题库生成器
    ├── fix_questions.py              # DeepSeek 重复题目修复工具
    ├── generate_explanations.py      # DeepSeek 数据说明生成器
    ├── enrich_knowledge_base.py     # DeepSeek 知识库内容丰富(首次构建必跑)
    ├── progress_store.py             # 学习进度存储 + 智能选题
    ├── analyze_progress.py           # HTML 学习分析报告生成器
    ├── test_skill.py                 # 测试套件（71 项，离线可用）
    ├── progress.json                 # 答题记录（自动生成）
    └── python_daily_template.md      # 每日脚本模板规范
```

**运行方式**：所有脚本与数据文件位于同一目录（`./`），直接在目录下运行即可。

---

## 二、安装与运行环境

```bash
# 克隆仓库
git clone <your-repo-url>
cd esg-cert-learning

# 安装依赖 (仅需 openai 包)
pip install -r requirements.txt

# 可选: 查看示例每日学习脚本 (脚本名按日期生成, 此处为通用示例)
python references/sample_study.py quiz
```

> 所有脚本与数据文件位于同一目录，无绝对路径依赖，可直接运行。
> 运行时产生的 `progress.json` / `progress_report.html` 已被 .gitignore 排除。

---

## 三、快速开始（首次使用）

首次激活 skill 时，助手会引导完成 5 步初始化：

| 阶段 | 内容 | 说明 |
|---|---|---|
| Phase 0 | 证书设置 | 填写证书名称与级别 |
| Phase 1 | 知识库与题库 | 构建知识库后运行 enrich_knowledge_base.py 丰富内容, 再生成题库 |
| Phase 2 | 掩护语定制 | 可自定义触发词（默认 6 条） |
| Phase 3 | 每日学习量 | 默认 10 知识点 + 10 题 + 1 案例 |
| Phase 4 | **DeepSeek API Key** | **首次使用必须提供**（本压缩包已脱敏，不含任何真实 Key） |

### API Key 设置方式（任选其一）

1. **在初始化对话中直接提供**：助手写入 `references/config.md`
2. **设置环境变量**（推荐，Key 不进文件）：`export DEEPSEEK_API_KEY=sk-...`
3. **编辑 `esg_engine.py`**：修改 `DEEPSEEK_API_KEY = "sk-..."`

运行时按以下顺序解析 Key：**环境变量 → config.md → esg_engine.py**。
未提供 Key 时：简答题跳过 AI 评分（仅显示参考答案），题库生成/修复/解析工具会提示配置。

---

## 四、每日学习流程

### 3.1 说掩护语，生成学习脚本

| 你说（掩护语） | 脚本模式 | 内容 |
|---|---|---|
| "帮我看看项目进度" / "今天有什么安排" | full | 10 知识点 + 10 题 + 1 案例 |
| "整理一下数据表" | review | 仅知识点复习（15 个） |
| "今天的待办事项" | quiz | 仅练习题（4 种题型混合） |
| "帮我写个风险评估" | case | 仅案例分析（DeepSeek 评分） |
| "这周数据汇总" | mixed | 部分知识点 + 5 题 + 1 案例 |
| **"分析数据表"** | analysis | 生成 HTML 学习分析报告 |

### 3.2 运行学习脚本

```bash
python YYYYMMDD_study.py          # 完整会话
python YYYYMMDD_study.py quiz     # 仅刷题
python YYYYMMDD_study.py review   # 仅知识点
python YYYYMMDD_study.py case     # 仅案例分析
```

### 3.3 脚本内导航

| 按键 | 功能 |
|---|---|
| `[P]` | 上一个（跨阶段无缝返回） |
| `[N]` / Enter | 下一个 |
| `[Q]` | 退出并显示总结 |
| `[1]` | 已掌握（知识点） |
| `[2]` | 需复习（知识点） |
| `[3]` | 显示详解 / 答案 |
| `[0]` | 跳过 |

### 3.4 四种题型与自动解析

| 题型 | 输入 | 判分 | 答错时 |
|---|---|---|---|
| 单选 | 字母（如 B） | 本地即时 | **自动显示解析** |
| 多选 | 字母组合（如 ABC） | 本地即时 | **自动显示解析** |
| 判断 | T / F | 本地即时 | **自动显示解析** |
| 简答 | 多行文本 | DeepSeek API（0-10分） | 显示参考答案 + 评分要点 |

---

## 五、进度追踪与智能选题

### 4.1 记录内容（progress.json）

每次答题自动记录：

| 字段 | 说明 |
|---|---|
| 作答次数 / 正确次数 | 简答按 AI 评分 ≥ 8 分计正确 |
| 未评分次数 | 无 API Key 时的简答作答 |
| 最近输入 / 最近结果 | 上次作答情况 |
| 用户输入历史 | 最近 50 条 |
| AI 输出 | 简答评分 reason/suggestion（最近 20 条） |

### 4.2 智能选题优先级

1. 未作答的题目优先
2. 正确率低的题目优先
3. 作答次数少的题目优先（练熟的题自然减少出现）
4. 上次答错的题目优先
5. 同一次会话内不重复

> 效果：不会总抽到重复题目，正确率高的题目会逐渐淡出，薄弱点自动加强。

---

## 六、学习分析报告

说 **"分析数据表"**，助手运行：

```bash
python analyze_progress.py
```

生成 `progress_report.html`（浅色主题，浏览器打开），包含：
- 总体统计卡片（已答题目、总作答次数、总正确率、薄弱知识点数、错题数）
- 各模块正确率条形图
- 知识点掌握排行（薄弱优先）
- 错题清单（题目 / 正确答案 / 你的作答 / 解析 / AI 评分）
- 复习建议

---

## 七、题库维护工具

| 工具 | 命令 | 用途 |
|---|---|---|
| 题库生成 | `python generate_questions.py --generate` | 按 v3.0 规则调用 DeepSeek 补齐缺失题目 |
| 重复修复 | `python fix_questions.py --fix` | 检测同知识点同题型重复题，DeepSeek 改写为反例/对比/场景/因果题 |
| 解析补齐 | `python generate_explanations.py --generate` | 为说明缺失/过短的样本调用 DeepSeek 生成说明 |
| 知识库丰富 | `python enrich_knowledge_base.py` | **首次构建知识库后必跑**：为每个知识点生成 300-500 字详细说明 |
| 全套测试 | `python test_skill.py` | 71 项自动化测试（数据完整性/题库结构/规则合规/引擎/生成/修复/进度） |
| 测试+自动修复 | `python test_skill.py --fix` | 测试发现重复题后自动调用修复工具 |

### 量化规则（v3.0）核心

四因子复杂度评分：**内容长度 + 内容类型 + 考察类型 + 难度**（总分 4~14）→ 决定每知识点题量：

| 总分 | 额外题 | 总题数 | 题型分配 |
|---|---|---|---|
| 4-5 | +0 | 4 | S1 M1 T1 A1 |
| 6-7 | +2 | 6 | S2 M2 T1 A1 |
| 8-9 | +3 | 7 | S3 M2 T1 A1 |
| 10-11 | +5 | 9 | S3 M3 T1 A2 |
| 12-14 | +8 | 12 | S3 M4 T2 A3 |

---

## 八、关于示例数据（重要）

> 本仓库/压缩包内包含的 **`question_bank.json`（603题）和 `knowledge_base.json`（74知识点）
> 均为示例数据（metadata 中标记 `data_status: EXAMPLE_SAMPLE`）**，仅用于展示
> 题库结构、题型格式与量化规则的运行效果。

**实际使用 skill 时**：
1. skill 首次初始化（Phase 1）会**检测到示例数据标记并排除**
2. 根据你选择的证书考试大纲**重新构建知识库**（联网搜索官方考纲）
3. **运行 `python enrich_knowledge_base.py` 丰富知识点内容**（DeepSeek 为每个知识点
   生成 300-500 字详细说明，覆盖定义/范围/方法/标准/最佳实践/误区）
4. 按 `references/question_generation_rules.md`（v3.0 量化规则）
   **重新生成题库**（每知识点4-12题，4种题型保底）

示例数据与真实题库互不干扰，请勿将示例数据当作真实考试内容使用。

---

## 九、安全说明

- 本压缩包已做 **API Key 脱敏**：不含任何真实密钥
- 配置真实 Key 后，包含 Key 的文件/目录（如 `esg-daily/`）**请勿对外分享或上传**
- 推荐使用环境变量方式设置 Key，避免 Key 写入文件
