# SRE Agent (GEAP Sandboxes + Google Developer Knowledge MCP + ADK Skills)

Google の SRE ベストプラクティスに基づき、**GEAP Shell Sandbox (`agentplatform.Client().sandboxes`)** を用いた Cloud Logging の直接調査・Python 分析、**Google Developer Knowledge API (MCP)** を用いた公式ドキュメント検索、および **ADK `SkillToolset` (`app/skills/`)** による段階的スキル読み込みを組み合わせた SRE エージェントです。

## アーキテクチャ概要

- **Root Agent (`app/agent.py`)**:
  - `gemini-4-argon` モデルを採用。
  - 対象 Google Cloud プロジェクト ID が未指定の場合は調査前にユーザーへ確認。
  - Cloud Logging から観測可能なシグナル（エラー傾向・例外・リソース枯渇イベント・監査ログ上の変更履歴・HTTP レイテンシ）に基づく初期トリアージを実施（Cloud Monitoring メトリクスでしか分からない CPU/メモリ使用率や全体 QPS は推測で断定せず明確に区別）。
  - 仮説駆動の根本原因分析（RCA）に確信度（`Confidence Level: High / Medium / Low`）と公式ドキュメント URL を付与し、リスク評価付きの緩和策提案および Blameless Postmortem 作成を実施。
- **ADK Agent Skills (`sre_skill_toolset` in `app/agent.py`, `app/skills/`)**:
  - ADK 標準の `SkillToolset`（`SkillDiscoveryMode.EAGER`）を用い、普段はスキル名と概要（L1 メタデータ）のみをシステムプロンプトへ注入し、必要時のみ `load_skill`（L2 手順）および `load_skill_resource`（L3 リファレンス）で詳細知識を展開する Progressive Disclosure 構成。
  - 保守性と安全性を高めるため、独自スクリプト（`.py` / `.sh`）を含まない**純粋な Markdown スキル構成（スクリプトレス）**を採用し、`tool_filter=["load_skill", "load_skill_resource"]` によりホスト側でのスクリプト実行ツールを非公開化（集計処理はすべて隔離された GEAP Shell Sandbox 内で実行）。
- **GEAP Shell Sandbox ツール (`run_in_sandbox` in `app/tools.py`)**:
  - セッションごとに隔離された GEAP Shell Sandbox（Egress インターネット通信有効）を起動・再利用し、初回実行時に公式の `google-cloud-cli` (`gcloud`) を `/var/tmp/google-cloud-sdk`（overlayfs）へ自動ストリーミング展開。
  - ホスト側サービスアカウント（`sre-agent@llm20260121.iam.gserviceaccount.com`）の短命 OAuth トークンを `CLOUDSDK_AUTH_ACCESS_TOKEN` として注入し、サンドボックス内で本物の `gcloud` CLI（`gcloud logging read`、`gcloud compute`、`gcloud run` 等）や Python 集計スクリプトを実行。
- **Google Developer Knowledge MCP (`developer_knowledge_mcp` in `app/tools.py`)**:
  - `https://developerknowledge.googleapis.com/mcp` に Streamable HTTP で接続。
  - API キーを使わず、サービスアカウント（ADC）の Bearer トークンと `X-Goog-User-Project` ヘッダーで認証。

---

## プロンプト行動指針と搭載 SRE スキル (`app/skills/`)

### 1. 常時適用の行動指針 (`SRE_INSTRUCTION` in `app/agent.py`)
1. **スコープ特定ゲートとログベースの初期トリアージ**: プロジェクト ID・対象サービス・発生時間帯（UTC）をまず整理し、いきなり大量のログを取得しない。
2. **Context Bloat（コンテキスト肥大化）防止**: 生の巨大 JSON ログを標準出力へ直接流さず、サンドボックス内の `/tmp/logs.json` に保存して Python で必要フィールド抽出・統計集計のみを出力する。
3. **Data Integrity（データ完全性）と公式知見の裏付け**: ログの数値やタイムスタンプを推測・補完しない（ログ 0 件の区間は事実として 0 件と扱う）。エラー原因や CLI オプションは Developer Knowledge MCP で裏付ける。
4. **止血優先（Mitigate First）とリスク評価付きコマンド提案**: エージェント自身は読み取り専用を維持し、ユーザーへ提示する `gcloud` / `kubectl` コマンドには必ず以下のリスク評価ヘッダを付与する：
   ```bash
   # 🎬 <操作の簡潔な説明>
   # ⚠️ Risk: <⚪ NONE | 🟢 LOW | 🟡 MEDIUM | 🔴 HIGH>: <影響範囲・前提条件・ロールバック可否>
   <command>
   ```

### 2. オンデマンド SRE スキル一覧 (`app/skills/`)

```text
app/
├── agent.py                                           # Root Agent 定義 & SkillToolset 統合
├── tools.py                                           # GEAP Shell Sandbox & Developer Knowledge MCP
└── skills/
    ├── cloud-logging-investigation/
    │   ├── SKILL.md                                   # 段階的ログ調査・Revision相関・Sparkline・異常スパイク特定と平易な報告規約
    │   └── references/
    │       └── query_patterns.md                      # LQL 構文ルール & Cloud Run / GKE / Audit Logs フィルタ集
    ├── gcp-mitigation-playbooks/
    │   ├── SKILL.md                                   # Generic Mitigations 7分類マトリクス & MCP 裏付け手順
    │   └── references/
    │       ├── run.md                                 # Cloud Run 緩和プレイブック（Rollback / Upsize / Drain 等）
    │       └── container.md                           # GKE 緩和プレイブック（Undo / Quarantine / Drain / Restart 等）
    └── blameless-postmortem/
        └── SKILL.md                                   # Blameless Postmortem テンプレート & 箇条書き Timeline 規約
```

| スキル名 | 主な役割・収録内容 |
| :--- | :--- |
| **`cloud-logging-investigation`** | - Cloud Logging JSON ペイロードのフォールバック抽出順序（`textPayload` → `jsonPayload` → `protoPayload` → `httpRequest`）と Apache 風1行サマリー整形<br>- リビジョン／Pod 別エラー相関フォーマット（`✅ CLEAN` vs `❌ Errors` と初出時刻の特定）<br>- 8段階ブロック文字（` ▂▃▄▅▆▇█`）を用いた **Unicode Sparkline** と記述統計の出力規約<br>- 異常スパイク時間帯の統計的特定（過検知防止の内部チェック）と、統計用語（バケット・Z-Score等）を排した**平易な日本語での報告ルール**<br>- `references/query_patterns.md`: LQL 構文の注意点と Cloud Run / GKE / Cloud Audit Logs / Vertex AI 向け実践フィルタ集 |
| **`gcp-mitigation-playbooks`** | - Google SRE の **Generic Mitigations 7分類マトリクス**（`Rollback` / `Data Rollback` / `Degrade` / `Upsize` / `Block List` / `Drain` / `Quarantine`）の適用条件・前提条件（DB スキーマ互換性等）・副作用リスク（下流ボトルネック移動等）<br>- `references/run.md` / `references/container.md`: Cloud Run・GKE の具体的な緩和コマンド、リスク評価、および適用後の Cloud Logging 検証クエリ<br>- Developer Knowledge MCP を用いた他サービス・CLI フラグの公式ドキュメント裏付け手順 |
| **`blameless-postmortem`** | - Google SRE の Postmortem Culture に準拠した Blameless Postmortem Markdown テンプレート<br>- 視認性の高い箇条書きタイムライン規約（UTC 明記、`Start of Incident` / `Incident Detected` / `Mitigation` / `End of Incident` マイルストーン表記）<br>- `Mitigate` / `Detect` / `Prevent` 分類と優先度付きの Action Items テーブル定義 |

---

### なぜ ADK 標準の `AgentEngineSandboxCodeExecutor` をそのまま使わないのか？

ADK には GEAP Sandboxes 用の公式ラッパークラス `AgentEngineSandboxCodeExecutor` が存在しますが、本ユースケースでは以下の 4 つの理由から関数ツール `run_in_sandbox` として実装しています：

1. **Egress 有効テンプレートの指定不可**: `AgentEngineSandboxCodeExecutor` は内部で `spec={'code_execution_environment': {}}` がハードコードされており、外部通信（Cloud Logging API へのアクセス）を許可する `sandbox_environment_template` を指定できないため。
2. **Shell Sandbox (`execute_bash`) 非対応**: Python コード断片用の `execute_code()` 固定であり、`gcloud` CLI を直接実行する `execute_bash()` に対応していないため。
3. **SA トークン注入フックの不在**: ホスト側サービスアカウントのアクセストークンをサンドボックス内の環境変数へ渡す仕組みがないため。
4. **Function Calling への統一**: `McpToolset`（Developer Knowledge MCP）や `SkillToolset` と同じ標準の Function Calling ツールとして統一することで、スキル読込・ログ調査・公式ドキュメント検索の連携を安定させるため（なお、`session.state['sandbox_name']` によるセッション単位のサンドボックス再利用と `STATE_RUNNING` チェックは `AgentEngineSandboxCodeExecutor` の設計を踏襲しています）。

---

## 事前要件 (GCP Project & Service Account)

- **GCP Project**: `llm20260121`（デフォルトのサンドボックスホスト／課金プロジェクト）
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

# 単体テストの実行（Agent構成・SkillToolset読込・SKILL.md Frontmatter検証・Sandboxモック検証）
uv run pytest tests/unit

# Lint & スペルチェック
agents-cli lint

# 評価データセットによるエージェント評価
agents-cli eval run

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

---

## 参考リファレンス

- [Skills for ADK agents (`SkillToolset` / `SKILL.md` 公式ドキュメント)](https://adk.dev/skills/)
- [Cloud Logging Query Language 公式ガイド](https://docs.cloud.google.com/logging/docs/view/logging-query-language)
- [Google Developer Knowledge API & MCP ドキュメント](https://developers.google.com/knowledge)
- [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Google SRE Workbook: Postmortem Culture](https://sre.google/workbook/postmortem-culture/)
