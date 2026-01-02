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
    """Return possible env var names for the given prefixes and suffix."""
    return [f"{prefix}_{suffix}" for prefix in prefixes]


def _get_env_value(candidates: Sequence[str], label: str, required: bool = True) -> str | None:
    """Return the first non-empty env var among candidates or raise if required."""
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
    """Create an AzureChatOpenAI instance using multiple possible env prefixes."""
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
    """Normalize various LLM return shapes (list/dict/etc.) into a printable string."""
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
    system_prompt = SystemMessage(content=_load_prompt("draft_system.txt"))
    human_prompt_content = _load_prompt("draft_human.txt").format(
        theme=state["theme"]
    )
    human_prompt = HumanMessage(content=human_prompt_content)

    draft = llm5_mini.invoke([system_prompt, human_prompt]).content
    return {"draft": draft}


def split_sections(state: ArticleState) -> dict:
    prompt_template = _load_prompt("split_sections.txt")
    prompt = prompt_template.format(article=state["draft"])
    res = llm5_mini.invoke(prompt).content
    match = re.search(r"\{[\s\S]*\}", res)
    if not match:
        raise ValueError("JSON形式の出力が見つかりませんでした。")
    sections = json.loads(match.group())

    return {"sections": sections}


def fact_check(state: ArticleState) -> dict:

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
    diagrams = {}
    prompt_template = _load_prompt("diagram.txt")
    for title, body in state["sections"].items():
        prompt = prompt_template.format(body=body)
        diagram = llm5_mini.invoke(prompt).content.strip()
        diagram = diagram.replace("(", "[").replace(")", "]")
        diagrams[title] = diagram
    return {"diagrams": diagrams}


def generate_seo_title(state: ArticleState) -> dict:
    prompt = _load_prompt("title.txt").format(
        theme=state["theme"],
        article=state["article"],
    )
    response = llm5_mini.invoke(prompt).content.strip()
    title = response.splitlines()[0].strip("# ").strip()
    article = _apply_seo_title(state["article"], title)
    return {"seo_title": title, "article": article}


def merge_article(state: ArticleState) -> dict:
    order = ["書き出し", "本文", "まとめ"]
    sections = sorted(
        state["sections"].items(),
        key=lambda item: order.index(
            item[0]) if item[0] in order else len(order),
    )
    if not sections:
        return {"article": ""}

    diagrams = state.get("diagrams", {})
    parts = []

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

    article_body = "\n\n".join(parts)
    return {"article": _sanitize_article(article_body)}


def build_graph() -> StateGraph[ArticleState]:

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
