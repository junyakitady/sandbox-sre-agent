# Google Kubernetes Engine - GKE (`container.googleapis.com`) 緩和プレイブック

このリファレンスは、Generic Mitigations を GKE / Kubernetes の具体的な操作にマッピングします。

## 1. Rollback（Deployment のロールバック）
直近の RollingUpdate により `CrashLoopBackOff` やアプリケーションエラーが急増した場合、Deployment を直前の正常な ReplicaSet（Revision）へ切り戻します。

```bash
# 🎬 Rollback: ロールアウト履歴の確認
# ⚠️ Risk: ⚪ NONE: 読み取り専用の確認操作です。
kubectl rollout history deployment/DEPLOYMENT_NAME -n NAMESPACE

# 🎬 Rollback: 直前のリビジョンへ切り戻す
# ⚠️ Risk: 🟡 MEDIUM: Pod が直前の正常テンプレートで順次再作成されます。進行中の長寿命コネクションが切断される場合があります。
kubectl rollout undo deployment/DEPLOYMENT_NAME -n NAMESPACE
```

## 2. Upsize（Pod レプリカ数・Node Pool の拡張）
負荷増大やリソース逼迫時に Pod 数（水平スケール）または GKE Node Pool のノード数を増強します。

```bash
# 🎬 Upsize: Deployment の Pod レプリカ数を増やす
# ⚠️ Risk: 🟢 LOW: クラスタに空きリソースがあれば即座に Pod が追加起動します。下流DBのコネクション上限に注意してください。
kubectl scale deployment/DEPLOYMENT_NAME --replicas=NEW_COUNT -n NAMESPACE

# 🎬 Upsize: GKE Node Pool のノード数を増やす（Pending Pod 発生時）
# ⚠️ Risk: 🟡 MEDIUM: 新規VMノードの起動完了まで数分かかります。
gcloud container clusters resize CLUSTER_NAME \
  --node-pool=NODE_POOL_NAME \
  --num-nodes=NEW_COUNT \
  --region=REGION --project=PROJECT_ID
```

## 3. Quarantine / Traffic Drain（異常 Pod の隔離・不良ノードの Drain）
特定の Pod だけが悪影響を受けている場合、Pod を削除せずに Service のセレクタラベルを書き換えてトラフィックから切り離す（デバッグ用に状態を残す）か、障害ノードから Pod を退避させます。

```bash
# 🎬 Quarantine: 特定 Pod のラベルを変更して Service トラフィックから切り離す
# ⚠️ Risk: 🟢 LOW: 該当 Pod への新規通信のみを停止し、Deployment が代替の新しい Pod を自動補充します。
kubectl label pod POD_NAME app=SERVICE_NAME-quarantined --overwrite -n NAMESPACE

# 🎬 Drain: 特定ノードをスケジュール不可にして Pod を別ノードへ退避させる
# ⚠️ Risk: 🔴 HIGH: ノード上の全 Pod が強制退避（Evict）されます。他ノードに十分な空き容量があることを確認してください。
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

## 4. Restart（グレースフルな全 Pod 再起動）
一時的なデッドロックやコネクション不整合を解消するため、Deployment 配下の Pod をローリング方式で順次再起動します。

```bash
# 🎬 Restart: Deployment のローリング再起動
# ⚠️ Risk: 🟡 MEDIUM: Readiness Probe に従い順次入れ替わりますが、一時的にリソース使用量が増加します。
kubectl rollout restart deployment/DEPLOYMENT_NAME -n NAMESPACE
```

## 5. 緩和策適用後の Cloud Logging 検証クエリ
```bash
gcloud logging read 'resource.type=("k8s_container" OR "k8s_pod") AND resource.labels.namespace_name="NAMESPACE" AND severity>=ERROR' --freshness=15m --limit=20
```
