"""Deterministic research-report coverage gate, not semantic truth verification."""
from rag.service import validate_claims
from rag.index import SOURCES
from services.api.route_history import valid_saved_profile
from agents.model_evidence import valid_observation
from agents.distribution_evidence import valid_observation as valid_distributions,LIMIT as DISTRIBUTION_LIMIT
from agents.duration_evidence import valid_observation as valid_duration,required_quotes as duration_quotes
from agents.june_evidence import valid_observation as valid_june,required_quotes as june_quotes


def document_scope(request):
    explicit=request.get('document_scope')
    if explicit is not None:
        if explicit not in SOURCES: raise ValueError('Unapproved document scope')
        return explicit
    mentioned=[source for source in SOURCES if source.lower() in request['objective'].lower()]
    return mentioned[0] if len(mentioned)==1 else None


def substantive_quote(quote):
    text=quote.strip()
    return not text.startswith(('Source:','#')) and any(character.isalnum() for character in text) and len(text.split())>=4


def report_evidence(run):
    return [{'id':step['id'],'text':step['observation']['evidence_text']} for step in run['steps']
            if step['state']=='completed' and step.get('observation',{}).get('available')]


def collect_claims(raw,evidence):
    if not isinstance(raw,dict) or set(raw)!={'claims'} or not isinstance(raw['claims'],list) or len(raw['claims'])>3:
        raise RuntimeError('Invalid report structure')
    accepted,rejected,seen=[],0,set()
    for claim in raw['claims']:
        try:
            if not isinstance(claim,dict) or set(claim)!={'text','citation','quote'} or not isinstance(claim['text'],str) or len(claim['text'])>700:
                raise RuntimeError('Invalid proposed extract')
            # Discard the model's interpretation before validation: only its selected exact quotation is published.
            extract={'text':claim['quote'],'citation':claim['citation'],'quote':claim['quote']}
            validated=validate_claims({'claims':[extract]},evidence)[0]
            if not substantive_quote(validated['quote']): raise RuntimeError('Metadata alone is not a finding')
            # A real citation does not prove a generated paraphrase. Publish the verified extract itself.
            key=(validated['citation'],validated['text'],validated['quote'])
            if key not in seen: accepted.append(validated);seen.add(key)
        except (RuntimeError,TypeError,KeyError): rejected+=1
    return accepted,rejected


def assess_report(run):
    evidence=report_evidence(run)
    available={item['id'] for item in evidence}
    selected={step['tool'] for step in run['steps']}
    invalid=[];cited=set()
    for index,claim in enumerate(run['claims']):
        try:
            validate_claims({'claims':[claim]},evidence)
            if claim['text']!=claim['quote']: raise RuntimeError('Finding must use exact source wording')
            if not substantive_quote(claim['quote']): raise RuntimeError('Metadata alone is not a finding')
            cited.add(claim['citation'])
        except (RuntimeError,TypeError,KeyError): invalid.append(index+1)
    missing=sorted(set(run['request'].get('required_tools',[]))-selected)
    if run['request'].get('route') is not None and 'route_history' not in selected and 'route_history' not in missing:
        missing.append('route_history')
    if run['request'].get('include_model_evidence') and 'model_evidence' not in selected and 'model_evidence' not in missing:
        missing.append('model_evidence')
    if run['request'].get('include_distribution_evidence') and 'distribution_evidence' not in selected and 'distribution_evidence' not in missing:missing.append('distribution_evidence')
    if run['request'].get('include_duration_evidence') and 'duration_evidence' not in selected and 'duration_evidence' not in missing:missing.append('duration_evidence')
    if run['request'].get('include_june_evidence') and 'june_evidence' not in selected and 'june_evidence' not in missing:missing.append('june_evidence')
    failed=[s['id'] for s in run['steps'] if s['state']!='completed']
    unavailable=[s['id'] for s in run['steps'] if s['state']=='completed' and not s.get('observation',{}).get('available')]
    uncited=[item['id'] for item in evidence if item['id'] not in cited]
    scope=document_scope(run['request'])
    mismatches=[s['id'] for s in run['steps'] if s['tool']=='knowledge_search' and scope is not None
        and any(row['source']!=scope for row in s.get('observation',{}).get('evidence',[]))]
    route_mismatches=[s['id'] for s in run['steps'] if s['tool']=='route_history' and s['state']=='completed'
        and s.get('observation',{}).get('available') and (s.get('arguments')!=run['request'].get('route') or s['observation'].get('scope')!=run['request'].get('route')
            or not valid_saved_profile(s['observation'].get('profile'),run['request'].get('route')))]
    model_mismatches=[s['id'] for s in run['steps'] if s['tool']=='model_evidence' and s['state']=='completed'
        and s.get('observation',{}).get('available') and (run['request'].get('include_model_evidence') is not True
            or s.get('arguments')!={} or not valid_observation(s['observation']))]
    model_limits=[s['id'] for s in run['steps'] if s['tool']=='model_evidence' and s['state']=='completed'
        and s.get('observation',{}).get('available') and not any(c.get('citation')==s['id']
            and 'Input reliance is not causality or an individual-flight explanation.' in c.get('quote','') for c in run['claims'])]
    distribution_mismatches=[s['id'] for s in run['steps'] if s['tool']=='distribution_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        and (run['request'].get('include_distribution_evidence') is not True or s.get('arguments')!={} or not valid_distributions(s['observation']))]
    distribution_limits=[s['id'] for s in run['steps'] if s['tool']=='distribution_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        and not any(c.get('citation')==s['id'] and DISTRIBUTION_LIMIT in c.get('quote','') for c in run['claims'])]
    duration_mismatches=[s['id'] for s in run['steps'] if s['tool']=='duration_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        and (run['request'].get('include_duration_evidence') is not True or s.get('arguments')!={} or not valid_duration(s['observation']))]
    duration_missing=[s['id']+':'+label for s in run['steps'] if s['tool']=='duration_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        for label,quote in duration_quotes(s['observation']).items() if not quote or not any(c.get('citation')==s['id'] and quote in c.get('quote','') for c in run['claims'])]
    duration_limits=sorted({item.split(':')[0] for item in duration_missing})
    june_mismatches=[s['id'] for s in run['steps'] if s['tool']=='june_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        and (run['request'].get('include_june_evidence') is not True or s.get('arguments')!={} or not valid_june(s['observation']))]
    june_missing=[s['id']+':'+label for s in run['steps'] if s['tool']=='june_evidence' and s['state']=='completed' and s.get('observation',{}).get('available')
        for label,quote in june_quotes(s['observation']).items() if not quote or not any(c.get('citation')==s['id'] and quote in c.get('quote','') for c in run['claims'])]
    june_limits=sorted({item.split(':')[0] for item in june_missing})
    passed=bool(available and run['claims']) and not (missing or failed or unavailable or uncited or invalid or mismatches or route_mismatches or model_mismatches or model_limits or distribution_mismatches or distribution_limits or duration_mismatches or duration_limits or june_mismatches or june_limits)
    return {'version':'research-coverage-v1','passed':passed,'required_tools':run['request'].get('required_tools',[]),
        'missing_tools':missing,'failed_steps':failed,'unavailable_steps':unavailable,'uncited_tools':uncited,
        'invalid_claims':invalid,'covered_sources':len(available&cited),'available_sources':len(available),
        'document_scope':scope,'document_scope_mismatches':mismatches,
        'route_scope_mismatches':route_mismatches,'model_evidence_mismatches':model_mismatches,'model_limitations_uncited':model_limits,
        'distribution_evidence_mismatches':distribution_mismatches,'distribution_limitations_uncited':distribution_limits,
        'duration_evidence_mismatches':duration_mismatches,'duration_quotes_uncited':duration_limits,'duration_required_quotes_missing':duration_missing,
        'june_evidence_mismatches':june_mismatches,'june_quotes_uncited':june_limits,'june_required_quotes_missing':june_missing,
        'finding_style':'verbatim_source_extracts','semantic_entailment_verified':False,'all_objective_parts_verified':False,
        'meaning':'Checks explicit tool requirements, successful evidence coverage and citation/number integrity; human semantic review is still required.'}
