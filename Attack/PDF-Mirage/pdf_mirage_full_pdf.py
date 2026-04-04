import sys
import os
import argparse
from shutil import copyfile
from pathlib import Path

try:
    import fitz
except ImportError:
    print("[-] 需要安装PyMuPDF库来提取PDF文本")
    print("[-] 请运行: pip install PyMuPDF")
    sys.exit(1)

punctuation = {
    "!": "Exclam",
    "\"": "Quotedbl",
    "#": "Numbersign",
    "$": "Dollar",
    "%": "Percent",
    "&": "Ampersand",
    "\'": "Quotesingle",
    "(": "Parenleft",
    ")": "Parenright",
    "*": "Asterisk",
    "+": "Plus",
    ",": "Comma",
    "-": "Minus",
    ".": "Period",
    "/": "Slash",
    ":": "Colon",
    ";": "Semicolon",
    "<": "Less",
    ">": "Greater",
    "=": "Equal",
    "?": "Question",
    "@": "At",
    "[": "Bracketleft",
    "]": "Bracketright",
    "\\": "Backslash",
    "^": "Asciicircum"
}

class PDFMirageFullPDF:
    def __init__(self, input_pdf, under_text, output_dir=None):
        self.input_pdf = input_pdf
        self.under_text = under_text
        self.output_dir = output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_full")
        self.src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
        self.fonts_dir = os.path.join(self.src_dir, "fonts")
        
        self.under_words = []
        self.show_words = []
        self.latex_text = []
        self.used_fonts = []
        
    def extract_text_from_pdf(self):
        """从PDF中提取文本作为显示内容"""
        doc = fitz.open(self.input_pdf)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        show_words = []
        for line in text.splitlines():
            for word in line.split():
                show_words.append(word)
        
        return show_words
    
    def parse_under_text(self):
        """解析隐藏文本"""
        under_words = []
        for line in self.under_text.splitlines():
            for word in line.split():
                under_words.append(word)
        return under_words
    
    def get_font_name(self, char):
        """获取字符对应的字体文件名"""
        if char in punctuation:
            return punctuation[char]
        if char.isupper():
            return char + char
        return char
    
    def append_word_and_font(self, under_char, show_char, case):
        """生成LaTeX代码片段并跟踪使用的字体"""
        tmp_code = ""
        if case == "c1":
            font_name = self.get_font_name(show_char)
            tmp_code += r"\cus" + font_name + r"{" + under_char + "}"
            if font_name not in self.used_fonts:
                self.used_fonts.append(font_name)
        elif case == "c2":
            font_name = self.get_font_name(show_char)
            tmp_code += r"\cus" + font_name + r"{\_}"
            if font_name not in self.used_fonts:
                self.used_fonts.append(font_name)
        elif case == "c3":
            tmp_code += r"\cusempty{" + under_char + "}"
            if "empty" not in self.used_fonts:
                self.used_fonts.append("empty")
        return tmp_code
    
    def pair_two_words(self, under_word, show_word):
        """配对两个单词，处理字符长度不一致的情况"""
        latex_code = r"\RemoveSpaces{"
        if len(under_word) < len(show_word):
            for i in range(len(show_word)):
                if i < len(under_word):
                    latex_code += self.append_word_and_font(under_word[i], show_word[i], "c1")
                else:
                    latex_code += self.append_word_and_font("", show_word[i], "c2")
        else:
            for i in range(len(under_word)):
                if i < len(show_word):
                    latex_code += self.append_word_and_font(under_word[i], show_word[i], "c1")
                else:
                    latex_code += self.append_word_and_font(under_word[i], "", "c3")
        latex_code += r"}"
        self.latex_text.append(latex_code)
    
    def hide_under_word(self, word):
        """隐藏整个单词"""
        latex_code = r"\RemoveSpaces{"
        for char in word:
            latex_code += self.append_word_and_font(char, "", "c3")
        latex_code += r"}"
        self.latex_text.append(latex_code)
    
    def show_word_only(self, word):
        """只显示单词，没有隐藏内容"""
        latex_code = r"\RemoveSpaces{"
        for char in word:
            latex_code += self.append_word_and_font("", char, "c2")
        latex_code += r"}"
        self.latex_text.append(latex_code)
    
    def pair_texts(self):
        """配对显示文本和隐藏文本"""
        if len(self.show_words) < len(self.under_words):
            idx = 0
            for i in range(len(self.show_words)):
                idx += 1
                self.pair_two_words(self.under_words[i], self.show_words[i])
            for i in range(len(self.under_words) - idx):
                self.hide_under_word(self.under_words[i + idx])
        else:
            idx = 0
            for i in range(len(self.under_words)):
                idx += 1
                self.pair_two_words(self.under_words[i], self.show_words[i])
            for i in range(len(self.show_words) - idx):
                self.show_word_only(self.show_words[i + idx])
    
    def setup_output_dir(self):
        """设置输出目录"""
        if os.path.exists(self.output_dir):
            import shutil
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir)
        
        copyfile(os.path.join(self.src_dir, "doc.tex"), os.path.join(self.output_dir, "doc.tex"))
        copyfile(os.path.join(self.fonts_dir, "T1-WGL4.enc"), os.path.join(self.output_dir, "T1-WGL4.enc"))
    
    def copy_fonts(self):
        """复制需要的字体文件"""
        for font in self.used_fonts:
            font_src = os.path.join(self.fonts_dir, font + ".ttf")
            font_dst = os.path.join(self.output_dir, font + ".ttf")
            if os.path.exists(font_src):
                copyfile(font_src, font_dst)
            else:
                print(f"[-] 警告: 字体文件 {font}.ttf 不存在，使用empty字体代替")
                empty_src = os.path.join(self.fonts_dir, "empty.ttf")
                copyfile(empty_src, font_dst)
    
    def generate_font_descriptions(self):
        """生成字体描述文件(.fd)"""
        for font in self.used_fonts:
            fd_content = (
                r"\ProvidesFile{T1" + font + r".fd}" + "\n" +
                r"\DeclareFontFamily{T1}{" + font + r"}{}" + "\n" +
                r"\DeclareFontShape{T1}{" + font + r"}{m}{n}{ <-> " + font + r"}{}" + "\n" +
                r"\pdfmapline{+" + font + r" <" + font + r".ttf <T1-WGL4.enc}" + "\n"
            )
            fd_path = os.path.join(self.output_dir, "T1" + font + ".fd")
            with open(fd_path, "w", encoding="utf-8") as f:
                f.write(fd_content)
    
    def convert_fonts_to_tfm(self):
        """使用ttf2tfm将TTF字体转换为TFM格式"""
        original_cwd = os.getcwd()
        try:
            os.chdir(self.output_dir)
            for font in self.used_fonts:
                cmd = f"ttf2tfm {font}.ttf -p T1-WGL4.enc"
                os.system(cmd)
        finally:
            os.chdir(original_cwd)
    
    def generate_latex_document(self):
        """生成完整的LaTeX文档"""
        latex_code = ""
        
        for font in self.used_fonts:
            latex_code += (
                r"\newcommand{\cus" + font + r"}[1]{{\fontencoding{T1}\fontfamily{" +
                font + r"}\selectfont #1}}" + "\n"
            )
        
        latex_code += r"\begin{document}" + "\n"
        for i in self.latex_text:
            latex_code += i + " "
        latex_code += r"\end{document}" + "\n"
        
        doc_path = os.path.join(self.output_dir, "doc.tex")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(latex_code)
    
    def compile_pdf(self):
        """使用pdflatex编译生成PDF"""
        original_cwd = os.getcwd()
        try:
            os.chdir(self.output_dir)
            os.system("pdflatex -interaction=nonstopmode doc.tex")
        finally:
            os.chdir(original_cwd)
    
    def run(self):
        """运行完整的PDF-Mirage攻击流程"""
        print("[+] 从原始PDF提取显示文本...")
        self.show_words = self.extract_text_from_pdf()
        print(f"[+] 提取了 {len(self.show_words)} 个单词")
        
        print("[+] 解析隐藏文本...")
        self.under_words = self.parse_under_text()
        print(f"[+] 隐藏文本包含 {len(self.under_words)} 个单词")
        
        print("[+] 配对文本...")
        self.pair_texts()
        
        print("[+] 设置输出目录...")
        self.setup_output_dir()
        
        print("[+] 复制字体文件...")
        self.copy_fonts()
        
        print("[+] 生成字体描述文件...")
        self.generate_font_descriptions()
        
        print("[+] 转换字体格式 (ttf2tfm)...")
        self.convert_fonts_to_tfm()
        
        print("[+] 生成LaTeX文档...")
        self.generate_latex_document()
        
        print("[+] 编译PDF...")
        self.compile_pdf()
        
        output_pdf = os.path.join(self.output_dir, "doc.pdf")
        if os.path.exists(output_pdf):
            print(f"[+] PDF-Mirage攻击完成!")
            print(f"[+] 输出文件: {output_pdf}")
        else:
            print("[-] PDF编译失败，请检查LaTeX环境")


def main():
    parser = argparse.ArgumentParser(description="PDF-Mirage: 直接使用PDF作为显示内容的字体映射攻击")
    parser.add_argument("-i", "--input", required=True, help="输入PDF文件路径")
    parser.add_argument("-u", "--under", required=True, help="隐藏内容（文本提取时得到）")
    parser.add_argument("-o", "--output", help="输出目录（可选）")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"[-] 错误: 输入PDF文件 '{args.input}' 不存在")
        sys.exit(1)
    
    under_text = args.under
    
    attacker = PDFMirageFullPDF(args.input, under_text, args.output)
    attacker.run()


if __name__ == "__main__":
    main()
