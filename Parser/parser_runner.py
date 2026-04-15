from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SMART_PDF_API = "http://localhost:5001/api/parseDocument?renderFormat=all"
DEFAULT_SMART_PDF_API_OCR = f"{DEFAULT_SMART_PDF_API}&applyOcr=yes"
DEFAULT_UNSTRUCTURED_API = "http://localhost:8000/general/v0/general"
DEFAULT_TIKA_URL = "http://localhost:9998/tika"

CONTENT_MARKERS = (
    "【正文内容",
    "【Markdown 内容",
    "【文本内容",
    "【内容】",
    "【表格内容",
)


@dataclass(frozen=True)
class ParserSpec:
    id: str
    framework: str
    env_name: str
    script_path: Path
    output_name: str
    input_mode: Literal["file", "directory"] = "file"
    extra_args: tuple[str, ...] = ()


PARSER_SPECS: tuple[ParserSpec, ...] = (
    ParserSpec("docling.docling", "docling", "Docling", BASE_DIR / "Docling" / "PDF Loader" / "Docling.py", "DoclingLoader.txt"),
    ParserSpec("docling.docling_force_ocr", "docling", "Docling", BASE_DIR / "Docling" / "PDF Loader" / "Docling.py", "DoclingLoader_force_ocr.txt", extra_args=("--ocr",)),

    ParserSpec("haystack.pypdf", "haystack", "Haystack-base", BASE_DIR / "Haystack" / "PDF Loader" / "PyPDFToDocument.py", "PyPDFToDocument.txt"),
    ParserSpec("haystack.multifile", "haystack", "Haystack-base", BASE_DIR / "Haystack" / "PDF Loader" / "MultiFileConverter.py", "MultiFileConverter.txt"),
    ParserSpec("haystack.pdfminer", "haystack", "Haystack-base", BASE_DIR / "Haystack" / "PDF Loader" / "PDFMinerToDocument.py", "PDFMinerToDocument.txt"),
    ParserSpec("haystack.unstructured", "haystack", "Haystack-base", BASE_DIR / "Haystack" / "PDF Loader" / "UnstructuredFileConverter.py", "UnstructuredFileConverter.txt", extra_args=("--api", DEFAULT_UNSTRUCTURED_API)),
    ParserSpec("haystack.tika", "haystack", "Haystack-base", BASE_DIR / "Haystack" / "PDF Loader" / "TiKaDocumentConverter.py", "TiKaDocumentConverter.txt", extra_args=("--url", DEFAULT_TIKA_URL)),

    ParserSpec("langchain.pypdf", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PyPDFLoader.py", "PyPDFLoader.txt"),
    ParserSpec("langchain.pymupdf", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PyMuPDF.py", "PyMuPDFLoader.txt"),
    ParserSpec("langchain.pymupdf4llm", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PyMuPDF4LLM.py", "PyMuPDF4LLMLoader.txt"),
    ParserSpec("langchain.pdfplumber", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PDFPlumber.py", "PDFPlumberLoader.txt"),
    ParserSpec("langchain.pypdfium2", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PyPDFium2.py", "PyPDFium2Loader.txt"),
    ParserSpec("langchain.pdfminer", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "PDFMiner.py", "PDFMinerLoader.txt"),
    ParserSpec("langchain.docling", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "Docling.py", "DoclingLoader.txt"),
    ParserSpec("langchain.opendataloader", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader.txt"),
    ParserSpec("langchain.opendataloader_all", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader_all.txt", extra_args=("--safety", "all")),
    ParserSpec("langchain.opendataloader_hidden_text", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader_hidden_text.txt", extra_args=("--safety", "hidden-text")),
    ParserSpec("langchain.opendataloader_off_page", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader_off_page.txt", extra_args=("--safety", "off-page")),
    ParserSpec("langchain.opendataloader_tiny", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader_tiny.txt", extra_args=("--safety", "tiny")),
    ParserSpec("langchain.opendataloader_hidden_ocg", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "OpenDataLoader.py", "OpenDataLoader_hidden_ocg.txt", extra_args=("--safety", "hidden-ocg")),
    ParserSpec("langchain.unstructured_fast", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "Unstructured.py", "UnstructuredLoader_fast.txt", extra_args=("--strategy", "fast")),
    ParserSpec("langchain.unstructured_hi_res", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "Unstructured.py", "UnstructuredLoader_hi_res.txt", extra_args=("--strategy", "hi_res")),
    ParserSpec("langchain.unstructured_ocr_only", "langchain", "LangChain", BASE_DIR / "LangChain" / "PDF Loader" / "Unstructured.py", "UnstructuredLoader_ocr_only.txt", extra_args=("--strategy", "ocr_only")),
    ParserSpec("llamaindex.pymupdf", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "PyMuPDFLoader.py", "PyMuPDFLoader.txt"),
    ParserSpec("llamaindex.pdfloader", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "PDFLoader.py", "StandardPDF.txt"),
    ParserSpec("llamaindex.unstructured", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "UnstructuredLoader.py", "UnstructuredLoader.txt"),
    ParserSpec("llamaindex.pdftable", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "PDFTableLoader.py", "PDFTable.txt", extra_args=("-p", "all")),
    ParserSpec("llamaindex.paddleocr", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "PaddleOCRLoader.py", "PaddleOCR.txt", extra_args=("--lang", "en")),
    ParserSpec("llamaindex.smartpdf", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "SmartPDFLoader.py", "SmartPDFLoader.txt", extra_args=("--api", DEFAULT_SMART_PDF_API)),
    ParserSpec("llamaindex.smartpdf_apply_ocr", "llamaindex", "LlamaIndex-base", BASE_DIR / "LlamaIndex" / "PDF Reader" / "SmartPDFLoader.py", "SmartPDFLoader_apply_ocr.txt", extra_args=("--api", DEFAULT_SMART_PDF_API_OCR)),
    ParserSpec("llamaindex.nougat", "llamaindex", "LlamaIndex-nougat", BASE_DIR / "LlamaIndex" / "PDF Reader" / "NougatOCRLoader.py", "NougatOCR.txt"),
    ParserSpec("llamaindex.marker", "llamaindex", "LlamaIndex-marker", BASE_DIR / "LlamaIndex" / "PDF Reader" / "PDFMarkerLoader.py", "PDFMarkerLoader.txt"),
    ParserSpec("llamaindex.docling", "llamaindex", "LlamaIndex-docling", BASE_DIR / "LlamaIndex" / "PDF Reader" / "DoclingLoader.py", "DoclingLoader.txt"),

    ParserSpec("llmsherpa.default", "llmsherpa", "LLMSherpa", BASE_DIR / "LLMSherpa" / "PDF Loader" / "LLMSherpa.py", "SherpaResult.txt"),
    ParserSpec("llmsherpa.apply_ocr", "llmsherpa", "LLMSherpa", BASE_DIR / "LLMSherpa" / "PDF Loader" / "LLMSherpa.py", "SherpaResult_apply_ocr.txt", extra_args=("--api", DEFAULT_SMART_PDF_API_OCR)),
)

PARSER_MAP = {spec.id: spec for spec in PARSER_SPECS}
FRAMEWORKS = sorted({spec.framework for spec in PARSER_SPECS})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统一运行 Parser 目录下所有 PDF parser，并将结果输出到指定目录。"
    )
    parser.add_argument("-i", "--input", help="单个 PDF 文件路径，或包含 PDF 的目录路径")
    parser.add_argument("-o", "--output-dir", help="统一输出目录")
    parser.add_argument(
        "-f",
        "--frameworks",
        nargs="+",
        choices=FRAMEWORKS,
        default=FRAMEWORKS,
        help="选择要跑的框架，默认全部",
    )
    parser.add_argument(
        "-p",
        "--parsers",
        nargs="+",
        default=[],
        help="按 parser id 精确筛选，例如: langchain.pypdf llamaindex.smartpdf",
    )
    parser.add_argument(
        "--include-metadata",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否保留原始 parser 输出中的元数据，默认保留",
    )
    parser.add_argument(
        "--use-current-python",
        action="store_true",
        help="使用当前 Python 解释器执行，不通过 conda run 切环境",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="目录输入时是否递归扫描 PDF，默认递归",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的任务，不真正运行",
    )
    parser.add_argument(
        "--list-frameworks",
        action="store_true",
        help="列出所有 framework 后退出",
    )
    parser.add_argument(
        "--list-parsers",
        action="store_true",
        help="列出所有 parser 及其环境、输入模式、脚本路径后退出",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        default="",
        help="额外导出 JSON 汇总到指定路径；默认仍会在输出目录生成 run_summary.json",
    )
    parser.add_argument(
        "--benchmark-output",
        type=str,
        default="",
        help="额外导出 benchmark 汇总到指定路径；默认会在输出目录生成 benchmark_summary.json",
    )
    return parser.parse_args()


def discover_pdfs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"输入文件不是 PDF: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"输入路径不存在: {input_path}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_path.glob(pattern) if path.is_file())


def select_parsers(frameworks: list[str], parser_ids: list[str]) -> list[ParserSpec]:
    if parser_ids:
        unknown = [parser_id for parser_id in parser_ids if parser_id not in PARSER_MAP]
        if unknown:
            raise ValueError(f"未知 parser id: {', '.join(unknown)}")
        selected = [PARSER_MAP[parser_id] for parser_id in parser_ids]
    else:
        selected = [spec for spec in PARSER_SPECS if spec.framework in frameworks]

    return sorted(selected, key=lambda spec: (spec.framework, spec.id))


def build_output_path(output_root: Path, input_root: Path, pdf_path: Path, spec: ParserSpec) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root) if input_root.is_dir() else Path()
    return output_root / relative_parent / pdf_path.stem / spec.framework / spec.output_name


def build_directory_output_path(output_root: Path, input_dir: Path, spec: ParserSpec) -> Path:
    return output_root / input_dir.name / spec.framework / spec.output_name


def build_command(spec: ParserSpec, input_target: Path, output_path: Path, use_current_python: bool) -> list[str]:
    python_cmd = sys.executable if use_current_python else "python"

    if use_current_python:
        base_cmd = [python_cmd]
    else:
        # Windows 下 conda run 默认也会做代理捕获，和 subprocess.capture_output 叠加后
        # 某些 parser 会出现“命令实际跑完但父进程卡住不返回”的情况。
        # 加上 --no-capture-output 让输出直接由子进程处理，避免卡住。
        base_cmd = ["conda", "run", "--no-capture-output", "-n", spec.env_name, python_cmd]

    command = base_cmd + [str(spec.script_path.name), "-i", str(input_target), "-o", str(output_path), *spec.extra_args]

    if input_target.is_dir() and spec.framework in {"langchain", "haystack", "docling", "llamaindex", "llmsherpa"} and spec.id != "langchain.pypdfdirectory":
        command.extend(["--output-name", spec.output_name])

    return command


def strip_metadata_from_text(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    skipping = False

    for line in lines:
        stripped = line.strip()
        is_metadata_header = stripped.startswith("【") and ("元数据" in stripped or "Metadata" in stripped)

        if is_metadata_header:
            skipping = True
            continue

        if skipping:
            if any(stripped.startswith(marker) for marker in CONTENT_MARKERS):
                cleaned.append(line)
                skipping = False
            continue

        cleaned.append(line)

    result = "\n".join(cleaned).strip()
    return result + "\n" if result else ""


def maybe_strip_metadata(output_path: Path, include_metadata: bool) -> None:
    if include_metadata or not output_path.exists():
        return

    raw_text = output_path.read_text(encoding="utf-8", errors="ignore")
    output_path.write_text(strip_metadata_from_text(raw_text), encoding="utf-8")


def ensure_conda_available(use_current_python: bool) -> None:
    if use_current_python:
        return

    from shutil import which

    if which("conda") is None:
        raise RuntimeError("未检测到 conda 命令。请先激活 conda，或改用 --use-current-python。")


def validate_required_args(args: argparse.Namespace) -> None:
    if args.list_frameworks or args.list_parsers:
        return

    if not args.input:
        raise ValueError("缺少 --input")
    if not args.output_dir:
        raise ValueError("缺少 --output-dir")


def print_frameworks() -> None:
    print("可用 frameworks:")
    for framework in FRAMEWORKS:
        count = sum(1 for spec in PARSER_SPECS if spec.framework == framework)
        print(f"- {framework} ({count} parsers)")


def print_parsers() -> None:
    print("可用 parsers:")
    for spec in sorted(PARSER_SPECS, key=lambda item: (item.framework, item.id)):
        print(
            f"- {spec.id}\n"
            f"    framework  : {spec.framework}\n"
            f"    env        : {spec.env_name}\n"
            f"    input_mode : {spec.input_mode}\n"
            f"    output     : {spec.output_name}\n"
            f"    script     : {spec.script_path.relative_to(BASE_DIR)}"
        )


def save_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_single_task(
    spec: ParserSpec,
    input_target: Path,
    output_path: Path,
    use_current_python: bool,
    include_metadata: bool,
    dry_run: bool,
    task_index: int | None = None,
    task_total: int | None = None,
    parser_index: int | None = None,
    parser_total: int | None = None,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(spec, input_target, output_path, use_current_python)

    progress_prefix = ""
    if task_index is not None and task_total is not None:
        progress_prefix += f"[task {task_index}/{task_total}] "
    if parser_index is not None and parser_total is not None:
        progress_prefix += f"[parser {parser_index}/{parser_total}] "

    print(f"\n{progress_prefix}[{spec.id}]")
    print(f"  env      : {spec.env_name}")
    print(f"  input    : {input_target}")
    print(f"  output   : {output_path}")
    print(f"  command  : {' '.join(command)}")

    if dry_run:
        return {
            "parser_id": spec.id,
            "framework": spec.framework,
            "env_name": spec.env_name,
            "script_path": str(spec.script_path),
            "input": str(input_target),
            "output": str(output_path),
            "status": "dry_run",
            "returncode": None,
            "duration_seconds": 0.0,
            "output_exists": False,
            "input_mode": spec.input_mode,
        }

    start = time.perf_counter()
    if use_current_python:
        completed = subprocess.run(
            command,
            cwd=spec.script_path.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    else:
        # conda run --no-capture-output 需要避免再次由 Python 捕获 stdout/stderr，
        # 否则在 Windows 上部分命令会出现已完成但 communicate() 不返回的问题。
        completed = subprocess.run(
            command,
            cwd=spec.script_path.parent,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    duration_seconds = round(time.perf_counter() - start, 4)

    maybe_strip_metadata(output_path, include_metadata)

    status = "success" if completed.returncode == 0 else "failed"
    print(f"  result   : {status}")
    print(f"  duration : {duration_seconds:.4f}s")

    return {
        "parser_id": spec.id,
        "framework": spec.framework,
        "env_name": spec.env_name,
        "script_path": str(spec.script_path),
        "input": str(input_target),
        "output": str(output_path),
        "status": status,
        "returncode": completed.returncode,
        "duration_seconds": duration_seconds,
        "output_exists": output_path.exists(),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "input_mode": spec.input_mode,
    }


def expand_result_rows(
    launch_result: dict,
    spec: ParserSpec,
    launch_input: Path,
    launch_output: Path,
    recursive: bool,
) -> list[dict]:
    if launch_input.is_file() or spec.input_mode == "directory":
        return [launch_result]

    pdfs = discover_pdfs(launch_input, recursive)
    expanded_rows: list[dict] = []
    for pdf_path in pdfs:
        output_path = build_output_path(launch_output, launch_input, pdf_path, spec)
        expanded_rows.append(
            {
                **launch_result,
                "input": str(pdf_path),
                "output": str(output_path),
                "output_exists": output_path.exists(),
            }
        )
    return expanded_rows


def build_tasks(input_path: Path, output_dir: Path, parsers: Iterable[ParserSpec], recursive: bool) -> list[tuple[ParserSpec, Path, Path]]:
    tasks: list[tuple[ParserSpec, Path, Path]] = []

    if input_path.is_file():
        for spec in parsers:
            if spec.input_mode != "file":
                continue
            output_path = build_output_path(output_dir, input_path.parent, input_path, spec)
            tasks.append((spec, input_path, output_path))
        return tasks

    pdfs = discover_pdfs(input_path, recursive)
    if not pdfs:
        raise ValueError(f"目录下未找到 PDF: {input_path}")

    batch_parser_ids = {
        "docling.docling",
        "docling.docling_force_ocr",
        "haystack.pypdf",
        "haystack.multifile",
        "haystack.pdfminer",
        "haystack.unstructured",
        "haystack.tika",
        "langchain.pypdf",
        "langchain.pymupdf",
        "langchain.pymupdf4llm",
        "langchain.pdfplumber",
        "langchain.pypdfium2",
        "langchain.pdfminer",
        "langchain.docling",
        "langchain.opendataloader",
        "langchain.opendataloader_all",
        "langchain.opendataloader_hidden_text",
        "langchain.opendataloader_off_page",
        "langchain.opendataloader_tiny",
        "langchain.opendataloader_hidden_ocg",
        "langchain.unstructured_fast",
        "langchain.unstructured_hi_res",
        "langchain.unstructured_ocr_only",
        "llamaindex.pymupdf",
        "llamaindex.pdfloader",
        "llamaindex.unstructured",
        "llamaindex.pdftable",
        "llamaindex.paddleocr",
        "llamaindex.smartpdf",
        "llamaindex.smartpdf_apply_ocr",
        "llamaindex.nougat",
        "llamaindex.marker",
        "llamaindex.docling",
        "llmsherpa.default",
        "llmsherpa.apply_ocr",
    }

    for spec in parsers:
        if spec.input_mode == "directory":
            output_path = build_directory_output_path(output_dir, input_path, spec)
            tasks.append((spec, input_path, output_path))
            continue

        if spec.id in batch_parser_ids:
            output_path = output_dir / spec.framework
            tasks.append((spec, input_path, output_path))
            continue

        for pdf_path in pdfs:
            output_path = build_output_path(output_dir, input_path, pdf_path, spec)
            tasks.append((spec, pdf_path, output_path))

    return tasks


def build_benchmark_summary(results: list[dict], launch_results: list[dict], pdf_count: int) -> dict:
    framework_stats: dict[str, dict] = {}
    parser_stats: dict[str, dict] = {}

    for item in launch_results:
        framework = item["framework"]
        parser_id = item["parser_id"]
        duration = float(item.get("duration_seconds", 0.0) or 0.0)
        status = item["status"]

        framework_bucket = framework_stats.setdefault(
            framework,
            {
                "framework": framework,
                "task_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "dry_run_count": 0,
                "total_duration_seconds": 0.0,
            },
        )
        framework_bucket["task_count"] += 1
        framework_bucket["total_duration_seconds"] = round(framework_bucket["total_duration_seconds"] + duration, 4)
        framework_bucket[f"{status}_count"] = framework_bucket.get(f"{status}_count", 0) + 1

        parser_bucket = parser_stats.setdefault(
            parser_id,
            {
                "parser_id": parser_id,
                "framework": framework,
                "env_name": item["env_name"],
                "task_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "dry_run_count": 0,
                "total_duration_seconds": 0.0,
                "avg_duration_seconds": 0.0,
            },
        )
        parser_bucket["task_count"] += 1
        parser_bucket["total_duration_seconds"] = round(parser_bucket["total_duration_seconds"] + duration, 4)
        parser_bucket[f"{status}_count"] = parser_bucket.get(f"{status}_count", 0) + 1

    for bucket in parser_stats.values():
        if bucket["task_count"]:
            bucket["avg_duration_seconds"] = round(bucket["total_duration_seconds"] / bucket["task_count"], 4)

    total_duration = round(sum(float(item.get("duration_seconds", 0.0) or 0.0) for item in launch_results), 4)
    return {
        "pdf_count": pdf_count,
        "task_count": len(launch_results),
        "success_count": sum(1 for item in launch_results if item["status"] == "success"),
        "failed_count": sum(1 for item in launch_results if item["status"] == "failed"),
        "dry_run_count": sum(1 for item in launch_results if item["status"] == "dry_run"),
        "total_duration_seconds": total_duration,
        "frameworks": sorted(framework_stats.values(), key=lambda item: item["framework"]),
        "parsers": sorted(parser_stats.values(), key=lambda item: item["parser_id"]),
    }


def main() -> int:
    args = parse_args()

    if args.list_frameworks:
        print_frameworks()
        return 0

    if args.list_parsers:
        print_parsers()
        return 0

    validate_required_args(args)
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()

    ensure_conda_available(args.use_current_python)
    parsers = select_parsers(args.frameworks, args.parsers)
    tasks = build_tasks(input_path, output_dir, parsers, args.recursive)
    pdf_count = len(discover_pdfs(input_path, args.recursive))

    print("=" * 72)
    print("统一 PDF Parser Runner")
    print(f"输入路径           : {input_path}")
    print(f"输出目录           : {output_dir}")
    print(f"PDF 数量           : {pdf_count}")
    print(f"框架数量           : {len({spec.framework for spec in parsers})}")
    print(f"Parser 数量        : {len(parsers)}")
    print(f"任务总数           : {len(tasks)}")
    print(f"保留元数据         : {args.include_metadata}")
    print(f"执行模式           : {'当前 Python' if args.use_current_python else 'conda run'}")
    print(f"仅预览             : {args.dry_run}")
    print("=" * 72)

    parser_order: list[str] = []
    for spec, _, _ in tasks:
        if spec.id not in parser_order:
            parser_order.append(spec.id)
    parser_position = {parser_id: index for index, parser_id in enumerate(parser_order, start=1)}

    results = [
        run_single_task(
            spec,
            input_target,
            output_path,
            args.use_current_python,
            args.include_metadata,
            args.dry_run,
            task_index=task_index,
            task_total=len(tasks),
            parser_index=parser_position[spec.id],
            parser_total=len(parser_order),
        )
        for task_index, (spec, input_target, output_path) in enumerate(tasks, start=1)
    ]

    expanded_results: list[dict] = []
    for launch_result, (spec, input_target, output_path) in zip(results, tasks):
        expanded_results.extend(
            expand_result_rows(
                launch_result=launch_result,
                spec=spec,
                launch_input=input_target,
                launch_output=output_path,
                recursive=args.recursive,
            )
        )

    success_count = sum(1 for item in results if item["status"] in {"success", "dry_run"})
    failed_count = sum(1 for item in results if item["status"] == "failed")

    summary = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "include_metadata": args.include_metadata,
        "use_current_python": args.use_current_python,
        "dry_run": args.dry_run,
        "frameworks": args.frameworks,
        "parsers": [spec.id for spec in parsers],
        "pdf_count": pdf_count,
        "task_count": len(results),
        "result_count": len(expanded_results),
        "success_count": success_count,
        "failed_count": failed_count,
        "launch_results": results,
        "results": expanded_results,
    }
    benchmark_summary = build_benchmark_summary(expanded_results, results, pdf_count)

    summary_path = save_json(output_dir / "run_summary.json", summary)
    benchmark_path = save_json(output_dir / "benchmark_summary.json", benchmark_summary)

    if args.json_output:
        save_json(Path(args.json_output).resolve(), summary)
    if args.benchmark_output:
        save_json(Path(args.benchmark_output).resolve(), benchmark_summary)

    print("\n" + "=" * 72)
    print(f"完成。成功/预览: {success_count}，失败: {failed_count}")
    print(f"运行汇总: {summary_path}")
    print(f"Benchmark: {benchmark_path}")
    print("=" * 72)

    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
