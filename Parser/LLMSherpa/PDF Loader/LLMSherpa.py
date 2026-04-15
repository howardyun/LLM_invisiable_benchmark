from __future__ import annotations

import argparse
import time
from pathlib import Path

from llmsherpa.readers import LayoutPDFReader


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_chunks_to_file(pdf_file_path: Path, output_path: Path, chunks) -> None:
    ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析结果 (Native LLMSherpa): {pdf_file_path.name}\n"
            f"保存位置: {output_path}\n"
            f"解析出的块(Chunks)数量: {len(chunks)}\n"
            f"{'=' * 30}\n\n"
        )
        print(header)
        file_obj.write(header)
        for index, chunk in enumerate(chunks):
            content = chunk.to_context_text()
            metadata_dict = {
                "page_idx": chunk.page_idx,
                "level": chunk.level,
                "tag": chunk.tag,
                "block_idx": chunk.block_idx,
                "top": chunk.top,
                "left": chunk.left,
            }
            metadata_str = f"【块索引 (Chunk {index}) 元数据】:\n"
            for key, value in metadata_dict.items():
                metadata_str += f"  - {key}: {value}\n"
            file_obj.write(f"{metadata_str}\n【正文内容】:\n{content}\n\n{'-' * 20}\n\n")


def parse_pdf_with_reader(pdf_file_path: Path, pdf_reader: LayoutPDFReader):
    with pdf_file_path.open("rb") as file_obj:
        pdf_bytes = file_obj.read()
    doc = pdf_reader.read_pdf(str(pdf_file_path), contents=pdf_bytes)
    return doc.chunks()


def load_pdf(input_path: str | Path, output_path: str | Path, api_url: str, pdf_reader: LayoutPDFReader | None = None) -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()
    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    if not pdf_file_path.exists():
        print(f"错误：找不到文件 '{pdf_file_path}'")
        return 0.0
    if pdf_reader is None:
        print(f"正在通过原生 LayoutPDFReader ({api_url}) 解析 PDF...")
        pdf_reader = LayoutPDFReader(api_url)
    start = time.perf_counter()
    chunks = parse_pdf_with_reader(pdf_file_path, pdf_reader)
    write_chunks_to_file(pdf_file_path, final_output_path, chunks)
    elapsed_seconds = time.perf_counter() - start
    print("解析完成！")
    print(f"完整内容已保存在: {final_output_path}")
    print(f"单个 PDF 耗时: {elapsed_seconds:.2f}s")
    return elapsed_seconds


def iter_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def build_batch_output_path(output_root: Path, input_root: Path, pdf_path: Path, output_name: str) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root)
    return output_root / relative_parent / pdf_path.stem / output_name


def load_pdf_batch(input_dir: str | Path, output_root: str | Path, output_name: str, api_url: str, recursive: bool = True) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()
    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return
    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return
    print(f"正在初始化 LayoutPDFReader（批处理模式，仅初始化一次）: {api_url}")
    pdf_reader = LayoutPDFReader(api_url)
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf(pdf_path, output_path, api_url, pdf_reader=pdf_reader)
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
    parser = argparse.ArgumentParser(description="LLMSherpa 原生解析工具")
    parser.add_argument("-i", "--input", type=str, default="../../PDF/Zero_Size/font_0.pdf", help="输入 PDF 文件路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/zero_size/font_0/SherpaResult.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("--api", type=str, default="http://localhost:5001/api/parseDocument?renderFormat=all", help="API 地址")
    parser.add_argument("--output-name", type=str, default="SherpaResult.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()
    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        load_pdf_batch(input_path, args.output, args.output_name, args.api, recursive=args.recursive)
    else:
        load_pdf(args.input, args.output, args.api)


if __name__ == "__main__":
    main()
