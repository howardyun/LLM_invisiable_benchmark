from __future__ import annotations

import argparse
import time
from pathlib import Path

from haystack.components.converters import TikaDocumentConverter


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_docs_to_file(file_path: Path, output_path: Path, docs, tika_url: str) -> None:
    ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析结果 (Apache Tika): {file_path.name}\n"
            f"保存位置: {output_path}\n"
            f"文档数量: {len(docs)}\n"
            f"Tika Server: {tika_url}\n"
            f"{'=' * 30}\n\n"
        )
        file_obj.write(header)

        for index, doc in enumerate(docs, start=1):
            content = doc.content
            metadata_dict = doc.meta
            metadata_str = f"【文档 {index} 元数据 (Meta)】:\n"
            for key, value in metadata_dict.items():
                str_val = str(value)
                if len(str_val) > 100:
                    str_val = str_val[:100] + "..."
                metadata_str += f"  - {key}: {str_val}\n"
            full_output = f"{metadata_str}\n【正文内容】:\n{content}\n\n{'-' * 20}\n\n"
            file_obj.write(full_output)


def load_pdf_with_tika(input_path: str | Path, output_path: str | Path, tika_url: str, converter: TikaDocumentConverter | None = None) -> float:
    file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()

    print(f"输入文件: {file_path}")
    print(f"输出文件: {final_output_path}")
    print(f"Tika URL: {tika_url}")

    if not file_path.exists():
        print(f"错误：找不到文件 '{file_path}'")
        return 0.0

    if converter is None:
        print("正在连接本地 Tika Server 解析 PDF...")
        print("提示: Tika 擅长提取极其详细的文档元数据 (Metadata)。")
        converter = TikaDocumentConverter(tika_url=tika_url)

    start = time.perf_counter()
    docs = converter.run(sources=[file_path])["documents"]
    if not docs:
        print("警告: Tika 未提取到任何内容。")
        return 0.0

    write_docs_to_file(file_path, final_output_path, docs, tika_url)
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


def load_pdf_with_tika_batch(input_dir: str | Path, output_root: str | Path, output_name: str, tika_url: str, recursive: bool = True) -> None:
    input_root = Path(input_dir).resolve()
    final_output_root = Path(output_root).resolve()

    if not input_root.is_dir():
        print(f"错误：输入目录不存在 '{input_root}'")
        return

    pdf_files = iter_pdf_files(input_root, recursive)
    if not pdf_files:
        print(f"错误：目录下未找到 PDF 文件 '{input_root}'")
        return

    print("正在初始化 TikaDocumentConverter（批处理模式，仅初始化一次）...")
    converter = TikaDocumentConverter(tika_url=tika_url)
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_with_tika(pdf_path, output_path, tika_url, converter=converter)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"发生错误: {exc}")
            print("常见错误检查：请确认 Tika 服务和依赖均可用。")
            import traceback
            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(
                f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / 累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apache Tika (Haystack) 解析工具")
    parser.add_argument("-i", "--input", type=str, default="../../PDF/Zero_Width/text/zero_width.pdf", help="输入文件路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/TikaConverter.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("--url", type=str, default="http://localhost:9998/tika", help="Tika Server 地址")
    parser.add_argument("--output-name", type=str, default="TiKaDocumentConverter.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        load_pdf_with_tika_batch(input_path, args.output, args.output_name, args.url, recursive=args.recursive)
    else:
        load_pdf_with_tika(args.input, args.output, args.url)


if __name__ == "__main__":
    main()
