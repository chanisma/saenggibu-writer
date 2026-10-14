# -*- coding: utf-8 -*-
"""쉼표 점검 — 세특 품질 검수의 필수 측정 도구.

바이트를 눈대중하지 않듯, 쉼표도 눈대중하지 않는다. humanizer 패턴 1·3을 결정적으로 측정한다.
  · 패턴 1 (쉼표 과다):      쉼표/문장 밀도. LLM은 인간보다 쉼표를 훨씬 자주 쓴다.
  · 패턴 3 (연결어미 뒤 쉼표): -고/-며/-여/-아/-어/-해 등 연결어미 뒤 쉼표.
                             인간 코퍼스 4.10% vs LLM 19.83%(약 5배) — 세특에서 가장 잦은 AI 흔적.

목록 쉼표(`A와 B, C`)·조사 뒤(`~에서,`/`~로,`)·도입 동격구(`~한 학생으로,`)는 정상이므로
연결어미 뒤 쉼표만 골라 센다. `--clean`은 그 쉼표만 안전하게 제거한다(원문은 평가문_초안에 보존).

사용법:
  # 단일 문자열 점검
  python comma_check.py "작성한 평가문"
  # students.json 일괄 점검(측정만, 파일 불변)
  python comma_check.py --json results/<연도>_<과목>/students.json
  # 연결어미 뒤 쉼표 정리 + 저장(원문은 평가문_초안 보존)
  python comma_check.py --json results/<연도>_<과목>/students.json --clean --write
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from byte_count import count_bytes  # noqa: E402

# 쉼표 바로 앞 음절이 이 집합이면 '동사 연결어미 뒤 쉼표'로 본다(조사 '에서·로'는 제외 처리).
CONN = set("고며여아어해나워켜껴져자")

# 끝음절만 보는 판정이라 같은 음절로 끝나는 **명사**가 오탐된다(`오해,` `기고,` `사용자,` …).
# 아래는 세특에 자주 나오는 명사 예외다. 완전한 목록이 아니므로 남는 오탐은 아래 print_hits()가
# 문맥을 함께 찍어 사람이 판단하게 한다. 새 오탐을 만나면 여기에 추가한다.
NOUN_EXC = set("""
참고 사고 보고 신고 광고 원고 최고 경고 예고 중고 기고 창고 재고 회고 충고 권고 통고
참여 기여 부여 급여 관여 잉여
유아 소아 치아 동아
언어 단어 국어 영어 용어 술어 주어 제어 방어 표어 조어 약어 명령어 검색어 외래어 신조어 반의어 유의어
오해 이해 견해 피해 손해 방해 화해 항해 양해 난해 병충해 냉해 수해 재해 공해 침해 훼손해
하나
문자 숫자 인자 전자 원자 분자 학자 기자 상자 의자 모자 격자 독자 저자 필자 화자 청자 환자 연산자
사용자 이용자 설계자 개발자 연구자 소비자 참가자 지원자 관찰자 대상자 제작자 관리자 진행자
부족 만족 충족 가족 발족 유족
""".split())

# 밀도 경고 임계 — 쉼표/문장. 인간 세특 기준 대략 0.5 이하가 자연스럽다.
# **이것은 참고치이지 통과 조건이 아니다.** 셋 이상을 나열하는 목록 쉼표 때문에 넘는 것은 정상이며,
# 이 값을 맞추려고 정상적인 나열을 풀어쓰면 오히려 글이 나빠진다(실제로 그런 사례가 반복됐다).
# 반드시 0이어야 하는 것은 '연결어미 뒤 쉼표'와 '가운뎃점'뿐이다.
DENSITY_WARN = 0.5


def count_sentences(text: str) -> int:
    """마침표(.!?) 기준 문장 수. 세특은 대개 '~함.'으로 끝난다."""
    parts = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return max(1, len(parts))


def _token_before(text: str, i: int) -> str:
    """쉼표 위치 i 바로 앞의 어절(공백 구분)을 돌려준다."""
    j = i
    while j > 0 and not text[j - 1].isspace():
        j -= 1
    return text[j:i]


def connective_comma_spans(text: str):
    """연결어미 뒤 쉼표의 인덱스 목록.

    (앞음절이 CONN + 뒤가 공백 + '에서,' 제외 + 앞 어절이 NOUN_EXC의 명사가 아님)
    """
    hits = []
    for i, ch in enumerate(text):
        if ch == "," and i > 0:
            prev = text[i - 1]
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if prev in CONN and nxt == " " and text[i - 2:i] != "에서":
                if _token_before(text, i) in NOUN_EXC:
                    continue                      # 명사 오탐(`오해,` `사용자,` …)
                hits.append(i)
    return hits


def hit_contexts(text: str, width: int = 14):
    """연결어미 뒤 쉼표가 걸린 자리의 앞뒤 문맥. 사람이 오탐을 가려낼 수 있게 한다."""
    return [text[max(0, i - width):i + 1] + "…" for i in connective_comma_spans(text)]


def analyze(text: str) -> dict:
    commas = text.count(",")
    sents = count_sentences(text)
    conn = connective_comma_spans(text)
    dot = text.count("·")          # 가운뎃점 나열(인공지능 흔적) — 0이어야 함
    density = commas / sents
    return {
        "쉼표": commas,
        "문장": sents,
        "밀도": round(density, 2),
        "연결어미뒤": len(conn),
        "가운뎃점": dot,
        # 반드시 고쳐야 하는 것 — 연결어미 뒤 쉼표와 가운뎃점
        "위반": len(conn) > 0 or dot > 0,
        # 참고치 — 목록 쉼표로 넘는 것은 정상이며 통과 조건이 아니다
        "밀도초과": density > DENSITY_WARN,
    }


def clean(text: str):
    """연결어미 뒤 쉼표만 제거(뒤 공백은 유지). (제거본, 제거건수) 반환."""
    drop = set(connective_comma_spans(text))
    out = [ch for i, ch in enumerate(text) if i not in drop]
    return "".join(out), len(drop)


def run_json(path: str, do_clean: bool, write: bool, field: str = "평가문"):
    """`field`가 가리키는 판본을 점검한다.

    4.5 검토 패스는 원본을 덮지 않고 '평가문_검토본'을 덧붙이므로,
    검토본을 재검증할 때는 `--field 평가문_검토본`으로 같은 도구를 그대로 쓴다.
    """
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    students = d.get("students", [])
    rows, tot_conn, tot_dot, warn_n, dens_n, removed_tot = [], 0, 0, 0, 0, 0
    ctx_rows = []
    draft_field = field + "_초안"
    byte_field = "바이트수" if field == "평가문" else "바이트수_검토본"
    for s in students:
        t = s.get(field) or ""
        if not t:
            continue
        a = analyze(t)
        removed = 0
        if do_clean and a["연결어미뒤"]:
            if draft_field not in s:              # 첫 수정이면 원문 보존
                s[draft_field] = t
            newt, removed = clean(t)
            s[field] = newt
            a = analyze(newt)                     # 정리 후 값으로 재측정
            if byte_field in s:                   # 기록된 바이트수가 낡지 않게 함께 갱신
                s[byte_field] = count_bytes(newt)
        rows.append((s.get("번호", ""), s.get("이름", ""), a, removed))
        tot_conn += a["연결어미뒤"]
        tot_dot += a["가운뎃점"]
        removed_tot += removed
        if a["위반"]:
            warn_n += 1
        if a["밀도초과"]:
            dens_n += 1
        for c in hit_contexts(s.get(field) or ""):
            ctx_rows.append((s.get("이름", ""), c))

    hdr = "번호     이름        쉼표  문장  밀도   연결어미뒤  가운뎃점  판정"
    print(hdr)
    print("-" * len(hdr))
    for num, name, a, removed in rows:
        verdict = "위반" if a["위반"] else ("양호(밀도↑)" if a["밀도초과"] else "양호")
        extra = f"  (제거 -{removed})" if removed else ""
        print(f"{str(num):<8} {name:<10} {a['쉼표']:>3}  {a['문장']:>3}  "
              f"{a['밀도']:>4}   {a['연결어미뒤']:>7}   {a['가운뎃점']:>5}    {verdict}{extra}")
    print("-" * len(hdr))
    print(f"학생 {len(rows)}명 · 연결어미뒤 쉼표 총 {tot_conn}건 · 가운뎃점 총 {tot_dot}개 · 위반 {warn_n}명"
          + (f" · 밀도 참고 초과 {dens_n}명" if dens_n else "")
          + (f" · 이번에 제거 {removed_tot}건" if do_clean else ""))
    if dens_n:
        print(f"※ 밀도는 참고치다. 셋 이상을 나열하는 목록 쉼표 때문에 넘는 것은 정상이며 고치지 않아도 된다. "
              f"이 값을 맞추려고 정상적인 나열을 풀어쓰지 말 것.")
    if ctx_rows:
        print("\n[연결어미 뒤 쉼표가 걸린 자리] — 명사 오탐이면 고치지 말고 NOUN_EXC에 그 명사를 추가할 것")
        for name, c in ctx_rows:
            print(f"  {name:<8} …{c}")
    if not do_clean and tot_conn:
        print("→ 연결어미 뒤 쉼표가 남아 있음. `--clean --write`로 정리하거나 문맥에 맞게 손보고, "
              "정리 후 byte_count.py로 바이트를 재검증할 것.")
    if tot_dot:
        print("→ 가운뎃점(·)으로 나열한 곳이 있음(인공지능 흔적). '와/과'·쉼표·풀어쓰기로 바꾸고 "
              "byte_count.py로 바이트를 재검증할 것. (문맥 판단이 필요해 자동 정리하지 않음.)")

    if do_clean and write:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f"저장: {path}  (원문은 각 학생 {draft_field}에 보존 · 기록된 {byte_field} 갱신)")
    elif do_clean and not write:
        print("※ --write 없이 실행되어 파일은 저장하지 않음(미리보기).")


def main():
    ap = argparse.ArgumentParser(description="세특 쉼표·가운뎃점 점검(humanizer 패턴 1·3 + 가운뎃점 나열)")
    ap.add_argument("text", nargs="?", help="점검할 평가문 한 개")
    ap.add_argument("--json", help="students.json 경로(일괄 점검)")
    ap.add_argument("--clean", action="store_true", help="연결어미 뒤 쉼표 제거")
    ap.add_argument("--write", action="store_true", help="--clean 결과를 파일에 저장")
    ap.add_argument("--field", default="평가문",
                    help="점검할 판본 필드명. 4.5 검토본은 '평가문_검토본'")
    args = ap.parse_args()

    if args.json:
        run_json(args.json, args.clean, args.write, args.field)
    elif args.text:
        a = analyze(args.text)
        verdict = "위반" if a["위반"] else ("양호(밀도↑)" if a["밀도초과"] else "양호")
        print(f"쉼표 {a['쉼표']} / 문장 {a['문장']} / 밀도 {a['밀도']} "
              f"/ 연결어미뒤 {a['연결어미뒤']} / 가운뎃점 {a['가운뎃점']} / 판정 {verdict}")
        for c in hit_contexts(args.text):
            print(f"  걸린 자리: …{c}")
        if args.clean and a["연결어미뒤"]:
            newt, rm = clean(args.text)
            print(f"정리(-{rm}): {newt}")
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
