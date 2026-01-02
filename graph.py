from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, Sequence, Any
from pathlib import Path
from functools import lru_cache
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()
PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _env_candidates(prefixes: Sequence[str], suffix: str) -> list[str]:
    """接頭辞とサフィックスの組み合わせから、環境変数名の候補一覧を生成する。"""
    return [f"{prefix}_{suffix}" for prefix in prefixes]


def _get_env_value(candidates: Sequence[str], label: str, required: bool = True) -> str | None:
    """候補群から最初に見つかった環境変数値を返し、必須指定なら未設定時に例外を投げる。"""
    for name in candidates:
        value = os.getenv(name)
        if value:
            return value
    if required:
        raise RuntimeError(
            f"{label} が設定されていません。以下のいずれかの環境変数を設定してください: {', '.join(candidates)}"
        )
    return None


def _build_azure_llm(*prefixes: str) -> AzureChatOpenAI:
    """複数の接頭辞を許容しながらAzureChatOpenAIインスタンスを構築する。"""
    api_version = _get_env_value(
        ["API_VERSION", "AZURE_OPENAI_API_VERSION",
            "OPENAI_API_VERSION"], "Azure API version"
    )
    endpoint = _get_env_value(_env_candidates(
        prefixes, "ENDPOINT"), f"{prefixes[0]} endpoint")
    deployment = _get_env_value(
        _env_candidates(prefixes, "DEPLOYMENT_NAME") +
        _env_candidates(prefixes, "DEPLOYMENT"),
        f"{prefixes[0]} deployment name",
    )
    api_key = _get_env_value(
        _env_candidates(prefixes, "SUBSCRIPTION_KEY") +
        _env_candidates(prefixes, "API_KEY"),
        f"{prefixes[0]} subscription key",
    )
    model_name = _get_env_value(
        _env_candidates(prefixes, "MODEL")
        + _env_candidates(prefixes, "MODEL_NAME")
        + _env_candidates(prefixes, "TIKTOKEN_MODEL_NAME"),
        f"{prefixes[0]} model name",
        required=False,
    )

    llm_kwargs = dict(
        api_version=api_version,
        azure_endpoint=endpoint,
        azure_deployment=deployment,
        api_key=api_key,
    )
    if model_name:
        llm_kwargs["model"] = model_name

    return AzureChatOpenAI(**llm_kwargs)


llm5_mini = _build_azure_llm("GPT_5_MINI")
llm5_1 = _build_azure_llm("GPT_5_1", "GPT_5.1")


def _to_text(value: Any) -> str:
    """LLMからの多様な返却形式（リスト/辞書など）を表示用の文字列に正規化する。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_to_text(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(f"- {key}: {_to_text(val)}" for key, val in value.items())
    return str(value)


def _apply_seo_title(article: str, title: str) -> str:
    lines = article.splitlines()
    heading = f"# {title}"
    if not lines:
        return heading
    if lines[0].startswith("#"):
        lines[0] = heading
    else:
        lines.insert(0, heading)
    return "\n".join(lines)


def _sanitize_article(article: str) -> str:
    forbidden_prefixes = [
        "結論：",
        "再結論：",
        "接続詞：",
        "文末：",
        "無駄語排除：",
        "要点先出し：",
        "漢字ひらがなバランス：",
        "校正：",
    ]
    sanitized_lines = []
    for line in article.splitlines():
        stripped = line.lstrip()
        for prefix in forbidden_prefixes:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].lstrip()
        leading_spaces = len(line) - len(line.lstrip())
        sanitized_lines.append(" " * leading_spaces + stripped)
    return "\n".join(sanitized_lines)


class ArticleState(TypedDict):
    theme: str
    draft: str
    sections: dict[str, str]
    notes: dict[str, str]
    diagrams: dict[str, str]
    article: str
    seo_title: str


def generate_draft(state: ArticleState) -> dict:
    """感情フックと構成の骨子を織り交ぜた初稿を生成する。"""
    system_prompt = SystemMessage(content=_load_prompt("draft_system.txt"))
    human_prompt_content = _load_prompt("draft_human.txt").format(
        theme=state["theme"]
    )
    human_prompt = HumanMessage(content=human_prompt_content)

    draft = llm5_mini.invoke([system_prompt, human_prompt]).content
    return {"draft": draft}


def split_sections(state: ArticleState) -> dict:
    """初稿をJSON形式で書き出し・本文・まとめに分割する。"""
    prompt_template = _load_prompt("split_sections.txt")
    prompt = prompt_template.format(article=state["draft"])
    res = llm5_mini.invoke(prompt).content
    match = re.search(r"\{[\s\S]*\}", res)
    if not match:
        raise ValueError("JSON形式の出力が見つかりませんでした。")
    sections = json.loads(match.group())

    return {"sections": sections}


def fact_check(state: ArticleState) -> dict:
    """各セクションを厳密にファクトチェックし、指摘メモを蓄積する。"""

    notes = {}
    prompt_template = _load_prompt("fact_check.txt")
    for title, body in state["sections"].items():
        prompt = prompt_template.format(body=body)
        res = llm5_mini.invoke([
            SystemMessage(content="あなたは厳密なファクトチェッカーです"),
            HumanMessage(content=prompt)
        ])
        notes[title] = res.content
    return {"notes": notes}


def revise_sections(state: ArticleState) -> dict:
    """ファクトチェック結果だけを反映し、構成を崩さずに本文を修正する。"""
    sections = {}
    prompt_template = _load_prompt("revise_sections.txt")
    for title, body in state["sections"].items():
        feedback = state.get("notes", {}).get(title, "")
        if not feedback:
            sections[title] = body
            continue
        prompt = prompt_template.format(body=body, feedback=feedback)
        sections[title] = _to_text(llm5_mini.invoke(prompt).content).strip()
    return {"sections": sections}


def generate_diagrams(state: ArticleState) -> dict:
    """各セクションの要点をMermaidフローチャートとして生成する。"""
    diagrams = {}
    prompt_template = _load_prompt("diagram.txt")
    for title, body in state["sections"].items():
        prompt = prompt_template.format(body=body)
        diagram = llm5_mini.invoke(prompt).content.strip()
        diagram = diagram.replace("(", "[").replace(")", "]")
        diagrams[title] = diagram
    return {"diagrams": diagrams}


def generate_seo_title(state: ArticleState) -> dict:
    """SEOを意識したタイトルを生成し、記事本文の先頭に差し込む。"""
    prompt = _load_prompt("title.txt").format(
        theme=state["theme"],
        article=state["article"],
    )
    response = llm5_mini.invoke(prompt).content.strip()
    title = response.splitlines()[0].strip("# ").strip()
    article = _apply_seo_title(state["article"], title)
    return {"seo_title": title, "article": article}


def merge_article(state: ArticleState) -> dict:
    """磨き込んだセクションを無料/有料構成の本文へ統合する。"""
    order = ["書き出し", "本文", "まとめ"]
    sections = sorted(
        state["sections"].items(),
        key=lambda item: order.index(
            item[0]) if item[0] in order else len(order),
    )
    if not sections:
        return {"article": ""}

    diagrams = state.get("diagrams", {})
    parts = [
        f"# {state['theme']}：有料noteで読む価値",
        "ここでは代表読者の課題と感情を共有しつつ、『考え方』だけでは解けない疑問を残します。具体的な数値・手順・テンプレートは有料エリアで開示します。",
    ]

    free_title, free_body = sections[0]
    free_display = "書き出し：読者のベネフィット" if "書き出し" in free_title else free_title
    parts.append(f"### {free_display}")
    parts.append(_to_text(free_body))
    if free_title in diagrams:
        parts.append("```mermaid")
        parts.append(diagrams[free_title])
        parts.append("```")

    premium_sections = sections[1:]
    if premium_sections:
        parts.extend(
            [
                "---",
                "## ここから先は有料エリア（購読者限定）",
                f"ここまでは考え方、ここからは数字と手順。無料パートで残した問いに、実データと再現可能なテンプレで答えます。",
            ]
        )
        for title, body in premium_sections:
            original_title = title
            if "本文" in title:
                title = "本文：準備→論理構成→ライティングコツ"
            elif "まとめ" in title:
                title = "まとめ：PREP再結論と次アクション"
            parts.append(f"### {title}")
            parts.append(_to_text(body))
            if original_title in diagrams:
                parts.append("```mermaid")
                parts.append(diagrams[original_title])
                parts.append("```")

        parts.extend(
            [
                "### 今日すぐ試せる一歩",
                "1. 有料パートで示した手順のうち、最も簡単な工程を今日中に1回だけ試してください。完璧なCSVではなく、3項目だけのメモで十分です。",
                "2. 実施前後の数値（体調・指標など）を同じ条件で記録し、48時間以内に差分を確認してください。",
                "3. 差分を有料パートで配布するテンプレートに入力し、次の改善サイクルに備えてください。",
                "### 付録：購読者限定の具体物",
                "- 進捗ログを自動集計するスプレッドシート（入力は3項目・1分で完了、毎週の報告準備を平均30分短縮）",
                "- 失敗パターン別リカバリ手順PDF（想定外のトラブルを最大3回まで先回りで回避）",
                "- ケーススタディ動画リンク（約15分、行動前後の思考整理を一発で学べます）",
            ]
        )

    parts.extend(
        [
            "## 読者が得られるもの",
            "- 主テーマに絞った一次体験と第三者データのセットで再現性を判断できること",
            "- すぐに記入できるチェックリストとログテンプレートが手に入ること",
            "- ありがちな失敗とリカバリ策を事前に把握し、意思決定の速度を上げられること",
            "## 次のアクション",
            "どの項目で詰まったか（データ取得/テンプレ活用/リカバリ）だけコメントで教えてください。必要なデータやテンプレを優先的に追加します。",
        ]
    )

    article_body = "\n\n".join(parts)
    return {"article": _sanitize_article(article_body)}


def build_graph() -> StateGraph[ArticleState]:
    """Socket.IOが利用するLangGraphパイプラインを構築してコンパイルする。"""

    graph = StateGraph(ArticleState)

    graph.add_node("draft", generate_draft)
    graph.add_node("split", split_sections)
    graph.add_node("fact", fact_check)
    graph.add_node("revise", revise_sections)
    graph.add_node("diagram", generate_diagrams)
    graph.add_node("merge", merge_article)
    graph.add_node("title", generate_seo_title)

    graph.set_entry_point("draft")

    graph.add_edge("draft", "split")
    graph.add_edge("split", "fact")
    graph.add_edge("fact", "revise")
    graph.add_edge("revise", "diagram")
    graph.add_edge("diagram", "merge")
    graph.add_edge("merge", "title")
    graph.add_edge("title", END)

    return graph.compile()
