---
name: blameless-postmortem
description: Google SRE のベストプラクティスに基づき、インシデントのタイムライン、根本原因、教訓、および再発防止アクションアイテムを含む Blameless Postmortem（障害報告書）を Markdown 形式で作成するスキル。ユーザーからポストモーテムやふりかえりドキュメントの作成を求められた際にロードしてください。
metadata:
  author: SRE Agent Team
  version: 1.0.0
  status: published
---

# Blameless Postmortem Generator Skill

このスキルは、調査が完了したインシデントについて、Google SRE の Postmortem Culture（参照: `https://sre.google/workbook/postmortem-culture/`）に準拠した構造化ドキュメントを作成します。

## 1. 執筆のコア原則

1. **Blameless（個人を責めない文化）**:
   - 「誰がミスをしたか」ではなく、「なぜシステム・監視・デプロイパイプライン・ガードレールがその事象を防げなかったのか／早期検知できなかったのか」というシステム要因に焦点を当てます。
2. **データ完全性 (Data Integrity)**:
   - タイムラインの時刻やエラー件数は、Cloud Logging で実際に確認された事実のみを記載し、推測のタイムスタンプを作ってはいけません（不明な箇所は「要確認」と明記します）。
3. **タイムラインの書式規約**:
   - タイムラインは視認性と情報密度を高めるため、表ではなく**箇条書きリスト**で記述します。
   - 先頭に日付とタイムゾーン（原則 `TZ=UTC`、必要に応じて JST 併記）を宣言します。
   - 以下の重要マイルストーンには必ず矢印マーカーを付与します：
     - `<== Start of Incident`（障害発生／トリガー時刻）
     - `<== Incident Detected`（検知時刻）
     - `<== Mitigation`（緩和策適用時刻）
     - `<== End of Incident`（復旧完了時刻）
4. **Action Items（再発防止策）の分類**:
   - 各アクションアイテムには必ず `Type` として **`Mitigate`（影響緩和・止血の迅速化）**、**`Detect`（検知・アラート改善）**、**`Prevent`（根本的な再発防止）** のいずれかと、優先度（`P1` / `P2` / `P3`）を割り当てます。

## 2. Postmortem Markdown テンプレート

以下のテンプレート構造に従って出力してください：

```markdown
# Postmortem: [インシデントの簡潔なタイトル]

## Executive Summary
[インシデントの概要、発生期間、ユーザー／システムへの影響、根本原因、およびどのように解決されたかを1段落で簡潔に要約]

## Impact
- **影響期間**: YYYY-MM-DD HH:MM UTC 〜 HH:MM UTC（計 XX 分）
- **影響範囲**: [対象サービス・リビジョン・エラー件数やエラー率などログから確認できた定量的事実]

## Root Causes and Trigger
- **Trigger（直接の引き金）**: [YYYY-MM-DD HH:MM:SS UTC に発生したデプロイ、設定変更、トラフィックスパイク等の具体的なトリガー]
- **Root Cause（根本原因）**: [なぜそのトリガーが障害に直結したのかの技術的メカニズムと、Google Developer Knowledge で確認した公式仕様上の背景]

## Detection and Monitoring
[どのように検知されたか、既存のログ・アラートでどこが機能し、どこに検知の遅れや死角があったか]

## Mitigation
[影響を抑えるために実施（または提案）した緩和策と、その効果]

## Lessons Learned

### Things That Went Well（うまくいったこと）
- ...

### Things That Went Poorly（改善が必要なこと）
- ...

### Where We Got Lucky（幸運だったこと）
- ...

## Action Items

| Action Item | Type | Priority | Owner / Target |
| :--- | :--- | :--- | :--- |
| [具体的な対策内容] | **Mitigate** / **Detect** / **Prevent** | **P1** / **P2** / **P3** | [担当または対象コンポーネント] |

## Timeline
Day: **YYYY-MM-DD** (TZ=UTC)
- `HH:MM:SS`: [イベント・変更内容] <== **Start of Incident**
- `HH:MM:SS`: [エラーログ初出・症状の拡大]
- `HH:MM:SS`: [アラート発火または調査開始] <== **Incident Detected**
- `HH:MM:SS`: [緩和策の適用] <== **Mitigation**
- `HH:MM:SS`: [エラー収束・正常化確認] <== **End of Incident**

---
> **Note**: この Postmortem ドラフトは Cloud Logging の調査結果と公式ドキュメントに基づき AI が生成しました。提出前に内容とタイムラインをレビューしてください。
```
