#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""students.json → 결과 JSON (평가문 산출물).

`students.json`은 파이프라인의 **작업 파일**이라 활동 원자료와 여러 판본이 함께 들어 있다.
이 스크립트는 거기서 **평가문 결과만 추려** 다른 곳에 넘기기 좋은 JSON으로 뽑는다.
build_html.py·build_workbook.py·build_gwagi.py와 같은 5단계 산출물이며
판본 규약(evaltext.py)과 `--text` 선택지도 build_gwagi.py와 같다.

담기는 것: 학번·반·번호·이름·성적·목표바이트·평가문·바이트수·판정
  (원본과 검토본이 모두 있으면 `평가문_원본`을 함께 넣어 무엇이 채택되었는지 남긴다)
활동 원자료는 담지 않는다. 원자료가 필요하면 students.json을 쓴다.

사용법:
  python build_json.py students.json 결과.json
  python build_json.py students.json 결과_원본.json --text 평가문
  python build_json.py students.json 결과.json --indent 0     # 한 줄(작은 파일)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from byte_count import count_bytes, verdict  # noqa: E402
from evaltext import base_text, final_text, review_text  # noqa: E402

# 학생마다 있으면 그대로 옮기는 식별·조건 필드(순서 유지)
CARRY = ("학번", "반", "번호", "이름", "성적", "제약사항", "목표바이트")


def pick(s, mode: str) -> str:
    if mode == "평가문":
        return base_text(s)
    if mode == "평가문_검토본":
        return review_text(s) or base_text(s)
    return final_text(s)          # auto — 검토본이 있으면 검토본


def build(src: str, dst: str, mode: str, indent):
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    students = data.get("students", data if isinstance(data, list) else [])

    out, empty = [], []
    for s in students:
        text = (pick(s, mode) or "").strip()
        row = {k: s[k] for k in CARRY if s.get(k) not in (None, "")}
        if not text:
            empty.append(s.get("이름", "?"))
            row["평가문"] = ""
            row["바이트수"] = 0
            row["판정"] = "미작성"
        else:
            n = count_bytes(text)
            row["평가문"] = text
            row["바이트수"] = n
            row["판정"] = verdict(n, s.get("목표바이트"))
            # 두 판본이 실제로 다를 때만 원본을 함께 남긴다(무엇이 채택됐는지 추적용)
            b = base_text(s).strip()
            if b and b != text:
                row["평가문_원본"] = b
        out.append(row)

    payload = {"subject": data.get("subject", ""), "판본": mode, "students": out}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False,
                  indent=(None if indent == 0 else indent))
        f.write("\n")

    n_ok = sum(1 for r in out if r["판정"] == "적정")
    print(f"저장 완료: {dst}  (학생 {len(out)}명, 판본 {mode}, 적정 {n_ok}명)")
    off = [f"{r['이름']} {r['판정']}" for r in out if r["판정"] not in ("적정", "—")]
    if off:
        print("  ⚠ 목표 벗어남: " + ", ".join(off))
    if empty:
        print("  ⚠ 평가문 없음: " + ", ".join(empty))


def main():
    ap = argparse.ArgumentParser(description="students.json → 결과 JSON(평가문 산출물)")
    ap.add_argument("src", help="students.json 경로")
    ap.add_argument("dst", help="출력 JSON 경로")
    ap.add_argument("--text", default="auto",
                    choices=["auto", "평가문", "평가문_검토본"],
                    help="담을 판본 (기본 auto = 검토본 우선)")
    ap.add_argument("--indent", type=int, default=2,
                    help="들여쓰기 칸수. 0이면 한 줄로 저장")
    a = ap.parse_args()
    build(a.src, a.dst, a.text, a.indent)


if __name__ == "__main__":
    main()
