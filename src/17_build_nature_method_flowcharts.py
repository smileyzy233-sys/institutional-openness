from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, Circle
from PIL import Image, ImageStat

import config


OUT_DIR = config.PROJECT_ROOT / "docs" / "figures"
QA_DIR = OUT_DIR / "qa"

FONT_CN = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
FONT_CN_BOLD = FontProperties(fname="C:/Windows/Fonts/msyhbd.ttc")

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "figure.facecolor": "white",
    }
)


PALETTE = {
    "ink": "#202124",
    "muted": "#6b7280",
    "line": "#31363b",
    "hair": "#d7dce0",
    "panel": "#ffffff",
    "neutral": "#f6f7f8",
    "stage1": "#eef3f7",
    "stage2": "#edf4f2",
    "review": "#f7f2e8",
    "output": "#f5f5f5",
    "accent": "#0f4d92",
}


@dataclass
class Node:
    key: str
    x: float
    y: float
    w: float
    h: float
    label: str
    fill: str = "panel"
    lw: float = 0.46
    bold: bool = False
    fs: float = 6.2
    linespacing: float = 1.05

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def edge(self, side: str) -> tuple[float, float]:
        if side == "left":
            return self.x, self.y + self.h / 2
        if side == "right":
            return self.x + self.w, self.y + self.h / 2
        if side == "top":
            return self.x + self.w / 2, self.y + self.h
        if side == "bottom":
            return self.x + self.w / 2, self.y
        raise ValueError(side)


def setup_fig() -> tuple[plt.Figure, plt.Axes]:
    # 183 mm Nature double-column width, moderate height.
    fig, ax = plt.subplots(figsize=(7.20, 4.15), dpi=600)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def t(
    ax: plt.Axes,
    x: float,
    y: float,
    s: str,
    *,
    fs: float = 6.2,
    color: str = "ink",
    bold: bool = False,
    ha: str = "center",
    va: str = "center",
    linespacing: float = 1.18,
) -> None:
    ax.text(
        x,
        y,
        s,
        ha=ha,
        va=va,
        fontsize=fs,
        fontproperties=FONT_CN_BOLD if bold else FONT_CN,
        color=PALETTE[color],
        linespacing=linespacing,
        zorder=5,
    )


def draw_node(ax: plt.Axes, node: Node, nodes: dict[str, Node]) -> None:
    nodes[node.key] = node
    ax.add_patch(
        FancyBboxPatch(
            (node.x, node.y),
            node.w,
            node.h,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            linewidth=node.lw,
            edgecolor=PALETTE["line"],
            facecolor=PALETTE[node.fill],
            zorder=3,
        )
    )
    # Keep node typography lighter than panel titles; hierarchy comes mostly from layout and fill.
    t(ax, *node.center, node.label, fs=node.fs, bold=False, linespacing=node.linespacing)


def draw_step(
    ax: plt.Axes,
    n: int,
    x: float,
    y: float,
    label: str,
    *,
    fill: str,
    fs: float = 6.0,
    dx: float = 0.022,
) -> None:
    ax.add_patch(Circle((x, y), 0.014, facecolor=fill, edgecolor=PALETTE["line"], lw=0.55, zorder=4))
    t(ax, x, y - 0.001, str(n), fs=5.5, bold=True)
    t(ax, x + dx, y, label, fs=fs, ha="left", va="center")


def arrow(
    ax: plt.Axes,
    points: list[tuple[float, float]],
    *,
    lw: float = 0.46,
    color: str = "line",
    dashed: bool = False,
) -> None:
    if len(points) < 2:
        return
    if len(points) > 2:
        xs, ys = zip(*points[:-1])
        ax.plot(xs, ys, color=PALETTE[color], lw=lw, ls="--" if dashed else "-", zorder=1)
    ax.annotate(
        "",
        xy=points[-1],
        xytext=points[-2],
        arrowprops={
            "arrowstyle": "-|>",
            "color": PALETTE[color],
            "lw": lw,
            "linestyle": "--" if dashed else "-",
            "mutation_scale": 5.2,
            "shrinkA": 0,
            "shrinkB": 2.5,
        },
        zorder=1,
    )


def connect(
    ax: plt.Axes,
    nodes: dict[str, Node],
    a: str,
    a_side: str,
    b: str,
    b_side: str,
    via: list[tuple[float, float]] | None = None,
    *,
    dashed: bool = False,
    lw: float = 0.46,
) -> None:
    arrow(
        ax,
        [nodes[a].edge(a_side), *(via or []), nodes[b].edge(b_side)],
        dashed=dashed,
        lw=lw,
    )


def panel_title(ax: plt.Axes, label: str, title: str, subtitle: str) -> None:
    t(ax, 0.045, 0.948, label, fs=6.8, bold=True, ha="left")
    t(ax, 0.088, 0.948, title, fs=7.25, bold=True, ha="left")
    t(ax, 0.088, 0.912, subtitle, fs=5.25, color="muted", ha="left")
    ax.plot([0.045, 0.955], [0.888, 0.888], color=PALETTE["hair"], lw=0.42)


def column_headers(ax: plt.Axes) -> None:
    labels = [
        ("Data", 0.080, 0.190),
        ("Stage 1", 0.245, 0.500),
        ("Stage 2", 0.555, 0.790),
        ("Output", 0.840, 0.945),
    ]
    for label, x0, x1 in labels:
        t(ax, (x0 + x1) / 2, 0.850, label, fs=5.4, color="muted", bold=True)
        ax.plot([x0, x1], [0.833, 0.833], color=PALETTE["hair"], lw=0.38)
    for x in [0.215, 0.528, 0.815]:
        ax.plot([x, x], [0.120, 0.820], color=PALETTE["hair"], lw=0.34)


def draw_common(ax: plt.Axes, nodes: dict[str, Node]) -> None:
    column_headers(ax)
    draw_node(ax, Node("raw", 0.066, 0.665, 0.116, 0.068, "DTA 2.0\n条款原始表", "neutral", bold=True, fs=6.1), nodes)
    draw_node(
        ax,
        Node("prep", 0.066, 0.520, 0.116, 0.078, "条款清洗\nID 构造\n协定-条款矩阵", "panel", fs=5.6),
        nodes,
    )

    draw_node(
        ax,
        Node("s1a", 0.248, 0.700, 0.128, 0.084, "1A 双模型\n开放识别\nn=1071", "stage1", bold=True, fs=5.55),
        nodes,
    )
    draw_node(
        ax,
        Node("s1a_review", 0.414, 0.705, 0.086, 0.074, "比较/仲裁\n冲突=103", "review", fs=5.6),
        nodes,
    )
    draw_node(
        ax,
        Node("inst", 0.414, 0.575, 0.086, 0.068, "制度型开放\n条款数=764", "stage1", bold=True, fs=5.55),
        nodes,
    )
    draw_node(
        ax,
        Node("s1b", 0.248, 0.438, 0.128, 0.086, "1B 双模型\n维度识别\n四类维度", "stage1", bold=True, fs=5.55),
        nodes,
    )
    draw_node(
        ax,
        Node("s1b_review", 0.414, 0.440, 0.086, 0.082, "比较/仲裁\n冲突=109\n最终维度", "review", fs=5.4),
        nodes,
    )
    draw_node(
        ax,
        Node("s1_final", 0.326, 0.285, 0.116, 0.070, "Stage 1 输出\n条款 + 维度", "neutral", bold=True, fs=5.9),
        nodes,
    )

    draw_node(
        ax,
        Node("out1", 0.842, 0.605, 0.108, 0.070, "条款层面\n贸易/投资权重", "output", bold=True, fs=5.8),
        nodes,
    )
    draw_node(
        ax,
        Node("out2", 0.842, 0.435, 0.108, 0.070, "协定层面\n指数", "output", fs=5.8),
        nodes,
    )
    draw_node(
        ax,
        Node("out3", 0.842, 0.260, 0.108, 0.080, "国家对-年份\n面板指标\n及 dummy", "output", fs=5.5),
        nodes,
    )

    connect(ax, nodes, "raw", "bottom", "prep", "top")
    connect(ax, nodes, "prep", "right", "s1a", "left", via=[(0.208, 0.559), (0.208, 0.742)])
    connect(ax, nodes, "s1a", "right", "s1a_review", "left")
    connect(ax, nodes, "s1a_review", "bottom", "inst", "top")
    connect(ax, nodes, "inst", "left", "s1b", "top", via=[(0.290, 0.609), (0.290, 0.522)])
    connect(ax, nodes, "s1b", "right", "s1b_review", "left")
    connect(ax, nodes, "s1b_review", "bottom", "s1_final", "top", via=[(0.457, 0.390), (0.384, 0.390)])
    connect(ax, nodes, "out1", "bottom", "out2", "top")
    connect(ax, nodes, "out2", "bottom", "out3", "top")


def draw_dual() -> plt.Figure:
    fig, ax = setup_fig()
    nodes: dict[str, Node] = {}
    panel_title(
        ax,
        "a",
        "DTA 条款编码框架：Stage 2 双模型仲裁方案",
        "共同 Stage 1 样本构建后，Stage 2 由两个模型独立编码，并将分歧条款交由盲审/人工仲裁。",
    )
    draw_common(ax, nodes)

    draw_node(ax, Node("s2_sample", 0.575, 0.705, 0.108, 0.064, "Stage 2 样本\nn=764", "neutral", bold=True, fs=5.9), nodes)
    draw_node(ax, Node("model_a", 0.570, 0.555, 0.116, 0.080, "模型 A\n独立编码\nmp/tr/both/none", "stage2", bold=True, fs=5.4), nodes)
    draw_node(ax, Node("model_b", 0.570, 0.410, 0.116, 0.080, "模型 B\n独立编码\nmp/tr/both/none", "stage2", bold=True, fs=5.4), nodes)
    draw_node(ax, Node("compare", 0.720, 0.478, 0.078, 0.088, "一致性\n比较\n与权重核验", "panel", bold=True, fs=5.2), nodes)
    draw_node(ax, Node("consensus", 0.720, 0.640, 0.078, 0.076, "一致样本\n接受\nn=682", "stage2", bold=True, fs=5.4), nodes)
    draw_node(ax, Node("conflict", 0.720, 0.300, 0.078, 0.086, "冲突样本\n仲裁\nn=82", "review", bold=True, fs=5.4), nodes)
    draw_node(ax, Node("trace", 0.570, 0.218, 0.116, 0.070, "可追溯记录\nprompt / hash\nrun", "panel", fs=4.9), nodes)

    connect(ax, nodes, "s1_final", "right", "s2_sample", "left", via=[(0.535, 0.320), (0.535, 0.737)])
    connect(ax, nodes, "s2_sample", "bottom", "model_a", "top")
    connect(ax, nodes, "s2_sample", "bottom", "model_b", "left", via=[(0.548, 0.705), (0.548, 0.450)])
    connect(ax, nodes, "model_a", "right", "compare", "left", via=[(0.704, 0.595), (0.704, 0.530)])
    connect(ax, nodes, "model_b", "right", "compare", "left", via=[(0.704, 0.450), (0.704, 0.512)])
    connect(ax, nodes, "compare", "top", "consensus", "bottom")
    connect(ax, nodes, "compare", "bottom", "conflict", "top", via=[(0.759, 0.430), (0.759, 0.386)])
    connect(ax, nodes, "consensus", "right", "out1", "left", via=[(0.816, 0.678), (0.816, 0.640)])
    connect(ax, nodes, "conflict", "right", "out1", "left", via=[(0.816, 0.343), (0.816, 0.640)])
    connect(ax, nodes, "trace", "right", "conflict", "bottom", via=[(0.700, 0.253), (0.759, 0.253)], dashed=True, lw=0.55)

    draw_step(ax, 1, 0.060, 0.115, "标准化条款粒度", fill=PALETTE["neutral"])
    draw_step(ax, 2, 0.250, 0.115, "Stage 1 识别制度型开放", fill=PALETTE["stage1"])
    draw_step(ax, 3, 0.570, 0.115, "Stage 2 双模型交叉验证", fill=PALETTE["stage2"])
    draw_step(ax, 4, 0.815, 0.115, "权重与面板输出", fill=PALETTE["output"])

    footer(ax, "注：mp/tr/both/none 为 Stage 2 影响类型标签，并按统一规则转换为贸易/投资权重；数字为当前复核版本统计。")
    return fig


def draw_single() -> plt.Figure:
    fig, ax = setup_fig()
    nodes: dict[str, Node] = {}
    panel_title(
        ax,
        "b",
        "DTA 条款编码框架：Stage 2 单模型方案",
        "共同 Stage 1 样本构建后，Stage 2 经模型表现评估和人工复核，采用模型 B 进行单模型编码。",
    )
    draw_common(ax, nodes)

    draw_node(ax, Node("s2_sample", 0.575, 0.705, 0.108, 0.064, "Stage 2 样本\nn=764", "neutral", bold=True, fs=5.9), nodes)
    draw_node(ax, Node("model_b", 0.575, 0.555, 0.108, 0.082, "模型 B\nQwen3.5-9B\n单模型编码", "stage2", bold=True, fs=5.4), nodes)
    draw_node(ax, Node("types", 0.575, 0.405, 0.108, 0.088, "影响类型\nmp/tr/both/none\n及权重", "panel", fs=5.35), nodes)
    draw_node(ax, Node("validate", 0.720, 0.540, 0.078, 0.090, "规则校验\n标签集合\n权重映射", "panel", bold=True, fs=5.15), nodes)
    draw_node(ax, Node("review", 0.720, 0.330, 0.078, 0.094, "人工复核\n边界领域\n抽样核查", "review", bold=True, fs=5.15), nodes)
    draw_node(ax, Node("trace", 0.575, 0.218, 0.108, 0.070, "可追溯记录\nmodel / prompt\nhash", "panel", fs=4.9), nodes)

    connect(ax, nodes, "s1_final", "right", "s2_sample", "left", via=[(0.535, 0.320), (0.535, 0.737)])
    connect(ax, nodes, "s2_sample", "bottom", "model_b", "top")
    connect(ax, nodes, "model_b", "bottom", "types", "top")
    connect(ax, nodes, "types", "right", "validate", "left", via=[(0.704, 0.449), (0.704, 0.585)])
    connect(ax, nodes, "validate", "bottom", "review", "top")
    connect(ax, nodes, "review", "right", "out1", "left", via=[(0.816, 0.377), (0.816, 0.640)])
    connect(ax, nodes, "trace", "right", "review", "bottom", via=[(0.700, 0.253), (0.759, 0.253)], dashed=True, lw=0.55)

    draw_step(ax, 1, 0.060, 0.115, "标准化条款粒度", fill=PALETTE["neutral"])
    draw_step(ax, 2, 0.250, 0.115, "Stage 1 识别制度型开放", fill=PALETTE["stage1"])
    draw_step(ax, 3, 0.570, 0.115, "Stage 2 单模型编码", fill=PALETTE["stage2"])
    draw_step(ax, 4, 0.815, 0.115, "权重与面板输出", fill=PALETTE["output"])

    footer(ax, "注：单模型方案为 Stage 2 简化编码的替代路径；Stage 1 的双模型识别和仲裁流程保持不变。")
    return fig


def footer(ax: plt.Axes, text: str) -> None:
    ax.plot([0.045, 0.955], [0.083, 0.083], color=PALETTE["hair"], lw=0.38)
    t(ax, 0.045, 0.055, text, fs=5.2, color="muted", ha="left", va="top")


def save_pub(fig: plt.Figure, stem: str) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        OUT_DIR / f"{stem}.svg",
        OUT_DIR / f"{stem}.pdf",
        OUT_DIR / f"{stem}.png",
        OUT_DIR / f"{stem}.tiff",
    ]
    fig.savefig(outputs[0], bbox_inches="tight")
    fig.savefig(outputs[1], bbox_inches="tight")
    fig.savefig(outputs[2], dpi=600, bbox_inches="tight")
    fig.savefig(outputs[3], dpi=600, bbox_inches="tight")
    plt.close(fig)
    return outputs


def qa_image(path: Path) -> dict[str, object]:
    im = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(im)
    width, height = im.size
    px = im.load()
    step = max(1, min(width, height) // 700)
    sampled = 0
    nonwhite = 0
    for y in range(0, height, step):
        for x in range(0, width, step):
            sampled += 1
            r, g, b = px[x, y]
            if (255 - r) + (255 - g) + (255 - b) > 18:
                nonwhite += 1
    return {
        "file": path.name,
        "width_px": width,
        "height_px": height,
        "mean_rgb": [round(v, 2) for v in stat.mean],
        "nonwhite_sample_share": round(nonwhite / sampled, 5),
    }


def write_contract_and_qa(outputs: dict[str, list[Path]]) -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    qa_rows = []
    for paths in outputs.values():
        for path in paths:
            if path.suffix.lower() == ".png":
                qa_rows.append(qa_image(path))

    notes = [
        "# Nature-style DTA method flowcharts QA notes",
        "",
        "Core conclusion: 同一 Stage 1 样本构建下，Stage 2 可以呈现为双模型仲裁方案或单模型 B 方案，二者共享制度型开放识别、质量控制和可追溯输出逻辑。",
        "",
        "Evidence chain:",
        "- Data preparation standardizes the provision grain and agreement-provision matrix.",
        "- Stage 1 identifies institutional opening and institutional dimensions through dual-model coding plus arbitration.",
        "- Stage 2 diverges into either dual-model independent coding with conflict arbitration, or single-model B coding with rule validation and human spot review.",
        "- Final outputs aggregate provision-level trade/investment weights into agreement-level and country-pair-year measures.",
        "",
        "Archetype: schematic-led composite.",
        "",
        "Journal/export contract:",
        "- Backend: Python/matplotlib only.",
        "- Width: 7.20 in before tight bounding, suitable for a double-column manuscript figure.",
        "- Exports: editable SVG, editable-font PDF, 600 dpi PNG, 600 dpi TIFF.",
        "- Text: Microsoft YaHei for Chinese labels; SVG/PDF fonttype settings keep text editable when supported by the viewer.",
        "- Color: neutral greys with restrained blue-green method family and pale review accent; no rainbow palette.",
        "",
        "Visual QA:",
    ]
    for row in qa_rows:
        notes.append(
            f"- {row['file']}: {row['width_px']}x{row['height_px']} px, "
            f"non-white sample share={row['nonwhite_sample_share']}, mean RGB={row['mean_rgb']}."
        )
    notes.append("")
    notes.append("No existing method_flow_stage2_dual_model.pdf or method_flow_stage2_single_model.pdf files were overwritten; new files use the `_nature` suffix.")
    (QA_DIR / "method_flow_stage2_nature_qa.md").write_text("\n".join(notes) + "\n", encoding="utf-8")


def run() -> None:
    outputs = {
        "dual": save_pub(draw_dual(), "method_flow_stage2_dual_model_nature"),
        "single": save_pub(draw_single(), "method_flow_stage2_single_model_nature"),
    }
    write_contract_and_qa(outputs)
    print(f"Wrote Nature-style flowcharts to {OUT_DIR}")
    for paths in outputs.values():
        for p in paths:
            print(p)
    print(QA_DIR / "method_flow_stage2_nature_qa.md")


if __name__ == "__main__":
    run()
