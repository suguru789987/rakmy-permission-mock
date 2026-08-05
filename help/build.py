# -*- coding: utf-8 -*-
"""help/draft-framer.md を各形式に変換する。
マーカー形式：
  【図N：説明】← ここに 図/xx.png …
  【画像①：説明】← ここにスクリーンショットを挿入 …
"""
import re,os,base64,markdown
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG={"1":"01_ご利用の流れ","2":"02_権限と担当店舗","3":"03_会社と店舗の区分"}
SRC=os.path.join(ROOT,"help/draft-framer.md")
RE_FIG=r"^【図(\d)：(.+?)】.*$"; RE_IMG=r"^【画像([①-⑩])：(.+?)】.*$"
md=open(SRC,encoding="utf-8").read()

# ── Notion版
out=[]
for l in md.split("\n"):
    m=re.match(RE_FIG,l)
    if m:
        out+=["---","",f'🖼 **【図{m.group(1)}：{m.group(2)}】**',
              f'図/{FIG[m.group(1)]}.png（または .svg）をアップロードし、**この案内文ごと差し替えてください。**図は作成済みです。','','---']; continue
    m=re.match(RE_IMG,l)
    if m:
        out+=["---","",f'📷 **【画像{m.group(1)}：{m.group(2)}】**',
              f'この画面のスクリーンショットを撮影し、**この案内文ごと差し替えてください。**未取得です（撮影リストの {m.group(1)} 番）。','','---']; continue
    out.append(l)
open(os.path.join(ROOT,"help/draft-notion.md"),"w",encoding="utf-8").write("\n".join(out))

# ── HTML（図はSVGを埋め込み、画像は未取得の枠）
HTMLP=os.path.join(ROOT,"20260804_権限設定_ヘルプページ.html")
CSS=re.search(r"<style>([\s\S]*?)</style>",open(HTMLP,encoding="utf-8").read()).group(1)
h=re.sub(RE_FIG,lambda m:(
  f'<figure class="fig"><img src="data:image/svg+xml;base64,'
  f'{base64.b64encode(open(os.path.join(ROOT,"help/figures",FIG[m.group(1)]+".svg"),encoding="utf-8").read().encode()).decode()}"'
  f' alt="{m.group(2)}"><figcaption>図{m.group(1)}　{m.group(2)}'
  f'　<span class="fno">figures/{FIG[m.group(1)]}.svg</span></figcaption></figure>'),md,flags=re.M)
h=re.sub(RE_IMG,r'<div class="imgph">📷 【画像\1】\2<span class="todo">スクリーンショット未取得 — 撮影リスト \1</span></div>',h,flags=re.M)
h=h.replace("---\n\nサポートが必要ですか？\n[サポートチームに連絡](https://docs.google.com/forms/d/e/1FAIpQLSe1qwnma82vLEpQQNdzjl_gLSt_qHMHZp6eqmhaziUB11IAOA/viewform)",
 '<div class="support"><b>サポートが必要ですか？</b><a href="https://docs.google.com/forms/d/e/1FAIpQLSe1qwnma82vLEpQQNdzjl_gLSt_qHMHZp6eqmhaziUB11IAOA/viewform">サポートチームに連絡</a></div>')
body=markdown.markdown(h,extensions=["tables","fenced_code","toc","sane_lists","md_in_html"])
heads={re.sub("<[^>]+>","",t):i for i,t in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>',body)}
def link_names(x):
    for name,anc in sorted(heads.items(),key=lambda y:-len(y[0])):
        x=re.sub(rf"(?<![>\w]){re.escape(name)}(?![^<]*</h2>)",f'<a href="#{anc}">{name}</a>',x,count=1)
    return x
i=body.index('<p><strong>目次</strong></p>'); j=body.index('<h2 id=')
body=body[:i]+link_names(body[i:j])+body[j:]
toc="".join(f'<li><a href="#{a}">{t}</a></li>' for t,a in heads.items())
open(HTMLP,"w",encoding="utf-8").write(
f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>権限設定 ｜ ラクミー サービスマニュアル（原稿）</title><style>{CSS}</style></head><body>
<header class="top"><h1>ラクミー サービスマニュアル（掲載原稿）</h1>
<div class="meta">経営管理 ／ 権限設定 ｜ オーナー・本部管理者向け ｜ 2026-08-05 更新 ｜ 図3点は作成済み・スクリーンショット10枚は未取得（撮影リストあり） ｜ 掲載先 help.rakmy.jp/management/権限設定</div></header>
<div class="wrap"><main><div class="toc"><b>ページの構成</b><ol>{toc}</ol></div>{body}</main></div></body></html>""")
print("Notion版・HTML を生成")
