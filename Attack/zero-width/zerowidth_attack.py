import fitz  # PyMuPDF
import random
import os

class ZeWInjector:
    def __init__(self, target_words):
        """
        :param target_words: 需要进行注入攻击的关键词列表（不区分大小写）
        """
        # 论文中常用的零宽字符
        self.zew_chars = [
            '\u200B', # Zero Width Space
            '\u200C', # Zero Width Non-Joiner
            '\u200D', # Zero Width Joiner
            '\uFEFF'  # Zero Width No-Break Space
        ]
        # 将目标词转为小写集合，方便快速匹配
        self.target_words = set(word.lower() for word in target_words)

    def inject_word(self, word, mask_type='mask2'):
        """执行零宽字符注入"""
        # 如果单词长度太短或不在目标列表中，不进行处理
        if len(word) < 2 or word.lower() not in self.target_words:
            return word

        char_to_inject = random.choice(self.zew_chars)
        
        if mask_type == 'mask1':
            # Mask1: 仅在单词正中间插入一个字符
            mid = len(word) // 2
            return word[:mid] + char_to_inject + word[mid:]
        
        else:
            # Mask2: 在每个字母之间均匀插入字符
            return char_to_inject.join(list(word))

    def process_pdf(self, input_path, output_path, mask_type='mask2'):
        """处理PDF并在指定位置注入字符"""
        doc = fitz.open(input_path)
        out_doc = fitz.open()

        for page in doc:
            # 获取页面上的所有单词及其坐标
            words = page.get_text("words") 
            new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            
            # 使用标准字体，确保PDF渲染正常
            font = "helv" 
            
            for w in words:
                x0, y0, x1, y1, text, block_no, line_no, word_no = w
                
                # 检查当前词是否在攻击名单中
                processed_text = self.inject_word(text, mask_type)
                
                # 在相同位置重新写入文本
                # y1-2 是为了微调基线位置，使其看起来与原版一致
                new_page.insert_text((x0, y1-2), processed_text, fontsize=11, fontname=font)

        out_doc.save(output_path)
        out_doc.close()
        doc.close()
        print(f"成功！已针对 {len(self.target_words)} 个关键词生成注入后的PDF: {output_path}")

# ================= 使用示例 =================
if __name__ == "__main__":
    # 1. 定义你想要"隐藏"或"破坏"的关键词列表
    my_targets = ["Apple", "Machine", "Intelligence", "Security", "Attack","this"]

    # 2. 初始化注入器
    injector = ZeWInjector(target_words=my_targets)

    # 3. 获取用户输入的PDF路径
    input_pdf = input("请输入PDF文件路径: ").strip()
    output_pdf = input("请输入输出PDF文件路径 (留空则默认保存在同一文件夹下): ").strip()

    # 如果输出路径为空，则生成默认输出路径
    if not output_pdf:
        # 获取输入文件所在目录和文件名
        input_dir = os.path.dirname(input_pdf)
        input_filename = os.path.basename(input_pdf)
        # 分离文件名和扩展名
        name, ext = os.path.splitext(input_filename)
        # 生成新的输出文件名，添加_injected后缀
        output_filename = f"{name}_injected{ext}"
        # 如果输入路径没有目录，则直接使用文件名
        if input_dir:
            output_pdf = os.path.join(input_dir, output_filename)
        else:
            output_pdf = output_filename
        print(f"输出路径未指定，默认保存为: {output_pdf}")

    # 4. 执行处理
    injector.process_pdf(input_pdf, output_pdf, mask_type='mask2')