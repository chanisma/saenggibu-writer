#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원자료 규약 — 활동지 원문을 담은 불변 입력을 students.json에 이어 붙인다.

3단계에서 만든 `원자료.json`은 **요약하지 않은 활동지 원문**이며 한 번 뽑으면 바뀌지 않는다.
`students.json`은 그 파일을 가리키기만 하고 자료를 복사해 두지 않는다.

    students.json:  { "원자료": "원자료.json", "students": [ {번호, 이름, 계획, 평가문 …} ] }

이렇게 두는 이유
  · **요약본을 근거로 쓰면 누가 언제 요약했느냐에 따라 글이 달라진다.** 계획과 평가문은 원문을 본다.
  · 원문은 바뀔 이유가 없으므로 한 파일에 두고 여러 판본이 함께 참조한다(중복 보관하지 않는다).
  · 검수 산출물(Excel·HTML)은 이 모듈로 원문을 붙여 근거를 대조할 수 있게 한다.

`students.json`에 `활동`이 이미 들어 있으면 그대로 두고, 없을 때만 원자료에서 채운다.
"""
import json
import os

RAW_FIELD = "원자료"
# 학생을 가리키는 값이거나 본문이 아닌 열 — 활동 본문에서 뺀다(제출시각은 머리글로 따로 붙인다)
META = {"타임스탬프", "제출시각", "이름", "학번", "반/번호", "날짜"}


def raw_path(students_path, data):
    """students.json이 가리키는 원자료 파일 경로(상대경로는 students.json 기준)."""
    ref = data.get(RAW_FIELD)
    if not ref:
        return None
    return ref if os.path.isabs(ref) else os.path.join(os.path.dirname(os.path.abspath(students_path)), ref)


def load(students_path, data):
    """원자료를 읽어 돌려준다. 가리키는 파일이 없으면 None."""
    p = raw_path(students_path, data)
    if not p or not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _submission_text(rec):
    """제출 한 건을 '필드: 값' 줄로 편다. 값은 원문 그대로 둔다."""
    ts = rec.get("제출시각") or rec.get("타임스탬프") or ""
    lines = [f"[{ts}]"] if ts else []
    for k, v in rec.items():
        if k in META:
            continue
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def activities_of(student_raw, activity_names=None):
    """한 학생의 제출을 {활동명: 원문} 으로. 중복 제출은 모두 이어 붙인다."""
    out = {}
    for sheet, records in (student_raw.get("제출") or {}).items():
        name = (activity_names or {}).get(sheet, sheet)
        blocks = [_submission_text(r) for r in records]
        if len(blocks) > 1:
            blocks = [f"— 제출 {i}/{len(blocks)} —\n{b}" for i, b in enumerate(blocks, 1)]
        out[name] = "\n\n".join(blocks)
    return out


def attach(students_path, data):
    """students.json의 각 학생에게 원자료의 활동 원문을 붙인다(이미 있으면 두고, 없을 때만).

    돌려주는 값은 (붙인 학생 수, 원자료 경로). 원자료가 없으면 (0, None).
    """
    raw = load(students_path, data)
    if not raw:
        return 0, None
    names = raw.get("활동명") or {}
    by_id = {}
    for r in raw.get("students", []):
        for key in (str(r.get("학번", "")), str(r.get("번호", ""))):
            if key:
                by_id[key] = r
        if r.get("이름"):
            by_id.setdefault(str(r["이름"]), r)

    n = 0
    for s in data.get("students", []):
        if s.get("활동"):
            continue
        r = by_id.get(str(s.get("번호", ""))) or by_id.get(str(s.get("이름", "")))
        if not r:
            continue
        acts = activities_of(r, names)
        if acts:
            s["활동"] = acts
            n += 1
    return n, raw_path(students_path, data)
