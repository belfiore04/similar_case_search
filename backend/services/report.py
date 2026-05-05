"""
对比报告生成服务 - 使用 DeepSeek API
"""
import os
from openai import OpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _case_text(case, field: str, display_field: str = None, fallback: str = "无") -> str:
    value = getattr(case, field, None)
    if value:
        return value
    if display_field:
        value = getattr(case, display_field, None)
        if value:
            return value
    return fallback


def get_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，无法调用真实 DeepSeek 报告生成服务。")
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def generate_comparison_report(
    user_case_name: str,
    user_case_description: str,
    similar_cases: list,
) -> dict:
    """生成类案对比报告"""
    client = get_client()

    # 构建类案信息
    cases_text = ""
    for i, case in enumerate(similar_cases, 1):
        cases_text += f"""
--- 类案{i}: {case.case_name} ---
案号: {case.case_number or '无'}
案由: {case.cause_of_action or '无'}
审理法院: {case.court or '无'}
裁判日期: {case.judge_date or '无'}
基本案情: {_case_text(case, 'case_summary', 'case_summary_display')}
争议焦点: {case.dispute_focus or '无'}
裁判结果: {_case_text(case, 'judgment_result', 'judgment_result_display')}
裁判理由: {_case_text(case, 'judgment_reason', 'judgment_reason_display')}
裁判要点: {case.judgment_points or '无'}
相关法条: {case.related_laws or '无'}
"""

    prompt = f"""你是一位资深法律分析师，请根据用户输入的案情和检索到的类案，生成一份专业的类案对比分析报告。

## 用户案情
案件名称: {user_case_name}
案情描述: {user_case_description}

## 检索到的类案
{cases_text}

## 请按以下JSON格式输出报告：
{{
  "title": "类案检索分析报告 - [案件名称简称]",
  "summary": "案情概述与检索结果摘要（200字以内）",
  "comparisons": [
    {{
      "aspect": "对比维度（如：案件事实、法律关系、争议焦点、适用法律、裁判结果）",
      "user_case": "用户案情在该维度的内容",
      "similar_case": "类案在该维度的内容",
      "analysis": "对比分析与参考价值"
    }}
  ],
  "legal_references": ["相关法律条文列表"],
  "conclusion": "综合分析结论与建议（包括胜诉可能性分析、证据建议、策略建议）"
}}

要求：
1. 对比维度至少包括：案件事实、法律关系、争议焦点、适用法律、裁判结果
2. 分析要专业客观，引用具体法条
3. 结论要有实际参考价值
4. 直接输出JSON，不要包含markdown代码块标记
"""

    import json
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一位专业的法律AI助手，擅长类案分析和法律研究。请始终以JSON格式输出。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        content = response.choices[0].message.content.strip()
        # 清理可能的markdown代码块
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as exc:
        raise RuntimeError(f"DeepSeek 报告生成失败: {exc}") from exc
