# -*- coding: utf-8 -*-
"""受入条件表・検証プランの TSV から xlsx を再生成する。
TSV が唯一の元データ。書式（集計ブロック・条件付き書式・入力規則）はここで付ける。
"""
import csv,sys,os
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIN=Side(style="thin",color="D6DEE5")
BOX=Border(THIN,THIN,THIN,THIN)
HDR=PatternFill("solid",fgColor="1F7A8C")

def style(ws,hrow,ncol,widths,rowh=64):
    for c in ws[hrow]:
        c.font=Font(bold=True,size=10,color="FFFFFF"); c.fill=HDR
        c.alignment=Alignment(wrap_text=True,vertical="center",horizontal="center")
    for row in ws.iter_rows(min_row=hrow):
        for c in row:
            c.border=BOX
            if c.row>hrow: c.alignment=Alignment(wrap_text=True,vertical="top")
    for i,w in enumerate(widths,1): ws.column_dimensions[get_column_letter(i)].width=w
    for r in range(hrow+1,ws.max_row+1): ws.row_dimensions[r].height=rowh
    ws.row_dimensions[hrow].height=34

def build_ac():
    rows=list(csv.DictReader(open(f"{ROOT}/20260803_06_権限設定_受入条件表_PdM引継.tsv",encoding="utf-8"),delimiter="\t"))
    hdr=list(rows[0].keys()); wb=Workbook(); ws=wb.active; ws.title="受入条件表"
    ws["A1"]="権限設定 受入条件表 ─ どこまで実装できれば合格か"
    ws["A2"]="「合否」に OK / NG を入れると下の到達状況が自動で集計されます。判定は上のマイルストーン順に進めてください。"
    ws["A1"].font=Font(bold=True,size=13,color="1F4E5F"); ws["A2"].font=Font(size=10,color="5B6B7C")
    ws.append([])
    ms=[]
    for r in rows:
        if r["マイルストーン"] not in [m[0] for m in ms]: ms.append((r["マイルストーン"],r["マイルストーンの完了条件"]))
    ws.append(["マイルストーン","完了条件","","","条件数","OK","NG","未判定","到達率"])
    hrow_sum=ws.max_row
    first=hrow_sum+len(ms)+4   # データ開始行（集計ヘッダ＋マイルストーン行＋空行2＋見出し行の次）
    for m,cond in ms:
        r=ws.max_row+1
        ws.append([m,cond,"","",
                   f'=COUNTIF($A${first}:$A${first+len(rows)-1},A{r})',
                   f'=COUNTIFS($A${first}:$A${first+len(rows)-1},A{r},$N${first}:$N${first+len(rows)-1},"OK")',
                   f'=COUNTIFS($A${first}:$A${first+len(rows)-1},A{r},$N${first}:$N${first+len(rows)-1},"NG")',
                   f"=E{r}-F{r}-G{r}", f'=IF(E{r}=0,"",F{r}/E{r})'])
    for c in ws[hrow_sum]: c.font=Font(bold=True,size=10,color="FFFFFF"); c.fill=HDR
    for r in range(hrow_sum,ws.max_row+1):
        for c in ws[r]: c.border=BOX; c.alignment=Alignment(wrap_text=True,vertical="center")
        ws.cell(row=r,column=9).number_format="0%"
    ws.append([]); ws.append([])
    ws.append(hdr); hrow=ws.max_row
    for r in rows: ws.append([r[k] for k in hdr])
    ni=hdr.index("合否")+1
    dv=DataValidation(type="list",formula1='"OK,NG,対象外"',allow_blank=True)
    ws.add_data_validation(dv); dv.add(f"{get_column_letter(ni)}{hrow+1}:{get_column_letter(ni)}{ws.max_row}")
    rng=f"{get_column_letter(ni)}{hrow+1}:{get_column_letter(ni)}{ws.max_row}"
    ws.conditional_formatting.add(rng,CellIsRule(operator="equal",formula=['"OK"'],fill=PatternFill("solid",fgColor="D8F0E0")))
    ws.conditional_formatting.add(rng,CellIsRule(operator="equal",formula=['"NG"'],fill=PatternFill("solid",fgColor="FBDCDC")))
    W=[16,30,16,9,10,34,40,36,22,22,16,26,24,9,16,12,12]
    style(ws,hrow,len(hdr),W,rowh=76)
    ws.freeze_panes=f"D{hrow+1}"
    p=f"{ROOT}/20260804_権限設定_01_受入条件表.xlsx"; wb.save(p); return p,len(rows)

def build_tp():
    rows=list(csv.DictReader(open(f"{ROOT}/20260803_07_権限設定_検証プラン_PdM引継.tsv",encoding="utf-8"),delimiter="\t"))
    hdr=list(rows[0].keys()); wb=Workbook(); ws=wb.active; ws.title="検証プラン"
    ws["A1"]="確かめる手順。上から順に実施する。S-01〜S-06 は準備、T-01〜 が検証。\n「画面」を開いて「操作」を行い、「期待挙動」と「起きてはいけないこと」を見て、「合否ライン」に照らして「判定」に OK / NG を入れる。\n右端の「受入条件ID／遷移フローID／ヘルプページの該当箇所」は、NG のときにどこへ跳ね返るかを示す。"
    ws["A1"].font=Font(bold=True,size=11,color="1F4E5F")
    ws.append(hdr); hrow=ws.max_row
    for r in rows: ws.append([r[k] for k in hdr])
    ji=hdr.index("判定")+1
    dv=DataValidation(type="list",formula1='"OK,NG,検証不能"',allow_blank=True)
    ws.add_data_validation(dv); dv.add(f"{get_column_letter(ji)}{hrow+1}:{get_column_letter(ji)}{ws.max_row}")
    rng=f"{get_column_letter(ji)}{hrow+1}:{get_column_letter(ji)}{ws.max_row}"
    ws.conditional_formatting.add(rng,CellIsRule(operator="equal",formula=['"OK"'],fill=PatternFill("solid",fgColor="D8F0E0")))
    ws.conditional_formatting.add(rng,CellIsRule(operator="equal",formula=['"NG"'],fill=PatternFill("solid",fgColor="FBDCDC")))
    style(ws,hrow,len(hdr),[8,9,22,26,24,38,36,34,40,36,34,10,16,12,32,16,9],rowh=120)
    ws.freeze_panes=f"C{hrow+1}"
    p=f"{ROOT}/20260804_権限設定_02_検証プラン.xlsx"; wb.save(p); return p,len(rows)

if __name__=="__main__":
    for p,n in (build_ac(),build_tp()): print(f"  {os.path.basename(p)}  {n}件")
