from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV_DIR = PROJECT_ROOT / "Evaluation" / "results" / "batch1"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Figures" / "output" / "batch1"
# 与评估脚本保持一致：画框架图时去掉 docling。
# 另外 llamaindex 的 docling / unstructured、haystack 的 unstructured
# 已在评估阶段从聚合结果中排除，因此这里直接沿用筛过的 4 个 framework 列。
CSV_FRAMEWORK_KEYS = ["haystack", "langchain", "llamaindex", "llmsherpa"]
FRAMEWORKS = ["Haystack", "LangChain", "LlamaIndex", "LLMSherpa"]
SOFT_REDS_CMAP = LinearSegmentedColormap.from_list(
    "soft_reference_reds",
    ["#fff5f0", "#fdd0c2", "#fc9272", "#ef3b2c", "#99000d"],
)
CSV_SPECS = [
    ("framework_category_success_rate.csv", "Attack Categories - Injection Parsing Success Rate", "attack_category", "framework_category_success_rate.png"),
    (
        "framework_category_recovery_completeness.csv",
        "Attack Categories - Injection Recovery Completeness",
        "attack_category",
        "framework_category_recovery_completeness.png",
    ),
    (
        "framework_subcategory_success_rate.csv",
        "Attack Subcategories - Injection Parsing Success Rate",
        "attack_subcategory",
        "framework_subcategory_success_rate.png",
    ),
    (
        "framework_subcategory_recovery_completeness.csv",
        "Attack Subcategories - Injection Recovery Completeness",
        "attack_subcategory",
        "framework_subcategory_recovery_completeness.png",
    ),
]
ATTACK_SUBCATEGORY_LABELS = {
    "pdf_mirage": "PDF Mirage",
}
CHINESE_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "SimHei",
    "SimSun",
    "NSimSun",
    "KaiTi",
    "FangSong",
    "PingFang SC",
    "Heiti SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
]


def configure_matplotlib_fonts() -> str | None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in CHINESE_FONT_CANDIDATES:
        if font_name in available_fonts:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return font_name

    plt.rcParams["axes.unicode_minus"] = False
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 Evaluation 生成的 CSV 绘制五框架热图")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="存放 framework_*.csv 的目录")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="热图输出目录")
    parser.add_argument("--dpi", type=int, default=240, help="图片 DPI")
    return parser.parse_args()


def load_heatmap_csv(csv_path: Path, row_field: str) -> tuple[list[str], list[list[float]], str]:
    row_labels: list[str] = []
    values: list[list[float]] = []
    metric_label = ""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            row_label = row[row_field]
            if row_field == "attack_subcategory":
                row_label = ATTACK_SUBCATEGORY_LABELS.get(row_label, row_label)
            row_labels.append(row_label)
            if not metric_label:
                metric_label = row.get("metric", "")

            current_row: list[float] = []
            for framework in CSV_FRAMEWORK_KEYS:
                raw_value = (row.get(framework) or "").strip()
                current_row.append(float(raw_value) if raw_value else math.nan)
            values.append(current_row)

    return row_labels, values, metric_label


def choose_figure_size(row_count: int) -> tuple[float, float]:
    width = 10.5
    height = max(4.8, row_count * 0.72 + 1.8)
    return width, height


def translate_metric_label(metric_label: str) -> str:
    metric_map = {
        "隐式注入解析成功率": "Injection Parsing Success Rate",
        "隐式注入内容回复完整度": "Injection Recovery Completeness",
    }
    return metric_map.get(metric_label, metric_label)


def draw_heatmap(
    row_labels: list[str],
    values: list[list[float]],
    title: str,
    metric_label: str,
    output_path: Path,
    dpi: int,
) -> None:
    fig_width, fig_height = choose_figure_size(len(row_labels))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    cmap = SOFT_REDS_CMAP.copy()
    cmap.set_bad(color="#d9d9d9")

    image = ax.imshow(values, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(FRAMEWORKS)))
    ax.set_xticklabels(FRAMEWORKS, rotation=20, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_title(title, fontsize=14, pad=14)

    ax.set_xticks([x - 0.5 for x in range(1, len(FRAMEWORKS))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(row_labels))], minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)

    for row_idx, row_values in enumerate(values):
        for col_idx, value in enumerate(row_values):
            label = "N/A" if math.isnan(value) else f"{value:.3f}"
            text_color = "#1f1f1f" if math.isnan(value) or value < 0.6 else "white"
            ax.text(col_idx, row_idx, label, ha="center", va="center", fontsize=10, color=text_color)

    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label(translate_metric_label(metric_label) or "Metric", rotation=90)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def save_overview_figure(output_dir: Path, created_files: list[Path], dpi: int) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    for ax, image_path in zip(axes, created_files):
        image = plt.imread(image_path)
        ax.imshow(image)
        ax.set_title(image_path.stem.replace("_", " "), fontsize=11)
        ax.axis("off")

    for ax in axes[len(created_files):]:
        ax.axis("off")

    fig.tight_layout()
    fig.savefig(output_dir / "framework_heatmaps_overview.png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configured_font = configure_matplotlib_fonts()
    if configured_font:
        print(f"已启用中文字体: {configured_font}")
    else:
        print("未检测到可用中文字体，图中中文可能仍然显示异常")
    created_files: list[Path] = []

    for csv_name, title, row_field, output_name in CSV_SPECS:
        csv_path = args.csv_dir / csv_name
        if not csv_path.exists():
            print(f"跳过，未找到 CSV: {csv_path}")
            continue

        row_labels, values, metric_label = load_heatmap_csv(csv_path, row_field)
        if not row_labels:
            print(f"跳过，CSV 为空: {csv_path}")
            continue

        output_path = args.output_dir / output_name
        draw_heatmap(row_labels, values, title, metric_label, output_path, args.dpi)
        created_files.append(output_path)
        print(f"已生成热图: {output_path}")

    if created_files:
        save_overview_figure(args.output_dir, created_files, args.dpi)
        print(f"已生成总览图: {args.output_dir / 'framework_heatmaps_overview.png'}")
    else:
        print("未生成任何热图，请检查 CSV 目录")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

