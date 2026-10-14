#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
students.json  ->  검수용 HTML (표형 + 검색/정렬)

각 학생의 자료(활동별), 구성 계획, 평가문, 바이트수/목표/판정을 한 표에서 정렬·검색하며 검수한다.
구성 계획(4단계)·활동 자료·제약사항은 표 안에서 펼쳐 볼 수 있어
"무엇을 증명하려 했는가 → 무엇을 근거로 삼았는가 → 실제로 그렇게 썼는가"를 한 줄에서 대조할 수 있다.
평가문 칸마다 복사 단추가 있어 NEIS 등에 바로 붙여 넣을 수 있다(클립보드 API가 막힌
로컬 파일 환경에서도 대체 방식으로 복사된다).
데이터는 HTML 안에 JSON으로 임베드되어 단일 파일로 어디서나 열린다.

품질 검토 패스(5.5단계)를 돌려 `평가문_검토본`이 들어 있으면, 원본을 덮어쓰지 않고
**원본과 검토본을 나란히** 보여준다. 상단에서 '나란히 / 원본만 / 검토본만'을 고를 수 있고
검토본 칸에는 원본과 달라진 학생에게 '수정' 표시가 붙는다.
두 판본의 **달라진 곳은 색으로 강조**한다(원본 쪽은 빠진 말에 취소선, 검토본 쪽은 들어온 말에 강조).
어디가 왜 바뀌었는지 눈으로 바로 짚을 수 있어야 검토를 승인할 수 있기 때문이다.

사용법: python build_html.py students.json 결과.html
"""
import sys
import os
import re
import json
import difflib
import html as htmllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from byte_count import count_bytes, parse_target  # noqa: E402
from evaltext import (base_text, review_text, has_review, is_changed,  # noqa: E402
                      has_plan, plan_lines)
import rawdata  # noqa: E402

# 변경 강조가 이 길이 이하의 교체 덩어리는 글자 단위로 한 번 더 좁힌다.
# (단어 단위로만 보면 '묻는 물음 → 던진 물음' 같은 한 글자 차이도 어절 통째로 칠해져 읽기 나쁘다)
REFINE_MAX = 60
REFINE_RATIO = 0.6


def _tokens(t):
    """어절 단위로 자르되 뒤따르는 공백을 붙여 둔다(합치면 원문이 그대로 복원된다)."""
    return re.findall(r"\S+\s*", t)


def _merge(ops):
    """같은 표시가 이어지면 하나로 합친다."""
    out = []
    for op, t in ops:
        if not t:
            continue
        if out and out[-1][0] == op:
            out[-1][1] += t
        else:
            out.append([op, t])
    return out


def diff_ops(a, b):
    """원본 a와 검토본 b를 비교해 (원본 표시, 검토본 표시)를 돌려준다.

    표시는 [기호, 글자] 목록이고 기호는 '='(그대로) / '-'(빠짐) / '+'(들어옴).
    글자를 모두 이으면 각각 원문과 검토본이 그대로 복원되므로 표시가 본문을 훼손하지 않는다.
    """
    ta, tb = _tokens(a), _tokens(b)
    left, right = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        A, B = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        if tag == "equal":
            left.append(["=", A])
            right.append(["=", B])
        elif tag == "delete":
            left.append(["-", A])
        elif tag == "insert":
            right.append(["+", B])
        elif (len(A) <= REFINE_MAX and len(B) <= REFINE_MAX
              and difflib.SequenceMatcher(None, A, B).ratio() > REFINE_RATIO):
            for t2, x1, x2, y1, y2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
                if t2 == "equal":
                    left.append(["=", A[x1:x2]])
                    right.append(["=", B[y1:y2]])
                else:
                    left.append(["-", A[x1:x2]])
                    right.append(["+", B[y1:y2]])
        else:
            left.append(["-", A])
            right.append(["+", B])
    return _merge(left), _merge(right)


def verdict(text, target):
    """바이트 판정. 저장된 '바이트수'는 낡았을 수 있어 항상 재계산한다."""
    n = count_bytes(text)
    lo, hi = parse_target(target)
    if not text:
        return n, "empty"
    if hi is not None and n > hi:
        return n, "over"
    if lo is not None and n < lo:
        return n, "under"
    return n, "ok"


def enrich(students):
    out = []
    for i, s in enumerate(students):
        target = s.get("목표바이트", "")
        text = base_text(s)
        n, status = verdict(text, target)
        rtext = review_text(s)
        rn, rstatus = verdict(rtext, target)
        dl, dr = diff_ops(text, rtext) if is_changed(s) else (None, None)
        out.append({
            "i": i,                       # 복사 단추가 원문을 되찾을 때 쓰는 자리(정렬·필터와 무관해야 한다)
            "번호": s.get("번호", ""),
            "이름": s.get("이름", ""),
            "성적": s.get("성적", ""),
            "제약사항": s.get("제약사항", ""),
            "활동": s.get("활동", {}) or {},
            "계획": plan_lines(s),        # [항목, 내용] 목록 — 주장·근거·순서·제외
            "목표바이트": target,
            "평가문": text,
            "바이트수": n if text else "",
            "status": status,
            "평가문_검토본": rtext,
            "바이트수_검토본": rn if rtext else "",
            "status_검토본": rstatus,
            "수정됨": is_changed(s),
            "diff_원본": dl,
            "diff_검토본": dr,
        })
    return out


def embed_json(obj) -> str:
    """<script> 안에 안전하게 넣을 JSON 직렬화.

    학생 자료(활동 내용)에 '</script>' 같은 HTML이 들어 있으면 스크립트 태그가
    조기 종료되어 페이지 전체가 깨진다. JSON에서 <, >, &는 문자열 안에서만
    나타나므로 유니코드 이스케이프로 바꿔도 값이 보존된다. U+2028/U+2029는
    구형 JS 파서에서 문자열 리터럴을 깨뜨리므로 함께 이스케이프한다.
    """
    s = json.dumps(obj, ensure_ascii=False)
    for ch, rep in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                    ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        s = s.replace(ch, rep)
    return s


TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 생활기록부 검수</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--line:#e6e8eb;--ink:#1f2328;--sub:#6b7280;--accent:#2f5496;}
  *{box-sizing:border-box}
  body{margin:0;height:100vh;height:100dvh;display:flex;flex-direction:column;
       font-family:"Pretendard","맑은 고딕","Malgun Gothic",system-ui,sans-serif;background:var(--bg);color:var(--ink)}
  header{background:var(--accent);color:#fff;padding:14px 20px;box-shadow:0 1px 6px rgba(0,0,0,.15)}
  header h1{margin:0;font-size:18px;font-weight:700}
  header .meta{font-size:13px;opacity:.9;margin-top:2px}
  .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 20px;background:#fff;border-bottom:1px solid var(--line)}
  /* 검색창(툴바 직계 input)만 늘린다 — 체크박스까지 늘어나지 않도록 자식 선택자로 좁힘 */
  .toolbar>input{flex:1;min-width:180px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:14px}
  .wrap{flex:1;min-height:0;display:flex;flex-direction:column;width:100%;max-width:1180px;margin:0 auto;padding:14px 20px 18px}
  /* 원본과 검토본을 나란히 놓으면 열이 늘어나므로 지면을 넓힌다 */
  body.rev .wrap{max-width:1560px}
  .count{font-size:13px;color:var(--sub);margin:0 0 10px}
  .pill{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px}
  .ok{background:#d9ead3;color:#274e13}.over{background:#f4cccc;color:#a61b1b}
  .under{background:#fff2cc;color:#7f6000}.empty{background:#eee;color:#888}
  /* 표 — 표 영역이 스크롤 컨테이너라서 머리글이 top:0 으로 항상 고정된다.
     (페이지 스크롤 + 고정 offset 방식은 overflow 래퍼 안에서 sticky가 무력화되어 폐기) */
  .tablewrap{flex:1;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:8px}
  table{width:100%;border-collapse:separate;border-spacing:0;font-size:13.5px}
  th,td{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}
  th:last-child,td:last-child{border-right:0}
  th{position:sticky;top:0;z-index:2;background:var(--accent);color:#fff;cursor:pointer;white-space:nowrap}
  th.plain{cursor:default}
  td.c{text-align:center;white-space:nowrap}
  td.eval{min-width:360px;line-height:1.7;white-space:pre-wrap}
  tr:nth-child(even) td{background:#fafbfc}
  .constraint{font-size:12.5px;color:#a61b1b;margin-top:6px}
  .tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;margin-bottom:5px}
  .tag.chg{background:#dbe5f1;color:#1f3864}.tag.same{background:#eee;color:#888}
  .toolbar select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;font-size:14px;background:#fff}
  .toolbar label{font-size:13px;color:var(--sub);display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
  /* 변경 강조 — 원본에서 빠진 말과 검토본에 들어온 말 */
  .del{background:#fbdcdc;color:#8f1d1d;text-decoration:line-through;text-decoration-thickness:1px;
       border-radius:3px;padding:0 1px}
  .ins{background:#d9ead3;color:#274e13;border-radius:3px;padding:0 1px;font-weight:600}
  .legend{font-size:12.5px;color:var(--sub);white-space:nowrap}
  .legend .del,.legend .ins{font-weight:600}
  @media print{.del{background:none;color:#000}.ins{background:none;color:#000;text-decoration:underline}}
  details{font-size:13px}details summary{cursor:pointer;color:var(--accent);font-weight:600}
  details+details{margin-top:6px}
  .act{margin:6px 0;padding:8px 10px;background:#f6f7f9;border-radius:6px;min-width:240px;max-width:520px;overflow-wrap:anywhere}
  .act b{display:block;color:var(--accent);margin-bottom:2px;font-size:12.5px}
  /* 구성 계획 — 무엇을 증명하려 한 글인지. 자료(회색)와 구별되게 다른 바탕을 준다 */
  .plan{margin:6px 0;padding:8px 10px;background:#fbf6e8;border-radius:6px;min-width:240px;max-width:520px;overflow-wrap:anywhere}
  .plan b{display:block;color:#7f6000;margin-bottom:2px;font-size:12.5px}
  details.plans summary{color:#7f6000}
  /* 복사 단추 — 평가문·자료·계획을 그대로 집어 갈 수 있게 */
  .copy{font-size:11px;font-weight:600;padding:2px 9px;border:1px solid var(--line);border-radius:999px;
        background:#fff;color:var(--sub);cursor:pointer;line-height:1.6;white-space:nowrap;font-family:inherit}
  .copy:hover{background:#eef2f8;color:var(--accent);border-color:#c9d4e6}
  .copy.done{background:#d9ead3;color:#274e13;border-color:#b6d7a8}
  .cell-h{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:5px;white-space:normal}
  .blk-h{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .noresult{padding:28px;text-align:center;color:var(--sub)}
  @media print{
    body{display:block;height:auto}
    .toolbar{display:none}
    .copy{display:none}
    .wrap{max-width:none}
    .tablewrap{overflow:visible;border:0}
    th{position:static}
  }
</style></head>
<body class="__BODYCLS__">
<header><h1>__TITLE__ · 생활기록부 평가문</h1><div class="meta">학생 __N__명 · 열 머리글로 정렬, 검색으로 필터, 평가문은 복사 단추로 집어 가세요</div></header>
<div class="toolbar">
  <input id="q" placeholder="이름·번호·내용 검색…" oninput="render()">
  __VIEWSEL__
  <button class="copy" onclick="cpAll(this)">보이는 평가문 모두 복사</button>
</div>
<div class="wrap">
  <div class="count" id="count"></div>
  <div class="tablewrap" id="tableView"></div>
</div>
<script>
const DATA = __DATA__;
const HAS_REVIEW = __HAS_REVIEW__;          // 검토본이 하나라도 있으면 참
const HAS_PLAN = __HAS_PLAN__;              // 구성 계획(4단계)이 하나라도 있으면 참
let SHOWN = DATA;                           // 지금 화면에 걸러져 보이는 학생 — '모두 복사'가 집는 범위
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const STAT = {ok:"적정",over:"초과",under:"미달",empty:"미작성"};
const RANK = {over:0,under:1,empty:2,ok:3};   // 판정 정렬: 문제 있는 학생부터
let view = HAS_REVIEW ? "both" : "orig";      // both | orig | review — 검토본은 원본을 덮지 않는다
let DIFF = HAS_REVIEW;                        // 바뀐 곳 색으로 강조
let onlyChanged = false;                      // 수정된 학생만 보기
function setView(v){view=v;render();}
function setDiff(on){DIFF=on;render();}
function setOnlyChanged(on){onlyChanged=on;render();}
// 보기 모드에 따라 열 구성이 달라진다. [정렬키|null, 머리글]
function cols(){
  const c=[["번호","번호"],["이름","이름"],["성적","성적"]];
  if(view!=="review") c.push([null,HAS_REVIEW?"평가문(원본)":"평가문"],["바이트수","바이트"]);
  if(HAS_REVIEW&&view!=="orig") c.push([null,"평가문(검토본)"],["바이트수_검토본","바이트"]);
  c.push([null,"목표"],["status","판정"],[null,HAS_PLAN?"계획 · 자료":"활동 자료"]);
  return c;
}
function match(s,q){if(!q)return true;q=q.toLowerCase();const hay=[s.번호,s.이름,s.제약사항,s.평가문,s.평가문_검토본,JSON.stringify(s.계획),JSON.stringify(s.활동)].join(" ").toLowerCase();return hay.includes(q);}
// ── 복사 ───────────────────────────────────────────────────────────────
// 로컬 파일(file://)에서는 클립보드 API가 막히는 브라우저가 있어 textarea 방식으로 대체한다.
function flash(btn,msg){
  if(!btn.dataset.label)btn.dataset.label=btn.textContent;
  btn.textContent=msg;btn.classList.add("done");
  clearTimeout(btn._t);btn._t=setTimeout(()=>{btn.textContent=btn.dataset.label;btn.classList.remove("done");},1200);
}
function writeClip(text,btn){
  if(!text){flash(btn,"내용 없음");return;}
  const done=()=>flash(btn,"복사됨");
  const fallback=()=>{
    const ta=document.createElement("textarea");
    ta.value=text;ta.setAttribute("readonly","");
    ta.style.cssText="position:fixed;top:0;left:0;width:1px;height:1px;opacity:0";
    document.body.appendChild(ta);ta.select();ta.setSelectionRange(0,ta.value.length);
    let ok=false;try{ok=document.execCommand("copy");}catch(e){}
    ta.remove();ok?done():flash(btn,"복사 실패");
  };
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done).catch(fallback);}
  else fallback();
}
function cpField(btn,i,f){writeClip(DATA[i][f],btn);}
function cpAct(btn){const d=btn.dataset;writeClip((DATA[d.i].활동||{})[d.k]||"",btn);}
function cpPlan(btn){
  writeClip((DATA[btn.dataset.i].계획||[]).map(([k,v])=>`[${k}] ${v}`).join("\\n"),btn);
}
// 화면에 걸러진 학생 전부를 '번호 이름 → 평가문'으로. 보기 모드에 맞는 판본을 집는다.
function cpAll(btn){
  const useR=HAS_REVIEW&&view!=="orig";
  const txt=SHOWN.map(s=>{
    const t=(useR&&s.평가문_검토본)?s.평가문_검토본:s.평가문;
    return t?`${s.번호} ${s.이름}\\n${t}`:null;
  }).filter(Boolean).join("\\n\\n");
  writeClip(txt,btn);
}
function copyBtn(js,label){return `<button class="copy" ${js}>${label||"복사"}</button>`;}
function actsHTML(s){
  const acts=Object.entries(s.활동||{}).map(([k,v])=>
    `<div class="act"><div class="blk-h"><b>${esc(k)}</b>${copyBtn(`data-i="${s.i}" data-k="${esc(k)}" onclick="cpAct(this)"`)}</div>${esc(v)}</div>`).join("");
  const plan=(s.계획&&s.계획.length)
    ? `<details class="plans"><summary>구성 계획</summary><div class="plan"><div class="blk-h"><b>이 글이 증명하려는 것</b>${copyBtn(`data-i="${s.i}" onclick="cpPlan(this)"`)}</div>`
      + s.계획.map(([k,v])=>`<div style="margin-top:4px"><b style="display:inline;color:#7f6000">${esc(k)}</b> ${esc(v)}</div>`).join("")
      + `</div></details>` : "";
  return plan+`<details><summary>활동 자료</summary>${acts||"<div class='act'>자료 없음</div>"}</details>`;
}
// 변경 강조: [기호,글자] 목록을 태그로 옮긴다. 글자를 모두 이으면 본문 그대로라 내용이 상하지 않는다.
function marked(ops,plain){
  if(!DIFF||!ops||!ops.length)return esc(plain);
  return ops.map(([op,t])=>op==="="?esc(t):`<span class="${op==="-"?"del":"ins"}">${esc(t)}</span>`).join("");
}
// 평가문 칸 — 머리에 배지와 복사 단추를 두고 본문은 그대로 둔다(복사는 강조 표시가 아닌 원문을 집는다)
function evalCell(s,field,html,con,tag){
  const head=`<div class="cell-h"><span>${tag||""}</span>${s[field]?copyBtn(`onclick="cpField(this,${s.i},'${field}')"`):""}</div>`;
  return `<td class="eval">${head}${html||"<i style='color:#aaa'>미작성</i>"}${con}</td>`;
}
function tableHTML(list){
  if(!list.length)return `<div class="noresult">검색 결과가 없습니다</div>`;
  const arrow=k=>sortKey===k?(sortAsc?" ▲":" ▼"):"";
  const C=cols();
  const ths=C.map(([k,label])=>k?`<th onclick="sortBy('${k}')">${label}${arrow(k)}</th>`
                                :`<th class="plain">${label}</th>`).join("");
  const rows=list.map(s=>{
    const con=s.제약사항?`<div class="constraint">⚠ ${esc(s.제약사항)}</div>`:"";
    // 검토본 유무와 무관하게 판정은 화면에 보이는 최종 판단 기준(검토본 우선)을 따른다
    const st=(HAS_REVIEW&&view!=="orig"&&s.평가문_검토본)?s.status_검토본:s.status;
    let td="";
    if(view!=="review") td+=evalCell(s,"평가문",marked(s.diff_원본,s.평가문),con,"")
                          + `<td class="c">${s.바이트수===""?"":s.바이트수}</td>`;
    if(HAS_REVIEW&&view!=="orig"){
      const tag=s.평가문_검토본?`<span class="tag ${s.수정됨?"chg":"same"}">${s.수정됨?"수정":"동일"}</span>`:"";
      const body=s.평가문_검토본?marked(s.diff_검토본,s.평가문_검토본):"<i style='color:#aaa'>검토 없음</i>";
      td+=evalCell(s,"평가문_검토본",body,view==="review"?con:"",tag)
        + `<td class="c">${s.바이트수_검토본===""?"":s.바이트수_검토본}</td>`;
    }
    return `<tr><td class="c">${esc(s.번호)}</td><td class="c">${esc(s.이름)}</td><td class="c">${esc(s.성적)}</td>
    ${td}<td class="c">${esc(s.목표바이트)}</td>
    <td class="c"><span class="pill ${st}">${STAT[st]||""}</span></td>
    <td>${actsHTML(s)}</td></tr>`;
  }).join("");
  return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
}
let sortKey=null,sortAsc=true;
function sortBy(k){if(sortKey===k)sortAsc=!sortAsc;else{sortKey=k;sortAsc=true;}render();}
function render(){
  const q=document.getElementById('q').value;
  let list=DATA.filter(s=>match(s,q));
  if(onlyChanged) list=list.filter(s=>s.수정됨);
  if(sortKey){list=[...list].sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
    if(sortKey==="status"){x=RANK[x];y=RANK[y];}
    else if(!isNaN(parseFloat(x))&&!isNaN(parseFloat(y))){x=+x;y=+y;}
    return (x>y?1:x<y?-1:0)*(sortAsc?1:-1);});}
  SHOWN=list;
  const useR=HAS_REVIEW&&view!=="orig";
  const n={ok:0,over:0,under:0,empty:0};
  list.forEach(s=>n[(useR&&s.평가문_검토본)?s.status_검토본:s.status]++);
  const chg=HAS_REVIEW?` · 검토 수정 ${list.filter(s=>s.수정됨).length}명`:"";
  document.getElementById('count').textContent=
    `표시: ${list.length}명 · 적정 ${n.ok} · 초과 ${n.over} · 미달 ${n.under} · 미작성 ${n.empty}${chg}`;
  document.getElementById('tableView').innerHTML=tableHTML(list);
}
render();
</script>
</body></html>"""


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: python build_html.py students.json 결과.html")
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    students = data.get("students", data if isinstance(data, list) else [])
    # 활동 원문은 students.json에 복사해 두지 않고 `원자료` 파일에서 가져온다(3단계 산출·불변)
    nraw, rawp = rawdata.attach(src, data)
    if nraw:
        print(f"원자료 연결: {os.path.basename(rawp)} → 학생 {nraw}명의 활동 원문 사용")
    subject = data.get("subject", "생활기록부")
    rows = enrich(students)
    hasrev = has_review(students)
    viewsel = ("""<label for="view">보기</label>
  <select id="view" onchange="setView(this.value)">
    <option value="both">원본과 검토본 나란히</option>
    <option value="orig">원본만</option>
    <option value="review">검토본만</option>
  </select>
  <label><input type="checkbox" checked onchange="setDiff(this.checked)">변경 강조</label>
  <label><input type="checkbox" onchange="setOnlyChanged(this.checked)">수정된 학생만</label>
  <span class="legend"><span class="del">빠진 말</span> <span class="ins">들어온 말</span></span>""" if hasrev else "")
    html = (TEMPLATE
            .replace("__TITLE__", htmllib.escape(subject))
            .replace("__N__", str(len(rows)))
            .replace("__VIEWSEL__", viewsel)
            .replace("__BODYCLS__", "rev" if hasrev else "")
            .replace("__HAS_REVIEW__", "true" if hasrev else "false")
            .replace("__HAS_PLAN__", "true" if has_plan(students) else "false")
            .replace("__DATA__", embed_json(rows)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    nchg = sum(1 for r in rows if r["수정됨"])
    extra = f", 검토본 수정 {nchg}명" if hasrev else ""
    print(f"저장 완료: {out}  (학생 {len(rows)}명{extra})")


if __name__ == "__main__":
    main()
