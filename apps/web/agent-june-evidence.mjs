import {validateJune,renderJune} from './june-evaluation.mjs';
export const JUNE_LIMIT='This frozen later-month US comparison does not establish a globally untouched holdout, statistical significance, causality, UAE validation or operational approval. No refit, threshold change, new inference or deployment is performed by this tool.';
export function juneEvidenceText(r){
 validateJune(r);const m=r.model,b=r.constant_training_prior,u=r.uncertainty,ll=u.statistics.mean_log_loss_difference_model_minus_prior,bs=u.statistics.mean_brier_difference_model_minus_prior,f=v=>v.toFixed(6);
 return [`June 2025: ${m.records} eligible flights; frozen-model ROC-AUC ${f(m.roc_auc)}; log loss ${f(m.log_loss)} versus training-prior baseline ${f(b.log_loss)}; Brier score ${f(m.brier_score)} versus baseline ${f(b.brier_score)}.`,
 `Descriptive uncertainty: ${u.replicates} seeded resamples of ${u.date_clusters} complete flight-date clusters; model-minus-prior 95% percentile intervals are [${f(ll.lower)}, ${f(ll.upper)}] for mean log loss and [${f(bs.lower)}, ${f(bs.upper)}] for mean Brier score; negative differences favour the model.`,JUNE_LIMIT,
 `The fixed decision threshold is ${r.frozen_threshold.toFixed(2)}; report fingerprint ${r.report_sha256}. The monthly SQL selector and January-May prediction window are unchanged.`].join('\n');
}
export function validateJuneSnapshot(observation){
 const s=observation?.snapshot;
 if(observation?.data_kind!=='recorded_june_evaluation'||observation.available!==true||s?.format!=='ain-agent-june-v1'||s.research_only!==true||s.production_ready!==false)throw new Error('Invalid saved June scope');
 validateJune(s.evaluation);if(observation.evidence_text!==juneEvidenceText(s.evaluation))throw new Error('Changed June source wording');return s;
}
export function renderJuneSnapshot(observation){
 const s=validateJuneSnapshot(observation);
 return `<span class="research-badge">Recorded June comparison · Saved tool evidence</span><h4>June evaluation retained with this investigation</h4><p>This structured snapshot is separate from the agent's selected source extracts. It reads the frozen report and does not run inference. The June cohort is independent of the investigation's optional monthly SQL selector.</p>${renderJune(s.evaluation)}`;
}
