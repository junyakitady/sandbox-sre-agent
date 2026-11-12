---
name: gcp-mitigation-playbooks
description: Google SRE の Generic Mitigations（7分類の止血・緩和戦略）と Cloud Run / GKE 等の Google Cloud サービス別プレイブックを提供するスキル。障害の緩和策（Mitigation）や復旧コマンドを立案・提案する際にロードしてください。
metadata:
  author: SRE Agent Team
  version: 1.0.0
  status: published
---

# GCP Mitigation Playbooks & Generic Mitigations Skill

このスキルは、障害発生時に **Time to Mitigate (TTM: 緩和までの時間)** を最小化するための Google SRE 標準フレームワーク（Duct-Tape Outage Resolution）と、具体的な Google Cloud 操作へのマッピングを提供します。

## 1. コア原則: Mitigate First, Root-Cause Later

1. **止血を最優先する**: ユーザー影響を止めるために、根本原因を100%解明し切る必要はありません。まず既知の安全な手段でシステムを安定させ、詳細な診断のための時間を稼ぎます。
2. **実績ある広域手段を選ぶ**: 障害対応の最中に、未テストの新しい縮退ロジック（Degradation path）やアドホックなコード修正を実装してはいけません。
3. **安全管理と検証クエリのセット提示**: 緩和策を提案する際は、必ず**事前条件（スキーマ互換性や下流負荷）**、**リスク評価（⚪/🟢/🟡/🔴）**、および**適用後に Cloud Logging で改善を確認するための検証コマンド**をセットで提示します。

## 2. Generic Mitigations 7分類マトリクス

観察された症状（Blast Radius・直近デプロイの有無・リソース飽和）から、以下の7分類のどれが最適かを選択します：

| 緩和策カテゴリ | 最適な適用シナリオ | 必須の前提条件 (Prerequisites) | 主なリスク・注意点 (Cautions) |
| :--- | :--- | :--- | :--- |
| **1. Rollback**<br>（バイナリ／設定切り戻し） | デプロイ直後のエラー急増、ビジネスロジックのリグレッション | 明確に特定された「直前の正常リビジョン／ビルド」が存在すること | DB スキーマ変更や API 仕様変更を伴う場合のステート非互換、接続中セッションの瞬断 |
| **2. Data Rollback**<br>（データ／設定復元） | 破損した設定・パイプラインデータ・キャッシュの混入 | 検証済みのバックアップと、ステートが分離されていること | ロールバック対象期間中の正常なトランザクションデータが失われる可能性 |
| **3. Degrade**<br>（機能縮退） | キャパシティ飽和、連鎖障害、システム全体の高負荷 | 高コスト・非必須な処理（推薦や重い集計等）をオフにする既存のフィーチャーフラグ／環境変数 | エンドユーザー向けの一部機能制限（※障害中に新規の縮退コードを実装しないこと） |
| **4. Upsize**<br>（スケールアウト／増強） | 予期せぬトラフィックスパイク、メモリ不足（OOM）・CPU枯渇 | スケール可能なインフラ上限（Quota）があること | **下流（DB コネクション数や外部 API レート制限）へのボトルネック移動**・コスト増加 |
| **5. Block List**<br>（遮断・スロットリング） | 単一テナントの暴走、Query of Death、DoS 的リクエスト | Cloud Armor / API Gateway / LB 等での迅速なフィルタリング手段 | 条件が広すぎる場合の正常ユーザー誤遮断 |
| **6. Drain**<br>（トラフィック退避） | 特定リージョン・ゾーン・特定ノードの局所的なインフラ障害 | 退避先のリージョン／ノード群が追加トラフィックを吸収できる余力を持つこと | 退避先リージョンへの過負荷集中による連鎖障害（Cascading Failure） |
| **7. Quarantine**<br>（隔離） | 特定の破損 Pod、ホットスポット化したテナント／ストリーム | 対象の Pod やストリームを論理的にトラフィックから切り離せること | 根本原因が共通にある場合、他インスタンスでも再発する可能性 |

## 3. サービス別プレイブックと Developer Knowledge MCP の連携手順

1. **対象サービスの特定**:
   - **Cloud Run (`run.googleapis.com`)** の場合: `load_skill_resource` で `references/run.md` を読み込みます。
   - **GKE (`container.googleapis.com`)** の場合: `load_skill_resource` で `references/container.md` を読み込みます。
2. **Google Developer Knowledge MCP による公式ドキュメント裏付け**:
   - 上記以外のサービス（Cloud SQL, AlloyDB, Pub/Sub, Cloud Load Balancing, Vertex AI / Agent Engine 等）や、特定のエラーコード・CLI フラグの詳細仕様を確認する場合は、**必ず `search_documents` / `get_documents` ツールを呼び出して Google Cloud 公式ドキュメントで裏付け**を取ります。
3. **リスク評価付きコマンド提案フォーマット**:
   エージェント自身は変更コマンドを実行せず、以下の形式でユーザーに提示します：
   ```bash
   # 🎬 <緩和策カテゴリ>: <操作の簡潔な説明>
   # ⚠️ Risk: <⚪ NONE | 🟢 LOW | 🟡 MEDIUM | 🔴 HIGH>: <影響範囲・前提条件・注意点>
   <gcloud or kubectl command>
   ```
