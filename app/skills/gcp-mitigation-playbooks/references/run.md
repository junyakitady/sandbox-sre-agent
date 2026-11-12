# Cloud Run (`run.googleapis.com`) 緩和プレイブック

このリファレンスは、Generic Mitigations を Google Cloud Run の具体的な操作にマッピングします。

## 1. Rollback（トラフィックの切り戻し）
Cloud Run ではデプロイごとに不変（Immutable）な Revision が作成されます。問題のある最新リビジョンから、エラーが発生していなかった直前の正常リビジョン（`✅ CLEAN`）へトラフィックを 100% 切り戻します。

```bash
# 🎬 Rollback: リビジョン一覧とトラフィック配分の確認
# ⚠️ Risk: ⚪ NONE: 読み取り専用の確認操作です。
gcloud run revisions list --service=SERVICE_NAME --region=REGION --project=PROJECT_ID

# 🎬 Rollback: 直前の正常リビジョンへトラフィックを100%切り戻す
# ⚠️ Risk: 🟢 LOW〜🟡 MEDIUM: 既知の正常リビジョンへ即座に切り戻します。DBスキーマや外部API仕様の非互換がないことを確認してください。
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=PREVIOUS_GOOD_REVISION=100 \
  --region=REGION --project=PROJECT_ID
```

## 2. Upsize（インスタンス上限・メモリ／CPU の増強）
急激なトラフィック増加による 429/503 エラーや、`Memory limit exceeded`（OOM）・CPU スロットリングがログで確認された場合に適用します。

```bash
# 🎬 Upsize: 最大インスタンス数の引き上げ（トラフィックスパイク対応）
# ⚠️ Risk: 🟢 LOW〜🟡 MEDIUM: スケール上限を引き上げますが、接続先DBの最大コネクション数を超過しないよう注意してください。
gcloud run services update SERVICE_NAME \
  --max-instances=NEW_MAX \
  --region=REGION --project=PROJECT_ID

# 🎬 Upsize: コンテナのメモリ・CPU割り当ての増強（OOM / CPU枯渇対応）
# ⚠️ Risk: 🟡 MEDIUM: 新しいリビジョンが作成され、順次トラフィックが切り替わります。
gcloud run services update SERVICE_NAME \
  --memory=2Gi --cpu=2 \
  --region=REGION --project=PROJECT_ID
```

## 3. Fix Forward（修正イメージの再デプロイ）
設定値（環境変数）の誤りや軽微なパッチ適用済みイメージがすでに用意できている場合に適用します。

```bash
# 🎬 Fix Forward: 修正済みコンテナイメージのデプロイ
# ⚠️ Risk: 🟡 MEDIUM: 新規リビジョンを作成しトラフィックをルーティングします。
gcloud run deploy SERVICE_NAME \
  --image=NEW_IMAGE_URL \
  --region=REGION --project=PROJECT_ID
```

## 4. Restart / Instance Refresh（インスタンスの強制入れ替え）
Cloud Run はサーバーレスのため個別コンテナの手動再起動コマンドはありませんが、一時的なメモリリークや不安定なインスタンス群をリフレッシュしたい場合は環境変数更新により新リビジョンを起動できます。

```bash
# 🎬 Restart: 新規リビジョン作成による全インスタンスの入れ替え
# ⚠️ Risk: 🟡 MEDIUM: 全インスタンスが順次再作成されるため、コールドスタートによる一時的なレイテンシ増加の可能性があります。
gcloud run services update SERVICE_NAME \
  --update-env-vars="RESTART_TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)" \
  --region=REGION --project=PROJECT_ID
```

## 5. Traffic Drain（リージョン退避に関する注意点）
- Cloud Run 単体の `--to-revisions` は**同一リージョン内のリビジョン間**でのみトラフィックを分割します。
- 特定リージョン全体の障害で別リージョンへ Drain する場合は、前段の **Global External Application Load Balancer（バックエンドサービスから該当リージョンの Serverless NEG を切り離す）** 側で操作する必要があります（リスク: 🔴 HIGH）。

## 6. 緩和策適用後の Cloud Logging 検証クエリ
緩和策の実行後、エラーが収束したかを確認するためのコマンド：
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="SERVICE_NAME" AND severity>=ERROR' --freshness=15m --limit=20
```
