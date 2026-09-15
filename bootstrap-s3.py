#!/usr/bin/python3
"""Idempotently create the local Langfuse S3 bucket using AWS SigV4."""
import datetime, hashlib, hmac, json, pathlib, urllib.request, urllib.error
c=json.loads((pathlib.Path.home()/'.config/aorus-langfuse/credentials.json').read_text())
now=datetime.datetime.now(datetime.timezone.utc)
date=now.strftime('%Y%m%d'); stamp=now.strftime('%Y%m%dT%H%M%SZ')
empty=hashlib.sha256(b'').hexdigest(); scope=f'{date}/us-east-1/s3/aws4_request'
headers=f'host:127.0.0.1:9000\nx-amz-content-sha256:{empty}\nx-amz-date:{stamp}\n'
signed='host;x-amz-content-sha256;x-amz-date'
canonical=f'PUT\n/langfuse\n\n{headers}\n{signed}\n{empty}'
to_sign='AWS4-HMAC-SHA256\n'+stamp+'\n'+scope+'\n'+hashlib.sha256(canonical.encode()).hexdigest()
key=('AWS4'+c['minio_password']).encode()
for item in [date,'us-east-1','s3','aws4_request']: key=hmac.new(key,item.encode(),hashlib.sha256).digest()
signature=hmac.new(key,to_sign.encode(),hashlib.sha256).hexdigest()
auth=f'AWS4-HMAC-SHA256 Credential=langfuse/{scope}, SignedHeaders={signed}, Signature={signature}'
req=urllib.request.Request('http://127.0.0.1:9000/langfuse',data=b'',method='PUT',headers={'Authorization':auth,'x-amz-date':stamp,'x-amz-content-sha256':empty})
try:
    with urllib.request.urlopen(req,timeout=15) as result: print('S3 bucket ready:',result.status)
except urllib.error.HTTPError as e:
    body=e.read()
    if e.code==409 and b'BucketAlreadyOwnedByYou' in body: print('S3 bucket already exists')
    else: raise SystemExit(f'S3 bootstrap failed: HTTP {e.code}')
