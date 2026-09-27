from pathlib import Path
for folder,kind in [('politics-latex-2003-2023','questions'),('politics-answers-latex-2009-2023','answers')]:
 p=Path('../')/folder/'build.py';s=p.read_text()
 s=s.replace('408 TeX','politics TeX').replace('exam-library/cs408','exam-library/politics').replace('408 双版本目录','政治双版本目录').replace('cs408-original','politics-original').replace('408 LaTeX','政治 LaTeX').replace('408 计算机统考','考研政治')
 s=s.replace(' · 真题；2009–2015 含原有解析',' · 真题' if kind=='questions' else ' · 答案解析')
 s=s.replace('正文与代码重排 · LaTeX 公式 · 独立图形保留原图','正文自适应重排 · 可编辑 LaTeX 源码 · 图表保留')
 s=s.replace('body_tex(text)+', 'body_tex(text)+')
 s=s.replace('assert page[\'blocks\'] or page.get(\'blank\')','assert page[\'blocks\'] or page.get(\'blank\') or page.get(\'continuation_only\')')
 # Early politics papers have five-option multiple-choice questions.
 s=s.replace('([ABCD])','([ABCDE])').replace("not in 'ABCD'","not in 'ABCDE'")
 s=s.replace('break_arrows=spec[\'kind\']==\'questions\'','break_arrows=True')
 p.write_text(s)
