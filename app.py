from flask import Flask, render_template, request, jsonify
from graph import build_graph

app = Flask(__name__)
graph_app = build_graph()


@app.route('/')
def index():
    return render_template('index.html')


@app.route("/generate", methods=["POST"])
def generate():
    theme = request.json.get("theme")
    if not theme:
        return jsonify({"error": "Theme is required"}), 400

    state = {
        "theme": theme,
        "draft": "",
        "sections": {},
        "notes": [],
        "diagrams": {},
        "article": ""
    }

    result = graph_app.invoke(state)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True)
