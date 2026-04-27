"""
Query filter extraction service.

Uses DeepSeek to extract structured filters from the user's natural-language
case description, with a small rule-based fallback for local demos.
"""
import json
import os
import re
from datetime import date
from typing import Any, Dict, Optional

from openai import OpenAI


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def normalize_case_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if "民事" in value:
        return "民事"
    if "刑事" in value:
        return "刑事"
    if "行政" in value:
        return "行政"
    return None


def normalize_date(value: Optional[str]) -> Optional[str]:
    """Normalize common Chinese/ISO date strings to YYYY-MM-DD."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"(\d{4})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3) or 1)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    match = re.search(r"(\d{4})", text)
    if match:
        return f"{int(match.group(1)):04d}-01-01"

    return None


def parse_query_filters(text: str) -> Dict[str, Any]:
    """
    Extract search filters from a user query.

    Returns:
        {
            "case_type": "民事" | "刑事" | "行政" | None,
            "time_range_start": "YYYY-MM-DD" | None,
            "time_range_end": "YYYY-MM-DD" | None,
            "cause_keywords": list[str],
            "source": "deepseek" | "rule_fallback"
        }
    """
    if DEEPSEEK_API_KEY:
        try:
            filters = _parse_with_deepseek(text)
            filters["source"] = "deepseek"
            return _normalize_filters(filters)
        except Exception as exc:
            print(f"[query_parser] DeepSeek extraction failed, falling back to rules: {exc}")

    filters = _parse_with_rules(text)
    filters["source"] = "rule_fallback"
    return _normalize_filters(filters)


def _parse_with_deepseek(text: str) -> Dict[str, Any]:
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    today = date.today().isoformat()
    prompt = f"""请从用户输入的法律类案检索 query 中抽取结构化筛选条件。

当前日期：{today}

只输出 JSON，不要输出 markdown，不要解释。

JSON 字段：
{{
  "case_type": "民事|刑事|行政|null",
  "time_range_start": "YYYY-MM-DD|null",
  "time_range_end": "YYYY-MM-DD|null",
  "cause_keywords": ["案由或关键纠纷类型关键词"]
}}

抽取规则：
1. 只有用户明确表达案件类别时才填 case_type，例如民事、刑事、行政、合同纠纷通常属于民事，盗窃/诈骗/危险驾驶通常属于刑事，行政处罚/行政登记通常属于行政。
2. 识别时间表达并转为裁判日期范围，例如“2020年到2023年”=> 2020-01-01 到 2023-12-31，“2021年以后”=> start=2021-01-01，“2019年以前”=> end=2019-12-31，“近三年”按当前日期推算。
3. 如果没有明确时间范围，time_range_start/time_range_end 都为 null。
4. cause_keywords 放案由、纠纷类型或高价值法律关键词，最多 5 个。

用户 query：
{text}
"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是法律检索 query 结构化抽取器，只输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=600,
    )
    content = response.choices[0].message.content.strip()
    return _load_json_object(content)


def _load_json_object(content: str) -> Dict[str, Any]:
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
    content = content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    return data if isinstance(data, dict) else {}


def _normalize_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    cause_keywords = filters.get("cause_keywords") or []
    if isinstance(cause_keywords, str):
        cause_keywords = [cause_keywords]
    cause_keywords = [str(k).strip() for k in cause_keywords if str(k).strip()][:5]

    return {
        "case_type": normalize_case_type(filters.get("case_type")),
        "time_range_start": normalize_date(filters.get("time_range_start")),
        "time_range_end": normalize_date(filters.get("time_range_end")),
        "cause_keywords": cause_keywords,
        "source": filters.get("source") or "unknown",
    }


def _parse_with_rules(text: str) -> Dict[str, Any]:
    case_type = None
    if any(word in text for word in ["盗窃", "诈骗", "危险驾驶", "刑事", "公诉"]):
        case_type = "刑事"
    elif any(word in text for word in ["行政", "处罚决定", "行政处罚", "市场监督", "生态环境部门"]):
        case_type = "行政"
    elif any(word in text for word in ["合同", "借款", "租赁", "劳动", "离婚", "侵权", "赔偿", "民事"]):
        case_type = "民事"

    start = None
    end = None
    range_match = re.search(r"(\d{4})\s*年?\s*(?:到|至|-|—|~)\s*(\d{4})\s*年?", text)
    if range_match:
        start = f"{range_match.group(1)}-01-01"
        end = f"{range_match.group(2)}-12-31"
    else:
        after_match = re.search(r"(\d{4})\s*年?\s*(以后|之后|以来|起)", text)
        before_match = re.search(r"(\d{4})\s*年?\s*(以前|之前|前)", text)
        if after_match:
            start = f"{after_match.group(1)}-01-01"
        if before_match:
            end = f"{before_match.group(1)}-12-31"

    keywords = []
    for keyword in [
        "买卖合同", "劳动合同", "民间借贷", "交通事故", "房屋租赁", "离婚",
        "继承", "侵权", "知识产权", "盗窃", "诈骗", "危险驾驶", "行政处罚",
    ]:
        if keyword in text:
            keywords.append(keyword)

    return {
        "case_type": case_type,
        "time_range_start": start,
        "time_range_end": end,
        "cause_keywords": keywords,
    }
