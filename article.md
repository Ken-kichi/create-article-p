## セットアップ
```bash
~/Desktop $ mkdir create-article
~/Desktop $ cd create-article
~/Desktop/create-article $ uv init
~/Desktop/create-article $ uv venv
~/Desktop/create-article $ source ./.venv/bin/activate
~/Desktop/create-article $ uv add langchain langgraph openai tiktoken langchain_openai dotenv
(create-article) ~/Desktop/create-article $ uv pip compile ./pyproject.toml > requirements.txt

```

## graph.py

## app.py
main.py -> app.py
