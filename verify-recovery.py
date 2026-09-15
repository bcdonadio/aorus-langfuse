#!/usr/bin/python3
"""Bounded Loki outage/Collector restart test preserving a known OTLP log."""
import importlib.util,json,pathlib,secrets,subprocess,time,urllib.parse
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('telemetry',root/'verify-telemetry.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
marker='aorus-recovery-'+secrets.token_hex(8)
def ctl(*args):subprocess.run(['systemctl','--user',*args],check=True,timeout=45)
ctl('stop','langfuse-loki.service')
try:
 v.post_otlp('http://127.0.0.1:4318','logs',{'resourceLogs':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'aorus-recovery'}}]},'scopeLogs':[{'scope':{'name':'aorus-recovery'},'logRecords':[{'timeUnixNano':str(time.time_ns()),'body':{'stringValue':marker},'severityNumber':9,'severityText':'INFO'}]}]}]})
 time.sleep(4)
 ctl('restart','langfuse-collector.service')
finally:ctl('start','langfuse-loki.service')
query=urllib.parse.urlencode({'query':'{service_name="aorus-recovery"} |= "'+marker+'"','limit':10})
for attempt in range(24):
 try:
  response=v.container_request_json('aorus-langfuse-langfuse-web','http://loki:3100/loki/api/v1/query_range?'+query)
  if marker in json.dumps(response):
   print(json.dumps({'recovery_marker':marker,'queued_log_survived_collector_restart':True}));break
 except Exception:pass
 time.sleep(5)
else:raise SystemExit('Recovery marker did not arrive within120s')
