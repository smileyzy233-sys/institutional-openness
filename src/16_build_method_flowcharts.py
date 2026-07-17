from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

import config


FIGURE_DIR = config.PROJECT_ROOT / "docs" / "figures"

FONT_REGULAR = FontProperties(fname="C:/Windows/Fonts/simsun.ttc")
FONT_BOLD = FontProperties(fname="C:/Windows/Fonts/simhei.ttf")

mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42
mpl.rcParams["svg.fonttype"] = "none"
mpl.rcParams["axes.unicode_minus"] = False


COLORS = {
    "ink": "#222222",
    "muted": "#6b6b6b",
    "line": "#383838",
    "rule": "#c7c7c7",
    "box": "#ffffff",
    "soft": "#f7f7f7",
    "arbitration": "#f1f1f1",
    "final": "#fbfbfb",
}


def setup_axes() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(7.45, 5.15), dpi=450)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax


def add_title(ax: plt.Axes, panel: str, title: str, subtitle: str) -> None:
    ax.text(
        0.035,
        0.958,
        f"{panel}  {title}",
        ha="left",
        va="top",
        fontsize=8.9,
        fontproperties=FONT_BOLD,
        color=COLORS["ink"],
    )
    ax.text(
        0.035,
        0.918,
        subtitle,
        ha="left",
        va="top",
        fontsize=6.2,
        fontproperties=FONT_REGULAR,
        color=COLORS["muted"],
    )
    ax.plot([0.035, 0.965], [0.890, 0.890], color=COLORS["rule"], lw=0.55)


def add_column_header(ax: plt.Axes, x0: float, x1: float, label: str) -> None:
    ax.text(
        (x0 + x1) / 2,
        0.858,
        label,
        ha="center",
        va="center",
        fontsize=7.0,
        fontproperties=FONT_BOLD,
        color=COLORS["ink"],
    )
    ax.plot([x0, x1], [0.840, 0.840], color=COLORS["rule"], lw=0.5)


def add_footer(ax: plt.Axes, text: str) -> None:
    ax.plot([0.035, 0.965], [0.068, 0.068], color=COLORS["rule"], lw=0.45)
    ax.text(
        0.035,
        0.045,
        text,
        ha="left",
        va="top",
        fontsize=5.9,
        fontproperties=FONT_REGULAR,
        color=COLORS["muted"],
    )


def add_box(
    ax: plt.Axes,
    key: str,
    boxes: dict[str, tuple[float, float, float, float]],
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    *,
    fill: str = "box",
    lw: float = 0.72,
    fontsize: float = 6.8,
    bold: bool = False,
) -> None:
    boxes[key] = (x, y, w, h)
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.004,rounding_size=0.010",
            linewidth=lw,
            edgecolor=COLORS["line"],
            facecolor=COLORS[fill],
            zorder=3,
        )
    )
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontproperties=FONT_BOLD if bold else FONT_REGULAR,
        color=COLORS["ink"],
        linespacing=1.25,
        zorder=4,
    )


def edge(box: tuple[float, float, float, float], side: str) -> tuple[float, float]:
    x, y, w, h = box
    if side == "left":
        return x, y + h / 2
    if side == "right":
        return x + w, y + h / 2
    if side == "top":
        return x + w / 2, y + h
    if side == "bottom":
        return x + w / 2, y
    raise ValueError(side)


def arrow_path(
    ax: plt.Axes,
    points: list[tuple[float, float]],
    *,
    lw: float = 0.62,
    ls: str = "-",
) -> None:
    if len(points) < 2:
        return
    xs = [p[0] for p in points[:-1]]
    ys = [p[1] for p in points[:-1]]
    if len(points) > 2:
        ax.plot(xs, ys, color=COLORS["line"], lw=lw, ls=ls, zorder=1.5)
    ax.annotate(
        "",
        xy=points[-1],
        xytext=points[-2],
        arrowprops={
            "arrowstyle": "-|>",
            "color": COLORS["line"],
            "lw": lw,
            "linestyle": ls,
            "mutation_scale": 6.5,
            "shrinkA": 0,
            "shrinkB": 0,
        },
        zorder=1.5,
    )


def connect(
    ax: plt.Axes,
    boxes: dict[str, tuple[float, float, float, float]],
    start_key: str,
    start_side: str,
    end_key: str,
    end_side: str,
    *,
    via: list[tuple[float, float]] | None = None,
    lw: float = 0.62,
    ls: str = "-",
) -> None:
    arrow_path(
        ax,
        [edge(boxes[start_key], start_side), *(via or []), edge(boxes[end_key], end_side)],
        lw=lw,
        ls=ls,
    )


def add_label(ax: plt.Axes, x: float, y: float, text: str, *, ha: str = "center") -> None:
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va="center",
        fontsize=5.7,
        fontproperties=FONT_REGULAR,
        color=COLORS["muted"],
        zorder=5,
    )


def draw_common_structure(
    ax: plt.Axes,
    boxes: dict[str, tuple[float, float, float, float]],
    *,
    panel: str,
    title: str,
    subtitle: str,
) -> None:
    add_title(ax, panel, title, subtitle)
    add_column_header(ax, 0.045, 0.185, "数据准备")
    add_column_header(ax, 0.235, 0.510, "Stage 1：识别制度型开放")
    add_column_header(ax, 0.560, 0.805, "Stage 2：识别贸易/投资影响")
    add_column_header(ax, 0.845, 0.960, "输出")

    for x in [0.210, 0.535, 0.825]:
        ax.plot([x, x], [0.105, 0.835], color=COLORS["rule"], lw=0.42)

    add_box(ax, "raw", boxes, 0.055, 0.700, 0.115, 0.062, "DTA 2.0\n条款原始表", bold=True)
    add_box(
        ax,
        "prep",
        boxes,
        0.055,
        0.565,
        0.115,
        0.070,
        "条款清洗\nprovision_id 构造\n协定-条款矩阵",
        fontsize=6.1,
    )

    add_box(
        ax,
        "s1a",
        boxes,
        0.245,
        0.720,
        0.118,
        0.072,
        "1A 双模型判定\n是否制度型开放\nn=1071",
        fill="soft",
        bold=True,
        fontsize=6.2,
    )
    add_box(
        ax,
        "s1a_review",
        boxes,
        0.402,
        0.720,
        0.094,
        0.072,
        "比较与仲裁\n冲突=103",
        fill="arbitration",
        fontsize=6.2,
    )
    add_box(
        ax,
        "institutional",
        boxes,
        0.402,
        0.585,
        0.094,
        0.065,
        "制度型开放\n条款\nn=764",
        fill="final",
        bold=True,
        fontsize=6.3,
    )
    add_box(
        ax,
        "s1b",
        boxes,
        0.245,
        0.455,
        0.118,
        0.080,
        "1B 双模型判定\n制度维度\nrules 等四类",
        fill="soft",
        bold=True,
        fontsize=6.0,
    )
    add_box(
        ax,
        "s1b_review",
        boxes,
        0.402,
        0.455,
        0.094,
        0.080,
        "比较与仲裁\n冲突=109\n形成最终维度",
        fill="arbitration",
        fontsize=5.9,
    )
    add_box(
        ax,
        "s1_final",
        boxes,
        0.326,
        0.305,
        0.110,
        0.066,
        "Stage 1 输出\n制度型条款 + 维度",
        fill="final",
        bold=True,
        fontsize=6.1,
    )

    add_box(
        ax,
        "w_provision",
        boxes,
        0.850,
        0.625,
        0.103,
        0.065,
        "条款层面\n贸易/投资权重",
        fill="final",
        bold=True,
        fontsize=6.2,
    )
    add_box(
        ax,
        "w_agreement",
        boxes,
        0.850,
        0.455,
        0.103,
        0.068,
        "协定层面指数\nagreement-\nlevel",
        fill="final",
        fontsize=5.6,
    )
    add_box(
        ax,
        "w_panel",
        boxes,
        0.850,
        0.285,
        0.103,
        0.074,
        "国家对-年份面板\npair-year\nindices / dummy",
        fill="final",
        fontsize=5.65,
    )

    connect(ax, boxes, "raw", "bottom", "prep", "top")
    connect(ax, boxes, "prep", "right", "s1a", "left", via=[(0.205, 0.600), (0.205, 0.756)])
    connect(ax, boxes, "s1a", "right", "s1a_review", "left")
    connect(ax, boxes, "s1a_review", "bottom", "institutional", "top")
    connect(
        ax,
        boxes,
        "institutional",
        "left",
        "s1b",
        "top",
        via=[(0.285, 0.618), (0.285, 0.535)],
    )
    connect(ax, boxes, "s1b", "right", "s1b_review", "left")
    connect(ax, boxes, "s1b_review", "bottom", "s1_final", "top", via=[(0.449, 0.400), (0.381, 0.400)])
    connect(ax, boxes, "w_provision", "bottom", "w_agreement", "top")
    connect(ax, boxes, "w_agreement", "bottom", "w_panel", "top")


def draw_dual_model() -> None:
    fig, ax = setup_axes()
    boxes: dict[str, tuple[float, float, float, float]] = {}
    draw_common_structure(
        ax,
        boxes,
        panel="图1",
        title="DTA 条款编码框架：Stage 2 双模型仲裁方案",
        subtitle="Stage 1 双模型识别制度型开放及制度维度；Stage 2 双模型独立编码，并对分歧条款进行盲审/人工仲裁。",
    )

    add_box(ax, "s2_sample", boxes, 0.575, 0.700, 0.106, 0.062, "Stage 2 样本\nn=764", fill="final", bold=True)
    add_box(
        ax,
        "model_a",
        boxes,
        0.575,
        0.545,
        0.106,
        0.088,
        "模型 A\n独立编码\nmp/tr\nboth/none",
        fill="soft",
        fontsize=5.75,
        bold=True,
    )
    add_box(
        ax,
        "model_b",
        boxes,
        0.575,
        0.395,
        0.106,
        0.088,
        "模型 B\n独立编码\nmp/tr\nboth/none",
        fill="soft",
        fontsize=5.75,
        bold=True,
    )
    add_box(
        ax,
        "s2_compare",
        boxes,
        0.715,
        0.485,
        0.085,
        0.080,
        "一致性比较\n影响类型\n与权重核验",
        fill="box",
        bold=True,
        fontsize=5.8,
    )
    add_box(
        ax,
        "s2_consensus",
        boxes,
        0.715,
        0.635,
        0.085,
        0.072,
        "一致样本\n直接接受\nn=682",
        fill="final",
        bold=True,
        fontsize=5.9,
    )
    add_box(
        ax,
        "s2_conflict",
        boxes,
        0.715,
        0.300,
        0.085,
        0.080,
        "冲突样本\n盲审/人工仲裁\nn=82",
        fill="arbitration",
        bold=True,
        fontsize=5.8,
    )
    add_box(
        ax,
        "s2_trace",
        boxes,
        0.575,
        0.245,
        0.106,
        0.056,
        "可追溯记录\nprompt / hash\nrun",
        fontsize=5.55,
    )

    connect(
        ax,
        boxes,
        "s1_final",
        "right",
        "s2_sample",
        "left",
        via=[(0.540, 0.338), (0.540, 0.731)],
    )
    connect(ax, boxes, "s2_sample", "bottom", "model_a", "top")
    connect(
        ax,
        boxes,
        "s2_sample",
        "bottom",
        "model_b",
        "left",
        via=[(0.548, 0.700), (0.548, 0.439)],
    )
    connect(ax, boxes, "model_a", "right", "s2_compare", "left", via=[(0.700, 0.590), (0.700, 0.535)])
    connect(ax, boxes, "model_b", "right", "s2_compare", "left", via=[(0.700, 0.450), (0.700, 0.515)])
    connect(ax, boxes, "s2_compare", "top", "s2_consensus", "bottom")
    connect(
        ax,
        boxes,
        "s2_compare",
        "bottom",
        "s2_conflict",
        "top",
        via=[(0.758, 0.440), (0.758, 0.380)],
    )
    connect(
        ax,
        boxes,
        "s2_consensus",
        "right",
        "w_provision",
        "left",
        via=[(0.825, 0.671)],
    )
    connect(
        ax,
        boxes,
        "s2_conflict",
        "right",
        "w_provision",
        "left",
        via=[(0.825, 0.340), (0.825, 0.658)],
    )
    connect(
        ax,
        boxes,
        "s2_trace",
        "right",
        "s2_conflict",
        "bottom",
        via=[(0.700, 0.273), (0.758, 0.273)],
        ls="--",
        lw=0.50,
    )

    add_footer(
        ax,
        "注：mp / tr / both / none 为 Stage 2 影响类型标签，并按统一规则转换为贸易/投资权重；数字为当前复核版本统计。",
    )
    save_figure(fig, "method_flow_stage2_dual_model")


def draw_single_model() -> None:
    fig, ax = setup_axes()
    boxes: dict[str, tuple[float, float, float, float]] = {}
    draw_common_structure(
        ax,
        boxes,
        panel="图2",
        title="DTA 条款编码框架：Stage 2 单模型方案",
        subtitle="Stage 1 保持双模型识别与仲裁；Stage 2 经模型表现评估和人工复核后，采用模型 B 进行单模型编码。",
    )

    add_box(ax, "s2_sample", boxes, 0.575, 0.700, 0.106, 0.062, "Stage 2 样本\nn=764", fill="final", bold=True)
    add_box(
        ax,
        "model_b_single",
        boxes,
        0.575,
        0.555,
        0.106,
        0.074,
        "模型 B\nQwen3.5-9B\n单模型编码",
        fill="soft",
        bold=True,
        fontsize=5.85,
    )
    add_box(
        ax,
        "s2_type",
        boxes,
        0.575,
        0.415,
        0.106,
        0.088,
        "输出影响类型\nmp/tr\nboth/none\n及权重",
        fontsize=5.65,
    )
    add_box(
        ax,
        "s2_validate",
        boxes,
        0.715,
        0.540,
        0.085,
        0.083,
        "规则校验\n标签集合\n权重映射\n缺失/异常",
        fill="box",
        bold=True,
        fontsize=5.55,
    )
    add_box(
        ax,
        "s2_review",
        boxes,
        0.715,
        0.350,
        0.085,
        0.088,
        "人工/专家复核\n重点边界领域\n与抽样核查",
        fill="arbitration",
        bold=True,
        fontsize=5.65,
    )
    add_box(
        ax,
        "s2_trace",
        boxes,
        0.575,
        0.245,
        0.106,
        0.056,
        "可追溯记录\nmodel\nprompt / hash",
        fontsize=5.55,
    )

    connect(
        ax,
        boxes,
        "s1_final",
        "right",
        "s2_sample",
        "left",
        via=[(0.540, 0.338), (0.540, 0.731)],
    )
    connect(ax, boxes, "s2_sample", "bottom", "model_b_single", "top")
    connect(ax, boxes, "model_b_single", "bottom", "s2_type", "top")
    connect(
        ax,
        boxes,
        "s2_type",
        "right",
        "s2_validate",
        "left",
        via=[(0.700, 0.454), (0.700, 0.582)],
    )
    connect(ax, boxes, "s2_validate", "bottom", "s2_review", "top")
    connect(
        ax,
        boxes,
        "s2_review",
        "right",
        "w_provision",
        "left",
        via=[(0.825, 0.394), (0.825, 0.658)],
    )
    connect(
        ax,
        boxes,
        "s2_trace",
        "right",
        "s2_review",
        "bottom",
        via=[(0.700, 0.273), (0.758, 0.273)],
        ls="--",
        lw=0.50,
    )

    add_footer(
        ax,
        "注：单模型方案为 Stage 2 简化编码的替代路径；Stage 1 的双模型识别和仲裁流程保持不变。",
    )
    save_figure(fig, "method_flow_stage2_single_model_b")


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in [
        ("png", {"dpi": 450}),
        ("pdf", {}),
        ("svg", {}),
    ]:
        fig.savefig(FIGURE_DIR / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def run() -> None:
    draw_dual_model()
    draw_single_model()
    print(f"Wrote journal-style method flowcharts to {FIGURE_DIR}")


if __name__ == "__main__":
    run()
