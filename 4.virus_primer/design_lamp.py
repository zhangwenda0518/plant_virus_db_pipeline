#!/usr/bin/env python3
"""
Standalone LAMP primer designer — zero external dependencies.
================================================================
SantaLucia 1998 thermodynamics + Notomi 2000 geometry.
Hybrid mode: single-sequence (fast scan) for orphan viruses;
multi-sequence (conservation-based) when ≥2 strains exist.

Usage:
  python design_lamp.py --fasta target.fa --mode single --preset standard
  python design_lamp.py --fasta aligned_strains.fa --mode multi
  python design_lamp.py --fasta all_viruses.fa --mode batch --out-dir primers/
"""

import sys, json, argparse, math, itertools, os
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ============================================================================
# SantaLucia 1998 NN parameters
# ============================================================================
NN_DH = {"AA":-7.9,"TT":-7.9,"AT":-7.2,"TA":-7.2,"AC":-8.4,"TG":-8.4,
         "AG":-7.8,"TC":-7.8,"CA":-8.5,"GT":-8.5,"CT":-7.8,"GA":-7.8,
         "CC":-8.0,"GG":-8.0,"CG":-10.6,"GC":-9.8}
NN_DS = {"AA":-22.2,"TT":-22.2,"AT":-20.4,"TA":-21.3,"AC":-22.4,"TG":-22.4,
         "AG":-21.0,"TC":-21.0,"CA":-22.7,"GT":-22.7,"CT":-21.0,"GA":-21.0,
         "CC":-19.9,"GG":-19.9,"CG":-27.2,"GC":-24.4}

CMPL = str.maketrans("ACGTURYKMSWBDHVNacgturykmswbdhvn",
                     "TGCAAYRMKSWVHDBNtgcaayrmkswvhdbn")
def rc(s): return s.translate(CMPL)[::-1]
def gc(s): u=s.upper(); return 100*(u.count("G")+u.count("C"))/len(u) if u else 0

def calc_tm(seq, mv=50,dv=8,dntp=0.8,dna=200):
    s,N=seq.upper(),len(seq)
    if N<2: return 0
    dh=ds=0.0
    for i in range(N-1):
        st=s[i:i+2]; dh+=NN_DH.get(st,0); ds+=NN_DS.get(st,0)
    dh+=0.2; ds+=-5.7
    if s==rc(s): ds+=-1.4
    mg=max(0,dv-dntp); na=mv/1000+0.12*(mg/1000)**0.5
    if na<=0: na=0.001
    ds_s=ds+0.368*(N-1)*math.log(na)
    ct=dna*1e-9; R=1.9872
    return round((1000*dh)/(ds_s+R*math.log(ct/4))-273.15,1)

def hairpin(seq):
    s,N=seq.upper(),len(seq); best=0.0
    for sl in range(2,min(8,N//2)):
        for lp in range(3,min(12,N-2*sl)):
            for st in range(0,N-2*sl-lp+1):
                L=s[st:st+sl]; R=s[st+sl+lp:st+sl+lp+sl]
                if L==rc(R):
                    dg=-sum(2 if c in"GC"else 1 for c in L)+3+0.5*lp
                    if dg<best: best=dg
    return round(best,1)

def dimer(a,b):
    rb=rc(b); best=0.0
    for shift in range(-len(a)+1,len(b)):
        ov=dg=0
        for i,ca in enumerate(a):
            j=i-shift
            if 0<=j<len(rb) and ca.upper()==rb[j].upper():
                ov+=1; dg-=2 if ca.upper()in"GC"else 1
            else:
                if ov>=4 and dg<best: best=dg
                ov=dg=0
        if ov>=4 and dg<best: best=dg
    return round(best,1)

# ============================================================================
# Data
# ============================================================================
@dataclass
class P:
    seq:str; role:str; start:int; end:int; tm:float; gc:float

@dataclass
class PS:
    f3:P; b3:P; f2:P; b2:P; f1c:P; b1c:P
    lf:Optional[P]=None; lb:Optional[P]=None
    score:float=0; notes:list=field(default_factory=list)

    @property
    def fip(self): return self.f1c.seq+self.f2.seq
    @property
    def bip(self): return self.b1c.seq+self.b2.seq

    def to_dict(self):
        return {"F3":self.f3.seq,"F3_Tm":self.f3.tm,"F3_GC":self.f3.gc,
                "B3":self.b3.seq,"B3_Tm":self.b3.tm,"B3_GC":self.b3.gc,
                "FIP":self.fip,"F2_Tm":self.f2.tm,"F1c_Tm":self.f1c.tm,
                "BIP":self.bip,"B2_Tm":self.b2.tm,"B1c_Tm":self.b1c.tm,
                "LF":self.lf.seq if self.lf else"",
                "LB":self.lb.seq if self.lb else"",
                "amplicon":self.b2.end-self.f2.start,
                "score":self.score,"notes":"; ".join(self.notes)}

# ============================================================================
# Parameter presets (inspired by lamp-virus)
# ============================================================================
PRESETS={
 "strict":{"tm":(58,62),"tm_tol":2,"gc":(40,65),
   "f3_len":(18,22),"b3_len":(18,22),"f2_len":(18,22),"b2_len":(18,22),
   "f1c_len":(20,22),"b1c_len":(20,22),"loop_len":(18,22),
   "f3_f2_gap":(0,15),"b2_b3_gap":(0,15),
   "f2_f1_gap":(40,55),"b1_b2_gap":(40,55),
   "f2_b2_amp":(120,160),"hp_max":-1.5,"dim_max":-4,"max_sets":10},
 "standard":{"tm":(59,65),"tm_tol":3,"gc":(35,70),
   "f3_len":(17,23),"b3_len":(17,23),"f2_len":(17,23),"b2_len":(17,23),
   "f1c_len":(19,24),"b1c_len":(19,24),"loop_len":(17,23),
   "f3_f2_gap":(0,20),"b2_b3_gap":(0,20),
   "f2_f1_gap":(35,65),"b1_b2_gap":(35,65),
   "f2_b2_amp":(120,200),"hp_max":-2,"dim_max":-5,"max_sets":10},
 "loose":{"tm":(55,67),"tm_tol":5,"gc":(30,75),
   "f3_len":(16,25),"b3_len":(16,25),"f2_len":(16,25),"b2_len":(16,25),
   "f1c_len":(18,26),"b1c_len":(18,26),"loop_len":(16,25),
   "f3_f2_gap":(0,30),"b2_b3_gap":(0,30),
   "f2_f1_gap":(30,70),"b1_b2_gap":(30,70),
   "f2_b2_amp":(100,250),"hp_max":-3,"dim_max":-6,"max_sets":20},
}

# ============================================================================
# Candidate scanner
# ============================================================================
def scan_primers(template, len_range, p, min_start=0, max_start=None):
    if max_start is None: max_start=len(template)
    lo,hi=len_range; tm_lo,tm_hi=p["tm"]; gc_lo,gc_hi=p["gc"]; hp=p["hp_max"]
    cands=[]
    for st in range(min_start,min(max_start,len(template)-lo+1)):
        for ln in range(lo,min(hi+1,len(template)-st+1)):
            seq=template[st:st+ln]
            if"N"in seq.upper(): continue
            t=calc_tm(seq)
            if not(tm_lo<=t<=tm_hi): continue
            g=gc(seq)
            if not(gc_lo<=g<=gc_hi): continue
            if hairpin(seq)<hp: continue
            cands.append(P(seq=seq,role="",start=st,end=st+ln,tm=t,gc=g))
    return cands

# ============================================================================
# Core LAMP designer — pre-match F1c→F2, B1c→B2 for massive pruning
# ============================================================================
def design_lamp(template, params=None, cons_profile=None):
    """
    Pre-match strategy:
    1. For each F1c: find ALL F2 satisfying [F2.end ∈ F1c.start - [f2_f1_hi..f2_f1_lo]]
    2. For each B1c: find ALL B2 satisfying [B2.start ∈ B1c.end + [b1_b2_lo..b1_b2_hi]]
    3. Only iterate F1c×B1c pairs that BOTH have at least one partner.
    4. Inside: iterate pre-matched F2×B2, check amp_len, then match F3/B3.
    This prunes the search from O(N^6) to O(K²·M²) where K≪N, M is small.
    """
    p=PRESETS.get(params,PRESETS["standard"]) if isinstance(params,str) else \
      {**PRESETS["standard"],**(params or {})}
    t=template.upper(); n=len(t)

    # 1. Scan all
    all_c={}
    for role,lr in [("f3",p["f3_len"]),("b3",p["b3_len"]),
                     ("f2",p["f2_len"]),("b2",p["b2_len"]),
                     ("f1c",p["f1c_len"]),("b1c",p["b1c_len"]),
                     ("loop",p["loop_len"])]:
        all_c[role]=scan_primers(t,lr,p)

    if not all_c["f1c"] or not all_c["b1c"]: return []

    # 2. Build position indices
    f2_end={}; b2_start={}; f3_end={}; b3_start={}
    for pr in all_c["f2"]: f2_end.setdefault(pr.end,[]).append(pr)
    for pr in all_c["b2"]: b2_start.setdefault(pr.start,[]).append(pr)
    for pr in all_c["f3"]: f3_end.setdefault(pr.end,[]).append(pr)
    for pr in all_c["b3"]: b3_start.setdefault(pr.start,[]).append(pr)

    f2f1_lo,f2f1_hi = p["f2_f1_gap"]
    b1b2_lo,b1b2_hi = p["b1_b2_gap"]
    amp_lo,amp_hi = p["f2_b2_amp"]
    f3f2_lo,f3f2_hi = p["f3_f2_gap"]
    b2b3_lo,b2b3_hi = p["b2_b3_gap"]

    # 3. Pre-match F1c → [F2] and B1c → [B2]
    # Use position tuples as keys since P is not hashable
    f1c_f2_map={}  # (start,end) → [primer, [F2_list]]
    f1c_idx={}     # (start,end) → F1c primer object
    for f1c in all_c["f1c"]:
        lo=f1c.start-f2f1_hi; hi=f1c.start-f2f1_lo
        m=[]
        for ep in range(max(0,lo),hi+1): m.extend(f2_end.get(ep,[]))
        if m:
            key=(f1c.start,f1c.end)
            f1c_f2_map[key]=m
            f1c_idx[key]=f1c

    b1c_b2_map={}
    b1c_idx={}
    for b1c in all_c["b1c"]:
        lo=b1c.end+b1b2_lo; hi=b1c.end+b1b2_hi
        m=[]
        for sp in range(lo,min(hi+1,n)): m.extend(b2_start.get(sp,[]))
        if m:
            key=(b1c.start,b1c.end)
            b1c_b2_map[key]=m
            b1c_idx[key]=b1c

    f1c_keys=list(f1c_f2_map.keys())
    b1c_keys=list(b1c_b2_map.keys())
    if not f1c_keys or not b1c_keys: return []

    # Cap if still too many
    MC=50
    if len(f1c_keys)>MC: f1c_keys=f1c_keys[::len(f1c_keys)//MC][:MC]
    if len(b1c_keys)>MC: b1c_keys=b1c_keys[::len(b1c_keys)//MC][:MC]

    # 4. Iterate
    sets=[]; seen=set()
    def _cons(pos,ln):
        if not cons_profile: return 1.0
        r=cons_profile[pos:pos+ln] if pos+ln<=len(cons_profile) else cons_profile[pos:]
        return sum(r)/len(r) if r else 0.5

    for f1c_k in f1c_keys:
        if len(sets)>=p["max_sets"]*2: break
        f1c=f1c_idx[f1c_k]
        for b1c_k in b1c_keys:
            b1c=b1c_idx[b1c_k]
            if b1c.start<=f1c.end: continue
            if len(sets)>=p["max_sets"]*2: break
            core_c=_cons(f1c.start,b1c.end-f1c.start)

            for f2 in f1c_f2_map[f1c_k]:
                if f2.start>=f1c.start: continue
                fl=f2.end-f2.start
                for b2 in b1c_b2_map[b1c_k]:
                    if b2.end<=b1c.end: continue
                    al=b2.end-f2.start
                    if not(amp_lo<=al<=amp_hi): continue

                    # F3: end ∈ [f2.start-f3f2_hi, f2.start-f3f2_lo]
                    f3m=[]
                    for ep in range(max(0,f2.start-f3f2_hi),f2.start-f3f2_lo+1):
                        f3m.extend(f3_end.get(ep,[]))
                    for f3 in f3m:
                        # B3: start ∈ [b2.end+b2b3_lo, b2.end+b2b3_hi]
                        b3m=[]
                        for sp in range(b2.end+b2b3_lo,min(b2.end+b2b3_hi+1,n)):
                            b3m.extend(b3_start.get(sp,[]))
                        for b3 in b3m:
                            key=(f3.start,f3.end,f2.start,f2.end,
                                 f1c.start,f1c.end,b1c.start,b1c.end,
                                 b2.start,b2.end,b3.start,b3.end)
                            if key in seen: continue
                            seen.add(key)

                            tms=[f3.tm,b3.tm,f2.tm,b2.tm,f1c.tm,b1c.tm]
                            tr=max(tms)-min(tms)
                            if tr>p["tm_tol"]: continue

                            sqs=[f3.seq,b3.seq,f2.seq,b2.seq,f1c.seq,b1c.seq]
                            if any(dimer(a,b)<p["dim_max"]
                                   for a,b in itertools.combinations(sqs,2)): continue

                            # Loop
                            lf=lb=None; bld=bld2=float("inf")
                            for lp in all_c["loop"]:
                                if f2.end<lp.start<f1c.start:
                                    d=abs(lp.tm-f2.tm)
                                    if d<bld: bld=d; lf=lp
                                if b1c.end<lp.start<b2.start:
                                    d=abs(lp.tm-b2.tm)
                                    if d<bld2: bld2=d; lb=lp

                            sc=0.0-tr*3
                            for pr in[f3,b3,f2,b2,f1c,b1c]:
                                sc+=max(0,hairpin(pr.seq)+5)
                            sc+=core_c*10+_cons(f2.start,fl)*5
                            if lf: sc+=4
                            if lb: sc+=4

                            nt=[]
                            if not lf: nt.append("LF_not_found")
                            if not lb: nt.append("LB_not_found")
                            if cons_profile and core_c<0.8:
                                nt.append(f"low_cons_{core_c:.2f}")

                            sets.append(PS(f3=f3,b3=b3,f2=f2,b2=b2,
                                           f1c=f1c,b1c=b1c,lf=lf,lb=lb,
                                           score=round(sc,2),notes=nt))

    sets.sort(key=lambda s:s.score,reverse=True)
    return sets[:p["max_sets"]]

# ============================================================================
# FASTA & consensus
# ============================================================================
def read_fasta(path):
    recs=[]; hdr=None; lines=[]
    with open(path) as f:
        for line in f:
            line=line.strip()
            if line.startswith(">"):
                if hdr: recs.append((hdr,"".join(lines)))
                hdr=line[1:]; lines=[]
            elif line: lines.append(line)
        if hdr: recs.append((hdr,"".join(lines)))
    return recs

def build_consensus(recs,min_freq=0.5):
    seqs=[s for _,s in recs]; ml=max(len(s)for s in seqs)
    cons=[]
    for pos in range(ml):
        cs=[s[pos].upper()for s in seqs if pos<len(s)and s[pos]!="-"]
        if not cs: cons.append("N")
        else:
            t,c=Counter(cs).most_common(1)[0]
            cons.append(t if c/len(cs)>=min_freq else"N")
    return"".join(cons)

def conservation_profile(recs,window=10):
    seqs=[s.upper()for _,s in recs]; ml=max(len(s)for s in seqs)
    raw=[]
    for pos in range(ml):
        cs=[s[pos]for s in seqs if pos<len(s)and s[pos]!="-"]
        raw.append(Counter(cs).most_common(1)[0][1]/len(cs)if cs else 0)
    sm=[]
    for i in range(len(raw)):
        s=max(0,i-window//2); e=min(len(raw),i+window//2+1)
        sm.append(sum(raw[s:e])/(e-s))
    return sm

# ============================================================================
# Output
# ============================================================================
TSV_HDR=["rank","score","F3","F3_len","F3_Tm","F3_GC","F3_pos",
         "B3","B3_len","B3_Tm","B3_GC","B3_pos",
         "FIP","FIP_len","F2_Tm","F1c_Tm",
         "BIP","BIP_len","B2_Tm","B1c_Tm",
         "LF","LB","amplicon","tm_range","notes"]

def write_output(sets,tsv_path,json_path):
    with open(tsv_path,"w")as f:
        f.write("\t".join(TSV_HDR)+"\n")
        for i,s in enumerate(sets,1):
            tms=[s.f3.tm,s.b3.tm,s.f2.tm,s.b2.tm,s.f1c.tm,s.b1c.tm]
            f.write("\t".join([
                str(i),str(s.score),
                s.f3.seq,str(s.f3.end-s.f3.start),str(s.f3.tm),str(s.f3.gc),
                f"{s.f3.start}-{s.f3.end}",
                s.b3.seq,str(s.b3.end-s.b3.start),str(s.b3.tm),str(s.b3.gc),
                f"{s.b3.start}-{s.b3.end}",
                s.fip,str(len(s.fip)),str(s.f2.tm),str(s.f1c.tm),
                s.bip,str(len(s.bip)),str(s.b2.tm),str(s.b1c.tm),
                s.lf.seq if s.lf else"",
                s.lb.seq if s.lb else"",
                str(s.b2.end-s.f2.start),
                str(round(max(tms)-min(tms),1)),
                "; ".join(s.notes),
            ])+"\n")
    with open(json_path,"w")as f:
        json.dump([s.to_dict()for s in sets],f,indent=2)

def pretty(sets,n=3):
    print("="*70)
    for s in sets[:n]:
        tms=[s.f3.tm,s.b3.tm,s.f2.tm,s.b2.tm,s.f1c.tm,s.b1c.tm]
        print(f"\n Score:{s.score:.1f} Amp:{s.b2.end-s.f2.start}bp "
              f"TmΔ:{max(tms)-min(tms):.1f}°C")
        print(f" F3:  {s.f3.seq} (Tm={s.f3.tm})")
        print(f" B3:  {s.b3.seq} (Tm={s.b3.tm})")
        print(f" FIP: {s.fip}")
        print(f" BIP: {s.bip}")
        if s.lf: print(f" LF:  {s.lf.seq}")
        if s.lb: print(f" LB:  {s.lb.seq}")
        if s.notes: print(f" ⚠ {s.notes[0]}")

# ============================================================================
# Design per species
# ============================================================================
def design_one(fasta,mode,preset,out_prefix):
    recs=read_fasta(fasta)
    if not recs: return None
    if mode=="auto": mode="multi"if len(recs)>=2 else"single"

    if mode=="multi"and len(recs)>=2:
        t=build_consensus(recs); cp=conservation_profile(recs)
        nh=sum(1 for c in cp if c>=0.9)
        print(f"  [multi] {len(recs)} strains → {len(t)}bp, ≥90%:{nh}/{len(cp)} ({100*nh/len(cp):.0f}%)")
    else:
        t=recs[0][1]; cp=None
        print(f"  [single] {len(t)}bp GC={gc(t):.0f}%")

    sets=design_lamp(t,preset,cp)
    if not sets:
        print(f"  [!] No sets with '{preset}', trying 'loose'...")
        sets=design_lamp(t,"loose",cp)
    if not sets:
        print(f"  [!] Still no sets.")
        return None

    write_output(sets,f"{out_prefix}.tsv",f"{out_prefix}.json")
    print(f"  [+] {len(sets)} set(s) → {out_prefix}.tsv/json")
    return sets

# ============================================================================
# Batch
# ============================================================================
def batch_design(fasta,out_dir="lamp_output",preset="standard"):
    os.makedirs(out_dir,exist_ok=True)
    recs=read_fasta(fasta)
    print(f"[*] {len(recs)} sequences total")

    # Group by species (expect header: >acc|Species|...)
    groups={}
    for hdr,seq in recs:
        parts=hdr.split("|")
        sp=parts[1].strip()if len(parts)>1 else hdr.split()[0]if hdr.split()else hdr
        groups.setdefault(sp,[]).append((hdr,seq))

    print(f"[*] {len(groups)} species/clusters")
    ok=fail=0; failed=[]
    for sp,seqs in sorted(groups.items()):
        sn=sp.replace(" ","_").replace("/","_")[:80]
        pf=os.path.join(out_dir,sn)
        if len(seqs)>=2:
            with open(pf+"_msa.fa","w")as f:
                for h,s in seqs:
                    f.write(f">{h}\n")
                    for i in range(0,len(s),80): f.write(s[i:i+80]+"\n")
            sets=design_one(pf+"_msa.fa","multi",preset,pf)
        else:
            with open(pf+".fa","w")as f:
                f.write(f">{seqs[0][0]}\n")
                for i in range(0,len(seqs[0][1]),80): f.write(seqs[0][1][i:i+80]+"\n")
            sets=design_one(pf+".fa","single",preset,pf)
        if sets: ok+=1
        else: fail+=1; failed.append(sp)

    print(f"\n[+] {ok}/{len(groups)} species designed")
    if failed:
        print(f"[!] {fail} failed (too short/AT-rich?):")
        for sp in failed[:15]: print(f"    - {sp}")

# ============================================================================
# CLI
# ============================================================================
def main():
    ap=argparse.ArgumentParser(description="LAMP primer designer (zero deps)")
    ap.add_argument("--fasta",required=True)
    ap.add_argument("--mode",choices=["single","multi","auto","batch"],default="auto")
    ap.add_argument("--preset",choices=["strict","standard","loose"],default="standard")
    ap.add_argument("--out-prefix",default="lamp_primers")
    ap.add_argument("--out-dir",default="lamp_output")
    args=ap.parse_args()

    if args.mode=="batch":
        batch_design(args.fasta,args.out_dir,args.preset)
    else:
        sets=design_one(args.fasta,args.mode,args.preset,args.out_prefix)
        if sets: pretty(sets)

if __name__=="__main__":
    main()
