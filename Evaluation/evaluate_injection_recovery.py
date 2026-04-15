from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ATTACK_RECORDS = PROJECT_ROOT / "Dataset" / "batch1" / "attack_records.csv"
DEFAULT_PARSE_RESULTS = PROJECT_ROOT / "Parser" / "BatchParseResult" / "batch1"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Evaluation" / "results" / "batch1"
EXCLUDED_PARSER_IDS = {"langchain.pypdfdirectory"}
TARGET_FRAMEWORKS = ["docling", "haystack", "langchain", "llamaindex", "llmsherpa"]
ATTACK_CATEGORY_DISPLAY_ORDER = [
    "Visual Hiding",
    "Geometric Escape",
    "Presentation Layer Encoding",
    "Parsing Order/Multi-view Inconsistency",
]
ATTACK_SUBCATEGORY_DISPLAY_ORDER = [
    "Double Layer PDF",
    "TRM",
    "Zero Size",
    "White text",
    "OCG",
    "Out-of-bound",
    "Zero Width",
    "Misaligned",
]
ATTACK_SUBCATEGORY_ALIASES = {
    "double_layer_pdf": "Double Layer PDF",
    "trm": "TRM",
    "zero_size_font": "Zero Size",
    "white_text": "White text",
    "ocg": "OCG",
    "out_of_bound": "Out-of-bound",
    "zero_width": "Zero Width",
    "misaligned": "Misaligned",
}
METRIC_LABELS = {
    "injection_parse_success_rate": "隐式注入解析成功率",
    "avg_recovery_completeness": "隐式注入内容回复完整度",
}
KNOWN_PARSER_OUTPUTS: dict[str, dict[str, str]] = {
    "docling": {
        "DoclingLoader.txt": "docling.docling",
        "DoclingLoader_force_ocr.txt": "docling.docling_force_ocr",
    },
    "haystack": {
        "MultiFileConverter.txt": "haystack.multifile",
        "PDFMinerToDocument.txt": "haystack.pdfminer",
        "PyPDFToDocument.txt": "haystack.pypdf",
        "AzureOCRDocumentConverter.txt": "haystack.azureocr",
        "TikaDocumentConverter.txt": "haystack.tika",
        "UnstructuredFileConverter.txt": "haystack.unstructured",
    },
    "langchain": {
        "DoclingLoader.txt": "langchain.docling",
        "PDFMinerLoader.txt": "langchain.pdfminer",
        "PDFPlumberLoader.txt": "langchain.pdfplumber",
        "PyMuPDF4LLMLoader.txt": "langchain.pymupdf4llm",
        "PyMuPDFLoader.txt": "langchain.pymupdf",
        "PyPDFium2Loader.txt": "langchain.pypdfium2",
        "PyPDFLoader.txt": "langchain.pypdf",
        "UnstructuredLoader.txt": "langchain.unstructured_fast",
    },
    "llamaindex": {
        "DoclingReader.txt": "llamaindex.docling",
        "LlamaParse.txt": "llamaindex.llamaparse",
        "MarkerPDFLoader.txt": "llamaindex.marker",
        "NougatLoader.txt": "llamaindex.nougat",
        "PyMuPDFLoader.txt": "llamaindex.pymupdf",
        "SmartPDFLoader.txt": "llamaindex.smartpdf",
        "StandardPDF.txt": "llamaindex.pdfloader",
        "UnstructuredLoader.txt": "llamaindex.unstructured",
    },
    "llmsherpa": {
        "SherpaResult.txt": "llmsherpa.default",
    },
}


@dataclass(frozen=True)
class AttackRecord:
    output_file_name: str
    attack_category: str
    attack_subcategory: str
    injection_content: str
    source_pdf_name: str


@dataclass(frozen=True)
class ParseTask:
    parser_id: str
    framework: str
    env_name: str
    status: str
    input_path: Path
    output_path: Path
    output_exists: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估 PDF parser 对隐式注入内容的暴露能力与恢复完整度")
    parser.add_argument("--attack-records", type=Path, default=DEFAULT_ATTACK_RECORDS, help="attack_records.csv 路径")
    parser.add_argument("--parse-results", type=Path, default=DEFAULT_PARSE_RESULTS, help="Parser 批量输出目录")
    parser.add_argument(
        "--run-summary",
        type=Path,
        default=None,
        help="单个 run summary 文件路径；不传时会自动汇总 batch 目录下的多个 summary json",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="评估结果输出目录")
    parser.add_argument(
        "--success-threshold",
        type=float,
        default=0.1,
        help="将解析成功定义为恢复完整度达到该阈值，默认 0.1",
    )
    return parser.parse_args()


# 说明：如果某个 framework（例如 docling）是在服务器上单独跑的，
# 只要后续把输出文件同步到 `parse-results/<framework>/<pdf_stem>/...` 目录下，
# 即使本地没有对应的 summary json，本脚本也会根据输出文件名自动识别并纳入统计。


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = text.replace("\u00a0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def normalize_group_value(group_field: str, group_value: str) -> str:
    value = (group_value or "").strip()
    if group_field == "attack_subcategory":
        return ATTACK_SUBCATEGORY_ALIASES.get(value, value)
    return value


def iter_known_groups(group_field: str) -> list[str]:
    if group_field == "attack_category":
        return ATTACK_CATEGORY_DISPLAY_ORDER
    if group_field == "attack_subcategory":
        return ATTACK_SUBCATEGORY_DISPLAY_ORDER
    return []


def framework_sort_key(framework: str) -> tuple[int, str]:
    if framework in TARGET_FRAMEWORKS:
        return TARGET_FRAMEWORKS.index(framework), framework
    return len(TARGET_FRAMEWORKS), framework


def group_sort_key(group_field: str, group_name: str) -> tuple[int, str]:
    known_groups = iter_known_groups(group_field)
    if group_name in known_groups:
        return known_groups.index(group_name), group_name
    return len(known_groups), group_name


def ordered_match_count(reference_tokens: list[str], candidate_tokens: list[str]) -> int:
    if not reference_tokens or not candidate_tokens:
        return 0

    candidate_index = 0
    matched = 0
    candidate_len = len(candidate_tokens)

    for token in reference_tokens:
        while candidate_index < candidate_len and candidate_tokens[candidate_index] != token:
            candidate_index += 1
        if candidate_index >= candidate_len:
            break
        matched += 1
        candidate_index += 1

    return matched


def counter_overlap_count(reference_tokens: list[str], candidate_tokens: list[str]) -> int:
    if not reference_tokens or not candidate_tokens:
        return 0
    overlap = Counter(reference_tokens) & Counter(candidate_tokens)
    return sum(overlap.values())


def compute_metrics(injection_content: str, parsed_text: str, success_threshold: float) -> dict[str, Any]:
    normalized_injection = normalize_text(injection_content)
    normalized_parsed = normalize_text(parsed_text)

    injection_tokens = tokenize(injection_content)
    parsed_tokens = tokenize(parsed_text)

    exact_substring_match = bool(normalized_injection) and normalized_injection in normalized_parsed
    ordered_matches = ordered_match_count(injection_tokens, parsed_tokens)
    token_overlap = counter_overlap_count(injection_tokens, parsed_tokens)

    token_count = len(injection_tokens)
    if token_count == 0:
        ordered_recall = 0.0
        token_recall = 0.0
    else:
        ordered_recall = ordered_matches / token_count
        token_recall = token_overlap / token_count

    completeness = 1.0 if exact_substring_match else ordered_recall
    success = exact_substring_match or completeness >= success_threshold

    return {
        "exact_substring_match": exact_substring_match,
        "injection_token_count": token_count,
        "ordered_match_count": ordered_matches,
        "token_overlap_count": token_overlap,
        "ordered_recall": round(ordered_recall, 6),
        "token_recall": round(token_recall, 6),
        "recovery_completeness": round(completeness, 6),
        "injection_parse_success": success,
    }


def load_attack_records(csv_path: Path) -> list[AttackRecord]:
    records: list[AttackRecord] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            records.append(
                AttackRecord(
                    output_file_name=row["Output File Name"].strip(),
                    attack_category=normalize_group_value("attack_category", row["Attack Category"]),
                    attack_subcategory=normalize_group_value("attack_subcategory", row["Attack Subcategory"]),
                    injection_content=row["Injection Content"].strip(),
                    source_pdf_name=row["File Name"].strip(),
                )
            )
    return records


def discover_summary_files(parse_results_root: Path, explicit_summary: Path | None) -> list[Path]:
    if explicit_summary is not None:
        return [explicit_summary]

    summary_files = [
        path
        for path in parse_results_root.glob("*.json")
        if path.name not in {"benchmark_summary.json", "run_summary.json"}
    ]
    return sorted(summary_files, key=lambda path: path.name.lower())


def detect_parse_tasks_from_outputs(
    parse_results_root: Path,
    attack_records: list[AttackRecord],
    known_tasks: list[ParseTask],
) -> list[ParseTask]:
    attack_names = {record.output_file_name for record in attack_records}
    seen_pairs = {(task.parser_id, task.input_path.name) for task in known_tasks}
    discovered_tasks: list[ParseTask] = []

    for framework, output_map in KNOWN_PARSER_OUTPUTS.items():
        framework_root = parse_results_root / framework
        if not framework_root.exists() or not framework_root.is_dir():
            continue

        for sample_dir in sorted(path for path in framework_root.iterdir() if path.is_dir()):
            input_name = f"{sample_dir.name}.pdf"
            if input_name not in attack_names:
                continue

            for file_name, parser_id in output_map.items():
                output_path = sample_dir / file_name
                if not output_path.exists() or not output_path.is_file():
                    continue

                dedupe_key = (parser_id, input_name)
                if dedupe_key in seen_pairs:
                    continue

                seen_pairs.add(dedupe_key)
                discovered_tasks.append(
                    ParseTask(
                        parser_id=parser_id,
                        framework=framework,
                        env_name="detected_from_output",
                        status="success",
                        input_path=Path(input_name),
                        output_path=output_path,
                        output_exists=True,
                    )
                )

    return discovered_tasks


def load_parse_tasks_from_payload(payload: dict[str, Any], summary_path: Path, parse_results_root: Path) -> list[ParseTask]:
    parse_tasks: list[ParseTask] = []

    for item in payload.get("results", []):
        if item.get("parser_id") in EXCLUDED_PARSER_IDS:
            continue

        input_path = Path(item["input"])
        if input_path.is_dir() or input_path.suffix.lower() != ".pdf":
            continue

        output_path = Path(item["output"])
        if not output_path.is_absolute():
            output_path = (summary_path.parent / output_path).resolve()

        if not output_path.exists():
            try:
                relative_output = output_path.relative_to(parse_results_root)
            except ValueError:
                relative_output = None

            if relative_output is not None and relative_output.parts:
                if relative_output.parts[0] != item["framework"]:
                    output_path = parse_results_root / item["framework"] / relative_output
            else:
                output_path = (parse_results_root / item["framework"] / output_path.name).resolve()

        parse_tasks.append(
            ParseTask(
                parser_id=item["parser_id"],
                framework=item["framework"],
                env_name=item["env_name"],
                status=item["status"],
                input_path=input_path,
                output_path=output_path,
                output_exists=output_path.exists(),
            )
        )

    return parse_tasks


def load_parse_tasks(summary_files: list[Path], parse_results_root: Path) -> tuple[list[ParseTask], list[str]]:
    all_tasks: list[ParseTask] = []
    skipped_directory_parsers: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    for summary_path in summary_files:
        with summary_path.open("r", encoding="utf-8") as summary_file:
            payload = json.load(summary_file)

        for item in payload.get("results", []):
            if item.get("parser_id") in EXCLUDED_PARSER_IDS:
                continue
            input_path = Path(item["input"])
            if input_path.is_dir() or input_path.suffix.lower() != ".pdf":
                skipped_directory_parsers.add(item["parser_id"])

        for task in load_parse_tasks_from_payload(payload, summary_path, parse_results_root):
            dedupe_key = (task.parser_id, task.input_path.name)
            if dedupe_key in seen_pairs:
                continue
            seen_pairs.add(dedupe_key)
            all_tasks.append(task)

    return all_tasks, sorted(skipped_directory_parsers)


def read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def build_sample_rows(
    attack_records: list[AttackRecord],
    parse_tasks: list[ParseTask],
    success_threshold: float,
) -> list[dict[str, Any]]:
    records_by_output_name = {record.output_file_name: record for record in attack_records}
    parser_ids = sorted({task.parser_id for task in parse_tasks})

    task_lookup: dict[tuple[str, str], ParseTask] = {}
    parser_framework: dict[str, str] = {}

    for task in parse_tasks:
        pdf_name = task.input_path.name
        if pdf_name in records_by_output_name:
            task_lookup[(task.parser_id, pdf_name)] = task
            parser_framework[task.parser_id] = task.framework

    rows: list[dict[str, Any]] = []

    for parser_id in parser_ids:
        for record in attack_records:
            task = task_lookup.get((parser_id, record.output_file_name))
            parsed_text = read_text_if_exists(task.output_path) if task and task.output_exists else ""
            metrics = compute_metrics(record.injection_content, parsed_text, success_threshold)

            rows.append(
                {
                    "parser_id": parser_id,
                    "framework": parser_framework.get(parser_id, "unknown"),
                    "attack_sample": record.output_file_name,
                    "source_pdf_name": record.source_pdf_name,
                    "attack_category": record.attack_category,
                    "attack_subcategory": record.attack_subcategory,
                    "injection_content": record.injection_content,
                    "task_status": task.status if task else "not_run",
                    "output_path": str(task.output_path) if task else "",
                    "output_exists": bool(task and task.output_exists),
                    **metrics,
                }
            )

    return rows


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_samples = len(rows)
    success_samples = sum(1 for row in rows if row["injection_parse_success"])
    existing_outputs = sum(1 for row in rows if row["output_exists"])
    completeness_values = [float(row["recovery_completeness"]) for row in rows]

    return {
        "attacked_sample_count": total_samples,
        "available_output_count": existing_outputs,
        "successful_sample_count": success_samples,
        "injection_parse_success_rate": round(success_samples / total_samples, 6) if total_samples else 0.0,
        "avg_recovery_completeness": round(sum(completeness_values) / total_samples, 6) if total_samples else 0.0,
    }


def build_parser_rows(sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sample_rows:
        grouped[row["parser_id"]].append(row)

    parser_rows: list[dict[str, Any]] = []
    for parser_id, rows in sorted(grouped.items(), key=lambda item: (framework_sort_key(item[1][0]["framework"]), item[0])):
        parser_rows.append(
            {
                "parser_id": parser_id,
                "framework": rows[0]["framework"],
                **summarize_rows(rows),
            }
        )

    return parser_rows


def build_group_rows(sample_rows: list[dict[str, Any]], group_field: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sample_rows:
        grouped[(row["parser_id"], row[group_field])].append(row)

    group_rows: list[dict[str, Any]] = []
    for (parser_id, group_name), rows in sorted(
        grouped.items(),
        key=lambda item: (framework_sort_key(item[1][0]["framework"]), group_sort_key(group_field, item[0][1]), item[0][0]),
    ):
        group_rows.append(
            {
                "parser_id": parser_id,
                "framework": rows[0]["framework"],
                group_field: group_name,
                **summarize_rows(rows),
            }
        )

    return group_rows


def build_framework_group_rows(sample_rows: list[dict[str, Any]], group_field: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sample_rows:
        grouped[(row["framework"], row[group_field])].append(row)

    framework_rows: list[dict[str, Any]] = []
    frameworks_in_data = sorted({framework for framework, _ in grouped}, key=framework_sort_key)

    for framework in frameworks_in_data:
        for group_name in iter_known_groups(group_field):
            rows = grouped.get((framework, group_name), [])
            if not rows:
                continue
            framework_rows.append(
                {
                    "framework": framework,
                    group_field: group_name,
                    "parser_count": len({row["parser_id"] for row in rows}),
                    **summarize_rows(rows),
                }
            )

    return framework_rows


def build_framework_metric_rows(
    framework_group_rows: list[dict[str, Any]],
    group_field: str,
    metric_field: str,
) -> list[dict[str, Any]]:
    by_group: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in framework_group_rows:
        by_group[row[group_field]][row["framework"]] = row

    output_rows: list[dict[str, Any]] = []
    for group_name in iter_known_groups(group_field):
        metric_row: dict[str, Any] = {
            group_field: group_name,
            "metric": METRIC_LABELS[metric_field],
        }
        has_any_value = False
        for framework in TARGET_FRAMEWORKS:
            source_row = by_group.get(group_name, {}).get(framework)
            if source_row is None:
                metric_row[framework] = ""
                continue
            metric_row[framework] = round(float(source_row[metric_field]), 6)
            has_any_value = True
        if has_any_value:
            output_rows.append(metric_row)

    return output_rows


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()

    attack_records = load_attack_records(args.attack_records)
    summary_files = discover_summary_files(args.parse_results, args.run_summary)
    if not summary_files:
        raise FileNotFoundError(f"未找到 summary json: {args.parse_results}")

    parse_tasks, skipped_directory_parsers = load_parse_tasks(summary_files, args.parse_results)
    detected_tasks = detect_parse_tasks_from_outputs(args.parse_results, attack_records, parse_tasks)
    parse_tasks.extend(detected_tasks)

    sample_rows = build_sample_rows(attack_records, parse_tasks, args.success_threshold)
    parser_rows = build_parser_rows(sample_rows)
    category_rows = build_group_rows(sample_rows, "attack_category")
    subcategory_rows = build_group_rows(sample_rows, "attack_subcategory")
    framework_category_rows = build_framework_group_rows(sample_rows, "attack_category")
    framework_subcategory_rows = build_framework_group_rows(sample_rows, "attack_subcategory")

    category_success_rows = build_framework_metric_rows(
        framework_category_rows,
        "attack_category",
        "injection_parse_success_rate",
    )
    category_completeness_rows = build_framework_metric_rows(
        framework_category_rows,
        "attack_category",
        "avg_recovery_completeness",
    )
    subcategory_success_rows = build_framework_metric_rows(
        framework_subcategory_rows,
        "attack_subcategory",
        "injection_parse_success_rate",
    )
    subcategory_completeness_rows = build_framework_metric_rows(
        framework_subcategory_rows,
        "attack_subcategory",
        "avg_recovery_completeness",
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sample_csv_path = args.output_dir / "sample_level_metrics.csv"
    parser_csv_path = args.output_dir / "parser_level_metrics.csv"
    category_csv_path = args.output_dir / "parser_attack_category_metrics.csv"
    subcategory_csv_path = args.output_dir / "parser_attack_subcategory_metrics.csv"
    framework_category_csv_path = args.output_dir / "framework_attack_category_metrics.csv"
    framework_subcategory_csv_path = args.output_dir / "framework_attack_subcategory_metrics.csv"
    category_success_csv_path = args.output_dir / "framework_category_success_rate.csv"
    category_completeness_csv_path = args.output_dir / "framework_category_recovery_completeness.csv"
    subcategory_success_csv_path = args.output_dir / "framework_subcategory_success_rate.csv"
    subcategory_completeness_csv_path = args.output_dir / "framework_subcategory_recovery_completeness.csv"
    summary_json_path = args.output_dir / "evaluation_summary.json"

    save_csv(sample_csv_path, sample_rows)
    save_csv(parser_csv_path, parser_rows)
    save_csv(category_csv_path, category_rows)
    save_csv(subcategory_csv_path, subcategory_rows)
    save_csv(framework_category_csv_path, framework_category_rows)
    save_csv(framework_subcategory_csv_path, framework_subcategory_rows)
    save_csv(category_success_csv_path, category_success_rows)
    save_csv(category_completeness_csv_path, category_completeness_rows)
    save_csv(subcategory_success_csv_path, subcategory_success_rows)
    save_csv(subcategory_completeness_csv_path, subcategory_completeness_rows)

    summary_payload = {
        "attack_record_count": len(attack_records),
        "evaluated_parser_count": len(parser_rows),
        "evaluated_framework_count": len({row['framework'] for row in parser_rows}),
        "evaluated_sample_pairs": len(sample_rows),
        "success_threshold": args.success_threshold,
        "attack_records_path": str(args.attack_records.resolve()),
        "parse_results_path": str(args.parse_results.resolve()),
        "summary_files": [str(path.resolve()) for path in summary_files],
        "skipped_directory_parsers": skipped_directory_parsers,
        "detected_task_count_from_outputs": len(detected_tasks),
        "sample_level_metrics_csv": str(sample_csv_path.resolve()),
        "parser_level_metrics_csv": str(parser_csv_path.resolve()),
        "parser_attack_category_metrics_csv": str(category_csv_path.resolve()),
        "parser_attack_subcategory_metrics_csv": str(subcategory_csv_path.resolve()),
        "framework_attack_category_metrics_csv": str(framework_category_csv_path.resolve()),
        "framework_attack_subcategory_metrics_csv": str(framework_subcategory_csv_path.resolve()),
        "framework_category_success_rate_csv": str(category_success_csv_path.resolve()),
        "framework_category_recovery_completeness_csv": str(category_completeness_csv_path.resolve()),
        "framework_subcategory_success_rate_csv": str(subcategory_success_csv_path.resolve()),
        "framework_subcategory_recovery_completeness_csv": str(subcategory_completeness_csv_path.resolve()),
    }
    save_json(summary_json_path, summary_payload)

    print("评估完成")
    print(f"攻击样本数: {len(attack_records)}")
    print(f"参与评估的 parser 数: {len(parser_rows)}")
    print(f"参与评估的 framework 数: {len({row['framework'] for row in parser_rows})}")
    print(f"样本-解析器配对数: {len(sample_rows)}")
    if skipped_directory_parsers:
        print(f"跳过的目录型 parser: {', '.join(skipped_directory_parsers)}")
    print(f"五框架-四大类成功率: {category_success_csv_path}")
    print(f"五框架-四大类完整度: {category_completeness_csv_path}")
    print(f"五框架-八小类成功率: {subcategory_success_csv_path}")
    print(f"五框架-八小类完整度: {subcategory_completeness_csv_path}")
    print(f"汇总 JSON: {summary_json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
