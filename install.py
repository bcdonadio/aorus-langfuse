#!/usr/bin/python3
"""Install the Aorus rootless deployment. Run on the host as bcdonadio."""
import argparse, base64, json, os, pathlib, secrets, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path('/mnt/aorus/langfuse')
CONFIG = pathlib.Path.home()/'.config/aorus-langfuse'

def run(*args):
    return subprocess.run(args, check=True, text=True)

def check_mount():
    result = subprocess.check_output(['findmnt','-J','-T',str(DATA)], text=True)
    mounts = json.loads(result)['filesystems']
    if not any(m.get('target') == str(DATA) and m.get('fstype') == 'xfs' and m.get('source') == '/dev/mapper/aorus-langfuse' for m in mounts):
        raise SystemExit('Refusing to proceed: expected aorus-langfuse XFS filesystem is not mounted')

def write_private(name, text):
    path = CONFIG/name
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,'w') as f: f.write(text)
    path.chmod(0o600)

def env(name, values):
    for value in values.values():
        if '\n' in str(value): raise ValueError('Environment value contains newline')
    write_private(name, ''.join(f'{k}={v}\n' for k,v in values.items()))

def prepare():
    check_mount()
    owners={'postgres':(999,999),'clickhouse':(101,101),'clickhouse-logs':(101,101),'redis':(999,999),'minio':(65532,65532),'collector':(10001,10001),'loki':(10001,10001),'prometheus':(65534,65534),'grafana':(472,472),'metrics':(10001,10001)}
    for name,(uid,gid) in owners.items():
        directory=DATA/name
        if directory.is_symlink(): raise SystemExit(f'Refusing symlink {directory}')
        directory.mkdir(exist_ok=True)
        # Only change the root directory; never recursively rewrite existing data.
        run('podman','unshare','chown',f'{uid}:{gid}',str(directory))
        run('podman','unshare','chmod','750',str(directory))

def credentials():
    CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
    CONFIG.chmod(0o700)
    path=CONFIG/'credentials.json'
    if path.exists(): c=json.loads(path.read_text())
    else:
        c={k:secrets.token_hex(32) for k in ['postgres_password','redis_password','clickhouse_password','minio_password','admin_password','grafana_password','nextauth_secret','salt','encryption_key']}
        c.update(langfuse_public_key='pk-lf-'+secrets.token_hex(16),langfuse_secret_key='sk-lf-'+secrets.token_hex(32),admin_email='bcdonadio@bcdonadio.com')
        write_private('credentials.json',json.dumps(c,indent=2)+'\n')
    env('postgres.env',dict(POSTGRES_USER='langfuse',POSTGRES_DB='langfuse',POSTGRES_PASSWORD=c['postgres_password'],TZ='UTC',PGTZ='UTC'))
    env('redis.env',dict(REDIS_PASSWORD=c['redis_password']))
    env('clickhouse.env',dict(CLICKHOUSE_USER='langfuse',CLICKHOUSE_PASSWORD=c['clickhouse_password'],CLICKHOUSE_DB='default',TZ='UTC',CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT='1'))
    env('minio.env',dict(MINIO_ROOT_USER='langfuse',MINIO_ROOT_PASSWORD=c['minio_password'],MINIO_BROWSER='off'))
    common=dict(NEXTAUTH_URL='http://127.0.0.1:3000',NEXTAUTH_SECRET=c['nextauth_secret'],SALT=c['salt'],ENCRYPTION_KEY=c['encryption_key'],DATABASE_URL=f"postgresql://langfuse:{c['postgres_password']}@postgres:5432/langfuse",DIRECT_URL=f"postgresql://langfuse:{c['postgres_password']}@postgres:5432/langfuse",CLICKHOUSE_MIGRATION_URL='clickhouse://clickhouse:9000',CLICKHOUSE_URL='http://clickhouse:8123',CLICKHOUSE_USER='langfuse',CLICKHOUSE_PASSWORD=c['clickhouse_password'],CLICKHOUSE_CLUSTER_ENABLED='false',REDIS_HOST='redis',REDIS_PORT='6379',REDIS_AUTH=c['redis_password'],REDIS_TLS_ENABLED='false',TELEMETRY_ENABLED='false',AUTH_DISABLE_SIGNUP='true',LANGFUSE_OBSERVATION_FIELD_OVERFLOW_ENABLED='true',LANGFUSE_OTEL_INGESTION_MAX_BODY_BYTES='67108864',LANGFUSE_INIT_ORG_ID='aorus',LANGFUSE_INIT_ORG_NAME='Aorus',LANGFUSE_INIT_PROJECT_ID='codex',LANGFUSE_INIT_PROJECT_NAME='Codex',LANGFUSE_INIT_PROJECT_PUBLIC_KEY=c['langfuse_public_key'],LANGFUSE_INIT_PROJECT_SECRET_KEY=c['langfuse_secret_key'],LANGFUSE_INIT_USER_EMAIL=c['admin_email'],LANGFUSE_INIT_USER_NAME='Bernardo Donadio',LANGFUSE_INIT_USER_PASSWORD=c['admin_password'],LANGFUSE_S3_BATCH_EXPORT_ENABLED='true',LANGFUSE_S3_MEDIA_UPLOAD_INTERNAL_ENDPOINT='http://minio:9000',LANGFUSE_INGESTION_QUEUE_PROCESSING_CONCURRENCY='4')
    for kind,prefix in [('EVENT','events/'),('MEDIA','media/'),('BATCH_EXPORT','exports/')]:
        stem='LANGFUSE_S3_'+kind+('_UPLOAD' if kind!='BATCH_EXPORT' else '')
        common.update({stem+'_BUCKET':'langfuse',stem+'_REGION':'us-east-1',stem+'_ACCESS_KEY_ID':'langfuse',stem+'_SECRET_ACCESS_KEY':c['minio_password'],stem+'_ENDPOINT':'http://127.0.0.1:9000' if kind=='MEDIA' else 'http://minio:9000',stem+'_FORCE_PATH_STYLE':'true',stem+'_PREFIX':prefix})
    env('langfuse.env',common)
    auth='Basic '+base64.b64encode((c['langfuse_public_key']+':'+c['langfuse_secret_key']).encode()).decode()
    env('collector.env',{'LANGFUSE_AUTH_HEADER':auth})
    env('grafana.env',dict(GF_SECURITY_ADMIN_USER='admin',GF_SECURITY_ADMIN_PASSWORD=c['grafana_password'],GF_USERS_ALLOW_SIGN_UP='false',GF_AUTH_ANONYMOUS_ENABLED='false',GF_ANALYTICS_REPORTING_ENABLED='false',GF_ANALYTICS_CHECK_FOR_UPDATES='false',GF_SERVER_ROOT_URL='http://127.0.0.1:3001'))

def install():
    images=json.loads((ROOT/'images.lock.json').read_text())
    for name,image in images.items():
        unit=name if name.startswith('langfuse-') else 'langfuse-'+name
        lines=(ROOT/(unit+'.container')).read_text().splitlines()
        if [line[6:] for line in lines if line.startswith('Image=')] != [image]:
            raise SystemExit(f'Image pin mismatch: {unit}')
    check_mount(); credentials()
    for name in ['collector.yaml','loki.yaml','prometheus.yaml','grafana-datasources.yaml','grafana-dashboards.yaml','grafana-dashboard.json','clickhouse.xml','clickhouse-users.xml','disk-metrics.py']:
        shutil.copyfile(ROOT/name, CONFIG/name)
        (CONFIG/name).chmod(0o644)
    for suffix,destination in [('.container',pathlib.Path.home()/'.config/containers/systemd'),('.network',pathlib.Path.home()/'.config/containers/systemd'),('.service',pathlib.Path.home()/'.config/systemd/user'),('.slice',pathlib.Path.home()/'.config/systemd/user'),('.target',pathlib.Path.home()/'.config/systemd/user'),('.timer',pathlib.Path.home()/'.config/systemd/user')]:
        destination.mkdir(parents=True,exist_ok=True)
        for source in ROOT.glob('*'+suffix):
            link=destination/source.name
            if link.is_symlink() and link.resolve()==source: continue
            if link.exists() or link.is_symlink(): raise SystemExit(f'Refusing to replace unrelated unit {link}')
            link.symlink_to(source)
    run('systemctl','--user','daemon-reload')
    run('systemctl','--user','enable','langfuse.target','langfuse-disk-metrics.timer')
    print('Installed. Credentials are in ~/.config/aorus-langfuse/credentials.json (0600).')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--credentials-only',action='store_true')
    args=parser.parse_args()
    if args.prepare: prepare()
    elif args.credentials_only: credentials()
    else: install()
