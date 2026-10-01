import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = process.argv[2] || "outputs/blind-review/teacher_blind_review_template.xlsx";
const fontName = "Arial";
const navy = "#17365D";
const blue = "#D9EAF7";
const lightBlue = "#EDF4FA";
const inputFill = "#FFF2CC";
const border = "#C7D2E0";
const redFill = "#FCE8E6";
const greenFill = "#E2F0D9";

const workbook = Workbook.create();
const summary = workbook.worksheets.add("使用说明");
const review = workbook.worksheets.add("标注记录");
const rubric = workbook.worksheets.add("判定口径");

for (const sheet of [summary, review, rubric]) {
  sheet.showGridLines = false;
}
summary.tabColor = navy;
review.tabColor = "#4472C4";
rubric.tabColor = "#A9BCD0";

summary.getRange("A2:H2").merge();
summary.getRange("A2").values = [["跨阶段真实匿名样本教师盲审标注表"]];
summary.getRange("A2").format = { font: { name: fontName, size: 16, bold: true, color: navy } };
summary.getRange("A3:H3").format.borders = { bottom: { style: "thin", color: navy } };
summary.getRange("A5:B8").values = [
  ["评审人代码", ""],
  ["批次编号", ""],
  ["标注日期", ""],
  ["样本总数", "=COUNTA('标注记录'!B6:B55)"],
];
summary.getRange("B5:B7").format.fill = inputFill;
summary.getRange("B7").format.numberFormat = "yyyy-mm-dd";
summary.getRange("A5:A8").format.font = { name: fontName, bold: true, color: navy };
summary.getRange("A10:B15").values = [
  ["完成情况", "数量"],
  ["已完成", "=COUNTIFS('标注记录'!L6:L55,\"yes\")"],
  ["未完成", "=B8-B11"],
  ["低风险", "=COUNTIFS('标注记录'!H6:H55,\"low\",'标注记录'!L6:L55,\"yes\")"],
  ["中风险", "=COUNTIFS('标注记录'!H6:H55,\"medium\",'标注记录'!L6:L55,\"yes\")"],
  ["高风险", "=COUNTIFS('标注记录'!H6:H55,\"high\",'标注记录'!L6:L55,\"yes\")"],
];
summary.getRange("A10:B10").format = { fill: navy, font: { name: fontName, bold: true, color: "#FFFFFF" } };
summary.getRange("A10:B15").format.borders = { preset: "outside", style: "thin", color: border };
summary.getRange("D5:H12").values = [
  ["操作要求", "", "", "", ""],
  ["1", "只查看匿名文档，不查看算法分数或另一位教师的标注。", "", "", ""],
  ["2", "先在“判定口径”阅读 low / medium / high / uncertain 定义。", "", "", ""],
  ["3", "每个分项填 1–5；总体风险单独综合判断，不能机械换算。", "", "", ""],
  ["4", "证据位置写章节或标题；理由保持简洁，不复制大段论文原文。", "", "", ""],
  ["5", "无法可靠定级时选 uncertain，交由裁决人处理。", "", "", ""],
  ["6", "完成一行后将 review_complete 改为 yes。", "", "", ""],
  ["7", "回收后保留原始文件，不覆盖或补写另一位教师的记录。", "", "", ""],
];
summary.getRange("D5:H5").merge();
summary.getRange("D5:H5").format = { fill: navy, font: { name: fontName, bold: true, color: "#FFFFFF" } };
for (let row = 6; row <= 12; row += 1) summary.getRange(`E${row}:H${row}`).merge();
summary.getRange("D6:H12").format = { fill: lightBlue, font: { name: fontName, size: 10 }, wrapText: true };
summary.getRange("A2:H15").format.verticalAlignment = "center";
summary.getRange("A1:H20").format.font = { name: fontName, size: 10 };
summary.getRange("A:A").format.columnWidth = 16;
summary.getRange("B:B").format.columnWidth = 18;
summary.getRange("C:C").format.columnWidth = 3;
summary.getRange("D:D").format.columnWidth = 6;
summary.getRange("E:H").format.columnWidth = 16;
summary.getRange("D6:H12").format.rowHeight = 30;

review.getRange("A2:L2").merge();
review.getRange("A2").values = [["教师独立标注记录"]];
review.getRange("A2").format = { font: { name: fontName, size: 15, bold: true, color: navy } };
review.getRange("A3:L3").merge();
review.getRange("A3").values = [["黄色单元格由评审填写。case_id 与 available_stages 由数据协调员导入。"]];
review.getRange("A3").format = { font: { name: fontName, size: 10, italic: true, color: "#5B6573" } };
review.getRange("A5:L5").values = [[
  "reviewer_code", "case_id", "available_stages", "topic_continuity_1_5",
  "objective_continuity_1_5", "method_continuity_1_5", "scope_change",
  "overall_risk", "confidence_1_5", "evidence_location", "rationale", "review_complete",
]];
review.getRange("A5:L5").format = {
  fill: navy,
  font: { name: fontName, size: 10, bold: true, color: "#FFFFFF" },
  wrapText: true,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#FFFFFF" },
};
review.getRange("A6:L55").format = { font: { name: fontName, size: 10 }, verticalAlignment: "center" };
review.getRange("A6:A55").format.fill = inputFill;
review.getRange("B6:C55").format.fill = "#E7E6E6";
review.getRange("D6:L55").format.fill = inputFill;
review.getRange("A6:L55").format.borders = {
  insideHorizontal: { style: "thin", color: border },
  bottom: { style: "thin", color: border },
};
review.getRange("A6:A55").dataValidation = { rule: { type: "list", values: ["A", "B"] } };
for (const col of ["D", "E", "F", "I"]) {
  review.getRange(`${col}6:${col}55`).dataValidation = {
    rule: { type: "whole", operator: "between", formula1: 1, formula2: 5 },
  };
}
review.getRange("G6:G55").dataValidation = {
  rule: { type: "list", values: ["none", "refinement", "partial", "replacement", "uncertain"] },
};
review.getRange("H6:H55").dataValidation = {
  rule: { type: "list", values: ["low", "medium", "high", "uncertain"] },
};
review.getRange("L6:L55").dataValidation = { rule: { type: "list", values: ["no", "yes"] } };
review.getRange("L6:L55").values = Array.from({ length: 50 }, () => ["no"]);
review.getRange("H6:H55").conditionalFormats.add("containsText", {
  text: "high", format: { fill: redFill, font: { color: "#9C0006", bold: true } },
});
review.getRange("L6:L55").conditionalFormats.add("containsText", {
  text: "yes", format: { fill: greenFill, font: { color: "#375623" } },
});
review.getRange("A5:L55").format.wrapText = false;
review.getRange("J6:K55").format.wrapText = true;
review.freezePanes.freezeRows(5);
review.freezePanes.freezeColumns(3);
const widths = [16, 14, 22, 25, 29, 26, 18, 17, 20, 24, 36, 18];
widths.forEach((width, index) => { review.getRangeByIndexes(0, index, 55, 1).format.columnWidth = width; });
review.getRange("A5:L5").format.rowHeight = 42;
review.getRange("A6:L55").format.rowHeight = 32;

rubric.getRange("A2:F2").merge();
rubric.getRange("A2").values = [["跨阶段漂移判定口径"]];
rubric.getRange("A2").format = { font: { name: fontName, size: 15, bold: true, color: navy } };
rubric.getRange("A4:F8").values = [
  ["总体标签", "研究对象/问题", "研究目标", "方法与范围", "判断原则", "处理"],
  ["low", "保持一致", "保持一致或正常细化", "实现方式可调整", "后续阶段仍清楚延续原课题", "直接纳入一致性统计"],
  ["medium", "部分变化", "至少一项核心目标实质变化", "仍能追溯原主线", "变化显著但不是课题替换", "直接纳入一致性统计"],
  ["high", "明显替换", "主要目标被替换", "研究范围或成果类型改变", "难以视为原课题连续发展", "直接纳入一致性统计"],
  ["uncertain", "信息不足或冲突", "无法可靠判断", "疑似错版或材料缺失", "不得勉强定级", "必须进入裁决"],
];
rubric.getRange("A4:F4").format = { fill: navy, font: { name: fontName, bold: true, color: "#FFFFFF" }, wrapText: true };
rubric.getRange("A5:F8").format = { font: { name: fontName, size: 10 }, wrapText: true, verticalAlignment: "top" };
rubric.getRange("A4:F8").format.borders = {
  insideHorizontal: { style: "thin", color: border },
  bottom: { style: "thin", color: border },
};
rubric.getRange("A10:C16").values = [
  ["连续性分值", "含义", "使用提示"],
  [1, "完全不连续", "研究对象、核心问题或目标已替换"],
  [2, "连续性较弱", "保留少量元素，但核心方向明显变化"],
  [3, "部分延续", "主线仍可追溯，同时存在实质调整"],
  [4, "较高连续", "主线稳定，存在正常细化或方法调整"],
  [5, "高度连续", "核心对象、问题和目标均稳定"],
  ["注意", "分项分数不自动生成总体标签", "总体风险须结合证据独立判断"],
];
rubric.getRange("A10:C10").format = { fill: navy, font: { name: fontName, bold: true, color: "#FFFFFF" } };
rubric.getRange("A11:C16").format = { font: { name: fontName, size: 10 }, wrapText: true };
rubric.getRange("A10:C16").format.borders = {
  insideHorizontal: { style: "thin", color: border },
  bottom: { style: "thin", color: border },
};
rubric.getRange("A:A").format.columnWidth = 15;
rubric.getRange("B:B").format.columnWidth = 24;
rubric.getRange("C:C").format.columnWidth = 32;
rubric.getRange("D:F").format.columnWidth = 28;
rubric.getRange("A4:F8").format.rowHeight = 44;
rubric.getRange("A10:C16").format.rowHeight = 34;
rubric.freezePanes.freezeRows(4);

// Exercise the workflow once, then restore the distributed template to blank.
review.getRange("A6:C6").values = [["A", "BR001", "proposal|final"]];
review.getRange("D6:I6").values = [[4, 4, 3, "refinement", "low", 4]];
review.getRange("J6:L6").values = [["研究目标章节", "研究主线延续。", "yes"]];
workbook.recalculate();
const workflowCheck = await workbook.inspect({
  kind: "table",
  range: "使用说明!A8:B15",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 3,
});
console.log(workflowCheck.ndjson);
review.getRange("A6:K6").clear({ applyTo: "contents" });
review.getRange("L6").values = [["no"]];
workbook.recalculate();

const keyCheck = await workbook.inspect({
  kind: "table",
  range: "使用说明!A2:H15",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 10,
});
const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(keyCheck.ndjson);
console.log(errorCheck.ndjson);

const previewDir = await fs.mkdtemp(path.join(os.tmpdir(), "blind-review-preview-"));
for (const [sheetName, range] of [["使用说明", "A1:H16"], ["标注记录", "A1:L16"], ["判定口径", "A1:F17"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
console.log(`PREVIEW_DIR=${previewDir}`);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT=${path.resolve(outputPath)}`);
