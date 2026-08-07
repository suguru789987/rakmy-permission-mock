# -*- coding: utf-8 -*-
"""権限設定 引き継ぎ資料の整合チェック。
使い方: python3 tools/check_all.py
資料を直したら必ず実行する。NG が1件でもあれば終了コード1。
"""
import csv,re,sys,os,collections,subprocess
try: import openpyxl
except ImportError: openpyxl=None

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
DESK=os.path.expanduser("~/Desktop/権限設定_20260804")
NG=[]; WARN=[]
def tsv(p): return list(csv.DictReader(open(p,encoding="utf-8"),delimiter="\t"))
def chk(cat,name,cond,detail=""):
    print(f"  {'OK ' if cond else '★NG'} {name}"+(f"  {detail}" if detail and not cond else ""))
    if not cond: NG.append(f"[{cat}] {name}"+(f" / {detail}" if detail else ""))
def warn(name,cond,detail=""):
    if not cond: print(f"  ▲   {name}  {detail}"); WARN.append(name)

AC=tsv("20260803_06_権限設定_受入条件表_PdM引継.tsv")
TP=tsv("20260803_07_権限設定_検証プラン_PdM引継.tsv")
FL=tsv("20260803_09_権限設定_ケース別遷移フロー.tsv")
D8=tsv("dataset/08_権限設定値.tsv"); D9=tsv("dataset/09_指標の初期値.tsv"); D7=tsv("dataset/07_検証ユーザー.tsv")
HELP=open("help/draft-framer.md",encoding="utf-8").read()
DSMD=open("20260803_10_権限設定_検証用データセット.md",encoding="utf-8").read()
SPEC=open("20260803_05_権限設定_仕様書_PdM引継.md",encoding="utf-8").read()
acid={x["条件ID"] for x in AC}; tid={x["検証ID"] for x in TP}; fid={x[list(x)[0]] for x in FL}
HN={l.lstrip("# ").strip() for l in HELP.split("\n") if l.startswith(("## ","### "))}
HN|={re.split(r"[　(（]",n)[0] for n in HN}
ids=lambda s: set(re.findall(r"[ST]-\d+\w?",s))

print("\n■ 1. 参照先の実在")
chk("参照","受入条件表 → 検証ID", not [t for x in AC for t in ids(x["対応検証ID"]) if t not in tid],
    str([t for x in AC for t in ids(x["対応検証ID"]) if t not in tid][:5]))
chk("参照","検証プラン → 受入条件ID", not [t for x in TP for t in x["受入条件ID"].split() if t!="—" and t not in acid])
chk("参照","検証プラン → 遷移フローID", not [t for x in TP for t in x["遷移フローID"].split() if t!="—" and t not in fid])
def helpng(rows,k):
    o=[]
    for x in rows:
        v=x.get("ヘルプページの該当箇所","")
        if not v or v.startswith("—"): continue
        for part in re.split(r"／(?![^（]*）)",v):
            b=re.sub(r"（[^）]*）","",part).strip()
            if b and not any(b.startswith(n) or n in b for n in HN): o.append((x[k],b))
    return o
chk("参照","受入条件表 → ヘルプ見出し", not helpng(AC,"条件ID"), str(helpng(AC,"条件ID")[:3]))
chk("参照","検証プラン → ヘルプ見出し", not helpng(TP,"検証ID"), str(helpng(TP,"検証ID")[:3]))
sheets={f[:-4] for f in os.listdir("dataset") if f.endswith(".tsv")}
short={s.split("_")[0] for s in sheets}
def dsh(v):
    v=re.sub(r"US-\d+","",v); return set(re.findall(r"(?<![-\d])(\d{2})(?=[_（\s／]|$)",v))
chk("参照","検証プラン → データセットのシート", not [s for x in TP for s in dsh(x["使う検証データ"]) if s not in short])
PN={p["権限名"] for p in D8}
def perm_ok(v):
    # 「A → B」の付け替え表記に対応。各辺が権限名で始まっていればOK
    return all(any(part.strip().startswith(n) for n in PN) for part in v.split("→") if part.strip())
_bad=[(u["ID"],u["割当権限"]) for u in D7 if not perm_ok(u["割当権限"])]
chk("参照","検証ユーザーの割当権限が 08 に実在", not _bad, str(_bad))
chk("参照","検証ユーザーの担当店舗が 01 の店舗名と一致",
    not [(u["ID"],u["担当店舗"]) for u in D7
         if not any(k in u["担当店舗"] for k in ["全社","全店","—","-"]+[s["店舗名"].split()[-1] for s in tsv("dataset/01_店舗.tsv")])])

print("\n■ 2. 双方向の一致")
a2t={x["条件ID"]:ids(x["対応検証ID"])&tid for x in AC}
t2a=collections.defaultdict(set)
for x in TP:
    for a in x["受入条件ID"].split():
        if a!="—": t2a[a].add(x["検証ID"])
mism=[a for a in a2t if a2t[a] and t2a.get(a) and a2t[a]!=t2a[a]]
chk("双方向","受入条件表 ↔ 検証プラン", not mism, str([(a,sorted(a2t[a]^t2a[a])) for a in mism][:4]))
chk("双方向","範囲記法（〜）を使っていない", not [x["条件ID"] for x in AC if "〜" in x["対応検証ID"]])
if openpyxl and os.path.exists("20260806_権限設定_03_検証用データセット.xlsx"):
    wb=openpyxl.load_workbook("20260806_権限設定_03_検証用データセット.xlsx")
    plan=collections.defaultdict(set)
    for x in TP:
        for s in dsh(x["使う検証データ"]): plan[s].add(x["検証ID"])
    d=[r[0] for r in wb["目次"].iter_rows(min_row=5,values_only=True)
       if r and r[0] and str(r[0])[:2].isdigit() and plan.get(str(r[0])[:2],set())!=ids(str(r[4] or ""))]
    chk("双方向","データセット目次 ↔ 検証プラン", not d, str(d))

print("\n■ 3. 網羅")
mvp={x["条件ID"] for x in AC if x["実装レベル"] in ("MVP必須","品質必須")}
chk("網羅","MVP必須・品質必須が検証から参照される", not mvp-set(t2a), str(sorted(mvp-set(t2a))))
chk("網羅","受入条件に空欄が無い",
    not [x["条件ID"] for x in AC if not x["合格ライン（この数値を満たせば実装完了）"].strip() or not x["対応検証ID"].strip()])
chk("網羅","検証ケースに空欄が無い",
    not [x["検証ID"] for x in TP if not x["期待挙動"].strip() or not x["合否ライン"].strip() or not x["画面"].strip()])
chk("網羅","スクショに写すものが全件記入", not [x["検証ID"] for x in TP if not x["スクショに写すもの"].strip()])

print("\n■ 4. 件数の整合")
perm={x["権限名"] for x in D8}
chk("件数",f"権限7件（実データ{len(perm)}）",len(perm)==7)
chk("件数",f"検証ユーザー8名（実データ{len(D7)}）",len(D7)==8)
chk("件数",f"受入条件40件（{len(AC)}）",len(AC)==40)
chk("件数",f"検証31ケース（{len(TP)}）",len(TP)==31)
blob=" ".join(" ".join(x.values()) for x in AC+TP)
stale=[m for m in re.findall(r"[^ 　]{0,10}[56]権限[^ 　]{0,10}",blob)]
chk("件数","古い権限件数（5・6権限）が残っていない",not stale,str(stale))
chk("件数","09 が 08 の全権限を網羅",
    len({r["権限名"].split("（")[0] for r in D9 if not r["権限名"].startswith("（")})>=len({p.split("（")[0] for p in perm}))

print("\n■ 5. データセット内部")
EXP={"従業員":("17","0"),"店長":("36","8"),"本部管理":("36","25")}
base={x["権限名"]:x["ベース"] for x in D8}
m9={x["権限名"]:(x["店舗指標 ON"],x["会社指標 ON"]) for x in D9}
bad=[]
for k,b in base.items():
    tag="従業員" if "従業員" in b else ("店長" if "店長" in b else "本部管理")
    row=next((v for kk,v in m9.items() if kk.split("（")[0]==k.split("（")[0] and (("会社" in kk)==("会社" in k))),None)
    if row is None: row=next((v for kk,v in m9.items() if kk.startswith(k)),None)
    if row!=EXP[tag]: bad.append((k,tag,EXP[tag],row))
chk("データ","08のベース と 09の期待値が対応",not bad,str(bad))
for f,col in [("03_売上.tsv","売上"),("04_仕入.tsv","仕入"),("05_人件費.tsv","人件費")]:
    r=tsv(f"dataset/{f}"); k=[c for c in r[0] if col in c][0]
    v=sorted(int(str(x[k]).replace(",","")) for x in r)
    chk("データ",f"{f} が 1:2:4",len(v)==3 and v[1]==v[0]*2 and v[2]==v[0]*4,str(v))

print("\n■ 6. 検証プラン内部")
idx={x["検証ID"]:i for i,x in enumerate(TP)}
chk("検証","前提が自分より後ろを指さない",
    not [(x["検証ID"],t) for i,x in enumerate(TP) for t in ids(x["前提・入力値"]) if t in idx and idx[t]>i])
chk("検証","T-04（初回状態）が S-04 より前", idx.get("T-04",99)<idx.get("S-04",0))
SCR=["権限一覧","権限編集","ユーザー割当","割当編集","役割サマリ","権限テンプレート","指標一覧","指標条件設定","一括割当",
     "ダッシュボード","売上分析","仕入分析","詳細分析","集計","従業員管理","お支払い","会社情報","費用設定","予算設定"]
s_of=lambda t:{x for x in SCR if x in t}
mis=[(x["検証ID"],sorted((s_of(x["期待挙動"])|s_of(x["合否ライン"])|s_of(x["スクショに写すもの"]))-s_of(x["画面"]))) for x in TP
     if (s_of(x["期待挙動"])|s_of(x["合否ライン"])|s_of(x["スクショに写すもの"]))-s_of(x["画面"])]
chk("検証","画面名が列をまたいで一致",not mis,str(mis[:4]))
chk("検証","状態を変える検証に後始末がある",
    all(k in " ".join(TP[idx[t]].values()) for t,k in [("T-02","削除"),("T-18","S-05に戻す"),("T-23","元の値へ戻す"),("T-17","別の全権アカウント")]))

print("\n■ 7. 用語・表記")
chk("表記","実画面に無い「プレーン」を使っていない","プレーン" not in blob)
chk("表記","ヘルプの雛形名が実名（まっさら（なし））","まっさら（なし）" in HELP)
chk("表記","ヘルプに罫線文字が無い",not re.search(r"[─│┌┐└┘├┤┬┴┼━┃]",HELP))
chk("表記","ヘルプに『ロール』の説明語が無い（画面ラベルを除く）",
    HELP.count("ロール")<=3, f"{HELP.count('ロール')}箇所")

print("\n■ 8. ヘルプの安全性")
for t,k in [("操作制限を断定していない","変更操作を禁止する制御は、次回以降"),
            ("データ範囲を断定していない","担当外の店舗のデータを画面に出さない制御は、次回以降"),
            ("指標の反映を断定していない","分析画面の表示に反映されるのは次回以降")]:
    chk("ヘルプ",t,k in HELP)
secs=[l[3:].strip() for l in HELP.split("\n") if l.startswith("## ")]
i=HELP.index("**目次**"); j=HELP.index("## 権限設定でできること"); toc=HELP[i:j]
named=[re.split("　",m.group(1))[0] for m in re.finditer(r"^\d+\. (.+)$",toc,re.M)]
named+=[x.strip() for x in toc.split("**共通項目**　")[1].split("\n")[0].split("／")]+["ケース別のやり方","よくあるご質問","用語の説明"]
chk("ヘルプ","目次から全章に到達できる",not [s for s in secs if s not in named and s!="参照リンク"],
    str([s for s in secs if s not in named and s!="参照リンク"]))

print("\n■ 9. 生成物と元データ")
if openpyxl:
    for f,sheet,src in [("20260804_権限設定_01_受入条件表.xlsx","受入条件表",AC),
                        ("20260804_権限設定_02_検証プラン.xlsx","検証プラン",TP)]:
        wb=openpyxl.load_workbook(f); ws=wb[sheet]
        h=[r for r in range(1,30) if ws.cell(r,1).value==list(src[0].keys())[0]][-1]
        hdr=[c.value for c in ws[h]]
        chk("生成",f"{os.path.basename(f)} が TSV と一致",hdr==list(src[0].keys()) and ws.max_row-h==len(src),
            f"列{len(hdr)}/{len(src[0])} 行{ws.max_row-h}/{len(src)}")
        spec=[r[1] for r in wb["列仕様"].iter_rows(min_row=5,values_only=True) if r[0] and str(r[0]).isdigit()]
        chk("生成",f"{os.path.basename(f)} の列仕様が実データと一致",spec==list(src[0].keys()),
            str(set(spec)^set(src[0].keys())))

print("\n■ 10. 連番・重複・区分の自動検査")
# ID の重複
chk("連番","条件IDに重複が無い",len(acid)==len(AC),str([k for k,v in collections.Counter(x["条件ID"] for x in AC).items() if v>1]))
chk("連番","検証IDに重複が無い",len(tid)==len(TP),str([k for k,v in collections.Counter(x["検証ID"] for x in TP).items() if v>1]))
# ヘルプの画像番号が掲載順に連番
NUM="①②③④⑤⑥⑦⑧⑨⑩"
imgs=re.findall(r"【画像([①-⑩])：",HELP)
chk("連番","ヘルプの画像番号が掲載順に連番",imgs==list(NUM[:len(imgs)]),f"実際={''.join(imgs)}")
figs=re.findall(r"【図(\d)：",HELP)
chk("連番","図のファイルが実在",all(os.path.exists(f"help/figures/0{n}_"+d+".svg") for n,d in
    [("1","ご利用の流れ"),("2","権限と担当店舗"),("3","会社と店舗の区分")]))
# 列仕様の通し番号が 1..N
if openpyxl:
    for f in ["20260804_権限設定_01_受入条件表.xlsx","20260804_権限設定_02_検証プラン.xlsx"]:
        w=openpyxl.load_workbook(f)["列仕様"]
        ns=[int(r[0]) for r in w.iter_rows(min_row=5,values_only=True) if r[0] and str(r[0]).isdigit()]
        chk("連番",f"{os.path.basename(f)[-12:]} の列番号が連番",ns==list(range(1,len(ns)+1)),str(ns))
# 08 の各権限の許可画面が、その区分で扱える画面か（AC-22 型の取り違えを検出）
ctx=collections.defaultdict(set)
for x in D8: ctx[x["ctx"]].add(x["画面（カテゴリ）"])
bad=[]
for x in D8:
    if x["設定値"] in ("なし",""): continue
    c=x["ctx"]; k=x["区分"]
    if (c=="company" and k!="会社") or (c=="shop" and k!="店舗"):
        bad.append((x["権限名"],x["画面（カテゴリ）"],k,c))
chk("区分","権限の許可画面が区分の範囲内（AC-22型）",not bad,str(bad[:5]))
# 検証プラン・受入条件表の括弧内に書いたヘルプ引用が本文に実在するか
HELP_FLAT=HELP.replace("**","")
def quoted(rows,k):
    o=[]
    for x in rows:
        v=x.get("ヘルプページの該当箇所","")
        if v.startswith("—"): continue   # 該当なしの説明書きは対象外
        for m in re.findall(r"（([^）]+)）",v):
            for piece in re.split(r"\s*[＋／]\s*",m):
                piece=piece.strip()
                if not piece or piece.startswith("—") or "図" in piece or "顧客向け" in piece or "設計" in piece: continue
                if "ケース" in piece and "すべて" in piece: continue
                if piece.replace("**","") not in HELP_FLAT: o.append((x[k],piece))
    return o
q1=quoted(AC,"条件ID"); q2=quoted(TP,"検証ID")
chk("参照","受入条件表のヘルプ引用が本文に実在",not q1,str(q1[:4]))
chk("参照","検証プランのヘルプ引用が本文に実在",not q2,str(q2[:4]))

print("\n■ 11. デスクトップ同期")
if os.path.isdir(DESK):
    pairs=[(f,f) for f in ["20260803_06_権限設定_受入条件表_PdM引継.tsv","20260803_07_権限設定_検証プラン_PdM引継.tsv",
        "20260803_10_権限設定_検証用データセット.md","20260804_権限設定_01_受入条件表.xlsx",
        "20260804_権限設定_02_検証プラン.xlsx","20260806_権限設定_03_検証用データセット.xlsx",
        "20260804_権限設定_ヘルプページ.html"]]
    pairs+=[("help/draft-framer.md","ヘルプページ/20260806_権限設定_ヘルプページ_Framer用.md"),
            ("help/draft-notion.md","ヘルプページ/20260806_権限設定_ヘルプページ_Notion用.md"),
            ("help/README.md","ヘルプページ/20260806_権限設定_ヘルプページ_掲載情報.md")]
    pairs+=[(f"dataset/{f}",f"検証用データセット/{f}") for f in sorted(os.listdir("dataset")) if f.endswith(".tsv")]
    diff=[d for s,d in pairs if not os.path.exists(f"{DESK}/{d}") or subprocess.run(["diff","-q",s,f"{DESK}/{d}"],capture_output=True).returncode]
    chk("同期",f"デスクトップと一致（{len(pairs)}件）",not diff,str(diff[:5]))
else:
    warn("デスクトップフォルダが見つからない",False,DESK)

print("\n"+"="*60)
if NG:
    print(f"  ★ 要修正 {len(NG)}件")
    for n in NG: print(f"    - {n}")
else:
    print("  すべてOK")
if WARN: print(f"  ▲ 注意 {len(WARN)}件: {WARN}")
sys.exit(1 if NG else 0)
