# Cloud Logging Query Language (LQL) 実践フィルタ集

## 1. GEAP Shell Sandbox 内 `gcloud logging read` の利用規約
サンドボックス内では公式の Google Cloud CLI (`gcloud`) が利用可能です。Python で集計する場合は必ず `--format=json` を明示して `/tmp/logs.json` に出力してください（`--format` 省略時のデフォルトは YAML になります）：
```bash
gcloud logging read '<FILTER>' \
  --project=PROJECT_ID \
  --limit=50 \
  --freshness=1h \
  --order=desc \
  --format=json
```
- `--freshness`: `30m`, `2h`, `1d`, `7d` などの相対時間指定が可能。
- `--limit`: 初期トリアージでは `20`〜`50`（または `--format="table(timestamp,severity,resource.type)"` で一覧確認）、`/tmp/logs.json` 保存集計では `--format=json` とともに `200`〜`1000` を推奨。

## 2. LQL 構文エラーを防ぐ必須ルール
公式ドキュメント（`https://docs.cloud.google.com/logging/docs/view/logging-query-language` および `https://docs.cloud.google.com/logging/docs/view/troubleshoot-lql`）に基づく構文上の注意点：
1. **論理演算子は必ず大文字**: `AND`, `OR`, `NOT` を使用します（小文字の `and` / `or` は検索語として扱われます）。
2. **`OR` 条件は必ず丸括弧でグループ化**:
   - NG: `resource.type="cloud_run_revision" OR "k8s_container" AND severity>=ERROR`
   - OK: `resource.type=("cloud_run_revision" OR "k8s_container") AND severity>=ERROR`
3. **クォートの使い分け**: シェル上ではフィルタ全体をシングルクォート `'...'` で囲み、値に含まれるコロン `:` や空白・スラッシュはダブルクォート `"..."` で囲みます。
4. **`google.protobuf.Any` 型フィールド（AuditLog の `status.details` 等）**: `.value` は自動走査されるため、クエリパスに `.value` を含めてはいけません。

## 3. ワークロード別の高シグナル調査フィルタ

### A. プロジェクト全体の初期エラー概況把握
```bash
gcloud logging read 'severity>=ERROR' --freshness=2h --limit=30
```

### B. Cloud Run (`run.googleapis.com`)
```bash
# 特定サービスのエラー・5xx レスポンス抽出
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="SERVICE_NAME" AND (severity>=ERROR OR httpRequest.status>=500)' --freshness=6h --limit=200 --format=json > /tmp/logs.json

# メモリ上限超過 (OOM) やコンテナクラッシュ・起動失敗の特定
gcloud logging read 'resource.type="cloud_run_revision" AND ("Memory limit" OR "Container called exit" OR "failed to start" OR "Request timeout")' --freshness=24h --limit=100 --format=json
```

### C. Google Kubernetes Engine - GKE (`container.googleapis.com`)
```bash
# コンテナ・Pod のエラーおよびクラッシュ調査
gcloud logging read 'resource.type=("k8s_container" OR "k8s_pod" OR "k8s_node") AND (severity>=ERROR OR "OOMKilled" OR "CrashLoopBackOff" OR "Evicted" OR "Back-off restarting failed container")' --freshness=6h --limit=200 --format=json > /tmp/logs.json
```

### D. 直近のデプロイ・設定変更との相関調査 (Cloud Audit Logs)
障害のトリガーとなった変更（新リビジョン投入、トラフィック変更、サービス更新）の正確な UTC タイムスタンプを特定します：
```bash
gcloud logging read 'logName:"cloudaudit.googleapis.com%2Factivity" AND protoPayload.serviceName=("run.googleapis.com" OR "container.googleapis.com" OR "aiplatform.googleapis.com")' --freshness=24h --limit=50
```

### E. Vertex AI / Agent Engine (`aiplatform.googleapis.com`)
```bash
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND severity>=ERROR' --freshness=6h --limit=100
```
