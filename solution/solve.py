#!/usr/bin/env python3
from pathlib import Path
import csv, json
DATA=Path('/app/data'); OUT=Path('/app/result.json')
B64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
B64I={c:i for i,c in enumerate(B64)}

def rows(n):
    with open(DATA/n,newline='') as f:return list(csv.DictReader(f))
def norm(u): return u.split('#',1)[0].split('?',1)[0]
def active(dep,ts,chunk):
    xs=[x for x in dep if x['chunk']==chunk and int(x['ts_ms'])<=ts]
    if not xs: raise ValueError('no deployment')
    return max(xs,key=lambda x:int(x['ts_ms']))['revision']
def replay(use_cache=True):
    dep=rows('deployments.csv'); ctr={}; cache={}; loads={}
    for e in sorted(rows('sw_events.csv'),key=lambda x:(int(x['ts_ms']),int(x['seq']))):
        t=e['event']; ts=int(e['ts_ms']); c=e['client']; w=e['worker']; u=e['url']
        if t=='controller': ctr[c]=w
        elif t=='controller_clear': ctr.pop(c,None)
        elif t=='cache_put':
            k=norm(u); cache[(w,k)]=active(dep,ts,Path(k).name)
        elif t=='cache_delete': cache.pop((w,norm(u)),None)
        elif t=='script_load':
            k=norm(u); chunk=Path(k).name; cw=ctr.get(c)
            if use_cache and cw and (cw,k) in cache: r=cache[(cw,k)]
            else:
                r=active(dep,ts,chunk)
                if use_cache and cw: cache[(cw,k)]=r
            loads[e['load_id']]=(r,chunk)
    return loads

def vlq(s,i):
    v=0; sh=0
    while True:
        d=B64I[s[i]]; i+=1; v|=(d&31)<<sh
        if not d&32: break
        sh+=5
    neg=v&1; v>>=1
    return (-v if neg else v),i

def decoded(obj):
    out=[]; ps=pol=poc=pn=0
    for line in obj.get('mappings','').split(';'):
        segs=[]; pg=0
        if line:
            for enc in line.split(','):
                vals=[]; i=0
                while i<len(enc):
                    x,i=vlq(enc,i); vals.append(x)
                pg+=vals[0]
                if len(vals)>=4:
                    ps+=vals[1]; pol+=vals[2]; poc+=vals[3]
                    if len(vals)>=5: pn+=vals[4]
                    nm=obj.get('names',[])[pn] if len(vals)>=5 and obj.get('names') else None
                    segs.append((pg,obj['sources'][ps],pol,poc,nm))
        out.append(segs)
    return out

def plain(obj,l,c):
    ls=decoded(obj)
    if l<0 or l>=len(ls): return None
    xs=[x for x in ls[l] if x[0]<=c]
    if not xs:return None
    _,src,ol,oc,n=max(xs,key=lambda x:x[0]); return src,ol,oc,n

def indexed(obj,l,c):
    sec=None
    for s in obj['sections']:
        o=s['offset']; key=(int(o['line']),int(o['column']))
        if (l,c)>=key: sec=s
        else: break
    if not sec:return None
    o=sec['offset']; ll=l-int(o['line']); cc=c-int(o['column']) if ll==0 else c
    return plain(sec['map'],ll,cc)

def jload(rel):return json.loads((DATA/rel).read_text())
def pos(path,offset,mode='utf16'):
    p=path.read_bytes()[:offset]; l=p.count(b'\n'); tail=p.rsplit(b'\n',1)[-1].decode('utf-8')
    c=len(tail) if mode=='codepoint' else len(tail.encode('utf-16-le'))//2
    return l,c
def modpaths(): return {(x['revision'],x['intermediate_source']):x['map_path'] for x in rows('module_map_index.csv')}
def compose(rev,obj,l,c,mods):
    a=indexed(obj,l,c)
    if not a:return None
    src,ol,oc,n=a
    if src.startswith('src/'): return src,ol+1,oc,n or ''
    b=plain(jload(mods[(rev,src)]),ol,oc)
    if not b:return None
    s2,l2,c2,n2=b; return s2,l2+1,c2,n2 or ''

def choices(mode='anchors',column_mode='utf16'):
    idx=rows('map_index.csv'); an=rows('anchors.csv'); mods=modpaths(); groups={}
    for x in idx:groups.setdefault((x['revision'],x['chunk']),[]).append(x)
    out={}
    for key,cands in sorted(groups.items()):
        if mode=='first': out[key]=sorted(cands,key=lambda x:x['candidate'])[0]; continue
        r,c=key; aa=[x for x in an if x['revision']==r and x['chunk']==c]; good=[]
        for cand in cands:
            obj=jload(cand['map_path']); ok=True
            for a in aa:
                l,col=pos(DATA/'assets'/r/c,int(a['asset_offset_bytes']),column_mode)
                got=compose(r,obj,l,col,mods); exp=(a['source'],int(a['line']),int(a['column']),a['name'])
                if got!=exp:ok=False;break
            if ok:good.append(cand)
        if len(good)!=1:raise ValueError(f'candidate map not identifiable for {key}: {len(good)}')
        out[key]=good[0]
    return out

def build_result(use_worker_cache=True,choice_mode='anchors',column_mode='utf16',chain_maps=True):
    loads=replay(use_worker_cache); ch=choices(choice_mode,column_mode); mods=modpaths(); frames=[]
    raw=rows('frames.csv')
    for f in raw:
        rev,lc=loads[f['load_id']]; c=f['chunk']
        if lc!=c:raise ValueError('load/chunk mismatch')
        cand=ch[(rev,c)]; obj=jload(cand['map_path']); l,col=pos(DATA/'assets'/rev/c,int(f['asset_offset_bytes']),column_mode)
        if chain_maps: m=compose(rev,obj,l,col,mods)
        else:
            q=indexed(obj,l,col); m=None if not q else (q[0],q[1]+1,q[2],q[3] or '')
        if not m:raise ValueError(f'unmapped {f["frame_id"]}')
        s,ol,oc,n=m; frames.append({'frame_id':f['frame_id'],'revision':rev,'source':s,'line':int(ol),'column':int(oc),'name':n})
    by={x['frame_id']:x for x in frames}; inc=[]
    for i in rows('incidents.csv'):
        stack=sorted([x for x in raw if x['incident_id']==i['incident_id']],key=lambda x:int(x['stack_order']))
        root=next((by[x['frame_id']] for x in stack if by[x['frame_id']]['source'].startswith('src/') and not by[x['frame_id']]['source'].startswith('src/telemetry/')),None)
        if not root:raise ValueError('no actionable root')
        inc.append({'incident_id':i['incident_id'],'root_frame_id':root['frame_id'],'signature':root['source']+':'+root['name']})
    mc=[{'revision':k[0],'chunk':k[1],'candidate':v['candidate']} for k,v in sorted(ch.items())]
    return {'map_choices':mc,'frames':sorted(frames,key=lambda x:x['frame_id']),'incidents':sorted(inc,key=lambda x:x['incident_id'])}



def fit_clock_models():
    import math
    groups={}
    for r in rows('clock_samples.csv'):
        groups.setdefault((r['process'],r['segment']),[]).append((float(r['local_us']),float(r['capture_us'])))
    models={}
    for key,pts in groups.items():
        best=None
        # Candidate lines from pairs, scored by support then refitted RMS.
        for i in range(len(pts)):
            for j in range(i+1,len(pts)):
                x1,y1=pts[i]; x2,y2=pts[j]
                if x1==x2: continue
                a=(y2-y1)/(x2-x1); b=y1-a*x1
                inl=[p for p in pts if abs((a*p[0]+b)-p[1])<=150.0]
                if len(inl)<2: continue
                mx=sum(x for x,y in inl)/len(inl); my=sum(y for x,y in inl)/len(inl)
                den=sum((x-mx)**2 for x,y in inl)
                aa=sum((x-mx)*(y-my) for x,y in inl)/den
                bb=my-aa*mx
                inl2=[p for p in pts if abs((aa*p[0]+bb)-p[1])<=150.0]
                if len(inl2)>=2:
                    mx=sum(x for x,y in inl2)/len(inl2); my=sum(y for x,y in inl2)/len(inl2)
                    den=sum((x-mx)**2 for x,y in inl2)
                    aa=sum((x-mx)*(y-my) for x,y in inl2)/den
                    bb=my-aa*mx
                rms=(sum(((aa*x+bb)-y)**2 for x,y in inl2)/len(inl2))**0.5
                score=(len(inl2),-rms)
                if best is None or score>best[0]: best=(score,aa,bb,inl2)
        if best is None or best[0][0] != 7:
            raise ValueError(f'clock model not identifiable for {key}: support {None if best is None else best[0][0]}')
        models[key]=(best[1],best[2])
    return models

def async_frame_result(loads,ch,mods):
    out=[]
    for f in rows('async_frames.csv'):
        rev,lc=loads[f['load_id']]
        if lc!=f['chunk']: raise ValueError('async load/chunk mismatch')
        cand=ch[(rev,f['chunk'])]
        obj=jload(cand['map_path'])
        l,col=pos(DATA/'assets'/rev/f['chunk'],int(f['asset_offset_bytes']))
        m=compose(rev,obj,l,col,mods)
        if not m: raise ValueError(f'unmapped async frame {f["frame_id"]}')
        s,ol,oc,n=m
        out.append({'frame_id':f['frame_id'],'event_id':f['event_id'],'revision':rev,'source':s,'line':int(ol),'column':int(oc),'name':n})
    return sorted(out,key=lambda x:x['frame_id'])

def align_messages(events, times, mode='dp'):
    groups={}
    for e in events:
        if e['kind'] in ('message_send','message_recv'):
            groups.setdefault((e['channel'],e['direction']),{'send':[],'recv':[]})['send' if e['kind']=='message_send' else 'recv'].append(e)
    pairs={}
    for key,g in groups.items():
        ss=sorted(g['send'],key=lambda e:(times[e['event_id']],e['event_id']))
        rr=sorted(g['recv'],key=lambda e:(times[e['event_id']],e['event_id']))
        if mode=='greedy':
            used=set()
            for r in rr:
                cand=[s for s in ss if s['event_id'] not in used and s['payload']==r['payload'] and 0 <= times[r['event_id']]-times[s['event_id']] <= 250000]
                if cand:
                    s=min(cand,key=lambda x:abs(times[r['event_id']]-times[x['event_id']]))
                    used.add(s['event_id']); pairs[r['event_id']]=s['event_id']
            continue
        # sequence alignment: maximize matches, then minimize total positive transit time
        n,m=len(ss),len(rr)
        dp=[[None]*(m+1) for _ in range(n+1)]
        dp[0][0]=(0,0,())
        def better(a,b):
            if a is None:return b
            if b is None:return a
            # more matches, smaller cost, lexicographically stable path
            ka=(a[0],-a[1]); kb=(b[0],-b[1])
            if kb>ka:return b
            if kb<ka:return a
            return b if b[2]<a[2] else a
        for i in range(n+1):
            for j in range(m+1):
                cur=dp[i][j]
                if cur is None: continue
                if i<n:
                    v=(cur[0],cur[1],cur[2]+(('S',ss[i]['event_id']),))
                    dp[i+1][j]=better(dp[i+1][j],v)
                if j<m:
                    v=(cur[0],cur[1],cur[2]+(('R',rr[j]['event_id']),))
                    dp[i][j+1]=better(dp[i][j+1],v)
                if i<n and j<m and ss[i]['payload']==rr[j]['payload']:
                    dt=times[rr[j]['event_id']]-times[ss[i]['event_id']]
                    if 0<=dt<=250000:
                        v=(cur[0]+1,cur[1]+int(round(dt)),cur[2]+(('M',ss[i]['event_id'],rr[j]['event_id']),))
                        dp[i+1][j+1]=better(dp[i+1][j+1],v)
        final=dp[n][m]
        if final is None: raise ValueError(f'no alignment {key}')
        for step in final[2]:
            if step[0]=='M': pairs[step[2]]=step[1]
    return pairs

def causal_results(async_frames, clock_mode='robust', match_mode='dp'):
    ev=rows('async_events.csv')
    if clock_mode=='robust': models=fit_clock_models()
    else: models={k:(1.0,0.0) for k in {(e['process'],e['segment']) for e in ev}}
    times={e['event_id']:models[(e['process'],e['segment'])][0]*float(e['local_us'])+models[(e['process'],e['segment'])][1] for e in ev}
    by={e['event_id']:e for e in ev}
    msg_parent=align_messages(ev,times,match_mode)
    reverse={}
    for e in ev:
        if e['parent_event_id']:
            reverse[e['event_id']]=e['parent_event_id']
    reverse.update(msg_parent)
    afr={x['event_id']:x for x in async_frames}
    out=[]
    for e in ev:
        if e['kind']!='error' or not e['incident_id']: continue
        cur=e['event_id']; seen=set(); root=None
        while cur:
            if cur in seen: raise ValueError('causal cycle')
            seen.add(cur); q=by[cur]
            if q['kind']=='interaction': root=q; break
            cur=reverse.get(cur,'')
        if root is None: raise ValueError(f'no interaction root for {e["incident_id"]}')
        rf=afr.get(root['event_id'])
        if rf is None: raise ValueError('root lacks async frame')
        latency=(times[e['event_id']]-times[root['event_id']])/1000.0
        out.append({'incident_id':e['incident_id'],'trigger_event_id':root['event_id'],'trigger_frame_id':rf['frame_id'],'signature':rf['source']+':'+rf['name'],'latency_ms':round(latency,3)})
    return sorted(out,key=lambda x:x['incident_id'])

def message_pair_results():
    ev=rows('async_events.csv')
    models=fit_clock_models()
    times={e['event_id']:models[(e['process'],e['segment'])][0]*float(e['local_us'])+models[(e['process'],e['segment'])][1] for e in ev}
    pairs=align_messages(ev,times,'dp')
    by={e['event_id']:e for e in ev}
    out=[]
    for recv_id,send_id in pairs.items():
        r=by[recv_id]; s=by[send_id]
        out.append({'channel':r['channel'],'direction':r['direction'],'send_event_id':send_id,'recv_event_id':recv_id,'transit_ms':round((times[recv_id]-times[send_id])/1000.0,3)})
    return sorted(out,key=lambda x:(x['channel'],x['direction'],x['recv_event_id']))



def _scheduler_valid_pages(mode='chain'):
    import struct, zlib, hashlib
    page_size=1024
    raw=(DATA/'scheduler_ring.bin').read_bytes()
    if len(raw)%page_size: raise ValueError('scheduler ring size')
    valid=[]
    fmt='<4sBBBBIIHH8s8sI8s'
    for off in range(0,len(raw),page_size):
        pg=raw[off:off+page_size]
        try:
            magic,ver,pc,sc,slot,seq,gen,rc,blen,prev,ph,bcrc,res=struct.unpack_from(fmt,pg,0)
        except struct.error:
            continue
        if magic!=b'SRG3' or ver!=3 or blen<0 or blen>page_size-48: continue
        body=pg[48:48+blen]
        if (zlib.crc32(body)&0xffffffff)!=bcrc: continue
        h0=bytearray(pg[:48]); h0[28:36]=b'\x00'*8
        calc=hashlib.blake2s(bytes(h0)+body,digest_size=8).digest()
        if calc!=ph: continue
        valid.append({'pc':pc,'sc':sc,'slot':slot,'seq':seq,'gen':gen,'rc':rc,'body':body,'prev':prev,'hash':ph})
    if mode=='max_generation':
        # Deliberately plausible but incorrect recovery for audit: keep the highest generation for each page sequence.
        out={}
        for q in valid:
            k=(q['pc'],q['sc'],q['seq'])
            if k not in out or q['gen']>out[k]['gen']: out[k]=q
        streams={}
        for q in out.values(): streams.setdefault((q['pc'],q['sc']),[]).append(q)
        for k in streams: streams[k].sort(key=lambda x:x['seq'])
        return streams
    manifests=rows('scheduler_manifest.csv')
    byhash={q['hash']:q for q in valid}
    pcode={'rendererA':0,'rendererB':1,'workerA':2,'workerB':3}; scode={'s0':0,'s1':1}
    streams={}
    for m in manifests:
        tail=bytes.fromhex(m['tail_page_hash']); count=int(m['page_count']); chain=[]; cur=tail
        for _ in range(count):
            q=byhash.get(cur)
            if q is None: raise ValueError(f'missing scheduler page {cur.hex()}')
            if (q['pc'],q['sc'])!=(pcode[m['process']],scode[m['segment']]): raise ValueError('scheduler stream hash mismatch')
            chain.append(q); cur=q['prev']
        if cur!=b'\x00'*8: raise ValueError('scheduler chain does not terminate')
        chain.reverse()
        if len(chain)!=count: raise ValueError('scheduler chain length')
        streams[(q['pc'],q['sc'])]=chain
    return streams


def _promise_parent_map(tasks, mode='visible'):
    import struct, zlib
    revp={0:'rendererA',1:'rendererB',2:'workerA',3:'workerB'}; revs={0:'s0',1:'s1'}
    snaps={(r['process'],r['segment']):int(r['snapshot_serial']) for r in rows('promise_manifest.csv')}
    raw=(DATA/'promise_heap.bin').read_bytes(); fmt='<4sBBBBHHBBHHHHI14s'; size=struct.calcsize(fmt)
    if len(raw)%size: raise ValueError('promise heap size')
    ents=[]
    for off in range(0,len(raw),size):
        b=raw[off:off+size]
        try:
            magic,ver,pc,sc,flags,pid,target,ct,res,co,born,dead,eseq,crc,pad=struct.unpack(fmt,b)
        except struct.error: continue
        if magic!=b'PRH2' or ver!=2 or pc not in revp or sc not in revs or flags not in (1,2): continue
        chk=zlib.crc32(b[:22]+b'\x00\x00\x00\x00'+b[26:])&0xffffffff
        if chk!=crc: continue
        ents.append({'stream':(revp[pc],revs[sc]),'flags':flags,'pid':pid,'target':target,'ct':ct,'co':co,'born':born,'dead':dead,'seq':eseq})
    def before(a,b):
        d=(b-a)&0xffff
        return 0<d<0x8000
    grouped={}
    for e in ents: grouped.setdefault((e['stream'],e['pid']),[]).append(e)
    chosen={}
    for key,xs in grouped.items():
        st,pid=key; snap=snaps[st]
        if mode=='numeric_latest':
            q=max(xs,key=lambda x:(x['born'],x['seq']))
            chosen[key]=q; continue
        vis=[x for x in xs if (x['born']==snap or before(x['born'],snap)) and (x['dead']==0xffff or before(snap,x['dead']))]
        if len(vis)!=1: raise ValueError(f'promise visibility {st} {pid}: {len(vis)}')
        chosen[key]=vis[0]
    def resolve(st,pid):
        seen=set()
        while True:
            if pid in seen: raise ValueError('promise forwarding cycle')
            seen.add(pid); e=chosen.get((st,pid))
            if e is None: raise ValueError(f'missing live promise {st} {pid}')
            if e['flags']==2:
                pid=e['target']; continue
            uid=f'{st[0]}/{st[1]}/t{e["ct"]}.{e["co"]}'
            if uid not in tasks:
                if mode=='numeric_latest': return None
                raise ValueError(f'promise creator absent {uid}')
            return uid
    return resolve

def _scheduler_decode(mode='chain', ignore_parent_back=False, promise_mode='visible'):
    import struct
    revp={0:'rendererA',1:'rendererB',2:'workerA',3:'workerB'}; revs={0:'s0',1:'s1'}
    qnames={0:'user',1:'message',2:'microtask',3:'timer',4:'render',5:'worker',6:'continuation',7:'background'}
    streams=_scheduler_valid_pages(mode)
    tasks={}; parents={}; markers=[]; awaits={}
    for (pc,sc),pages in streams.items():
        process,segment=revp[pc],revs[sc]
        hist={i:[] for i in range(256)}; current={}
        for pg in pages:
            b=pg['body']; off=0; nrec=0
            while off+2<=len(b):
                ln=struct.unpack_from('<H',b,off)[0]; off+=2
                if ln<1 or off+ln>len(b): raise ValueError('bad scheduler record length')
                typ=b[off]; payload=b[off+1:off+ln]; off+=ln; nrec+=1
                if typ==1:
                    if len(payload)!=2: raise ValueError('ALLOC size')
                    tok,qc=struct.unpack('<BB',payload); occ=len(hist[tok])+1
                    uid=f'{process}/{segment}/t{tok}.{occ}'
                    hist[tok].append(uid); current[tok]=uid; tasks[uid]={'queue':qnames[qc],'process':process,'segment':segment}
                elif typ==2:
                    if len(payload)!=3: raise ValueError('LINK size')
                    ct,pt,back=struct.unpack('<BBB',payload)
                    if ct not in current or not hist[pt]: raise ValueError('dangling LINK')
                    if ignore_parent_back: back=0
                    if back>=len(hist[pt]):
                        # A malformed decoy branch is intentionally not usable as a committed history.
                        continue
                    parents[current[ct]]=hist[pt][-1-back]
                elif typ==3:
                    if len(payload)!=11: raise ValueError('MARK size')
                    tok,tag,cap=struct.unpack('<B H q',payload)
                    if tok not in current: raise ValueError('MARK without task')
                    markers.append({'process':process,'segment':segment,'task_uid':current[tok],'tag':tag,'capture_us':cap})
                elif typ in (4,5):
                    if len(payload)!=1: raise ValueError('close size')
                    tok=payload[0]
                    current.pop(tok,None)
                elif typ in (6,7):
                    if len(payload)!=1: raise ValueError('yield/resume size')
                elif typ==8:
                    if len(payload)!=8: raise ValueError('CHECK size')
                elif typ==9:
                    if len(payload)!=3: raise ValueError('AWAIT size')
                    tok,pid=struct.unpack('<B H',payload)
                    if tok not in current: raise ValueError('AWAIT without task')
                    awaits[current[tok]]=(process,segment,pid)
                else:
                    raise ValueError(f'unknown scheduler record {typ}')
            if nrec!=pg['rc']: raise ValueError('scheduler record count')
    resolve=_promise_parent_map(tasks,promise_mode)
    for child,(process,segment,pid) in awaits.items():
        par=resolve((process,segment),pid)
        if par is None: continue
        if child in parents and parents[child]!=par: raise ValueError('duplicate scheduler parent')
        parents[child]=par
    return tasks,parents,markers

def _scheduler_match(markers, models):
    # Global order-preserving marker/event alignment by support then total absolute calibrated residual.
    ev=rows('async_events.csv'); tags={r['event_id']:int(r['tag']) for r in rows('scheduler_events.csv')}
    times={e['event_id']:models[(e['process'],e['segment'])][0]*float(e['local_us'])+models[(e['process'],e['segment'])][1] for e in ev}
    result={}
    for stream in sorted({(e['process'],e['segment']) for e in ev}):
        ms=[m for m in markers if (m['process'],m['segment'])==stream]
        es=[e for e in ev if (e['process'],e['segment'])==stream]
        es.sort(key=lambda e:(times[e['event_id']],e['event_id']))
        n,m=len(ms),len(es)
        # score = (matches, total_abs_us); maximize matches, minimize cost.
        neg=(-10**9,float('inf'))
        dp=[[neg]*(m+1) for _ in range(n+1)]; act=[[None]*(m+1) for _ in range(n+1)]
        dp[0][0]=(0,0.0)
        def better(a,b):
            if b[0]>a[0]: return True
            if b[0]<a[0]: return False
            return b[1]<a[1]-1e-9
        for i in range(n+1):
            for j in range(m+1):
                cur=dp[i][j]
                if cur[0]<0: continue
                if i<n:
                    cand=cur
                    if better(dp[i+1][j],cand): dp[i+1][j]=cand; act[i+1][j]=('skip_m',i,j)
                if j<m:
                    cand=cur
                    if better(dp[i][j+1],cand): dp[i][j+1]=cand; act[i][j+1]=('skip_e',i,j)
                if i<n and j<m and ms[i]['tag']==tags[es[j]['event_id']]:
                    d=ms[i]['capture_us']-times[es[j]['event_id']]
                    if abs(d)<=1200.0:
                        cand=(cur[0]+1,cur[1]+abs(d))
                        if better(dp[i+1][j+1],cand): dp[i+1][j+1]=cand; act[i+1][j+1]=('match',i,j)
        i,j=n,m; pairs=[]
        while i or j:
            a=act[i][j]
            if a is None: raise ValueError(f'no scheduler alignment backtrace for {stream}')
            kind,pi,pj=a
            if kind=='match': pairs.append((pi,pj))
            i,j=pi,pj
        pairs.reverse()
        for mi,ej in pairs:
            e=es[ej]; mk=ms[mi]; eid=e['event_id']
            if eid in result: raise ValueError('duplicate scheduler event match')
            result[eid]={'task_uid':mk['task_uid'],'marker_error_ms':(mk['capture_us']-times[eid])/1000.0}
    return result,times

def scheduler_results(message_pairs, mode='chain', ignore_parent_back=False, promise_mode='visible'):
    tasks,parents,markers=_scheduler_decode(mode,ignore_parent_back,promise_mode)
    matched,times=_scheduler_match(markers,fit_clock_models())
    # Every async event is represented by a committed marker in the intended capture.
    ev=rows('async_events.csv'); by={e['event_id']:e for e in ev}
    if mode=='chain' and not ignore_parent_back and len(matched)!=len(ev):
        raise ValueError(f'scheduler match count {len(matched)} != {len(ev)}')
    bindings=[]
    for eid,x in matched.items():
        t=tasks[x['task_uid']]
        bindings.append({'event_id':eid,'task_uid':x['task_uid'],'queue':t['queue'],'marker_error_ms':round(x['marker_error_ms'],3)})
    recv_to_send={r['recv_event_id']:r['send_event_id'] for r in message_pairs}
    event_to_task={eid:x['task_uid'] for eid,x in matched.items()}
    task_to_event={x['task_uid']:eid for eid,x in matched.items()}
    paths=[]
    for e in ev:
        if e['kind']!='error' or not e['incident_id'] or e['event_id'] not in event_to_task: continue
        cur=event_to_task[e['event_id']]; chain=[]; handoffs=0; seen=set(); trigger=''
        while cur:
            if cur in seen: raise ValueError('scheduler ancestry cycle')
            seen.add(cur); chain.append(cur)
            pe=task_to_event.get(cur)
            if pe and by[pe]['kind']=='interaction': trigger=pe; break
            if cur in parents:
                cur=parents[cur]; continue
            if pe and by[pe]['kind']=='message_recv' and pe in recv_to_send:
                se=recv_to_send[pe]
                if se not in event_to_task: break
                cur=event_to_task[se]; handoffs+=1; continue
            break
        if not trigger:
            if mode=='chain' and not ignore_parent_back and promise_mode=='visible': raise ValueError(f'no scheduler interaction root for {e["incident_id"]}')
            continue
        paths.append({'incident_id':e['incident_id'],'trigger_event_id':trigger,'handoff_count':handoffs,'tasks':list(reversed(chain))})
    return sorted(bindings,key=lambda x:x['event_id']),sorted(paths,key=lambda x:x['incident_id'])

def build_extended(clock_mode='robust',match_mode='dp',use_worker_cache=True,choice_mode='anchors',column_mode='utf16',chain_maps=True):
    base=build_result(use_worker_cache,choice_mode,column_mode,chain_maps)
    loads=replay(use_worker_cache); ch=choices(choice_mode,column_mode); mods=modpaths()
    af=async_frame_result(loads,ch,mods)
    cr=causal_results(af,clock_mode,match_mode)
    mp=message_pair_results() if clock_mode=='robust' and match_mode=='dp' else []
    sb,sp=scheduler_results(mp) if mp else ([],[])
    return {**base,'async_frames':af,'message_pairs':mp,'causal_roots':cr,'task_bindings':sb,'task_paths':sp}

def main():
    OUT.write_text(json.dumps(build_extended(),indent=2,sort_keys=True)+'\n')
if __name__=='__main__': main()
