"""Cooperative stop markers; no thread/process/provider interruption."""


class StopRequested(Exception):
    pass


def finish_cancelled(result,at):
    result.update(state='cancelled',cancelled_at=at,claims=[],
        error='Stopped at a safe boundary. Completed tool evidence is retained; no draft is available for review.')
    for key in ['report_sha256','quality','report_status','uncited_tools','finding_style']:
        result.pop(key,None)
    for step in result['steps']:
        if step['state']=='running':
            step.update(state='cancelled_before_execution',error='Stop requested before this tool call started.')
    if result.get('report_repair',{}).get('state')=='running':result['report_repair']['state']='cancelled'
