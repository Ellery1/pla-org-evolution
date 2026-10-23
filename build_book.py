#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《中国人民解放军编制史》HTML 生成器。

读取 01_~09_ 共 9 个 Markdown 章节文件，合并为单页 HTML。

特性：
- 左侧固定目录（编→章→节），滚动时自动高亮当前章节
- 点击正文任意位置，左侧目录自动定位并高亮所在章节
- 编制结构图以 <pre> 代码块呈现（保持原始缩进）
- 人事表格以 HTML <table> 呈现
- 脚注可点击跳转 / 返回
- 底部悬浮工具栏：字号 / 行距 / 字体 / 主题
- 虚线边框 + 拖拽调节内容区宽度
- 阅读位置记忆
- 响应式 + 移动端汉堡菜单
- 打印样式
- 暗色模式
"""

import os
import re
import markdown
from html import escape
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_DIR, "中国人民解放军编制变迁史.html")
BOOK_TITLE = "中国人民解放军编制变迁史：从南昌起义到新时代"

# 按文件名排序读取所有章节
MD_FILES = sorted([
    f for f in os.listdir(PROJECT_DIR)
    if f.endswith('.md') and f[:2].isdigit()
])


# ============================================================
# 人物简介数据库
# 从 人物简介.md 读取，格式为每行 "人名|简介"
# ## 标题行决定人物归属哪一章（按章标题中的"第X章"匹配）
# ============================================================

FIGURE_BIO_FILE = os.path.join(PROJECT_DIR, "人物简介.md")


def load_figure_bio():
    """从 人物简介.md 加载人物数据库。
    返回:
        bio_dict: {人名: 简介}
        chapter_groups: {章关键词: [人名, ...]}  按出现顺序
    章关键词从 ## 标题中提取，如 "## 第六章 其他苏区红军" → "第六章"
    """
    bio_dict = {}
    chapter_groups = {}
    current_chapter = None

    with open(FIGURE_BIO_FILE, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('>'):
                continue
            # # 一级标题忽略（文件标题）
            if line.startswith('# ') and not line.startswith('## '):
                continue
            # ## 章节标题 → 提取章关键词
            if line.startswith('## '):
                title = line[3:].strip()
                # 提取 "第X章" 或 "第XX章"
                m = re.search(r'第.{1,4}章', title)
                if m:
                    current_chapter = m.group(0)
                    if current_chapter not in chapter_groups:
                        chapter_groups[current_chapter] = []
                continue
            # 人物条目
            if '|' in line and current_chapter:
                parts = line.split('|', 1)
                name = parts[0].strip()
                desc = parts[1].strip()
                if name and desc:
                    bio_dict[name] = desc
                    chapter_groups[current_chapter].append(name)

    return bio_dict, chapter_groups


FIGURE_BIO, CHAPTER_GROUPS = load_figure_bio()

# 已输出过的人物集合，跨章节全局追踪（防止同一人在多章重复出现时重复输出）
_introduced_figures = set()


def build_figure_bio_html(chapter_title):
    """为一个章节构建人物简介 HTML。
    根据章标题中的"第X章"匹配 人物简介.md 中的分组。
    已输出过的人物不再重复。
    """
    global _introduced_figures

    # 从章标题提取 "第X章"
    m = re.search(r'第.{1,4}章', chapter_title)
    if not m:
        return ""
    chapter_key = m.group(0)

    names = CHAPTER_GROUPS.get(chapter_key, [])
    # 过滤掉已输出过的
    new_names = [n for n in names if n not in _introduced_figures]
    if not new_names:
        return ""

    for n in new_names:
        _introduced_figures.add(n)

    rows = []
    for name in new_names:
        bio = FIGURE_BIO[name]
        rows.append(f'<tr><td class="bio-name">{escape(name)}</td><td>{escape(bio)}</td></tr>')

    return (
        '<div class="figure-bio-box">'
        '<h4>本章人物简介</h4>'
        '<table class="bio-table"><tbody>'
        + ''.join(rows)
        + '</tbody></table></div>'
    )


# ============================================================
# 解析 Markdown 文件，提取目录结构
# ============================================================

def parse_toc_from_md(md_text, file_idx):
    """从 markdown 提取 h1~h3 标题，生成 TOC 条目列表。
    返回 [(level, title, anchor_id), ...]
    """
    toc = []
    h_counter = 0
    for line in md_text.split('\n'):
        m = re.match(r'^(#{1,3})\s+(.+)', line.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            anchor_id = f"f{file_idx}-h{h_counter}"
            toc.append((level, title, anchor_id))
            h_counter += 1
    return toc


def split_into_chapters(md_text):
    """将一个编的 markdown 按 ## 章标题分割为多个片段。
    返回 [(chapter_lines, is_preamble), ...]
    第一个片段可能是编标题 + 编级内容（在第一个 ## 之前），is_preamble=True。
    后续每个片段以 ## 开头，is_preamble=False。
    """
    lines = md_text.split('\n')
    chunks = []
    current_chunk = []

    for line in lines:
        # 检测 ## 章标题（不含 ### 及以上）
        if re.match(r'^##\s+[^#]', line):
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [line]
        else:
            current_chunk.append(line)

    if current_chunk:
        chunks.append(current_chunk)

    # 标记第一个片段：如果不以 ## 开头，就是前言（编标题等）
    result = []
    for i, chunk in enumerate(chunks):
        is_preamble = (i == 0 and not re.match(r'^##\s+[^#]', chunk[0]))
        result.append((chunk, is_preamble))

    return result


def process_chapter_section(lines, file_idx, h_counter_start, chapter_sec_idx):
    """处理一个章节片段（可能是前言或一个完整章），返回 (html, h_counter_end)。
    脚注在本片段内闭合，ID 用 f{file_idx}-s{chapter_sec_idx}-fn-{num} 确保唯一。
    """
    fn_prefix = f"f{file_idx}-s{chapter_sec_idx}"

    processed_lines = []
    in_code_block = False
    h_counter = h_counter_start

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            processed_lines.append(line)
            continue

        if not in_code_block:
            m = re.match(r'^(#{1,4})\s+(.+)', line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                anchor_id = f"f{file_idx}-h{h_counter}"
                h_counter += 1
                tag = f'h{level}'
                processed_lines.append(f'<{tag} id="{anchor_id}">{escape(title)}</{tag}>')
                continue

        processed_lines.append(line)

    text = '\n'.join(processed_lines)

    # 处理脚注引用 [^N] → 上标链接（仅在非脚注定义行）
    def fn_ref_replace(m):
        num = m.group(1)
        return (f'<sup class="fn-ref">'
                f'<a href="#{fn_prefix}-fn-{num}" id="{fn_prefix}-fnref-{num}">[{num}]</a>'
                f'</sup>')

    result_lines = []
    for line in text.split('\n'):
        if re.match(r'^\[\^[\d\*]+\]:', line.strip()):
            result_lines.append(line)
        else:
            line = re.sub(r'\[\^(\d+)\]', fn_ref_replace, line)
            result_lines.append(line)

    text = '\n'.join(result_lines)

    # 分离脚注定义和正文
    footnotes = []
    body_lines = []
    for line in text.split('\n'):
        m = re.match(r'^\[\^(\d+)\]:\s*(.+)', line.strip())
        if m:
            footnotes.append((m.group(1), m.group(2)))
        elif re.match(r'^\[\^\*\]', line.strip()):
            # 存疑脚注 [*]
            m2 = re.match(r'^\[\^\*\]\s*(.+)', line.strip())
            if m2:
                footnotes.append(('*', m2.group(1)))
        else:
            # 过滤掉 MD 原文中的 **注释** 标题行（脚本会自动生成"参考文献"）
            stripped_line = line.strip()
            if stripped_line in ('**注释**', '注释', '**参考文献**', '参考文献'):
                continue
            if re.match(r'^(\*{1,2})?注释(\*{1,2})?\s*$', stripped_line):
                continue
            body_lines.append(line)

    body_md = '\n'.join(body_lines)
    html = markdown.markdown(
        body_md,
        extensions=['tables', 'fenced_code', 'sane_lists'],
    )

    # 后处理：为表格中"类别合并"行添加CSS class
    # 第一列td为空的行 → class="row-merged"（隐藏上边框）
    # 第一列td非空、但下一行第一列为空 → class="row-group-start"（隐藏下边框）
    import re as _re
    def _add_row_classes(table_html):
        rows = _re.findall(r'<tr>(.*?)</tr>', table_html, _re.DOTALL)
        if not rows:
            return table_html
        new_rows = []
        for i, row in enumerate(rows):
            tds = _re.findall(r'<td>(.*?)</td>', row, _re.DOTALL)
            if not tds:
                new_rows.append(f'<tr>{row}</tr>')
                continue
            first_td = tds[0].strip()
            is_empty = first_td == '' or first_td == '&nbsp;'
            # 看下一行
            next_empty = False
            if i + 1 < len(rows):
                next_tds = _re.findall(r'<td>(.*?)</td>', rows[i + 1], _re.DOTALL)
                if next_tds and (next_tds[0].strip() == '' or next_tds[0].strip() == '&nbsp;'):
                    next_empty = True
            if is_empty:
                new_rows.append(f'<tr class="row-merged">{row}</tr>')
            elif next_empty:
                new_rows.append(f'<tr class="row-group-start">{row}</tr>')
            else:
                new_rows.append(f'<tr>{row}</tr>')
        result = table_html
        for old, new in zip(
            [f'<tr>{r}</tr>' for r in rows],
            new_rows
        ):
            result = result.replace(old, new, 1)
        return result

    html = _re.sub(r'<table>.*?</table>', lambda m: _add_row_classes(m.group()), html, flags=_re.DOTALL)

    # 构建脚注区
    if footnotes:
        fn_html = '<div class="footnotes"><h4>参考文献</h4><ol>'
        for num, text_content in footnotes:
            if num == '*':
                fn_html += f'<li style="list-style-type:none">[*] {escape(text_content)}</li>'
            else:
                fn_html += (
                    f'<li id="{fn_prefix}-fn-{num}" value="{num}">'
                    f'{escape(text_content)} '
                    f'<a href="#{fn_prefix}-fnref-{num}" class="fn-back" title="返回正文">↩</a>'
                    f'</li>'
                )
        fn_html += '</ol></div>'
        html += fn_html

    return html, h_counter


def process_markdown(md_text, file_idx):
    """将一个编的 markdown 转换为 HTML。
    按章（##）分割，每章独立处理脚注，使注释紧跟章末而非编末。
    非前言章节在脚注之后追加人物简介。
    """
    chapters = split_into_chapters(md_text)
    html_parts = []
    h_counter = 0

    for sec_idx, (chapter_lines, is_preamble) in enumerate(chapters):
        chapter_html, h_counter = process_chapter_section(
            chapter_lines, file_idx, h_counter, sec_idx
        )
        # 为非前言章节追加人物简介
        if not is_preamble:
            raw_text = '\n'.join(chapter_lines)
            bio_html = build_figure_bio_html(raw_text)
            if bio_html:
                chapter_html += bio_html
        html_parts.append(chapter_html)

    return '\n'.join(html_parts)


# ============================================================
# 构建侧边栏目录
# ============================================================

def build_sidebar_toc(all_toc_entries):
    """构建侧边栏 HTML。all_toc_entries = [(file_idx, level, title, anchor_id), ...]"""
    items = []
    all_section_anchors = []  # 用于滚动高亮

    for file_idx, level, title, anchor_id in all_toc_entries:
        if level == 1:
            # 编 (h1) → 大标题
            items.append(
                f'<li class="toc-part" data-anchor="{anchor_id}">'
                f'<a href="#{anchor_id}">{escape(title)}</a></li>'
            )
            all_section_anchors.append(anchor_id)
        elif level == 2:
            # 章 (h2)
            items.append(
                f'<li class="toc-chapter" data-anchor="{anchor_id}">'
                f'<a href="#{anchor_id}">{escape(title)}</a></li>'
            )
            all_section_anchors.append(anchor_id)
        elif level == 3:
            # 节 (h3)
            items.append(
                f'<li class="toc-section" data-anchor="{anchor_id}">'
                f'<a href="#{anchor_id}">{escape(title)}</a></li>'
            )
            all_section_anchors.append(anchor_id)

    return '\n'.join(items), all_section_anchors


# ============================================================
# 主生成函数
# ============================================================

def generate_html():
    global _introduced_figures
    _introduced_figures = set()  # 每次生成时重置

    all_toc_entries = []
    all_content_parts = []

    for file_idx, filename in enumerate(MD_FILES):
        filepath = os.path.join(PROJECT_DIR, filename)
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            md_text = f.read()

        # 提取目录
        toc_entries = parse_toc_from_md(md_text, file_idx)
        for level, title, anchor_id in toc_entries:
            all_toc_entries.append((file_idx, level, title, anchor_id))

        # 转换为 HTML
        html = process_markdown(md_text, file_idx)

        all_content_parts.append(f'''
        <section class="chapter-card" id="card-{file_idx}">
            {html}
        </section>''')

    content_html = '\n'.join(all_content_parts)
    toc_html, all_anchors = build_sidebar_toc(all_toc_entries)
    all_anchors_json = '[' + ', '.join(f'"{a}"' for a in all_anchors) + ']'

    gen_date = datetime.now().strftime('%Y年%m月%d日')

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(BOOK_TITLE)}</title>

    <style>
        :root {{
            --bg-page: #faf8f5;
            --bg-card: #fffef9;
            --bg-sidebar: #f3efe8;
            --bg-code: #1e1e2e;
            --bg-code-inline: #efeae0;
            --bg-blockquote: #fdf9ed;
            --bg-table-head: #e8e2d3;
            --bg-table-alt: #f9f6f0;
            --bg-header-start: #1a3a4a;
            --bg-header-end: #1e5668;
            --bg-toc-active: rgba(30, 86, 104, 0.10);
            --toc-active-color: #1e5668;

            --color-text: #333333;
            --color-heading: #1a1a2e;
            --color-secondary: #777777;
            --color-accent: #1e5668;
            --color-accent-light: #2a7a8a;
            --color-gold: #1e5668;
            --color-link: #1e5668;
            --color-link-hover: #144052;
            --color-border: #d8d2c5;
            --color-blockquote-border: #1e5668;
            --color-code-text: #e0e0e0;
            --color-tag-bg: #e8f0f4;
            --color-tag-text: #1e5668;

            --font-body: "KaiTi", "STKaiti", "楷体", "Noto Serif SC", "Songti SC", serif;
            --font-heading: "SimHei", "STHeiti", "黑体", "PingFang SC", "Microsoft YaHei", sans-serif;
            --font-code: "Fira Code", "JetBrains Mono", "Consolas", "Courier New", monospace;

            --sidebar-width: 220px;
            --content-max-width: 860px;
            --font-size-body: 17px;
            --line-height-body: 1.95;
            --letter-spacing-body: 0.03em;
            --card-radius: 12px;
            --card-shadow: 0 2px 16px rgba(0, 0, 0, 0.06);
            --transition: 0.3s ease;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-page: #1a1a2e;
                --bg-card: #232340;
                --bg-sidebar: #1e1e36;
                --bg-code: #0d0d1a;
                --bg-code-inline: #2a2a48;
                --bg-blockquote: #2a2840;
                --bg-table-head: #2a2a48;
                --bg-table-alt: #1f1f38;
                --bg-header-start: #0d1f2a;
                --bg-header-end: #142a36;
                --bg-toc-active: rgba(46, 150, 180, 0.15);
                --toc-active-color: #5cb8d4;
                --color-text: #c8c8d8;
                --color-heading: #e0e0f0;
                --color-secondary: #8888a8;
                --color-border: #3a3a58;
                --color-blockquote-border: #4a8a9a;
                --color-link: #5cb8d4;
                --color-link-hover: #7cc8e0;
                --color-tag-bg: #223344;
                --color-tag-text: #7cc8e0;
            }}
        }}

        body.theme-paper {{
            --bg-page: #fdfaf3; --bg-card: #ffffff; --bg-sidebar: #f7f3ea;
            --bg-header-start: #3a2f28; --bg-header-end: #5a4030;
            --color-accent: #5a3c1e; --color-gold: #8b6914;
            --color-link: #5a3c1e; --color-link-hover: #8b4513;
            --color-blockquote-border: #8b6914;
            --bg-toc-active: rgba(139, 105, 20, 0.12); --toc-active-color: #8b6914;
        }}
        body.theme-sepia {{
            --bg-page: #f4ecd8; --bg-card: #faf3e0; --bg-sidebar: #ede0c8;
            --bg-header-start: #3a3020; --bg-header-end: #504830;
            --color-text: #4a3a28; --color-heading: #2a1a08; --color-secondary: #8a7a60;
            --color-accent: #6b4a1e; --color-link: #6b4a1e; --color-link-hover: #8b5a2e;
            --color-blockquote-border: #8a7a4a; --color-border: #c8b898;
            --bg-toc-active: rgba(107, 74, 30, 0.10); --toc-active-color: #6b4a1e;
        }}
        body.theme-dark {{
            --bg-page: #1a1a2e !important; --bg-card: #232340 !important;
            --bg-sidebar: #1e1e36 !important; --bg-code: #0d0d1a !important;
            --bg-code-inline: #2a2a48 !important; --bg-blockquote: #2a2840 !important;
            --bg-table-head: #2a2a48 !important; --bg-table-alt: #1f1f38 !important;
            --bg-header-start: #0d1f2a !important; --bg-header-end: #142a36 !important;
            --bg-toc-active: rgba(46, 150, 180, 0.15) !important; --toc-active-color: #5cb8d4 !important;
            --color-text: #c8c8d8 !important; --color-heading: #e0e0f0 !important;
            --color-secondary: #8888a8 !important; --color-border: #3a3a58 !important;
            --color-blockquote-border: #4a8a9a !important;
            --color-link: #5cb8d4 !important; --color-link-hover: #7cc8e0 !important;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; scroll-padding-top: 30px; }}
        body {{
            font-family: var(--font-body); background: var(--bg-page); color: var(--color-text);
            font-size: var(--font-size-body); line-height: var(--line-height-body);
            letter-spacing: var(--letter-spacing-body);
            -webkit-font-smoothing: antialiased;
        }}

        .page-header {{
            background: linear-gradient(135deg, var(--bg-header-start) 0%, var(--bg-header-end) 100%);
            padding: 60px 20px 50px; text-align: center;
        }}
        .page-header h1 {{
            font-family: var(--font-heading); font-size: 2.2em; font-weight: 800;
            background: linear-gradient(135deg, #e8c860 0%, #f0e0a0 50%, #e8c860 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; letter-spacing: 0.08em; margin-bottom: 12px;
        }}
        .page-header .subtitle {{
            color: rgba(255,255,255,0.65); font-size: 0.95em; letter-spacing: 0.1em;
        }}
        .chapter-card .sign-meta {{
            margin-top: 14px; text-align: center; text-indent: 0;
            color: var(--color-secondary); font-size: 0.9em; letter-spacing: 0.1em;
        }}

        .layout {{ display: flex; align-items: flex-start; }}

        /* 侧边栏 */
        #sidebar {{
            position: sticky; top: 0; width: var(--sidebar-width); height: 100vh;
            background: var(--bg-sidebar); border-right: 1px solid var(--color-border);
            overflow-y: auto; flex-shrink: 0; z-index: 100; transition: transform var(--transition);
        }}
        #sidebar::-webkit-scrollbar {{ width: 5px; }}
        #sidebar::-webkit-scrollbar-thumb {{ background: #c0b8a0; border-radius: 3px; }}
        .sidebar-header {{ padding: 24px 16px 16px; border-bottom: 1px solid var(--color-border); }}
        .sidebar-header h2 {{
            font-family: var(--font-heading); font-size: 16px; color: var(--color-heading);
            letter-spacing: 0.05em;
        }}
        .toc-nav {{ padding: 8px 0 60px; }}
        .toc-nav ul {{ list-style: none; }}

        .toc-part {{
            padding: 14px 14px 6px; font-size: 13px; font-weight: 700;
            font-family: var(--font-heading); color: var(--color-accent);
            letter-spacing: 1px; border-top: 1px solid var(--color-border);
            margin-top: 6px;
        }}
        .toc-part:first-child {{ border-top: none; margin-top: 0; }}
        .toc-part a {{
            color: var(--color-accent); text-decoration: none;
        }}
        .toc-part a:hover {{ text-decoration: underline; }}

        .toc-chapter {{
            position: relative;
        }}
        .toc-chapter > a {{
            display: block; padding: 3px 14px 3px 20px; font-size: 13px; font-weight: 600;
            color: var(--color-heading); text-decoration: none;
            transition: all 0.15s ease; border-left: 3px solid transparent;
            line-height: 1.5; font-family: var(--font-body);
        }}
        .toc-chapter > a:hover {{
            background: var(--bg-toc-active); color: var(--toc-active-color);
        }}
        .toc-chapter.active > a {{
            background: var(--bg-toc-active); border-left-color: var(--toc-active-color);
            color: var(--toc-active-color); font-weight: 700;
        }}

        .toc-section > a {{
            display: block; padding: 2px 14px 2px 32px; font-size: 12px;
            color: var(--color-secondary); text-decoration: none;
            transition: all 0.15s ease; border-left: 3px solid transparent;
            line-height: 1.5; font-family: var(--font-body);
        }}
        .toc-section > a:hover {{
            background: var(--bg-toc-active); color: var(--toc-active-color);
        }}
        .toc-section.active > a {{
            background: var(--bg-toc-active); border-left-color: var(--toc-active-color);
            color: var(--toc-active-color); font-weight: 600;
        }}

        /* 主内容 */
        #main {{ flex: 1; padding: 30px 0 80px; min-width: 0; }}
        .content-wrapper {{
            width: var(--content-max-width); min-width: 360px; max-width: 95vw;
            margin: 0 auto; padding: 0 40px; position: relative;
            border-left: 2px dashed var(--color-border); border-right: 2px dashed var(--color-border);
            border-bottom: 2px dashed var(--color-border);
            border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
        }}
        .drag-handle {{
            position: absolute; top: 0; right: -12px; width: 24px; height: 100%;
            cursor: ew-resize; z-index: 10; background: transparent;
        }}
        .drag-handle::after {{
            content: ""; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
            width: 3px; height: 60px; border-radius: 2px;
            background: var(--color-secondary); opacity: 0.2; transition: opacity 0.2s;
        }}
        .content-wrapper:hover .drag-handle::after, .drag-handle:active::after {{ opacity: 0.6; }}

        /* 章节卡片 */
        .chapter-card {{
            background: var(--bg-card); border-radius: var(--card-radius);
            box-shadow: var(--card-shadow); padding: 36px 40px; margin-bottom: 30px;
            scroll-margin-top: 20px;
        }}

        .chapter-card h1 {{
            font-family: var(--font-heading); font-size: 1.7em; font-weight: 800;
            color: var(--color-heading); line-height: 1.4;
            padding-bottom: 14px; margin-bottom: 24px;
            border-bottom: 2px solid var(--color-gold); letter-spacing: 0.02em;
        }}
        .chapter-card h2 {{
            font-family: var(--font-heading); font-size: 1.3em; font-weight: 700;
            color: var(--color-heading); margin-top: 40px; margin-bottom: 14px; line-height: 1.5;
        }}
        .chapter-card h3 {{
            font-family: var(--font-heading); font-size: 1.1em; font-weight: 700;
            color: var(--color-accent); margin-top: 28px; margin-bottom: 10px;
        }}
        .chapter-card h4 {{
            font-family: var(--font-heading); font-size: 1em; font-weight: 700;
            color: var(--color-heading); margin-top: 20px; margin-bottom: 8px;
        }}

        .chapter-card p {{
            margin-bottom: 1.1em; text-align: justify;
            line-height: var(--line-height-body); text-indent: 2em;
        }}
        .chapter-card blockquote p, .chapter-card li p, .chapter-card pre p {{ text-indent: 0; }}

        .chapter-card blockquote {{
            background: var(--bg-blockquote); border-left: 4px solid var(--color-blockquote-border);
            margin: 20px 0; padding: 14px 22px; border-radius: 0 6px 6px 0;
        }}
        .chapter-card blockquote p:last-child {{ margin-bottom: 0; }}

        .chapter-card table {{
            width: 100%; border-collapse: collapse; margin: 20px 0;
            font-size: 0.9em; border-radius: 6px; overflow: hidden;
        }}
        .chapter-card thead {{ background: var(--bg-table-head); }}
        .chapter-card th {{
            padding: 10px 14px; text-align: left; font-weight: 700;
            font-family: var(--font-heading); color: var(--color-heading);
            border-bottom: 2px solid var(--color-border); white-space: nowrap;
        }}
        .chapter-card td {{
            padding: 8px 14px; border-bottom: 1px solid var(--color-border);
        }}
        .chapter-card td:empty {{
            border-bottom: none;
        }}
        .chapter-card tr.row-merged td {{
            border-top: none;
        }}
        .chapter-card tr.row-group-start td {{
            border-bottom: none;
        }}
        .chapter-card tbody tr:nth-child(even) {{ background: var(--bg-table-alt); }}

        .chapter-card ul, .chapter-card ol {{ margin: 12px 0 18px 0; padding-left: 28px; }}
        .chapter-card li {{ margin-bottom: 5px; line-height: 1.85; }}

        .chapter-card code {{
            font-family: var(--font-code); font-size: 0.85em;
            background: var(--bg-code-inline); color: #c0392b; padding: 2px 5px; border-radius: 3px;
        }}
        .chapter-card pre {{
            background: var(--bg-code); border-radius: 8px; padding: 16px 18px;
            overflow-x: auto; margin: 18px 0; font-size: 0.82em; line-height: 1.6;
        }}
        .chapter-card pre code {{
            background: none; color: var(--color-code-text); padding: 0; border-radius: 0;
        }}

        .chapter-card hr {{ border: none; text-align: center; margin: 32px 0; }}
        .chapter-card hr::after {{
            content: '· · ·'; color: var(--color-gold); font-size: 1.2em; letter-spacing: 0.5em;
        }}

        .chapter-card a {{ color: var(--color-link); text-decoration: none; border-bottom: 1px dashed var(--color-link); }}
        .chapter-card a:hover {{ color: var(--color-link-hover); border-bottom-style: solid; }}
        .chapter-card strong {{ font-weight: 700; color: var(--color-heading); }}

        /* 脚注 */
        .fn-ref a {{
            color: var(--color-accent); text-decoration: none; font-size: 0.8em;
            border-bottom: none;
        }}
        .fn-ref a:hover {{ text-decoration: underline; }}
        .footnotes {{
            border-top: 1px solid var(--color-border); margin-top: 32px; padding-top: 16px;
        }}
        .footnotes h4 {{
            font-family: var(--font-heading); font-size: 0.95em; color: var(--color-secondary);
            margin-bottom: 10px;
        }}
        .footnotes ol {{
            padding-left: 28px; font-size: 0.85em; color: var(--color-secondary);
            line-height: 1.7;
        }}
        .footnotes li {{ margin-bottom: 4px; scroll-margin-top: 20px; }}
        .fn-back {{
            color: var(--color-accent); text-decoration: none; font-size: 0.9em; border-bottom: none !important;
        }}

        /* 人物简介卡片 */
        .figure-bio-box {{
            margin-top: 28px; padding: 18px 22px 14px;
            background: var(--bg-blockquote); border-radius: 8px;
            border: 1px solid var(--color-border);
        }}
        .figure-bio-box h4 {{
            font-family: var(--font-heading); font-size: 0.95em;
            color: var(--color-accent); margin-bottom: 12px; letter-spacing: 0.05em;
        }}
        .bio-table {{
            width: 100%; border-collapse: collapse; font-size: 0.88em;
            margin: 0 !important;
        }}
        .bio-table td {{
            padding: 6px 10px; border-bottom: 1px solid var(--color-border);
            vertical-align: top; line-height: 1.7;
        }}
        .bio-table tr:last-child td {{ border-bottom: none; }}
        .bio-name {{
            white-space: nowrap; font-weight: 700; color: var(--color-heading);
            width: 5.5em; font-family: var(--font-heading);
        }}

        /* 页脚 */
        .page-footer {{
            background: var(--bg-sidebar); border-top: 1px solid var(--color-border);
            padding: 30px 20px; text-align: center; font-size: 0.82em;
            color: var(--color-secondary); line-height: 1.8;
        }}
        .page-footer p {{ margin: 4px 0; }}

        /* 回到顶部 */
        #back-to-top {{
            position: fixed; bottom: 60px; right: 30px; width: 44px; height: 44px;
            background: linear-gradient(135deg, #1e5668 0%, #144052 100%);
            color: #fff; border: none; border-radius: 50%; font-size: 20px;
            cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.2); z-index: 90;
            opacity: 0; visibility: hidden; transition: all var(--transition);
            display: flex; align-items: center; justify-content: center;
        }}
        #back-to-top.visible {{ opacity: 1; visibility: visible; }}
        #back-to-top:hover {{ transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,0,0,0.3); }}

        /* 底部工具栏 */
        #reading-bar {{
            position: fixed; bottom: 0; left: 0; right: 0; height: 44px;
            background: var(--bg-card); border-top: 1px solid var(--color-border);
            display: flex; align-items: center; justify-content: center; gap: 2px;
            z-index: 95; padding: 0 12px; box-shadow: 0 -2px 8px rgba(0,0,0,0.05);
        }}
        #reading-bar button {{
            height: 32px; padding: 0 12px; border: 1px solid var(--color-border);
            background: var(--bg-card); color: var(--color-text); font-size: 13px;
            font-family: var(--font-heading); cursor: pointer; border-radius: 4px;
            transition: all 0.15s; white-space: nowrap;
        }}
        #reading-bar button:hover {{
            background: var(--bg-toc-active); color: var(--toc-active-color);
            border-color: var(--toc-active-color);
        }}
        #reading-bar .rb-sep {{ width: 1px; height: 20px; background: var(--color-border); margin: 0 4px; }}
        #reading-bar .rb-label {{ font-size: 11px; color: var(--color-secondary); font-family: var(--font-heading); padding: 0 4px; }}

        /* 移动端 */
        #menu-toggle {{
            display: none; position: fixed; top: 14px; left: 14px; z-index: 150;
            background: var(--color-accent); color: #fff; border: none; border-radius: 6px;
            padding: 8px 14px; font-size: 14px; cursor: pointer;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}
        #overlay {{
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.4); z-index: 99;
        }}
        #overlay.visible {{ display: block; }}

        @media (max-width: 768px) {{
            .content-wrapper {{ padding: 0 24px; }}
            .chapter-card {{ padding: 28px 26px; }}
            .page-header h1 {{ font-size: 1.8em; }}
            #reading-bar button {{ font-size: 11px; padding: 0 8px; }}
        }}
        @media (max-width: 480px) {{
            :root {{ --font-size-body: 15px; }}
            #menu-toggle {{ display: block; }}
            #sidebar {{
                position: fixed; top: 0; left: 0; transform: translateX(-100%);
                width: 80%; max-width: 300px; z-index: 110;
            }}
            #sidebar.open {{ transform: translateX(0); }}
            .content-wrapper {{ padding: 0 12px; }}
            .chapter-card {{ padding: 20px 16px; border-radius: 8px; }}
            .chapter-card h1 {{ font-size: 1.5em; }}
            .page-header {{ padding: 50px 16px 36px; }}
            .page-header h1 {{ font-size: 1.5em; }}
            #reading-bar {{ gap: 0; padding: 0 4px; }}
            #reading-bar button {{ font-size: 10px; padding: 0 6px; }}
            #reading-bar .rb-label {{ display: none; }}
        }}

        @media print {{
            #sidebar, #back-to-top, #menu-toggle, #overlay, #reading-bar {{ display: none !important; }}
            .layout {{ display: block; }}
            #main {{ padding: 0; }}
            .content-wrapper {{ max-width: 100%; padding: 0; border: none; }}
            .chapter-card {{ box-shadow: none; border-radius: 0; page-break-inside: avoid; }}
            .page-header {{ background: none; color: #000; padding: 20px 0; }}
            .page-header h1 {{ -webkit-text-fill-color: #000; color: #000; }}
        }}
    </style>
</head>
<body>

    <header class="page-header">
        <h1>{escape(BOOK_TITLE)}</h1>
    </header>

    <button id="menu-toggle">☰ 目录</button>
    <div id="overlay"></div>

    <div class="layout">
        <nav id="sidebar">
            <div class="sidebar-header"><h2>目 录</h2></div>
            <div class="toc-nav"><ul>{toc_html}</ul></div>
        </nav>

        <div id="main">
            <div class="content-wrapper" id="drag-container">
                {content_html}
                <div class="drag-handle" id="drag-handle"></div>
            </div>
            <footer class="page-footer">
                <p><strong>{escape(BOOK_TITLE)}</strong></p>
                <p>作者：Ellery ｜ 版本：v1.0 ｜ 时间：2026-10-05</p>
                <p>生成于 {gen_date}</p>
                <p>全书内容基于公开出版文献与官方报道</p>
            </footer>
        </div>
    </div>

    <button id="back-to-top" title="回到顶部">↑</button>

    <div id="reading-bar">
        <span class="rb-label">字号</span>
        <button data-act="font-">A−</button>
        <span class="rb-label" id="rb-fs-label">17px</span>
        <button data-act="font+">A＋</button>
        <span class="rb-sep"></span>
        <span class="rb-label">行距</span>
        <button data-act="lh-">−</button>
        <span class="rb-label" id="rb-lh-label">1.95</span>
        <button data-act="lh+">＋</button>
        <span class="rb-sep"></span>
        <button data-act="font" id="rb-font">字体·楷体</button>
        <span class="rb-sep"></span>
        <button data-act="theme" id="rb-theme">主题·跟随系统</button>
    </div>

    <script>
        // 移动端菜单
        var menuToggle = document.getElementById('menu-toggle');
        var sidebar = document.getElementById('sidebar');
        var overlay = document.getElementById('overlay');
        function openMenu() {{ sidebar.classList.add('open'); overlay.classList.add('visible'); }}
        function closeMenu() {{ sidebar.classList.remove('open'); overlay.classList.remove('visible'); }}
        menuToggle.addEventListener('click', openMenu);
        overlay.addEventListener('click', closeMenu);
        document.querySelectorAll('#sidebar a').forEach(function(link) {{
            link.addEventListener('click', function() {{
                if (window.innerWidth <= 480) closeMenu();
            }});
        }});

        // 回到顶部
        var backToTop = document.getElementById('back-to-top');
        window.addEventListener('scroll', function() {{
            backToTop.classList.toggle('visible', window.pageYOffset > 400);
        }});
        backToTop.addEventListener('click', function() {{
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }});

        // 目录高亮
        var allAnchors = {all_anchors_json};
        var anchorElements = allAnchors.map(function(id) {{
            return document.getElementById(id);
        }}).filter(function(el) {{ return el !== null; }});

        var tocItems = document.querySelectorAll('.toc-part, .toc-chapter, .toc-section');

        // 让高亮项在侧边栏中可见：只滚动侧边栏自身。
        // 这里不能用 scrollIntoView，因为浏览器会连带把整个文档滚回页面顶部，
        // 表现就是点完目录后页面自己缓缓滚回全书开头。
        function scrollSidebarToActive() {{
            var activeItem = document.querySelector('.toc-nav .active');
            if (!activeItem || !sidebar) return;
            var box = sidebar.getBoundingClientRect();
            var item = activeItem.getBoundingClientRect();
            if (item.top < box.top + 30 || item.bottom > box.bottom - 30) {{
                sidebar.scrollTo({{
                    top: sidebar.scrollTop + (item.top - box.top) - box.height / 2 + item.height / 2,
                    behavior: 'smooth'
                }});
            }}
        }}

        function highlightAnchor(id) {{
            tocItems.forEach(function(item) {{
                item.classList.toggle('active', item.dataset.anchor === id);
            }});
            scrollSidebarToActive();
        }}

        function findCurrentHeading() {{
            for (var i = 0; i < anchorElements.length; i++) {{
                if (anchorElements[i].getBoundingClientRect().top > 100) {{
                    return i > 0 ? anchorElements[i - 1].id : anchorElements[0].id;
                }}
            }}
            return anchorElements.length ? anchorElements[anchorElements.length - 1].id : null;
        }}

        // 点击正文任意位置 → 左侧目录自动定位并高亮所在章节
        function findHeadingAtY(y) {{
            var found = null;
            for (var i = 0; i < anchorElements.length; i++) {{
                if (anchorElements[i].getBoundingClientRect().top <= y) found = anchorElements[i].id;
            }}
            return found || (anchorElements.length ? anchorElements[0].id : null);
        }}
        document.getElementById('main').addEventListener('click', function(e) {{
            var id = findHeadingAtY(e.clientY);
            if (id) highlightAnchor(id);
        }});

        var scrollTimer = null;
        window.addEventListener('scroll', function() {{
            if (scrollTimer) return;
            scrollTimer = setTimeout(function() {{
                scrollTimer = null;
                var id = findCurrentHeading();
                if (id) highlightAnchor(id);
            }}, 150);
        }});
        var initId = findCurrentHeading();
        if (initId) highlightAnchor(initId);

        // 拖拽宽度
        (function() {{
            var c = document.getElementById('drag-container');
            var h = document.getElementById('drag-handle');
            if (!c || !h) return;
            var KEY = 'pla_history_width';
            var saved = localStorage.getItem(KEY);
            if (saved) {{ var w = parseInt(saved, 10); if (w >= 360) c.style.width = w + 'px'; }}
            var dragging = false, startX = 0, startW = 0;
            h.addEventListener('mousedown', function(e) {{
                dragging = true; startX = e.clientX; startW = c.offsetWidth;
                document.body.style.cursor = 'ew-resize'; document.body.style.userSelect = 'none';
                e.preventDefault();
            }});
            document.addEventListener('mousemove', function(e) {{
                if (!dragging) return;
                var nw = Math.max(360, Math.min(startW + e.clientX - startX, window.innerWidth * 0.95));
                c.style.width = nw + 'px';
            }});
            document.addEventListener('mouseup', function() {{
                if (dragging) {{ dragging = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; localStorage.setItem(KEY, c.offsetWidth); }}
            }});
        }})();

        // 阅读位置记忆
        (function() {{
            var KEY = 'pla_history_scroll';
            var saved = localStorage.getItem(KEY);
            if (saved) {{ var p = parseInt(saved, 10); if (p > 0) {{ window.scrollTo(0, p); setTimeout(function() {{ window.scrollTo(0, p); }}, 1500); }} }}
            var t = null;
            window.addEventListener('scroll', function() {{
                if (t) return;
                t = setTimeout(function() {{ t = null; localStorage.setItem(KEY, window.scrollY); }}, 500);
            }});
            window.addEventListener('beforeunload', function() {{ localStorage.setItem(KEY, window.scrollY); }});
        }})();

        // 工具栏
        (function() {{
            var KEY = 'pla_history_settings';
            var FONTS = ['kai', 'song', 'hei'];
            var FNAME = {{ kai: '楷体', song: '宋体', hei: '黑体' }};
            var FCSS = {{
                kai: '"KaiTi","STKaiti","楷体","Noto Serif SC","Songti SC",serif',
                song: '"SimSun","STSong","宋体","Noto Serif SC",serif',
                hei: '"SimHei","STHeiti","黑体","PingFang SC","Microsoft YaHei",sans-serif'
            }};
            var THEMES = ['auto', 'paper', 'sepia', 'dark'];
            var TNAME = {{ auto: '跟随系统', paper: '纸张', sepia: '护眼', dark: '暗色' }};
            var S = {{ fs: 17, lh: 1.95, font: 'kai', theme: 'auto' }};
            try {{ var p = JSON.parse(localStorage.getItem(KEY));
                if (p) {{ if (typeof p.fs==='number') S.fs=p.fs; if (typeof p.lh==='number') S.lh=p.lh;
                    if (FONTS.indexOf(p.font)>=0) S.font=p.font; if (THEMES.indexOf(p.theme)>=0) S.theme=p.theme; }}
            }} catch(e) {{}}
            function apply() {{
                var r = document.documentElement.style;
                r.setProperty('--font-size-body', S.fs+'px');
                r.setProperty('--line-height-body', S.lh);
                r.setProperty('--font-body', FCSS[S.font]);
                document.body.classList.remove('theme-paper','theme-sepia','theme-dark');
                if (S.theme !== 'auto') document.body.classList.add('theme-'+S.theme);
                var fl=document.getElementById('rb-fs-label'); if(fl) fl.textContent=S.fs+'px';
                var ll=document.getElementById('rb-lh-label'); if(ll) ll.textContent=S.lh.toFixed(2);
                var fb=document.getElementById('rb-font'); if(fb) fb.textContent='字体·'+FNAME[S.font];
                var tb=document.getElementById('rb-theme'); if(tb) tb.textContent='主题·'+TNAME[S.theme];
            }}
            function save() {{ localStorage.setItem(KEY, JSON.stringify(S)); }}
            apply();
            document.getElementById('reading-bar').addEventListener('click', function(e) {{
                var btn = e.target.closest('button'); if (!btn) return;
                var act = btn.dataset.act; if (!act) return;
                if (act==='font+') S.fs=Math.min(24,S.fs+1);
                else if (act==='font-') S.fs=Math.max(12,S.fs-1);
                else if (act==='lh+') S.lh=Math.min(3,+(S.lh+0.1).toFixed(2));
                else if (act==='lh-') S.lh=Math.max(1.3,+(S.lh-0.1).toFixed(2));
                else if (act==='font') {{ var i=FONTS.indexOf(S.font); S.font=FONTS[(i+1)%FONTS.length]; }}
                else if (act==='theme') {{ var i=THEMES.indexOf(S.theme); S.theme=THEMES[(i+1)%THEMES.length]; }}
                apply(); save();
            }});
        }})();
    </script>
</body>
</html>'''

    return html


if __name__ == '__main__':
    html_content = generate_html()
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
    file_size = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"HTML 文件已生成: {OUTPUT_FILE}")
    print(f"文件大小: {file_size:.1f} KB")
    print(f"共处理 {len(MD_FILES)} 个章节文件")
