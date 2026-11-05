#!/usr/bin/env python3
"""Linux ARM64 production runtime comparison through local Docker.

Creates only containers/networks named hamh-runtime-bench-*. Never connects to a
real Home Assistant. Builds images first; see RUNTIME_BENCHMARK.md.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--rounds', type=int, default=3)
parser.add_argument('--entities', type=int, nargs='+', default=[0,100,500])
parser.add_argument('--seconds', type=float, default=10)
parser.add_argument('--settle', type=float, default=5)
parser.add_argument('--variants', nargs='+', choices=['node','bun'], default=['node','bun'])
parser.add_argument('--images', nargs=2, default=['home-assistant-matter-hub:node-baseline','bun-home-assistant-matter-hub:local'])
args=parser.parse_args()
if args.rounds<1 or args.seconds<=0 or args.settle<0 or any(n<0 for n in args.entities):
    parser.error('Use positive rounds/seconds and nonnegative entity counts/settle time.')
args.output.mkdir(parents=True,exist_ok=True)
network='hamh-runtime-bench-20261105'
app='hamh-runtime-bench-app'
fixture='hamh-runtime-bench-fixture'
load='hamh-runtime-bench-load'
owned=[]
rows=[]
network_owned=False
metadata={'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'run.py',HERE/'http-load.mjs',HERE/'mock-home-assistant.ts']},'rounds':args.rounds,'profiles':args.entities,'phase_seconds':args.seconds,'settle_seconds':args.settle,'container_cpus':2,'container_memory_bytes':2*1024**3,'concurrency':16,'state_changes_per_second':100,'paired_controllers':0,'variants':args.variants,'producer_cpus':4,'producer_threads':4,'warmup_seconds':2,'request_mix':'strict equal quarters, verified per run','rss_note':'Linux kernel smaps_rollup RSS for the application process; cgroup memory is also retained. Sampling approximately once per second. CPU includes the small in-container sampler overhead.'}


def docker(*words,check=True,timeout=180):
    p=subprocess.run(['docker',*map(str,words)],capture_output=True,text=True,timeout=timeout)
    if check and p.returncode: raise RuntimeError(f'docker {words}: {p.stderr}')
    return (p.stdout + (p.stderr if words and words[0]=='logs' else '')).strip()


def request(port,path,body=None,timeout=10):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as res: return json.load(res)


def remove(name):
    docker('rm','-fv',name,check=False)
    if name in owned: owned.remove(name)


def start(name,*options):
    docker('run','--pull=never','--platform=linux/arm64','-d','--name',name,'--network',network,*options)
    owned.append(name)


SAMPLE='''
echo CPU
cat /sys/fs/cgroup/cpu.stat
echo CGROUP_MEMORY
cat /sys/fs/cgroup/memory.current
for d in /proc/[0-9]*; do
  exe=$(readlink "$d/exe" 2>/dev/null)
  case "$exe" in
    */bun|*/node)
      echo APP_PROCESS
      cat "$d/smaps_rollup"
      ;;
  esac
done
'''


def sample():
    raw=docker('exec',app,'sh','-c',SAMPLE,timeout=15)
    rss=re.findall(r'^Rss:\s+(\d+) kB',raw,re.M)
    pss=re.findall(r'^Pss:\s+(\d+) kB',raw,re.M)
    private=re.findall(r'^Private_Dirty:\s+(\d+) kB',raw,re.M)
    if len(rss)!=1: raise RuntimeError(f'Expected one app process: {raw}')
    return {'at':time.monotonic(),'rss_bytes':int(rss[0])*1024,'pss_bytes':int(pss[0])*1024,'private_dirty_bytes':int(private[0])*1024,'cpu_seconds':int(re.search(r'usage_usec (\d+)',raw)[1])/1e6,'cgroup_memory_bytes':int(re.search(r'CGROUP_MEMORY\n(\d+)',raw)[1])}


def phase(name,seconds):
    samples=[sample()]
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        time.sleep(min(1,max(0,deadline-time.monotonic())))
        samples.append(sample())
    return phase_result(name,samples)


def phase_result(name,samples):
    elapsed=samples[-1]['at']-samples[0]['at']
    cpu=samples[-1]['cpu_seconds']-samples[0]['cpu_seconds']
    return {'name':name,'seconds':elapsed,'cpu_seconds':cpu,'cpu_percent_one_core':100*cpu/elapsed,'rss_median_bytes':statistics.median(s['rss_bytes'] for s in samples),'rss_peak_bytes':max(s['rss_bytes'] for s in samples),'pss_median_bytes':statistics.median(s['pss_bytes'] for s in samples),'private_dirty_median_bytes':statistics.median(s['private_dirty_bytes'] for s in samples),'samples':samples}


def wait_ready(expected):
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if docker('inspect','--format','{{.State.Running}}',app)!='true':
            raise RuntimeError(docker('logs',app,check=False))
        try:
            metrics=request(18482,'/api/metrics')
            if metrics['homeAssistant']['connected'] and metrics['homeAssistant']['entities']==expected:
                return metrics
        except Exception: pass
        time.sleep(.2)
    raise RuntimeError('Readiness timeout')


def persist():
    (args.output/'results.json').write_text(json.dumps({'metadata':metadata,'runs':rows},indent=2)+'\n')


try:
    # Refuse to take ownership of an existing network from an earlier run.
    if docker('network','ls','--filter',f'name=^{network}$','--format','{{.Name}}'):
        raise RuntimeError(f'{network} already exists; inspect/remove the previous benchmark resources first.')
    docker('network','create','--ipv6','--subnet','fd42:4c25:1105:1::/64',network)
    network_owned=True
    info=json.loads(docker('info','--format','{{json .}}'))
    metadata['docker']={k:info[k] for k in ['ServerVersion','Architecture','NCPU','MemTotal','OperatingSystem','KernelVersion']}
    metadata['images']={}
    for v,image in zip(['node','bun'],args.images):
        info=json.loads(docker('image','inspect',image))[0]
        metadata['images'][v]={k:info[k] for k in ['Id','RepoTags','Architecture','Os','Size']}
    start(load,'--cpus=4','--memory=512m','hamh-runtime-benchmark:load')
    for round_index in range(1,args.rounds+1):
        for count in args.entities:
            for variant in (args.variants if round_index%2 else list(reversed(args.variants))):
                print(f'BEGIN round={round_index} entities={count} {variant}',flush=True)
                start(fixture,'--cpus=1','--memory=256m','-p','127.0.0.1:18123:18123','-e',f'ENTITY_COUNT={count}','hamh-runtime-benchmark:fixture')
                image=args.images[0 if variant=='node' else 1]
                t0=time.monotonic()
                start(app,'--no-healthcheck','--cpus=2','--memory=2g','-p','127.0.0.1:18482:8482','-e','HAMH_HOME_ASSISTANT_URL=http://hamh-runtime-bench-fixture:18123','-e','HAMH_HOME_ASSISTANT_ACCESS_TOKEN=local-fixture-only','-e','HAMH_LOG_LEVEL=warn','-e','HAMH_PROTOCOL_LOG_LEVEL=error','-e','HAMH_DISABLE_LOG_COLORS=true','-e','HAMH_HOME_ASSISTANT_REFRESH_INTERVAL=3600',image)
                metrics=wait_ready(count)
                startup=time.monotonic()-t0
                bridge_seconds=0
                if count:
                    bridge_start=time.monotonic()
                    bridge=request(18482,'/api/matter/bridges',{'name':'Runtime benchmark','filter':{'include':[{'type':'pattern','value':'*'}],'exclude':[]}},timeout=180)
                    bridge_seconds=time.monotonic()-bridge_start
                    if bridge['status']!='running': raise RuntimeError(f'Bridge failed: {bridge}')
                    deadline=time.monotonic()+120
                    while True:
                        metrics=request(18482,'/api/metrics')
                        if metrics['bridges']['totalDevices']==count: break
                        if time.monotonic()>deadline: raise RuntimeError(f'Endpoint count mismatch: {metrics}')
                        time.sleep(.5)
                warm=docker('exec',load,'node','/bench/http-load.mjs',f'http://{app}:8482','2','16',str(count))
                if json.loads(warm)['errors']: raise RuntimeError(f'Warm-up errors: {warm}')
                time.sleep(args.settle)
                phases=[phase('idle',args.seconds)]
                control_before=request(18123,'/control')
                if count:
                    request(18123,'/control',{'rate':100})
                    phases.append(phase('state-updates',args.seconds))
                generator_cpu_before=int(re.search(r'usage_usec (\d+)',docker('exec',load,'cat','/sys/fs/cgroup/cpu.stat'))[1])/1e6
                first=sample()
                prefix=args.output/f'{round_index}-{count}-{variant}'
                with prefix.with_suffix('.load.log').open('w') as out:
                    gen=subprocess.Popen(['docker','exec',load,'node','/bench/http-load.mjs',f'http://{app}:8482',str(args.seconds),'16',str(count)],stdout=out,stderr=subprocess.STDOUT)
                    samples=[first]
                    deadline=time.monotonic()+args.seconds+30
                    while gen.poll() is None:
                        if time.monotonic()>deadline: gen.kill(); raise RuntimeError('Load generator timeout')
                        time.sleep(.5)
                        samples.append(sample())
                    if gen.returncode: raise RuntimeError(prefix.with_suffix('.load.log').read_text())
                if len(samples)<2: samples.append(sample())
                generator_cpu_after=int(re.search(r'usage_usec (\d+)',docker('exec',load,'cat','/sys/fs/cgroup/cpu.stat'))[1])/1e6
                load_result=json.loads(prefix.with_suffix('.load.log').read_text())
                distribution=list(load_result['byPath'].values())
                if len(distribution)!=4 or max(distribution)-min(distribution)>16: raise RuntimeError(f'Unbalanced request mix: {load_result}')
                cpu_load=phase_result('api-and-state-updates' if count else 'api',samples)
                cpu_load['http']=load_result
                cpu_load['generator_cpu_seconds']=generator_cpu_after-generator_cpu_before
                cpu_load['cpu_ms_per_request']=cpu_load['cpu_seconds']*1000/load_result['requests']
                phases.append(cpu_load)
                request(18123,'/control',{'rate':0})
                phases.append(phase('recovery',max(5,args.seconds/2)))
                after=request(18123,'/control')
                metrics=request(18482,'/api/metrics')
                health=request(18482,'/api/health/')
                if health['status']!='healthy' or metrics['bridges']['totalDevices']!=count: raise RuntimeError(f'Health/count failure: {health} {metrics}')
                if count and (after['sentUpdates']-control_before['sentUpdates'])<100*args.seconds: raise RuntimeError(f'Updates not delivered: {after}')
                endpoint_validation=None
                if count:
                    tree=request(18482,f'/api/matter/bridges/{bridge["id"]}/devices',timeout=30)
                    temperatures=[]
                    def walk(endpoint):
                        state=endpoint.get('state',{}).get('temperatureMeasurement',{})
                        if 'measuredValue' in state: temperatures.append(state['measuredValue'])
                        for child in endpoint.get('parts',[]): walk(child)
                    walk(tree)
                    changed=sum(value is not None and value!=2000 for value in temperatures)
                    endpoint_validation={'temperature_endpoints':len(temperatures),'changed_from_initial':changed}
                    if len(temperatures)!=math.ceil(count/2) or not changed: raise RuntimeError(f'Matter states not updated: {endpoint_validation}')
                log=docker('logs',app,check=False)
                prefix.with_suffix('.app.log').write_text(log)
                docker('stop','--time','30',app,timeout=40)
                stopped=json.loads(docker('inspect',app))[0]['State']
                if stopped['OOMKilled'] or stopped['ExitCode']!=0: raise RuntimeError(f'Bad shutdown: {stopped}')
                row={'round':round_index,'variant':variant,'entities':count,'startup_ready_seconds':startup,'bridge_creation_seconds':bridge_seconds,'phases':phases,'fixture':after,'metrics':metrics,'health':health,'exit_code':stopped['ExitCode'],'oom_killed':stopped['OOMKilled'],'endpoint_validation':endpoint_validation}
                rows.append(row);persist()
                print(f'END {variant} entities={count} idleRSS={phases[0]["rss_median_bytes"]/1024**2:.1f}MiB HTTP={load_result["requests_per_second"]:.0f}/s errors={load_result["errors"]}',flush=True)
                remove(app);remove(fixture)
    summary={}
    for count in args.entities:
        summary[str(count)]={}
        for variant in args.variants:
            runs=[r for r in rows if r['variant']==variant and r['entities']==count]
            data={key:statistics.median(r[key] for r in runs) for key in ['startup_ready_seconds','bridge_creation_seconds']}
            for name in [p['name'] for p in runs[0]['phases']]:
                ps=[next(p for p in r['phases'] if p['name']==name) for r in runs]
                data[name]={key:statistics.median(p[key] for p in ps) for key in ['cpu_percent_one_core','rss_median_bytes','rss_peak_bytes','pss_median_bytes','private_dirty_median_bytes']}
                if 'http' in ps[0]:
                    data[name]['http']={key:statistics.median(p['http'][key] for p in ps) for key in ['requests_per_second','p50_ms','p95_ms','p99_ms','errors']}
                    data[name]['cpu_ms_per_request']=statistics.median(p['cpu_ms_per_request'] for p in ps)
            summary[str(count)][variant]=data
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    for name in reversed(owned):
        docker('rm','-fv',name,check=False)
    if network_owned: docker('network','rm',network,check=False)
