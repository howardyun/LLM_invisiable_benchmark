import os
import sys
from pathlib import Path

# 获取当前文件所在目录
current_dir = Path(__file__).parent

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter
import fitz


def find_keyword_positions_v2(pdf_path, keywords):
    """
    使用 PyMuPDF 内置搜索功能精确获取关键词坐标
    :param pdf_path: PDF文件路径
    :param keywords: 关键词列表
    :return: 关键词位置列表
    """
    doc = fitz.open(pdf_path)
    keyword_locations = []
    
    for page_num, page in enumerate(doc):
        for keyword in keywords:
            # search_for 直接返回该页面所有匹配项的 Rect 列表 [x0, y0, x1, y1]
            insts = page.search_for(keyword)
            for rect in insts:
                keyword_locations.append({
                    "page": page_num,
                    "keyword": keyword,
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "matched_text": keyword
                })
    doc.close()
    return keyword_locations


def create_image_pdf(image_pages, output_file):
    """
    创建包含多张图片的PDF文件（原始功能）
    :param image_pages: 列表，每个元素是 (image_path, page_num) 元组
    :param output_file: 输出PDF文件路径
    """
    c = canvas.Canvas(output_file, pagesize=letter)
    
    # 按页码排序
    sorted_image_pages = sorted(image_pages, key=lambda x: x[1])
    
    # 为每张图片创建对应的页面
    current_page = 1
    for image_path, page_num in sorted_image_pages:
        # 如果当前页码小于目标页码，创建空白页面
        while current_page < page_num:
            c.showPage()
            current_page += 1
        
        # 在目标页面添加图片
        c.drawImage(str(image_path), 50, 500, width=500, height=500)
        c.showPage()
        current_page += 1
    
    c.save()


def create_image_pdf_with_keywords(image_path, keyword_locations, output_file, padding=2, pdf_path=None):
    """
    根据精确坐标创建覆盖层
    :param image_path: 图片文件路径
    :param keyword_locations: 关键词位置列表
    :param output_file: 输出PDF文件路径
    :param padding: 覆盖区域的额外边距
    :param pdf_path: 原始PDF文件路径（用于获取页面尺寸）
    """
    # 获取原始 PDF 的页面尺寸（确保坐标系同步）
    doc = fitz.open(pdf_path)
    
    c = canvas.Canvas(output_file)
    
    # 按页码处理
    for page_num in range(len(doc)):
        page = doc[page_num]
        p_width = page.rect.width
        p_height = page.rect.height
        c.setPageSize((p_width, p_height))
        
        # 筛选当前页的关键词
        current_page_locs = [l for l in keyword_locations if l["page"] == page_num]
        
        for loc in current_page_locs:
            bbox = loc["bbox"]
            
            # 转换坐标系：PyMuPDF (x0, y0, x1, y1) -> ReportLab (x, y, w, h)
            # ReportLab 的 y = 页面总高度 - PyMuPDF 的 y1
            w = bbox[2] - bbox[0] + (2 * padding)
            h = bbox[3] - bbox[1] + (2 * padding)
            x = bbox[0] - padding
            y = p_height - bbox[3] - padding
            
            # 绘制图片，去除 preserveAspectRatio 以便完全覆盖文字矩形
            c.drawImage(str(image_path), x, y, width=w, height=h, mask='auto')
        
        c.showPage()
        
    c.save()
    doc.close()


def merge_pdfs_with_keyword_cover(text_pdf, image_path, keywords, output_file, padding=2):
    """
    使用图片覆盖文字层PDF中的关键词
    :param text_pdf: 文字层PDF文件路径
    :param image_path: 用于覆盖的图片文件路径
    :param keywords: 要覆盖的关键词列表
    :param output_file: 输出PDF文件路径
    :param padding: 覆盖区域的额外边距
    """
    # 使用内置引擎搜索关键词位置
    print("[+] 正在使用内置引擎搜索关键词位置...")
    keyword_locations = find_keyword_positions_v2(text_pdf, keywords)
    
    if not keyword_locations:
        print("[-] 未找到匹配的关键词")
        return False
    
    print(f"[+] 找到 {len(keyword_locations)} 个精确匹配点")
    
    # 创建临时图片层PDF
    temp_image_pdf = Path(text_pdf).parent / "temp_cover.pdf"
    create_image_pdf_with_keywords(image_path, keyword_locations, str(temp_image_pdf), padding, text_pdf)
    
    # 合并PDF
    print(f"[+] 正在合并PDF...")
    merge_pdfs(text_pdf, str(temp_image_pdf), output_file)
    
    # 删除临时文件
    if temp_image_pdf.exists():
        temp_image_pdf.unlink()
    
    print(f"[+] 关键词覆盖完成，输出文件: {output_file}")
    return True


# 合并两个PDF：一个是文字层，另一个是图片层
def merge_pdfs(text_pdf, image_pdf, output_file):
    reader_text = PdfReader(text_pdf)
    reader_image = PdfReader(image_pdf)

    writer = PdfWriter()

    # 获取文字层PDF的页数
    num_pages = len(reader_text.pages)

    # 遍历所有页面，进行合并
    for i in range(num_pages):
        # 获取文字层页面
        page_text = reader_text.pages[i]
        
        # 检查图片层PDF是否有对应的页面
        if i < len(reader_image.pages):
            page_image = reader_image.pages[i]
            # 合并页面：图片层在文字层之上
            page_text.merge_page(page_image)
        
        writer.add_page(page_text)

    # 写入输出文件
    with open(output_file, "wb") as f:
        writer.write(f)


# 只有当文件被直接执行时才运行以下代码
if __name__ == "__main__":
    print("===== 双层PDF生成工具 =====")
    print("该工具提供两种模式:")
    print("1. 传统模式: 将图片和文字层PDF合并为双层PDF文件")
    print("2. 关键词覆盖模式: 使用图片覆盖文字层PDF中的关键词")
    print()
    
    # 选择模式
    while True:
        mode_choice = input("请选择模式 (1/2): ").strip()
        if mode_choice in ['1', '2']:
            break
        print("错误: 请输入 1 或 2")
    
    print()
    
    if mode_choice == '1':
        # 传统模式
        print("===== 传统模式 =====")
        print("支持添加多张图片并指定每张图片对应的页码")
        print()
        
        # 交互式输入图片和页码
        image_pages = []
        while True:
            image_path_str = input("请输入图片文件路径 (输入 'done' 结束): ").strip()
            if image_path_str.lower() == "done":
                break
            
            if not image_path_str:
                print("错误: 图片路径不能为空，请重新输入")
                continue
            
            image_path = Path(image_path_str)
            if not image_path.exists():
                print(f"错误: 图片文件 '{image_path}' 不存在，请重新输入")
                continue
            
            # 输入页码
            while True:
                page_num_str = input(f"请输入 '{image_path.name}' 对应的页码: ").strip()
                if not page_num_str.isdigit():
                    print("错误: 页码必须是数字，请重新输入")
                    continue
                page_num = int(page_num_str)
                if page_num < 1:
                    print("错误: 页码必须大于等于 1，请重新输入")
                    continue
                break
            
            image_pages.append((image_path, page_num))
            print(f"已添加: {image_path.name} -> 第 {page_num} 页")
            print()
        
        # 检查是否添加了至少一张图片
        if not image_pages:
            print("错误: 至少需要添加一张图片，请重新运行程序")
            input("\n按回车键退出...")
            exit(1)
        
        print()
        
        # 交互式输入文字层PDF路径
        while True:
            text_pdf_path_str = input("请输入文字层PDF文件路径: ").strip()
            if not text_pdf_path_str:
                print("错误: 文字层PDF路径不能为空，请重新输入")
                continue
            
            text_pdf_path = Path(text_pdf_path_str)
            if not text_pdf_path.exists():
                print(f"错误: 文字层PDF文件 '{text_pdf_path}' 不存在，请重新输入")
                continue
            break
        
        print()
        
        # 交互式输入输出PDF路径（可选，有默认值）
        output_pdf_path_str = input("请输入输出PDF文件路径 (默认: merged_double_layer.pdf): ").strip()
        if not output_pdf_path_str:
            output_pdf_path = current_dir / "merged_double_layer.pdf"
            print(f"将使用默认输出路径: {output_pdf_path}")
        else:
            output_pdf_path = Path(output_pdf_path_str)
        
        print()
        print("正在处理...")
        print()
        
        # 创建临时图片层PDF
        temp_image_pdf = current_dir / "temp_image_layer.pdf"
        
        # 为图片创建PDF
        create_image_pdf(image_pages, str(temp_image_pdf))
        
        # 合并PDF
        merge_pdfs(str(text_pdf_path), str(temp_image_pdf), str(output_pdf_path))
        
        # 删除临时文件
        if temp_image_pdf.exists():
            temp_image_pdf.unlink()
        
        print("[+] 图片层PDF创建成功")
        print(f"[+] 使用的文字层PDF: {text_pdf_path}")
        print(f"[+] 合并后的PDF已保存到: {output_pdf_path}")
        print("[+] 任务完成！")
        
    else:
        # 关键词覆盖模式
        print("===== 关键词覆盖模式 =====")
        print("使用图片覆盖文字层PDF中的关键词")
        print()
        
        # 交互式输入文字层PDF路径
        while True:
            text_pdf_path_str = input("请输入文字层PDF文件路径: ").strip()
            if not text_pdf_path_str:
                print("错误: 文字层PDF路径不能为空，请重新输入")
                continue
            
            text_pdf_path = Path(text_pdf_path_str)
            if not text_pdf_path.exists():
                print(f"错误: 文字层PDF文件 '{text_pdf_path}' 不存在，请重新输入")
                continue
            break
        
        print()
        
        # 交互式输入图片路径
        while True:
            image_path_str = input("请输入用于覆盖的图片文件路径: ").strip()
            if not image_path_str:
                print("错误: 图片路径不能为空，请重新输入")
                continue
            
            image_path = Path(image_path_str)
            if not image_path.exists():
                print(f"错误: 图片文件 '{image_path}' 不存在，请重新输入")
                continue
            break
        
        print()
        
        # 交互式输入关键词
        keywords_input = input("请输入要覆盖的关键词 (逗号分隔): ").strip()
        if not keywords_input:
            print("错误: 关键词不能为空，请重新运行程序")
            input("\n按回车键退出...")
            exit(1)
        
        keywords = [k.strip() for k in keywords_input.split(',')]
        
        # 交互式输入padding
        padding_str = input("请输入覆盖区域的额外边距 (默认: 2): ").strip()
        padding = int(padding_str) if padding_str.isdigit() else 2
        
        print()
        
        # 交互式输入输出PDF路径（可选，有默认值）
        output_pdf_path_str = input("请输入输出PDF文件路径 (默认: keyword_covered.pdf): ").strip()
        if not output_pdf_path_str:
            output_pdf_path = current_dir / "keyword_covered.pdf"
            print(f"将使用默认输出路径: {output_pdf_path}")
        else:
            output_pdf_path = Path(output_pdf_path_str)
        
        print()
        print("正在处理...")
        print()
        
        # 执行关键词覆盖
        success = merge_pdfs_with_keyword_cover(
            str(text_pdf_path),
            str(image_path),
            keywords,
            str(output_pdf_path),
            padding
        )
        
        if success:
            print("[+] 任务完成！")
        else:
            print("[-] 任务失败，请检查输入参数")
    
    # 按任意键退出
    input("\n按回车键退出...")