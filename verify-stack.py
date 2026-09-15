#!/usr/bin/python3
"""Check deployed Quadlet containment, persistence and public bindings."""
import json,pathlib,subprocess,urllib.request,time
root=pathlib.Path(__file__).resolve().parent
images=json.loads((root/'images.lock.json').read_text())
def output(*cmd): return subprocess.check_output(cmd,text=True)
checks=[]
for name,image in images.items():
    unit=name if name.startswith('langfuse-') else 'langfuse-'+name
    assert output('systemctl','--user','is-active',unit+'.service').strip()=='active',unit
    info=json.loads(output('podman','--cgroup-manager=systemd','inspect','aorus-langfuse-'+name))[0]
    pid=info['State']['Pid']; assert pid>0
    cg=pathlib.Path(f'/proc/{pid}/cgroup').read_text().strip().split(':',2)[2]
    assert '/langfuse.slice/' in cg,(name,cg)
    supervisor=info['State'].get('ConmonPid')
    if supervisor:
        supervisor_cg=pathlib.Path(f'/proc/{supervisor}/cgroup').read_text()
        assert '/langfuse.slice/' in supervisor_cg,(name,'supervisor escaped slice')
    assert info['ImageDigest']==image.split('@')[1],(name,'image digest mismatch')
    for mount in info['Mounts']:
        if mount.get('RW'):
            assert mount['Source'].startswith('/mnt/aorus/langfuse/'),(name,mount['Source'])
    for mappings in (info['NetworkSettings'].get('Ports') or {}).values():
        for entry in mappings or []: assert entry['HostIp']=='127.0.0.1',entry
    checks.append({'container':name,'cgroup':cg,'image_digest_verified':True})
slice_cg=output('systemctl','--user','show','langfuse.slice','-p','ControlGroup','--value').strip()
p=pathlib.Path('/sys/fs/cgroup'+slice_cg)
expected={'memory.high':str(12*1024**3),'memory.max':str(16*1024**3),'memory.swap.max':str(2*1024**3),'pids.max':'4096','cpu.weight':'25'}
for key,value in expected.items(): assert (p/key).read_text().strip()==value,(key,(p/key).read_text())
assert 'default 25' in (p/'io.weight').read_text()
quota,period=(p/'cpu.max').read_text().split(); assert int(quota)==6*int(period)
for url in ['http://127.0.0.1:3000/api/public/health?failIfDatabaseUnavailable=true','http://127.0.0.1:3001/api/health']:
    with urllib.request.urlopen(url,timeout=10) as response: assert response.status==200
assert output('systemctl','--user','is-active','langfuse-bootstrap.service').strip()=='active'
assert output('systemctl','--user','is-enabled','langfuse.target').strip()=='enabled'
# Probe internal backends through the already running web container.
script="""Promise.all(['http://langfuse-worker:3030/api/health?failIfQueueConsumptionStuck=true','http://loki:3100/ready','http://prometheus:9090/-/ready','http://minio:9000/minio/health/ready'].map(async url=>{const r=await fetch(url,{signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error(url+': '+r.status)})).catch(e=>{console.error(e.message);process.exit(1)})"""
for attempt in range(12):
    result=subprocess.run(['podman','exec','aorus-langfuse-langfuse-web','node','-e',script],capture_output=True,text=True,timeout=20)
    if result.returncode==0: break
    time.sleep(5)
else: raise SystemExit('Backend readiness failed: '+result.stderr.strip())
subprocess.run(['python3',str(root/'bootstrap-s3.py')],check=True,timeout=20)
print(json.dumps({'containers':checks,'aggregate_limits':expected,'cpu_quota_cores':6,'boot_enabled':True},indent=2))
