from __future__ import annotations

import argparse
import time
from pathlib import Path

from llama_index.readers.pdf_table import PDFTableReader


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_docs_to_file(pdf_file_path: Path, output_path: Path, docs, pages: str) -> None:
    ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析结果 (PDFTableReader): {pdf_file_path.name}\n"
            f"保存位置: {output_path}\n"
            f"页码范围: {pages}\n"
            f"提取到的表格数量: {len(docs)}\n"
            f"{'=' * 30}\n\n"
        )
        print(header)
        file_obj.write(header)
        if len(docs) == 0:
            msg = "【警告】未在指定页面检测到表格。请检查页码范围或确认PDF是否包含可选中的表格层。\n"
            print(msg)
            file_obj.write(msg)
        for index, doc in enumerate(docs):
            content = doc.text
            metadata_dict = doc.metadata
            metadata_str = f"【表格 (Table {index}) 元数据】:\n"
            if metadata_dict:
                for key, value in metadata_dict.items():
                    metadata_str += f"  - {key}: {value}\n"
            else:
                metadata_str += "  - (无元数据)\n"
            file_obj.write(f"{metadata_str}\n【表格内容】:\n{content}\n\n{'-' * 20}\n\n")


def load_pdf_table(input_path: str | Path, output_path: str | Path, pages: str, loader: PDFTableReader | None = None) -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()
    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    print(f"目标页码范围: {pages}")
    if not pdf_file_path.exists():
        print(f"错误：找不到文件 '{pdf_file_path}'")
        return 0.0
    if loader is None:
        print("正在初始化 PDFTableReader...")
        loader = PDFTableReader()
    start = time.perf_counter()
    docs = loader.load_data(file=pdf_file_path, pages=pages)
    write_docs_to_file(pdf_file_path, final_output_path, docs, pages)
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


def load_pdf_table_batch(input_dir: str | Path, output_root: str | Path, output_name: str, pages: str, recursive: bool = True) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()
    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return
    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return
    print("正在初始化 PDFTableReader（批处理模式，仅初始化一次）...")
    loader = PDFTableReader()
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_table(pdf_path, output_path, pages, loader=loader)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"发生错误: {exc}")
            print("提示: 此加载器通常依赖系统安装 Ghostscript，请检查是否已安装该环境。")
            import traceback
            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / 累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF Table 解析工具 (提取 PDF 中的表格)")
    parser.add_argument("-i", "--input", type=str, default="../../PDF/Double_Layer/double_layer.pdf", help="输入 PDF 路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/PDFTable.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("-p", "--pages", type=str, default="all", help="页码范围 (例如: 'all', '1', '1,3,5', '10-20')")
    parser.add_argument("--output-name", type=str, default="PDFTable.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()
    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        load_pdf_table_batch(input_path, args.output, args.output_name, args.pages, recursive=args.recursive)
    else:
        load_pdf_table(args.input, args.output, args.pages)


if __name__ == "__main__":
    main()
