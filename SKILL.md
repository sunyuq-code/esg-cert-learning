---
name: esg-cert-learning
description: "ESG certificate covert learning tool for office use. Disguises ESG (Environmental, Social, Governance) certification exam preparation as normal work-related AI conversations. Supports any ESG certificate (LCCI, CFA ESG, EFFAS, etc.) at any level. The skill generates Python scripts that look like work tools but are actually interactive study sessions. Trigger phrases include '帮我看看项目进度', '今天有什么安排', '整理一下数据表', '今天的待办事项'. Short-answer questions are graded by DeepSeek API."
agent_created: true
---

# ESG Certificate Covert Learning (ESG证书隐蔽学习)

A skill for covertly preparing for ESG certification exams during office hours
by generating Python scripts that look like work tools (data processing,
project progress reports, compliance checklists) but are actually interactive
ESG study sessions with knowledge review, practice questions, and case studies.

## Core Principles

1. **Pure Python script mode.** All learning happens inside generated `.py`
   files. The user runs the script in their terminal and interacts with it
   directly — no chat-based learning.
2. **Covert appearance.** Generated scripts look like data processing tools,
   project progress reports, or compliance checklists. Variable names, comments,
   and output all use work-like language.
3. **DeepSeek API grading.** Short-answer and case-study questions are graded
   by the DeepSeek API (model: `deepseek-chat`). Scoring is 0-10; scores below
   8 trigger improvement suggestions.
4. **Unified navigation with [P] support.** Scripts use a single item list
   (knowledge points + questions + case study) so `[P]` (previous) works
   seamlessly across all phases. Also: `[N]`/Enter for next, `[Q]` to quit,
   `[1]` mastered, `[2]` needs review, `[3]` show detail, `[0]` skip.
5. **Question types match exam requirements.** Four types: single choice,
   multiple choice, true/false, short answer. Every knowledge point has at
   least one question of each type (minimum guarantee), with additional
   questions allocated by a quantitative complexity scoring system (see
   `references/question_generation_rules.md`). Total: 603 questions across
   74 knowledge points (4-13 per KP, rules target max 12 based on content complexity).
6. **Shared engine architecture.** `esg_engine.py` is a reusable engine
   module; daily scripts import it and only contain content selection logic.
   Both files live in `./` (脚本所在目录).
7. **API-driven question generation.** `generate_questions.py` generates
   missing questions via the DeepSeek API (JSON mode), driven by the
   quantitative rules engine `question_rules.py` (v3.0 scoring). Run
   `python generate_questions.py` to check gaps, `--generate` to create and
   merge, `--preview N` to smoke-test the API without saving.
8. **Automated testing.** `test_skill.py` validates data integrity, bank
   structure, rules compliance, engine functions, and the generation
   pipeline. Run `python test_skill.py` (expect ALL PASSED); it works
   offline except the live API-key check.
9. **Learning progress tracking.** Every answer (correct/wrong, user input,
   and AI output for short answers) is recorded in `progress.json`. Daily
   scripts select questions by progress: unanswered → low-accuracy →
   least-practiced, so previously mastered questions rarely repeat.
10. **Wrong answers always show explanations.** Choice and true/false
    answers display the explanation automatically on error; short answers
    show the reference answer. `generate_explanations.py` fills missing or
    short explanations via the DeepSeek API before generating daily scripts.
11. **Learning analysis report.** Saying "分析数据表" runs
    `analyze_progress.py`, which reads the recorded progress and generates
    an HTML report: overall accuracy, per-module/per-KP accuracy, wrong
    question list with explanations and AI scores, and review suggestions.

## Initialization Flow

When the skill is first activated (no existing config found), guide the user
through this setup sequence:

### Phase 0: Certificate Setup

Ask the user for:
1. **Certificate name** — e.g., "LCCI中英联合ESG分析师", "CFA ESG Investing",
   "EFFAS Certified ESG Analyst", "SASB FSA Credential", etc.
2. **Level** — e.g., "初级", "中级", "高级", "Level I", "Level II", etc.

Store this in the skill config file: `references/config.md`

### Phase 1: Knowledge Base & Question Bank Construction

After the certificate is identified:

0. **Detect & exclude sample data.** The shipped `question_bank.json` /
   `knowledge_base.json` are marked `data_status: EXAMPLE_SAMPLE` in their
   metadata. At first use, check this marker; if present, **treat the
   bundled data as read-only examples and rebuild real content** (do not
   use sample questions as exam material):
   - Ask the user for confirmation, then proceed to rebuild.
1. **Search the web** for the certificate's official exam syllabus, knowledge
   points, and study materials.
2. **Build/update the knowledge base** at `references/knowledge_base.md`:
   - Organize knowledge points by module/chapter
   - Each point includes: ID, topic, key concept, explanation, difficulty level
   - Ensure comprehensive coverage of the exam syllabus
   - Update `references/knowledge_base.json` and clear the sample marker
3. **Generate study questions** at `references/question_bank.md`:
   - **Mandatory coverage**: every knowledge point must have at least one
     question of EACH type (single choice, multiple choice, true/false,
     short answer). For N knowledge points, minimum 4×N questions.
   - Each question includes: ID, type, knowledge point reference, question
     text, options/answer, explanation, difficulty level
   - Short-answer questions must include: `reference_answer` and
     `scoring_points` (list of key points for AI grading)
   - Generate questions via `python generate_questions.py --generate`
     (DeepSeek API) or in-assistant generation, then update
     `references/question_bank.json` and clear the sample marker
4. **Confirm completion** to the user with a summary.

### Phase 2: Cover Story Customization

Ask the user whether they want to modify the default cover story (掩护语).

**Default trigger phrases (generate Python scripts):**

| User Says (Cover Phrase) | Script Type | Content |
|---|---|---|
| "帮我看看项目进度" / "今天有什么安排" | Full session | Knowledge points + questions + case study |
| "整理一下数据表" | Knowledge review | Knowledge points only |
| "今天的待办事项" | Practice quiz | Questions only (all types) |
| "帮我写个风险评估" | Case study | Case study only (DeepSeek graded) |
| "这周数据汇总" | Mixed quick review | Partial knowledge + 5 questions + 1 case |
| **"分析数据表"** | **Analysis report** | **生成HTML学习分析报告 (progress_report.html)** |

If the user wants to customize, let them provide their own trigger phrases.

**"分析数据表" workflow** (analysis trigger):
1. Run `python analyze_progress.py`
2. Report saved to `progress_report.html`
3. Report contains: overall accuracy, per-module/per-KP accuracy bars,
   wrong-question list (with explanation and AI score), review suggestions
4. Tell the user the report path and open it for them

### Phase 3: Daily Study Volume Customization

Ask whether to modify the daily study volume.

**Default daily volume:**
- Knowledge point review: 10 points (4 basic + 4 intermediate + 2 advanced)
- Practice questions: 10 questions (mix of all 4 types, balanced difficulty)
- Case study: 1 case (rotates difficulty)

### Phase 4: DeepSeek API Key Setup

Ask the user to provide their DeepSeek API key for automated grading of
short-answer questions. **The key is requested at first use of the skill**
(the shipped skill package is desensitized — no real key is embedded).

**Setup instructions for the user:**
1. Go to https://platform.deepseek.com/ to register and get an API key
2. The key can be provided in any of these ways:
   - **During this setup** — paste it here; the assistant writes it into
     `references/config.md` (and embeds it in generated daily scripts)
   - Set environment variable `DEEPSEEK_API_KEY=sk-...` (recommended for
     keeping the key out of files)
   - Edit `DEEPSEEK_API_KEY` in `esg_engine.py`
3. If no key is provided, short-answer questions will skip API grading and
   only show the reference answer; question generation / explanation
   generation / duplicate repair will show a hint instead of running.

**Config storage:** Store the API key in `references/config.md` under the
`DeepSeek API` section. When generating Python scripts, embed the key directly
in the script. The key is resolved at runtime in this order:
env var `DEEPSEEK_API_KEY` → `references/config.md` → `esg_engine.py`.

**Security:** The packaged skill zip is desensitized — it contains only the
placeholder key. Never share files or zips that embed a real key.

### Phase 5: Start Learning

After setup is complete, generate the first Python learning script and tell
the user the file path. The user runs it with:
```
python YYYYMMDD_study.py
```

## Python Script Generation Workflow

### Question Bank Generation via DeepSeek API

When the question bank needs expansion or new questions:

1. Run `python generate_questions.py` (dry-run)
   to see which knowledge points are missing questions under the v3.0 rules.
2. Run `python generate_questions.py --generate`
   to call the DeepSeek API and generate+merge the missing questions.
   Options: `--module M1|M2|M3|M4|M5a|M5b`, `--force`, `--preview N`.
3. The generator reads the API key in this order: env var
   `DEEPSEEK_API_KEY` → `references/config.md` → `esg_engine.py`.
4. After generation, run `python test_skill.py`
   to verify the bank remains valid (unique IDs, valid answers, rules
   compliance, no duplicates).

### Daily Script Generation with Progress Awareness

When generating a daily study script (`YYYYMMDD_study.py`):

1. **Load progress** — read `progress.json` (created automatically on first run).
2. **Select questions by progress** — the script calls
   `progress_store.select_questions()`: unanswered questions first, then
   low-accuracy, then least-practiced. High-accuracy questions naturally
   fade out; already-answered questions don't repeat within a session.
3. **Ensure explanations exist** — before generating, optionally run
   `python generate_explanations.py --generate`
   so every selected question has a complete explanation (DeepSeek fills
   missing/short ones). Wrong answers will then always display the
   explanation in-script.
4. **Record answers** — the engine records every answer into `progress.json`:
   answer count, correct count, last input, and (for short answers) the AI
   score/reason/suggestion.
5. **Analyze anytime** — user says "分析数据表" → run
   `analyze_progress.py` → `progress_report.html`.

### Explanation Generation (解析补齐)

```
python generate_explanations.py             # 检测
python generate_explanations.py --generate  # 生成并更新
python generate_explanations.py --force     # 全量重生成
```

Calls DeepSeek per question with the linked knowledge-point content to write
a 60-150 char explanation. Missing/short explanations are fixed and the bank
is saved to both runtime and skill references.

### Testing the Skill

Run the test suite anytime after data or code changes:

```
python test_skill.py
python test_skill.py --verbose
python test_skill.py --fix   # 测试后自动修复重复题目
```

Covers: [T1] data integrity, [T2] bank structure, [T3] rules compliance,
[T4] engine functions, [T5] generator offline checks, [T6] API config,
[T7] generation pipeline (mocked API), [T8] repair tool checks,
[T9] progress store & analysis.
Exit code 0 = all passed.

### Duplicate Question Repair (题目修复)

When the test suite (T2/T8) or a manual check finds duplicate questions
(same KP, same type, core similarity > 0.75), repair them via DeepSeek:

```
python fix_questions.py           # 仅检测
python fix_questions.py --fix     # 检测并自动修复
python fix_questions.py --dry-run # 预览不改写
```

**Repair flow** (integrated into the skill workflow):
1. **检测**: scan question bank for same-KP same-type pairs whose core
   similarity exceeds 0.75 (interrogative shells and topic prefixes are
   stripped before comparison).
2. **改写**: for each pair, keep the first question and call the DeepSeek
   API to rewrite the second into a different angle — 反例识别 (counter-
   example), 对比辨析 (comparison), 场景应用 (scenario application), or
   因果推理 (causal reasoning). The type/ID/kp_ref/level are preserved.
3. **校验**: the rewritten question is validated (fields, answer within
   options, no new duplicate) with up to 2 API retries on failure.
4. **替换**: the fixed question replaces the original in
   `question_bank.json` (both runtime and skill references copies).
5. **复查**: re-run the duplicate scan; loop until clean.
6. **复测**: run `test_skill.py` again to confirm ALL PASSED.

Optionally, `python test_skill.py --fix` chains steps 1-6 automatically
after the test suite detects duplicates.

### When a Trigger Phrase is Detected

1. **Determine script mode** from the trigger phrase (see Phase 2 table).
2. **Check engine files exist** in `./` (脚本所在目录):
   - `esg_engine.py` — if missing, copy from skill references
   - `question_bank.json` — if missing, copy from skill references
   - `knowledge_base.json` — if missing, copy from skill references
3. **Generate the daily script** `YYYYMMDD_study.py`:
   - Import `StudySession` from `esg_engine`
   - Load `question_bank.json` and `knowledge_base.json`
   - Select content based on mode + date rotation
   - Embed the DeepSeek API key from config
4. **Save the script** to `YYYYMMDD_study.py`
5. **Tell the user** the file path and run command:
   "数据表已整理完毕，路径：`YYYYMMDD_study.py`，
   运行查看：`python YYYYMMDD_study.py`"
   For mode-specific runs: append `review`, `quiz`, `case`, or `full`.

### Script Naming Convention

- Directory: `./` (脚本所在目录)
- Filename: `YYYYMMDD_study.py` (e.g., `sample_study.py`)
- If multiple scripts per day, append `_2`, `_3`, etc.

## Python Script Features

### 1. Interactive CLI with Unified Navigation

```
  [1] 已掌握  [2] 需复习  [3] 显示详解  [0] 跳过
  [P] 上一个  [N]/Enter 下一个  [Q] 退出
```

- `[P]` — go back to previous item (works across ALL phases: knowledge → questions → case)
- `[N]` or Enter — proceed to next item
- `[Q]` — quit and show summary
- `[1]` — mark as mastered (knowledge points)
- `[2]` — mark as needs review
- `[3]` — show explanation / reference answer
- `[0]` — skip current item
- Navigation uses a single unified item list, so [P] seamlessly crosses phase boundaries

### 2. Question Types

| Type | Display | Answer Input | Grading |
|---|---|---|---|
| 单选 (single_choice) | Options A-D | Letter (e.g., "B") | Immediate, local |
| 多选 (multiple_choice) | Options A-E | Letters (e.g., "ABC") | Immediate, local |
| 判断 (true_false) | Statement | T/F | Immediate, local |
| 简答 (short_answer) | Question | Multi-line text | **DeepSeek API**, 0-10 score |

**Wrong-answer explanation display:**
- 单选/多选/判断答错时自动显示 `>> 解析: ...`（结合知识点内容的完整解析）
- 简答提交后始终显示参考答案与评分要点；AI评分时显示评分理由与改正建议
- 解析由题库自带（`generate_explanations.py` 用DeepSeek补齐缺失/过短解析）

### 3. Learning Progress Tracking

Every answer is recorded to `progress.json` (runtime dir + skill references):

| 记录项 | 说明 |
|---|---|
| answer_count | 作答次数 |
| correct_count | 正确次数 (AI评分简答>=8分算正确) |
| ungraded_count | 未评分作答 (无AI Key时简答) |
| last_input / last_result | 最近一次作答与结果 |
| user_inputs | 用户输入历史 (最近50条) |
| ai_outputs | 简答题AI评分输出 (最近20条) |

**Smart selection** (`progress_store.select_questions`):
1. 未作答的题目优先
2. 正确率低的题目优先
3. 作答次数少的题目优先 (练熟的题自然降低频率)
4. 上次答错的题目优先
5. 同一次会话内不重复 (exclude set)

### 4. Learning Analysis Report

User says **"分析数据表"** → run `analyze_progress.py`:
- 输出 `progress_report.html`（浅色主题，可直接浏览器打开）
- 内容: 总体统计卡片、各模块正确率条形图、知识点掌握排行（薄弱优先）、
  错题清单（含题目/正确答案/你的作答/解析/AI评分）、复习建议
- 报告用于调整每日学习侧重

### 5. DeepSeek API Grading (Short Answer & Case Study)

When the user submits a short-answer or case-study response:

1. Call DeepSeek API with the question, reference answer, scoring points,
   and user's answer
2. API returns JSON: `{"score": 8, "reason": "...", "suggestion": "..."}`
3. Display score (X/10), reason
4. If score < 8: display improvement suggestions (改正建议)
5. Always show reference answer after grading

**API configuration in the script:**
```python
DEEPSEEK_API_KEY = "sk-..."  # from config
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
```

**API call uses:**
- Model: `deepseek-chat`
- `response_format={'type': 'json_object'}`
- System prompt includes JSON format example
- `max_tokens=1000`

**Error handling:**
- If API key is empty: skip grading, show reference answer only
- If `openai` package not installed: show hint to `pip install openai`
- If API error: show error, fall back to reference answer

### 6. Covert Appearance

- **Filename**: `.py` extension
- **Docstring**: "Project Progress Report", "Data Validation Module"
- **Variable names**: `DATA_ENTRY`, `CHECK_ITEM`, `RISK_CASE`
- **Phase labels**: "Data Entry Review", "Validation Checklist", "Risk Assessment"
- **Output style**: code-assignment format, progress bars

### 7. Progress Tracking

The script tracks:
- Knowledge points: mastered / needs review / skipped
- Questions: correct / wrong / skipped (also persisted to `progress.json`)
- Short-answer scores: list of scores, average (also persisted with AI output)
- Displays summary at the end

## Config File Format

Stored at `references/config.md`:

```markdown
# ESG Learning Config

## Certificate
- Name: [certificate name]
- Level: [level]

## DeepSeek API
- API Key: [user's key or empty]
- Base URL: https://api.deepseek.com
- Model: deepseek-chat

## Cover Story
[trigger phrases table]

## Daily Volume
[volume settings]

## Progress
- Last session date: [date]
- Knowledge points reviewed: [list of IDs]
- Questions answered: [count]
- Accuracy: [percentage]
```

## Reference Files

- `references/config.md` — Skill configuration (certificate, API key, volume)
- `references/knowledge_base.md` — Knowledge points organized by module (markdown)
- `references/knowledge_base.json` — Same as above in JSON format (for engine loading)
- `references/question_bank.json` — Complete 603 questions in JSON format (74 KPs, v3.0 rules)
- `references/question_rules.py` — Rules engine (v3.0 scoring, authoritative 74-KP table)
- `references/generate_questions.py` — DeepSeek API question generator
- `references/fix_questions.py` — DeepSeek API duplicate-question repair tool
- `references/generate_explanations.py` — DeepSeek API explanation generator
- `references/progress_store.py` — Learning progress storage & smart selection
- `references/analyze_progress.py` — HTML learning analysis report generator
- `references/test_skill.py` — Test suite (9 groups, offline-capable, --fix auto-repair)
- `references/progress.json` — Answer records (answer count, correct count, AI outputs)
- `references/python_daily_template.md` — Python script template documentation
- Runtime files at `./` (脚本所在目录):
  - `esg_engine.py` — Shared interactive study engine
  - `question_bank.json` — Copy of question bank for runtime use
  - `knowledge_base.json` — Copy of knowledge base for runtime use
  - `YYYYMMDD_study.py` — Daily generated scripts

When the skill is activated, check if `config.md` exists. If not, run the
initialization flow. If it exists, load the config and wait for trigger phrases.

## Safety and Cover Maintenance

- **If the user explicitly types ESG terms**, treat it as natural work context.
- **If asked what the script does**, the default explanation is "数据处理脚本，
  项目进度核查用的" (data processing script for project progress review).
- **Never mention exam preparation** in the generated Python files.
- **API key security**: the key is stored locally in the config and embedded
  in scripts. Do not share scripts containing the API key externally.
