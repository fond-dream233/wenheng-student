# AIC 智能体互联参赛改造工作区

本目录用于把现有的本科论文检查 Web 系统改造成符合赛事要求的 ACPs/AIP 多智能体应用。现有规则检查代码继续作为确定性业务能力复用，不复制或改写其核心算法。

## 1. 推荐作品定位

- 作品名（20 字以内候选）：`文衡：多智能体论文质检平台`
- 核心场景：学生提交开题、中期、终稿，Leader 按阶段拆分任务并发现/调用专职 Partner，汇总为可追溯报告。
- 差异化亮点：跨阶段目标漂移检查 + 确定性格式规则 + 内容审查 + AIP 标准化协作 + 全链路审计。
- 对外表述：不要把统计规则包装成大模型判定；当前“AI 痕迹”只能描述为启发式风险提示。

## 2. 目标智能体拓扑

```text
用户 / 梧桐平台
       |
       v
论文质检 Leader
  |-- ADP 发现 --> 文档解析 Partner
  |-- AIP RPC --> 格式检查 Partner（复用 FormatExpert）
  |-- AIP RPC --> 逻辑审查 Partner（复用 LogicExpert）
  |-- AIP RPC --> 跨阶段对比 Partner（新增）
  `-- AIP RPC --> 报告聚合 Partner（复用 ReportBuilder）
```

第一阶段先跑通 Direct RPC 的 `start -> awaiting-completion -> complete -> completed`；第二阶段再接入 ADP 自动发现、mTLS 身份绑定和梧桐平台；只有在多个 Partner 必须共享会话上下文时才引入 RabbitMQ Group 模式。

## 3. 评分项到工程任务映射

| 评分项 | 分值 | 当前状态 | 必须补齐的工程与证据 |
| --- | ---: | --- | --- |
| 创新性 | 25 | 单体规则检查 | 5 个职责清晰的智能体；三阶段跨文档对比；标注官方复用与自主代码边界 |
| 需求分析 | 10 | 有项目定位 PDF | 教师/学生访谈或问卷、同类产品对比、四类指标（功能/性能/兼容/部署） |
| AI 技术应用 | 20 | 已完成本地 AIP Direct RPC 闭环 | 继续补齐 AIC、ADP、mTLS、梧桐注册/发现/互联/访问证据 |
| 项目实施 | 15 | Flask 原型与一键本地演示可运行 | 继续补齐持久化、错误恢复、量化测试矩阵、开发计划和真实提交记录 |
| 应用成效 | 10 | 有样例结果 | 时延、并发、成功率、规则准确率、跨阶段检出率、平台累计访问量与日志 |
| 总结展望 | 10 | 未形成 | 开源代码改造复盘、兼容问题、标准化价值、推广路线 |
| 附加分 | 10 | 未准备 | 一键部署 1-3；3-5 分钟全流程视频 1-3；平台访问量 1-4 |

## 4. 硬性验收门槛

- 使用赛事指定的 AIP-PUB/ACPs 官方参考实现，而不是同名的其他 AIP 或 A2A 协议。
- 在梧桐平台完成注册、自动发现、跨端互联和访问；保存后台访问量截图与交互日志。
- 技术方案 PDF 小于 10 MB；演示视频 MP4、3-5 分钟且小于 300 MB。
- 作品方案、视频、答辩材料中不得出现学校名称、学校 LOGO 或指导教师信息。
- 代码包不包含学生论文、SQLite 数据库、默认口令、Secret Key、AIC 私钥或证书。

## 5. 分阶段实施

### P0：提交安全基线

- [x] 增加 `.gitignore`，阻止论文、数据库、日志和证书进入代码包。
- [x] 增加官方 ACPs SDK 可选依赖入口。
- [x] 增加 ACS 模板和评分差距表。
- [x] 删除演示环境默认口令；竞赛模式强制设置至少 12 位的管理员密码。
- [x] 增加 CSRF、登录限流、Cookie 安全属性、上传文件内容校验与安全响应头。
- [x] 增加“竞赛匿名模式”，统一隐藏学校和教师信息。

### P1：最小 AIP 闭环

- [x] 把格式与逻辑检查包装成两个 Partner `/rpc` 服务。
- [x] 实现任务状态、结构化输入和 JSON 产出物。
- [x] 实现本地 Leader，同时调用两个 Partner 并聚合结果。
- [x] 为 `start/get/continue/complete/cancel` 编写协议测试。
- [x] 实现跨阶段对比 Partner，支持开题/中期/终稿中的任意两个或三个阶段。
- [x] 提供 Web + 三 Partner 的一键启动、健康检查、冒烟测试和精确 PID 停止脚本。

### P1 本地运行

```powershell
.\.venv\Scripts\python.exe -m competition.aip_partner --role format --port 9021
.\.venv\Scripts\python.exe -m competition.aip_partner --role logic --port 9022
.\.venv\Scripts\python.exe -m competition.aip_leader "outputs\papers\student_2\示例.docx" --output "competition\aip-evidence.local.json"
```

本地模式关闭身份绑定，仅用于开发验证。梧桐平台部署必须设置正式 AIC、启用 `AIP_IDENTITY_BINDING_ENABLED=true`，并在反向代理或 ASGI 服务层配置平台签发的 mTLS 证书。

注册时分别以 `acs.format-partner.example.json`、`acs.logic-partner.example.json` 和 `acs.cross-stage-partner.example.json` 为模板，为三个 Partner 申请不同 AIC。`acs.paper-review-agent.example.json` 仅作为合并能力目录参考，不应替代三个实际 Partner 的注册信息。

平台注册的正确顺序是：先提交 ACS 等待审核，审核通过后平台才分配 AIC，随后用 `acps-cli` 获取 EAB 和 mTLS 证书。生成可上传 ACS 时不需要填写 AIC：

```powershell
.\.venv\Scripts\python.exe scripts\generate_acs.py --host format.example.com --role format
.\.venv\Scripts\python.exe scripts\generate_acs.py --host logic.example.com --role logic
.\.venv\Scripts\python.exe scripts\generate_acs.py --host cross.example.com --role cross-stage
```

脚本会去掉 `aic` 字段并生成 `competition/acs.<role>-partner.json`。正式部署时给 Leader 设置 `AIP_DISCOVERY_BASE_URL` 即可改用 ADP 自动发现；不设置该变量时仍使用 `AIP_FORMAT_URL`、`AIP_LOGIC_URL`、`AIP_CROSS_STAGE_URL` 指定的地址。

### 一键演示

```powershell
.\scripts\setup.ps1
$env:DEFAULT_TEACHER_PASSWORD = "替换为至少12位的强密码"
.\scripts\start_competition_demo.ps1
.\scripts\smoke_aip.ps1 -Document "论文样例.docx"
.\scripts\smoke_cross_stage.ps1 -Proposal "开题.docx" -Midterm "中期.docx" -Final "终稿.docx"
.\scripts\stop_competition_demo.ps1
```

Web 服务使用 Waitress，格式、逻辑、跨阶段三个 AIP Partner 使用 Uvicorn。启动脚本会进行四项健康检查并记录精确 PID；停止脚本只结束这些已记录进程。

跨阶段 Partner 接收 `documents` 数组，每项使用 `proposal`、`midterm` 或 `final` 阶段标识以及 DOCX 的 Base64 内容。它对相邻阶段计算正文主题、目标章节、标题结构、关键词和篇幅变化，输出 0–100 漂移分、风险等级、证据指标及修改建议。该结果属于确定性词汇与结构风险提示，不是语义事实判断或学术不端认定。

格式 Partner 按论文阶段套用规范（`tools/rules_schema.py` 的 `FINAL_ONLY_RULES`）：摘要、关键词、目录、参考文献著录、总字数与页眉等成稿型规则默认仅在终稿阶段启用，开题/中期自动跳过且不计入格式分，报告中标注「本阶段不适用」；「必需章节」在开题/中期自动替换为对应阶段的默认章节清单（`STAGE_SECTION_PRESETS`），教师自定义的清单不受影响。规则配置页对仅终稿适用的检查项有徽标提示。

2026-09-21 本地验收结果：Web `/health` 返回 `ok`，格式、逻辑、跨阶段 Partner 均返回 `completed`，全量自动化测试 `17 passed`。本地调用证据写入 `competition/aip-evidence.local.json` 和 `competition/cross-stage-evidence.local.json`；这些文件仅用于复现，不应替代 P2 的平台交互日志。

2026-10-02：格式规则阶段化（`FINAL_ONLY_RULES` 门控 + 必需章节分阶段默认值）落地，新增 5 项测试，全量自动化测试 `37 passed`。

### P2：赛事平台闭环

- [ ] 提交三个 Partner 的 ACS 并等待审核，获得各自 AIC。
- [ ] 使用 `acps-cli` 获取 EAB、证书、私钥与 trust bundle。
- [ ] 部署公网 HTTPS 服务并配置 `AIP_DISCOVERY_BASE_URL`，验证 ADP 自动发现。
- [ ] 开启 mTLS 与发送方 AIC 身份绑定。
- [ ] 完成梧桐平台跨端访问，保存时间戳、访问量、截图和原始交互日志。

**⚠️ 生产部署红线**：web 与全部三个 Partner 的启动环境必须包含 `COMPETITION_MODE=true`，否则页眉规则（`header_text`）会输出「西南科技大学」默认规范文案，违反材料匿名要求。systemd 单元示例：`Environment=COMPETITION_MODE=true`。部署后必须跨端调用一次并检查报告全文不含学校名。

### P3：竞争力与材料

- [x] 新增开题/中期/终稿输入类型和跨阶段对比 Partner。
- [x] 在学生 Web 页面增加三阶段上传、课题历史关联和对比报告展示。
- [x] 在教师提交页增加跨阶段报告列表与学生报告查看入口。
- [x] 建立 30 组匿名合成评测样本，低/中/高漂移各 10 组，并提供可复现生成器。
- [x] 建立真实样本匿名化、双教师独立标注、一致性计算和冲突裁决流程及标准标注表。
- [ ] 完成授权真实样本的实际双教师盲审并锁定正式人工标注基准。
- [x] 输出本机核心算法的 P50/P95、成功率、并发吞吐量、三分类准确率和漂移误报率。
- [ ] 在赛事平台环境复测包含 ADP、mTLS、网络和排队开销的端到端性能。
- [ ] 完成技术报告、3-5 分钟视频脚本、答辩 PPT 和证据索引。

### P3 评测基线结果

运行 `\.venv\Scripts\python.exe -m evaluation.run_benchmark` 可重新生成全部匿名 DOCX 并复测。当前本机结果：30 组全部成功，三分类准确率 90.0%，Macro F1 89.8%，漂移检出召回率 100.0%，低漂移误报率 0.0%；并发 1 的 P50/P95 为 68.19/90.83 ms，并发 4 的吞吐量为 26.00 组/秒。3 个边界型中漂移样本被判为高风险，保留为后续阈值校准证据。

详细定义与限制见 `evaluation/README.md`。上述结果来自确定性匿名合成样本和本机核心算法，不应表述为真实学生样本上的泛化结论或赛事平台端到端性能。

## 6. 需要从赛事平台取得的配置

实现平台接入前必须取得并只通过环境变量或忽略目录注入：

- 正式 AIC；
- EAB/注册凭据；
- Agent 证书、私钥与 trust bundle；
- Registry、CA、Discovery、Monitor、MQ 的正式地址；
- 梧桐平台对外可访问的 HTTPS RPC 地址。

不要把上述真实值填进 `acs.paper-review-agent.example.json` 后提交。
