"""
对比报告生成服务 - 使用 DeepSeek API
"""
import os
from typing import List
from openai import OpenAI

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def get_client() -> OpenAI:
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def generate_comparison_report(
    user_case_name: str,
    user_case_description: str,
    similar_cases: list,
) -> dict:
    """生成类案对比报告"""
    if not DEEPSEEK_API_KEY:
        return _mock_report(user_case_name, user_case_description, similar_cases)

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
基本案情: {case.case_summary or '无'}
争议焦点: {case.dispute_focus or '无'}
裁判结果: {case.judgment_result or '无'}
裁判理由: {case.judgment_reason or '无'}
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

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位专业的法律AI助手，擅长类案分析和法律研究。请始终以JSON格式输出。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    import json
    content = response.choices[0].message.content.strip()
    # 清理可能的markdown代码块
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
    return json.loads(content)


def _mock_report(user_case_name: str, user_case_description: str, similar_cases: list) -> dict:
    """Mock报告生成，用于开发测试"""
    comparisons = []

    aspects = [
        ("案件事实", "本案涉及的基本事实要素"),
        ("法律关系", "当事人之间的法律关系性质"),
        ("争议焦点", "案件的核心争议问题"),
        ("适用法律", "适用的法律法规"),
        ("裁判结果", "法院的判决结果"),
    ]

    for case in similar_cases[:3]:
        for aspect_name, aspect_desc in aspects:
            comparisons.append({
                "aspect": aspect_name,
                "user_case": f"用户案情中关于{aspect_name}的描述：{user_case_description[:50]}...",
                "similar_case": f"【{case.case_name}】{aspect_desc}：{(case.case_summary or '暂无详细信息')[:80]}...",
                "analysis": f"两案在{aspect_name}方面具有较高相似性，{case.case_name}的裁判思路对本案具有重要参考价值。",
            })

    legal_refs = []
    for case in similar_cases[:3]:
        if case.related_laws:
            legal_refs.extend([law.strip() for law in case.related_laws.split("；")])
    legal_refs = list(set(legal_refs)) if legal_refs else ["《中华人民共和国民法典》相关条款"]

    return {
        "title": f"类案检索分析报告 - {user_case_name}",
        "summary": f"本报告基于案情「{user_case_description[:60]}」进行类案检索，共检索到{len(similar_cases)}个高度相似案例。通过多维度对比分析，为本案的诉讼策略提供参考依据。",
        "comparisons": comparisons,
        "legal_references": legal_refs,
        "conclusion": f"综合分析{len(similar_cases)}个类案的裁判结果和裁判理由，建议当事人重点关注证据收集和法律关系的准确认定。类案的裁判趋势表明，在类似案件中法院倾向于保护合法权益，建议及时固定关键证据，明确诉讼请求。",
    }
