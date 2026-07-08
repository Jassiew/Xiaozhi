// 生成符合武汉工程大学学报格式要求的论文 .docx 文件
const fs = require('fs');
const {
    Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
    Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
    ShadingType, PageNumber, PageBreak, TabStopType, TabStopPosition
} = require('docx');

const paper = require('./paper_content.js');

// ========== 格式常量 ==========
const FONT_CN = "宋体";
const FONT_HEI = "黑体";
const FONT_KAI = "方正楷体";
const FONT_FZFS = "方正仿宋";
const FONT_EN = "Times New Roman";

function cnRun(text, size = 21, font = FONT_CN, bold = false) {
    return new TextRun({ text, font: { name: font }, size, bold, characterSpacing: 0 });
}
function enRun(text, size = 21, bold = false, italics = false) {
    return new TextRun({ text, font: { name: FONT_EN }, size, bold, italics, characterSpacing: 0 });
}
function mixPara(runs, alignment = AlignmentType.JUSTIFIED, spacing = { line: 312 }) {
    return new Paragraph({ children: runs, alignment, spacing });
}

// ========== 构建文档 ==========
const doc = new Document({
    styles: {
        default: {
            document: { run: { font: FONT_CN, size: 21 } } // 五号 = 10.5pt = 21 half-pts
        }
    },
    sections: [
        // ===== 中文标题页 =====
        {
            properties: {
                page: {
                    size: { width: 11906, height: 16838 }, // A4
                    margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
                }
            },
            headers: {
                default: new Header({
                    children: [new Paragraph({
                        children: [cnRun("", 15)],
                        border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000", space: 4 } }
                    })]
                })
            },
            children: [
                // 空行
                new Paragraph({ children: [cnRun("")], spacing: { before: 400 } }),

                // 中文标题 - 二号黑体居中
                new Paragraph({
                    children: [cnRun(paper.titleCN, 44, FONT_HEI, true)],
                    alignment: AlignmentType.CENTER,
                    spacing: { before: 400, after: 200 }
                }),
                // 副标题
                new Paragraph({
                    children: [cnRun(paper.subtitleCN, 36, FONT_HEI)],
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 400 }
                }),

                // 作者 - 四号方正仿宋居中
                new Paragraph({
                    children: [cnRun(paper.authorsCN, 28, FONT_FZFS)],
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 200 }
                }),

                // 单位 - 五号楷体居中
                new Paragraph({
                    children: [cnRun(paper.affiliationCN, 21, FONT_KAI)],
                    alignment: AlignmentType.CENTER,
                    spacing: { before: 200, after: 400 }
                }),

                // 摘要标签
                new Paragraph({
                    children: [cnRun("摘  要：", 18, FONT_HEI, true)],
                    spacing: { line: 312 }
                }),
                // 摘要内容
                new Paragraph({
                    children: [cnRun(paper.abstractCN, 18, FONT_CN)],
                    spacing: { line: 312 },
                    indent: { firstLine: 0 }
                }),

                // 关键词
                new Paragraph({
                    children: [
                        cnRun("关键词：", 18, FONT_HEI, true),
                        cnRun(paper.keywordsCN, 18, FONT_CN),
                    ],
                    spacing: { line: 312, before: 100 }
                }),

                // 中图分类号
                new Paragraph({
                    children: [
                        cnRun("中图分类号：TP391.4", 18, FONT_HEI, true),
                        cnRun("    文献标识码：A", 18, FONT_CN),
                    ],
                    spacing: { line: 312, before: 100 }
                }),

                // ===== 英文部分 =====
                new Paragraph({ children: [cnRun("")], spacing: { before: 400 } }),

                // 英文标题 - 4号 Times New Roman 加粗居中
                new Paragraph({
                    children: [enRun(paper.titleEN, 28, true)],
                    alignment: AlignmentType.CENTER,
                    spacing: { before: 200, after: 200 }
                }),

                // 英文作者 - 五号斜体居中
                new Paragraph({
                    children: [enRun(paper.authorsEN, 21, false, true)],
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 100 }
                }),

                // 英文单位
                new Paragraph({
                    children: [enRun(paper.affiliationEN, 18)],
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 200 }
                }),

                // 英文摘要
                new Paragraph({
                    children: [enRun("Abstract: ", 21, true)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [enRun(paper.abstractEN, 21)],
                    spacing: { line: 312 }
                }),

                // 英文关键词
                new Paragraph({
                    children: [
                        enRun("Keywords: ", 21, true),
                        enRun(paper.keywordsEN, 21),
                    ],
                    spacing: { line: 312, before: 100 }
                }),

                // ===== 分页：正文开始 =====
                new Paragraph({ children: [new PageBreak()] }),

                // ===== 0. 引言 =====
                sectionHeading("0  引  言"),
                ...bodyParagraphs(paper.section1_intro),

                // ===== 1. 相关工作 =====
                sectionHeading("1  相关工作"),
                ...bodyParagraphs(paper.section2_related),

                // ===== 2. 方法 =====
                sectionHeading("2  方法"),
                ...bodyParagraphs(paper.section3_method),

                // ===== 3. 实验与分析 =====
                sectionHeading("3  实验与分析"),
                ...bodyParagraphs(paper.section4_experiment),

                // ===== 4. 讨论 =====
                sectionHeading("4  挑战、局限性与未来展望"),
                ...bodyParagraphs(paper.section5_discussion),

                // ===== 5. 结论 =====
                sectionHeading("5  结  论"),
                ...bodyParagraphs(paper.section6_conclusion),

                // 致谢
                new Paragraph({ children: [cnRun("")], spacing: { before: 200 } }),
                new Paragraph({
                    children: [cnRun(paper.acknowledgements, 21, FONT_KAI)],
                    spacing: { line: 312 }
                }),

                // ===== 参考文献 =====
                new Paragraph({ children: [new PageBreak()] }),
                new Paragraph({
                    children: [cnRun("参考文献", 18, FONT_HEI, true)],
                    spacing: { before: 200, after: 200, line: 312 },
                    alignment: AlignmentType.CENTER
                }),
                ...paper.references.map(ref =>
                    new Paragraph({
                        children: [cnRun(ref, 18, FONT_CN)],
                        spacing: { line: 312 },
                        indent: { firstLine: 0 }
                    })
                ),

                // ===== 代码附录 =====
                new Paragraph({ children: [new PageBreak()] }),
                new Paragraph({
                    children: [cnRun("附录：代码与开源仓库", 28, FONT_HEI, true)],
                    spacing: { before: 200, after: 200, line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("本文涉及的系统代码已开源，GitHub仓库地址如下：", 21, FONT_CN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("", 21, FONT_CN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("后端分析系统（含CBPH-Net推理模块、Agent LLM对话模块、Web管理端）：", 21, FONT_HEI, true)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("https://github.com/[your-username]/student-monitor", 21, FONT_EN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("", 21, FONT_CN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("ESP32-S3设备固件（含SenseCAP Watcher摄像头驱动、WebSocket帧上传、SSCMA推理）：", 21, FONT_HEI, true)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("https://github.com/[your-username]/xiaozhi-esp32", 21, FONT_EN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("", 21, FONT_CN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("CBPH-Net训练代码及模型权重：", 21, FONT_HEI, true)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("https://github.com/icedle/CBPH-Net", 21, FONT_EN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("", 21, FONT_CN)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("SCB-Dataset公开数据集：", 21, FONT_HEI, true)],
                    spacing: { line: 312 }
                }),
                new Paragraph({
                    children: [cnRun("https://github.com/Whiffe/SCB-dataset", 21, FONT_EN)],
                    spacing: { line: 312 }
                }),
            ]
        }
    ]
});

// ========== 辅助函数 ==========
function sectionHeading(text) {
    return new Paragraph({
        children: [cnRun(text, 28, FONT_HEI, true)],
        spacing: { before: 400, after: 200, line: 312 },
    });
}

function bodyParagraphs(text) {
    const paragraphs = text.split(/\n{2,}/).filter(p => p.trim());
    return paragraphs.flatMap(p => {
        const trimmed = p.trim();

        // 图表占位标记
        if (trimmed.startsWith("【此处插入")) {
            return [
                new Paragraph({
                    children: [cnRun(trimmed, 21, FONT_KAI)],
                    spacing: { line: 312, before: 200, after: 100 },
                    alignment: AlignmentType.CENTER,
                    border: {
                        top: { style: BorderStyle.DASHED, size: 1, color: "999999" },
                        bottom: { style: BorderStyle.DASHED, size: 1, color: "999999" },
                        left: { style: BorderStyle.DASHED, size: 1, color: "999999" },
                        right: { style: BorderStyle.DASHED, size: 1, color: "999999" },
                    }
                })
            ];
        }

        // 图题：以"图"或"Fig"开头 → 居中、段前空一行
        if (trimmed.startsWith("图") && trimmed.includes("Fig")) {
            const lines = trimmed.split("\n");
            return lines.map(line => {
                if (line.startsWith("图")) {
                    return new Paragraph({
                        children: [cnRun(line, 18, FONT_HEI, true)],
                        spacing: { line: 312, before: 200 },
                        alignment: AlignmentType.CENTER,
                    });
                } else if (line.startsWith("Fig")) {
                    return new Paragraph({
                        children: [enRun(line, 18)],
                        spacing: { line: 312, after: 100 },
                        alignment: AlignmentType.CENTER,
                    });
                } else if (line.startsWith("(") || line.startsWith("注")) {
                    return new Paragraph({
                        children: [cnRun(line, 15, FONT_KAI)],
                        spacing: { line: 280 },
                        alignment: AlignmentType.CENTER,
                    });
                }
                return new Paragraph({ children: [cnRun(line, 15, FONT_CN)], spacing: { line: 280 } });
            });
        }

        // 表题：以"表"或"Tab"开头 → 居中
        if (trimmed.startsWith("表") && trimmed.includes("Tab")) {
            const lines = trimmed.split("\n");
            return lines.map(line => {
                if (line.startsWith("表")) {
                    return new Paragraph({
                        children: [cnRun(line, 18, FONT_HEI, true)],
                        spacing: { line: 312, before: 200 },
                        alignment: AlignmentType.CENTER,
                    });
                } else if (line.startsWith("Tab")) {
                    return new Paragraph({
                        children: [enRun(line, 18)],
                        spacing: { line: 312, after: 100 },
                        alignment: AlignmentType.CENTER,
                    });
                }
                return new Paragraph({ children: [cnRun(line, 15, FONT_CN)], spacing: { line: 280 } });
            });
        }

        // 普通正文段落
        return [new Paragraph({
            children: [cnRun(trimmed, 21, FONT_CN)],
            spacing: { line: 312 },
            indent: { firstLine: 420 },
        })];
    });
}

// ========== 生成文件 ==========
Packer.toBuffer(doc).then(buffer => {
    const outputPath = 'D:/Xiaozhi/student-monitor/结课论文_大模型时代课堂行为理解新范式.docx';
    fs.writeFileSync(outputPath, buffer);
    console.log('论文已生成: ' + outputPath);
    console.log('正文字数约: ' + countChineseChars() + ' 字');
}).catch(err => {
    console.error('生成失败:', err);
});

function countChineseChars() {
    let total = 0;
    const sections = [
        paper.section1_intro, paper.section2_related, paper.section3_method,
        paper.section4_experiment, paper.section5_discussion, paper.section6_conclusion
    ];
    sections.forEach(s => {
        total += (s.match(/[一-鿿]/g) || []).length;
    });
    return total;
}
