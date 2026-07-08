import matplotlib.pyplot as plt

# 解决中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Zen Hei']
plt.rcParams['axes.unicode_minus'] = False

# 数据准备
labels = [
    '低身体幸福感',
    '低心理幸福感',
    '高缺乏工作活力',
    '高质疑工作价值',
    '高怀疑工作能力'
]
percentages = [16.42, 8.90, 7.41, 4.81, 0.74]
colors = ['#3377cc', '#5599dd', '#66aadd', '#77bbee', '#99ccff']

# 控制柱子宽度和间距
bar_width = 0.4
spacing = 0.6
x = [i * (bar_width + spacing) for i in range(len(labels))]

# 创建画布（透明背景）
plt.figure(figsize=(12, 7), dpi=150, facecolor='none')
ax = plt.gca()
ax.set_facecolor('none')

# 绘制柱状图
bars = plt.bar(x, percentages, width=bar_width, color=colors)

# ---------------------- 重点修改：数据标签字体调大 ----------------------
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height + 0.3,
        f'{height}%',
        ha='center', va='bottom',
        fontsize=12,  # 原先是10，这里调大了
        fontweight='bold'  # 可选：加粗，更醒目
    )

# 设置坐标轴与标题
plt.xticks(x, labels, rotation=20, ha='right', fontsize=11)  # X轴标签也稍微调大
plt.ylim(0, 20)
plt.yticks([0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20], fontsize=10)
plt.ylabel('占比 (%)', fontsize=12)  # Y轴标签也调大
plt.title('石化行业人员心理健康与安全风险现状', fontsize=15, pad=20)

# 美化
ax.yaxis.grid(True, linestyle='--', alpha=0.6)
ax.set_axisbelow(True)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()

# 导出PNG（透明背景）
plt.savefig(
    "石化行业心理健康柱状图.png",
    dpi=150,
    transparent=True,
    bbox_inches='tight'
)

plt.show()