from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from graph import build_graph

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

graph_app = build_graph()
NODE_LABELS = {
    "draft": "下書き作成",
    "split": "見出し分割",
    "fact": "ファクトチェック",
    "diagram": "図解生成",
    "merge": "記事統合",
}
TOTAL_STEPS = len(NODE_LABELS)


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on("start")
def start(data):
    theme = data.get("theme", "")

    state = {
        "theme": theme,
        "draft": "",
        "sections": {},
        "notes": {},
        "diagrams": {},
        "article": ""
    }

    completed_nodes = set()

    emit("progress", {"msg": "生成を開始しました", "percent": 0})

    final_state = None
    try:
        for mode, payload in graph_app.stream(state, stream_mode=["updates", "values"]):
            if mode == "updates" and isinstance(payload, dict):
                for node_name in payload.keys():
                    if node_name == "__metadata__":
                        continue
                    if node_name in NODE_LABELS:
                        completed_nodes.add(node_name)
                    label = NODE_LABELS.get(node_name, node_name)
                    percent = int(len(completed_nodes) / TOTAL_STEPS * 100) if TOTAL_STEPS else 100
                    emit("progress", {"msg": f"{label}が完了しました", "percent": percent})
            elif mode == "values":
                final_state = payload

        article = (final_state or {}).get("article", "")
        emit("done", {"article": article, "percent": 100})
    except Exception as exc:
        app.logger.exception("Article generation failed")
        percent = int(len(completed_nodes) / TOTAL_STEPS * 100) if TOTAL_STEPS else 0
        emit("progress", {"msg": f"エラー: {exc}", "percent": percent})
        emit("failed", {"message": "記事生成中にエラーが発生しました。"})


if __name__ == '__main__':
    socketio.run(app, debug=True)
