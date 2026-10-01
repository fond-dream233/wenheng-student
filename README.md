# 西南科技大学本科毕业论文检查系统

> 参赛改造说明：本仓库已完成本地 AIP 三类 Partner、跨阶段对比、评测集与 Web 端三阶段工作流；后续仍需完成赛事平台上的注册、发现与联调。详见 [`competition/README.md`](competition/README.md)。

基于 Flask + python-docx 的毕业论文检查系统。按开题、中期、定稿阶段上传 `.docx` 后，可生成单篇检查报告和同一课题的跨阶段对比报告，给出格式分、逻辑分、AI 痕迹评估、研究漂移风险与逐条修改建议。

**全程离线运行，不连接任何大模型或外部接口**，评分完全由本地规则与统计特征计算，可复现、无数据外泄风险。

---

## 一、默认账号

| 角色 | 账号 | 密码 | 说明 |
| --- | --- | --- | --- |
| 教师（管理员） | `teacher` | 首次启动随机生成 | 未设置环境变量时写入 `outputs/db/initial_admin_password.txt` |
| 学生（示例） | `student` | `student@2026` | 学号 20220001，示例班级，仅用于演示登录 |

- 教师账号在数据库首次初始化时自动创建；推荐启动前通过 `DEFAULT_TEACHER_PASSWORD` 设置强口令。未设置时随机口令只写入本地忽略文件，不写入日志。
- 学生账号由教师在「学生账号管理」页（`/teacher/students`）创建：
  - 单个创建：填账号、姓名、学号、班级，密码留空则由系统随机生成；
  - 批量创建：每行一条「学号 姓名」，账号默认取学号，密码随机生成，结果自动导出到 `outputs/results/accounts_*.txt` 供下载分发；
  - 支持重置密码、启用/停用、删除。
- 登录后均可自行修改密码（学生端「修改密码」）。
- 修改教师初始账号/口令：在**数据库未初始化前**设置环境变量 `DEFAULT_TEACHER_USERNAME`、`DEFAULT_TEACHER_PASSWORD`、`DEFAULT_TEACHER_NAME`。

## 二、快速启动

```powershell
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
python app.py

# 3. 访问
http://127.0.0.1:5000
```

仅依赖 `Flask`、`Werkzeug`、`python-docx`（Python 3.10+）。

## 三、目录结构

```
├── app.py                 # Flask 入口
├── config/settings.py     # 全局配置（全部读环境变量，无硬编码）
├── routes/                # 蓝图：auth / teacher / student
├── tools/                 # 核心模块
│   ├── docx_parser.py     # docx 解析（段落、样式、页面设置、图表题注）
│   ├── rules_schema.py    # 43 条格式规则定义与学校模板默认值
│   ├── format_expert.py   # 格式专家：按启用的规则逐项检查
│   ├── format_checks.py   # 各格式规则的具体检查函数
│   ├── logic_expert.py    # 逻辑专家：结构与论证检查
│   ├── logic_checks.py    # 12 项逻辑检查（结构、章节、段落、论证）
│   ├── logic_ai_checks.py # 8 项 AI 痕迹检查（统计特征，非模型判定）
│   ├── analyzer.py        # 分析编排：解析 → 双专家 → 落盘 → 入库
│   ├── scorer.py          # 分数合成、等级评定、总评生成
│   ├── report_builder.py  # HTML 报告渲染
│   ├── database.py        # SQLite 数据访问
│   └── logger.py          # 按日期分割日志
├── utils/                 # 通用工具（密码哈希、校验等）
├── templates/ static/     # 页面模板与样式
└── outputs/               # 运行产物
    ├── papers/            # 上传的论文原件
    ├── reports/           # HTML 报告
    ├── results/           # JSON 结果数据
    └── db/thesis.db       # SQLite 数据库（含 secret.key）
logs/                      # 按日期分割的运行日志
```

## 四、使用流程

**学生端** `/student`
1. 输入或选择课题，按开题、中期、定稿阶段上传 `.docx`；
2. 每次上传后自动生成单篇分析报告；
3. 同一课题至少具备两个阶段后，点击「生成跨阶段报告」；
4. 在线查看单篇报告、跨阶段报告，并可打印或另存为 PDF。

**教师端** `/teacher`
- 仪表盘：提交概览与分数分布；
- 学生账号管理：单个/批量创建、重置密码、启用禁用、删除、导出账号；
- 格式规范配置：43 条规则逐项启用与改值，支持「载入学校模板默认规范」「清空」；
- 提交记录、单篇报告与跨阶段报告查看/下载。

## 五、检查内容

**格式检查（43 条，8 个分组）**
页面设置、正文格式、标题格式、结构完整性与篇幅、目录、图与表、参考文献、排版细节。

默认值取自《西南科技大学本科毕业论文（设计）模板（2026届）》实测参数（A4、页边距 2.5cm、宋体/Times New Roman 小四、固定行距 22 磅、首行缩进 2 字符、章标题小二居中、题注与参考文献五号、GB/T 7714 等）。教师可按本院要求逐项修改；**留空的规则自动跳过，不计入格式分**。

**逻辑检查（12 项）**
章节完整性、章节顺序、章节篇幅均衡、标题层级跳跃、标题重复、标题与内容匹配、段落过长、单句段落、论证缺支撑、模糊表述过多、指代词开头等。

**AI 痕迹检查（8 项）**
套话命中、句长均齐度、句首重复、用词多样性、连接词过度使用、段落重复、摘要与结论相似度、数据支撑缺失。基于统计特征打分，**仅供参考提示，不计入总分**。

## 六、评分规则

- 总分 = 格式分 × 0.5 + 逻辑分 × 0.5（权重可通过环境变量 `FORMAT_WEIGHT` / `LOGIC_WEIGHT` 调整）；
- 未配置任何格式规则时，总分取逻辑分，并提示「格式规范尚未配置」；
- 等级：≥90 优秀 / ≥80 良好 / ≥70 中等 / ≥60 合格 / <60 待大幅修改。

## 七、常用配置（环境变量）

在启动前设置，例如 PowerShell：

```powershell
$env:MAX_UPLOAD_MB = "100"      # 上传上限，默认 30MB，含大量图片的论文建议调大
$env:APP_PORT = "5000"          # 端口
$env:DEFAULT_TEACHER_PASSWORD = "至少 12 位的自定义强密码"   # 仅对尚未初始化的数据库生效
python app.py
```

其余可配项见 `config/settings.py`（路径、学校名称、调试开关等）。**修改配置后需重启服务生效。**

## 八、常见问题

- **上传报 413 Request Entity Too Large**：论文超过上传上限，调大 `MAX_UPLOAD_MB` 后重启，或在 Word 中压缩图片。
- **报 `No module named 'markupsafe'`**：Flask/Werkzeug 的传递依赖缺失，执行 `pip install markupsafe`；若装到错误解释器，用 `pip install --target <该解释器的 site-packages> markupsafe`。
- **分析失败**：检查是否为 `.docx`（不支持 `.doc`），文件是否损坏或被加密；详情见 `logs/` 当日日志。
