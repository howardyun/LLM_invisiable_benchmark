from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from langchain_opendataloader_pdf import OpenDataLoaderPDFLoader


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_docs_to_file(pdf_file_path: Path, final_output_path: Path, docs) -> None:
    ensure_parent_dir(final_output_path)
    with final_output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"文件解析结果 (OpenDataLoader): {pdf_file_path.name}\n"
            f"保存位置: {final_output_path}\n"
            f"文档片段数: {len(docs)}\n"
            f"特点: 本地 Java 引擎，重构文档布局(Markdown)，内置 AI 安全过滤。\n"
            f"{'=' * 30}\n\n"
        )
        file_obj.write(header)

        for doc in docs:
            content = doc.page_content
            metadata_dict = doc.metadata
            metadata_str = "【元数据 (Metadata)】:\n"
            for key, value in metadata_dict.items():
                metadata_str += f"  - {key}: {value}\n"

            full_output = f"{metadata_str}\n【Markdown 内容】:\n{content}\n\n"
            file_obj.write(full_output)


def load_pdf_with_opendataloader(input_path: str | Path, output_path: str | Path, safety_mode: str = "default") -> float:
    if not shutil.which("java"):
        print("【错误】：未检测到 Java 环境。")
        print("OpenDataLoader 需要 Java 11+ 才能运行。请安装 Java 并将其添加到 PATH 环境变量。")
        return 0.0

    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()

    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    print(f"安全过滤模式: {safety_mode}")

    if not pdf_file_path.exists():
        print(f"错误：找不到文件 '{pdf_file_path}'")
        return 0.0

    print("正在使用 OpenDataLoader 解析 PDF...")
    print("提示: OpenDataLoader 在本地运行，具备 AI 安全过滤功能。")

    loader_params = {
        "file_path": [str(pdf_file_path)],
        "format": "markdown",
    }
    if safety_mode != "default":
        loader_params["content_safety_off"] = [safety_mode]
        print(f"【配置】已禁用安全过滤: {loader_params['content_safety_off']}")
    else:
        print("【配置】使用默认安全过滤策略")

    start = time.perf_counter()
    docs = OpenDataLoaderPDFLoader(**loader_params).load()
    write_docs_to_file(pdf_file_path, final_output_path, docs)
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


def load_pdf_with_opendataloader_batch(
    input_dir: str | Path,
    output_root: str | Path,
    output_name: str,
    safety_mode: str = "default",
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

    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_with_opendataloader(pdf_path, output_path, safety_mode=safety_mode)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except Exception as exc:
            failed_count += 1
            print(f"发生错误: {exc}")
            if "java" in str(exc).lower():
                print("提示: 这很可能是 Java 环境配置问题，请确保 `java -version` 在终端能正常运行。")
            import traceback
            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(
                f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / "
                f"累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenDataLoader PDF 解析工具")
    parser.add_argument("-i", "--input", type=str, default="../PDF/Word_Shift/pdf_poc.pdf", help="输入 PDF 文件路径，或批处理目录路径")
    parser.add_argument("-o", "--output", type=str, default="Output/word_shift/OpenDataLoader_all.txt", help="单文件模式输出 txt 路径；目录模式输出根目录")
    parser.add_argument("--safety", type=str, default="default", choices=["default", "all", "hidden-text", "off-page", "tiny", "hidden-ocg"], help="控制 content_safety_off 模式")
    parser.add_argument("--output-name", type=str, default="OpenDataLoader.txt", help="目录批处理模式下，每个 PDF 的输出文件名")
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True, help="目录模式下是否递归扫描 PDF，默认递归")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if input_path.is_dir():
        load_pdf_with_opendataloader_batch(
            input_path,
            args.output,
            args.output_name,
            safety_mode=args.safety,
            recursive=args.recursive,
        )
    else:
        load_pdf_with_opendataloader(args.input, args.output, args.safety)


if __name__ == "__main__":
    main()
