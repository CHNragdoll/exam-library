"""Reviewed image-table transcription and source-numbering notes."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
T=lambda rows,columns=None:dict(type='table',rows=rows,**({'columns':columns} if columns else {}))
P=lambda t:dict(type='paragraph',text=t)
H=lambda t:dict(type='heading',text=t)
replacements={
(2003,1):[T([['固定资本','1000',''],['其中：厂房','300',r'\(\frac{1}{20}\)'],['机器','600',r'\(\frac{1}{10}\)'],['小工具','100',r'\(\frac{1}{4}\)'],['流动资本','500','3.4']],['生产资本构成','价值（单位：万元）','年周转次数'])],
(2003,4):[T([['GDP增长率','9.2','14.2','13.5','12.6','10.5','9.6','8.8','7.8','7.1','8.0','7.3'],['物价上涨率','3.4','6.4','14.7','24.1','17.1','8.3','2.8','-0.8','-1.4','0.4','0.7']],['年份']+[str(y) for y in range(1991,2002)])],
(2007,4):[P('农村各阶层户数及其所占土地的比例（单位：%）'),T([['户数·抗战前','3.6','7.2','28.4','54.0','5.5','1.8'],['户数·减租后','2.4','6.7','38.0','47.0','2.5','3.4'],['土地·抗战前','29.5','21.0','29.5','19.0','0.8','0.2'],['土地·减租后','13.5','17.5','42.5','22.5','0.6','3.4']],['阶层','地主','富农','中农','贫农','雇农','其它'])],
(2007,5):[H('材料2'),P('十一五时期资源节约方面的主要指标'),T([['单位国内生产总值消耗','降低20%','约束性'],['单位工业增加值用水量','降低30%','约束性'],['农业灌溉用水有效利用系数','由0.45增加到0.5','预期性'],['工业固体废物综合利用率','由55.8%提高到60%','预期性']],['指标','2010年与2005年相比','属性（注）']),P('注：预期指标是指国家期望的发展目标，主要依靠市场主体的自主行为实现。政府要利用各种政策引导社会资源配置，努力争取实现。约束性指标是在预期的基础上进一步明确并强化政府职责的指标，政府要通过合理配置资源和有效运用行政力量，确保实现。'),P('十一五时期环境保护方面的主要指标'),T([['耕地保有量','减少0.3亿公顷','约束性'],['主要污染物排放总量','减少10%','约束性'],['森林覆盖率','增加1.8%','约束性']],['指标','2010年与2005年相比','属性（注）'])],
(2010,6):[P('《人民日报》关于不文明开车行为及其原因的调查'),T([['斑马线不减速让行2156票','乱停车挡道1687票','司机素质普遍有待提高2269票'],['夜间会车不关远光灯2045票','胡乱鸣笛1412票','跟风，随大流1469票'],['“加塞儿”并线不打灯1928票','司机出口成脏1076票','行人不文明导致司机不文明747票'],['雨天不减速水溅行人1902票','抢黄灯944票','因车多路堵无法文明驾驶464票']],['个人反感的不文明开车行为','个人反感的不文明开车行为（续）','不文明开车的原因'])]
}
notes={2005:['原稿第35题表格的年份行有两列均标为2001，重排版按原稿保留。'],2004:['原稿第36题位置只有表格和两个设问，未印题号及引导句；按原稿保留。'],2010:['原稿题号从20直接跳到22，未见第21题；按原稿保留，不补写缺题。'],2011:['原稿“做大分好社会财富这个‘蛋糕’”题未印25题号；正文按原稿保留。'],2017:['原稿第14题题号后缺少标点，重排版补上句点以区分题号和正文。']}
for year in range(2003,2022):
 p=ROOT/f'source/{year}.json';d=json.loads(p.read_text());done=[]
 for pg in d['pages']:
  blocks=[];n=pg['source_page'];seen=0
  for b in pg['blocks']:
   if b['type']=='figure':
    seen+=1
    if (year,n) in replacements and seen==1:blocks.extend(replacements[(year,n)]);done.append(n);continue
    if year==2010 and n==6 and seen==2:
     blocks.extend([P('某市交管局一年查处交通违章的数据统计'),T([['全年查处交通违章总数','207万起','100%'],['其中：机动车违章','112.2万起','54.2%'],['非机动车违章','80.5万起','38.9%'],['行人违章','14.3万起','6.9%']],['项目','数量','比例'])]);continue
    if year==2004 and n==4:continue # original blank 20px spacer image
   if year==2017 and b.get('text','').startswith('14 社会主义'):b['text']=b['text'].replace('14 社会主义','14.社会主义',1)
   blocks.append(b)
  pg['blocks']=blocks
 d['notes']=notes.get(year,[])
 d['extraction']['manually_transcribed_image_tables_pages']=done
 # sequential main-question coverage, excluding incidental decimal table values
 nums=[]
 for pg in d['pages']:
  for b in pg['blocks']:
   import re
   m=re.match(r'^(\d{1,2})\s*[.．、]',b.get('text',''))
   if m and int(m[1])>max(nums,default=0) and int(m[1])<=38:nums.append(int(m[1]))
 d['question_numbers']=nums
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
