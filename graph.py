from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, Sequence
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()


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
        ["API_VERSION", "AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"], "Azure API version"
    )
    endpoint = _get_env_value(_env_candidates(prefixes, "ENDPOINT"), f"{prefixes[0]} endpoint")
    deployment = _get_env_value(
        _env_candidates(prefixes, "DEPLOYMENT_NAME") + _env_candidates(prefixes, "DEPLOYMENT"),
        f"{prefixes[0]} deployment name",
    )
    api_key = _get_env_value(
        _env_candidates(prefixes, "SUBSCRIPTION_KEY") + _env_candidates(prefixes, "API_KEY"),
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


class ArticleState(TypedDict):
    theme: str
    draft: str
    sections: dict[str, str]
    notes: dict[str, str]
    diagrams: dict[str, str]
    article: str


def generate_draft(state: ArticleState) -> dict:
    system_prompt = SystemMessage(
        content=(
            "あなたは有料noteで課金される深掘りテック記事の編集長です。"
            "読者は初級〜中級のエンジニアで、歴史的背景から現代の実務までをつなぐ洞察を求めています。"
            "リード文ではベネフィットを明示し、中盤以降は具体的なタイムライン、事例、学びを盛り込み、"
            "最後に有料購読で得られる価値を打ち出してください。"
        )
    )
    human_prompt = HumanMessage(
        content=f"""
        「{state['theme']}」というテーマで、有料note向けの草稿を作成してください。

        【アウトライン要件】
        - 3〜4個の大見出し（##）を含め、それぞれ300文字以上で具体的に書く
        - 導入では「誰に何の価値があるか」「今読む理由」を短く提示する
        - 少なくとも1つのタイムライン、1つの事例、1つの実践アドバイスを含める
        - セクション名は内容を的確に表す日本語タイトルにし、「見出し1」等は禁止

        【トーン】
        - 読者目線で親しみやすく、しかし専門家としての確信を持つ語り口
        - 初心者にも理解できるように歴史的事実と現代的な示唆を結びつける

        【出力形式】
        - Markdown。タイトル行、続いて複数のセクションを配置する。
        - 箇条書きや番号付きリストを適宜利用して読みやすくする。
        """
    )

    draft = llm5_mini.invoke([system_prompt, human_prompt]).content
    return {"draft": draft}


def split_sections(state: ArticleState) -> dict:
    prompt = f"""
    以下の記事を見出し単位で分割してください。

    【制約】
    - 見出しは最大3つ
    - 出力はJSONのみ
    - 説明文は禁止
    - 見出し名は内容を要約した日本語タイトル（10文字以上）にする
    - 「見出し1」「セクションA」などのプレースホルダは禁止

    形式:
    {{
    "見出し1": "本文",
    "見出し2": "本文"
    }}

    記事:
    {state['draft']}
    """
    res = llm5_mini.invoke(prompt).content
    match = re.search(r"\{[\s\S]*\}", res)
    if not match:
        raise ValueError("JSON形式の出力が見つかりませんでした。")
    sections = json.loads(match.group())

    return {"sections": sections}


def fact_check(state: ArticleState) -> dict:

    notes = {}
    for title, body in state["sections"].items():
        prompt = prompt = f"""
        以下の文章をファクトチェックしてください。
        ・怪しい点
        ・補足すべき情報
        ・注意点

        文章:
        {body}
        """
        res = llm5_mini.invoke([
            SystemMessage(content="あなたは厳密なファクトチェッカーです"),
            HumanMessage(content=prompt)
        ])
        notes[title] = res.content
    return {"notes": notes}


def generate_diagrams(state: ArticleState) -> dict:
    diagrams = {}
    for title, body in state["sections"].items():
        prompt = f"""
        以下をMermaid図にしてください。
        説明は禁止。Mermaidコードのみ。

        文章:
        {body}
        """
        diagrams[title] = llm5_mini.invoke(prompt).content.strip()
    return {"diagrams": diagrams}


def merge_article(state: ArticleState) -> dict:
    sections = list(state["sections"].items())
    if not sections:
        return {"article": ""}

    diagrams = state.get("diagrams", {})
    notes = state.get("notes", {})
    parts = [
        f"# {state['theme']}：有料noteで読む価値",
        "このレポートは初心者エンジニアが歴史から実務的知見を抽出できるように設計されています。",
        "最初のセクションまでは無料で公開し、以降は購読者限定の深掘り解説です。",
        "## 無料パート：リードと全体像",
    ]

    free_title, free_body = sections[0]
    parts.append(f"### {free_title}")
    parts.append(free_body)
    if free_title in diagrams:
        parts.append(f"```mermaid\n{diagrams[free_title]}\n```")
    if free_title in notes:
        parts.append("#### Fact memo")
        parts.append(notes[free_title])

    premium_sections = sections[1:]
    if premium_sections:
        parts.extend(
            [
                "---",
                "## ここから先は有料エリア（購読者限定）",
                "設計思想の背景、歴史的な転換点ごとの意思決定、現場への落とし込み方を実務レベルで解説します。",
            ]
        )
        for title, body in premium_sections:
            parts.append(f"### {title}")
            parts.append(body)
            if title in diagrams:
                parts.append(f"```mermaid\n{diagrams[title]}\n```")
            if title in notes:
                parts.append("#### Fact memo")
                parts.append(notes[title])

    parts.extend(
        [
            "## 読者が得られるもの",
            "- 歴史と現在のPythonエコシステムを結びつけた理解",
            "- プロダクト選定や学習計画に使える判断基準",
            "- コミュニティ/PSFの動きを踏まえたキャリアのヒント",
            "## 次のアクション",
            "・記事末尾のコメントで疑問を共有してください。フォローアップで資料を追加します。",
            "・有料購読者には図解付きPDFと追加ケーススタディを後日配布します。",
        ]
    )

    return {"article": "\n\n".join(parts)}


def build_graph() -> StateGraph[ArticleState]:

    graph = StateGraph(ArticleState)

    graph.add_node("draft", generate_draft)
    graph.add_node("split", split_sections)
    graph.add_node("fact", fact_check)
    graph.add_node("diagram", generate_diagrams)
    graph.add_node("merge", merge_article)

    graph.set_entry_point("draft")

    graph.add_edge("draft", "split")
    graph.add_edge("split", "fact")
    graph.add_edge("split", "diagram")
    graph.add_edge("fact", "merge")
    graph.add_edge("diagram", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
