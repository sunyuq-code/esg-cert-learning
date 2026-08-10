# Python Daily Learning Script Template

This file defines the architecture and generation rules for daily Python
learning scripts. The system uses a **shared engine + daily script** approach.

## Architecture

```
./ (脚本所在目录)
  esg_engine.py             # Shared engine (navigation, DeepSeek grading, progress, explanations)
  question_bank.json        # Full question bank (603 questions, 74 KPs, v3.0 rules)
  knowledge_base.json       # Knowledge points (74 items, 5 modules)
  progress_store.py         # Progress storage + smart selection
  progress.json             # Answer records (auto-created)
  generate_explanations.py  # DeepSeek explanation filler (run before generating scripts)
  analyze_progress.py       # HTML learning analysis report ("分析数据表")
  YYYYMMDD_study.py         # Daily script (imports engine, selects content by progress)
```

### Why shared engine?

- Engine code is written once, reused by all daily scripts
- Daily scripts are small — just content selection + configuration
- Bug fixes in the engine automatically apply to all sessions
- User runs `python YYYYMMDD_study.py` which imports the engine

## File Naming and Location

- **Directory**: `./ (脚本所在目录)`
- **File name**: `YYYYMMDD_study.py` (e.g., `sample_study.py`)
- **Create directory if missing**

## Daily Script Structure

Each daily script:

1. Imports `StudySession` from `esg_engine.py`
2. Loads `question_bank.json` and `knowledge_base.json`
3. Loads learning progress from `progress.json` (auto-created on first run)
4. Selects content based on:
   - **Trigger phrase** (determines mode: full/review/quiz/case)
   - **Date** (rotates through content so each day covers different material)
   - **Progress** (questions: unanswered → low-accuracy → least-practiced;
     high-accuracy questions naturally fade out; no repeat within a session)
5. Embeds the DeepSeek API key (from config)
6. Creates a `StudySession` with `progress_data` (records every answer) and
   calls `.run()`
7. On exit, progress is saved to `progress.json` (runtime + skill references)

### Trigger Phrase → Script Mode Mapping

| User Says (Cover Phrase) | Mode | Content |
|---|---|---|
| "帮我看看项目进度" / "今天有什么安排" | full | 10 knowledge points + 10 questions + 1 case |
| "整理一下数据表" | review | 15 knowledge points only |
| "今天的待办事项" | quiz | 10 questions (mix of all 4 types) |
| "帮我写个风险评估" | case | 1 case study only (DeepSeek graded) |
| "这周数据汇总" | mixed | 5 knowledge points + 5 questions + 1 case |

## Engine Features

### 1. Unified Navigation (Cross-Phase [P] Support)

The engine builds a single item list:
```
[kp1, kp2, ..., kpN, q1, q2, ..., qM, case_study]
```

Navigation uses a single index, so `[P]` (previous) works seamlessly:
- From question 1 → [P] → last knowledge point
- From case study → [P] → last question
- From first knowledge point → [P] → stays at first (no crash)

| Key | Action |
|---|---|
| [P] | Previous item (across all phases) |
| [N] / Enter | Next item |
| [Q] | Quit and show summary |
| [1] | Mark as mastered (knowledge points) |
| [2] | Mark as needs review |
| [3] | Show explanation / reference answer |
| [0] | Skip |

### 2. DeepSeek API Grading (Short Answer & Case Study)

**API Configuration:**
```python
DEEPSEEK_API_KEY = ""  # User fills in their key
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
```

**Grading flow:**
1. User submits multi-line text answer
2. Engine calls DeepSeek API with:
   - System prompt (ESG scoring expert, JSON output format)
   - User prompt (question, reference answer, scoring points, user answer)
   - `response_format={'type': 'json_object'}`
   - `max_tokens=1000`
3. API returns JSON: `{"score": 8, "reason": "...", "suggestion": "..."}`
4. Display: score (X/10), reason
5. If score < 8: display improvement suggestions (改正建议)
6. If score >= 8: show "表现优秀！"
7. Always show reference answer and scoring points after grading

**Error handling:**
- No API key → skip grading, show reference answer only
- `openai` not installed → hint to `pip install openai`
- 401 error → "API Key 无效"
- 429 error → "API调用频率超限"
- Network error → "网络连接异常"
- JSON parse error → "API返回格式异常"

### 3. Four Question Types

| Type | key | Input | Grading |
|---|---|---|---|
| 单选 | `single_choice` | Letter (e.g., "B") | Local, immediate |
| 多选 | `multiple_choice` | Letters (e.g., "ABC") | Local, immediate |
| 判断 | `true_false` | T/F | Local, immediate |
| 简答 | `short_answer` | Multi-line text | **DeepSeek API**, 0-10 score |

**错题自动显示解析:**
- 单选/多选/判断答错时自动显示 `>> 解析: ...`
- 简答提交后始终显示参考答案与评分要点
- 解析不完整时, 生成脚本前运行 `python generate_explanations.py --generate`
  用DeepSeek结合知识点内容补齐

### 4. Learning Progress (进度记录)

Every answer is recorded into `progress.json`:

| 字段 | 说明 |
|---|---|
| answer_count / correct_count | 作答次数 / 正确次数 |
| ungraded_count | 无AI评分时的简答作答数 |
| last_input / last_result | 最近一次输入与对错 |
| user_inputs | 用户输入历史(最近50条) |
| ai_outputs | 简答AI评分输出(最近20条) |

Smart selection priority: 未作答 → 正确率低 → 作答次数少 → 上次答错。
用户输入"分析数据表" → `analyze_progress.py` 生成 HTML 报告。

### 5. Answer Normalization

The engine handles inconsistent answer formats in the question bank:
- `"ABC"` (string) → `"ABC"`
- `["A","B","C"]` (list) → `"ABC"`
- `"A,B,C"` (comma-separated) → `"ABC"`
- `"BAC"` (unsorted) → `"ABC"` (sorted for comparison)

### 6. Short Answer Data Structure

Each short-answer question includes:
```python
{
    "id": "Q-ESG-T-001-A1",
    "type": "short_answer",
    "kp_ref": "ESG-T-001",
    "level": "basic",
    "question": "简述ESG三大支柱各自关注的核心内容。",
    "reference_answer": "E(环境): ... S(社会): ... G(治理): ...",
    "scoring_points": [
        "E(环境)关注碳排放、资源消耗等",
        "S(社会)关注劳工权益、社区影响等",
        "G(治理)关注董事会结构、信息披露等"
    ],
    "explanation": "ESG三大支柱各有侧重。"
}
```

### 7. Covert Appearance

- File header: "Project Progress Report", "Data Validation Module"
- Variable names: `DATA_ENTRY`, `CHECK_ITEM`, `RISK_CASE`
- Phase labels: "Data Entry Review", "Validation Checklist", "Risk Assessment"
- Progress bar: `[===-------] Data Entry 3/10 (30%)`

### 8. Progress Tracking

The engine tracks:
- Knowledge points: mastered / needs review / skipped
- Questions: correct / wrong / skipped
- Short-answer scores: list of scores, average
- Displays summary at the end with accuracy percentage

## Generation Checklist

When generating a daily Python script, ensure:

- [ ] Script is saved to `./ (脚本所在目录)YYYYMMDD_study.py`
- [ ] `esg_engine.py` exists in the same directory (copy if missing)
- [ ] `question_bank.json` exists in the same directory (copy if missing)
- [ ] `knowledge_base.json` exists in the same directory (copy if missing)
- [ ] `DEEPSEEK_API_KEY` is filled from config (or left empty if not set)
- [ ] Content selection matches the trigger phrase mode
- [ ] Date-based rotation is used to cover different content each day
- [ ] User is told the file path and run command

## DeepSeek API Key Setup

When the user first sets up the system:

1. Ask the user to get a DeepSeek API key from https://platform.deepseek.com/
2. Store the key in `references/config.md` under the DeepSeek API section
3. When generating daily scripts, embed the key in the script:
   ```python
   DEEPSEEK_API_KEY = "sk-..."  # from config
   ```
4. Alternatively, the user can edit `esg_engine.py` directly to set the key

If no key is provided:
- Short-answer questions skip API grading
- Only the reference answer is shown
- The script displays a warning at startup
