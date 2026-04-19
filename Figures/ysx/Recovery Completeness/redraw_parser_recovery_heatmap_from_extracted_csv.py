
from pathlib import Path
import math
import pandas as pd
import matplotlib.pyplot as plt

# ===== 改这两个路径就能直接在 PyCharm 运行 =====
CSV_PATH = Path(r"./parser_subcategory_recovery_completeness_extracted.csv")
OUTPUT_PATH = Path(r"./parser_subcategory_recovery_completeness_redrawn.pdf")
TITLE = "Parser by Attack Subcategory - Injection Recovery Completeness"


def draw_heatmap(df: pd.DataFrame, output_path: Path, title: str) -> None:
    row_labels = df.index.tolist()
    col_labels = df.columns.tolist()
    values = df.values

    fig_width = max(12, len(col_labels) * 0.9 + 2)
    fig_height = max(6, len(row_labels) * 0.9 + 1.5)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(values, cmap="Reds", vmin=0.0, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_title(title, fontsize=16, pad=14)

    ax.set_xticks([x - 0.5 for x in range(1, len(col_labels))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(row_labels))], minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)

    for i, row in enumerate(values):
        for j, value in enumerate(row):
            label = f"{value:.3f}" if not math.isnan(value) else "N/A"
            text_color = "white" if value >= 0.6 else "#333333"
            ax.text(j, i, label, ha="center", va="center", fontsize=10, color=text_color)

    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Metric")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main():
    df = pd.read_csv(CSV_PATH, index_col=0)
    draw_heatmap(df, OUTPUT_PATH, TITLE)
    print(f"Saved to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
