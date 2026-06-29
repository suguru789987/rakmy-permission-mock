# 具体テストケース仕様（前提データ＋入力値＋期待結果）

`VERIFICATION.md`（検証項目・合格点の枠組み）の**実行可能な具体版**。前提データ（フィクスチャ）を固定し、「どの画面で・どのロール設定で・どの指標を・どう操作したら・どうなる」を1ケースずつ定義する。feature_key は `feature_keys.json` 準拠。

---

## 1. 前提データ（フィクスチャ）
テスト環境にこの固定データを投入してから実行する。

### 店舗
| store_id | 名称 |
|---|---|
| S1 | 麺屋ミライ 渋谷店 |
| S2 | 麺屋ミライ 新宿店 |
| S3 | 麺屋ミライ 池袋店 |

### ユーザー（管理者＝経営管理ログイン）
| user | home_store | 付与ロール(scope) |
|---|---|---|
| U-manager1 | S1 | 店長(self) |
| U-staff1 | S1 | 従業員(self) |
| U-area1 | S1 | エリア長(stores=[S1,S2]) |
| U-keiri1 | 本部 | 経理(all) |
| U-owner | 本部 | オーナー(全権固定) |
| U-multi | S2 | 店長(self) ＋ 経理(all)（兼務＝和集合の検証用） |

### ロール権限（role_permissions・主要キーのみ。空欄=既定なし）
| feature_key | 店長 | 従業員 | エリア長 | 経理 |
|---|---|---|---|---|
| vendor（発注先&仕入商品） | 操作 | なし | 操作 | 操作 |
| delivery（納品書） | 操作 | 閲覧 | 操作 | 操作 |
| inventory.exec（棚卸実施） | 操作 | なし | 操作 | 閲覧 |
| employees.ledger（従業員台帳） | 操作(自店舗) | なし | 操作(管轄) | 操作(全社) |
| employees.payroll（給与） | （キー無=なし） | （無） | （無） | 操作 |
| closing（締め処理） | （会社専用=なし） | （なし） | （なし） | 操作 |
| closing_view（締め状況・閲覧） | 閲覧 | 閲覧 | 閲覧 | 閲覧 |
| report（集計・予実） | 閲覧 | なし | 閲覧 | 閲覧 |
| sales（売上分析） | 閲覧(+export) | 閲覧 | 閲覧 | 閲覧 |
| dashboard（ダッシュボード） | 閲覧固定 | 閲覧固定 | 閲覧固定 | 閲覧固定 |

### 指標（metrics・抜粋）
| metric_key | 名称 | sensitivity | scope |
|---|---|---|---|
| sales_excluded | 売上(税抜) | open | store |
| customers | 客数 | open | store |
| op_profit_store | 営業利益(自店舗) | store | store |
| op_profit_company | 営業利益(全社) | company | company |
| labor_cost_company | 人件費(全社) | company | company |

### ロール指標 allowlist（role_metrics）
| metric | 店長 | 従業員 | 経理 |
|---|---|---|---|
| sales_excluded | 表示 | 表示 | 表示 |
| op_profit_store | 表示 | 非表示 | 表示 |
| op_profit_company | 非表示 | 非表示 | 表示 |
| labor_cost_company | 非表示 | 非表示 | 表示 |

---

## 2. テストケース（画面×設定×入力×期待結果）

### P1 閲覧判定
| ID | 画面/操作 | 実行ユーザー(設定) | 入力 | 期待結果（合格） |
|---|---|---|---|---|
| TC-P1-01 | 発注先一覧 GET /vendors | U-staff1（vendor=なし） | 画面アクセス | 403（閲覧不可） |
| TC-P1-02 | 発注先一覧 GET /vendors | U-manager1（vendor=操作） | 画面アクセス | 200（閲覧可） |
| TC-P1-03 | 集計・予実 GET /report | U-staff1（report=なし） | 画面アクセス | 403 |
| TC-P1-04 | 集計・予実 GET /report | U-manager1（report=閲覧） | 画面アクセス | 200 |
| TC-P1-05 | 給与 GET /employees/payroll | U-manager1（payrollキー無=なし） | 画面アクセス | 403（会社ロール専用） |
| TC-P1-06 | 給与 GET /employees/payroll | U-keiri1（payroll=操作） | 画面アクセス | 200 |

### P2 操作・削除判定
| ID | 画面/操作 | 実行ユーザー(設定) | 入力 | 期待結果 |
|---|---|---|---|---|
| TC-P2-01 | 発注先 登録 POST /vendors | U-manager1（vendor=操作） | {store_id:S1, name:"新規仕入先"} | 201（登録成功） |
| TC-P2-02 | 発注先 登録 POST /vendors | U-staff1（vendor=なし） | 同上 | 403 |
| TC-P2-03 | 案C連動：登録を許可 | 設定UIで店長 vendor.登録=許可 | 保存→再取得 | vendor.編集も自動=許可（登録↔編集連動） |
| TC-P2-04 | 案C連動：操作をなし | 設定UIで店長 vendor=なし | 保存→再取得 | 登録/編集/削除すべてOFF |
| TC-P2-05 | 削除 DELETE /vendors/:id（確認なし） | U-manager1（vendor=操作・削除OFF） | 削除実行 | 403（削除未付与） |
| TC-P2-06 | 削除：opt-in | 設定UIで店長 vendor.削除=許可（確認OK） | 保存→DELETE実行 | 削除成功＋audit_logs記録／確認キャンセル時は付与されず |

### P3 スコープ強制
| ID | 画面/操作 | 実行ユーザー(設定) | 入力 | 期待結果 |
|---|---|---|---|---|
| TC-P3-01 | 発注先一覧 | U-manager1（店長@S1） | GET /vendors | S1のデータのみ。S2/S3=0件 |
| TC-P3-02 | 発注先 他店直指定 | U-manager1（店長@S1） | GET /vendors/:id（S2の発注先） | 403 or 空（越境不可） |
| TC-P3-03 | 発注先一覧 | U-area1（エリア長[S1,S2]） | GET /vendors | S1+S2のみ。S3=0件 |
| TC-P3-04 | 発注先一覧 | U-keiri1（経理all） | GET /vendors | 全店（S1,S2,S3）表示 |
| TC-P3-05 | 兼務の和集合 | U-multi（店長@S2＋経理all） | GET /vendors | all優先で全店表示（和集合） |
| TC-P3-06 | 作成時の店舗検証 | U-manager1（店長@S1） | POST /vendors {store_id:S2} | 403（自店舗外への作成不可） |

### P4 指標カタログ＋越境防御
| ID | 画面/操作 | 実行ユーザー(設定) | 入力 | 期待結果 |
|---|---|---|---|---|
| TC-P4-01 | ダッシュボード指標 | U-manager1（店長） | GET /dashboard/metrics | sales_excluded, op_profit_store を含む |
| TC-P4-02 | 全社指標の越境 | U-manager1（店長） | 同上 | op_profit_company, labor_cost_company を**含まない**（機密company＝全社scopeロールのみ） |
| TC-P4-03 | allowlist外 | U-staff1（従業員・op_profit_store=非表示） | GET /dashboard/metrics | op_profit_store を含まない |
| TC-P4-04 | 会社ロール | U-keiri1（経理all） | GET /dashboard/metrics | op_profit_company を含む |
| TC-P4-05 | 直接API越境試行 | U-manager1（店長） | GET /metrics?key=op_profit_company | 403 or 空（allowlist＋機密で二重ブロック） |
| TC-P4-06 | 新規指標fail-closed | sensitivity未設定の新指標 | 店長で取得 | 含まれない（既定company扱い） |

### P5 運用機構
| ID | 操作 | 実行ユーザー | 入力 | 期待結果 |
|---|---|---|---|---|
| TC-P5-01 | 監査記録 | U-keiri1 | 店長 vendor=操作 に変更保存 | audit_logs に change_perm 記録（actor/対象/差分） |
| TC-P5-02 | 削除権限付与の監査 | U-owner | あるロールに vendor.削除=許可 | audit_logs に記録（破壊的付与） |
| TC-P5-03 | ロックアウト防止 | U-owner | 最後のオーナーを削除/降格 | 不可（ブロック・エラー） |
| TC-P5-04 | publish反映 | U-keiri1 | 権限変更を適用 | 適用後、対象ユーザーの次リクエストで反映 |
| TC-P5-05 | 移行一致 | - | master→owner, manager→店長(self), shop_manager→エリア長 で判定比較 | 移行前後で主要画面の許可/拒否が一致（差分0） |

---

## 3. 実行・記録ルール
- 各ケースは **前提（フィクスチャ）→入力→期待結果** を満たせば合格。結果は「OK/NG＋実値」で記録。
- スコープ系（P3/P4）は**他店ID・全社指標を意図的に指定**して「漏れない」ことを確認（ポジティブ＋ネガティブ両方）。
- 設定変更系（案C連動・削除opt-in）は**保存→再取得**で連動結果を確認。
- 自動化：RSpec/request spec でフィクスチャ＋各ケースを実装し CI 化を推奨。

> 合格点の枠組み＝`VERIFICATION.md`、設計＝`ENFORCEMENT.md`、判定キー＝`feature_keys.json`。
