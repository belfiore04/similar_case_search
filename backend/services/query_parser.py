"""
Query filter extraction service.

Uses DeepSeek to extract structured filters from the user's natural-language
case description.
"""
import json
import os
import re
from datetime import date
from typing import Any, Dict, Optional

from openai import OpenAI


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
            "source": "deepseek"
        }
    """
    try:
        filters = _parse_with_deepseek(text)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"DeepSeek 查询条件抽取失败: {exc}") from exc
    filters["source"] = "deepseek"
    return _normalize_filters(filters)


def _parse_with_deepseek(text: str) -> Dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法调用真实 DeepSeek 查询条件抽取服务。")
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
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
