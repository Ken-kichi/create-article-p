## セットアップ
```bash
~/Desktop $ mkdir create-article
~/Desktop $ cd create-article
~/Desktop/create-article $ uv init
~/Desktop/create-article $ uv venv
~/Desktop/create-article $ source ./.venv/bin/activate
~/Desktop/create-article $ uv add langchain langgraph openai tiktoken langchain_openai dotenv flask
(create-article) ~/Desktop/create-article $ uv pip compile ./pyproject.toml > requirements.txt

```

## graph.py

## app.py
main.pyをapp.pyに変更


## インフラの構築
### リソースグループ
（リソースグループの説明）

（作成手順）
リソースグループの作成
グループ名：create-article
リージョン：Japan West
### Azure AI Foundry
#### Azure AI Foundry resource
Azure ポータルの検索欄でai foundryを検索
Foundry resource
name:article-ai
rigion:East US
default project name:article-ai
#### モデルをデプロイ
gpt-5.1-chatとgpt-5-miniをデプロイ
（作成手順）
### App Service
（作成手順）

## ローカルテスト

## デプロイ

.envの作成
環境変数ファイルを作成し、OPENAIの
```bash
touch .env
```
