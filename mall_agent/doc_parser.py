import os
import json


def parse_file(file_path: str) -> str:
    if not file_path:
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in (".txt", ".md", ".csv", ".json"):
            return _parse_text(file_path)
        elif ext == ".pdf":
            return _parse_pdf(file_path)
        elif ext in (".xlsx", ".xls"):
            return _parse_excel(file_path)
        elif ext in (".docx", ".doc"):
            return _parse_docx(file_path)
        else:
            return f"[不支持的文件格式: {ext}]"
    except Exception as e:
        return f"[解析文件失败: {str(e)}]"


def parse_files(file_paths: list) -> str:
    chunks = []
    for fp in file_paths:
        content = parse_file(fp)
        if content:
            name = os.path.basename(fp)
            chunks.append(f"=== 文件: {name} ===\n{content}")
    return "\n\n".join(chunks)


def _parse_text(file_path: str) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(file_path, "r", encoding=enc) as f:
                text = f.read()
            return text[:8000]
        except UnicodeDecodeError:
            continue
    return "[无法识别文件编码]"


def _parse_pdf(file_path: str) -> str:
    import pdfplumber
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
    text = "\n".join(pages)
    return text[:8000] if text else "[PDF 未检测到文本内容]"


def _parse_excel(file_path: str) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    sheets = []
    for sheet in wb.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            sheets.append(f"-- Sheet: {sheet.title} --\n" + "\n".join(rows))
    text = "\n\n".join(sheets)
    return text[:8000] if text else "[Excel 未检测到数据]"


def _parse_docx(file_path: str) -> str:
    try:
        import docx
        doc = docx.Document(file_path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paras)
        return text[:8000] if text else "[Word 文档未检测到文本]"
    except ImportError:
        return "[需要安装 python-docx 才能解析 .docx 文件]"
