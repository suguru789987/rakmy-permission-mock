# -*- coding: utf-8 -*-
"""ヘルプページの図を SVG で生成する。
ASCII図は Notion・Framer で崩れるため使わない。
PNG化: Chrome のヘッドレスで
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
    --force-device-scale-factor=2 --window-size=W,H --screenshot=out.png file://.../in.svg
"""
import os
FONT='"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif'
INK,SUB,LINE,ACC,BG='#1f2d3d','#5b6b7c','#c9d6e0','#1f7a8c','#f4f9fb'
OUT=os.path.join(os.path.dirname(__file__),"figures")

def head(w,h,t):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{t}"><title>{t}</title><rect width="{w}" height="{h}" fill="#fff"/>'
            f'<style>text{{font-family:{FONT}}}</style>')
def txt(x,y,t,size=14,fill=INK,w="400",anchor="middle"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{fill}" font-weight="{w}">{t}</text>'
def rect(x,y,w,h,fill=BG,stroke=LINE):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
def arrow(x1,y,x2,color=ACC):
    return (f'<line x1="{x1}" y1="{y}" x2="{x2-9}" y2="{y}" stroke="{color}" stroke-width="2"/>'
            f'<path d="M{x2} {y} L{x2-10} {y-5.5} L{x2-10} {y+5.5} Z" fill="{color}"/>')

def fig1():
    W,H=1000,266
    s=head(W,H,"権限設定のご利用の流れ")
    s+=txt(W/2,34,"はじめて設定する場合は、この順番がおすすめです",15,SUB)
    STEP=[("導入時の初期設定","よく使う権限を\nまとめて登録"),("権限を作成する","足りない権限を\n貴社に合わせて追加"),
          ("権限をメンバーに\n割り当てる","誰にどの権限を\n付けるか決める"),("担当店舗を設定する","店舗の権限を付けた方に\n担当店舗を紐付け"),
          ("設定内容を確認する","誰が何の権限を\n持っているか確認")]
    bw,gap,y0,bh=176,30,70,128; x=(W-(bw*5+gap*4))/2
    for i,(t,sub) in enumerate(STEP):
        cx=x+i*(bw+gap)
        s+=rect(cx,y0,bw,bh)
        s+=f'<circle cx="{cx+22}" cy="{y0+22}" r="13" fill="{ACC}"/>'+txt(cx+22,y0+27,i+1,13,"#fff","700")
        for k,ln in enumerate(t.split("\n")): s+=txt(cx+bw/2,y0+56+k*19,ln,15.5,INK,"600")
        for k,ln in enumerate(sub.split("\n")): s+=txt(cx+bw/2,y0+98+k*17,ln,12.5,SUB)
        if i<4: s+=arrow(cx+bw+5,y0+bh/2,cx+bw+gap-5)
    s+=f'<rect x="{x}" y="216" width="{bw*4+gap*3}" height="30" rx="6" fill="#eef6f8" stroke="{ACC}" stroke-width="1" stroke-dasharray="4 3"/>'
    s+=txt(x+(bw*4+gap*3)/2,236,"ここまでで初期設定は完了です",13,ACC,"600")
    return "01_ご利用の流れ",W,H,s+"</svg>"

def fig2():
    W,H=1000,340
    s=head(W,H,"権限と担当店舗の関係")
    s+=txt(W/2,32,"権限は共通のものを使い、どの店舗を見せるかは人ごとに設定します",15,SUB)
    s+=rect(60,130,230,92,"#eef6f8",ACC)+txt(175,170,"権限「店長」",18,INK,"600")+txt(175,194,"1つ作れば全員で共有",13,SUB)
    s+=txt(175,246,"権限設定で作る",12.5,SUB)
    for nm,st,yy in [("渋谷店の店長 Aさん","担当店舗：渋谷店",92),("新宿店の店長 Bさん","担当店舗：新宿店",170),("池袋店の店長 Cさん","担当店舗：池袋店",248)]:
        s+=f'<path d="M290 176 C 400 176, 430 {yy+33}, 555 {yy+33}" fill="none" stroke="{ACC}" stroke-width="2"/>'
        s+=f'<path d="M566 {yy+33} L555 {yy+27} L555 {yy+39} Z" fill="{ACC}"/>'
        s+=rect(575,yy,365,66,"#fff",LINE)+txt(757,yy+29,nm,17,INK,"600")+txt(757,yy+51,st,13,SUB)
    s+=txt(757,330,"ユーザー割当で人ごとに設定する　※複数の店舗や「全店」も選べます",12.5,SUB)
    return "02_権限と担当店舗",W,H,s+"</svg>"

def fig3():
    W,H=1000,330
    s=head(W,H,"会社と店舗の区分")
    s+=txt(W/2,32,"権限は会社か店舗のどちらかに属します。1つの権限で両方は扱えません",15,SUB)
    s+=f'<line x1="500" y1="52" x2="500" y2="300" stroke="{LINE}" stroke-width="1.5" stroke-dasharray="5 4"/>'
    for x,kb,t2,sub2,cnt,fs in [(60,"会社","会社の画面（4種類）","会社情報・お支払い・店舗（管理）・ダウンロード",21,12.5),
                                (540,"店舗","店舗の画面（6種類）","発注先&amp;仕入商品・店舗情報・連携設定・費用設定・休業日設定・予算設定",23,11)]:
        cx=x+200
        s+=rect(x,62,400,74,"#f7f7f9",LINE)+txt(cx,92,"共通の画面（17種類）",16,INK,"600")+txt(cx,116,"ダッシュボード・売上分析・従業員管理 など",12.5,SUB)
        s+=txt(cx,166,"＋",18,ACC,"700")
        s+=rect(x,186,400,76,"#eef6f8",ACC)+txt(cx,216,t2,16,INK,"600")+txt(cx,240,sub2,fs,SUB)
        s+=txt(cx,296,f"区分「{kb}」＝ {cnt}画面",16,INK,"700")
    return "03_会社と店舗の区分",W,H,s+"</svg>"

if __name__=="__main__":
    os.makedirs(OUT,exist_ok=True)
    for f in (fig1,fig2,fig3):
        name,w,h,svg=f()
        open(os.path.join(OUT,name+".svg"),"w",encoding="utf-8").write(svg)
        print(f"{name}.svg  {w}x{h}")
