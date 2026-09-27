"""Display-size math, including operators inside fraction arguments."""
import re

FRACTION=re.compile(r'\\(?:dfrac|tfrac|frac|dbinom|tbinom|binom)(?![A-Za-z])')
OPERATOR=re.compile(r'\\(?:sum|prod|coprod|bigcup|bigcap|bigvee|bigwedge|bigsqcup|bigoplus|bigotimes|bigodot|int|iint|iiint|iiiint|oint|lim|limsup|liminf|sup|inf|max|min)(?![A-Za-z])')

def argument(s,start):
    while start<len(s) and s[start].isspace():start+=1
    if start==len(s):raise ValueError('Missing TeX argument')
    if s[start]=='{':
        depth=1;pos=start+1
        while pos<len(s):
            if s[pos]=='\\':
                token=re.match(r'\\(?:[A-Za-z]+|.)',s[pos:]);pos+=len(token[0]);continue
            if s[pos]=='{':depth+=1
            elif s[pos]=='}':
                depth-=1
                if depth==0:return s[start+1:pos],pos+1
            pos+=1
        raise ValueError('Unbalanced TeX group')
    if s[start]=='\\':
        token=re.match(r'\\(?:[A-Za-z]+|.)',s[start:]);return token[0],start+len(token[0])
    return s[start],start+1

def expand_fractions(s):
    parts=[];start=0
    while match:=FRACTION.search(s,start):
        parts.append(s[start:match.start()])
        numerator,end=argument(s,match.end());denominator,end=argument(s,end)
        command=r'\dbinom' if 'binom' in match[0] else r'\dfrac'
        parts.append(command+r'{\displaystyle '+expand_fractions(numerator)+r'}{\displaystyle '+expand_fractions(denominator)+'}')
        start=end
    return ''.join(parts)+s[start:]

def display_style(s):
    # TeX's display style resets to text style in fractions and array cells.
    # Explicit style on both arguments and each large operator prevents that.
    s=expand_fractions(s)
    s=OPERATOR.sub(lambda m:r'\displaystyle '+m[0],s)
    return re.sub(r'(?:\\displaystyle\s*){2,}',lambda _:r'\displaystyle ',r'\displaystyle '+s)
