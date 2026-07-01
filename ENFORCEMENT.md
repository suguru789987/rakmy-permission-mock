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

**区分(tier)とスコープは独立・スコープは割当(user_roles)で束縛**：ロール定義の区分・範囲は既定値で、実効スコープは `user_roles.scope_type`＋`store_ids`（割当時）で決まる。同一人物でも割当で複数店舗/全社を持てる（従業員が複数店舗所属・従業員に会社ロール・データ範囲=会社 等を許容）。区分×範囲は自由に組み合わせ可。**越境防御はロール区分でなく指標の機密(sensitivity)×実効スコープでゲート**（§4）するため、店舗ロール＋全社にしても全社集計/機密company指標は除外され漏洩しない。

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

---

## 10. feature_key 体系設計（UI ↔ バックエンド判定キー）
モックの「カテゴリ→機能」を、永続安定な `feature_key` に1:1で写す。インデックス(fi)ではなく**意味のあるキー**で固定（画面追加・並べ替えに耐える）。

### 命名規則
- `feature_key = "<category_id>"`（単一機能カテゴリ）／`"<category_id>.<slug>"`（複数機能）。
- カテゴリ群：`view`（一覧画面権限）/`ops`（設定画面権限）。判定の閾値はこの群に依存。
- 例（抜粋）：

| UI カテゴリ/機能 | group | feature_key | 取りうる権限 |
|---|---|---|---|
| ダッシュボード（閲覧） | view | `dashboard` | 閲覧固定（常時1） |
| 売上分析 | view | `sales` | なし/閲覧（+export op） |
| 集計・予実 | view | `report` | なし/閲覧 |
| 従業員（閲覧） | view | `emp_view` | なし/閲覧（店長のみ・自店舗） |
| 発注先&仕入商品 | ops | `vendor` | なし/閲覧/操作/全て |
| 納品書 | ops | `delivery` | 〃 |
| 棚卸（実施／商品管理） | ops | `inventory.exec` / `inventory.product` | 〃 |
| 従業員管理（台帳/給与/勤怠…） | ops | `employees.ledger` / `employees.payroll` / … | 〃（会社ロール中心） |
| 締め管理 | ops | `closing` | 〃（会社ロール） |
| 予算設定 / 費用設定 | ops | `budget` / `cost` | 〃 |
| ダッシュボード（カスタマイズ） | ops | `uicustom` | なし/操作（編集/DnD/タグ作成） |

### キーの規律
- **コントローラ/アクション側に `feature_key` を宣言**（`require_permission 'vendor', op: :create` 等）。UIの feature_key と**同一の辞書**を共有（コード生成 or 定数表）。
- 画面新設時は **role_permissions に既定 level=0（なし）**で全ロールに並ぶ＝デフォルト拒否。付与は権限設定UIで。
- `metric_key`（指標）は feature_key とは別系統（`metrics.key`）。指標の可否は `role_metrics`＋機密で判定。

## 11. 画面別 判定実装例（Rails / Pundit 風）

### 11-1. 発注先&仕入商品（`vendor`・edit・店舗スコープ）
```ruby
class VendorsController < ApplicationController
  def index   # 一覧表示
    authorize_feature! 'vendor', need_level: 1            # 閲覧
    @vendors = Vendor.for_user(current_user)              # スコープ強制
  end
  def create
    authorize_feature! 'vendor', op: :create             # 登録（案C：登録↔編集連動）
    @vendor = Vendor.new(vendor_params.merge(store_id: scoped_store_id!))
    ...
  end
  def update; authorize_feature! 'vendor', op: :update; ...; end
  def destroy
    authorize_feature! 'vendor', op: :delete             # 削除＝独立判定（全て相当）
    ...
  end
end

# 基底
def authorize_feature!(key, need_level: 1, op: nil)
  perm = current_user.effective_permissions[key]
  raise Forbidden unless perm && perm.level >= need_level
  raise Forbidden if op && !perm.ops[op]
end
def scoped_store_id!     # 作成時：自店舗 or 指定店舗のいずれかに属するか検証
  sid = params[:store_id].to_i
  ids = effective_store_ids(current_user)
  raise Forbidden unless ids == :all || ids.include?(sid)
  sid
end
```

### 11-2. ダッシュボード（`dashboard`・閲覧固定＋指標 allowlist）
```ruby
def show
  # 閲覧は全ロール常時可（ランディング）＝level判定不要（feature_key 'dashboard' は常時1）
  metrics = DashboardMetric.all
            .where(id: visible_metric_ids(current_user))   # role_metrics の allowlist
            .reject { |m| crosses_boundary?(m, current_user) } # 機密×スコープ越境防御
  render_dashboard(metrics)
end
def visible_metric_ids(user)
  RoleMetric.where(role_id: user.role_ids, visible: true).pluck(:metric_id).uniq
end
def crosses_boundary?(metric, user)
  # 全社集計/機密=company は scope all のロールが無ければ除外（多層防御をサーバ側で再現）
  (metric.scope == 'company' || metric.sensitivity == 'company') && !user.has_company_scope?
end
```

### 11-3. 売上分析（`sales`・閲覧＋エクスポート＋スコープ＋指標）
```ruby
def index
  authorize_feature! 'sales', need_level: 1
  @rows = Sales.for_user(current_user)            # 店舗スコープ
            .visible_metrics_for(current_user)     # 指標 allowlist
end
def export
  authorize_feature! 'sales', op: :export         # エクスポートは個別op（閲覧の付随操作）
  send_csv(Sales.for_user(current_user))
end
```

### 11-4. 従業員管理（`employees.*`・会社ロール中心・台帳は店長=自店舗）
```ruby
def index   # 従業員台帳一覧
  authorize_feature! 'employees.ledger', need_level: 1
  @emps = Employee.for_user(current_user)         # 店長=自店舗 / 会社ロール=全社
end
def payroll # 給与（会社ロールのみ＝fixed）
  authorize_feature! 'employees.payroll', need_level: 1
  # role_permissions に store ロールの employees.payroll が存在しない（=なし固定）
end
```

### 11-5. 締め管理（`closing`・会社ロール操作／店舗は閲覧のみ）
```ruby
def index;  authorize_feature! 'closing_view', need_level: 1; end  # 締め状況＝閲覧（店舗ロール可）
def close;  authorize_feature! 'closing',     op: :update;   end   # 締め処理＝操作（会社ロール）
```

### 共通：スコープの `for_user`
```ruby
module StoreScoped
  def self.included(base)
    base.scope :for_user, ->(user) {
      ids = effective_store_ids(user)
      ids == :all ? all : where(store_id: ids)     # 会社ロール=:all は無制限
    }
  end
end
# 店舗データを持つモデル(Vendor/Sales/Employee/Inventory…)に include
```

### まとめ（判定の対応表）
| UI操作 | 判定 |
|---|---|
| 画面表示（閲覧） | `need_level: 1` |
| 登録 | `op: :create`（連動で update も） |
| 編集 | `op: :update` |
| 削除 | `op: :delete`（独立・破壊的） |
| エクスポート | `op: :export` |
| 設定（管理系） | `need_level: 2`（設定可） |
| データ範囲 | `for_user` スコープで強制 |
| 指標 | `role_metrics` allowlist ＋ 機密×スコープ越境防御 |

---

## 付録A. feature_key 辞書（全カテゴリ網羅・27カテゴリ60機能）
UIの全カテゴリ・機能と判定キーの完全対応。`view`=一覧画面権限(なし/閲覧)、`ops`=設定画面権限(なし/閲覧/操作/全て)。単一機能カテゴリは `<category_id>`、複数は `<category_id>.<slug>`。slugは実装確定時に意味的命名を踏襲（本表は提案）。

| group | feature_key | UI名 | ctx | 取りうる権限 | 備考 |
|---|---|---|---|---|---|
| view | `dashboard.main` | ダッシュボード | common | 閲覧固定 |  |
| view | `dashboard.news` | お知らせ（ニュース） | common | 閲覧固定 |  |
| view | `sales.abc` | ABC分析 | common | なし/閲覧 |  |
| view | `sales.product` | 商品別分析 | common | なし/閲覧 |  |
| view | `sales.hourly` | 時間帯別分析 | common | なし/閲覧 |  |
| view | `sales.weekday` | 曜日別分析 | common | なし/閲覧 |  |
| view | `sales.payment` | 支払種別分析 | common | なし/閲覧 |  |
| view | `purchase.vendor` | 仕入先別分析 | common | なし/閲覧 |  |
| view | `purchase.product` | 商品別分析 | common | なし/閲覧 |  |
| view | `purchase.costitem` | 費目別分析 | common | なし/閲覧 |  |
| view | `purchase.unit_price` | 商品仕入単価 | common | なし/閲覧 |  |
| view | `purchase.avg_price` | 平均単価推移 | common | なし/閲覧 |  |
| view | `detail.progress` | 進捗分析 | common | なし/閲覧 |  |
| view | `detail.sensitivity` | 感度分析 | shop | なし/閲覧 |  |
| view | `detail.inflow` | 流入分析 | shop | なし/閲覧 |  |
| view | `detail.table` | テーブル稼働分析 | shop | なし/閲覧 |  |
| view | `report.annual_pl` | 年間予実対比 | common | なし/閲覧 |  |
| view | `report.pl` | 予実対比 | common | なし/閲覧 |  |
| view | `report.monthly` | 月次集計 | shop | なし/閲覧 |  |
| view | `report.monthly_report` | 月次レポート | common | なし/閲覧 |  |
| view | `report.daily_report` | 日次レポート | common | なし/閲覧 |  |
| view | `report.order_report` | 発注分析レポート | shop | なし/閲覧 |  |
| view | `emp_view` | 従業員画面の閲覧（一覧） | common | なし/閲覧 | 店長以上 |
| view | `closing_view` | 締め状況の閲覧 | common | なし/閲覧 |  |
| ops | `data.download` | ダウンロード | company | なし/実行可 | 会社ロールのみ |
| ops | `data.extract` | 売上・仕入データ抽出 | company | なし/閲覧 | 会社ロールのみ |
| ops | `uicustom.widget` | ダッシュボードカスタマイズ（ウィジェット/プリセット） | common | なし/閲覧/操作/全て |  |
| ops | `uicustom.tag` | カスタムタグ作成・管理（本部のみ） | common | なし/閲覧/操作/全て | 会社ロールのみ |
| ops | `uicustom.dnd_shop` | UIカスタマイズ：DnD編集（店舗画面） | common | なし/実行可 | 店長以上 |
| ops | `uicustom.dnd_company` | UIカスタマイズ：DnD編集（会社画面） | common | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `label` | ラベル（登録・一覧） | common | なし/閲覧/操作/全て |  |
| ops | `vendor` | 発注先&仕入商品（一覧・登録・編集） | shop | なし/閲覧/操作/全て |  |
| ops | `delivery` | 納品書管理（一覧・編集） | common | なし/閲覧/操作/全て |  |
| ops | `saleslog` | 売上（売上ログ入力・実績） | common | なし/閲覧/操作/全て |  |
| ops | `inventory.exec` | 棚卸実施（棚卸履歴・実施） | common | なし/閲覧/操作/全て |  |
| ops | `inventory.product` | 棚卸商品管理 | common | なし/閲覧/操作/全て |  |
| ops | `pettycash.manage` | 小口現金管理（一覧・登録・締め） | common | なし/閲覧/操作/全て |  |
| ops | `pettycash.expense_item` | 経費項目設定 | common | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `employees.manage` | 従業員の管理（登録・編集・勤怠・時間記録・人件費・履歴・打刻） | common | なし/閲覧/操作/全て | 店長以上 |
| ops | `employees.payroll` | 給与設定・履歴 | company | なし/閲覧/操作/全て | 会社ロールのみ |
| ops | `closing.close` | 締め処理（仮締め・本締め・一括） | company | なし/閲覧/操作/全て | 会社ロールのみ |
| ops | `closing.fiscal` | 会計年度設定 | company | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `users` | ユーザー（アカウント・招待） | common | なし/閲覧/設定可 |  |
| ops | `transfer` | 店舗間商品移動 | common | なし/閲覧/操作/全て |  |
| ops | `shop` | 店舗管理（一覧・登録・編集・削除） | company | なし/閲覧/操作/全て | 会社ロールのみ |
| ops | `company.info` | 会社情報 | company | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `company.setup` | 初期設定（アカウント登録） | company | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `billing` | お支払い（請求・契約・プラン） | company | なし/閲覧/設定可 | 会社ロールのみ |
| ops | `shopinfo` | 店舗情報 | shop | なし/閲覧/操作/全て |  |
| ops | `integration` | 連携設定（POS／仕入／勤怠の連携先） | shop | なし/閲覧/設定可 |  |
| ops | `cost.setting` | 費用設定（費目別の費用予算・費目の追加/編集/削除） | shop | なし/閲覧/操作/全て |  |
| ops | `cost.actual_list` | 費用実績入力・一覧（費目×月の実績入力／年間一覧表示・CSV取込） | shop | なし/閲覧/操作/全て |  |
| ops | `holiday` | 休業日設定 | shop | なし/閲覧/操作/全て |  |
| ops | `budget.list` | 予算一覧 | shop | なし/閲覧 |  |
| ops | `budget.monthly_wizard` | 月次予算設定（ウィザード） | shop | なし/閲覧/操作/全て |  |
| ops | `budget.month_cost` | 単月費用設定 | shop | なし/閲覧/操作/全て | →月次予算設定（ウィザード）連動 |
| ops | `budget.sales_ratio` | 売上構成比設定 | shop | なし/閲覧/操作/全て | →月次予算設定（ウィザード）連動 |
| ops | `budget.weekday_bias` | 曜日別バイアス設定 | shop | なし/閲覧/操作/全て | →月次予算設定（ウィザード）連動 |
| ops | `budget.annual_list` | 年間予算一覧 | shop | なし/閲覧 |  |
| ops | `budget.calendar` | 予実管理カレンダー（日次） | shop | なし/閲覧 |  |

**注記**
- `会社ロールのみ`（fixed）＝ロール tier=company のみ付与可（店舗ロールは判定キー自体が存在＝なし固定）。
- `店長以上`（noStaff）＝店舗ロールのうち店長/エリア長のみ（従業員=不可）。
- `→…連動`（inheritFrom）＝親機能の権限に自動追従（独立判定しない）。
- ダッシュボード(`dashboard.*`)は閲覧固定（常時level1）。指標は `role_metrics` で別判定。
