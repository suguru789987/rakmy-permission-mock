# 本番 enforcement 層 設計（権限の実強制）

モック（UI＝権限をどう設定するか）に対し、**設定した権限を本番で実際に効かせる**バックエンド設計。Rails / Pundit 前提・論理設計レベル（実本番スキーマの列ダンプは含めない）。

## 0. 原則
- **UIで設定 → DBに保存 → 各操作で判定 → スコープで範囲限定 → ログ記録**、を一貫させる。
- **権限はロールに、ユーザーにはロールを割当**（権限→ロール→ユーザー・複数ロールは和集合）。
- **fail-closed**：判定不能・未設定は「拒否」。緩める方向のみ明示設定で。
- **スコープはクエリレベルで強制**（コントローラ毎の手当てに頼らない＝漏れ防止）。
- 本番 `rakmy`/`rakmy_server` 本体テーブルは非破壊。新規は別テーブルで付加し、既存ロール(master/manager/shop_manager)から移行。

## 1. データモデル（新規テーブル）

```
roles                      -- ロール定義（経理/店長/エリア長/カスタム…）
  id, key, name,
  tier            enum(shop, company),
  is_system       bool,           -- オーナー等の固定ロール
  created_by, created_at, updated_at

role_permissions           -- ロール×機能の権限（モックの「機能レベル＋操作詳細」）
  id, role_id, feature_key,        -- feature_key = カテゴリ.機能の安定キー
  level           int,            -- 0=なし 1=閲覧 2=操作 3=全て（4状態）
  ops             jsonb,          -- 操作詳細 {create,update,delete,export,...}（levelの内訳・微調整）
  unique(role_id, feature_key)

role_feature_items         -- 機能内の指標/画面項目の表示可否（任意・粒度が要る機能のみ）
  role_id, feature_key, item_key, visible bool

user_roles                 -- ユーザー(管理者)へのロール割当＋スコープ束縛
  id, user_id, role_id,
  scope_type      enum(self, stores, all),   -- self=自店舗 / stores=指定店舗群 / all=全社
  store_ids       bigint[],                  -- scope_type=stores の対象店舗
  assigned_by, assigned_at,
  unique(user_id, role_id)

metrics                    -- 指標メタ（§12-8 のデータ化。486〜737種）
  id, key, name,
  sensitivity     enum(open, store, company), -- 機密レベル（越境防御の軸）
  category,                                    -- 系統（売上/仕入原価/人件費/固定費/利益…）
  scope           enum(store, company),        -- 自店舗集計 / 全社集計
  is_system       bool

role_metrics               -- ロールが閲覧できる指標（指標一覧＝allowlist）
  role_id, metric_id, visible bool
  -- ダッシュボード等の「閲覧可能指標」はここを自動反映（読取）

audit_logs                 -- 監査
  id, actor_id, action enum(grant, revoke, change_perm, assign, unassign, delegate),
  target_role_id, target_user_id, detail jsonb, created_at
```

- **enforcement判定はキャッシュ可能な「実効権限」へ集約**：`effective_permissions(user)` = 全 user_roles の role_permissions を feature_key で**和集合（max level / OR ops）**。
- **スコープも和集合**：`effective_store_ids(user)` = 各 user_roles の scope を合算（後述）。

## 2. 権限判定（Pundit ポリシー）
各コントローラ/アクション（＝画面・API・操作）の前で判定。

```ruby
# 例：ApplicationPolicy 基底
def allow?(feature_key, need_level: 1, op: nil)
  perm = current_user.effective_permissions[feature_key]   # キャッシュ
  return false unless perm
  return false if perm.level < need_level                  # 4状態の閾値
  return false if op && !perm.ops[op]                      # 操作詳細(create/update/delete/export)
  true
end
```
- 画面表示＝`need_level: 1(閲覧)`、登録/編集＝`op: :create/:update`、削除＝`op: :delete`（破壊的＝level 3相当）。
- **UI と同じ feature_key 体系**を使い、モックの「操作/閲覧/なし・操作詳細」がそのまま判定に対応。
- **削除はポリシーでも別扱い**（案C：操作と分離。`op: :delete` を明示要求）。

## 3. スコープ強制（最重要・性能と安全の肝）
「店長＝自店舗 / エリア長＝管轄店 / 会社ロール＝全社」を**クエリで強制**。

```ruby
def effective_store_ids(user)
  ids = []
  user.user_roles.each do |ur|
    case ur.scope_type
    when 'all'    then return :all                 # 全社（会社ロール）→ 制限なし
    when 'stores' then ids |= ur.store_ids
    when 'self'   then ids |= [user.home_store_id] # 従業員台帳/アカウントの所属店舗
    end
  end
  ids
end
```
- **店舗スコープのモデルには共通スコープを適用**：`Model.for_user(user)` → `where(store_id: ids)`（`:all` なら無制限）。default_scope ではなく**明示的な query object / scope** にし、バッチ等の例外を制御。
- **全社集計指標（metrics.scope=company）は会社ロール（scope all）のみ**。店舗ロールには集計APIの段階でクランプ（越境防御 L6相当）。
- 直クエリ常用を避け、**集計バッチ/リードレプリカ/指標API**経由（CLAUDE.md ガバナンス）。

## 4. 指標カタログ＋越境防御
- ダッシュボード/分析の**指標応答を `role_metrics.visible` でフィルタ**（allowlist）。
- 加えて**機密×スコープの二重チェック**：`metrics.sensitivity=company` or `metrics.scope=company` の指標は、scope=all を持たないロールには**シード段階で付与しない＋応答でも除外**（多層防御 L1〜L8 をサーバ側で再現）。
- 新規/AI生成指標は **sensitivity を fail-closed（既定 company 扱い）**、緩めるのは人の承認後（§12-7）。

## 5. 適用タイミング・キャッシュ
- `effective_permissions` / `effective_store_ids` は**ユーザー単位でキャッシュ**（Redis等）。権限/割当変更時に**該当ユーザーのキャッシュを invalidate**。
- 変更反映は **publish 方式**（下書き→適用）を推奨。ログイン中ユーザーは次リクエストで反映。
- モックの「保存」はこの publish に対応。

## 6. 監査・ロックアウト防止
- **audit_logs** に grant/revoke/change/delegate を必須記録（特に削除権限付与・全権委譲・スコープ拡大）。
- **最後のオーナー/全権を剥奪できない**保護（削除/降格前にカウントチェック）。

## 7. 既存からの移行
- 既存 `master` / `manager` / `shop_manager` を新ロールへマッピング：
  - master → オーナー（全権・固定）または本部管理（会社ロール・scope all）
  - manager → 店長（shop・scope self）※店舗紐付けを user_roles.store へ
  - shop_manager / area → エリア長（shop・scope stores）
- 移行は**併存期間**を設け、新ロールで判定しつつ旧経路はフォールバック→段階的に撤去。

## 8. 段階導入（ロードマップ）
1. **データモデル＋ role_permissions の保存**（UIから書ける）。読み取り判定は既存のまま（影シャドー運用で差分検証）。
2. **Pundit 判定を主要画面から有効化**（閲覧→操作→削除の順）。
3. **スコープ強制**を店舗スコープモデルへ適用（最も慎重に・性能検証）。
4. **指標カタログ＋越境防御**をサーバ側で強制（指標メタ整備が前提）。
5. 監査・ロックアウト・publish・移行。

## 9. 未決・要確認
- feature_key の**安定キー体系**（UIのカテゴリ/機能と1:1で永続化）。画面追加時の付与既定＝なし。
- scope の**多階層**（エリア→店舗の包含、将来のマルチテナント親子）。
- 操作詳細(ops) を role_permissions.jsonb に持つか別テーブルか（監査・索引の要件次第）。
- 指標メタ（sensitivity/scope/category）の**整備主体と運用**（誰がいつ付与・AI分類の承認フロー）。

---
※本書は論理設計。実本番の実テーブル/列名・DBダンプは含めない（ガバナンス）。指標↔実列の確定マッピングは private リポを参照。
