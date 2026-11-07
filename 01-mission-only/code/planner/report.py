"""최종 리포트: LLM으로 Markdown 생성 -> 검증 -> 오류 섹션 부착 -> HTML 변환."""

from __future__ import annotations

import html
import json
import re
from datetime import date
from typing import Any

from .errors import VALIDATION_ERROR, APIError, ErrorLog
from .llm import LLMClient, describe_date

REQUIRED_HEADINGS = [
    "## 추천 지역",
    "## 추천 이유",
    "## 날씨 요약",
    "## 행사/축제",
    "## 맛집 추천",
    "## 1일 일정 제안",
]
ERRORS_HEADING = "## 오류 요약(errors)"
NO_DATA = "데이터 없음"

DATA_BEGIN = "<<<DATA_JSON"
DATA_END = "DATA_JSON>>>"

REPORT_SYSTEM = (
    "당신은 국내 여행 리포트를 작성하는 에디터입니다. "
    "주어진 데이터만 근거로 한국어 Markdown 리포트를 작성합니다. "
    "데이터에 없는 맛집 이름이나 주소를 지어내지 않습니다."
)


def _no_data_reason(place: dict[str, Any]) -> str:
    if place.get("status") == "empty":
        return "장소 검색 결과 0건"
    if place.get("status") == "error":
        return f"장소 검색 실패: {place.get('error', 'UNKNOWN')}"
    return "장소 검색을 수행하지 못함"


def build_report_payload(rec: dict[str, Any], places: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM에 넘길 입력 데이터. 맛집은 리포트에 필요한 필드만 추린다."""
    by_city = {p["city"]: p for p in places}
    cities = []
    for c in rec["recommended_cities"]:
        p = by_city.get(c["city"], {"status": "error", "error": "NOT_SEARCHED", "items": []})
        cities.append(
            {
                **c,
                "restaurants": [
                    {k: r.get(k, "") for k in ("name", "category", "address", "url")}
                    for r in p.get("items", [])
                ],
                "restaurants_note": "" if p.get("items") else f"{NO_DATA} ({_no_data_reason(p)})",
            }
        )
    return {"cities": cities}


def build_report_prompt(d: date, payload: dict[str, Any]) -> str:
    multi = len(payload["cities"]) > 1
    multi_rule = (
        "- 도시가 여러 개이므로 '## 추천 지역'에는 모든 도시를 나열하고, "
        "'## 추천 이유', '## 날씨 요약', '## 행사/축제', '## 맛집 추천', '## 1일 일정 제안' 안에서는 "
        "'### 도시명' 소제목으로 도시별로 나누세요.\n"
        if multi
        else ""
    )
    return f"""여행 날짜: {describe_date(d)}

아래 데이터로 여행 리포트를 Markdown으로 작성하세요.

{DATA_BEGIN}
{json.dumps(payload, ensure_ascii=False, indent=2)}
{DATA_END}

형식 규칙:
- 첫 줄은 "# {d.isoformat()} 국내 여행 추천 리포트"
- 다음 제목(##)을 이 순서 그대로, 글자 하나 바꾸지 말고 모두 포함하세요:
{chr(10).join("  " + h for h in REQUIRED_HEADINGS)}
{multi_rule}- '## 추천 이유'는 reason을 2~3문장으로 요약하세요.
- '## 행사/축제'는 events를 글머리표 목록으로 쓰세요.
- '## 맛집 추천'은 restaurants를 글머리표로 "**이름** (카테고리) - 주소 - [지도](url)" 형식으로 쓰세요.
  restaurants가 비어 있으면 restaurants_note 문구를 "- 데이터 없음 (...)" 형태로 그대로 쓰세요.
- '## 1일 일정 제안'은 **오전 / 오후 / 저녁**으로 나눠 쓰고, 가능하면 위 맛집을 식사 장소로 활용하세요.
- 오류 섹션은 쓰지 마세요(프로그램이 따로 붙입니다). 코드블록(```)으로 감싸지 마세요."""


def template_report(d: date, payload: dict[str, Any]) -> str:
    """LLM 없이 데이터만으로 만드는 리포트. (mock 모드, LLM 리포트 실패 시 대체본)"""
    cities = payload["cities"]
    multi = len(cities) > 1
    lines = [f"# {d.isoformat()} 국내 여행 추천 리포트", ""]

    lines += ["## 추천 지역", ""]
    lines += [f"- **{c['city']}**" for c in cities] + [""]

    def per_city(heading: str, render) -> None:
        lines.extend([heading, ""])
        for c in cities:
            if multi:
                lines.extend([f"### {c['city']}", ""])
            lines.extend(render(c))
            lines.append("")

    per_city("## 추천 이유", lambda c: [c["reason"]])
    per_city("## 날씨 요약", lambda c: [c["weather"]])
    per_city("## 행사/축제", lambda c: [f"- {e}" for e in c["events"]])

    def restaurants(c):
        if not c["restaurants"]:
            return [f"- {c['restaurants_note']}"]
        out = []
        for r in c["restaurants"]:
            item = f"- **{r['name']}**"
            if r.get("category"):
                item += f" ({r['category']})"
            if r.get("address"):
                item += f" - {r['address']}"
            if r.get("url"):
                item += f" - [지도]({r['url']})"
            out.append(item)
        return out

    per_city("## 맛집 추천", restaurants)

    def schedule(c):
        rs = [r["name"] for r in c["restaurants"]]
        lunch = f"**{rs[0]}**에서 점심" if rs else "현지 식당에서 점심"
        dinner = f"**{rs[1]}**에서 저녁 식사" if len(rs) > 1 else "현지 식당에서 저녁 식사"
        event = c["events"][0] if c["events"] else "주요 명소"
        return [
            f"- **오전**: {c['city']} 대표 명소 산책으로 하루 시작",
            f"- **오후**: {lunch} 후 {event} 둘러보기",
            f"- **저녁**: {dinner}, 야경 감상 후 휴식",
        ]

    per_city("## 1일 일정 제안", schedule)
    return "\n".join(lines).rstrip() + "\n"


def _clean_markdown(text: str) -> str:
    text = text.strip()
    fence = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # LLM이 오류 섹션을 써버렸다면 잘라낸다 (실제 오류는 프로그램이 붙임)
    text = re.split(r"^##\s*오류 요약.*$", text, maxsplit=1, flags=re.MULTILINE)[0]
    return text.rstrip() + "\n"


def missing_headings(md: str) -> list[str]:
    present = {line.strip() for line in md.splitlines()}
    return [h for h in REQUIRED_HEADINGS if h not in present]


def generate_report(
    client: LLMClient, d: date, payload: dict[str, Any], errors: ErrorLog
) -> tuple[str, str]:
    """(markdown, source) 반환. source는 'llm' 또는 'template'."""
    try:
        md = _clean_markdown(client.complete(REPORT_SYSTEM, build_report_prompt(d, payload)))
    except APIError as exc:
        errors.add("report", exc.type, f"{exc.message} - 템플릿 리포트로 대체")
        print(f"    - 오류: {exc.type} - {exc.message}")
        print("    - 데이터 기반 템플릿 리포트로 대체합니다.")
        return template_report(d, payload), "template"

    missing = missing_headings(md)
    if missing:
        errors.add("report", VALIDATION_ERROR, f"필수 섹션 누락: {', '.join(missing)} - 템플릿 리포트로 대체")
        print(f"    - 필수 섹션 누락({', '.join(missing)}), 템플릿 리포트로 대체합니다.")
        return template_report(d, payload), "template"
    return md, "llm"


def errors_section(errors: list[dict[str, str]]) -> str:
    lines = [ERRORS_HEADING, ""]
    if not errors:
        lines.append("- 없음")
    else:
        lines += ["| 단계 | 유형 | 메시지 |", "| --- | --- | --- |"]
        for e in errors:
            msg = e["message"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {e['step']} | {e['type']} | {msg} |")
    return "\n".join(lines) + "\n"


def finalize_markdown(md: str, errors: list[dict[str, str]]) -> str:
    return _clean_markdown(md) + "\n" + errors_section(errors)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --accent: #2f6fde; --bg: #f5f7fb; --card: #fff; --text: #1f2430; --muted: #6b7280; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
         line-height: 1.7; }}
  main {{ max-width: 860px; margin: 40px auto; padding: 40px 48px; background: var(--card);
          border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.06); }}
  h1 {{ margin-top: 0; font-size: 1.9rem; border-bottom: 3px solid var(--accent); padding-bottom: .4em; }}
  h2 {{ margin-top: 2.2em; font-size: 1.35rem; color: var(--accent); }}
  h3 {{ margin-top: 1.4em; font-size: 1.1rem; }}
  a {{ color: var(--accent); }}
  ul {{ padding-left: 1.3em; }}
  li {{ margin: .25em 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
  th, td {{ border: 1px solid #e3e7ef; padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #eef3fd; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-top: 3em; border-top: 1px solid #eee; padding-top: 1em; }}
  .badge {{ display: inline-block; background: #fff4d6; color: #8a6100; border-radius: 6px; padding: 2px 8px;
            font-size: .8rem; margin-bottom: 1em; }}
  @media (max-width: 640px) {{ main {{ margin: 0; border-radius: 0; padding: 24px 20px; }} }}
</style>
</head>
<body>
<main>
{badge}
{body}
<p class="meta">{meta}</p>
</main>
</body>
</html>
"""


def _fallback_md_to_html(md: str) -> str:
    """markdown 패키지가 없을 때를 위한 아주 단순한 변환기."""
    out, in_list = [], False

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        return s

    for line in md.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        is_item = re.match(r"^\s*[-*]\s+(.*)", line)
        if in_list and not is_item:
            out.append("</ul>")
            in_list = False
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif is_item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(is_item.group(1))}</li>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def render_html(md: str, title: str, meta: str, *, mock: bool = False) -> str:
    try:
        import markdown  # type: ignore

        body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    except ImportError:
        body = _fallback_md_to_html(md)
    # 맛집 지도 링크는 새 탭으로 열리게
    body = body.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')
    badge = '<span class="badge">MOCK 모드 - 예시 데이터로 생성된 리포트입니다</span>' if mock else ""
    return HTML_TEMPLATE.format(
        title=html.escape(title), body=body, meta=html.escape(meta), badge=badge
    )
