#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""평가문·구성계획 필드 규약 — 판본과 계획을 함께 다루기 위한 공용 헬퍼.

품질 검토 패스(5.5단계)의 결과는 **원본을 덮어쓰지 않고 별도 필드로 추가**한다.
그래야 검수하는 사람이 "무엇이 왜 바뀌었는지"를 산출물에서 바로 대조할 수 있고,
검토를 되돌리고 싶을 때 원본이 그대로 남아 있다.

    "평가문":        5단계에서 작성한 원본. 검토 패스가 있어도 그대로 둔다.
    "평가문_검토본":  검토 지적을 반영한 판본. 검토를 돌렸을 때만 존재한다.
    "계획":          4단계(구성 계획)의 설계 메모. 글이 무엇을 증명하려 했는지의 기록이다.

빌드 스크립트는 이 규약을 따라 두 판본을 나란히 보여주고, 업로드 양식은
최종본(검토본이 있으면 검토본)을 쓴다. 계획은 검수 산출물에만 실리고 업로드본에는 넣지 않는다.
"""

BASE_FIELD = "평가문"
REVIEW_FIELD = "평가문_검토본"
PLAN_FIELD = "계획"
# 계획의 항목 순서 — 주장(무엇을 증명할지) → 근거(무엇으로) → 순서(어떻게 놓을지) → 제외(무엇을 버릴지)
PLAN_KEYS = ("주장", "근거", "순서", "제외")


def base_text(s) -> str:
    """4단계에서 쓴 원본 평가문."""
    return s.get(BASE_FIELD, "") or ""


def review_text(s) -> str:
    """검토 패스를 반영한 판본. 검토를 돌리지 않았으면 빈 문자열."""
    return s.get(REVIEW_FIELD, "") or ""


def final_text(s) -> str:
    """업로드에 쓸 최종본 — 검토본이 있으면 검토본, 없으면 원본."""
    return review_text(s) or base_text(s)


def has_review(students) -> bool:
    """명단에 검토본이 하나라도 있으면 참."""
    return any(review_text(s) for s in students)


def is_changed(s) -> bool:
    """검토본이 원본과 실제로 다른지(공백만 다른 것은 같은 것으로 본다)."""
    r = review_text(s)
    return bool(r) and r.strip() != base_text(s).strip()


def plan(s) -> dict:
    """4단계 구성 계획. 세우지 않았으면 빈 dict."""
    p = s.get(PLAN_FIELD)
    return p if isinstance(p, dict) else {}


def has_plan(students) -> bool:
    """명단에 계획이 하나라도 있으면 참."""
    return any(plan(s) for s in students)


def plan_lines(s):
    """계획을 [(항목, 내용)] 목록으로 편다 — Excel·HTML이 같은 모양으로 보여주기 위한 공용 변환.

    근거는 항목이 여러 개이고 각각 '어느 활동의 / 어떤 사실이 / 왜 주장을 뒷받침하는지'로
    이루어지므로, 근거 하나를 한 줄로 접어 보여준다.
    """
    p = plan(s)
    if not p:
        return []
    out = []
    for k in PLAN_KEYS:
        v = p.get(k)
        if not v:
            continue
        if k == "근거" and isinstance(v, list):
            for i, e in enumerate(v, 1):
                if isinstance(e, dict):
                    act, fact, why = e.get("활동", ""), e.get("사실", ""), e.get("증명", "")
                    body = " / ".join(x for x in (act, fact) if x)
                    if why:
                        body = f"{body} → {why}" if body else why
                else:
                    body = str(e)
                out.append((f"근거 {i}", body))
        else:
            out.append((k, v if isinstance(v, str) else str(v)))
    # 규약에 없는 항목도 버리지 않고 뒤에 붙인다(과목별로 항목을 더 둘 수 있다).
    for k, v in p.items():
        if k not in PLAN_KEYS and v:
            out.append((k, v if isinstance(v, str) else str(v)))
    return out


def plan_text(s) -> str:
    """계획을 여러 줄 문자열로. (Excel 셀·검색용)"""
    return "\n".join(f"[{k}] {v}" for k, v in plan_lines(s))
