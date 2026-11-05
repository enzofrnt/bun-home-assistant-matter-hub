#!/usr/bin/env python3
"""Measure an active bridge with one paired, fixed Matter controller."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.request

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--rounds',type=int,default=3)
parser.add_argument('--seconds',type=int,default=10)
parser.add_argument('--entities',type=int,default=100)
args=parser.parse_args()
if min(args.rounds,args.seconds,args.entities)<1: parser.error('rounds, seconds and entities must be positive')
args.output.mkdir(parents=True,exist_ok=True)
network='hamh-runtime-paired-20261105'
app='hamh-runtime-paired-app'
fixture='hamh-runtime-paired-fixture'
controller='hamh-runtime-paired-controller'
images={'node':'home-assistant-matter-hub:node-baseline','bun':'bun-home-assistant-matter-hub:local'}
owned=[]
network_owned=False
runs=[]
metadata={'entities':args.entities,'rounds':args.rounds,'phase_seconds':args.seconds,'app_cpus':2,'app_memory_bytes':2*1024**3,'controller_runtime':'Bun 1.4.2 with matter.js 0.18.0, identical for both servers','controller_cpus':2,'controller_memory_bytes':1024**3,'subscription_min_seconds':0,'subscription_max_seconds':10,'state_changes_per_second':100,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('matter-controller.mjs')]}}


def docker(*words,check=True,timeout=180):
    result=subprocess.run(['docker',*map(str,words)],capture_output=True,text=True,timeout=timeout)
    if check and result.returncode: raise RuntimeError(f'{words}: {result.stderr}')
    return (result.stdout+(result.stderr if words[0]=='logs' else '')).strip()


def request(port,path,body=None,timeout=20):
    req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response: return json.load(response)


def start(name,*options):
    docker('run','--pull=never','--platform=linux/arm64','-d','--name',name,'--network',network,*options)
    owned.append(name)


def remove(name):
    docker('rm','-fv',name,check=False)
    if name in owned: owned.remove(name)


SAMPLE='''
cat /sys/fs/cgroup/cpu.stat
echo NETWORK
cat /proc/net/dev
for p in /proc/[0-9]*; do
  exe=$(readlink "$p/exe" 2>/dev/null)
  case "$exe" in */bun|*/node) cat "$p/smaps_rollup" ;; esac
done
'''


def sample(name=app):
    raw=docker('exec',name,'sh','-c',SAMPLE,timeout=15)
    rss=re.findall(r'^Rss:\s+(\d+) kB',raw,re.M)
    if len(rss)!=1: raise RuntimeError(f'Expected one application runtime: {raw}')
    net=re.search(r'eth0:\s+(.*)',raw)[1].split()
    return {'rx_bytes':int(net[0]),'tx_bytes':int(net[8]),'at':time.monotonic(),'rss_bytes':int(rss[0])*1024,'cpu_seconds':int(re.search(r'usage_usec (\d+)',raw)[1])/1e6}


def stats(name,samples):
    seconds=samples[-1]['at']-samples[0]['at']
    cpu=samples[-1]['cpu_seconds']-samples[0]['cpu_seconds']
    return {'name':name,'seconds':seconds,'cpu_seconds':cpu,'cpu_percent_one_core':100*cpu/seconds,'rss_median_bytes':statistics.median(s['rss_bytes'] for s in samples),'rss_peak_bytes':max(s['rss_bytes'] for s in samples),'rx_bytes':samples[-1]['rx_bytes']-samples[0]['rx_bytes'],'tx_bytes':samples[-1]['tx_bytes']-samples[0]['tx_bytes'],'samples':samples}


def phase(name,seconds):
    samples=[sample()]
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        time.sleep(min(1,max(0,end-time.monotonic())))
        samples.append(sample())
    return stats(name,samples)


def persist():
    (args.output/'results.json').write_text(json.dumps({'metadata':metadata,'runs':runs},indent=2)+'\n')


try:
    if docker('network','ls','--filter',f'name=^{network}$','--format','{{.Name}}'): raise RuntimeError('Paired benchmark network already exists')
    docker('network','create','--ipv6','--subnet','fd42:4c25:1105:2::/64',network)
    network_owned=True
    metadata['image_ids']={v:docker('image','inspect','--format','{{.Id}}',image) for v,image in images.items()}
    metadata['controller_image_id']=docker('image','inspect','--format','{{.Id}}','hamh-runtime-benchmark:controller')
    for round_index in range(1,args.rounds+1):
        for variant in (['node','bun'] if round_index%2 else ['bun','node']):
            print(f'BEGIN paired round={round_index} {variant}',flush=True)
            prefix=args.output/f'{round_index}-{variant}'
            start(fixture,'--network-alias','hamh-runtime-bench-fixture','--cpus=1','--memory=256m','-p','127.0.0.1:18125:18123','-e',f'ENTITY_COUNT={args.entities}','hamh-runtime-benchmark:fixture')
            start(app,'--network-alias','hamh-runtime-bench-app','--no-healthcheck','--cpus=2','--memory=2g','-p','127.0.0.1:18483:8482','-e','HAMH_HOME_ASSISTANT_URL=http://hamh-runtime-bench-fixture:18123','-e','HAMH_HOME_ASSISTANT_ACCESS_TOKEN=local-fixture-only','-e','HAMH_LOG_LEVEL=warn','-e','HAMH_PROTOCOL_LOG_LEVEL=error','-e','HAMH_DISABLE_LOG_COLORS=true','-e','HAMH_HOME_ASSISTANT_REFRESH_INTERVAL=3600',images[variant])
            deadline=time.monotonic()+60
            while True:
                try:
                    metrics=request(18483,'/api/metrics')
                    if metrics['homeAssistant']['entities']==args.entities: break
                except Exception: pass
                if time.monotonic()>deadline: raise RuntimeError('Application not ready')
                time.sleep(.3)
            bridge=request(18483,'/api/matter/bridges',{'name':'Paired benchmark','filter':{'include':[{'type':'pattern','value':'*'}],'exclude':[]}},timeout=120)
            if bridge['status']!='running' or bridge['deviceCount']!=args.entities: raise RuntimeError(f'Bad bridge: {bridge}')
            phases=[phase('unpaired-idle',3)]
            start(controller,'--cpus=2','--memory=1g','-p','127.0.0.1:18124:18124','hamh-runtime-benchmark:controller')
            deadline=time.monotonic()+20
            while True:
                try:
                    request(18124,'/status'); break
                except Exception:
                    if time.monotonic()>deadline: raise
                    time.sleep(.2)
            pairing=request(18124,'/start',{},timeout=120)
            time.sleep(2)
            initial=request(18124,'/status')
            if not initial['ready'] or initial['values']!=args.entities: raise RuntimeError(f'Bad initial subscription: {initial}')
            phases.append(phase('paired-idle',args.seconds))
            request(18125,'/control',{'rate':100})
            phases.append(phase('paired-state-updates',args.seconds))
            after_updates=request(18124,'/status')
            if after_updates['changed']<args.entities: raise RuntimeError(f'No subscription changes: {after_updates}')
            producer_before=sample(controller)
            samples=[sample()]
            with ThreadPoolExecutor(max_workers=1) as pool:
                result=pool.submit(request,18124,'/reads',{'seconds':args.seconds,'expected':args.entities},args.seconds+30)
                deadline=time.monotonic()+args.seconds+35
                while not result.done():
                    if time.monotonic()>deadline: raise RuntimeError('Matter read benchmark timeout')
                    time.sleep(.5);samples.append(sample())
                reads=result.result()
            producer_after=sample(controller)
            if reads.get('error') or reads['errors'] or not reads['requests']: raise RuntimeError(f'Matter read failures: {reads}')
            read_phase=stats('paired-reads-and-updates',samples)
            read_phase['reads']=reads
            read_phase['cpu_ms_per_read']=read_phase['cpu_seconds']*1000/reads['requests']
            read_phase['controller_cpu_seconds']=producer_after['cpu_seconds']-producer_before['cpu_seconds']
            phases.append(read_phase)
            request(18125,'/control',{'rate':0})
            phases.append(phase('paired-recovery',5))
            status=request(18124,'/status')
            health=request(18483,'/api/health/')
            metrics=request(18483,'/api/metrics')
            if health['status']!='healthy' or metrics['bridges']['totalFabrics']!=1 or metrics['bridges']['totalDevices']!=args.entities: raise RuntimeError(f'Invalid final health: {health} {metrics}')
            app_log=docker('logs',app)
            prefix.with_suffix('.app.log').write_text(app_log)
            if re.search(r'\b(?:ERROR|FATAL)\b|Unhandled rejection',app_log): raise RuntimeError('Application emitted a runtime error; see app log')
            prefix.with_suffix('.controller.log').write_text(docker('logs',controller))
            docker('stop','--time','30',controller,timeout=40)
            docker('stop','--time','30',app,timeout=40)
            final=json.loads(docker('inspect',app))[0]['State']
            if final['OOMKilled'] or final['ExitCode']: raise RuntimeError(f'Bad application shutdown: {final}')
            runs.append({'round':round_index,'variant':variant,'pairing_seconds':pairing['pairingSeconds'],'phases':phases,'controller':status,'health':health,'metrics':metrics,'exit_code':final['ExitCode'],'oom_killed':final['OOMKilled']})
            persist()
            print(f'END paired {variant} subscription changes={status["changed"]} reads/s={reads["requests_per_second"]:.1f}',flush=True)
            remove(controller);remove(app);remove(fixture)
    summary={}
    for variant in ['node','bun']:
        selected=[r for r in runs if r['variant']==variant]
        summary[variant]={'pairing_seconds':statistics.median(r['pairing_seconds'] for r in selected)}
        for phase_name in [p['name'] for p in selected[0]['phases']]:
            ps=[next(p for p in r['phases'] if p['name']==phase_name) for r in selected]
            summary[variant][phase_name]={k:statistics.median(p[k] for p in ps) for k in ['rss_median_bytes','rss_peak_bytes','cpu_percent_one_core']}
            if 'reads' in ps[0]:
                summary[variant][phase_name]['reads']={k:statistics.median(p['reads'][k] for p in ps) for k in ['requests_per_second','p50_ms','p95_ms','errors']}
                summary[variant][phase_name]['cpu_ms_per_read']=statistics.median(p['cpu_ms_per_read'] for p in ps)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
except Exception as error:
    (args.output/'failure.json').write_text(json.dumps({'error':str(error)},indent=2)+'\n')
    for name in owned:
        (args.output/f'failure-{name}.log').write_text(docker('logs',name,check=False))
    raise
finally:
    for name in reversed(owned): docker('rm','-fv',name,check=False)
    if network_owned: docker('network','rm',network,check=False)
