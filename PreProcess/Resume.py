from pathlib import Path
from pathlib import Path
import shutil




# ====== 总目录 ======
ROOT_DIR = Path(r"../Data_Source/Resume/Resumes_PDF")

# ====== 是否只是预演 ======
# True = 只打印，不真正删除
# False = 真正执行删除
DRY_RUN = True

# ====== 常见图片后缀 ======
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"
}

PDF_EXT = ".pdf"


def process_folder(folder: Path):
    """
    处理单个子文件夹：
    - 删除图片
    - 统计PDF数量
    - 若文件夹为空则删除文件夹
    """
    deleted_images = 0
    pdf_count = 0

    # 只统计当前文件夹下的文件；如果你要递归处理子目录，可改成 rglob("*")
    for file in folder.iterdir():
        if file.is_file():
            suffix = file.suffix.lower()

            if suffix in IMAGE_EXTS:
                if DRY_RUN:
                    print(f"[预演] 删除图片: {file}")
                else:
                    file.unlink()
                    print(f"[已删除图片] {file}")
                deleted_images += 1

            elif suffix == PDF_EXT:
                pdf_count += 1

    # 删除图片后，检查文件夹是否为空
    remaining_items = list(folder.iterdir())
    folder_deleted = False

    if len(remaining_items) == 0:
        if DRY_RUN:
            print(f"[预演] 删除空文件夹: {folder}")
        else:
            folder.rmdir()
            print(f"[已删除空文件夹] {folder}")
        folder_deleted = True

    return {
        "folder": str(folder),
        "deleted_images": deleted_images,
        "pdf_count": pdf_count,
        "folder_deleted": folder_deleted,
    }
def merge_and_rename_pdfs(
    source_root,
    target_dir,
    prefix="Resume",
    digits=4,
    move_files=False
):
    """
    将 source_root 下所有 PDF 收集到 target_dir 中，
    并重命名为 prefix_0001.pdf 这类格式。

    参数：
    - source_root: 原始总目录
    - target_dir: 目标总文件夹
    - prefix: 重命名前缀，默认 Resume
    - digits: 编号位数，默认 4 -> 0001
    - move_files: False=复制，True=移动
    """
    source_root = Path(source_root)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 递归查找全部 PDF
    pdf_files = list(source_root.rglob("*.pdf")) + list(source_root.rglob("*.PDF"))

    # 排序，保证编号稳定
    pdf_files = sorted(set(pdf_files), key=lambda x: str(x).lower())

    if not pdf_files:
        print("没有找到 PDF 文件。")
        return

    print(f"共找到 {len(pdf_files)} 个 PDF 文件。")

    for idx, pdf_path in enumerate(pdf_files, start=1):
        new_name = f"{prefix}_{idx:0{digits}d}.pdf"
        new_path = target_dir / new_name

        if move_files:
            shutil.move(str(pdf_path), str(new_path))
        else:
            shutil.copy2(str(pdf_path), str(new_path))

        print(f"{pdf_path}  ->  {new_path}")

    print(f"\n处理完成，所有 PDF 已保存到：{target_dir}")


def main_delete_pic():
    if not ROOT_DIR.exists():
        print(f"目录不存在: {ROOT_DIR}")
        return

    results = []
    total_pdf = 0
    total_deleted_images = 0
    total_deleted_folders = 0

    # 只处理 ROOT_DIR 下的一级子文件夹
    for subfolder in ROOT_DIR.iterdir():
        if subfolder.is_dir():
            result = process_folder(subfolder)
            results.append(result)

            total_pdf += result["pdf_count"]
            total_deleted_images += result["deleted_images"]
            total_deleted_folders += int(result["folder_deleted"])

    print("\n" + "=" * 60)
    print("处理结果汇总")
    print("=" * 60)

    for r in results:
        print(
            f"文件夹: {r['folder']}\n"
            f"  删除图片数量: {r['deleted_images']}\n"
            f"  PDF数量: {r['pdf_count']}\n"
            f"  是否删除文件夹: {'是' if r['folder_deleted'] else '否'}\n"
        )

    print("=" * 60)
    print(f"总删除图片数: {total_deleted_images}")
    print(f"总PDF数: {total_pdf}")
    print(f"总删除文件夹数: {total_deleted_folders}")
    print("=" * 60)

def main_merge_PDFs(target_dir,prefix="Resume",digits = 4,move_files = False):
    merge_and_rename_pdfs(
        source_root=ROOT_DIR,
        target_dir=target_dir,
        prefix=prefix,
        digits=digits,
        move_files=move_files  # 先复制；确认无误后可改成 True
    )



if __name__ == "__main__":


    # 删除文件夹中多余的图片
    main_delete_pic()
    # 将所有的PDF都合成到一个大的文件夹当中
    main_merge_PDFs(target_dir='../Data_Source/Resume/Resumes_Merge',move_files = True)
        # 你的原始总目录




