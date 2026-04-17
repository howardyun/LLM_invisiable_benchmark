from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "Dataset"
DEFAULT_PARSE_RESULTS_ROOT = PROJECT_ROOT / "Parser" / "BatchParseResult"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Evaluation" / "results" / "all_batches"
# 按当前实验设置，整体去掉 docling 框架。
TARGET_FRAMEWORKS = ["haystack", "langchain", "llamaindex", "llmsherpa"]
# 同时去掉 docling 整个框架，以及 langchain 下 OpenDataLoader 及其 6 种配置，
# 再额外去掉 llamaindex 的 docling / unstructured，以及 haystack 的 unstructured。
EXCLUDED_FRAMEWORKS = {"docling"}
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
        # 当前实验中排除 Haystack 的 Unstructured。
        # "UnstructuredFileConverter.txt": "haystack.unstructured",
    },
    "langchain": {
        # 当前实验中排除 OpenDataLoader 及其 6 种配置。
        # "OpenDataLoader.txt": "langchain.opendataloader",
        # "OpenDataLoader_all.txt": "langchain.opendataloader_all",
        # "OpenDataLoader_hidden_ocg.txt": "langchain.opendataloader_hidden_ocg",
        # "OpenDataLoader_hidden_text.txt": "langchain.opendataloader_hidden_text",
        # "OpenDataLoader_off_page.txt": "langchain.opendataloader_off_page",
        # "OpenDataLoader_tiny.txt": "langchain.opendataloader_tiny",
        "DoclingLoader.txt": "langchain.docling",
        "PDFMinerLoader.txt": "langchain.pdfminer",
        "PDFPlumberLoader.txt": "langchain.pdfplumber",
        "PyMuPDF4LLMLoader.txt": "langchain.pymupdf4llm",
        "PyMuPDFLoader.txt": "langchain.pymupdf",
        "PyPDFium2Loader.txt": "langchain.pypdfium2",
        "PyPDFLoader.txt": "langchain.pypdf",
        "UnstructuredLoader.txt": "langchain.unstructured_fast",
        "UnstructuredLoader_fast.txt": "langchain.unstructured_fast",
    },
    "llamaindex": {
        # 当前实验中排除 LlamaIndex 的 Docling。
        # "DoclingLoader.txt": "llamaindex.docling",
        # "DoclingReader.txt": "llamaindex.docling",
        "LlamaParse.txt": "llamaindex.llamaparse",
        "MarkerPDFLoader.txt": "llamaindex.marker",
        "NougatLoader.txt": "llamaindex.nougat",
        "PyMuPDFLoader.txt": "llamaindex.pymupdf",
        "SmartPDFLoader.txt": "llamaindex.smartpdf",
        "StandardPDF.txt": "llamaindex.pdfloader",
        # 当前实验中排除 LlamaIndex 的 Unstructured。
        # "UnstructuredLoader.txt": "llamaindex.unstructured",
    },
    "llmsherpa": {
        "SherpaResult.txt": "llmsherpa.default",
    },
}


@dataclass(frozen=True)
class AttackRecord:
    batch_name: str
    output_file_name: str
    attack_category: str
    attack_subcategory: str
    injection_content: str
    source_pdf_name: str


@dataclass(frozen=True)
class ParseTask:
    batch_name: str
    attack_sample: str
    parser_id: str
    framework: str
    output_path: Path


@dataclass(frozen=True)
class PreparedText:
    raw_text: str
    normalized_text: str
    tokens: list[str]


@dataclass(frozen=True)
class ProgressLogger:
    enabled: bool = True

    def log(self, message: str) -> None:
        if self.enabled:
            print(f"[evaluate_injection_recovery] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估 PDF parser 对隐式注入内容的暴露能力与恢复完整度")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="包含多个 batch 子目录的 Dataset 根目录",
    )
    parser.add_argument(
        "--parse-results-root",
        type=Path,
        default=DEFAULT_PARSE_RESULTS_ROOT,
        help="包含多个 batch 子目录的 Parser 输出根目录",
    )
    parser.add_argument(
        "--batches",
        nargs="*",
        default=None,
        help="要评估的 batch 名称列表；不传时自动取 Dataset 与 Parser 输出中共同存在的 batch",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="评估结果输出目录")
    parser.add_argument(
        "--success-threshold",
        type=float,
        default=0.1,
        help="将解析成功定义为恢复完整度达到该阈值，默认 0.1",
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


def prepare_text(text: str) -> PreparedText:
    normalized_text = normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized_text)
    return PreparedText(raw_text=text, normalized_text=normalized_text, tokens=tokens)


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


def compute_metrics(
    prepared_injection: PreparedText,
    prepared_parsed: PreparedText,
    success_threshold: float,
) -> dict[str, Any]:
    exact_substring_match = bool(prepared_injection.normalized_text) and (
        prepared_injection.normalized_text in prepared_parsed.normalized_text
    )
    ordered_matches = ordered_match_count(prepared_injection.tokens, prepared_parsed.tokens)
    token_overlap = counter_overlap_count(prepared_injection.tokens, prepared_parsed.tokens)

    token_count = len(prepared_injection.tokens)
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


def discover_batches(dataset_root: Path, parse_results_root: Path, requested_batches: list[str] | None) -> list[str]:
    if requested_batches:
        return requested_batches

    dataset_batches = {path.name for path in dataset_root.iterdir() if path.is_dir()} if dataset_root.exists() else set()
    result_batches = {path.name for path in parse_results_root.iterdir() if path.is_dir()} if parse_results_root.exists() else set()
    batches = sorted(dataset_batches & result_batches)
    if not batches:
        raise FileNotFoundError("未找到可评估的 batch：请检查 Dataset 与 Parser/BatchParseResult 目录")
    return batches


def load_attack_records(dataset_root: Path, batch_names: list[str]) -> list[AttackRecord]:
    records: list[AttackRecord] = []

    for batch_name in batch_names:
        csv_path = dataset_root / batch_name / "attack_records.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"未找到 attack_records.csv: {csv_path}")

        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                records.append(
                    AttackRecord(
                        batch_name=batch_name,
                        output_file_name=row["Output File Name"].strip(),
                        attack_category=normalize_group_value("attack_category", row["Attack Category"]),
                        attack_subcategory=normalize_group_value("attack_subcategory", row["Attack Subcategory"]),
                        injection_content=row["Injection Content"].strip(),
                        source_pdf_name=row["File Name"].strip(),
                    )
                )

    return records


def discover_parse_tasks(parse_results_root: Path, attack_records: list[AttackRecord], batch_names: list[str]) -> list[ParseTask]:
    attack_records_by_batch: dict[str, dict[str, AttackRecord]] = defaultdict(dict)
    for record in attack_records:
        attack_records_by_batch[record.batch_name][record.output_file_name] = record

    tasks: list[ParseTask] = []
    seen: set[tuple[str, str, str]] = set()

    for batch_name in batch_names:
        batch_root = parse_results_root / batch_name
        if not batch_root.exists():
            raise FileNotFoundError(f"未找到 batch 输出目录: {batch_root}")

        valid_samples = attack_records_by_batch.get(batch_name, {})
        for framework, output_map in KNOWN_PARSER_OUTPUTS.items():
            if framework in EXCLUDED_FRAMEWORKS:
                continue

            framework_root = batch_root / framework
            if not framework_root.exists() or not framework_root.is_dir():
                continue

            for sample_dir in sorted(path for path in framework_root.iterdir() if path.is_dir()):
                attack_sample = f"{sample_dir.name}.pdf"
                if attack_sample not in valid_samples:
                    continue

                for file_name, parser_id in output_map.items():
                    if parser_id in EXCLUDED_PARSER_IDS:
                        continue

                    output_path = sample_dir / file_name
                    if not output_path.exists() or not output_path.is_file():
                        continue

                    dedupe_key = (batch_name, attack_sample, parser_id)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    tasks.append(
                        ParseTask(
                            batch_name=batch_name,
                            attack_sample=attack_sample,
                            parser_id=parser_id,
                            framework=framework,
                            output_path=output_path,
                        )
                    )

    return tasks


def read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def build_prepared_attack_lookup(
    attack_records: list[AttackRecord],
    logger: ProgressLogger | None = None,
) -> dict[tuple[str, str], PreparedText]:
    prepared_lookup: dict[tuple[str, str], PreparedText] = {}
    total_records = len(attack_records)
    progress_interval = max(1, total_records // 10) if total_records else 1

    for index, record in enumerate(attack_records, start=1):
        prepared_lookup[(record.batch_name, record.output_file_name)] = prepare_text(record.injection_content)
        if logger and (index == 1 or index == total_records or index % progress_interval == 0):
            logger.log(f"注入文本预处理进度: {index}/{total_records}")

    return prepared_lookup


def build_prepared_parse_lookup(
    parse_tasks: list[ParseTask],
    logger: ProgressLogger | None = None,
) -> dict[tuple[str, str, str], PreparedText]:
    prepared_lookup: dict[tuple[str, str, str], PreparedText] = {}
    total_tasks = len(parse_tasks)
    progress_interval = max(1, total_tasks // 10) if total_tasks else 1

    for index, task in enumerate(parse_tasks, start=1):
        prepared_lookup[(task.batch_name, task.attack_sample, task.parser_id)] = prepare_text(read_text_if_exists(task.output_path))
        if logger and (index == 1 or index == total_tasks or index % progress_interval == 0):
            logger.log(f"解析输出预处理进度: {index}/{total_tasks}")

    return prepared_lookup


def build_sample_rows(
    attack_records: list[AttackRecord],
    parse_tasks: list[ParseTask],
    success_threshold: float,
    logger: ProgressLogger | None = None,
) -> list[dict[str, Any]]:
    parser_ids = sorted({task.parser_id for task in parse_tasks})
    task_lookup: dict[tuple[str, str, str], ParseTask] = {}
    parser_framework: dict[str, str] = {}

    for task in parse_tasks:
        task_lookup[(task.batch_name, task.attack_sample, task.parser_id)] = task
        parser_framework[task.parser_id] = task.framework

    if logger:
        logger.log(f"开始构建缓存：{len(attack_records)} 条攻击记录，{len(parse_tasks)} 个解析输出")
    prepared_attack_lookup = build_prepared_attack_lookup(attack_records, logger=logger)
    prepared_parse_lookup = build_prepared_parse_lookup(parse_tasks, logger=logger)
    empty_prepared_text = PreparedText(raw_text="", normalized_text="", tokens=[])

    total_pairs = len(parser_ids) * len(attack_records)
    progress_interval = max(1, total_pairs // 20) if total_pairs else 1
    processed_pairs = 0

    rows: list[dict[str, Any]] = []
    for parser_id in parser_ids:
        if logger:
            logger.log(f"开始评估 parser: {parser_id}")
        for record in attack_records:
            task = task_lookup.get((record.batch_name, record.output_file_name, parser_id))
            prepared_injection = prepared_attack_lookup[(record.batch_name, record.output_file_name)]
            prepared_parsed = (
                prepared_parse_lookup[(task.batch_name, task.attack_sample, task.parser_id)] if task else empty_prepared_text
            )
            metrics = compute_metrics(prepared_injection, prepared_parsed, success_threshold)

            rows.append(
                {
                    "batch_name": record.batch_name,
                    "parser_id": parser_id,
                    "framework": parser_framework.get(parser_id, "unknown"),
                    "attack_sample": record.output_file_name,
                    "source_pdf_name": record.source_pdf_name,
                    "attack_category": record.attack_category,
                    "attack_subcategory": record.attack_subcategory,
                    "injection_content": record.injection_content,
                    "task_status": "success" if task else "not_run",
                    "output_path": str(task.output_path) if task else "",
                    "output_exists": bool(task),
                    **metrics,
                }
            )
            processed_pairs += 1
            if logger and (processed_pairs == 1 or processed_pairs == total_pairs or processed_pairs % progress_interval == 0):
                logger.log(f"样本-解析器评估进度: {processed_pairs}/{total_pairs}")

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


def build_attack_method_ranking_rows(sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_by_subcategory: dict[str, str] = {}

    for row in sample_rows:
        attack_method = row["attack_subcategory"]
        grouped[attack_method].append(row)
        category_by_subcategory[attack_method] = row["attack_category"]

    ranking_rows: list[dict[str, Any]] = []
    sorted_items = sorted(
        grouped.items(),
        key=lambda item: (
            -float(summarize_rows(item[1])["injection_parse_success_rate"]),
            -float(summarize_rows(item[1])["avg_recovery_completeness"]),
            item[0],
        ),
    )

    for rank, (attack_method, rows) in enumerate(sorted_items, start=1):
        ranking_rows.append(
            {
                "rank": rank,
                "attack_category": category_by_subcategory[attack_method],
                "attack_method": attack_method,
                **summarize_rows(rows),
            }
        )

    return ranking_rows


def build_parser_vulnerability_ranking_rows(sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    framework_by_parser: dict[str, str] = {}

    for row in sample_rows:
        parser_id = row["parser_id"]
        grouped[parser_id].append(row)
        framework_by_parser[parser_id] = row["framework"]

    ranking_rows: list[dict[str, Any]] = []
    sorted_items = sorted(
        grouped.items(),
        key=lambda item: (
            -float(summarize_rows(item[1])["injection_parse_success_rate"]),
            -float(summarize_rows(item[1])["avg_recovery_completeness"]),
            framework_sort_key(framework_by_parser[item[0]]),
            item[0],
        ),
    )

    for rank, (parser_id, rows) in enumerate(sorted_items, start=1):
        ranking_rows.append(
            {
                "rank": rank,
                "parser_id": parser_id,
                "framework": framework_by_parser[parser_id],
                **summarize_rows(rows),
            }
        )

    return ranking_rows


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
    logger = ProgressLogger()
    total_start = perf_counter()

    logger.log("开始评估")
    logger.log(f"dataset_root = {args.dataset_root}")
    logger.log(f"parse_results_root = {args.parse_results_root}")
    logger.log(f"output_dir = {args.output_dir}")

    step_start = perf_counter()
    batch_names = discover_batches(args.dataset_root, args.parse_results_root, args.batches)
    logger.log(f"已发现 {len(batch_names)} 个 batch: {', '.join(batch_names)}，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
    attack_records = load_attack_records(args.dataset_root, batch_names)
    logger.log(f"已加载攻击记录 {len(attack_records)} 条，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
    parse_tasks = discover_parse_tasks(args.parse_results_root, attack_records, batch_names)
    logger.log(f"已发现解析输出任务 {len(parse_tasks)} 个，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
    sample_rows = build_sample_rows(attack_records, parse_tasks, args.success_threshold, logger=logger)
    logger.log(f"样本级评估完成，共 {len(sample_rows)} 条记录，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
    parser_rows = build_parser_rows(sample_rows)
    category_rows = build_group_rows(sample_rows, "attack_category")
    subcategory_rows = build_group_rows(sample_rows, "attack_subcategory")
    framework_category_rows = build_framework_group_rows(sample_rows, "attack_category")
    framework_subcategory_rows = build_framework_group_rows(sample_rows, "attack_subcategory")
    logger.log(f"聚合统计完成，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
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
    attack_method_ranking_rows = build_attack_method_ranking_rows(sample_rows)
    parser_vulnerability_ranking_rows = build_parser_vulnerability_ranking_rows(sample_rows)
    logger.log(f"框架热图指标与排序整理完成，耗时 {perf_counter() - step_start:.2f}s")

    step_start = perf_counter()
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
    attack_method_ranking_csv_path = args.output_dir / "attack_method_success_ranking.csv"
    parser_vulnerability_ranking_csv_path = args.output_dir / "parser_vulnerability_ranking.csv"
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
    save_csv(attack_method_ranking_csv_path, attack_method_ranking_rows)
    save_csv(parser_vulnerability_ranking_csv_path, parser_vulnerability_ranking_rows)

    summary_payload = {
        "batch_names": batch_names,
        "batch_count": len(batch_names),
        "attack_record_count": len(attack_records),
        "evaluated_parser_count": len(parser_rows),
        "evaluated_framework_count": len({row['framework'] for row in parser_rows}),
        "evaluated_sample_pairs": len(sample_rows),
        "discovered_output_task_count": len(parse_tasks),
        "success_threshold": args.success_threshold,
        "dataset_root": str(args.dataset_root.resolve()),
        "parse_results_root": str(args.parse_results_root.resolve()),
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
        "attack_method_success_ranking_csv": str(attack_method_ranking_csv_path.resolve()),
        "parser_vulnerability_ranking_csv": str(parser_vulnerability_ranking_csv_path.resolve()),
    }
    save_json(summary_json_path, summary_payload)
    logger.log(f"结果文件已写出，耗时 {perf_counter() - step_start:.2f}s")
    logger.log(f"总耗时 {perf_counter() - total_start:.2f}s")

    print("评估完成")
    print(f"Batch 数: {len(batch_names)} -> {', '.join(batch_names)}")
    print(f"攻击样本数: {len(attack_records)}")
    print(f"发现输出任务数: {len(parse_tasks)}")
    print(f"参与评估的 parser 数: {len(parser_rows)}")
    print(f"参与评估的 framework 数: {len({row['framework'] for row in parser_rows})}")
    print(f"样本-解析器配对数: {len(sample_rows)}")
    print(f"五框架-四大类成功率: {category_success_csv_path}")
    print(f"五框架-四大类完整度: {category_completeness_csv_path}")
    print(f"五框架-八小类成功率: {subcategory_success_csv_path}")
    print(f"五框架-八小类完整度: {subcategory_completeness_csv_path}")
    print(f"攻击方法成功率排序: {attack_method_ranking_csv_path}")
    print(f"解析器易受攻击排序: {parser_vulnerability_ranking_csv_path}")
    print(f"汇总 JSON: {summary_json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
