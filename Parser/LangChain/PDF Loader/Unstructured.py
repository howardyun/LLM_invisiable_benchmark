from __future__ import annotations

import argparse
import time
from pathlib import Path

from langchain_unstructured import UnstructuredLoader


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_docs_to_file(pdf_file_path: Path, final_output_path: Path, docs) -> None:
    ensure_parent_dir(final_output_path)
    with final_output_path.open("w", encoding="utf-8") as file_obj:
        header = (
            f"本地解析结果 (Unstructured Local): {pdf_file_path.name}\n"
            f"输出位置: {final_output_path}\n"
            f"识别元素数量: {len(docs)}\n"
            f"解析策略: \n"
            f"{'=' * 30}\n\n"
        )
        file_obj.write(header)

        for index, doc in enumerate(docs, start=1):
            content = doc.page_content
            metadata = doc.metadata
            category = metadata.get("category", "Unknown")
            page_num = metadata.get("page_number", "?")

            metadata_str = "【元数据】:\n"
            for key, value in metadata.items():
                metadata_str += f"  - {key}: {value}\n"

            element_info = f"--- Element {index} [页码: {page_num} | 类型: {category}] ---\n"
            full_text = f"{element_info}{metadata_str}【内容】:\n{content}\n\n"
            file_obj.write(full_text)


def load_pdf_local(input_path: str | Path, output_path: str | Path, strategy: str = "fast") -> float:
    pdf_file_path = Path(input_path).resolve()
    final_output_path = Path(output_path).resolve()

    print(f"输入文件: {pdf_file_path}")
    print(f"输出文件: {final_output_path}")
    print(f"解析策略: {strategy}")

    if not pdf_file_path.exists():
        print(f"错误：找不到文件 '{pdf_file_path}'")
        return 0.0

    print("正在进行本地解析 (Local Parsing)...")
    print("提示: 本地解析通常依赖 Poppler 和 Tesseract，如缺失会报错")

    start = time.perf_counter()
    docs = UnstructuredLoader(
        str(pdf_file_path),
        strategy=strategy,
    ).load()
    write_docs_to_file(pdf_file_path, final_output_path, docs)
    elapsed_seconds = time.perf_counter() - start
    print(f"本地解析完成，文件已保存: {final_output_path}")
    print(f"单个 PDF 耗时: {elapsed_seconds:.2f}s")
    return elapsed_seconds


def iter_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def build_batch_output_path(output_root: Path, input_root: Path, pdf_path: Path, output_name: str) -> Path:
    relative_parent = pdf_path.parent.relative_to(input_root)
    return output_root / relative_parent / pdf_path.stem / output_name


def load_pdf_local_batch(
    input_dir: str | Path,
    output_root: str | Path,
    output_name: str,
    strategy: str = "fast",
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

    print("进入 Unstructured 批处理模式（复用同一 Python 进程）...")
    total = len(pdf_files)
    success_count = 0
    failed_count = 0
    total_elapsed_seconds = 0.0
    for index, pdf_path in enumerate(pdf_files, start=1):
        output_path = build_batch_output_path(final_output_root, input_root, pdf_path, output_name)
        print(f"[{index}/{total}] 解析: {pdf_path}")
        try:
            elapsed_seconds = load_pdf_local(pdf_path, output_path, strategy=strategy)
            success_count += 1
            total_elapsed_seconds += elapsed_seconds
        except ImportError:
            failed_count += 1
            print("错误: 缺少必要 Python 库。请检查 unstructured 相关依赖")
        except Exception as exc:
            failed_count += 1
            print(f"解析失败: {pdf_path} -> {exc}")
            if "poppler" in str(exc).lower() or "tesseract" in str(exc).lower():
                print("提示: 可能缺少 Poppler 或 Tesseract 系统依赖")
            import traceback

            traceback.print_exc()
        finally:
            average_seconds = total_elapsed_seconds / success_count if success_count else 0.0
            print(
                f"当前进度: 成功 {success_count} / 失败 {failed_count} / 总计 {total} / "
                f"累计耗时 {total_elapsed_seconds:.2f}s / 平均耗时 {average_seconds:.2f}s"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Unstructured PDF 解析器")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="../PDF/Word_Shift/pdf_poc.pdf",
        help="输入 PDF 文件路径，或批处理目录路径",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="Output/word_shift/UnstructuredLoader_fast.txt",
        help="单文件模式输出 txt 路径；目录模式输出根目录",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="fast",
        choices=["fast", "hi_res", "ocr_only"],
        help="解析策略: fast, hi_res, ocr_only",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="UnstructuredLoader_fast.txt",
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
            load_pdf_local_batch(
                input_path,
                args.output,
                output_name=args.output_name,
                strategy=args.strategy,
                recursive=args.recursive,
            )
        else:
            load_pdf_local(args.input, args.output, args.strategy)
    except ImportError:
        print("错误: 缺少必要的 Python 库。请执行: pip install 'langchain-unstructured[local]'")
    except Exception as exc:
        print(f"处理失败: {exc}")
        if "poppler" in str(exc).lower() or "tesseract" in str(exc).lower():
            print("提示: 请确认已安装 Poppler 和 Tesseract")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
