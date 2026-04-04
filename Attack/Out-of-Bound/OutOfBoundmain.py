# oob_text_poc.py
#
# 运行后会生成两个文件：
#   - oob_poc_base.pdf  : 添加了越界隐藏文本的原始 PDF（未裁剪）
#   - oob_poc_cropped.pdf : 带“越界隐藏文本”的 PoC（可见区被裁剪）

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import red

from pypdf import PdfReader, PdfWriter  # 如果你装的是 PyPDF2，则改为 from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO


def add_hidden_text_to_pdf(input_pdf_path: str, output_pdf_path: str, target_page: int = None):
    """
    读取用户传入的原始 PDF，并添加越界隐藏文本：
    - 保留原始 PDF 的所有内容
    - 添加一行"Out-of-Bound"隐藏文本（画在页面可见区域之外）
    
    Args:
        input_pdf_path: 输入PDF文件路径
        output_pdf_path: 输出PDF文件路径
        target_page: 目标页码（从0开始），如果为None则对所有页面进行攻击
    """
    # 读取原始 PDF
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    
    # 确定要处理的页面范围
    if target_page is not None:
        # 只处理指定页面
        page_range = [target_page]
    else:
        # 处理所有页面
        page_range = range(len(reader.pages))
    
    # 遍历页面
    for page_num in page_range:
        # 检查页码是否有效
        if page_num >= len(reader.pages):
            print(f"警告: 页码 {page_num} 超出范围，跳过")
            continue
        
        # 获取当前页面
        page = reader.pages[page_num]
        
        # 获取页面尺寸
        media_box = page.mediabox
        page_width = media_box.width
        page_height = media_box.height
        
        # 创建一个临时画布来绘制隐藏文本
        temp_canvas = BytesIO()
        c = canvas.Canvas(temp_canvas, pagesize=(page_width, page_height))
        
        # 越界隐藏文本（Out-of-Bound Text）
        # 思路：把文字画在“正常阅读区域”上方，比如 y 坐标远大于页面高度
        # 很多 PDF viewer 会把它裁掉，但解析工具仍然能读到。
        hidden_text = (
            "HIDDEN and invisible."
        )
        # 故意设置一个“超出页面高度”的 y 坐标，比如页面高度+300pt
        c.setFont("Helvetica", 12)
        c.setFillColorRGB(1, 0, 0)  # 颜色无所谓，只是便于调试（看不见就无所谓了）
        c.drawString(30 * mm, page_height + 300, hidden_text)
        
        # 你也可以加更多“超边界”的内容，比如在右侧超宽处：
        hidden_text_right = "EXTRA ANOTHER HIDDEN OOB TEXT placed far to the right."
        c.drawString(page_width + 300, 200 * mm, hidden_text_right)
        
        c.showPage()
        c.save()
        
        # 将临时画布的内容添加到原始页面
        temp_canvas.seek(0)
        hidden_text_pdf = PdfReader(temp_canvas)
        
        # 合并页面内容
        writer.add_page(page)
        writer.pages[page_num].merge_page(hidden_text_pdf.pages[0])
    
    # 保存添加了隐藏文本的 PDF
    with open(output_pdf_path, "wb") as output_file:
        writer.write(output_file)


def crop_pdf_to_hide_oob_text(input_pdf: str, output_pdf: str, target_page: int = None):
    """
    使用 pypdf / PyPDF2 修改 CropBox：
    - MediaBox 保持原始尺寸（内容都在）
    - CropBox 缩小，只显示页面中间一块，可见内容只剩"正常文字"
    - 越界文本虽然在内容流里，但被裁出可见区域
    
    Args:
        input_pdf: 输入PDF文件路径
        output_pdf: 输出PDF文件路径
        target_page: 目标页码（从0开始），如果为None则对所有页面进行裁剪
    """
    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    # 确定要处理的页面范围
    if target_page is not None:
        # 只处理指定页面
        page_range = [target_page]
    else:
        # 处理所有页面
        page_range = range(len(reader.pages))

    # 遍历页面
    for page_num in page_range:
        # 检查页码是否有效
        if page_num >= len(reader.pages):
            print(f"警告: 页码 {page_num} 超出范围，跳过")
            continue
        
        page = reader.pages[page_num]

        # 取原始页面尺寸（单位：pt）
        media_box = page.mediabox
        x0, y0, x1, y1 = media_box

        # 你可以根据需要调整“可见区域”大小，这里示例：仅保留下方 2/3 的区域
        # 也可以直接手动给一个 crop 区域，比如 (0, 0, 595, 600)
        new_y1 = y1 * 0.7  # 上方 30% 的内容被裁掉（包括我们塞在更上方的隐藏文本）

        # 设置 CropBox：指定“可见的矩形区域”
        page.cropbox.lower_left = (x0, y0)
        page.cropbox.upper_right = (x1, new_y1)

        writer.add_page(page)

    with open(output_pdf, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    # 获取用户输入的原始 PDF 文件路径
    input_pdf_path = input("请输入原始 PDF 文件的路径：").strip()
    
    # 定义输出文件名，与 README.md 中描述的一致
    base_pdf = "oob_poc_base.pdf"
    cropped_pdf = "oob_poc_cropped.pdf"

    # 1. 读取用户传入的 PDF 并添加越界隐藏文本
    add_hidden_text_to_pdf(input_pdf_path, base_pdf)
    print(f"[+] Created base PDF with OOB text: {base_pdf}")

    # 2. 修改 CropBox，形成真正的 Out-of-Bound Text PoC
    crop_pdf_to_hide_oob_text(base_pdf, cropped_pdf)
    print(f"[+] Created cropped PoC PDF with OOB text: {cropped_pdf}")
    
    print("\n[+] 任务完成！已生成以下文件：")
    print(f"   - {base_pdf}: 基础 PDF 文件，包含正常文本和越界隐藏文本")
    print(f"   - {cropped_pdf}: 裁剪后的 PDF 文件，只显示正常文本，隐藏越界文本")





