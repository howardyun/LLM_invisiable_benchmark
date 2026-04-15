from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from llama_index.readers.nougat_ocr import PDFNougatOCR


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def cleanup_nougat_temp_files(pdf_file_path: Path) -> None:
    mmd_filename = pdf_file_path.stem + ".mmd"
    possible_paths = [Path("output") / mmd_filename, pdf_file_path.with_suffix(".mmd"), Path(mmd_filename)]
    cleaned_file = False
    for file_path in possible_paths:
        if file_path.exists():
            try:
                os.remove(file_path)
                print(f"【清理】已删除中间文件: {file_path}")
                cleaned_file = True
            except Exception as exc:
                print(f"【警告】无法删除文件 {file_path}: {exc}")
    nougat_output_dir = Path("output")
    if nougat_output_dir.exists() and nougat_output_dir.is_dir():
        try:
            os.rmdir(nougat_output_dir)
            print(f"【清理】已移除空的临时目录: {nougat_output_dir}")
        except OSError:
            pass
    if not cleaned_file:
        print("【提示】未发现残留的 .mmd 文件 (可能已经被自动清理)")


def write_docs_to_file(pdf_file_path: Path, output_path: Path, docs) -> None:
    ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析结果 (NougatOCR): {pdf_file_path.name}\n"
            f"保存位置: {output_path}\n"
            f"解析出的文档对象数量: {len(docs)}\n"
            f"说明: Nougat 擅长提取公式(LaTeX)和表格格式\n"
            f"{'=' * 30}\n\n"
        )
        print(header)
        file_obj.write(header)
        for index, doc in enumerate(docs):
            content = doc.text
            metadata_dict = doc.metadata
            metadata_str = f"【文档块 (Document {index}) 元数据】:\n"
            if metadata_dict:
                for key, value in metadata_dict.items():
                    metadata_str += f"  - {key}: {value}\n"
            else:
                metadata_str += "  - (无元数据)\n"
            file_obj.write(f"{metadata_str}\n【正文内容 (Markdown/LaTeX)】:\n{content}\n\n{'-' * 20}\n\n")


def load_pdf_nougat(input_path: str | Path, output_path: str | Path, loader: PDFNougatOCR | None = None) -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()
    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    if not pdf_file_path.exists():
        print(f"错误：找不到文件 '{pdf_file_path}'")
        return 0.0
    if loader is None:
        print("正在初始化 Nougat OCR 模型 (首次运行可能需要下载模型)...")
        loader = PDFNougatOCR()
    start = time.perf_counter()
    docs = loader.load_data(pdf_file_path)
    if docs is None:
        print("【严重错误】Nougat 解析失败，未返回任何数据。")
        return 0.0
    write_docs_to_file(pdf_file_path, final_output_path, docs)
    elapsed_seconds = time.perf_counter() - start
    print("解析完成！")
    print(f"完整内容已保存在: {final_output_path}")
    print(f"单个 PDF 耗时: {elapsed_seconds:.2f}s")
    print("正在清理中间文件...")
    cleanup_nougat_temp_files(pdf_file_path)
    return elapsed_seconds


def iter_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def build_batch_output_path(output_root: Path, input_root: Path, pdf_path: Path, output_name: str) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root)
    return output_root / relative_parent / pdf_path.stem / output_name


def load_pdf_nougat_batch(input_dir: str | Path, output_root: str | Path, output_name: str, recursive: bool = True) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()
    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return
    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return
    print("正在初始化 Nougat OCR（批处理模式，仅初始化一次）...")
    loader = PDFNougatOCR()
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_nougat(pdf_path, output_path, loader=loader)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"发生错误: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / 累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nougat OCR PDF 解析工具")
    parser.add_argument("-i", "--input", type=str, default="../../PDF/Double_Layer/double_layer.pdf", help="输入 PDF 路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/NougatOCR.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("--output-name", type=str, default="NougatOCR.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()
    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        load_pdf_nougat_batch(input_path, args.output, args.output_name, recursive=args.recursive)
    else:
        load_pdf_nougat(args.input, args.output)


if __name__ == "__main__":
    main()
