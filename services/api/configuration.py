"""Pure local configuration validation. Never reads secret files or opens a database."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

FLAGS=('AIN_CONTAINER','AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_OBSERVER_MOUNTED','AIN_INTAKE_OVERVIEW_MOUNTED')


class ConfigurationError(ValueError):
    def __init__(self,codes):
        self.codes=tuple(dict.fromkeys(codes))
        super().__init__('Invalid local configuration: '+','.join(self.codes))


@dataclass(frozen=True)
class LocalSettings:
    profile:str
    container:bool
    web_port:int
    api_port:int
    agent_jobs:bool
    monitor:bool
    local_https:bool=False


def validate_environment(env):
    errors=[];profile=env.get('AIN_ENV','local')
    if profile not in ('local','test'):errors.append('runtime_profile_not_supported')
    flags={}
    for name in FLAGS:
        value=env.get(name,'0')
        if value not in ('0','1'):errors.append('invalid_'+name.lower())
        flags[name]=value=='1'
    ports={}
    for name,default in (('PORT','8080'),('AIN_API_PORT','8002')):
        value=env.get(name,default)
        valid=isinstance(value,str) and re.fullmatch('[0-9]{1,5}',value) and 1<=int(value)<=65535
        if not valid:errors.append('invalid_'+name.lower())
        ports[name]=int(value) if valid else 0
    if ports['PORT'] and ports['PORT']==ports['AIN_API_PORT']:errors.append('ports_must_differ')
    container=flags['AIN_CONTAINER'];bind=env.get('AIN_BIND_HOST','127.0.0.1')
    if bind not in ('127.0.0.1','0.0.0.0') or bind=='0.0.0.0' and not container:errors.append('bind_host_not_allowed')
    api_host=env.get('AIN_API_HOST','127.0.0.1')
    if api_host not in ('127.0.0.1','api') or api_host=='api' and not container:errors.append('api_host_not_allowed')
    model_host=env.get('AIN_OLLAMA_HOST','127.0.0.1')
    if model_host not in ('127.0.0.1','ollama','host.docker.internal') or model_host!='127.0.0.1' and not container:errors.append('model_host_not_allowed')
    cookie=env.get('AIN_SESSION_COOKIE','ain_session')
    local_https=env.get('AIN_LOCAL_HTTPS','0')=='1'
    if env.get('AIN_LOCAL_HTTPS','0') not in ('0','1'):errors.append('invalid_ain_local_https')
    if local_https:
        if profile!='test' or container or bind!='127.0.0.1' or api_host!='127.0.0.1' or cookie!='ain_test_session':errors.append('local_https_requires_native_test')
        value=env.get('AIN_LOCAL_TLS_DIRECTORY')
        try:
            base=Path(__file__).resolve().parents[2]/'.local'
            if not isinstance(value,str) or not value or any(ord(c)<32 for c in value) or '..' in value.replace('\\','/').split('/'):raise ValueError()
            target=(base.parent/Path(value)).absolute()
            if target==base or not target.is_relative_to(base):raise ValueError()
        except (OSError,ValueError):errors.append('local_tls_directory_invalid')
        if not isinstance(env.get('AIN_LOCAL_TLS_SHA256'),str) or not re.fullmatch('[a-f0-9]{64}',env['AIN_LOCAL_TLS_SHA256']):errors.append('local_tls_pin_invalid')
        try:
            state_value=env.get('AIN_STATE_ROOT');database_value=env.get('AIN_DB_PATH')
            if not isinstance(state_value,str) or not state_value or not isinstance(database_value,str) or not database_value:raise ValueError()
            private_base=Path(__file__).resolve().parents[2]/'.local'
            private_state=Path(state_value).resolve();private_database=Path(database_value).resolve()
            if private_state==private_base or not private_state.is_relative_to(private_base) or private_database!=private_state/'ain.sqlite3':raise ValueError()
        except (OSError,ValueError):errors.append('local_https_requires_explicit_private_state')
    elif any(k in env for k in ('AIN_LOCAL_TLS_DIRECTORY','AIN_LOCAL_TLS_SHA256')):errors.append('local_tls_requires_https')
    if cookie not in ('ain_session','ain_release_session') and not (cookie=='ain_test_session' and profile=='test' and not container):errors.append('cookie_namespace_not_allowed')
    if not container and (flags['AIN_OBSERVER_MOUNTED'] or flags['AIN_INTAKE_OVERVIEW_MOUNTED']):errors.append('container_mounts_require_container_mode')
    if env.get('AIN_AUTH_PROVIDER','local')!='local':errors.append('identity_provider_not_configured')
    if 'AIN_PUBLIC_ORIGIN' in env:errors.append('public_origin_not_configured')
    if any(k in env for k in ('AIN_COOKIE_SECURE','AIN_TLS_ENABLED','AIN_TRUST_PROXY','AIN_CORS_ORIGINS')):errors.append('external_security_not_configured')
    if any(k in env for k in ('AIN_SECRET_KEY','AIN_API_KEY','AIN_ADMIN_PASSWORD','AIN_JWT_SECRET')):errors.append('inline_secret_not_supported')
    if 'AIN_SECRETS_FILE' in env:errors.append('secret_provider_not_configured')
    if 'AIN_DATABASE_URL' in env:errors.append('managed_database_not_configured')
    revision=env.get('AIN_RELEASE_REVISION')
    if revision is not None and not (re.fullmatch('[0-9a-f]{40}',revision) or revision in ('working-tree','development-working-tree')):errors.append('invalid_release_revision')
    state=env.get('AIN_STATE_ROOT');database=env.get('AIN_DB_PATH')
    for name,value in (('state_root',state),('db_path',database)):
        if value is not None and (not isinstance(value,str) or not value or any(ord(c)<32 for c in value)):errors.append('invalid_'+name)
        elif isinstance(value,str) and (value.startswith(('\\\\','//')) or re.match('[A-Za-z][A-Za-z0-9+.-]*://',value)):errors.append('state_paths_must_be_local')
    if container:
        if state!='/app/.local/active' or database!='/app/.local/active/ain.sqlite3':errors.append('container_state_paths_not_allowed')
    elif not any(code in errors for code in ('invalid_state_root','invalid_db_path','state_paths_must_be_local')):
        try:
            resolved_state=Path(state).resolve() if state else None
            resolved_database=Path(database).resolve() if database else None
            if resolved_state and resolved_database and resolved_database.parent!=resolved_state:errors.append('state_database_paths_mismatch')
        except (OSError,ValueError):errors.append('state_paths_invalid')
    if errors:raise ConfigurationError(errors)
    return LocalSettings(profile,container,ports['PORT'],ports['AIN_API_PORT'],flags['AIN_AGENT_JOBS'],flags['AIN_MONITOR_ENABLED'],local_https)


def diagnostic(env):
    try:config=validate_environment(env)
    except ConfigurationError as error:
        return {'format':'ain-environment-check-v1','component':'api','valid':False,'errors':list(error.codes),'production_ready':False}
    return {'format':'ain-environment-check-v1','component':'api','valid':True,'errors':[],
        'profile':config.profile,'container':config.container,'web_port':config.web_port,'api_port':config.api_port,
        'agent_jobs':config.agent_jobs,'monitor':config.monitor,'secret_provider_configured':False,'managed_identity_configured':False,'production_ready':False}


def main():
    report=diagnostic(os.environ);print(json.dumps(report,indent=2))
    if not report['valid']:raise SystemExit(2)


if __name__=='__main__':main()
