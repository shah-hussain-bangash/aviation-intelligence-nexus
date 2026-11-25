"""Pure admission for explicitly pinned, synthetic-only local rehearsals."""
import re


def require(condition, message='rehearsal_check_failed'):
    if not condition:
        raise ValueError(message)


def admit_images(images, revision):
    require(isinstance(images, dict) and set(images) == {'api', 'web'}, 'two_pinned_images_required')
    require(all(isinstance(v, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', v) for v in images.values()), 'immutable_image_ids_required')
    require(isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision), 'full_revision_required')


def validate_configuration(config, project, volume, port, images):
    require(isinstance(project, str) and re.fullmatch(r'ain-http-check-[0-9a-f]{12}', project), 'isolated_project_required')
    require(volume == project + '_state', 'fresh_named_volume_required')
    require(type(port) is int and 1024 <= port <= 65535, 'unprivileged_port_required')
    require(config['name'] == project and set(config['services']) == {'api', 'web'}, 'project_services_mismatch')
    require(set(config['volumes']) == {'state'} and config['volumes']['state']['name'] == volume
            and config['volumes']['state'].get('external', False) is False, 'private_volume_required')
    api, web = config['services']['api'], config['services']['web']
    networks = config.get('networks', {})
    require(set(networks) == {'default'} and networks['default'].get('name') == project + '_default'
            and not networks['default'].get('external', False), 'private_network_required')
    for name, service in (('api', api), ('web', web)):
        require(service['image'] == images[name], 'pinned_image_mismatch')
        require(service.get('read_only') is True and service.get('cap_drop') == ['ALL'], 'container_safeguards_required')
        require('no-new-privileges:true' in service.get('security_opt', []), 'no_privilege_escalation_required')
        require(service.get('restart') == 'no' and not service.get('privileged', False), 'manual_bounded_lifecycle_required')
        require(not service.get('network_mode') and not service.get('pid') and not service.get('devices'), 'shared_host_namespace_not_allowed')
        require(set(service.get('networks', {})) == {'default'}, 'private_service_network_required')
    mounts = api.get('volumes', [])
    require(len(mounts) == 1 and mounts[0]['type'] == 'volume' and mounts[0]['source'] == 'state'
            and mounts[0]['target'] == '/app/.local', 'private_state_mount_required')
    require(not api.get('ports') and not web.get('volumes'), 'unexpected_mount_or_api_port')
    ports = web.get('ports', [])
    require(len(ports) == 1 and ports[0]['host_ip'] == '127.0.0.1'
            and int(ports[0]['published']) == port and int(ports[0]['target']) == 8080, 'loopback_web_port_required')
    require(api['environment']['AIN_AGENT_JOBS'] == api['environment']['AIN_MONITOR_ENABLED'] == '0', 'background_workers_must_be_disabled')
    require(api['environment']['AIN_STATE_ROOT'] == '/app/.local/active'
            and api['environment']['AIN_DB_PATH'] == '/app/.local/active/ain.sqlite3', 'container_state_paths_required')
    return True


def toolkit_identity():
    """Record the harness separately from the images' expected source revision."""
    import hashlib
    from services.api.paths import ROOT
    from infra.verify_schema8 import source_identity
    names = ('infra/rehearsal_admission.py', 'infra/http_rehearsal.py',
             'infra/rehearsal_scenarios.py', 'infra/packaged_recovery_rehearsal.py',
             'infra/encrypted_recovery_rehearsal.py', 'infra/fixtures/packaged_recovery_probe.py')
    return {**source_identity(), 'harness_sha256': {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}}
