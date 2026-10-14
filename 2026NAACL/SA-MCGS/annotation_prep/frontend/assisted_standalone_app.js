/* Added to the offline page before bootstrap; the original blind UI stays intact. */
const HINT_MODELS = ['gpt-4o', 'gemini-2.5-pro'];
const HINT_METHODS = ['lea', 'sa-mcgs'];
const HINT_MODEL_LABELS = { 'gpt-4o': 'GPT-4o', 'gemini-2.5-pro': 'Gemini 2.5 Pro' };
const HINT_METHOD_LABELS = { lea: 'LEA', 'sa-mcgs': 'SA-MCGS' };
const LEGACY_STORE_PREFIX = 'sa_mcgs_blind_expert_audit_v2';
state.hints = null;
state.hintsVisible = true;
state.progressOrigin = 'new_assisted_session';
state.hintPackHistory = [];

function validateHints(manifest, hints) {
  if (!hints || hints.schema_version !== 'assisted_method_hints.v1'
    || hints.annotation_mode !== 'method_assisted_review'
    || hints.source_manifest_hash !== manifest.manifest_hash
    || !/^sha256:[a-f0-9]{64}$/.test(hints.hint_pack_hash || '')) {
    throw new Error('算法提示与当前材料版本不一致。');
  }
  if (Object.keys(hints.cases || {}).length !== manifest.cases.length) {
    throw new Error('算法提示样本数量不一致。');
  }
  if (hints.previous_hint_pack_hashes !== undefined && (!Array.isArray(hints.previous_hint_pack_hashes)
    || hints.previous_hint_pack_hashes.some((hash) => !/^sha256:[a-f0-9]{64}$/.test(hash)))) {
    throw new Error('历史提示版本列表无效。');
  }
  for (const item of manifest.cases) {
    const entry = hints.cases[item.presentation_id];
    if (!entry || !['pre', 'post'].includes(entry.condition) || entry.identity_verified !== true
      || Object.keys(entry.sections || {}).length !== item.sections.length) {
      throw new Error(`样本 ${item.presentation_id} 的提示身份校验失败。`);
    }
    for (const section of item.sections) {
      for (const method of HINT_METHODS) {
        for (const model of HINT_MODELS) {
          const hint = entry.sections[section.section_id]?.methods?.[method]?.models?.[model];
          if (!hint || !['available', 'strict_invalid', 'missing', 'not_run'].includes(hint.status)) {
            throw new Error(`样本 ${item.presentation_id} 的段落提示不完整或身份不符。`);
          }
          if (hint.status === 'available' && (typeof hint.selected !== 'boolean'
            || (hint.score != null && !Number.isFinite(hint.score))
            || (hint.rank != null && (!Number.isInteger(hint.rank) || hint.rank < 1
              || !Number.isInteger(hint.total_nodes) || hint.rank > hint.total_nodes)))) {
            throw new Error('算法提示的分数、排名或选择状态无效。');
          }
        }
      }
    }
  }
  return hints;
}

function initializeAssistedHints(manifest = state.manifest) {
  state.hints = validateHints(manifest, readEmbeddedJson('methodHintsData'));
  state.hintPackHistory = [state.hints.hint_pack_hash];
  return state.hints;
}

function mergedHintHistory(history = [], sourceHash = state.hints.hint_pack_hash) {
  const allowed = new Set([state.hints.hint_pack_hash, ...(state.hints.previous_hint_pack_hashes || [])]);
  if (!Array.isArray(history) || history.some((hash) => !allowed.has(hash)) || !allowed.has(sourceHash)) {
    throw new Error('进度包含未经核验的提示版本。');
  }
  return [...new Set([...history, sourceHash, state.hints.hint_pack_hash])];
}

const validateBlindData = validateData;
validateData = function validateAssistedData(manifest, translations) {
  const result = validateBlindData(manifest, translations);
  initializeAssistedHints(manifest);
  return result;
};

function renderModelHint(model, hint) {
  const label = esc(HINT_MODEL_LABELS[model] || model);
  if (!hint || hint.status !== 'available') {
    const reason = hint?.reason_zh || (hint?.status === 'strict_invalid'
      ? '旧输出未通过严格校验' : '该快照没有可用输出');
    return `<div class="model-hint unavailable"><div class="hint-model-row"><strong>${label}</strong>
      <span class="selection-chip">暂无可靠提示</span></div>
      <div class="hint-metrics">${esc(reason)}；不代表无风险。</div></div>`;
  }
  const metrics = [];
  metrics.push(hint.score == null ? '未提供分数' : `风险相关分 ${hint.score.toFixed(3)}（非概率）`);
  if (hint.rank != null) metrics.push(`排名 ${hint.rank} / ${hint.total_nodes}`);
  if (hint.top3 === true) metrics.push('前 3 名');
  return `<div class="model-hint ${hint.selected ? 'selected' : 'not-selected'}">
    <div class="hint-model-row"><strong>${label}</strong><span class="selection-chip">${hint.selected ? '已纳入结果子图' : '未纳入结果子图'}</span></div>
    <div class="hint-metrics">${metrics.map(esc).join(' · ')}</div></div>`;
}

function renderAlgorithmHints(item, section) {
  const entry = state.hints.cases[item.presentation_id].sections[section.section_id];
  return `<aside class="algorithm-hints" aria-label="本段算法提示" ${state.hintsVisible ? '' : 'hidden'}>
    <div class="heading">本段算法提示 <span>供参考，不是标准答案</span></div>
    <div class="method-grid">${HINT_METHODS.map((method) => `<section class="method-hint-card">
      <h5>${HINT_METHOD_LABELS[method]}</h5>
      ${HINT_MODELS.map((model) => renderModelHint(model, entry.methods[method].models[model])).join('')}
    </section>`).join('')}</div></aside>`;
}

const renderBlindParagraph = renderParagraph;
renderParagraph = function renderAssistedParagraph(item, section, index) {
  const html = renderBlindParagraph(item, section, index);
  const marker = '</details>\n    </div>\n    <div class="paragraph-form">';
  if (!html.includes(marker)) throw new Error('段落提示插入位置发生变化。');
  return html.replace(marker, `</details>${renderAlgorithmHints(item, section)}\n    </div>\n    <div class="paragraph-form">`);
};

function updateAssistedControls() {
  const toggle = $('toggleHintsBtn');
  if (toggle) {
    toggle.textContent = state.hintsVisible ? '隐藏算法提示' : '显示算法提示';
    toggle.setAttribute('aria-pressed', String(state.hintsVisible));
    toggle.onclick = toggleHints;
  }
  const notice = $('migrationNotice');
  if (notice) {
    const hintsUpdated = state.progressOrigin.startsWith('copied_from_assisted_hint_update');
    notice.hidden = !hintsUpdated && !state.progressOrigin.startsWith('copied_from_blind');
    notice.textContent = hintsUpdated
      ? '已接续更新前的标注进度；原记录保留，导出会记录新旧提示版本。'
      : '已复制原页面进度；原盲版记录未改动。本页后续保存和导出均标记为辅助复核。';
  }
}

const renderBlindWorkspace = renderWorkspace;
renderWorkspace = function renderAssistedWorkspace() {
  renderBlindWorkspace();
  const item = currentCase();
  const meta = $('workspace')?.querySelector('.case-meta');
  if (item && meta) {
    const condition = state.hints.cases[item.presentation_id].condition;
    meta.insertAdjacentHTML('beforeend', `<span class="pill sample-condition">${condition === 'pre' ? '未注入 · 原始材料' : '注入后 · 变体材料'}</span>`);
  }
  updateAssistedControls();
};

function toggleHints() {
  captureCurrentForm();
  state.hintsVisible = !state.hintsVisible;
  saveState('提示显示已切换；仍为辅助复核模式');
  // Do not rebuild the form: preserve focus, expanded original text and scroll position.
  $('workspace')?.querySelectorAll('.algorithm-hints').forEach((panel) => { panel.hidden = !state.hintsVisible; });
  updateAssistedControls();
}

const originalStoreKey = storeKey;
storeKey = function assistedStoreKey() {
  return `${originalStoreKey()}:${state.hints.hint_pack_hash}`;
};

const loadBlindStoredState = loadStoredState;
loadStoredState = function loadAssistedStoredState() {
  if (!state.hints) initializeAssistedHints();
  try {
    let stored = JSON.parse(localStorage.getItem(storeKey()) || 'null');
    if (!stored) {
      // Same frozen material, newer verified hints: copy progress, never overwrite its old key.
      for (const priorHash of state.hints.previous_hint_pack_hashes || []) {
        const priorKey = `${originalStoreKey()}:${priorHash}`;
        const prior = JSON.parse(localStorage.getItem(priorKey) || 'null');
        if (!prior) continue;
        if (prior.schema_version !== STATE_SCHEMA || prior.annotation_mode !== 'method_assisted_review'
          || prior.study_id !== state.manifest.study_id || prior.manifest_hash !== state.manifest.manifest_hash
          || prior.translation_pack_hash !== state.translations.translation_pack_hash || prior.hint_pack_hash !== priorHash) {
          throw new Error('旧辅助页进度不匹配，未自动复制。');
        }
        validateOrderMap(prior.orders);
        validateAnnotationMap(prior.annotations || {});
        stored = {
          ...prior, hint_pack_hash: state.hints.hint_pack_hash,
          hint_pack_history: mergedHintHistory(prior.hint_pack_history || [], priorHash),
          progress_origin: `copied_from_assisted_hint_update:${prior.progress_origin || 'assisted'}`,
        };
        localStorage.setItem(storeKey(), JSON.stringify(stored));
        break;
      }
    }
    if (!stored) {
      const legacyKey = `${LEGACY_STORE_PREFIX}:${state.manifest.study_id}:${state.manifest.manifest_hash}`;
      const legacy = JSON.parse(localStorage.getItem(legacyKey) || 'null');
      if (legacy) {
        if (legacy.schema_version !== 'blind_annotation.state.v2'
          || legacy.annotation_mode !== 'blind_human_audit'
          || legacy.study_id !== state.manifest.study_id
          || legacy.manifest_hash !== state.manifest.manifest_hash
          || (legacy.translation_pack_hash && legacy.translation_pack_hash !== state.translations.translation_pack_hash)) {
          throw new Error('旧进度不匹配，未自动复制；请保留原备份。');
        }
        validateOrderMap(legacy.orders);
        validateAnnotationMap(legacy.annotations || {});
        stored = {
          ...legacy, schema_version: STATE_SCHEMA, annotation_mode: 'method_assisted_review',
          hint_pack_hash: state.hints.hint_pack_hash, hints_visible: true,
          hint_pack_history: [state.hints.hint_pack_hash],
          progress_origin: 'copied_from_blind_local_storage',
        };
        // Copy only: never delete or overwrite the original blind storage key.
        localStorage.setItem(storeKey(), JSON.stringify(stored));
      }
    }
    if (stored) {
      if (stored.schema_version !== STATE_SCHEMA || stored.study_id !== state.manifest.study_id
        || stored.manifest_hash !== state.manifest.manifest_hash
        || stored.annotation_mode !== 'method_assisted_review' || stored.hint_pack_hash !== state.hints.hint_pack_hash
        || (stored.translation_pack_hash && stored.translation_pack_hash !== state.translations.translation_pack_hash)) {
        throw new Error('已保存进度的提示版本不匹配。');
      }
      validateOrderMap(stored.orders);
      validateAnnotationMap(stored.annotations || {});
      state.progressOrigin = stored.progress_origin || 'assisted_local_storage';
      state.hintsVisible = stored.hints_visible !== false;
      state.hintPackHistory = mergedHintHistory(stored.hint_pack_history || [], stored.hint_pack_hash);
    }
  } catch (error) {
    // Fail closed: bootstrap must not overwrite an unreadable existing progress record.
    throw new Error(`未覆盖已有进度：${error.message}`);
  }
  loadBlindStoredState();
};

const buildBlindExportRows = buildExportRows;
buildExportRows = function buildAssistedExportRows(expertId = state.activeExpert) {
  const rows = buildBlindExportRows(expertId);
  for (const row of [...rows.caseRows, ...rows.sectionRows]) {
    Object.assign(row, {
      标注模式: '带算法提示的辅助复核', annotation_mode: 'method_assisted_review',
      hint_pack_hash: state.hints.hint_pack_hash, hints_visible: state.hintsVisible,
      hint_pack_history: state.hintPackHistory.join(';'),
      progress_origin: state.progressOrigin,
    });
  }
  return rows;
};

const blindExportFilename = exportFilename;
exportFilename = function assistedExportFilename(kind, incomplete, extension) {
  return blindExportFilename(`辅助复核_${kind}`, incomplete, extension);
};

const restoreBlindBackup = restoreBackup;
restoreBackup = async function restoreAssistedBackup(raw) {
  let normalized = raw;
  if (raw?.schema_version === 'blind_annotation.export.v2' && raw.annotation_mode === 'blind_human_audit') {
    normalized = {
      ...raw, schema_version: EXPORT_SCHEMA, annotation_mode: 'method_assisted_review',
      hint_pack_hash: state.hints.hint_pack_hash, progress_origin: 'copied_from_blind_json_backup',
      hint_pack_history: [state.hints.hint_pack_hash],
    };
  } else if (raw?.annotation_mode !== 'method_assisted_review'
    || ![state.hints.hint_pack_hash, ...(state.hints.previous_hint_pack_hashes || [])].includes(raw.hint_pack_hash)) {
    throw new Error('备份的辅助复核模式或提示版本不匹配。');
  } else {
    normalized = {
      ...raw, hint_pack_hash: state.hints.hint_pack_hash,
      hint_pack_history: mergedHintHistory(raw.hint_pack_history || [], raw.hint_pack_hash),
      progress_origin: raw.hint_pack_hash === state.hints.hint_pack_hash ? raw.progress_origin
        : `copied_from_assisted_hint_update:${raw.progress_origin || 'assisted_json_backup'}`,
    };
  }
  await restoreBlindBackup(normalized);
};
