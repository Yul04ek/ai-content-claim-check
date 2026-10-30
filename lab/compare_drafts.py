import re,glob,json,itertools,difflib,statistics
import os
base=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")+"/"
def body(t):
    t=t.split("----------------------------------------")[-1]
    t=re.sub(r"Suggested topic tags:.*","",t)
    t=re.sub(r"#\w+","",t)
    t=re.sub(r"\[Add:[^\]]*\]","",t)
    return re.sub(r"\s+"," ",t).strip()
def words(t): return re.findall(r"[a-z0-9’']+",t.lower())
def sents(t): return [s for s in re.split(r"(?<=[.!?])\s+",t) if len(s.split())>2]
def wdiff(a,b):  # share of words that differ (1 - sequence ratio on word lists)
    return 1-difflib.SequenceMatcher(None,words(a),words(b)).ratio()
def sdiff(a,b):  # share of sentences in a with no close match in b (word ratio >=0.6)
    sa,sb=sents(a),sents(b)
    def best(s):
        return max((difflib.SequenceMatcher(None,words(s),words(x)).ratio() for x in sb),default=0)
    return sum(1 for s in sa if best(s)<0.6)/len(sa), len(sa)
ids=["F-003","F-004","F-005","F-006","F-007"]
V1={i:body(open(base+f"baseline-v1/golden/drafts/{i}_draft_v1.txt").read()) for i in ids}
B={i:body(open(base+f"lab/make_run_2026-10-30/drafts/{i}.txt").read()) for i in ids}
runs=sorted(glob.glob(base+"lab/drafts/gemini-3.1-flash-lite_draft_prompt_v2_2026-10-30/run*_F-00*_draft.txt"))
C={i:[body(open(f).read()) for f in runs if f"_{i}_" in f] for i in ids}
def avg(x): return sum(x)/len(x)
print("Compare drafts: v1 Make (29 Oct), v2 Make (30 Oct), lab runs\n")
print("words per draft  v1 / Make-v2 / lab runs")
for i in ids: print(i,len(words(V1[i])),len(words(B[i])),[len(words(c)) for c in C[i]])
print("\n(1) same record, v1 Make draft vs v2 Make draft: % different words | % sentences without close match (of v1 sentences)")
for i in ids:
    s,n=sdiff(V1[i],B[i]); print(i,f"{wdiff(V1[i],B[i])*100:.0f}% | {s*100:.0f}% of {n}")
print("\n(2) lab, prompt v2 (Gemini 3.1), between the 3 runs of one record: mean % different words | mean % sentences w/o match")
allw=[];alls=[]
for i in ids:
    pairs=list(itertools.combinations(range(len(C[i])),2))
    w=[wdiff(C[i][a],C[i][b]) for a,b in pairs]
    s=[sdiff(C[i][a],C[i][b])[0] for a,b in pairs]+[sdiff(C[i][b],C[i][a])[0] for a,b in pairs]
    allw+=w;alls+=s
    print(i,len(C[i]),"runs",f"{avg(w)*100:.0f}% | {avg(s)*100:.0f}%")
print("all",f"{avg(allw)*100:.0f}% | {avg(alls)*100:.0f}%")
print("\n(3) Make v2 (gpt-5-nano) vs each lab run (Gemini): mean % different words")
for i in ids: print(i,f"{avg([wdiff(B[i],c) for c in C[i]])*100:.0f}%")
print("\n(3b) Make v1 vs lab v2 runs: for reference")
for i in ids: print(i,f"{avg([wdiff(V1[i],c) for c in C[i]])*100:.0f}%")
