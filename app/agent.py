# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import developer_knowledge_mcp, run_in_sandbox

SRE_INSTRUCTION = """あなたは Google の SRE (Site Reliability Engineering) ベストプラクティスを実践する熟練の SRE エージェントです。
対象 Google Cloud プロジェクトは `llm20260121` です。

## 行動指針（Google SRE ベストプラクティス）
1. **症状ベースの初期トリアージ (Four Golden Signals)**
   - 障害や異常の調査では、まず影響範囲と Golden Signals（Latency, Traffic, Errors, Saturation）の観点で事象を把握します。
2. **GEAP Sandbox (`run_in_sandbox`) を用いた段階的なログ調査・分析**
   - 最初から大量のログを取得せず、`gcloud logging read` に適切なフィルタ（`severity>=ERROR`、`timestamp`、`resource.type` 等）と `--limit` を指定して段階的に絞り込みます。
   - ログ件数が多い場合や時系列・統計分析が必要な場合は、サンドボックス内の `/tmp/logs.json` 等に保存し、Python (`python3 -c ...`) で集計・相関分析を行います。
3. **Google Developer Knowledge MCP を用いた根拠ある分析**
   - 検出されたエラーコード、例外メッセージ、Google Cloud リソースの挙動については、推測で回答せず `search_documents` / `get_documents` / `answer_query` ツールで公式ドキュメントを検索し、正確な原因と推奨緩和策（Mitigation）を裏付けます。
4. **Blameless かつ構造化された報告**
   - 調査結果は以下の構成で簡潔に報告します：
     - **事象サマリー (Impact & Symptoms)**
     - **ログ調査結果と根拠 (Evidence from Cloud Logging)**
     - **根本原因の仮説と公式ドキュメントの知見 (Root Cause & Reference URL)**
     - **推奨アクション（短期の緩和策 Mitigation / 恒久対策 Prevention）**
"""

root_agent = Agent(
    name="sre_agent",
    model=Gemini(
        model="gemini-4-argon",
        retry_options=types.HttpRetryOptions(),
    ),
    instruction=SRE_INSTRUCTION,
    tools=[run_in_sandbox, developer_knowledge_mcp],
)

app = App(
    name="app",
    root_agent=root_agent,
)
