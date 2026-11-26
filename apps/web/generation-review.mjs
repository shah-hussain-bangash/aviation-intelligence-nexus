// This offline page only collects declarations. Python performs authoritative assessment.
export function reviewSnapshot(initial, edits) {
  const result = structuredClone(initial);
  if (typeof edits.reviewer_label !== 'string' || edits.reviewer_label.length > 80) throw Error('Invalid reviewer label');
  if (!Array.isArray(edits.cases) || edits.cases.length !== initial.cases.length) throw Error('Case inventory changed');
  result.reviewer_label = edits.reviewer_label;
  for (let i = 0; i < initial.cases.length; i++) {
    const base = initial.cases[i], row = edits.cases[i], out = result.cases[i];
    if (row.id !== base.id || row.case_sha256 !== base.case_sha256 || typeof row.source_checked !== 'boolean' || typeof row.notes !== 'string' || row.notes.length > 2000) throw Error('Invalid case review');
    out.source_checked = row.source_checked; out.notes = row.notes;
    for (const key of ['question_answered', 'abstention_appropriate']) {
      if (base[key] === 'uncertain' ? !['yes', 'no', 'uncertain'].includes(row[key]) : row[key] !== base[key]) throw Error('Invalid decision rating');
      out[key] = row[key];
    }
    if (!Array.isArray(row.claims) || row.claims.length !== base.claims.length) throw Error('Claim inventory changed');
    for (let j = 0; j < base.claims.length; j++) {
      const claim = row.claims[j], original = base.claims[j];
      if (claim.claim_index !== original.claim_index || claim.citation !== original.citation) throw Error('Claim binding changed');
      for (const key of ['supported', 'relevant']) {
        if (!['yes', 'no', 'uncertain'].includes(claim[key])) throw Error('Invalid claim rating');
        out.claims[j][key] = claim[key];
      }
    }
  }
  return result;
}

export function reviewProgress(annotations) {
  const counts = { pending: 0, declared: 0, not_evaluable: 0 };
  for (const row of annotations.cases) {
    if (row.question_answered === 'not_evaluable') { counts.not_evaluable++; continue; }
    const values = [row.question_answered, row.abstention_appropriate, ...row.claims.flatMap(c => [c.supported, c.relevant])];
    counts[annotations.reviewer_label.trim() && row.source_checked && !values.includes('uncertain') ? 'declared' : 'pending']++;
  }
  return counts;
}

export function mountGenerationReview(root, packet, initial, seed = initial, seedHash = null) {
  const edits = reviewSnapshot(initial, seed);
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const mast = node('header', undefined, 'mast');
  mast.append(node('div', 'AIN. / RESEARCH ASSURANCE', 'eyebrow'), node('h1', 'Every answer. Every source.'),
    node('p', 'Read the evidence. Record your judgment. Keep the original answer intact.', 'intro'));
  root.append(mast);
  const layout = node('main', undefined, 'layout'), sidebar = node('aside', undefined, 'sidebar'), content = node('section', undefined, 'content');
  layout.append(sidebar, content); root.append(layout);
  sidebar.append(node('p', 'GENERATION REVIEW', 'eyebrow'), node('h2', 'Your review desk'));
  const progress = node('p', '', 'progress'); progress.setAttribute('role', 'status');
  const update = () => {
    const counts = reviewProgress(reviewSnapshot(initial, edits));
    progress.textContent = `${counts.pending} pending · ${counts.declared} declared · ${counts.not_evaluable} unavailable`;
  };
  sidebar.append(progress);
  const label = node('label', 'Reviewer label'), reviewer = node('input');
  reviewer.maxLength = 80; reviewer.placeholder = 'Enter your name or review label'; reviewer.autocomplete = 'off';
  reviewer.value = edits.reviewer_label;
  reviewer.addEventListener('input', () => { edits.reviewer_label = reviewer.value; update(); });
  label.append(reviewer); sidebar.append(label);
  sidebar.append(node('p', 'Unsigned self-review. Your identity is not verified. These declarations do not approve airline operations.', 'notice'));
  const download = node('button', 'Download review JSON', 'primary'); download.type = 'button';
  const message = node('p', (seedHash ? 'Resumed from the supplied review file. ' : '') + 'Download new changes before closing. Refresh restores this page’s starting entries.', 'small'); message.setAttribute('role', 'status');
  download.addEventListener('click', () => {
    try {
      const annotations = reviewSnapshot(initial, edits);
      const blob = new Blob([JSON.stringify(annotations, null, 2) + '\n'], { type: 'application/json' });
      const url = URL.createObjectURL(blob), link = node('a');
      link.href = url; link.download = 'annotations.review.json'; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message.textContent = 'Download requested. Run the Python assessment command to verify this file against the packet.';
    } catch { message.textContent = 'Review could not be exported. Check the label, notes and ratings.'; }
  });
  sidebar.append(download, message);
  const provenance = node('details'); provenance.append(node('summary', 'Packet & model identity'));
  provenance.append(node('p', `Packet SHA-256: ${initial.packet_sha256}`, 'mono'), node('p', `Report SHA-256: ${packet.report_sha256}`, 'mono'),
    node('p', `Generator: ${packet.report.generation_model}`), node('p', packet.report.generation_digest, 'mono'));
  if (seedHash) provenance.append(node('p', `Starting review file SHA-256: ${seedHash}`, 'mono'),
    node('p', 'File binding verified when this page was built. Reviewer identity and semantic correctness are not verified.', 'small'));
  sidebar.append(provenance);
  content.append(node('p', 'LOCAL FILE · NO UPLOADS · NO AUTOMATIC RATINGS', 'eyebrow'), node('h2', 'Review the saved diagnostic cases'),
    node('p', 'Support checks whether the cited context justifies the claim. Relevance checks whether the claim helps answer the question. Unavailable runs cannot receive answer-quality credit.', 'guidance'));
  const select = (title, value, change) => {
    const wrapper = node('label', title), control = node('select');
    for (const [key, text] of [['uncertain', 'Not assessed / uncertain'], ['yes', 'Yes'], ['no', 'No']]) {
      const option = node('option', text); option.value = key; control.append(option);
    }
    control.value = value; control.addEventListener('change', () => { change(control.value); update(); }); wrapper.append(control); return wrapper;
  };
  packet.report.cases.forEach((item, index) => {
    const row = edits.cases[index], card = node('article', undefined, 'case');
    card.append(node('p', `${String(index + 1).padStart(2, '0')} / ${item.id} · ${item.outcome.replaceAll('_', ' ')}`, 'case-meta'), node('h3', item.question));
    for (let i = 0; i < item.claims.length; i++) {
      const claim = item.claims[i], box = node('section', undefined, 'claim');
      box.append(node('p', `CLAIM ${i + 1}`, 'eyebrow'), node('p', claim.text, 'answer'), node('blockquote', claim.quote),
        node('p', `${claim.source} · lines ${claim.start_line}–${claim.end_line} · ${claim.citation}`, 'mono'));
      const fields = node('div', undefined, 'fields');
      fields.append(select('Supported by the cited evidence?', row.claims[i].supported, value => { row.claims[i].supported = value; }),
        select('Relevant to the question?', row.claims[i].relevant, value => { row.claims[i].relevant = value; }));
      box.append(fields); card.append(box);
    }
    const evidence = node('details'); evidence.append(node('summary', `Read retrieved evidence (${packet.reviews[index].evidence.length})`));
    for (const passage of packet.reviews[index].evidence) evidence.append(node('p', `${passage.source} · lines ${passage.start_line}–${passage.end_line} · ${passage.id}`, 'mono'), node('pre', passage.text));
    card.append(evidence);
    if (row.question_answered === 'not_evaluable') {
      card.append(node('p', 'Unavailable / rejected. Retained for transparency; no answer-quality rating is allowed.', 'notice'));
    } else {
      const checked = node('label', undefined, 'checkbox'), input = node('input'); input.type = 'checkbox';
      input.checked = row.source_checked;
      input.addEventListener('change', () => { row.source_checked = input.checked; update(); });
      checked.append(input, document.createTextNode(' I have checked the source context for this case.')); card.append(checked);
      if (initial.cases[index].question_answered === 'uncertain') card.append(select('Does the answer address the question?', row.question_answered, value => { row.question_answered = value; }));
      else card.append(select('Was abstaining appropriate?', row.abstention_appropriate, value => { row.abstention_appropriate = value; }));
    }
    const notesLabel = node('label', 'Reviewer notes (optional)'), notes = node('textarea'); notes.maxLength = 2000; notes.rows = 2;
    notes.value = row.notes;
    notes.addEventListener('input', () => { row.notes = notes.value; }); notesLabel.append(notes); card.append(notesLabel); content.append(card);
  });
  const corpus = node('details', undefined, 'case'); corpus.append(node('summary', 'Read the six full source documents'));
  for (const document of packet.documents) corpus.append(node('h3', document.path), node('p', document.sha256, 'mono'), node('pre', document.text));
  content.append(corpus); update();
}
