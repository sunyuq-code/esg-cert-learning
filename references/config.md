# ESG Learning Config

## Certificate
- Name: LCCI中英联合ESG分析师
- Level: 初级
- Issuing Bodies: IAB英国伦敦工商会LCCI + 中国企业财务管理协会
- Standard: T/ZCX 006-2023 (ESG分析师专业能力评价规范)

## DeepSeek API
- API Key: (待用户填写 — 首次使用skill时提供, 用于①简答/案例AI评分 ②题库生成 ③解析生成)
- Base URL: https://api.deepseek.com
- Model: deepseek-chat
- Usage:
  1. 评分简答题和案例分析题，0-10分制，低于8分给出改正建议
  2. 题库生成: `python generate_questions.py --generate` 调用API补齐缺失题目
- Get key at: https://platform.deepseek.com/
- 设置方式(任选): ①环境变量 DEEPSEEK_API_KEY ②本文件API Key字段 ③esg_engine.py的DEEPSEEK_API_KEY

## Cover Story
### Trigger Phrases (掩护语 → 生成Python脚本)
| User Says (Cover Phrase) | Script Type | Content |
|---|---|---|
| "帮我看看项目进度" / "今天有什么安排" | Full session | 知识点 + 练习题 + 案例分析 |
| "整理一下数据表" | Knowledge review | 仅知识点复习 |
| "今天的待办事项" | Practice quiz | 仅练习题(含4种题型) |
| "帮我写个风险评估" | Case study | 仅案例分析(DeepSeek评分) |
| "这周数据汇总" | Mixed quick review | 部分知识点 + 5题 + 1案例 |
| "分析数据表" | Analysis report | 生成HTML学习分析报告 (progress_report.html) |

### In-Script Navigation (脚本内导航，固定)
| Key | Action |
|---|---|
| [P] | 上一个 |
| [N] / Enter | 下一个 |
| [Q] | 退出并显示总结 |
| [1] | 已掌握 |
| [2] | 需复习 |
| [3] | 显示详解/答案 |
| [0] | 跳过 |

## Daily Volume
- Knowledge points: 10 (4 basic + 4 intermediate + 2 advanced)
- Questions: 10 (mix of single/multiple/true-false/short-answer, balanced difficulty)
- Case studies: 1 (rotates difficulty)

## Knowledge Base
- Markdown: references/knowledge_base.md
- JSON: references/knowledge_base.json (数据与脚本同目录)
- Total knowledge points: 74
- Modules: 5 (ESG理论与实践, ESG标准框架, ESG投资策略, ESG评级入门, ESG新兴趋势与热点)
- Difficulty: 35 basic + 28 intermediate + 11 advanced

## Question Bank
- JSON: references/question_bank.json (603 questions, 数据与脚本同目录)
- Rules: references/question_generation_rules.md (题库生成量化规则 v3.0)
- Total questions: 603 (rules target: 550, plus 53 legacy questions from v1/v2)
- Types: 191 single choice + 181 multiple choice + 94 true/false + 137 short answer
- Each KP has 4-13 questions depending on content complexity score (CL+CT+ET+D, max 12 target)
- Every knowledge point has at least 1 question of each type (minimum guarantee)
- Extra questions allocated by score: 6-7分→+2(S1M1), 8-9分→+3(S2M1), 10-11分→+5(S2M2A1), 12-14分→+8(S2M3T1A2)
- Short answer questions include reference_answer and scoring_points for DeepSeek API grading
- Answer format: some multiple_choice answers are lists (["A","B","C"]), engine normalizes automatically

## Progress
- Last session date: 2026-08-10
- Knowledge points reviewed: []
- Questions answered: 0
- Accuracy: N/A
- Short answer avg score: N/A

## Python Script Architecture
- Engine: esg_engine.py (shared, reusable, 进度记录+错题解析)
- Rules engine: question_rules.py (v3.0量化规则)
- Question generator: generate_questions.py (DeepSeek API)
- Question repair: fix_questions.py (DeepSeek API, 重复题目改写)
- Explanation generator: generate_explanations.py (DeepSeek API, 解析补齐)
- Progress store: progress_store.py (答题记录+智能选题)
- Analysis report: analyze_progress.py (HTML学习分析报告)
- Test suite: test_skill.py (python test_skill.py [--fix])
- Question bank: question_bank.json
- Knowledge base: knowledge_base.json
- Progress data: progress.json (作答次数/正确次数/输入/AI输出)
- Daily scripts: YYYYMMDD_study.py
- Run command: python YYYYMMDD_study.py [full|review|quiz|case]
- Navigation: [P] previous (cross-phase), [N]/Enter next, [Q] quit, [1] mastered, [2] review, [3] detail, [0] skip
