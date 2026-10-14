/* Targeted third-expert annotation with optional method hints and preserved history. */
(() => {
  'use strict';
  const PROTOCOL = 'binary_judgment_v1';
  const REVIEW_PROTOCOL = 'targeted_third_blind_v1';
  const LEGACY_SCHEMA = 'third_expert_blind_export.v1';
  const EXPORT_SCHEMA = 'third_expert_review_export.v2';
  const PAGE_MODE = 'method_assisted_review';
  const HINT_METHODS = ['lea', 'sa-mcgs'];
  const HINT_MODELS = ['gpt-4o', 'gemini-2.5-pro'];
  const HINT_LABELS = { lea: 'LEA', 'sa-mcgs': 'SA-MCGS', 'gpt-4o': 'GPT-4o', 'gemini-2.5-pro': 'Gemini 2.5 Pro' };
  const PROVENANCE_FIELDS = ['annotation_mode', 'hint_pack_hash', 'hints_visible', 'hints_displayed'];
  const INJECTION_FIELDS = ['injection_marker_pack_hash', 'injection_hints_visible', 'injection_hints_displayed'];
  const EXPERT = 'expert_3';
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const state = { annotations: {}, reviewerId: '', activeIndex: 0, filter: 'all', hintsVisible: true, hintsDisplayed: new Set(), injectionHintsDisplayed: new Set() };
  let manifest, translations, hints, injectionMarkers, cases, order, storageKey, writable = true, storageAvailable = true;

  function fail(message) { throw new Error(message); }
  function keysAllowed(value, allowed, label) {
    if (!object(value) || Object.keys(value).some((key) => !allowed.includes(key))) fail(`${label}含未知字段或结构不正确。`);
  }
  function validateData() {
    if (manifest.schema_version !== 'blind_annotation.v1' || manifest.review_protocol !== REVIEW_PROTOCOL
      || manifest.study_id !== 'arr_oct2026_expert_audit_third_review_v1'
      || typeof manifest.manifest_hash !== 'string' || !manifest.manifest_hash
      || typeof manifest.parent_manifest_hash !== 'string' || !manifest.parent_manifest_hash
      || !Array.isArray(manifest.cases) || !manifest.cases.length) fail('样本包版本或内容无效。');
    cases = new Map();
    for (const item of manifest.cases) {
      if (!object(item) || typeof item.presentation_id !== 'string' || !item.presentation_id
        || cases.has(item.presentation_id) || !Array.isArray(item.sections) || !item.sections.length) fail('样本编号重复或材料不完整。');
      const ids = new Set();
      for (const section of item.sections) {
        if (typeof section.section_id !== 'string' || !section.section_id || ids.has(section.section_id)
          || typeof section.text !== 'string' || typeof section.title !== 'string') fail('段落编号或原文无效。');
        ids.add(section.section_id);
        const translated = translations.cases?.[item.presentation_id]?.sections?.[section.section_id];
        if (!translated || typeof translated.text_zh !== 'string' || typeof translated.title_zh !== 'string') fail('中文材料不完整。');
      }
      cases.set(item.presentation_id, item);
    }
    order = manifest.expert_orders?.[EXPERT];
    if (!Array.isArray(order) || order.length !== cases.size || new Set(order).size !== order.length
      || order.some((id) => !cases.has(id))) fail('专家 3 的冻结顺序不完整。');
    if (Object.keys(translations.cases || {}).some((id) => !cases.has(id))) fail('中文材料含当前样本包以外的案例。');
    if (translations.source_manifest_hash !== manifest.manifest_hash
      || typeof translations.translation_pack_hash !== 'string' || !translations.translation_pack_hash) fail('中文材料版本与样本包不匹配。');
    storageKey = `sa-mcgs:third-expert:${manifest.study_id}:${manifest.manifest_hash}:${PROTOCOL}:${EXPERT}`;
    validateHints();
    validateInjectionMarkers();
  }
  function validateHints() {
    if (!hints || hints.schema_version !== 'third_expert_method_hints.v1'
      || hints.annotation_mode !== PAGE_MODE || hints.source_manifest_hash !== manifest.manifest_hash
      || hints.parent_manifest_hash !== manifest.parent_manifest_hash
      || !/^sha256:[a-f0-9]{64}$/.test(hints.hint_pack_hash || '')
      || !/^sha256:[a-f0-9]{64}$/.test(hints.parent_hint_pack_hash || '')
      || !same(hints.methods, HINT_METHODS) || !same(hints.models, HINT_MODELS)
      || !same(Object.keys(hints.cases || {}).sort(), [...cases.keys()].sort())) fail('算法提示与样本包不匹配。');
    for (const item of cases.values()) {
      const entry = hints.cases[item.presentation_id];
      if (entry.identity_verified !== true || !same(Object.keys(entry.sections || {}).sort(), item.sections.map((s) => s.section_id).sort())) fail('算法提示段落身份不匹配。');
      for (const section of item.sections) for (const method of HINT_METHODS) for (const model of HINT_MODELS) {
        const cell = entry.sections[section.section_id]?.methods?.[method]?.models?.[model];
        if (!cell || !['available', 'strict_invalid', 'missing', 'not_run'].includes(cell.status)) fail('算法提示状态无效。');
        if (cell.status === 'available' && (typeof cell.selected !== 'boolean'
          || (cell.score != null && !Number.isFinite(cell.score))
          || (cell.rank != null && (!Number.isInteger(cell.rank) || cell.rank < 1 || cell.total_nodes !== item.sections.length || cell.rank > cell.total_nodes)))) fail('算法分数、排名或选择状态无效。');
      }
    }
  }
  function validateInjectionMarkers() {
    if (!injectionMarkers || injectionMarkers.schema_version !== 'third_expert_injection_markers.v1'
      || injectionMarkers.source_manifest_hash !== manifest.manifest_hash
      || injectionMarkers.parent_manifest_hash !== manifest.parent_manifest_hash
      || !/^sha256:[a-f0-9]{64}$/.test(injectionMarkers.marker_pack_hash || '')
      || !/^sha256:[a-f0-9]{64}$/.test(injectionMarkers.parent_marker_pack_hash || '')
      || !same(Object.keys(injectionMarkers.cases || {}).sort(), [...cases.keys()].sort())) fail('注入提示与当前样本包不匹配。');
    for (const item of cases.values()) {
      const marker = injectionMarkers.cases[item.presentation_id];
      const ids = new Set(item.sections.map((s) => s.section_id));
      if (!['pre', 'post'].includes(marker.condition) || !Array.isArray(marker.modified_section_ids)
        || new Set(marker.modified_section_ids).size !== marker.modified_section_ids.length
        || marker.modified_section_ids.some((id) => !ids.has(id))
        || (marker.condition === 'pre' && marker.modified_section_ids.length !== 0)
        || (marker.condition === 'post' && marker.modified_section_ids.length === 0)) fail('注入状态或注入段落身份无效。');
    }
  }
  function currentProvenance(id) {
    return { annotation_mode: PAGE_MODE, hint_pack_hash: hints.hint_pack_hash,
      hints_visible: state.hintsVisible, hints_displayed: state.hintsDisplayed.has(id),
      injection_marker_pack_hash: injectionMarkers.marker_pack_hash,
      injection_hints_visible: state.hintsVisible, injection_hints_displayed: state.injectionHintsDisplayed.has(id) };
  }
  function originMode(record) { return record.annotation_mode || 'blind_human_audit'; }
  function answerOnly(record) {
    return Object.fromEntries(['reviewer_id', 'target_conflict', 'judgment_sufficient', 'confidence', 'comments', 'sections'].map((key) => [key, record[key]]));
  }
  function currentCase() { return cases.get(order[state.activeIndex]); }
  function blank(item) {
    return { annotation_protocol: PROTOCOL, review_protocol: REVIEW_PROTOCOL, expert_slot: EXPERT,
      reviewer_id: state.reviewerId, target_conflict: '', judgment_sufficient: '', confidence: '', comments: '',
      sections: Object.fromEntries(item.sections.map((s) => [s.section_id, { minimal_evidence: false, repair_packet: false, note: '' }])),
      sets_reviewed: false, saved_at: '', ...currentProvenance(item.presentation_id) };
  }
  function annotation(id) { return state.annotations[id] || blank(cases.get(id)); }
  function caseErrors(record, item, requireConfirmation = true) {
    const errors = [];
    if (!record.reviewer_id?.trim()) errors.push('请填写匿名标注者编号。');
    if (!['present', 'absent'].includes(record.target_conflict)) errors.push('请选择是否存在目标冲突。');
    if (!['yes', 'no'].includes(record.judgment_sufficient)) errors.push('请选择当前材料是否足够支持上述判断。');
    if (!['1', '2', '3', '4', '5'].includes(String(record.confidence))) errors.push('请选择判断信心。');
    if (requireConfirmation && record.sets_reviewed !== true) errors.push('请检查所有段落选择后，点击“确认并保存”。');
    const sections = item.sections.map((s) => record.sections?.[s.section_id]);
    if (sections.some((s) => !s || typeof s.minimal_evidence !== 'boolean' || typeof s.repair_packet !== 'boolean')) errors.push('段落集合记录不完整。');
    if (sections.some((s) => s?.minimal_evidence && !s.repair_packet)) errors.push('最小证据必须同时纳入修复材料。');
    const hasEvidence = sections.some((s) => s?.minimal_evidence);
    if (record.target_conflict === 'present' && record.judgment_sufficient === 'yes' && !hasEvidence) errors.push('判断存在冲突且材料充分时，请选择非空最小证据集。');
    if (record.target_conflict === 'absent' && hasEvidence) errors.push('判断不存在冲突时，不能同时选择用于证明冲突的最小证据。');
    return errors;
  }
  function isComplete(id) { return caseErrors(annotation(id), cases.get(id)).length === 0; }
  function eligibility(id) {
    if (!isComplete(id)) return 'pending';
    const record = annotation(id);
    if (record.judgment_sufficient === 'no') return 'insufficient';
    return record.target_conflict === 'present' ? 'positive' : 'negative';
  }
  function validateRecord(record, item, legacyOrigin = false) {
    keysAllowed(record, ['annotation_protocol', 'review_protocol', 'expert_slot', 'reviewer_id', 'target_conflict',
      'judgment_sufficient', 'confidence', 'comments', 'sections', 'sets_reviewed', 'saved_at', ...PROVENANCE_FIELDS, ...INJECTION_FIELDS], '标注记录');
    if (record.annotation_protocol !== PROTOCOL || record.review_protocol !== REVIEW_PROTOCOL || record.expert_slot !== EXPERT) fail('记录的标注协议或专家编号不匹配。');
    if (typeof record.reviewer_id !== 'string' || record.reviewer_id.length > 40
      || !['', 'present', 'absent'].includes(record.target_conflict)
      || !['', 'yes', 'no'].includes(record.judgment_sufficient)
      || !['', '1', '2', '3', '4', '5'].includes(record.confidence)
      || typeof record.comments !== 'string' || typeof record.saved_at !== 'string'
      || typeof record.sets_reviewed !== 'boolean') fail('记录含无效选项或数据类型。');
    const sectionIds = item.sections.map((s) => s.section_id);
    if (!object(record.sections) || !same(Object.keys(record.sections).sort(), [...sectionIds].sort())) fail('记录含缺失或未知段落编号。');
    for (const section of Object.values(record.sections)) {
      keysAllowed(section, ['minimal_evidence', 'repair_packet', 'note'], '段落记录');
      if (typeof section.minimal_evidence !== 'boolean' || typeof section.repair_packet !== 'boolean'
        || typeof section.note !== 'string' || (section.minimal_evidence && !section.repair_packet)) fail('段落选项类型或集合包含关系无效。');
    }
    if (record.sets_reviewed && caseErrors(record, item).length) fail('备份把未完成或相互矛盾的记录标记为已确认。');
    if (legacyOrigin) {
      if ([...PROVENANCE_FIELDS, ...INJECTION_FIELDS].some((field) => field in record)) fail('历史盲版记录的来源字段不一致。');
    } else if (record.annotation_mode !== PAGE_MODE || record.hint_pack_hash !== hints.hint_pack_hash
      || typeof record.hints_visible !== 'boolean' || typeof record.hints_displayed !== 'boolean'
      || (record.hints_visible && !record.hints_displayed)) fail('记录的算法提示来源不完整或不一致。');
    // Older algorithm-assisted records remain valid without injection-display metadata.
    if (INJECTION_FIELDS.some((field) => field in record)
      && (record.injection_marker_pack_hash !== injectionMarkers.marker_pack_hash
        || typeof record.injection_hints_visible !== 'boolean' || typeof record.injection_hints_displayed !== 'boolean'
        || record.injection_hints_visible !== record.hints_visible
        || (record.injection_hints_visible && !record.injection_hints_displayed)
        || (record.injection_hints_displayed && !record.hints_displayed))) fail('记录的注入提示来源不完整或不一致。');
  }
  function validateBackup(raw) {
    keysAllowed(raw, ['schema_version', 'study_id', 'manifest_hash', 'parent_manifest_hash', 'translation_pack_hash',
      'annotation_mode', 'annotation_protocol', 'review_protocol', 'expert_slot', 'reviewer_id', 'anonymous_reviewer_id',
      'order', 'active_index', 'annotations', 'exported_at', 'hint_pack_hash', 'parent_hint_pack_hash',
      'hints_visible', 'hints_displayed_case_ids', 'legacy_blind_record_ids',
      'injection_marker_pack_hash', 'injection_hints_displayed_case_ids'], '备份');
    const legacy = raw.schema_version === LEGACY_SCHEMA;
    if ((!legacy && raw.schema_version !== EXPORT_SCHEMA) || raw.study_id !== manifest.study_id
      || raw.manifest_hash !== manifest.manifest_hash || raw.parent_manifest_hash !== manifest.parent_manifest_hash
      || raw.translation_pack_hash !== translations.translation_pack_hash || raw.expert_slot !== EXPERT
      || raw.annotation_mode !== (legacy ? 'blind_human_audit' : PAGE_MODE) || raw.annotation_protocol !== PROTOCOL
      || raw.review_protocol !== REVIEW_PROTOCOL) fail('备份与当前页面的样本、专家、盲法模式或协议不匹配。');
    if (!same(raw.order, order) || !Number.isInteger(raw.active_index) || raw.active_index < 0 || raw.active_index >= order.length) fail('备份中的样本顺序或位置无效。');
    if (typeof raw.reviewer_id !== 'string' || raw.reviewer_id.length > 40
      || raw.anonymous_reviewer_id !== raw.reviewer_id || typeof raw.exported_at !== 'string') fail('备份中的标注者信息无效。');
    if (!object(raw.annotations)) fail('备份缺少标注记录。');
    const extraFields = ['hint_pack_hash', 'parent_hint_pack_hash', 'hints_visible', 'hints_displayed_case_ids', 'legacy_blind_record_ids',
      'injection_marker_pack_hash', 'injection_hints_displayed_case_ids'];
    if (legacy && extraFields.some((key) => key in raw)) fail('旧版备份不能含新版提示元数据。');
    if (!legacy) {
      if (raw.hint_pack_hash !== hints.hint_pack_hash || raw.parent_hint_pack_hash !== hints.parent_hint_pack_hash
        || typeof raw.hints_visible !== 'boolean') fail('备份的算法提示版本无效。');
      for (const field of ['hints_displayed_case_ids', 'legacy_blind_record_ids']) {
        if (!Array.isArray(raw[field]) || new Set(raw[field]).size !== raw[field].length || raw[field].some((id) => !cases.has(id))) fail('备份的提示历史或原始记录列表无效。');
      }
      const legacyIds = Object.keys(raw.annotations).filter((id) => raw.annotations[id]?.annotation_mode === undefined).sort();
      if (!same([...raw.legacy_blind_record_ids].sort(), legacyIds)) fail('历史盲版记录列表与答案不一致。');
    }
    const hasInjectionMetadata = 'injection_marker_pack_hash' in raw || 'injection_hints_displayed_case_ids' in raw;
    if (hasInjectionMetadata && (raw.injection_marker_pack_hash !== injectionMarkers.marker_pack_hash
      || !Array.isArray(raw.injection_hints_displayed_case_ids)
      || new Set(raw.injection_hints_displayed_case_ids).size !== raw.injection_hints_displayed_case_ids.length
      || raw.injection_hints_displayed_case_ids.some((id) => !cases.has(id) || !raw.hints_displayed_case_ids.includes(id)))) fail('备份的注入提示版本或显示历史无效。');
    for (const [id, record] of Object.entries(raw.annotations)) {
      if (!cases.has(id)) fail('备份含未知样本编号。');
      validateRecord(record, cases.get(id), legacy || raw.legacy_blind_record_ids.includes(id));
      if (record.reviewer_id !== raw.reviewer_id) fail('备份中标注者编号不一致。');
      if (!legacy && record.hints_displayed && !raw.hints_displayed_case_ids.includes(id)) fail('备份丢失了已记录的提示显示历史。');
      if (record.injection_marker_pack_hash && !hasInjectionMetadata) fail('备份缺少记录所用的注入提示版本。');
      if (record.injection_hints_displayed && !raw.injection_hints_displayed_case_ids.includes(id)) fail('备份丢失了注入提示显示历史。');
    }
    return true;
  }
  function payload() {
    return { schema_version: EXPORT_SCHEMA, study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      parent_manifest_hash: manifest.parent_manifest_hash, translation_pack_hash: translations.translation_pack_hash,
      annotation_mode: PAGE_MODE, annotation_protocol: PROTOCOL, review_protocol: REVIEW_PROTOCOL,
      hint_pack_hash: hints.hint_pack_hash, parent_hint_pack_hash: hints.parent_hint_pack_hash,
      hints_visible: state.hintsVisible, hints_displayed_case_ids: order.filter((id) => state.hintsDisplayed.has(id)),
      injection_marker_pack_hash: injectionMarkers.marker_pack_hash,
      injection_hints_displayed_case_ids: order.filter((id) => state.injectionHintsDisplayed.has(id)),
      legacy_blind_record_ids: order.filter((id) => state.annotations[id] && state.annotations[id].annotation_mode === undefined),
      expert_slot: EXPERT, reviewer_id: state.reviewerId, anonymous_reviewer_id: state.reviewerId,
      order: [...order], active_index: state.activeIndex, annotations: copy(state.annotations), exported_at: new Date().toISOString() };
  }
  function toast(message, error = false) {
    $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').classList.add('show');
    clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').classList.remove('show'), 4500);
  }
  function save(message = '草稿已自动保存') {
    if (!writable) return false;
    if (!storageAvailable) { $('saveStatus').textContent = '浏览器存储不可用；请及时导出进度备份'; $('saveIndicator').classList.add('error'); return false; }
    try { localStorage.setItem(storageKey, JSON.stringify(payload())); $('saveStatus').textContent = message;
      $('saveIndicator').classList.add('saved'); $('saveIndicator').classList.remove('error'); return true;
    } catch (_) { storageAvailable = false; $('saveStatus').textContent = '浏览器保存失败，请导出进度备份'; $('saveIndicator').classList.add('error'); return false; }
  }
  function renderList() {
    const count = order.filter(isComplete).length;
    $('progressText').textContent = `${count} / ${order.length}`;
    $('progressBar').style.width = `${100 * count / order.length}%`;
    $('caseList').innerHTML = order.map((id, index) => {
      const complete = isComplete(id);
      if ((state.filter === 'done' && !complete) || (state.filter === 'open' && complete)) return '';
      return `<button type="button" data-index="${index}" class="${index === state.activeIndex ? 'active ' : ''}${complete ? 'complete' : ''}" aria-current="${index === state.activeIndex ? 'true' : 'false'}">样本 ${index + 1}<small>${complete ? '已确认' : '未完成'}</small></button>`;
    }).join('');
  }
  function renderParagraph(item, section, index, record) {
    const translated = translations.cases[item.presentation_id].sections[section.section_id];
    const answer = record.sections[section.section_id];
    const injected = injectionMarkers.cases[item.presentation_id].modified_section_ids.includes(section.section_id);
    return `<article class="paragraph-card" data-section-id="${esc(section.section_id)}">
      <div class="paragraph-text"><p class="paragraph-number">段落 ${index + 1} <span class="case-id">${esc(section.section_id)}</span>${injected ? `<span class="injection-marker" ${state.hintsVisible ? '' : 'hidden'} title="该段文字相较同源未注入材料被修改；不代表专家已判定存在冲突。">注入段落</span>` : ''}</p>
        ${translated.title_zh ? `<h4 class="paragraph-title">${esc(translated.title_zh)}</h4>` : ''}<div class="paragraph-body">${esc(translated.text_zh)}</div>
        <details class="source-original"><summary>展开核对原文</summary>${section.title ? `<h5>${esc(section.title)}</h5>` : ''}<div>${esc(section.text)}</div></details>
        ${renderAlgorithmHints(item.presentation_id, section.section_id)}
      </div>
      <div class="paragraph-form"><h4>该段应纳入哪些材料？</h4><div class="check-grid">
        <label class="check-option"><input type="checkbox" data-minimal-evidence ${answer.minimal_evidence ? 'checked' : ''}><span><b>纳入最小证据集</b><br>证明目标冲突不可缺少的证据。</span></label>
        <label class="check-option"><input type="checkbox" data-repair-packet ${answer.repair_packet ? 'checked' : ''}><span><b>纳入修复材料</b><br>审阅、解释或提出修复建议时应保留的材料。</span></label>
      </div><p class="set-explanation">最小证据属于修复材料；两项都不选表示不纳入上述集合。不是“风险／安全”二分类。</p>
      <details><summary>补充判断备注（选填）</summary><textarea data-section-note placeholder="可记录判断依据">${esc(answer.note)}</textarea></details></div>
    </article>`;
  }
  function renderAlgorithmHints(id, sid) {
    const cells = hints.cases[id].sections[sid];
    return `<aside class="algorithm-hints" aria-label="本段算法提示" ${state.hintsVisible ? '' : 'hidden'}>
      <div class="heading">本段算法提示 <span>供参考，不是标准答案</span></div>
      <div class="method-grid">${HINT_METHODS.map((method) => `<section class="method-hint-card" data-method="${method}"><h5>${HINT_LABELS[method]}</h5>
        ${HINT_MODELS.map((model) => {
          const cell = cells.methods[method].models[model];
          if (cell.status !== 'available') return `<div class="model-hint unavailable" data-model="${model}"><div class="hint-model-row"><strong>${HINT_LABELS[model]}</strong><span class="selection-chip">暂无可靠提示</span></div><div class="hint-metrics">${cell.status === 'strict_invalid' ? '该份输出未通过严格校验，暂不展示分数或选择结果。' : '该快照没有可用输出。'}不代表无风险。</div></div>`;
          const metrics = [cell.score == null ? '未提供分数' : `风险相关分 ${cell.score.toFixed(3)}（非概率）`];
          if (cell.rank != null) metrics.push(`排名 ${cell.rank} / ${cell.total_nodes}`);
          if (cell.top3 === true) metrics.push('前 3 名');
          return `<div class="model-hint ${cell.selected ? 'selected' : 'not-selected'}" data-model="${model}"><div class="hint-model-row"><strong>${HINT_LABELS[model]}</strong><span class="selection-chip">${cell.selected ? '已纳入结果子图' : '未纳入结果子图'}</span></div><div class="hint-metrics">${metrics.map(esc).join(' · ')}</div></div>`;
        }).join('')}</section>`).join('')}</div></aside>`;
  }
  function updateHintControls() {
    $('toggleHintsBtn').textContent = state.hintsVisible ? '隐藏全部提示' : '显示全部提示';
    $('toggleHintsBtn').setAttribute('aria-pressed', String(state.hintsVisible));
    $('hintModeBadge').textContent = state.hintsVisible ? '专家 3 · 算法与注入提示已显示' : '专家 3 · 算法与注入提示已隐藏';
  }
  function noteHintDisplay() {
    const id = currentCase().presentation_id;
    if (!state.hintsVisible || (state.hintsDisplayed.has(id) && state.injectionHintsDisplayed.has(id))) return;
    state.hintsDisplayed.add(id); state.injectionHintsDisplayed.add(id);
    save('提示显示状态已记录；已有答案未改动');
  }
  function toggleHints() {
    state.hintsVisible = !state.hintsVisible;
    $('workspace').querySelectorAll('.algorithm-hints, .sample-condition, .injection-marker').forEach((panel) => { panel.hidden = !state.hintsVisible; });
    updateHintControls(); noteHintDisplay(); save('提示显示状态已保存；已有答案未改动');
  }
  function renderWorkspace() {
    noteHintDisplay(); updateHintControls();
    const item = currentCase(); const record = annotation(item.presentation_id);
    const checked = (name, value) => record[name] === value ? 'checked' : '';
    $('workspace').innerHTML = `<header class="case-header"><p class="eyebrow">标注材料 ${state.activeIndex + 1} / ${order.length}</p>
      <h2>样本 ${state.activeIndex + 1}</h2><p class="blind-notice">下列段落来自同一文档图中的循环关联区域。请判断其中是否存在无法同时成立的要求或记录，并选择证明及审阅问题所需的材料。</p>
      <div class="case-meta"><span class="pill">${esc(item.domain_label)}</span><span class="pill">${item.sections.length} 个段落</span><span class="pill case-id">${esc(item.presentation_id)}</span><span class="pill sample-condition" ${state.hintsVisible ? '' : 'hidden'}>${injectionMarkers.cases[item.presentation_id].condition === 'pre' ? '未注入 · 原始材料' : '已注入 · 注入后变体材料'}</span></div></header>
      <div class="instructions"><strong>阅读说明：</strong>中文译文是主要阅读版本；如有术语或细节疑问，请展开原文核对。请根据材料本身判断，不猜测材料来源。</div>
      <div id="validationBox" class="validation-box" hidden></div>
      <section class="section-wrap"><div class="section-heading"><h3>完整材料与逐段判断</h3><span>检查两个集合；备注选填</span></div><div class="paragraphs">${item.sections.map((s, i) => renderParagraph(item, s, i, record)).join('')}</div></section>
      <section class="overall-panel"><h3>整组材料判断</h3><div class="question-grid">
        <div class="question"><h4>这组材料是否存在目标冲突？ <span class="required">*</span></h4><div class="choice-row">
          <label><input type="radio" name="target_conflict" value="present" ${checked('target_conflict', 'present')}>存在</label><label><input type="radio" name="target_conflict" value="absent" ${checked('target_conflict', 'absent')}>不存在</label></div></div>
        <div class="question"><h4>当前材料是否足够支持上述判断？ <span class="required">*</span></h4><div class="choice-row">
          <label><input type="radio" name="judgment_sufficient" value="yes" ${checked('judgment_sufficient', 'yes')}>充分</label><label><input type="radio" name="judgment_sufficient" value="no" ${checked('judgment_sufficient', 'no')}>不充分</label></div></div>
        <div class="question"><h4>对本次判断的信心 <span class="required">*</span></h4><select name="confidence"><option value="">请选择</option>${[1, 2, 3, 4, 5].map((v) => `<option value="${v}" ${record.confidence === String(v) ? 'selected' : ''}>${v} / 5${v === 1 ? '（很低）' : v === 5 ? '（很高）' : ''}</option>`).join('')}</select></div>
        <div class="question wide"><h4>整体判断理由（选填）</h4><textarea name="comments" placeholder="可记录判断依据或材料缺口">${esc(record.comments)}</textarea></div>
      </div><p id="insufficientNotice" class="readonly-guidance" ${record.judgment_sufficient === 'no' ? '' : 'hidden'}>材料不充分可以正常提交。该结果将保留为不确定判断，不强行计作已确认的正例或负例。</p></section>
      <div class="savebar"><button id="previousCaseBtn" class="button ghost" type="button" ${state.activeIndex === 0 ? 'disabled' : ''}>上一项</button><button id="saveCurrentBtn" class="button secondary" type="button">确认并保存</button>
        <button id="nextCaseBtn" class="button primary" type="button">${state.activeIndex === order.length - 1 ? '确认并检查完成情况' : '确认并进入下一项'}</button><span id="reviewStatus" class="hint"></span></div>`;
    updateReviewStatus();
    $('previousCaseBtn').onclick = () => navigate(state.activeIndex - 1);
    $('saveCurrentBtn').onclick = () => confirmCurrent(false);
    $('nextCaseBtn').onclick = () => confirmCurrent(true);
  }
  function updateReviewStatus() {
    const complete = isComplete(currentCase().presentation_id);
    $('reviewStatus').textContent = complete ? '本项已确认；再次编辑后需要重新确认。' : '本项尚未确认；草稿保存和侧栏跳转不会自动确认。';
  }
  function capture() {
    const item = currentCase(), root = $('workspace'), previous = annotation(item.presentation_id);
    const record = { ...previous, reviewer_id: state.reviewerId, sets_reviewed: false, saved_at: new Date().toISOString(),
      target_conflict: root.querySelector('[name="target_conflict"]:checked')?.value || '',
      judgment_sufficient: root.querySelector('[name="judgment_sufficient"]:checked')?.value || '',
      confidence: root.querySelector('[name="confidence"]').value, comments: root.querySelector('[name="comments"]').value, sections: {} };
    root.querySelectorAll('.paragraph-card').forEach((card) => { record.sections[card.dataset.sectionId] = {
      minimal_evidence: card.querySelector('[data-minimal-evidence]').checked,
      repair_packet: card.querySelector('[data-repair-packet]').checked, note: card.querySelector('[data-section-note]').value }; });
    if (same(answerOnly(previous), answerOnly(record))) return;
    Object.assign(record, currentProvenance(item.presentation_id));
    state.annotations[item.presentation_id] = record;
    $('insufficientNotice').hidden = record.judgment_sufficient !== 'no';
    $('validationBox').hidden = true;
    save(); renderList(); updateReviewStatus();
  }
  function formChanged(event) {
    const input = event.target;
    if (!input.matches('input, select, textarea')) return;
    const card = input.closest('.paragraph-card');
    if (input.matches('[data-minimal-evidence]') && input.checked) card.querySelector('[data-repair-packet]').checked = true;
    if (input.matches('[data-repair-packet]') && !input.checked && card.querySelector('[data-minimal-evidence]').checked) {
      input.checked = true; toast('最小证据必须保留在修复材料中；如需移除，请先取消最小证据。');
    }
    capture();
  }
  function navigate(index) {
    if (index < 0 || index >= order.length) return;
    state.activeIndex = index; save('浏览位置已保存'); renderList(); renderWorkspace();
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function confirmCurrent(next) {
    const item = currentCase(); const record = annotation(item.presentation_id);
    const errors = caseErrors(record, item, false);
    if (errors.length) { $('validationBox').hidden = false; $('validationBox').innerHTML = `<strong>请先补充：</strong><ul>${errors.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>`;
      $('validationBox').scrollIntoView({ block: 'center' }); return; }
    if (!isComplete(item.presentation_id)) {
      record.sets_reviewed = true; record.saved_at = new Date().toISOString();
      Object.assign(record, currentProvenance(item.presentation_id));
      state.annotations[item.presentation_id] = record;
    }
    save('当前项已确认并保存'); renderList(); updateReviewStatus();
    if (next && state.activeIndex < order.length - 1) navigate(state.activeIndex + 1);
    else if (next) toast(order.every(isComplete) ? '全部已确认，请导出电子表格和进度备份。' : '当前项已确认；其他未完成项请从侧栏继续。');
    else toast(storageAvailable ? '当前项已确认。' : '当前项已确认，但浏览器未保存；请立即导出进度备份。', !storageAvailable);
  }
  function safeCell(value) { return typeof value === 'string' && /^[=+\-@]/.test(value) ? `'${value}` : value; }
  function buildExportRows() {
    const caseRows = [], sectionRows = [];
    order.forEach((id, index) => {
      const item = cases.get(id), record = annotation(id);
      const selected = (field) => item.sections.filter((s) => record.sections[s.section_id][field]).map((s) => s.section_id).join(';');
      const common = { 专家编号: '专家 3', 匿名标注者编号: state.reviewerId, 样本编号: id, 文本类型: item.domain_label, schema_version: EXPORT_SCHEMA,
        annotation_mode: originMode(record), page_annotation_mode: PAGE_MODE,
        hint_pack_hash: record.hint_pack_hash || '', hints_visible: record.hints_visible ?? '',
        hints_displayed: record.hints_displayed ?? '', page_hint_pack_hash: hints.hint_pack_hash,
        page_hints_visible: state.hintsVisible, page_hints_displayed_for_case: state.hintsDisplayed.has(id),
        injection_marker_pack_hash: record.injection_marker_pack_hash || '',
        injection_hints_visible: record.injection_hints_visible ?? '', injection_hints_displayed: record.injection_hints_displayed ?? '',
        page_injection_marker_pack_hash: injectionMarkers.marker_pack_hash,
        page_injection_hints_displayed_for_case: state.injectionHintsDisplayed.has(id),
        annotation_protocol: PROTOCOL, review_protocol: REVIEW_PROTOCOL, expert_slot: EXPERT,
        reviewer_id: state.reviewerId, manifest_hash: manifest.manifest_hash, parent_manifest_hash: manifest.parent_manifest_hash,
        translation_pack_hash: translations.translation_pack_hash, sets_reviewed: record.sets_reviewed,
        完成状态: isComplete(id) ? '已完成' : '未完成', scoring_eligibility: eligibility(id) };
      caseRows.push({ ...common, 展示顺序: index + 1, 段落数: item.sections.length,
        目标冲突判断: ({ present: '存在', absent: '不存在' })[record.target_conflict] || '', 目标冲突代码: record.target_conflict,
        判断充分性: ({ yes: '充分', no: '不充分' })[record.judgment_sufficient] || '', 判断充分性代码: record.judgment_sufficient,
        judgment_sufficient: record.judgment_sufficient, 判断信心_1到5: record.confidence,
        最小证据段落: selected('minimal_evidence'), 修复材料段落: selected('repair_packet'), 整体备注: record.comments,
        证据选择已确认: record.sets_reviewed ? '是' : '否', 保存时间: record.saved_at });
      item.sections.forEach((section, n) => {
        const answer = record.sections[section.section_id], translated = translations.cases[id].sections[section.section_id];
        sectionRows.push({ ...common, 段落序号: n + 1, 段落编号: section.section_id,
          中文标题: translated.title_zh, 中文正文: translated.text_zh, 原文标题: section.title, 原文正文: section.text,
          是否最小证据: answer.minimal_evidence ? '是' : '否', 是否修复材料: answer.repair_packet ? '是' : '否', 段落备注: answer.note });
      });
    });
    return { caseRows, sectionRows };
  }
  function filename(extension) {
    const who = (state.reviewerId || EXPERT).replace(/[^a-zA-Z0-9_\-\u4e00-\u9fff]/g, '_');
    return `arr_oct2026_expert3_辅助复核_${who}_${new Date().toISOString().slice(0, 10)}${order.every(isComplete) ? '' : '_未完成'}.${extension}`;
  }
  function download(content, extension, type) {
    const url = URL.createObjectURL(new Blob([content], { type })); const link = document.createElement('a');
    link.href = url; link.download = filename(extension); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportJson() { download(JSON.stringify(payload(), null, 2), 'json', 'application/json'); toast('进度备份已导出。'); }
  function exportXlsx() {
    if (!state.reviewerId.trim()) { toast('请先填写匿名标注者编号。', true); return; }
    const remaining = order.filter((id) => !isComplete(id)).length;
    if (remaining && !window.confirm(`还有 ${remaining} 项未确认。仍要导出未完成草稿吗？`)) return;
    if (!window.XLSX) { toast('电子表格组件不可用，请保存进度备份。', true); return; }
    const { caseRows, sectionRows } = buildExportRows(); const workbook = window.XLSX.utils.book_new();
    const metadata = [{ schema_version: EXPORT_SCHEMA, 研究编号: manifest.study_id, 标注模式: '含算法与注入提示的标注页面', 专家编号: '专家 3',
      匿名标注者编号: state.reviewerId, annotation_mode: PAGE_MODE, page_annotation_mode: PAGE_MODE,
      hint_pack_hash: hints.hint_pack_hash, parent_hint_pack_hash: hints.parent_hint_pack_hash,
      hints_visible: state.hintsVisible, hints_displayed_case_ids: order.filter((id) => state.hintsDisplayed.has(id)).join(';'),
      injection_marker_pack_hash: injectionMarkers.marker_pack_hash,
      injection_hints_displayed_case_ids: order.filter((id) => state.injectionHintsDisplayed.has(id)).join(';'),
      legacy_blind_record_ids: payload().legacy_blind_record_ids.join(';'), annotation_protocol: PROTOCOL,
      review_protocol: REVIEW_PROTOCOL, expert_slot: EXPERT, reviewer_id: state.reviewerId,
      manifest_hash: manifest.manifest_hash, parent_manifest_hash: manifest.parent_manifest_hash,
      translation_pack_hash: translations.translation_pack_hash, 样本数: order.length,
      已确认样本数: order.length - remaining, 导出时间: new Date().toISOString() }];
    for (const [name, rows] of [['样本整体标注', caseRows], ['逐段标注', sectionRows], ['版本信息', metadata]]) {
      const safeRows = rows.map((row) => Object.fromEntries(Object.entries(row).map(([k, v]) => [k, safeCell(v)])));
      window.XLSX.utils.book_append_sheet(workbook, window.XLSX.utils.json_to_sheet(safeRows), name);
    }
    window.XLSX.writeFile(workbook, filename('xlsx')); toast('电子表格已导出，请同时保存进度备份。');
  }
  function restoreBackup(raw) {
    validateBackup(raw); // Validate everything before archive, assignment, or any localStorage write.
    if (!storageAvailable && Object.keys(state.annotations).length) fail('浏览器存储不可用，无法安全归档当前进度。请先导出进度备份，再在新开页面恢复。');
    if (!window.confirm(storageAvailable
      ? '这将替换本页面当前的专家 3 进度；恢复前会保留原进度副本。是否继续？'
      : '浏览器存储不可用，将在当前空白页面恢复备份；后续进度需要手动导出。是否继续？')) return false;
    if (storageAvailable) {
      const existing = localStorage.getItem(storageKey);
      if (existing) localStorage.setItem(`${storageKey}:before-restore:${Date.now()}`, existing);
    }
    state.annotations = copy(raw.annotations); state.reviewerId = raw.reviewer_id; state.activeIndex = raw.active_index;
    if (raw.schema_version !== LEGACY_SCHEMA) {
      state.hintsVisible = raw.hints_visible;
      for (const id of raw.hints_displayed_case_ids) state.hintsDisplayed.add(id);
      for (const id of raw.injection_hints_displayed_case_ids || []) state.injectionHintsDisplayed.add(id);
    }
    $('reviewerId').value = state.reviewerId; save('进度备份已恢复'); renderList(); renderWorkspace(); toast('进度备份已恢复。'); return true;
  }
  function bindEvents() {
    $('reviewerId').addEventListener('input', () => {
      const nextId = $('reviewerId').value.trim();
      if (nextId === state.reviewerId) return;
      state.reviewerId = nextId;
      for (const record of Object.values(state.annotations)) { record.reviewer_id = state.reviewerId; record.sets_reviewed = false; }
      save('标注者编号已保存；请重新确认已填写项目'); renderList(); updateReviewStatus();
    });
    $('workspace').addEventListener('input', formChanged); $('workspace').addEventListener('change', formChanged);
    $('caseList').onclick = (event) => { const button = event.target.closest('[data-index]'); if (button) navigate(Number(button.dataset.index)); };
    document.querySelectorAll('[data-filter]').forEach((button) => button.onclick = () => {
      state.filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach((b) => b.classList.toggle('active', b === button)); renderList(); });
    $('firstIncompleteBtn').onclick = () => { const index = order.findIndex((id) => !isComplete(id)); if (index >= 0) navigate(index); else toast('全部样本已确认。'); };
    $('exportXlsxBtn').onclick = exportXlsx; $('exportJsonBtn').onclick = exportJson;
    $('toggleHintsBtn').onclick = toggleHints;
    $('restoreBtn').onclick = () => $('restoreInput').click();
    $('restoreInput').onchange = async (event) => {
      const file = event.target.files?.[0]; if (!file) return;
      try { restoreBackup(JSON.parse(await file.text())); } catch (error) { toast(`未恢复：${error.message}`, true); }
      event.target.value = '';
    };
  }
  function initialize() {
    try {
      manifest = JSON.parse($('manifestData').textContent); translations = JSON.parse($('translationData').textContent);
      hints = JSON.parse($('methodHintsData').textContent);
      injectionMarkers = JSON.parse($('injectionMarkersData').textContent); validateData();
      let existing = null;
      try { existing = localStorage.getItem(storageKey); } catch (_) { storageAvailable = false; }
      if (existing) { const restored = JSON.parse(existing); validateBackup(restored); state.annotations = copy(restored.annotations);
        state.reviewerId = restored.reviewer_id; state.activeIndex = restored.active_index;
        if (restored.schema_version === LEGACY_SCHEMA) {
          try { localStorage.setItem(`${storageKey}:before-hints:${Date.now()}`, existing); }
          catch (_) { storageAvailable = false; }
        } else {
          state.hintsVisible = restored.hints_visible;
          state.hintsDisplayed = new Set(restored.hints_displayed_case_ids);
          state.injectionHintsDisplayed = new Set(restored.injection_hints_displayed_case_ids || []);
          if (!restored.injection_marker_pack_hash) {
            try { localStorage.setItem(`${storageKey}:before-injection-hints:${Date.now()}`, existing); }
            catch (_) { storageAvailable = false; }
          }
        }
      }
      $('reviewerId').value = state.reviewerId; renderList(); renderWorkspace(); bindEvents();
      $('saveStatus').textContent = storageAvailable ? (existing ? '已恢复本页面进度' : '尚未填写；开始后自动保存草稿') : '浏览器存储不可用；仍可标注，请及时导出进度备份';
      if (!storageAvailable) $('saveIndicator').classList.add('error');
      window.ThirdExpertReview = Object.freeze({ getSnapshot: () => copy(payload()), validateBackup, restoreBackup,
        isComplete, buildExportRows, getStorageKey: () => storageKey, getCurrentCase: () => copy(currentCase()), exportJson, exportXlsx,
        getHintsVisible: () => state.hintsVisible, toggleHints, getHintsData: () => copy(hints),
        getInjectionMarkersData: () => copy(injectionMarkers) });
    } catch (error) {
      writable = false; $('saveStatus').textContent = '载入失败，未覆盖任何已有进度'; $('saveIndicator').classList.add('error');
      $('workspace').innerHTML = `<div class="fatal-error"><h2>材料或进度校验失败</h2><p>${esc(error.message)}</p><p>请保留当前文件和已有进度，联系组织者核对。未读取或迁移其他页面的标注。</p></div>`;
    }
  }
  initialize();
})();
