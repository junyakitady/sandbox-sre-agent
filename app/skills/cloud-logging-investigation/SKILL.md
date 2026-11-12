---
name: cloud-logging-investigation
description: Cloud Logging の段階的トリアージ、コンテキスト肥大化を防ぐフィールド抽出、リビジョン別エラー相関、Unicode Sparkline による時系列可視化、および異常スパイク時間帯の特定を行う調査スキル。障害調査やログ分析時にロードしてください。
metadata:
  author: SRE Agent Team
  version: 1.0.0
  status: published
---

# Cloud Logging Investigation Skill

このスキルは、隔離された GEAP Shell Sandbox (`run_in_sandbox`) 上の `gcloud logging read` と Python 3 標準ライブラリを組み合わせ、コンテキストウィンドウを飽和させずに高精度な根本原因分析（RCA）を行うための調査手順と出力規約を定義します。

## 1. 段階的ログ調査ワークフロー (Iterative Triage)

### Step 1: 初期トリアージ（対象と時間窓の絞り込み）
- 最初から大量のログを取得せず、`severity>=ERROR` と `--freshness`（例: `1h`, `6h`, `1d`）および `--limit=20`〜`50` を指定して直近のエラー傾向を把握します。
- 詳細なフィルタ構文が必要な場合は、`load_skill_resource` ツールで `references/query_patterns.md` を参照してください。

### Step 2: Context Bloat（コンテキスト肥大化）の防止とフィールド抽出
- **[禁止事項]** 数十件以上の生の Cloud Logging JSON エントリをそのまま標準出力に表示してはいけません。
- 件数が多い場合や集計を行う場合は、`--format=json` を指定してサンドボックス内の `/tmp/logs.json` に保存した上で、シェルのクォート衝突や Python f-string 内のバックスラッシュエスケープによる `SyntaxError` を防ぐため、`python3 -c "..."` ではなく必ずヒアドキュメント形式（`python3 - << 'EOF'`）で必要フィールドのみを抽出・集計して出力します：
  ```bash
  gcloud logging read '<FILTER>' --project=PROJECT_ID --freshness=3h --limit=500 --format=json > /tmp/logs.json
  python3 - << 'EOF'
  import json
  with open("/tmp/logs.json") as f:
      logs = json.load(f)
  # 必要フィールドの抽出・集計処理
  EOF
  ```
- **抽出対象フィールドの優先順位（取りこぼし防止）**:
  1. 基本メタデータ: `timestamp` (UTC), `severity`, `resource.type`
  2. リソース識別子 (`resource.labels`): `service_name`, `revision_name`, `configuration_name`, `pod_name`, `container_name`, `cluster_name`, `location`
  3. メッセージ・ペイロード（以下の優先順でフォールバック取得）:
     - `textPayload`
     - `jsonPayload.message` / `jsonPayload.error` / `jsonPayload.msg`
     - `protoPayload.status.message` / `protoPayload.methodName`
     - `httpRequest` (`requestMethod`, `requestUrl`, `status`, `latency`, `remoteIp`, `userAgent`)
- HTTP アクセスログを一覧確認する際は、トークン消費を抑えるため Apache Combined 風の1行フォーマットで整形出力します：
  `[timestamp] severity resource_id "METHOD URL" status latency "message_summary"`

## 2. 仮説駆動の根本原因分析 (Abductive RCA)

ログから以下の4つの観点で仮説を立てて検証します：
1. **Recent Changes（直近の変更との相関）**: 新規リビジョンのデプロイ、設定変更、環境変数変更の直後からエラーが始まっていないか（Audit Logs およびリビジョン別集計で確認）。
2. **Resource Saturation（リソース枯渇）**: `Memory limit exceeded`, `OOMKilled`, CPU スロットリング、DB コネクションプール枯渇、クォータ超過が発生していないか。
3. **Network / Downstream（通信・下流障害）**: 特定のバックエンドや外部 API に対するタイムアウト、`502`/`503`/`504`、DNS 解決失敗や接続拒否が発生していないか。
4. **Code / Poisonous Payload（コード不具合・特定入力）**: 特定のエンドポイント、特定のテナント／リクエストパラメータでのみ例外スタックトレースが発生していないか。

## 3. リビジョン／Pod 別エラー相関分析規約

Cloud Run や GKE の調査では、取得したログを `resource.labels.revision_name`（または `pod_name`）単位で集計し、どのバージョンでエラーが混入したかを以下の形式で対比報告します：

```text
=== REVISION ERROR CORRELATION (UTC) ===
Revision: my-service-00005-xyz
  Window: 2026-11-10T05:10:00Z .. 2026-11-10T06:00:00Z
  Status: ❌ 42 Errors (2 Error Types)
  - [500] TypeError: NoneType object is not subscriptable (38 hits, first: 05:10:12Z)
  - [504] Upstream deadline exceeded (4 hits, first: 05:14:03Z)
----------------------------------------
Revision: my-service-00004-abc
  Window: 2026-11-10T01:00:00Z .. 2026-11-10T05:10:00Z
  Status: ✅ CLEAN (0 Errors)
```
- 「N 回の正常稼働またはクリーンなリビジョンの後に**最初に失敗したイベント (`first_seen`)**」を特定し、Audit Logs のデプロイ時刻と突合します。

## 4. 時系列集計・Unicode Sparkline・異常スパイク時間帯の特定

### Unicode Sparkline と記述統計の出力規約
エラー件数やレイテンシの時系列推移を報告する際は、1分または5分単位の時間枠に集計し、8段階のブロック文字（` ▂▃▄▅▆▇█`、最小／0件は半角スペース ` `）を用いた Sparkline と統計値を提示します。
- **[Data Integrity 鉄則]** ログが存在しない時間帯（0件の時間枠）に推測値を補完してはいけません。連続した時間軸を生成し、ログがない時間帯は正確に `0` として扱います。

```text
=== LOG VOLUME / ERROR TIMELINE (UTC) ===
Metric:   severity>=ERROR 件数 (5分ごとの集計)
Window:   2026-11-10T04:00:00Z .. 2026-11-10T06:00:00Z (UTC)
Shape:    |    ▂█▇▆▅▃▂     |
Stats:    合計=128件, 最小=0件/5分, 平均=5.3件/5分, 最大=45件/5分 (ピーク時刻: 05:15:00Z)
```

### 異常スパイク特定時の内部ロジックと平易な日本語での報告ルール
時系列データからログやエラーの急増（スパイク）時刻を特定する際は、内部計算として以下の手順を行います：
1. **内部計算（過検知の防止）**: 各時間帯の件数に対して平均からの乖離（Z-Score 初期基準 `3.0` 以上など）でスパイク候補を抽出します。もし全時間帯の **5% を超える**枠が異常と判定された場合は、細かい揺れを拾いすぎているため、移動平均による平滑化や基準の引き上げを行い、本当に突出している時間帯のみに絞り込みます。
2. **【必須】レポート出力時は専門用語を使わず平易な日本語で記述する**:
   - ユーザー向けの最終レポートには、**「バケット」「Z-Score」「閾値 3.0」「5% ノイズ自己点検」といった統計用語・内部ルール名をそのまま出力してはいけません**。
   - 必ず**「5分ごとの集計枠」「普段は5分あたり平均約X件で推移していますが、`02:05:00Z〜02:10:00Z` の5分間だけ最大Y件へ急増（スパイク）しています」**のように、誰が読んでも直感的に意味が伝わる平易な日本語で報告してください。
