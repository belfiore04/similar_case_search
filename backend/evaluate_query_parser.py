"""
Evaluate DeepSeek query filter extraction for local demo scenarios.

Run:
  DEEPSEEK_API_KEY=... python evaluate_query_parser.py
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

from services.query_parser import parse_query_filters  # noqa: E402


def _years_ago_start(years: int) -> str:
    today = date.today()
    return f"{today.year - years:04d}-{today.month:02d}-{today.day:02d}"


TEST_CASES = [
    {
        "query": "查询2020年到2023年的民事买卖合同纠纷，卖方交货后买方拖欠货款。",
        "expected": {"case_type": "民事", "time_range_start": "2020-01-01", "time_range_end": "2023-12-31"},
    },
    {
        "query": "找一下2021年以后的劳动合同违法解除赔偿案例。",
        "expected": {"case_type": "民事", "time_range_start": "2021-01-01", "time_range_end": None},
    },
    {
        "query": "2019年以前的危险驾驶罪，醉酒驾驶机动车被查获。",
        "expected": {"case_type": "刑事", "time_range_start": None, "time_range_end": "2019-12-31"},
    },
    {
        "query": "行政处罚案件，企业不服生态环境部门罚款决定，最好是2022年至2024年的。",
        "expected": {"case_type": "行政", "time_range_start": "2022-01-01", "time_range_end": "2024-12-31"},
    },
    {
        "query": "交通事故赔偿，机动车撞到电动车，保险公司赔偿责任。",
        "expected": {"case_type": "民事", "time_range_start": None, "time_range_end": None},
    },
    {
        "query": "近三年的民间借贷纠纷，借款到期不还本金和利息。",
        "expected": {"case_type": "民事", "time_range_start": _years_ago_start(3), "time_range_end": date.today().isoformat()},
    },
    {
        "query": "盗窃罪案件，被告人多次秘密窃取他人财物，涉案金额较大。",
        "expected": {"case_type": "刑事", "time_range_start": None, "time_range_end": None},
    },
    {
        "query": "2024年房屋租赁合同纠纷，承租人拖欠租金并拒绝腾退。",
        "expected": {"case_type": "民事", "time_range_start": "2024-01-01", "time_range_end": "2024-12-31"},
    },
    {
        "query": "市场监督管理部门工商变更登记被起诉，行政登记行为违法。",
        "expected": {"case_type": "行政", "time_range_start": None, "time_range_end": None},
    },
    {
        "query": "诈骗案件，虚构投资项目骗取被害人钱款。",
        "expected": {"case_type": "刑事", "time_range_start": None, "time_range_end": None},
    },
    {
        "query": "2020年之后的离婚后财产分割纠纷，一方不配合房产过户。",
        "expected": {"case_type": "民事", "time_range_start": "2020-01-01", "time_range_end": None},
    },
    {
        "query": "2018年至2020年行政许可争议，申请人认为行政机关不予许可违法。",
        "expected": {"case_type": "行政", "time_range_start": "2018-01-01", "time_range_end": "2020-12-31"},
    },
]


def main() -> int:
    print("Query Parser Evaluation")
    print(f"Mode: {'deepseek' if os.getenv('DEEPSEEK_API_KEY') else 'rule_fallback'}")
    print("-" * 88)

    field_totals = {"case_type": 0, "time_range_start": 0, "time_range_end": 0}
    field_correct = {"case_type": 0, "time_range_start": 0, "time_range_end": 0}
    exact_correct = 0
    failures = []

    for idx, item in enumerate(TEST_CASES, 1):
        actual = parse_query_filters(item["query"])
        expected = item["expected"]
        exact = True

        for field in field_totals:
            field_totals[field] += 1
            if actual.get(field) == expected.get(field):
                field_correct[field] += 1
            else:
                exact = False

        if exact:
            exact_correct += 1
            status = "PASS"
        else:
            status = "FAIL"
            failures.append((idx, item["query"], expected, actual))

        print(
            f"{idx:02d} {status} | "
            f"type={actual.get('case_type')} "
            f"start={actual.get('time_range_start')} "
            f"end={actual.get('time_range_end')} "
            f"keywords={actual.get('cause_keywords')}"
        )

    print("-" * 88)
    total = len(TEST_CASES)
    print(f"Exact accuracy: {exact_correct}/{total} = {exact_correct / total:.2%}")
    for field in field_totals:
        print(
            f"{field} accuracy: "
            f"{field_correct[field]}/{field_totals[field]} = "
            f"{field_correct[field] / field_totals[field]:.2%}"
        )

    if failures:
        print("\nFailures:")
        for idx, query, expected, actual in failures:
            print(f"- #{idx}: {query}")
            print(f"  expected={expected}")
            print(
                "  actual="
                f"{{'case_type': {actual.get('case_type')!r}, "
                f"'time_range_start': {actual.get('time_range_start')!r}, "
                f"'time_range_end': {actual.get('time_range_end')!r}}}"
            )

    return 0 if exact_correct == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
