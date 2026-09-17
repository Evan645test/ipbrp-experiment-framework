#!/usr/bin/env python3
"""Materialise the source-checked reading repairs and exhibit interpretation plan."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import fitz
from build_references import atomic_json
from extract_phase_a import normalize_text
from prepare_remaining_papers import ROOT, PLAN

MERGES = {
 2:[[21,22],[28,29],[31,34],[35,37],[42,44],[86,95],[106,118,119,143],[149,151],[154,158],[176,177],[181,182]],
 3:[[4,5,6,7],[25,27]],
 4:[[7,8],[24,26],[41,42,43,44,45],[87,97]],
 5:[[1,2],[8,9],[27,29],[33,36],[40,43],[56,63,65],[88,95],[111,114],[113,119],[122,123]],
 6:[[14,15],[20,22],[74,82],[103,106]],
 7:[[1,2,17],[18,19],[25,26],[34,36],[38,40],[50,52],[54,63],[64,65],[70,71],[73,75],[95,100],[103,130],[133,134],[137,142],[145,157],[160,168],[171,172],[179,180]],
 8:[[1,2,17],[28,29],[42,43],[45,46],[60,82],[152,153],[159,160],[166,167],[172,173]],
}
ROLES = {
 2:{185:'Author Contributions',187:'Acknowledgements and funding',189:'Conflicts of Interest',191:'Data Availability Statement'},
 3:{76:'Code Availability',78:'Authors’ contributions',79:'Funding',80:'Data availability',81:'Ethics approval',82:'Consent for publication',83:'Consent to participate',84:'Conflicts of interest',85:'Open Access licence'},
 4:{111:'Acknowledgements',117:'ORCID',119:'Disclosure statement',120:'Funding',121:'Notes on contributors',122:'Notes on contributors',123:'Notes on contributors',124:'Notes on contributors',125:'Notes on contributors',126:'Ethics approval',127:'Informed consent',128:'Data availability'},
 5:{116:'Funding',121:'Ethics approval',122:'CRediT authorship contribution statement',124:'Acknowledgements',127:'Declaration of competing interest'},
 6:{130:'Disclosure statement',134:'ORCID'},
 7:{179:'Author Contributions',182:'Acknowledgements and funding',184:'Ethics Statement',186:'Consent',188:'Conflicts of Interest',190:'Data Availability Statement'},
 8:{3:'Open Access licence',185:'Author Contributions',187:'Acknowledgements and funding',189:'Conflicts of Interest',191:'Data Availability Statement',193:'Peer review transparency'},
}
TITLES = {
 2:{'table':['學習行為的操作定義與代碼','英語學習成就的共變數分析','科學學習成就的共變數分析','學習動機的共變數分析','心流體驗的兩組比較','學習焦慮的共變數分析','CM-CLDG 組的行為轉移殘差','C-CLDG 組的行為轉移殘差','兩組訪談學習經驗的對照'], 'figure':['概念圖融入數位遊戲的系統架構','遊戲任務的設計流程','完成任務的遊戲情境','蒐集動物棲地資訊的遊戲情境','任務內嵌的概念圖範本','完成遊戲前整合的概念圖','兩組介入與測量的實驗流程','CM-CLDG 組的學習行為序列','C-CLDG 組的學習行為序列','回答任務與持續投入的轉移','回答與結果回饋的轉移','場景資訊與回答任務的轉移','複習知識與回答任務的轉移']},
 3:{'table':['體育學習行為的代碼字典','瑜伽動作技能表現的共變數分析','學習投入的獨立樣本 t 檢定','實驗組的行為轉移調整殘差','控制組的行為轉移調整殘差'], 'figure':['AI 動作評估與遊戲化回饋的系統架構','遊戲化個人介面','動作監測與回饋介面','個人學習紀錄介面','排行榜與動作完成程度介面','兩組教學介入與測量流程','學生使用系統的活動示例','實驗組與控制組的行為轉移模式']},
 4:{'table':['完成三次測量者的背景特徵','學習投入與合作創造力的時間效果','時間與學生背景的交互作用'], 'figure':['健康促進課程的三階段與遊戲設計活動','教學階段與 T1、T2、T3 資料蒐集時點']},
 5:{'table':['各問卷前、後測的內部一致性','三組學習成就的共變數分析','不同題型學習成就的共變數分析','應用與分析題的內容分析','三組集體效能的共變數分析','三組批判思考傾向的共變數分析','三組問題解決技能的共變數分析','三組訪談的主題、代碼與出現次數'], 'figure':['CM-GAI-CL 的五階段學習流程','小組使用概念圖組織知識','小組合作查核與修訂概念圖','小組合作完成文章','三組介入、前後測與訪談流程']},
 6:{'table':['主動與被動行為的編碼定義','同儕評量規準','四組 CT 與 AI 概念學習成就','四組運算思維自我效能','四組學習焦慮與投入','控制組的行為轉移 Z 值','實驗組 EG3 的行為轉移 Z 值','實驗組 EG1 的行為轉移 Z 值'], 'figure':['AIoT 桌遊的實體配置','AIoT 遊戲式學習系統','AIoT 桌遊的活動流程','四組教學介入與測量流程','AIoT 桌遊的操作示例','進階學習任務','控制組的行為轉移模式','EG3 的行為轉移模式','EG1 的行為轉移模式']},
 7:{'table':['卡丁車結構任務的 LLM 回饋機制','遊戲行為的代碼與操作定義','學習成就的共變數分析','後設認知覺察的共變數分析','實驗組的行為轉移殘差','控制組的行為轉移殘差','互動次數、成功率與失敗率的描述統計','依互動次數中位數分組的成功率比較','互動、成功率與前後測的相關矩陣'], 'figure':['LLM-ARG 系統架構','ARG 的任務與學習路徑','STEM 四面向的學習內容','學生與虛擬代理人 V 的互動介面','LLM-ARG 的技術與資料傳輸流程','兩組介入與前後測流程','LLM-ARG 實驗組的行為轉移圖','C-ARG 控制組的行為轉移圖','與代理人互動次數的分布']},
 8:{'table':['虛擬博物館學習的八種行為代碼','學習成就的獨立樣本 t 檢定','批判思考傾向的獨立樣本 t 檢定','合作傾向的獨立樣本 t 檢定','後設認知的獨立樣本 t 檢定','SE-VML 實驗組的行為轉移殘差','C-VML 控制組的行為轉移殘差','兩組訪談主題與出現頻率'], 'figure':['自我解釋引導的 4C 虛擬博物館學習模式','虛擬博物館的情境學習','場景內的結構化引導問題','以文字表達理解的自我解釋任務','小組合作繪製概念圖','SE-VML 系統架構','隨機分組與介入、測量流程','SE-VML 實驗組的行為轉移圖','C-VML 控制組的行為轉移圖','實驗組訪談的主題與關聯','控制組訪談的主題與關聯']},
}
ANCOVA={(2,j) for j in (2,3,4,6)}|{(3,2)}|{(5,j) for j in (2,3,5,6,7)}|{(6,3)}|{(7,j) for j in (3,4)}
RESIDUAL={(2,j) for j in(7,8)}|{(3,j) for j in(4,5)}|{(6,j) for j in(6,7,8)}|{(7,j) for j in(5,6)}|{(8,j) for j in(6,7)}
BEHAVIOUR={(2,j) for j in range(8,14)}|{(3,8)}|{(6,j) for j in(7,8,9)}|{(7,j) for j in(7,8)}|{(8,j) for j in(8,9)}
PROCEDURE={(2,7),(3,6),(4,2),(5,5),(6,4),(7,6),(8,7)}

def hash_text(text): return hashlib.sha256(text.encode()).hexdigest()

def fragments(pdf,page,box):
    return [{'page':page,'bbox':list(box),'pageSize':[pdf[page-1].rect.width,pdf[page-1].rect.height]}]

def main():
    plan=json.loads(PLAN.read_text())
    for n in range(2,9):
        pid=f'paper-{n:02d}'; item=plan['papers'][pid]; paper=json.loads((ROOT/f'public/data/{pid}.json').read_text()); ss=paper['segments']
        if hashlib.sha256((ROOT/f'public/data/{pid}.json').read_bytes()).hexdigest()!=item['beforeDataSha256']:
            raise ValueError('Annotate the untouched source only: '+pid)
        item.update(merges=[],replacements=[],additions=[],roles={},explanations={},semanticLinks=[],appendices=[],exclusions={})
        for indices in MERGES[n]:
            item['merges'].append({'targetId':ss[indices[0]]['id'],'absorbedIds':[ss[i]['id'] for i in indices[1:]],'expectedSources':{ss[i]['id']:ss[i]['sourceText'] for i in indices}})
        for index,section in ROLES[n].items(): item['roles'][ss[index]['id']]={'role':'statement','section':section}
        if n==3:
            for i in range(86,90): item['exclusions'][ss[i]['id']]='Reference list, preserved in the existing reference index.'
        # Original front-matter headings and addresses are not standalone arguments.
        for s in ss:
            if s['sourceText'].strip() in {'Summary','Declarations','Author Contributions','Acknowledgements','Funding','Ethics approval','CRediT authorship contribution statement','Declaration of competing interest','Disclosure statement','Author contributions','ORCID','Ethics Statement','Consent','Conflicts of Interest','Data Availability Statement'} or s['sourceText'].startswith('1College of Education, Zhejiang'):
                item['exclusions'][s['id']]='Front matter or statement heading; its associated text remains available.'
        with fitz.open(ROOT/f'public/papers/{pid}.pdf') as pdf:
            def add_native(page,box,section,role=None):
                source=normalize_text(pdf[page-1].get_textbox(fitz.Rect(box)))
                if len(source)<25: raise ValueError('Empty inspected native region '+pid+str(box))
                item['additions'].append({'id':pid+'-s-recovered-'+hash_text(source)[:12],'sourceText':source,'fragments':fragments(pdf,page,box),'section':section,'kind':'body',**({'readingRole':role} if role else {})})
            def replace_native(index,page,box):
                source=normalize_text(pdf[page-1].get_textbox(fitz.Rect(box)))
                item['replacements'].append({'segmentId':ss[index]['id'],'expectedSource':ss[index]['sourceText'],'sourceText':source,'fragments':fragments(pdf,page,box)})
            if n==2:
                replace_native(7,2,[312,510,553,588])
                # Questions 2–5 were omitted from the original extraction.
                for box in ([312,587,553,626],[312,627,553,666],[312,667,553,706],[312,707,553,736]): add_native(2,box,'1 | Introduction')
                add_native(3,[52,464,294,507],'1 | Introduction')
                r=next(r for r in item['merges'] if r['targetId']==ss[106]['id'])
                body=normalize_text(pdf[10].get_textbox(fitz.Rect([43,28,294,89])))
                r['sourceText']=' '.join(ss[i]['sourceText'] for i in [106,118,119])+' '+body
                r['fragments']=[f for i in [106,118,119] for f in ss[i]['fragments']]+fragments(pdf,11,[43,28,294,89])
            if n==3:
                add_native(2,[49,78,392,430],'Introduction')
                block=next(b for b in pdf[1].get_text('blocks') if b[4].startswith('In physical education (PE)'))
                item['additions'][-1]['sourceText']=normalize_text(block[4])
                item['additions'][-1]['id']=pid+'-s-recovered-'+hash_text(item['additions'][-1]['sourceText'])[:12]
                block=next(b for b in pdf[13].get_text('blocks') if b[4].startswith('Z-score greater'))
                item['replacements'].append({'segmentId':ss[44]['id'],'expectedSource':ss[44]['sourceText'],'sourceText':ss[44]['sourceText']+' '+normalize_text(block[4]),'fragments':ss[44]['fragments']+fragments(pdf,14,list(block[:4]))})
            if n==4:
                extra=normalize_text(pdf[2].get_textbox(fitz.Rect([58,50,438,117])))
                item['replacements'].append({'segmentId':ss[1]['id'],'expectedSource':ss[1]['sourceText'],'sourceText':ss[1]['sourceText']+' '+extra,'fragments':ss[1]['fragments']+fragments(pdf,3,[58,50,438,117])})
                add_native(16,[58,220,438,258],'Generative AI statement','statement')
            if n==5:
                for index,page,prefix in [(43,9,'underlying construct.'),(65,11,'that the experimental group')]:
                    block=next(b for b in pdf[page-1].get_text('blocks') if b[4].startswith(prefix))
                    item['replacements'].append({'segmentId':ss[index]['id'],'expectedSource':ss[index]['sourceText'],'sourceText':normalize_text(block[4]),'fragments':fragments(pdf,page,list(block[:4]))})
                # The original table spans to y=175; the body starts at y=190.
                item['exhibits'][pid+'-table-3']['bbox']=[37,48,510,179]
                add_native(17,[37,588,510,612],'Data availability','statement')
                item['roles'][ss[125]['id']]={'role':'appendix','section':'Appendix A'}
                item['appendices']=[{'captionSegmentId':ss[125]['id'],'page':17,'bbox':[37,172,510,540], 'number':'A','caption':'Appendix A. Coding scheme for content analysis','captionZh':'附錄 A．內容分析編碼規則','sourceText':normalize_text(pdf[16].get_textbox(fitz.Rect([37,172,510,540]))),'relatedSegmentIds':[s['id'] for s in ss if 'Appendix A' in s['sourceText'] and s['id']!=ss[125]['id']], 'guideZh':['先對照各類別與次類別的操作定義，再看表 4 的三組內容分析；本附錄提供判斷依據，沒有新增成效檢定。','編碼單位與分類依作者的方法段落；類別出現次數不等於個別學生的人數或能力分數。']}]
            if n==6:
                block=next(b for b in pdf[5].get_text('blocks') if b[4].startswith('platform were eligible'))
                item['replacements'].append({'segmentId':ss[22]['id'],'expectedSource':ss[22]['sourceText'],'sourceText':normalize_text(block[4]),'fragments':fragments(pdf,6,list(block[:4]))})
                add_native(18,[70,319,527,347],'Funding','statement')
                add_native(18,[70,385,527,427],'Author contributions','statement')
                for index,number in [(85,'7'),(103,'8'),(110,'9')]:
                    item['semanticLinks'].append({'segmentId':ss[index]['id'],'exhibitId':pid+'-figure-'+number,'relationshipZh':f'正文此處的圖號與實際圖說不一致；依作者描述的組別與完整圖說，本段對應 Figure {number}。保留正文原圖號，請並列核對。','suppressExplicitFigures':True})
            if n==7:
                for box in ([312,655,553,695],[312,696,553,725]): add_native(2,box,'1 | Introduction')
                # Two old extraction blocks combined table rows with paragraph continuations.
                for index,pattern in [(93,'within the experimental group'),(168,'metacognitive awareness whilst')]:
                    text=ss[index]['sourceText'];start=text.find(pattern)
                    if start<0: raise ValueError('Inspected continuation missing')
                    item['replacements'].append({'segmentId':ss[index]['id'],'expectedSource':text,'sourceText':text[start:],'fragments':[f for f in ss[index]['fragments'] if f['page']==(11 if index==93 else 15)]})
                # The continued data-analysis sentence belongs to its preceding paragraph.
                item['merges'].append({'targetId':ss[81]['id'],'absorbedIds':[ss[93]['id']],'expectedSources':{ss[81]['id']:ss[81]['sourceText'],ss[93]['id']:ss[93]['sourceText']}})
            if n==8:
                for index,box in [(22,[52,259,294,299]),(23,[52,300,294,328]),(24,[52,329,294,357]),(25,[52,358,294,386]),(26,[52,387,294,427])]: replace_native(index,3,box)
                ocr=json.loads((ROOT/'content/paper-08-recovered-text.json').read_text())
                if ocr['sourceSha256']!=paper['sourceSha256']: raise ValueError('OCR source changed')
                for region in ocr['regions']:
                    for j,text in enumerate(region['paragraphs']):
                        if text.startswith('6 | Discussion'): continue
                        text=text.replace('selfexplanation','self-explanation').replace('artefactspecific','artefact-specific').replace('¢=2.11','t=2.11').replace('¢.g., #1','e.g., 螽斯衍慶')
                        box=region['bbox'][:]
                        if text.startswith('In the context stage'):box=[304,443,553,499]
                        elif text.startswith('In the VR scenario'):box=[304,283,553,437]
                        if text=='a7':continue
                        is_heading=bool(re.fullmatch(r'[2-5]\.\s+[A-Z][A-Za-z ]+',text))
                        item['additions'].append({'id':pid+'-s-recovered-'+hash_text(text)[:12],'sourceText':text,'fragments':[{'page':region['page'],'bbox':box,'pageSize':region['pageSize']}],'section':'5 | Results' if region['page']>=9 else '3 | Learning model' if region['page']<7 else '4 | Method','kind':'heading' if is_heading else 'body',**({'excluded':True} if is_heading else {}),'sourceRecovery':{'method':ocr['engine'],'sourceSha256':ocr['sourceSha256'],'regionIndex':ocr['regions'].index(region),'paragraphIndex':j}})
                # Recoveries that continue an existing passage are joined in PDF order.
                def recovered(prefix):
                    found=[a for a in item['additions'] if a['sourceText'].startswith(prefix)]
                    if len(found)!=1: raise ValueError('Ambiguous OCR passage: '+prefix)
                    return found[0]
                def join_recovered(prefix,original,prepend=True):
                    a=recovered(prefix);s=ss[original]
                    item['replacements'].append({'segmentId':s['id'],'expectedSource':s['sourceText'],'sourceText':a['sourceText']+' '+s['sourceText'] if prepend else s['sourceText']+' '+a['sourceText'],'fragments':a['fragments']+s['fragments'] if prepend else s['fragments']+a['fragments'],'sourceRecovery':a['sourceRecovery']})
                    item['additions'].remove(a)
                join_recovered('In the context stage',40)
                join_recovered('Figure 7 shows',55)
                join_recovered('The behavioural conversion diagram',114)
                join_recovered('From Figures 8 and 9',124)
                # Author paragraph crosses the two columns.
                a=recovered('As shown in Table 5');b=recovered('with a medium effect size')
                a['sourceText']+=' '+b['sourceText'];a['fragments']+=b['fragments'];item['additions'].remove(b)
                a=recovered('Construction stage:');b=recovered('actively explored the background')
                a['sourceText']+=' '+b['sourceText'];a['fragments']+=b['fragments'];item['additions'].remove(b)
                a=recovered('Students mentioned several advantages');b=recovered('benefit:')
                if b: a['sourceText']+=' '+b['sourceText'];a['fragments']+=b['fragments'];item['additions'].remove(b)
        for eid,e in item['exhibits'].items():
            if n==3 and e['kind']=='table' and e['number']=='1':e['bbox'][1]=42
            if n==5 and e['kind']=='table' and e['number']=='8':e['bbox']=[37,48,510,210]
            number=int(e['number']); title=TITLES[n][e['kind']][number-1]; e['captionZh']=('圖' if e['kind']=='figure' else '表')+' '+e['number']+'．'+title
            guides=[];limits=['中文伴讀為 AI 草稿；精確內容與數值請以完整原圖表及作者正文為準。']
            if e['kind']=='table':
                if (n,number) in ANCOVA:
                    guides=['先確認各組 N、原始平均數 Mean 與標準差 SD，再看 Adjusted mean（調整後平均數）；不要把兩種平均數混用。','F 與 p 判斷模型的組別差異；η² 為效果量。三組以上若有事後比較，需逐組核對，整體顯著不代表每一對組別皆顯著。']
                    limits+=['需搭配方法段落核對共變數、回歸斜率同質性與分組方式；控制前測不會自動消除所有組間差異。']
                elif (n,number) in RESIDUAL:
                    guides=['由列（前一行為）讀到欄（下一行為）；格內為調整殘差／Z 值，星號的意義依原表註腳。','用本篇行為編碼表解讀縮寫，再對照對應的行為轉移圖；作者以 Z > 1.96 篩選顯著轉移。']
                    limits+=['Z 值不是行為次數、相關係數或效果量；序列先後不能單獨證明因果關係。']
                elif n==4 and number in(2,3):
                    guides=['T1、T2、T3 為同一批學生在不同階段的測量；Mean ± SD 是平均數與標準差。','表 2 的時間效果與表 3 的時間×背景交互作用回答不同問題；Bonferroni 欄用來核對實際顯著的時點或子群，n.s. 表示未達顯著。']
                    limits+=['本研究為單組重複測量，沒有同時期控制組；時間改變不能單獨歸因於共創遊戲教學。','合作創造力的整體提升不代表每個分量表均顯著：Distributed Creativity 的時間效果未達顯著。']
                elif n==8 and number in(2,3,4,5) or n==2 and number==5 or n==3 and number==3:
                    guides=['逐組對照樣本數 N、平均數 Mean 與標準差 SD，再讀 t 檢定及星號／p 值的註腳。','Cohen’s d 是標準化組間差異，與 t 值、p 值意義不同；統計顯著不等於具有同樣大小的實務效益。']
                    limits+=['未達顯著不等於已證明兩组相同；自陳傾向與實際能力表現也應分開解讀。']
                    if n==8:limits+=['本篇沒有介入前的基線測量；作者在研究限制中承認無法直接檢查兩組原先是否等同。']
                elif n==7 and number==9:
                    guides=['找出要比較的兩變項，在交叉格讀 Pearson r；正負號為關係方向，絕對值為線性關係強弱。','先区分 Q_count、Success_rate、Pretest、Posttest、Meta_pre、Meta_post，再依 **、*** 的註腳核對顯著水準。']
                    limits+=['此表僅分析實驗組；相關不證明代理人互動、後設認知或成績之間的因果方向。']
                elif n==7 and number==8:
                    guides=['依 Q_count 中位數分為高互動與低互動組；對照各組 N、互動平均、成功率及其標準差。','作者報告低互動組成功率較高；這是事後分組的比較，不是隨機指派不同互動量。']
                    limits+=['不能据此建议学生减少提问，也不能断言较多互动降低学习成效；原先能力与任务困难可能影响互动需求。']
                elif n==6 and number in(4,5):
                    guides=['此處使用 Kruskal–Wallis H 檢定；Mean Rank 是平均名次，不能當作原量尺的平均分數。','先看整體 H 檢定，再看作者列出的事後 U 檢定組對；焦慮與投入分量表需分別解讀。']
                    limits+=['高焦慮分數的方向依問卷計分定義解讀，不能把所有較高數值都說成較佳。']
                else:
                    guides=['先對照欄名與每列的操作定義，保留全部類別、資料列及表下注記。','次數、百分比、信度與評量規準回答不同問題；依本表標示的單位閱讀，不把編碼定義當作效果檢定。']
                    if (n,number) in {(2,9),(5,8),(8,8)}: limits+=['訪談中的提及次數不等於所有參與者的比例，也不是兩組差異的統計檢定。']
            elif (n,number) in BEHAVIOUR:
                guides=['先用本篇編碼表對照節點的行為意義，再沿箭頭方向讀取前後轉移。','箭頭與連線數字依圖例和作者說明解讀；比較兩組共有的序列與僅某組達顯著的序列。']
                limits+=['轉移網絡不直接顯示學習成績或因果效果；沒有箭頭不代表該行為從未發生。']
                if n==6:limits+=['本篇結果正文的圖號存在錯置；此處依完整圖說標示組別，保留作者正文原圖號供並列核對。']
            elif (n,number) in PROCEDURE:
                guides=['依箭頭與時間順序閱讀分組、教學介入、測量及訪談安排，再核對方法段落的實際時長。','分清哪些措施是各組共同條件，哪些是實驗組特有的介入；流程圖補充研究設計，不是成效結果。']
                limits+=['流程圖不能单独说明随机化、执行忠实度或混淆控制；这些细节需核对方法正文。']
            elif n==8 and number in(10,11):
                guides=['中心為組別，藍色方框為主題，外圍方框為子主題；is part of 表示主題包含關係，is associated with 表示主題關聯。','對照框內提及次數與表 8，再閱讀正文學生引語；實驗組紅框表示作者標出的額外子主題。']
                limits+=['概念關係圖整理訪談編碼，不是行為時間序列或因果模型。']
            else:
                guides=['將圖中的階段、模組或介面標示與本段作者說明逐項對照，依箭頭或畫面操作順序閱讀。','截圖與照片用來說明教學工具或活動如何實施；研究成效需回到測量與結果段落核對。']
                limits+=['設計圖、介面與活動示例本身不證明學生已學會，也不能從圖形大小估計效果量。']
            if n==8 and e['kind']=='figure' and number==1: guides=['依序看 Context（情境）、Construction（個人知識建構）、Conversation（對話澄清）、Collaboration（合作共構）。','有即時回饋的是場景引導問題；文字自我解釋任務不提供即時系統回饋，其輸出再帶入對話與概念圖共構。']
            e['study']={'summaryZh':title,'guideZh':guides,'limitsZh':limits}
    atomic_json(PLAN,plan)
    print('Annotated seven papers against the supplied PDFs.')

if __name__=='__main__': main()
