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
DEFAULT_ATTACK_RECORDS = PROJECT_ROOT / "Dataset" / "attack_records.csv"
DEFAULT_PARSE_RESULTS = PROJECT_ROOT / "Parser" / "BatchParseResult"
DEFAULT_RUN_SUMMARY = DEFAULT_PARSE_RESULTS / "run_summary.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Evaluation" / "results"


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
    parser.add_argument("--run-summary", type=Path, default=DEFAULT_RUN_SUMMARY, help="parser_runner 生成的 run_summary.json 路径")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="评估结果输出目录")
    parser.add_argument(
        "--success-threshold",
        type=float,
        default=0.5,
        help="将解析成功定义为恢复完整度达到该阈值，默认 0.5",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = text.replace("\u00a0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


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
                    attack_category=row["Attack Category"].strip(),
                    attack_subcategory=row["Attack Subcategory"].strip(),
                    injection_content=row["Injection Content"].strip(),
                    source_pdf_name=row["File Name"].strip(),
                )
            )
    return records


def load_run_summary(summary_path: Path) -> tuple[list[ParseTask], list[str]]:
    with summary_path.open("r", encoding="utf-8") as summary_file:
        payload = json.load(summary_file)

    parse_tasks: list[ParseTask] = []
    skipped_directory_parsers: list[str] = []

    for item in payload.get("results", []):
        input_path = Path(item["input"])
        if input_path.is_dir() or input_path.suffix.lower() != ".pdf":
            skipped_directory_parsers.append(item["parser_id"])
            continue

        parse_tasks.append(
            ParseTask(
                parser_id=item["parser_id"],
                framework=item["framework"],
                env_name=item["env_name"],
                status=item["status"],
                input_path=input_path,
                output_path=Path(item["output"]),
                output_exists=bool(item.get("output_exists", False)),
            )
        )

    return parse_tasks, sorted(set(skipped_directory_parsers))


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
    parser_env: dict[str, str] = {}

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


def build_parser_rows(sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sample_rows:
        grouped[row["parser_id"]].append(row)

    parser_rows: list[dict[str, Any]] = []

    for parser_id, rows in sorted(grouped.items()):
        total_samples = len(rows)
        success_samples = sum(1 for row in rows if row["injection_parse_success"])
        existing_outputs = sum(1 for row in rows if row["output_exists"])
        completeness_values = [float(row["recovery_completeness"]) for row in rows]
        success_completeness_values = [
            float(row["recovery_completeness"]) for row in rows if row["injection_parse_success"]
        ]

        parser_rows.append(
            {
                "parser_id": parser_id,
                "framework": rows[0]["framework"],
                "attacked_sample_count": total_samples,
                "available_output_count": existing_outputs,
                "successful_sample_count": success_samples,
                "injection_parse_success_rate": round(success_samples / total_samples, 6) if total_samples else 0.0,
                "avg_recovery_completeness": round(sum(completeness_values) / total_samples, 6) if total_samples else 0.0,
                "avg_recovery_completeness_on_success": round(
                    sum(success_completeness_values) / len(success_completeness_values), 6
                ) if success_completeness_values else 0.0,
            }
        )

    return parser_rows


def build_group_rows(sample_rows: list[dict[str, Any]], group_field: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sample_rows:
        grouped[(row["parser_id"], row[group_field])].append(row)

    group_rows: list[dict[str, Any]] = []

    for (parser_id, group_name), rows in sorted(grouped.items()):
        total_samples = len(rows)
        success_samples = sum(1 for row in rows if row["injection_parse_success"])
        existing_outputs = sum(1 for row in rows if row["output_exists"])
        completeness_values = [float(row["recovery_completeness"]) for row in rows]
        success_completeness_values = [
            float(row["recovery_completeness"]) for row in rows if row["injection_parse_success"]
        ]

        group_rows.append(
            {
                "parser_id": parser_id,
                "framework": rows[0]["framework"],
                group_field: group_name,
                "attacked_sample_count": total_samples,
                "available_output_count": existing_outputs,
                "successful_sample_count": success_samples,
                "injection_parse_success_rate": round(success_samples / total_samples, 6) if total_samples else 0.0,
                "avg_recovery_completeness": round(sum(completeness_values) / total_samples, 6) if total_samples else 0.0,
                "avg_recovery_completeness_on_success": round(
                    sum(success_completeness_values) / len(success_completeness_values), 6
                ) if success_completeness_values else 0.0,
            }
        )

    return group_rows


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
    parse_tasks, skipped_directory_parsers = load_run_summary(args.run_summary)

    sample_rows = build_sample_rows(attack_records, parse_tasks, args.success_threshold)
    parser_rows = build_parser_rows(sample_rows)
    category_rows = build_group_rows(sample_rows, "attack_category")
    subcategory_rows = build_group_rows(sample_rows, "attack_subcategory")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sample_csv_path = args.output_dir / "sample_level_metrics.csv"
    parser_csv_path = args.output_dir / "parser_level_metrics.csv"
    category_csv_path = args.output_dir / "parser_attack_category_metrics.csv"
    subcategory_csv_path = args.output_dir / "parser_attack_subcategory_metrics.csv"
    summary_json_path = args.output_dir / "evaluation_summary.json"

    save_csv(sample_csv_path, sample_rows)
    save_csv(parser_csv_path, parser_rows)
    save_csv(category_csv_path, category_rows)
    save_csv(subcategory_csv_path, subcategory_rows)

    summary_payload = {
        "attack_record_count": len(attack_records),
        "evaluated_parser_count": len(parser_rows),
        "evaluated_sample_pairs": len(sample_rows),
        "success_threshold": args.success_threshold,
        "attack_records_path": str(args.attack_records.resolve()),
        "parse_results_path": str(args.parse_results.resolve()),
        "run_summary_path": str(args.run_summary.resolve()),
        "skipped_directory_parsers": skipped_directory_parsers,
        "sample_level_metrics_csv": str(sample_csv_path.resolve()),
        "parser_level_metrics_csv": str(parser_csv_path.resolve()),
        "parser_attack_category_metrics_csv": str(category_csv_path.resolve()),
        "parser_attack_subcategory_metrics_csv": str(subcategory_csv_path.resolve()),
        "parser_metrics": parser_rows,
        "parser_attack_category_metrics": category_rows,
        "parser_attack_subcategory_metrics": subcategory_rows,
    }
    save_json(summary_json_path, summary_payload)

    print("评估完成")
    print(f"攻击样本数: {len(attack_records)}")
    print(f"参与评估的 parser 数: {len(parser_rows)}")
    print(f"样本-解析器配对数: {len(sample_rows)}")
    if skipped_directory_parsers:
        print(f"跳过的目录型 parser: {', '.join(skipped_directory_parsers)}")
    print(f"样本级结果: {sample_csv_path}")
    print(f"Parser 级结果: {parser_csv_path}")
    print(f"按攻击类别汇总: {category_csv_path}")
    print(f"按攻击子类别汇总: {subcategory_csv_path}")
    print(f"汇总 JSON: {summary_json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

