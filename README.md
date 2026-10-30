# SRE Agent (GEAP Sandboxes + Google Developer Knowledge MCP)

Google の SRE ベストプラクティスに基づき、**GEAP Shell Sandbox (`agentplatform.Client().sandboxes`)** を用いた Cloud Logging の直接調査・Python 分析と、**Google Developer Knowledge API (MCP)** を用いた公式ドキュメント検索を組み合わせたサンプル SRE エージェントです。

## アーキテクチャ概要

- **Root Agent (`app/agent.py`)**: `gemini-4-argon` モデルを採用。Four Golden Signals（Latency / Traffic / Errors / Saturation）の観点でのトリアージ、仮説駆動の根本原因分析（RCA）、Blameless なレポート作成を実施。
- **GEAP Shell Sandbox ツール (`run_in_sandbox` in `app/tools.py`)**:
  - セッションごとに隔離された GEAP Shell Sandbox（Egress インターネット通信有効）を起動・再利用。
  - ホスト側サービスアカウント（`sre-agent@llm20260121.iam.gserviceaccount.com`）の短命 OAuth トークンを `CLOUDSDK_AUTH_ACCESS_TOKEN` として注入し、サンドボックス内で `gcloud logging read` や Python 集計スクリプトを実行。
- **Google Developer Knowledge MCP (`developer_knowledge_mcp` in `app/tools.py`)**:
  - `https://developerknowledge.googleapis.com/mcp` に Streamable HTTP で接続。
  - API キーを使わず、サービスアカウント（ADC）の Bearer トークンと `X-Goog-User-Project: llm20260121` ヘッダーで認証。

### なぜ ADK 標準の `AgentEngineSandboxCodeExecutor` をそのまま使わないのか？

ADK には GEAP Sandboxes 用の公式ラッパークラス `AgentEngineSandboxCodeExecutor` が存在しますが、本ユースケースでは以下の 4 つの理由から関数ツール `run_in_sandbox` として実装しています：

1. **Egress 有効テンプレートの指定不可**: `AgentEngineSandboxCodeExecutor` は内部で `spec={'code_execution_environment': {}}` がハードコードされており、外部通信（Cloud Logging API へのアクセス）を許可する `sandbox_environment_template` を指定できないため。
2. **Shell Sandbox (`execute_bash`) 非対応**: Python コード断片用の `execute_code()` 固定であり、`gcloud` CLI を直接実行する `execute_bash()` に対応していないため。
3. **SA トークン注入フックの不在**: ホスト側サービスアカウントのアクセストークンをサンドボックス内の環境変数へ渡す仕組みがないため。
4. **Function Calling への統一**: `McpToolset`（Developer Knowledge MCP）と同じ標準の Function Calling ツールとして統一することで、ログ調査と公式ドキュメント検索の連携を安定させるため（なお、`session.state['sandbox_name']` によるセッション単位のサンドボックス再利用と `STATE_RUNNING` チェックは `AgentEngineSandboxCodeExecutor` の設計を踏襲しています）。

---

## 事前要件 (GCP Project & Service Account)

- **GCP Project**: `llm20260121`
- **Service Account**: `sre-agent@llm20260121.iam.gserviceaccount.com`
- **必要な有効化 API**:
  - `aiplatform.googleapis.com`
  - `logging.googleapis.com`
  - `developerknowledge.googleapis.com`
- **必要な IAM ロール**:
  - `roles/aiplatform.user`（モデル呼び出し & GEAP Sandbox 操作）
  - `roles/logging.viewer`（Cloud Logging ログ参照）
  - `roles/serviceusage.serviceUsageConsumer`（Developer Knowledge MCP の `X-Goog-User-Project` 利用）

---

## セットアップ & ローカル実行

```bash
# 依存パッケージのインストール (.venv 構築)
agents-cli install

# 単体テストの実行
uv run pytest tests/unit

# ローカル Playground の起動
agents-cli playground
```

## Agent Runtime へのデプロイ

```bash
agents-cli deploy \
  --project llm20260121 \
  --region us-central1 \
  --service-account sre-agent@llm20260121.iam.gserviceaccount.com
```
