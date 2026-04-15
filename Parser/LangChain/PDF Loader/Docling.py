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
from langchain_docling import DoclingLoader


_CONVERTER_CACHE: dict[tuple[bool, bool], DocumentConverter] = {}


def build_docling_converter(force_ocr: bool = False) -> DocumentConverter:
    use_cuda = torch.cuda.is_available()
    cache_key = (force_ocr, use_cuda)
    cached = _CONVERTER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    pipeline_options = PdfPipelineOptions()
    if force_ocr:
        pipeline_options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)

    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=8,
        device=AcceleratorDevice.CUDA if use_cuda else AcceleratorDevice.CPU,
    )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    _CONVERTER_CACHE[cache_key] = converter
    return converter


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_docs_to_file(pdf_file_path: Path, final_output_path: Path, docs) -> None:
    ensure_parent_dir(final_output_path)
    with final_output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件名称: {pdf_file_path.name}\n"
            f"分块数量: {len(docs)}\n"
            f"{'=' * 30}\n\n"
        )
        file_obj.write(header)

        for doc in docs:
            content = doc.page_content
            metadata = doc.metadata

            metadata_str = "【Metadata】:\n"
            for key, value in metadata.items():
                if key == "dl_meta":
                    pretty_json = json.dumps(value, ensure_ascii=False, indent=2)
                    metadata_str += f"  - {key}:\n{pretty_json}\n"
                else:
                    metadata_str += f"  - {key}: {value}\n"

            full_output = f"{metadata_str}\n【文本内容】:\n{content}\n\n"
            file_obj.write(full_output)


def load_pdf_docling_full_meta(
    input_path: str | Path,
    output_path: str | Path,
    force_ocr: bool = False,
    converter: DocumentConverter | None = None,
) -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()

    if not pdf_file_path.exists():
        print(f"错误：找不到输入文件 '{pdf_file_path}'")
        return 0.0

    if converter is None:
        print("正在初始化 Docling ...")
        converter = build_docling_converter(force_ocr=force_ocr)

    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    print(f"OCR 模式: {'强制全页 OCR' if force_ocr else '默认(自动)'}")

    start = time.perf_counter()
    docs = DoclingLoader(file_path=str(pdf_file_path), converter=converter).load()
    write_docs_to_file(pdf_file_path, final_output_path, docs)
    elapsed_seconds = time.perf_counter() - start
    print(f"解析完成，结果已保存到: {final_output_path}")
    print(f"单个 PDF 耗时: {elapsed_seconds:.2f}s")
    return elapsed_seconds


def iter_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def build_batch_output_path(output_root: Path, input_root: Path, pdf_path: Path, output_name: str) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root)
    return output_root / relative_parent / pdf_path.stem / output_name


def load_pdf_docling_batch(
    input_dir: str | Path,
    output_root: str | Path,
    output_name: str,
    force_ocr: bool = False,
    recursive: bool = True,
) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()

    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return

    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return

    if torch.cuda.is_available():
        print(f"检测到 GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("未检测到 GPU，将使用 CPU")

    print("正在初始化 Docling（批处理模式，仅初始化一次）...")
    converter = build_docling_converter(force_ocr=force_ocr)

    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_docling_full_meta(
                pdf_path,
                output_path,
                force_ocr=force_ocr,
                converter=converter,
            )
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"解析失败: {pdf_path} -> {exc}")
            import traceback

            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(
                f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / "
                f"累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Docling PDF 解析器")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="../PDF/Zero_Size/font_0.pdf",
        help="输入 PDF 文件路径，或批处理目录路径",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="Output/zero_size/font_0/DoclingLoader_force_ocr.txt",
        help="单文件模式输出 txt 路径；目录模式输出根目录",
    )
    parser.add_argument(
        "--force_ocr",
        action="store_true",
        help="是否强制全页 OCR",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="DoclingLoader.txt",
        help="目录批处理模式下，每个 PDF 的输出文件名",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="目录模式下是否递归扫描 PDF，默认递归",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()

    try:
        if input_path.is_dir():
            load_pdf_docling_batch(
                input_path,
                args.output,
                output_name=args.output_name,
                force_ocr=args.force_ocr,
                recursive=args.recursive,
            )
        else:
            if torch.cuda.is_available():
                print(f"检测到 GPU: {torch.cuda.get_device_name(0)}")
            else:
                print("警告：未检测到 GPU，将使用 CPU，速度可能变慢")

            load_pdf_docling_full_meta(args.input, args.output, args.force_ocr)
    except Exception as exc:
        print(f"处理失败: {exc}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
