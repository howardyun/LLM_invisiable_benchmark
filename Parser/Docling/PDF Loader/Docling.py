from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption


_CONVERTER_CACHE: dict[tuple[bool, bool], DocumentConverter] = {}


def get_pipeline_options(force_ocr: bool, extract_tables: bool) -> PdfPipelineOptions:
    pipeline_options = PdfPipelineOptions()
    if torch.cuda.is_available():
        print(f"【硬件】检测到 GPU: {torch.cuda.get_device_name(0)}，已启用 CUDA 加速。")
        pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device=AcceleratorDevice.CUDA)
    else:
        print("【硬件】未检测到 GPU，将使用 CPU 处理（速度可能受限）。")
        pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device=AcceleratorDevice.CPU)

    if force_ocr:
        print("【策略】已启用：强制全页 OCR (RapidOCR)")
        pipeline_options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)
        pipeline_options.do_ocr = True
    else:
        print("【策略】默认：智能 OCR (仅在检测到扫描件时启用)")

    pipeline_options.do_table_structure = extract_tables
    if extract_tables:
        print("【策略】已启用：增强表格结构提取")

    return pipeline_options


def build_converter(force_ocr: bool, extract_tables: bool) -> DocumentConverter:
    use_cuda = torch.cuda.is_available()
    cache_key = (force_ocr, extract_tables and use_cuda)
    cached = _CONVERTER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=get_pipeline_options(force_ocr, extract_tables)
            )
        }
    )
    _CONVERTER_CACHE[cache_key] = converter
    return converter


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_doc_to_file(pdf_file_path: Path, output_path: Path, doc, elapsed_seconds: float, force_ocr: bool) -> None:
    ensure_parent_dir(output_path)
    dl_meta_content = doc.export_to_dict()
    mock_metadata = {"source": str(pdf_file_path), "dl_meta": dl_meta_content}

    metadata_str = "【Metadata】:\n"
    for key, value in mock_metadata.items():
        if key == "dl_meta":
            pretty_json = json.dumps(value, ensure_ascii=False, indent=2)
            metadata_str += f"  - {key}:\n{pretty_json}\n"
        else:
            metadata_str += f"  - {key}: {value}\n"

    content = doc.export_to_markdown()
    with output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析报告 (Native)\n"
            f"文件名: {pdf_file_path.name}\n"
            f"耗时: {elapsed_seconds:.2f} 秒\n"
            f"策略: OCR={'开启' if force_ocr else '自动'}\n"
            f"{'=' * 40}\n\n"
        )
        file_obj.write(header)
        file_obj.write(metadata_str)
        file_obj.write("\n【文本内容】:\n")
        file_obj.write(content)
        file_obj.write("\n\n")


def process_pdf(input_path: str | Path, output_path: str | Path, force_ocr: bool = False, extract_tables: bool = False, converter: DocumentConverter | None = None) -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()

    if not pdf_file_path.exists():
        print(f"错误：找不到输入文件: {pdf_file_path}")
        return 0.0

    print(f"\n🚀 开始处理: {pdf_file_path.name}")
    print(f"   输入: {pdf_file_path}")
    print(f"   输出: {final_output_path}")

    if converter is None:
        converter = build_converter(force_ocr, extract_tables)

    start = time.perf_counter()
    result = converter.convert(str(pdf_file_path))
    elapsed_seconds = time.perf_counter() - start
    write_doc_to_file(pdf_file_path, final_output_path, result.document, elapsed_seconds, force_ocr)
    print("✅ 解析完成！")
    print(f"   保存路径: {final_output_path}")
    print(f"单个 PDF 耗时: {elapsed_seconds:.2f}s")
    return elapsed_seconds


def iter_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def build_batch_output_path(output_root: Path, input_root: Path, pdf_path: Path, output_name: str) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root)
    return output_root / relative_parent / pdf_path.stem / output_name


def process_pdf_batch(input_dir: str | Path, output_root: str | Path, output_name: str, force_ocr: bool = False, extract_tables: bool = False, recursive: bool = True) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()

    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return

    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return

    print("正在初始化 Native Docling（批处理模式，仅初始化一次）...")
    converter = build_converter(force_ocr, extract_tables)
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = process_pdf(pdf_path, output_path, force_ocr=force_ocr, extract_tables=extract_tables, converter=converter)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"❌ 发生异常: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / 累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Docling Native PDF 解析工具 (含Metadata)")
    parser.add_argument("-i", "--input", type=str, default="../../PDF/Zero_Size/font_0.pdf", help="输入 PDF 文件路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/zero_size/font_0/DoclingLoader.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("--ocr", action="store_true", help="强制开启 OCR")
    parser.add_argument("--table", action="store_true", help="开启增强表格提取")
    parser.add_argument("--output-name", type=str, default="DoclingLoader.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        process_pdf_batch(input_path, args.output, args.output_name, force_ocr=args.ocr, extract_tables=args.table, recursive=args.recursive)
    else:
        process_pdf(args.input, args.output, force_ocr=args.ocr, extract_tables=args.table)


if __name__ == "__main__":
    main()
