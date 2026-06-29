# P0：基盤（テーブル定義＋保存＋シャドー）詳細設計

ロードマップ P0 の実装仕様。**判定はまだ効かせず**、(1)権限を保存できる (2)実効権限を計算できる (3)各操作で「新権限なら通すか」をログだけ出す（シャドー）まで。Rails/PostgreSQL 前提・論理設計（実本番列ダンプは含めない）。

## 0. ゴールと非ゴール
- **ゴール**：新テーブル作成／UIから role_permissions 保存／`effective_permissions(user)` 計算＋キャッシュ／**シャドーで現状挙動との差分を収集**。
- **非ゴール**：実際の拒否（enforce）。本番挙動は**従来のまま**。
- **可逆性**：判定未接続のため影響ゼロ。テーブル追加のみ（本体非破壊）。

## 1. マイグレーション（Rails）
```ruby
class CreatePermissionFoundation < ActiveRecord::Migration[7.0]
  def change
    create_table :roles do |t|
      t.string  :key,  null: false           # 'manager','keiri',... / custom='role_<n>'
      t.string  :name, null: false
      t.string  :tier, null: false            # 'shop' | 'company'
      t.boolean :is_system, null: false, default: false
      t.bigint  :created_by
      t.timestamps
    end
    add_index :roles, :key, unique: true

    create_table :role_permissions do |t|
      t.references :role, null: false, foreign_key: true
      t.string  :feature_key, null: false     # 付録A の辞書キー
      t.integer :level, null: false, default: 0  # 0なし 1閲覧 2操作 3全て
      t.jsonb   :ops, null: false, default: {}   # {create:,update:,delete:,export:,...}
      t.timestamps
    end
    add_index :role_permissions, [:role_id, :feature_key], unique: true

    create_table :role_feature_items do |t|     # 指標/画面項目の表示可否（任意）
      t.references :role, null: false, foreign_key: true
      t.string  :feature_key, null: false
      t.string  :item_key,    null: false
      t.boolean :visible, null: false, default: true
    end
    add_index :role_feature_items, [:role_id, :feature_key, :item_key], unique: true, name: 'idx_rfi_unique'

    create_table :user_roles do |t|
      t.bigint  :user_id, null: false          # 経営管理ログインアカウント(master連動)
      t.references :role, null: false, foreign_key: true
      t.string  :scope_type, null: false       # 'self' | 'stores' | 'all'
      t.bigint  :store_ids, array: true, default: []
      t.bigint  :assigned_by
      t.timestamps
    end
    add_index :user_roles, [:user_id, :role_id], unique: true
    add_index :user_roles, :user_id

    create_table :metrics do |t|                # 指標メタ（P4で本格運用・P0は箱だけ）
      t.string :key, null: false
      t.string :name
      t.string :sensitivity, null: false, default: 'company'  # fail-closed既定
      t.string :category
      t.string :scope, null: false, default: 'store'          # 'store'|'company'
      t.boolean :is_system, default: false
    end
    add_index :metrics, :key, unique: true

    create_table :role_metrics do |t|
      t.references :role, null: false, foreign_key: true
      t.references :metric, null: false, foreign_key: true
      t.boolean :visible, null: false, default: false
    end
    add_index :role_metrics, [:role_id, :metric_id], unique: true

    create_table :audit_logs do |t|
      t.bigint :actor_id
      t.string :action, null: false            # grant/revoke/change_perm/assign/unassign/delegate
      t.bigint :target_role_id
      t.bigint :target_user_id
      t.jsonb  :detail, default: {}
      t.datetime :created_at, null: false
    end
    add_index :audit_logs, :created_at
  end
end
```

## 2. モデル
```ruby
class Role < ApplicationRecord
  has_many :role_permissions, dependent: :destroy
  has_many :user_roles, dependent: :restrict_with_error
  has_many :role_metrics, dependent: :destroy
  validates :key, :name, :tier, presence: true
  validates :tier, inclusion: %w[shop company]
end

class RolePermission < ApplicationRecord
  belongs_to :role
  validates :level, inclusion: 0..3
end

class UserRole < ApplicationRecord
  belongs_to :role
  validates :scope_type, inclusion: %w[self stores all]
end
```

## 3. 実効権限（計算＋キャッシュ）
```ruby
module EffectivePermissions
  # { 'vendor' => Struct(level:Int, ops:Hash), ... } を返す（全ロール和集合）
  def effective_permissions
    Rails.cache.fetch("eff_perm:#{id}:#{perm_version}", expires_in: 12.hours) do
      acc = Hash.new { |h,k| h[k] = { level: 0, ops: {} } }
      RolePermission.where(role_id: role_ids).find_each do |rp|
        e = acc[rp.feature_key]
        e[:level] = [e[:level], rp.level].max          # max level
        rp.ops.each { |k,v| e[:ops][k] ||= false; e[:ops][k] ||= v }  # OR ops
      end
      acc
    end
  end

  def effective_store_ids
    return :all if user_roles.any? { |ur| ur.scope_type == 'all' }
    ids = []
    user_roles.each do |ur|
      ids |= ur.store_ids       if ur.scope_type == 'stores'
      ids |= [home_store_id]    if ur.scope_type == 'self'
    end
    ids
  end

  def role_ids; user_roles.pluck(:role_id); end
  def perm_version; ... end   # 権限/割当の更新で変わるトークン（cache key）。変更時に bump
end
class User < ApplicationRecord; include EffectivePermissions; end
```
- **invalidate**：role_permissions / user_roles を更新したら `perm_version` を bump（該当ユーザー or 全体）。

## 4. 保存フロー（権限設定UI → DB）
モックの「権限編集（ウィザード）保存」に対応する API。モックの内部表現（feature_key 毎の level＋ops、指標 allowlist）をそのまま受ける。
```ruby
# PUT /admin/roles/:id/permissions
def update_permissions
  role = Role.find(params[:id])
  ActiveRecord::Base.transaction do
    params[:permissions].each do |fk, p|        # fk=feature_key, p={level:, ops:{}}
      rp = role.role_permissions.find_or_initialize_by(feature_key: fk)
      rp.update!(level: p[:level], ops: p[:ops] || {})
    end
    # 指標 allowlist（任意）
    Array(params[:metrics]).each do |mk, visible|
      m = Metric.find_by!(key: mk)
      role.role_metrics.find_or_initialize_by(metric: m).update!(visible: visible)
    end
    AuditLog.create!(actor_id: current_user.id, action: 'change_perm',
                     target_role_id: role.id, detail: { keys: params[:permissions].keys },
                     created_at: Time.current)
  end
  bump_perm_version!   # キャッシュ無効化
  head :ok
end
```
- バリデーション：feature_key は**辞書（付録A）に存在するキーのみ**許可（不明キーは弾く）。tier 不整合（会社専用キーを店舗ロールに）も拒否。

## 5. シャドー検証（判定は効かせず差分ログ）
各リクエストで「新権限なら許可/拒否はどうか」を計算し、**現状の実挙動と比較してログだけ**出す。実際の許可/拒否は**従来ロジックのまま**。
```ruby
# 各アクションに宣言（enforce せず観測のみ）
class VendorsController < ApplicationController
  shadow_permission 'vendor', need_level: 1, on: :index
  shadow_permission 'vendor', op: :create,  on: :create
end

module ShadowPermission
  def shadow_check(key, need_level: 1, op: nil)
    decided = would_allow?(current_user, key, need_level, op)   # 新権限の判定
    actual  = true   # 現状はこのアクションに到達＝従来は許可されている
    unless decided == actual
      Rails.logger.info(shadow: { user: current_user.id, key: key, op: op,
        new_decision: decided, actual: actual, path: request.path })
      ShadowMiss.create!(...)   # 集計用テーブルに記録（任意）
    end
  end
end
```
- **読み方**：`new_decision:false, actual:true` ＝**過剰ブロック候補**（現状通っているのに新権限で塞がる）。これがP1有効化前に潰すべき差分。
- 逆（`new:true, actual:false`）は現状で既に塞がっている画面に到達していない＝基本出ない。
- **集計**：feature_key×ロール別に「過剰ブロック件数」を日次集計。0に収束したら P1（実拒否）へ。

## 6. シード（移行ベースライン）
- 既存 `master`/`manager`/`shop_manager` を初期ロールへ写像（ROADMAP P5の前倒し最小版）：
  - master→`owner`(is_system, 全権)／manager→`manager`(shop, self)／shop_manager→`area`(shop, stores)／本部相当→`company`系。
- 各既存アカウントに対応する `user_roles` を生成（scope_type/store_ids を所属から）。
- これによりシャドーで「現状ロール≒新ロール」の差分が測れる。

## 7. 受入条件（P0完了 → P1へ）
1. UIから role_permissions / role_metrics が保存・再表示できる。
2. `effective_permissions` がキャッシュされ、更新で invalidate される。
3. 1〜2週間のシャドーで **過剰ブロック差分が想定内（主要画面で0付近）**。
4. 本番実挙動が**変化していない**（判定未接続を確認）。

## 8. ロールバック
- フィーチャーフラグ `permissions.shadow` をOFFにすればログ収集も停止。テーブルは残置（無害）。判定未接続のため業務影響なし。

> 上位設計＝`ENFORCEMENT.md`、段階全体＝`ROADMAP.md`、UI＝`README.md`/`index.html`、辞書＝ENFORCEMENT 付録A。
