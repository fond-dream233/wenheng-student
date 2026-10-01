# 真实匿名样本双教师盲审流程

本流程用于建立跨阶段漂移的真实人工标注基准。盲审期间不向教师展示算法分数、风险等级或合成样本标签。真实论文、身份映射和教师姓名均不得提交到 Git。

## 角色隔离

- 数据协调员：取得授权，制作私密源清单，运行匿名化并保管身份映射。
- 教师 A / B：分别查看匿名文档，独立填写标注表，不交换标签。
- 裁决人：只处理不一致或 `uncertain` 样本，确定最终标签并说明理由。
- 评测执行人：最终标签锁定后才运行跨阶段 Partner，计算真实样本指标。

同一人可以兼任数据协调员和评测执行人，但两位初审教师应独立作答。裁决人不得直接覆盖初审记录。

## 标签口径

| 标签 | 定义 |
| --- | --- |
| `low` | 研究对象、核心问题和主要目标保持一致，变化属于细化、补充或正常实现调整。 |
| `medium` | 至少一个核心维度发生实质变化，但仍能追溯到原课题主线，例如部分目标替换或方法与对象同时调整。 |
| `high` | 研究对象、核心问题或主要成果基本被替换，后续阶段难以视为原课题的连续发展。 |
| `uncertain` | 文档信息不足、版本疑似错误或证据冲突，初审无法可靠定级；必须进入裁决。 |

连续性评分均为 1–5：1 表示完全不连续，3 表示部分延续，5 表示高度连续。总体风险标签应综合主题、目标、方法和范围变化判断，不能由单个分项机械换算。

## 1. 收集与授权

只接收已经取得学生授权、完成伦理/数据管理审批且允许用于比赛评测的论文。推荐不少于 30 组，每组至少两个阶段；尽量覆盖不同专业、不同阶段组合和预期风险。

在项目外的受控目录生成源清单：

```powershell
.\.venv\Scripts\python.exe -m evaluation.blind_review manifest-template D:\private-review\source_manifest.csv
```

每行填写一个真实课题：

- `source_case_id`：内部编号，仅协调员可见；
- `proposal_path` / `midterm_path` / `final_path`：至少填写两个 DOCX；
- `sensitive_terms`：需要替换的姓名、学号、院校、导师、项目编号等，以 `|` 分隔；
- `consent_confirmed`：只有已确认授权的样本填写 `yes`。

## 2. 生成盲审包

```powershell
.\.venv\Scripts\python.exe -m evaluation.blind_review prepare `
  D:\private-review\source_manifest.csv `
  D:\private-review\blind-package `
  D:\private-review\identity-private
```

程序会：

1. 随机分配 `BR001` 形式的编号；
2. 从可见正文和表格重建纯文本 DOCX，丢弃图片、批注、页眉页脚、隐藏对象和原始元数据；
3. 替换清单中的敏感词并进行失败即停止的复查；
4. 将身份映射单独写入私密目录；
5. 生成顺序不同的 `reviewer_a.csv` 与 `reviewer_b.csv`，且不计算或写入算法预测。

自动处理不能发现清单外的身份信息。协调员必须逐份人工检查匿名文档，确认无姓名、学号、单位、导师、致谢、文件属性、图片水印等泄露后再发给教师。匿名重建会牺牲排版和图片，只适用于本项目的跨阶段内容/结构漂移评测，不用于格式评分。

## 3. 独立标注

教师 A、B 各自使用一份工作簿模板或对应 CSV：

- 工作簿模板：`outputs/blind-review/teacher_blind_review_template.xlsx`；
- CSV 列定义与工作簿“标注记录”一致；
- `evidence_location` 填章节、标题或页内可定位描述，不复制大段原文；
- `rationale` 简述定级依据；
- 完成后将 `review_complete` 改为 `yes`。

教师之间不得查看彼此文件。协调员回收后保留原始版本，只在副本上做格式修复。

## 4. 一致性与裁决

```powershell
.\.venv\Scripts\python.exe -m evaluation.blind_review aggregate `
  D:\private-review\blind-package\reviewer_a.csv `
  D:\private-review\blind-package\reviewer_b.csv `
  D:\private-review\aggregate
```

输出：

- `agreement_report.json`：原始一致率、Cohen’s κ、冲突数和标签分布；
- `adjudication.csv`：仅列出不一致或 `uncertain` 样本；
- `human_baseline.csv`：先写入双评审一致的样本。

裁决人填写 `adjudication.csv` 的 `final_risk`、`final_reason`、`adjudicator`，再运行：

```powershell
.\.venv\Scripts\python.exe -m evaluation.blind_review aggregate `
  D:\private-review\blind-package\reviewer_a.csv `
  D:\private-review\blind-package\reviewer_b.csv `
  D:\private-review\aggregate-final `
  --adjudication D:\private-review\aggregate\adjudication.csv
```

只有 `baselineComplete=true` 时，`human_baseline.csv` 才能作为正式人工基准。应保留两份原始标注、裁决表、版本时间和匿名化检查记录。

## 5. 锁定后评测与对外披露

人工基准锁定后再运行算法，并按固定 `case_id` 合并结果。报告至少包含样本数、阶段组合、标签分布、原始一致率、Cohen’s κ、裁决数量、三分类准确率、Macro F1、漂移召回率和低漂移误报率。

对外只发布聚合指标、流程说明和经批准的匿名示例。不要发布论文正文、身份映射、教师姓名、未裁决标签或能够反向识别学生的细分结果。
