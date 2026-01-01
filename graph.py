from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()


llm5_mini = AzureChatOpenAI(
    api_version=os.getenv("API_VERSION"),
    azure_endpoint=os.getenv("GPT_5_MINI_ENDPOINT"),
    azure_deployment=os.getenv("GPT_5_MINI_DEPLOYMENT_NAME"),
    model=os.getenv("GPT_5_MINI_MODEL"),
)
llm5_1 = AzureChatOpenAI(
    api_version=os.getenv("API_VERSION"),
    azure_endpoint=os.getenv("GPT_5.1_ENDPOINT"),
    azure_deployment=os.getenv("GPT_5.1_DEPLOYMENT_NAME"),
    model=os.getenv("GPT_5.1_MODEL"),
)


class ArticleState(TypedDict):
    theme: str
    draft: str
    sections: dict[str, str]
    notes: list[str]
    diagrams: dict[str, str]
    article: str


def generate_draft(state: ArticleState) -> dict:
    prompt = f"""
    以下のテーマで、まずは記事を書いてください。
    完成度は60%で構いません。

    テーマ:
    {state['theme']}
    """
    return {"draft": llm5_1.invoke(prompt).content}


def split_sections(state: ArticleState) -> dict:
    prompt = f"""
    以下の記事を見出し単位で分割してください。

    【制約】
    - 見出しは最大3つ
    - 出力はJSONのみ
    - 説明文は禁止

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
    return {"sections": json.loads(match.group())}


def fact_check(state: ArticleState) -> dict:
    notes = []
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
        notes.append(f"## {title}\n{res.content}")
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
    parts = []
    for title, body in state["sections"].items():
        parts.append(f"## {title}")
        parts.append(body)

        if title in state.get("diagrams", {}):
            parts.append(f"```mermaid\n{state['diagrams'][title]}\n```")

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
