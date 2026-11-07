#!/usr/bin/env python3
"""국내 여행 추천 프로그램 (LLM API + 지도 API 조합).

흐름:  날짜 입력 -> [1] LLM 1차 추천(JSON) -> [2] 지도 API 맛집 검색 -> [3] LLM 최종 리포트(Markdown)
       -> results/ 에 원본 JSON + Markdown + HTML 저장

사용 예:
  python travel_planner.py -date "2026-03-15"
  python travel_planner.py --date 2026-03-15 --cities 3
  python travel_planner.py --date 2026-03-15 --mock         # API 키 없이 흐름 확인
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from planner.config import load_settings, missing_keys, setup_guide
from planner.errors import EMPTY_RESULT, ErrorLog
from planner.llm import GeminiClient, OpenAIClient, RecommendationError, recommend
from planner.mock import MockLLM, MockPlaces
from planner.places import KakaoPlaces, search_all
from planner.report import build_report_payload, finalize_markdown, generate_report, render_html

SCHEMA_VERSION = 1


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"날짜 형식이 올바르지 않습니다: '{value}' (YYYY-MM-DD 형식, 예: 2026-03-15)"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 입력하면 LLM이 국내 여행지를 추천하고, 지도 API로 맛집을 찾아 리포트를 만듭니다.",
        epilog='예: python travel_planner.py -date "2026-03-15"',
    )
    p.add_argument("-date", "--date", dest="date", type=parse_date, required=True,
                   metavar="YYYY-MM-DD", help="여행 날짜 (필수)")
    p.add_argument("--cities", type=int, choices=[1, 2, 3], default=1,
                   help="추천받을 지역 수 (기본 1, 보너스: 2~3)")
    p.add_argument("--places", type=int, default=5, metavar="N",
                   help="지역당 맛집 검색 개수 (기본 5, 최대 15)")
    p.add_argument("--out-dir", default="results", help="결과 저장 폴더 (기본 results)")
    p.add_argument("--no-cache", action="store_true",
                   help="같은 날짜의 저장된 결과가 있어도 API를 다시 호출")
    p.add_argument("--mock", nargs="?", const="all", choices=["all", "llm", "places"],
                   help="API 키 없이 예시 데이터로 실행 (all|llm|places, 값 생략 시 all)")
    return p


def mock_parts(mock: str | None) -> tuple[bool, bool]:
    return mock in ("all", "llm"), mock in ("all", "places")


# ---------------------------------------------------------------------------
# 캐시 (보너스): 같은 날짜/옵션의 원본 JSON이 있으면 API 호출을 건너뛴다.
# ---------------------------------------------------------------------------

def load_cache(path: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    if args.no_cache or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("  (캐시 파일을 읽을 수 없어 새로 생성합니다)")
        return None
    meta = data.get("meta", {})
    if (
        meta.get("schema_version") != SCHEMA_VERSION
        or meta.get("mock") != args.mock
        or meta.get("num_cities") != args.cities
        or meta.get("places_per_city") != args.places
        or not data.get("report_markdown")
    ):
        return None
    # 이전 실행이 오류로 '데이터 없음' 처리됐다면 캐시를 쓰지 않는다 (키를 고친 뒤 재실행하는 경우 등)
    if any(e.get("type") != EMPTY_RESULT for e in data.get("errors", [])):
        print("  (이전 실행에 오류가 있어 캐시를 사용하지 않고 새로 호출합니다)")
        return None
    return data


def write_outputs(out_dir: Path, d: date, raw: dict[str, Any], report_md: str) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = d.isoformat()
    json_path = out_dir / f"{stem}_raw.json"
    md_path = out_dir / f"{stem}_travel_plan.md"
    html_path = out_dir / f"{stem}_travel_plan.html"

    final_md = finalize_markdown(report_md, raw["errors"])
    meta = raw["meta"]
    meta_line = (
        f"생성: {meta['generated_at']} · LLM: {meta['llm']} · 지도: {meta['places']}"
        + (" · 원본: " + json_path.name)
    )
    json_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(final_md, encoding="utf-8")
    html_path.write_text(
        render_html(final_md, f"{stem} 국내 여행 추천 리포트", meta_line, mock=bool(meta["mock"])),
        encoding="utf-8",
    )
    return json_path, md_path, html_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)  # 날짜 형식 오류 시 사용법 출력 후 종료(exit 2)
    args.places = max(1, min(args.places, 15))
    d: date = args.date
    out_dir = Path(args.out_dir)
    json_path = out_dir / f"{d.isoformat()}_raw.json"

    cached = load_cache(json_path, args)
    if cached:
        print(f"캐시 사용: {json_path} (API 호출 생략, --no-cache 로 새로 생성 가능)")
        cached["meta"]["cache_hit_at"] = datetime.now().isoformat(timespec="seconds")
        _, md_path, html_path = write_outputs(out_dir, d, cached, cached["report_markdown"])
        print(f"\n완료! {md_path} 를 확인하세요.")
        print(f"      HTML: {html_path}")
        return 0

    # API 키 확인: 없으면 즉시 종료 + 설정 방법 안내
    settings = load_settings()
    mock_llm, mock_places = mock_parts(args.mock)
    missing = missing_keys(settings, need_llm=not mock_llm, need_places=not mock_places)
    if missing:
        print(setup_guide(missing), file=sys.stderr)
        return 1

    if mock_llm:
        llm = MockLLM()
    elif settings.llm_provider == "openai":
        llm = OpenAIClient(settings.openai_api_key, settings.openai_model, settings.timeout)
    else:
        llm = GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.timeout)
    places_client = MockPlaces() if mock_places else KakaoPlaces(settings.kakao_rest_api_key, settings.timeout)

    if args.mock:
        print(f"[MOCK 모드: {args.mock}] 예시 데이터를 사용합니다.\n")

    errors = ErrorLog()
    raw: dict[str, Any] = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "date": d.isoformat(),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "llm": llm.name,
            "places": places_client.name,
            "mock": args.mock,
            "num_cities": args.cities,
            "places_per_city": args.places,
        },
        "recommendation": None,
        "restaurants": [],
        "errors": [],
        "report_markdown": None,
        "report_source": None,
    }

    # [1/3] 1차 추천
    print("[1/3] 1차 추천 생성 중(LLM)...")
    try:
        rec = recommend(llm, d, args.cities, errors)
    except RecommendationError as exc:
        print(f"    - 오류: {exc}", file=sys.stderr)
        print("    - 추천 지역이 없어 다음 단계를 진행할 수 없습니다.", file=sys.stderr)
        raw["errors"] = errors.to_list()
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n실패. 오류 내역: {json_path}", file=sys.stderr)
        return 1
    raw["recommendation"] = rec
    cities = [c["city"] for c in rec["recommended_cities"]]
    if len(cities) == 1:
        print(f'    - recommended_city: "{cities[0]}"')
    else:
        print("    - recommended_cities: " + ", ".join(f'"{c}"' for c in cities))

    # [2/3] 맛집 검색 (실패해도 계속 진행)
    print("[2/3] 맛집 검색 중(지도/장소 API)...")
    raw["restaurants"] = search_all(places_client, cities, args.places, errors)

    # [3/3] 최종 리포트
    print("[3/3] 최종 리포트 생성 중(LLM)...")
    payload = build_report_payload(rec, raw["restaurants"])
    report_md, source = generate_report(llm, d, payload, errors)
    print("    - 리포트 생성 완료" + (" (템플릿 대체본)" if source == "template" and not mock_llm else ""))

    raw["errors"] = errors.to_list()
    raw["report_markdown"] = report_md
    raw["report_source"] = source

    json_path, md_path, html_path = write_outputs(out_dir, d, raw, report_md)
    print(f"\n완료! {md_path} 를 확인하세요.")
    print(f"      HTML: {html_path}")
    print(f"      원본 JSON: {json_path}")
    if errors:
        print(f"      (오류 {len(errors)}건 - 리포트의 '오류 요약' 섹션 참고)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n중단되었습니다.", file=sys.stderr)
        sys.exit(130)
