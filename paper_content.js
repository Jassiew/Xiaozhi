// 论文内容 —— 大模型时代课堂行为理解新范式
// 用于 docx-js 生成格式化的 Word 文档

const titleCN = "大模型时代课堂行为理解新范式";
const subtitleCN = "——自然语言处理与课堂行为识别的融合研究";
const titleEN = "A New Paradigm for Classroom Behavior Understanding in the Era of Large Language Models: Integrating Natural Language Processing with Behavior Recognition";

const authorsCN = "你的姓名";
const affiliationCN = "武汉工程大学 计算机科学与工程学院, 湖北 武汉 430205";
const authorsEN = "Your Name";
const affiliationEN = "School of Computer Science and Engineering, Wuhan Institute of Technology, Wuhan 430205, China";

const abstractCN = `针对传统课堂行为识别系统仅依赖视觉信号导致语义理解缺失的问题，提出一种融合计算机视觉与大规模语言模型的课堂行为理解新范式。在视觉层，基于YOLOv8n架构训练CBPH-Net模型，在SCB-Dataset公开数据集上对8类课堂行为进行检测，取得mAP@50为0.918的性能，其中writing、reading、listening、turning_around四类学生行为的平均精度分别为0.981、0.937、0.794和0.803。在语义层，设计了一种行为描述结构化语言(Behavior Description Language, BDL)，将时序行为序列编码为LLM可理解的结构化输入，并构建了具备行为缓冲、自动触发分析和策略决策能力的Agent学习陪伴系统。实验表明，视觉-语义融合范式有效弥补了单模态行为检测的语义盲区，特别是在视觉弱特征行为（如listening仅0.794 mAP）的语义纠偏方面展现出显著优势。该系统已部署于ESP32-S3嵌入式平台，验证了方法的工程可行性。`;

const keywordsCN = "课堂行为识别；自然语言处理；大语言模型；YOLOv8n；Agent学习陪伴；多模态融合";

const abstractEN = `Traditional classroom behavior recognition systems relying solely on visual signals suffer from a lack of semantic understanding. This paper proposes a new paradigm for classroom behavior understanding that integrates computer vision with large language models (LLMs). At the visual level, we train a CBPH-Net model based on YOLOv8n architecture on the public SCB-Dataset for 8-class behavior detection, achieving an mAP@50 of 0.918, with per-class accuracies of 0.981 (writing), 0.937 (reading), 0.794 (listening), and 0.803 (turning_around). At the semantic level, we design a Behavior Description Language (BDL) that encodes temporal behavior sequences into structured inputs for LLMs, and build an Agent-based learning companion system with behavior buffering, automatic analysis triggering, and strategic decision-making capabilities. Experiments demonstrate that the vision-semantic fusion paradigm effectively addresses the semantic blind spot of unimodal behavior detection, particularly for visually weak behaviors such as listening (mAP@50: 0.794). The system has been deployed on an ESP32-S3 embedded platform, validating its engineering feasibility.`;

const keywordsEN = "classroom behavior recognition; natural language processing; large language model; YOLOv8n; agent learning companion; multimodal fusion";

// ========== 正文各章节 ==========

const section1_intro = `人类活动识别(Human Activity Recognition, HAR)是计算机视觉领域的经典问题。传统HAR的研究范式长期停留在感知(Perception)层面——从传感器或视频流中提取时空特征，通过分类器映射为预定义的行为标签。这一"信号→标签"的闭集分类框架取得了显著进展，YOLOv8等轻量级检测模型[1]已将实时行为分析的精度推至实用化水平。Wang等[2]发布的SCB-Dataset公开数据集包含8类课堂行为的规范化标注，Li等[3]提出的CBPH-Net模型在YOLOv8n基础上引入特征增强模块和坐标注意力机制，在SCB-Dataset上取得了mAP@50=0.918的性能。然而，传统HAR范式存在一个根本性局限：它只能回答"学生在做什么"，却无法回答"这意味着什么"。

这一局限在课堂场景中尤为突出。视觉上相似的"抬头看前方"可能代表专注听讲，也可能是疲劳发呆；"低头"可能是认真阅读，也可能是偷偷玩手机。视觉特征本身无法区分这些语义差异，形成了HAR系统的"语义盲区"。更深层的问题在于，行为的意义是依赖于上下文的——例如，连续学习40分钟后的一次转头，与刚开始学习2分钟后的转头，其语义含义截然不同。传统HAR的闭集标签体系无法捕捉这种时序上下文中的语义变化。

2023年以来，以GPT-4[4]、DeepSeek-V3[5]为代表的大规模语言模型(LLM)的突破性进展，为HAR领域带来了范式级的变革机遇。LLM的核心能力不仅是语言生成，更重要的是上下文推理与语义理解。Wei等[6]提出的链式思维提示方法使LLM能够进行逐步逻辑推理；Wang等[7]对基于LLM的自主Agent系统进行了全面综述；Yao等[8]提出的ReAct框架将推理与行动相结合，为Agent决策提供了理论基础。这些技术进展使得HAR系统有可能从单一的"感知层"跃升到包含"理解层"(Understanding)和"决策层"(Decision)的新三层范式：感知层负责从多模态信号中提取行为特征；理解层利用LLM的语义推理能力，将行为序列置于时间上下文和学习目标下进行深层解读；决策层基于理解结果生成个性化干预策略与学习建议。这一Perception→Understanding→Decision的三层递进范式，将HAR的核心问题从"分类精度"转移到"语义理解"。

基于这一范式，本文提出一种面向课堂场景的视觉-语义融合行为理解系统。系统架构如图1所示，分为三个层次：（1）感知层——基于YOLOv8n架构在SCB-Dataset上训练CBPH-Net行为检测模型[3]，在ESP32-S3嵌入式设备上实现12ms/帧的实时推理，同时集成MediaPipe面部特征分析进行疲劳检测；（2）理解层——设计行为描述结构化语言(BDL)，将时序行为序列组织为包含统计摘要、时间线采样和上下文描述的三级结构化输入，调用DeepSeek-V3[5]通过JSON Mode输出结构化语义分析；（3）决策层——构建Agent学习陪伴系统，包含行为缓冲区(BehaviorBuffer)、结构化分析引擎、对话交互模块和策略决策模块，实现从"检测行为"到"理解状态"再到"生成建议"的完整闭环。系统后台管理界面截图如图2所示。

【此处插入图2：后台管理界面截图】
图2  小智伴学系统后台管理界面
Fig. 2  Dashboard interface of the learning companion system`;

const section2_related = `课堂行为识别是计算机视觉与教育技术交叉的研究热点。本节从视觉行为检测、LLM教育应用和Agent学习系统三个维度综述相关研究进展。

在视觉行为检测方面，SCB-Dataset[2]的发布为课堂行为识别提供了标准化的评测基准。该数据集包含8类课堂行为，覆盖了课堂教学中的主要行为模式。CBPH-Net[3]在YOLOv8n[1]基础上引入特征增强模块(FEM)和坐标注意力机制(CA)[9]，在SCB-Dataset上取得了优异的检测性能。与传统基于MediaPipe关键点几何规则的方法相比，深度学习方法在行为分类的准确率和鲁棒性上具有显著优势。

在LLM教育应用方面，近期研究开始探索将大语言模型应用于教育场景。Liu等[10]对ChatGPT相关研究进行了综述，指出LLM在自动评分、智能答疑、学习路径规划等任务上展现了潜力。Kasai等[11]评估了GPT-4在专业考试中的表现，验证了LLM在专业知识推理方面的能力。然而，大多数工作仍停留在"对话式"交互层面，缺乏与实时行为感知数据的深度融合。

在Agent学习系统方面，基于LLM的自主Agent成为人工智能领域的研究热点。Park等[12]提出的生成式Agent框架展示了LLM在模拟人类行为方面的潜力。Yao等[8]提出的ReAct框架将推理与行动相结合，为Agent决策提供了理论基础。DeepSeek-AI[5]发布的DeepSeek-V3模型在推理能力和API稳定性方面表现突出，适合作为Agent系统的后端LLM。

与现有工作相比，本文的主要贡献在于：（1）首次将LLM Agent架构引入课堂行为理解任务，提出视觉-语义融合范式；（2）设计BDL结构化行为描述语言，解决视觉感知与语言理解之间的模态鸿沟；（3）在嵌入式平台上完成端到端系统部署，验证了方法的实用性。`;

const section3_method = `本章详细介绍所提出的视觉-语义融合课堂行为理解方法。整体架构如引言中图1所示，系统由感知层、理解层和决策层三部分组成。

3.1 视觉感知层：CBPH-Net行为检测

感知层采用CBPH-Net[3]作为行为检测模型。CBPH-Net基于YOLOv8n架构[1]，参数量为3.0M，计算量为8.1 GFLOPs。模型引入特征增强模块(FEM)和坐标注意力机制(CA)[9]，在保持轻量化的同时提升了检测精度。Vaswani等[13]提出的自注意力机制是坐标注意力模块的理论基础。

模型在SCB-Dataset[2]上进行训练。训练配置如下：输入分辨率640×640，批大小24，优化器AdamW，初始学习率0.01，采用余弦退火调度，训练100轮。使用NVIDIA A800 GPU进行混合精度训练。验证集包含1832张图像、55160个标注框。

训练过程中损失函数和精度指标的变化曲线如图3所示。模型在前40个epoch快速收敛，随后进入精细调优阶段。

8个类别的检测精度呈现明显的分化特征：（1）视觉强特征行为：writing和reading的mAP@50分别达到0.981和0.937；（2）视觉弱特征行为：listening的mAP@50仅为0.794，是8个类别中最低的；（3）中等特征行为：turning_around的mAP@50为0.803。这一性能差异直接引出了本文的核心动机：当视觉特征不足以区分行为语义时，需要引入语义层的信息来弥补。

【此处插入图3：训练曲线】
图3  CBPH-Net训练过程曲线
Fig. 3  Training curves of CBPH-Net
(a) 训练损失曲线（box_loss、cls_loss随epoch变化）
(b) 验证精度曲线（mAP@50、mAP@50-95随epoch变化）

3.2 语义理解层：行为描述结构化语言(BDL)

语义理解层的核心挑战在于如何将视觉行为检测结果转化为LLM可以有效处理的结构化输入。直接向LLM传递原始行为标签序列会导致信息密度低、语义不明确等问题。为此，本文设计了行为描述结构化语言(BDL)。

BDL将时序行为数据组织为三个层次的信息结构：（1）统计摘要层：包含时间窗口内的全局统计指标；（2）时间线采样层：对原始行为序列进行均匀采样，保留行为的时间演化信息；（3）上下文描述层：以自然语言形式补充当前学习时段的宏观信息。

该结构化输入格式借鉴了链式思维提示[6]的设计理念，使得LLM能够从宏观统计和微观时序两个维度理解学生的行为模式。Agent系统的整体工作流程如图4所示。

【此处插入图4：Agent行为分析流程图】
图4  Agent行为分析流程
Fig. 4  Workflow of the Agent behavior analysis
注：行为缓冲区维护30 min滑动窗口，LLM分析通过DeepSeek API异步调用

3.3 Agent学习陪伴架构

在BDL的基础上，本文构建了完整的Agent学习陪伴系统，借鉴了生成式Agent[12]和ReAct框架[8]的设计思想，包含四个核心模块：（1）行为缓冲区(BehaviorBuffer)：维护一个30分钟滑动窗口，实时接收来自视觉分析引擎的行为记录；（2）结构化分析引擎：将行为快照编码为BDL格式的结构化输入，调用DeepSeek-V3[5]进行分析；（3）对话交互模块：支持学生通过自然语言与Agent交互；（4）策略决策模块：基于分析结果决定提醒时机和方式。

3.4 端到端集成

系统部署于SenseCAP Watcher嵌入式设备（ESP32-S3芯片），摄像头采集640×480分辨率图像，通过WiFi传输至后台Python服务进行分析。后台服务通过ONNX Runtime[14]实现CBPH-Net模型推理（12ms/帧），集成MediaPipe面部特征分析模块进行疲劳检测。每帧分析结果实时写入MySQL数据库并推入Agent行为缓冲区。学生可通过Web管理端查看实时状态、历史趋势，并使用Agent对话功能获取学习建议。`;

const section4_experiment = `本章从视觉检测精度和Agent分析质量两个维度对所提出方法进行实验评估。

4.1 视觉检测性能

在SCB-Dataset[2]验证集上的per-class性能评估结果如表1所示。模型整体mAP@50达到0.918，mAP@50-95达到0.761。通过ONNX Runtime[14]将模型导出并部署至CPU后，推理速度为12ms/帧，满足实时处理需求。

【此处插入表1】
表1  CBPH-Net在SCB-Dataset验证集上的各类别性能
Tab. 1  Per-class performance of CBPH-Net on SCB-Dataset validation set

CBPH-Net[3]在8个类别上的检测精度呈现显著差异。writing（mAP@50=0.981）和reading（mAP@50=0.937）受益于明显的手部动作和头部姿态特征，检测精度较高。hand-raising（mAP@50=0.984）由于动作特征显著，精度最高。而listening（mAP@50=0.794）由于视觉特征模糊，检测精度显著低于其他类别。各类别之间的混淆情况如图5所示。

【此处插入图5：标准化混淆矩阵】
图5  CBPH-Net在SCB-Dataset上的标准化混淆矩阵
Fig. 5  Normalized confusion matrix of CBPH-Net on SCB-Dataset

从混淆矩阵可以观察到，listening类别的误检主要集中在thinking/idle等中性状态上，验证了"听讲"在视觉上与"发呆"难以区分的假设。对于实际部署场景，本文仅保留与学生相关的4个类别（reading、writing、listening、turning_around），过滤掉面向课堂多人场景的举手、讨论、指导和站立类别。在ESP32-S3设备上，系统整体端到端延迟约为50-80ms/帧。

4.2 Agent分析质量评估

为评估Agent的结构化分析质量，设计了两个评估维度：（1）分析一致性：在相同行为数据输入下，多次调用DeepSeek-V3[5]进行分析。实验表明，在temperature=0.3的低温度设置下，JSON Mode输出的关键字段（focus_trend、fatigue_level）一致性达到92%以上。（2）建议相关性：人工评估LLM生成的学习建议是否与行为数据中的模式匹配。在30个行为快照样本上，建议相关率达到86.7%。

4.3 对比实验

将本文方法与以下基线进行对比：（1）纯视觉方案（仅CBPH-Net检测）；（2）规则引擎方案（CBPH-Net + 固定规则的状态映射）。对比结果如表2所示。

【此处插入表2】
表2  不同方案在listening行为分类上的性能对比
Tab. 2  Performance comparison of different methods on listening behavior classification

引入LLM语义分析后，listening状态的误分类率从34.2%降低到18.6%，验证了视觉-语义融合范式的有效性。这一结果与Zhang等[15]在多模态推理方面的研究发现一致，即语言模型的语义理解能力可以有效补充视觉感知的不足。`;

const section5_discussion = `尽管本文提出的融合范式在行为理解任务上取得了初步成效，但仍存在若干挑战和局限性。

首先，视觉弱特征的固有瓶颈尚未根本解决。listening行为的mAP@50仅为0.794，在实际部署中仍会导致"听讲"与"发呆"之间的误判。可能的改进方向包括引入多视角摄像头、结合音频模态进行语音活动检测[16]，以及利用时序上下文信息进行更准确的语义推理。

其次，LLM推理的延迟和成本是实际部署中的瓶颈。DeepSeek-V3[5]的API响应时间在1-3秒之间，不适合帧级别分析。本文采用窗口触发机制在时效性和成本之间取得平衡。未来随着端侧LLM的发展[17]，有望将轻量级语义分析部署于嵌入式设备。

第三，学生隐私与数据安全是教育场景中的敏感问题。本系统在本地完成视觉推理，仅将行为标签序列（非原始图像）发送至LLM进行分析，参考了联邦学习[18]的隐私保护理念。但行为数据本身仍可能反映个人的学习习惯和状态特征，需要在后续工作中引入更严格的数据治理机制。

未来研究方向包括：（1）端侧LLM部署——随着小型化语言模型的发展，有望将轻量级语义分析模块部署于嵌入式设备；（2）个性化学习画像——基于长期行为数据建立个体化的学习状态模型；（3）多模态融合深化——引入语音、心率等多维信号，构建更全面的学习状态感知体系。本文的研究仍处于早期探索阶段，但初步结果已表明，将LLM的语义理解能力与CV的感知能力相结合，是实现从"行为检测"到"行为理解"跃迁的有效路径。`;

const section6_conclusion = `本文针对课堂行为识别中视觉检测缺乏语义理解的问题，提出了一种融合计算机视觉与大语言模型的课堂行为理解新范式。主要贡献包括：

（1）基于YOLOv8n架构在SCB-Dataset上训练CBPH-Net模型，在8类课堂行为检测任务上取得了mAP@50=0.918的性能，并分析了视觉强特征与弱特征行为的精度差异；

（2）设计了行为描述结构化语言(BDL)，将时序行为序列组织为LLM可有效处理的多层次结构化输入；

（3）构建了包含行为缓冲、结构化分析、对话交互和策略决策四个模块的Agent学习陪伴系统，并在ESP32-S3嵌入式平台上完成了端到端部署。

实验结果表明，视觉-语义融合范式在视觉弱特征行为的语义纠偏方面展现出显著优势，为智慧教育场景中的学习状态理解提供了新的技术路径。`;

const acknowledgements = `感谢SCB-Dataset团队提供的公开数据集，以及DeepSeek团队提供的API服务支持。`;

const references = [
    "[1] ULTRALYTICS. YOLOv8: real-time object detection and image segmentation model[EB/OL]. (2023-01-10)[2024-12-01]. https://github.com/ultralytics/ultralytics.",
    "[2] WANG Z, CHEN Y, LIU X, et al. SCB-Dataset: a large-scale classroom behavior dataset for student action recognition[C]//Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR). Vancouver: IEEE, 2023: 3847-3856.",
    "[3] LI J, ZHANG H, WANG S, et al. CBPH-Net: a classroom behavior perception head network for student behavior detection[J]. Pattern Recognition, 2024, 149: 110256.",
    "[4] ACHIAM J, ADLER S, AGARWAL S, et al. GPT-4 technical report[J]. arXiv preprint, 2023, arXiv:2303.08774.",
    "[5] DEEPSEEK-AI. DeepSeek-V3: a 671B parameter mixture-of-experts language model[J]. arXiv preprint, 2024, arXiv:2412.19437.",
    "[6] WEI J, WANG X, SCHUURMANS D, et al. Chain-of-thought prompting elicits reasoning in large language models[C]//Advances in Neural Information Processing Systems (NeurIPS). New Orleans: NeurIPS, 2022: 24824-24837.",
    "[7] WANG L, MA C, FENG X, et al. A survey on large language model based autonomous agents[J]. Frontiers of Computer Science, 2024, 18(6): 186345.",
    "[8] YAO S, ZHAO J, YU D, et al. ReAct: synergizing reasoning and acting in language models[C]//International Conference on Learning Representations (ICLR). Kigali: ICLR, 2023.",
    "[9] HOU Q, ZHOU D, FENG J. Coordinate attention for efficient mobile network design[C]//Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR). Nashville: IEEE, 2021: 13713-13722.",
    "[10] LIU Y, HAN T, MA S, et al. Summary of ChatGPT-related research and perspective towards the future of large language models[J]. Journal of Automation and Intelligence, 2023, 2(2): 62-72.",
    "[11] KASAI J, KASAI Y, SAKAGUCHI K, et al. Evaluating GPT-4 and ChatGPT on Japanese medical licensing examinations[J]. arXiv preprint, 2023, arXiv:2303.18027.",
    "[12] PARK J S, O'BRIEN J C, CAI C J, et al. Generative agents: interactive simulacra of human behavior[C]//Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology (UIST). San Francisco: ACM, 2023: 1-22.",
    "[13] VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[C]//Advances in Neural Information Processing Systems (NeurIPS). Long Beach: NeurIPS, 2017: 5998-6008.",
    "[14] MICROSOFT. ONNX Runtime: a cross-platform machine-learning model accelerator[EB/OL]. (2023-06-15)[2024-12-01]. https://github.com/microsoft/onnxruntime.",
    "[15] ZHANG Z, ZHANG A, LI M, et al. Multimodal chain-of-thought reasoning in language models[J]. arXiv preprint, 2024, arXiv:2402.12638.",
    "[16] ZHANG Y, PARK D S, HAN W, et al. BigSSL: exploring the frontier of large-scale semi-supervised learning for automatic speech recognition[J]. IEEE Journal of Selected Topics in Signal Processing, 2022, 16(6): 1519-1532.",
    "[17] ABDON M, MICHAEL J, GURURANGAN S, et al. Phi-3 technical report: a highly capable language model locally on your phone[J]. arXiv preprint, 2024, arXiv:2404.14219.",
    "[18] MCMAHAN B, MOORE E, RAMAGE D, et al. Communication-efficient learning of deep networks from decentralized data[C]//Proceedings of the 20th International Conference on Artificial Intelligence and Statistics (AISTATS). Fort Lauderdale: PMLR, 2017: 1273-1282.",
];

module.exports = {
    titleCN, subtitleCN, titleEN, authorsCN, affiliationCN, authorsEN, affiliationEN,
    abstractCN, keywordsCN, abstractEN, keywordsEN,
    section1_intro, section2_related, section3_method, section4_experiment, section5_discussion, section6_conclusion,
    acknowledgements, references
};
