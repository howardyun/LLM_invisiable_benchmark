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
# 与评估脚本保持一致：画 parser 图时去掉 docling 框架、langchain 的 OpenDataLoader 变体，
# 以及 llamaindex 的 docling / unstructured、haystack 的 unstructured。
EXCLUDED_PARSER_IDS = {
    "docling.docling",
    "docling.docling_force_ocr",
    "langchain.opendataloader",
    "langchain.opendataloader_all",
    "langchain.opendataloader_hidden_ocg",
    "langchain.opendataloader_hidden_text",
    "langchain.opendataloader_off_page",
    "langchain.opendataloader_tiny",
    "llamaindex.docling",
    "llamaindex.unstructured",
    "haystack.unstructured",
}
SOFT_REDS_CMAP = LinearSegmentedColormap.from_list(
    "soft_reference_reds",
    ["#fff5f0", "#fdd0c2", "#fc9272", "#ef3b2c", "#99000d"],
)
CSV_SPECS = [
    (
        "parser_attack_category_metrics.csv",
        "attack_category",
        "injection_parse_success_rate",
        "Parser by Attack Category - Injection Parsing Success Rate",
        "parser_category_success_rate.png",
    ),
    (
        "parser_attack_category_metrics.csv",
        "attack_category",
        "avg_recovery_completeness",
        "Parser by Attack Category - Injection Recovery Completeness",
        "parser_category_recovery_completeness.png",
    ),
    (
        "parser_attack_subcategory_metrics.csv",
        "attack_subcategory",
        "injection_parse_success_rate",
        "Parser by Attack Subcategory - Injection Parsing Success Rate",
        "parser_subcategory_success_rate.png",
    ),
    (
        "parser_attack_subcategory_metrics.csv",
        "attack_subcategory",
        "avg_recovery_completeness",
        "Parser by Attack Subcategory - Injection Recovery Completeness",
        "parser_subcategory_recovery_completeness.png",
    ),
]
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
    parser = argparse.ArgumentParser(description="Plot parser-level heatmaps from evaluation CSV files")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="Directory containing parser_*.csv files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for generated heatmaps")
    parser.add_argument("--dpi", type=int, default=240, help="Output image DPI")
    return parser.parse_args()


def normalize_parser_label(parser_id: str) -> str:
    framework, _, parser_name = parser_id.partition(".")
    framework_label_map = {
        "haystack": "Haystack",
        "langchain": "LangChain",
        "llamaindex": "LlamaIndex",
        "llmsherpa": "LLMSherpa",
        "docling": "Docling",
    }
    parser_label_map = {
        "multifile": "MultiFile",
        "pdfminer": "PDFMiner",
        "pypdf": "PyPDF",
        "tika": "Tika",
        "unstructured": "Unstructured",
        "docling": "Docling",
        "pdfloader": "PDFLoader",
        "pymupdf": "PyMuPDF",
        "smartpdf": "SmartPDF",
        "default": "Default",
    }

    framework_label = framework_label_map.get(framework, framework.title())
    parser_label = parser_label_map.get(parser_name, parser_name.replace("_", " ").title())
    return f"{framework_label}.{parser_label}" if parser_name else framework_label


def choose_figure_size(row_count: int, col_count: int) -> tuple[float, float]:
    width = max(9.5, col_count * 0.9 + 3.0)
    height = max(4.8, row_count * 0.72 + 1.8)
    return width, height


def load_parser_heatmap_csv(
    csv_path: Path,
    row_field: str,
    metric_field: str,
) -> tuple[list[str], list[str], list[list[float]]]:
    grouped_values: dict[str, dict[str, float]] = {}
    parser_order: list[str] = []
    row_order: list[str] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            parser_id = row["parser_id"]
            if parser_id in EXCLUDED_PARSER_IDS:
                continue
            row_label = row[row_field]
            metric_value = float((row.get(metric_field) or "0").strip())

            if parser_id not in grouped_values:
                grouped_values[parser_id] = {}
                parser_order.append(parser_id)
            if row_label not in row_order:
                row_order.append(row_label)

            grouped_values[parser_id][row_label] = metric_value

    parser_labels = [normalize_parser_label(parser_id) for parser_id in parser_order]
    values: list[list[float]] = []
    for row_label in row_order:
        current_row: list[float] = []
        for parser_id in parser_order:
            current_row.append(grouped_values[parser_id].get(row_label, math.nan))
        values.append(current_row)

    return row_order, parser_labels, values


def draw_heatmap(
    row_labels: list[str],
    col_labels: list[str],
    values: list[list[float]],
    title: str,
    output_path: Path,
    dpi: int,
) -> None:
    fig_width, fig_height = choose_figure_size(len(row_labels), len(col_labels))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    cmap = SOFT_REDS_CMAP.copy()
    cmap.set_bad(color="#d9d9d9")

    image = ax.imshow(values, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=28, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_title(title, fontsize=14, pad=14)

    ax.set_xticks([x - 0.5 for x in range(1, len(col_labels))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(row_labels))], minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)

    for row_idx, row_values in enumerate(values):
        for col_idx, value in enumerate(row_values):
            label = "N/A" if math.isnan(value) else f"{value:.3f}"
            text_color = "#1f1f1f" if math.isnan(value) or value < 0.6 else "white"
            ax.text(col_idx, row_idx, label, ha="center", va="center", fontsize=9, color=text_color)

    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("Metric", rotation=90)

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
    fig.savefig(output_dir / "parser_heatmaps_overview.png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configured_font = configure_matplotlib_fonts()
    if configured_font:
        print(f"Enabled font: {configured_font}")
    else:
        print("No CJK font detected; labels may render incorrectly")

    created_files: list[Path] = []

    for csv_name, row_field, metric_field, title, output_name in CSV_SPECS:
        csv_path = args.csv_dir / csv_name
        if not csv_path.exists():
            print(f"Skip missing CSV: {csv_path}")
            continue

        row_labels, col_labels, values = load_parser_heatmap_csv(csv_path, row_field, metric_field)
        if not row_labels or not col_labels:
            print(f"Skip empty CSV: {csv_path}")
            continue

        output_path = args.output_dir / output_name
        draw_heatmap(row_labels, col_labels, values, title, output_path, args.dpi)
        created_files.append(output_path)
        print(f"Generated heatmap: {output_path}")

    if created_files:
        save_overview_figure(args.output_dir, created_files, args.dpi)
        print(f"Generated overview: {args.output_dir / 'parser_heatmaps_overview.png'}")
    else:
        print("No parser heatmaps were generated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

