/* Protocol isolation and exports for the simplified two-choice form. */
const ANNOTATION_PROTOCOL = 'binary_judgment_v1';
state.formProtocol = ANNOTATION_PROTOCOL;

function binaryScoringEligibility(annotation) {
  if (annotation.annotation_protocol !== ANNOTATION_PROTOCOL) return 'legacy_pending_review';
  if (annotation.sets_reviewed !== true
    || !['present', 'absent'].includes(annotation.target_conflict)
    || !['yes', 'no'].includes(annotation.judgment_sufficient)) return 'pending';
  if (!['1', '2', '3', '4', '5'].includes(String(annotation.confidence || ''))) return 'pending';
  const sections = Object.values(annotation.sections || {});
  if (!sections.length || sections.some((section) => typeof section.minimal_evidence !== 'boolean'
    || typeof section.repair_packet !== 'boolean' || (section.minimal_evidence && !section.repair_packet))) return 'pending';
  const hasEvidence = sections.some((section) => section.minimal_evidence);
  if (annotation.target_conflict === 'absent' && hasEvidence) return 'pending';
  if (annotation.target_conflict === 'present' && annotation.judgment_sufficient === 'yes' && !hasEvidence) return 'pending';
  if (annotation.judgment_sufficient === 'no') return 'insufficient';
  return annotation.target_conflict === 'present' ? 'positive' : 'negative';
}

const hintVersionStoreKey = storeKey;
storeKey = function binaryStoreKey() {
  return `${hintVersionStoreKey()}:${ANNOTATION_PROTOCOL}`;
};

const loadAssistedVersionState = loadStoredState;
loadStoredState = function loadBinaryProtocolState() {
  if (!state.hints) initializeAssistedHints();
  if (!localStorage.getItem(storeKey())) {
    const baseKey = originalStoreKey();
    const previous = state.hints.previous_hint_pack_hashes || [];
    // Prefer progress already reviewed under this protocol over older form versions.
    const candidates = [
      ...previous.map((hash) => ({ hash, key: `${baseKey}:${hash}:${ANNOTATION_PROTOCOL}` })),
      { hash: state.hints.hint_pack_hash, key: hintVersionStoreKey() },
      ...previous.map((hash) => ({ hash, key: `${baseKey}:${hash}` })),
    ];
    for (const candidate of candidates) {
      const raw = localStorage.getItem(candidate.key);
      if (!raw) continue;
      const prior = JSON.parse(raw);
      if (prior.schema_version !== STATE_SCHEMA || prior.annotation_mode !== 'method_assisted_review'
        || prior.study_id !== state.manifest.study_id || prior.manifest_hash !== state.manifest.manifest_hash
        || prior.translation_pack_hash !== state.translations.translation_pack_hash
        || prior.hint_pack_hash !== candidate.hash
        || (prior.annotation_protocol && prior.annotation_protocol !== ANNOTATION_PROTOCOL)) {
        throw new Error('原页面进度版本不匹配，未覆盖任何已有记录。');
      }
      validateOrderMap(prior.orders);
      validateAnnotationMap(prior.annotations || {});
      const copied = {
        ...prior, annotation_protocol: ANNOTATION_PROTOCOL,
        hint_pack_hash: state.hints.hint_pack_hash,
        hint_pack_history: mergedHintHistory(prior.hint_pack_history || [], candidate.hash),
        progress_origin: `copied_from_assisted_binary_form:${prior.progress_origin || 'assisted'}`,
      };
      // Preserve annotations verbatim. A new form does not imply renewed expert judgments.
      localStorage.setItem(storeKey(), JSON.stringify(copied));
      break;
    }
  }
  const stored = JSON.parse(localStorage.getItem(storeKey()) || 'null');
  if (stored?.annotation_protocol && stored.annotation_protocol !== ANNOTATION_PROTOCOL) {
    throw new Error('当前存档的标注协议不兼容，未覆盖已有记录。');
  }
  loadAssistedVersionState();
};

const updateHintControls = updateAssistedControls;
updateAssistedControls = function updateBinaryControls() {
  updateHintControls();
  const reviewer = $('reviewerId');
  if (reviewer && reviewer.dataset.binaryIdentityBound !== 'true') {
    reviewer.dataset.binaryIdentityBound = 'true';
    reviewer.addEventListener('input', () => {
      state.reviewerIds[state.activeExpert] = reviewer.value.trim();
      saveState('标注者编号已保存');
    });
  }
  if (state.progressOrigin.startsWith('copied_from_assisted_binary_form')) {
    const notice = $('migrationNotice');
    if (notice) {
      notice.hidden = false;
      notice.textContent = '已接续旧版进度，旧记录完整保留。新的“判断充分性”需亲自选择，不会把旧的“部分充分／不适用”自动改写。';
    }
  }
};

const buildAssistedVersionRows = buildExportRows;
buildExportRows = function buildBinaryProtocolRows(expertId = state.activeExpert) {
  const rows = buildAssistedVersionRows(expertId);
  for (const row of rows.caseRows) {
    row.旧版冲突证据充分性 = row.材料充分性;
    row.旧版冲突证据充分性代码 = row.材料充分性代码;
    row.旧版更多上下文判断 = row.是否需要更多上下文;
    row.旧版更多上下文代码 = row.更多上下文代码;
    delete row.材料充分性;
    delete row.材料充分性代码;
    delete row.是否需要更多上下文;
    delete row.更多上下文代码;
  }
  for (const row of [...rows.caseRows, ...rows.sectionRows]) {
    const annotation = annotationFor(row.样本编号, expertId);
    const protocol = annotation.annotation_protocol || 'legacy_annotation';
    Object.assign(row, {
      annotation_protocol: protocol,
      判断充分性: ({ yes: '充分', no: '不充分' })[annotation.judgment_sufficient] || '',
      判断充分性代码: annotation.judgment_sufficient || '',
      judgment_sufficient: annotation.judgment_sufficient || '',
      证据选择已确认: annotation.sets_reviewed === true ? '是' : '否',
      sets_reviewed: annotation.sets_reviewed === true,
      scoring_eligibility: binaryScoringEligibility(annotation),
      旧标签已保留: Boolean(annotation.legacy_annotation),
    });
  }
  return rows;
};

const restoreAssistedVersionBackup = restoreBackup;
restoreBackup = async function restoreBinaryProtocolBackup(raw) {
  if (raw?.annotation_protocol && raw.annotation_protocol !== ANNOTATION_PROTOCOL) {
    throw new Error('备份的标注协议不匹配。');
  }
  await restoreAssistedVersionBackup(raw);
};
