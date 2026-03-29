"""引用位置识别模块：让 LLM 将审查后的文献分配到论文具体段落。"""

import json
import re
from typing import List, Dict, Any, Optional, Set

import anthropic

# 不适合插入引用的段落特征（段落首60字符内匹配即排除）
_UNSUITABLE_PATTERNS = re.compile(
    r"^(图\s*\d|figure\s*\d|fig\.?\s*\d|表\s*\d|table\s*\d|"
    r"注[:：]|note[:：]|来源[:：]|source[:：]|"
    r"致谢|acknowledgment|acknowledgement|"
    r"摘要|abstract|关键词|keywords?|"
    r"作者简介|author|收稿日期|received|"
    r"基金项目|fund|supported by|"
    # 目录相关
    r"目\s*录|contents?|table\s+of\s+contents|"
    # 参考文献区块标题
    r"参考文献|references|bibliography|works\s+cited|"
    # 论文标题常见位置标志（独立一行的短标题行、序号标题行）
    r"\d+[\.\s]+\S|[一二三四五六七八九十]+[、．.]\S)",
    re.IGNORECASE,
)

# 目录条目：正文含省略号/连续点后跟页码（如"第一章……1"、"1.1 引言 .... 3"）
_TOC_ENTRY_PATTERN = re.compile(
    r"[\u2026\.·]{3,}\s*\d+\s*$"
)

_MIN_BODY_LENGTH = 40  # 适合引用的段落最短字符数


def locate_citation_positions_llm(
    paragraphs: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    max_paragraphs: int = 60,
) -> List[Dict[str, Any]]:
    """
    使用 LLM 将审查后的参考文献分配到论文中需要引用的段落。

    参数：
        paragraphs    : 清洗后的论文段落列表
        ranked_papers : llm_review_literature() 返回的已选文献

    返回列表，每项格式：
    {
        "paragraph_index": int,
        "text": str,
        "reason": str,
        "cite_indices": [int],   # ranked_papers 中的下标
        "cite_titles": [str],    # 对应文献标题
    }
    """
    if not ranked_papers:
        raise RuntimeError("[LLM引用] ranked_papers 为空，无法进行引用位置识别")

    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        client_kwargs["timeout"] = timeout_ms / 1000.0
    client = anthropic.Anthropic(**client_kwargs)

    # ── 格式化参考文献列表 ─────────────────────────────────────
    ref_lines = []
    for i, p in enumerate(ranked_papers):
        year = p.get("year", "")
        journal = p.get("journal", "")
        ref_lines.append(
            f"REF[{i}] ({year}) {p['title']}"
            + (f" — {journal}" if journal else "")
        )
    refs_text = "\n".join(ref_lines)

    # ── 格式化段落列表（过滤标题及不适合插入引用的段落）─────
    body_paras = [
        p for p in paragraphs
        if not p.get("is_heading") and _is_suitable_paragraph(p)
    ][:max_paragraphs]
    valid_para_indices: Set[int] = {p["index"] for p in body_paras}
    para_lines = "\n".join(
        f"PARA[{p['index']}] {p['text'][:200]}" for p in body_paras
    )

    n_refs = len(ranked_papers)

    prompt = f"""你是学术写作助手。请将每篇参考文献精确分配到论文正文中最合适的段落。

## 参考文献（共 {n_refs} 篇，REF[0] ~ REF[{n_refs - 1}]）
{refs_text}

## 论文段落（已过滤标题与非正文内容，仅含正文段落）
{para_lines}

## 规则（严格遵守，违反将导致结果无效）

### 【绝对禁止】以下类型段落 —— 无论任何情况均不得选择：
- 论文大标题（论文第一行标题）
- 章节标题、小节标题（如"一、引言"、"2.1 方法"）
- 目录页或目录条目（包含省略号"……"后跟页码的行）
- 摘要段落（Abstract / 摘要）及关键词行（Keywords / 关键词）
- 图题、图注（Figure X / 图X）、表题（Table X / 表X）
- 致谢段落（Acknowledgment / 致谢）
- 参考文献区块标题或条目（References / 参考文献）
- 作者信息、基金项目、收稿日期等非正文行
- 字符数少于 40 的短段落

### 【必须选择】含有实质性论述的正文段落：
- 引言、文献综述、研究背景中的陈述句
- 方法描述、实验设计、数据来源说明
- 结果分析、讨论、结论中的论证句
- 包含"研究表明"、"本文采用"、"实验结果"等学术表达的段落

1. 每篇参考文献 REF[i] 必须且只能分配到一个正文段落
2. 每个段落最多分配一篇参考文献
3. 为每篇文献找到内容最相关的正文段落
4. 输出条目数必须等于参考文献数量：{n_refs} 条

## 返回格式（仅返回 JSON，不含其他内容）
[
  {{
    "paragraph_index": 段落编号（PARA[X] 中的 X）,
    "reason": "选择理由（中文，一句话，说明文献与该段落正文内容的关联）",
    "cite_indices": [单个REF编号，如 [3]]
  }},
  ... （共 {n_refs} 条，每条对应一篇文献）
]

只输出 JSON。"""

    print("  [LLM] 正在识别引用位置...")

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text_content = "".join(
        block.text for block in response.content if block.type == "text"
    )

    if not text_content.strip():
        raise RuntimeError("[LLM引用] 模型未返回任何内容")

    # ── 解析 JSON ──────────────────────────────────────────────
    text_stripped = text_content.strip()
    if text_stripped.startswith("```"):
        text_stripped = re.sub(r"^```[a-z]*\n?", "", text_stripped)
        text_stripped = re.sub(r"\n?```$", "", text_stripped.strip()).strip()

    positions = _try_parse_array(text_stripped)

    if positions is None:
        print("[LLM引用] JSON 解析失败，回退为空结果（不中断流程）")
        return []

    # ── 校验：去重段落、确保每篇文献只出现一次，过滤不合适段落 ──
    seen_paras: set = set()
    seen_refs: set = set()
    deduped = []
    skipped_invalid = 0
    for pos in positions:
        pidx = pos.get("paragraph_index")
        refs = [i for i in (pos.get("cite_indices") or [])
                if isinstance(i, int) and 0 <= i < len(ranked_papers)]
        if not refs or pidx is None:
            continue
        ref = refs[0]  # 每条只取第一个
        # 严格校验：只接受出现在 body_paras 中的合法段落索引
        if pidx not in valid_para_indices:
            skipped_invalid += 1
            continue
        if pidx in seen_paras or ref in seen_refs:
            continue
        seen_paras.add(pidx)
        seen_refs.add(ref)
        pos["cite_indices"] = [ref]
        deduped.append(pos)
    if skipped_invalid:
        print(f"  [LLM引用] 已过滤 {skipped_invalid} 处无效/不适合位置（标题或非正文段落）")

    positions = deduped
    print(f"  [LLM引用] 识别到 {len(positions)} 处引用位置（共 {len(ranked_papers)} 篇文献）")

    # ── 补充 cite_titles 字段 ──────────────────────────────────
    para_index_to_text = {p["index"]: p.get("text", "") for p in body_paras}
    for pos in positions:
        indices = pos.get("cite_indices") or []
        pidx = pos.get("paragraph_index")
        if pidx in para_index_to_text and not pos.get("text"):
            pos["text"] = para_index_to_text[pidx][:100]
        # 优先使用 LLM 审查阶段给出的文献选择理由，便于在 Word 批注中复用。
        if indices:
            i0 = indices[0]
            if isinstance(i0, int) and 0 <= i0 < len(ranked_papers):
                review_reason = ranked_papers[i0].get("_review_reason", "")
                if review_reason:
                    pos["review_reason"] = review_reason
        pos["cite_titles"] = [
            ranked_papers[i]["title"]
            for i in indices
            if isinstance(i, int) and 0 <= i < len(ranked_papers)
        ]

    return positions


def _try_parse_array(text: str):
    """
    从 LLM 输出中提取 JSON 数组，能容忍输出被截断的情况。
    返回 list 或 None。
    """
    # 1. 直接解析
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 2. 提取 [ ... ] 块后解析
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 3. 截断修复：找到最后一个完整的 {...} 对象，截取到它为止再闭合数组
    # 适用于 max_tokens 不够导致末尾 JSON 不完整的场景
    start = text.find('[')
    if start == -1:
        return None

    # 找所有完整的顶层对象边界
    depth = 0
    last_complete_end = -1
    i = start + 1
    obj_start = -1
    while i < len(text):
        c = text[i]
        if c == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and obj_start != -1:
                last_complete_end = i
        i += 1

    if last_complete_end == -1:
        return None

    # 截取到最后一个完整对象，闭合数组
    truncated = text[start: last_complete_end + 1].rstrip().rstrip(',') + ']'
    try:
        result = json.loads(truncated)
        if isinstance(result, list):
            print(f"  [LLM引用] 输出被截断，已恢复 {len(result)} 条完整记录")
            return result
    except json.JSONDecodeError:
        pass

    return None


def _is_suitable_paragraph(para: Dict[str, Any]) -> bool:
    """
    判断段落是否适合插入引用。
    过滤：标题、目录、图题、表题、致谢、摘要、关键词、参考文献区块等非正文内容。
    """
    text = para.get("text", "").strip()
    # 过短的段落
    if len(text) < _MIN_BODY_LENGTH:
        return False
    # 匹配不适合的段落特征（前60字符内检测）
    if _UNSUITABLE_PATTERNS.match(text[:60]):
        return False
    # 目录条目（含省略号/连续点后跟页码）
    if _TOC_ENTRY_PATTERN.search(text):
        return False
    # 纯数字/单词段落（页码、编号等）
    if re.match(r"^\s*[\d\s\-–—/\\]+\s*$", text):
        return False
    return True
