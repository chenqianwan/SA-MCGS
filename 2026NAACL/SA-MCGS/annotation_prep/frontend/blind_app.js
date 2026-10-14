'use strict';

const STORE_PREFIX = 'sa_mcgs_blind_expert_audit_v2';
const STATE_SCHEMA = 'blind_annotation.state.v2';
const EXPORT_SCHEMA = 'blind_annotation.export.v2';
const EXPERTS = [
  { id: 'expert_1', label: '专家 1' },
  { id: 'expert_2', label: '专家 2' },
  { id: 'expert_3', label: '专家 3' },
];

const state = {
  manifest: null,
  translations: null,
  cases: [],
  activeExpert: 'expert_1',
  activeIndex: 0,
  activeIndices: {},
  annotations: {},
  reviewerIds: {},
  orders: {},
  filter: 'all',
  createdAt: new Date().toISOString(),
  storageAvailable: true,
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function readEmbeddedJson(id) {
  const node = $(id);
  if (!node) throw new Error(`页面缺少内置数据：${id}`);
  return JSON.parse(node.textContent);
}

function validateData(manifest, translations) {
  if (!manifest || manifest.schema_version !== 'blind_annotation.v1') {
    throw new Error('样本数据版本不兼容。');
  }
  if (!manifest.study_id || !manifest.manifest_hash || !Array.isArray(manifest.cases)) {
    throw new Error('样本数据缺少研究编号、版本哈希或样本列表。');
  }
  if (!translations || translations.schema_version !== 'annotation_translation.zh-CN.v1') {
    throw new Error('中文材料数据版本不兼容。');
  }
  if (translations.source_manifest_hash !== manifest.manifest_hash) {
    throw new Error('中文材料与样本版本不一致。');
  }
  const caseIds = new Set();
  const sectionIds = new Map();
  manifest.cases.forEach((item, caseIndex) => {
    if (!item.presentation_id || caseIds.has(item.presentation_id)) {
      throw new Error(`第 ${caseIndex + 1} 个样本编号缺失或重复。`);
    }
    caseIds.add(item.presentation_id);
    if (!Array.isArray(item.sections) || item.sections.length === 0) {
      throw new Error(`样本 ${item.presentation_id} 没有可标注段落。`);
    }
    const seenSections = new Set();
    item.sections.forEach((section, sectionIndex) => {
      if (!section.section_id || seenSections.has(section.section_id)) {
        throw new Error(`样本 ${item.presentation_id} 的第 ${sectionIndex + 1} 个段落编号无效。`);
      }
      seenSections.add(section.section_id);
      if (!section.text && !section.title) {
        throw new Error(`样本 ${item.presentation_id} 的 ${section.section_id} 没有文字。`);
      }
      const translated = translations.cases?.[item.presentation_id]?.sections?.[section.section_id];
      if (!translated || typeof translated.text_zh !== 'string') {
        throw new Error(`样本 ${item.presentation_id} 的 ${section.section_id} 缺少中文材料。`);
      }
    });
    sectionIds.set(item.presentation_id, seenSections);
  });
  EXPERTS.forEach((expert) => {
    const order = manifest.expert_orders?.[expert.id];
    if (!Array.isArray(order) || order.length !== manifest.cases.length) {
      throw new Error(`${expert.label} 的样本顺序不完整。`);
    }
    const unique = new Set(order);
    if (unique.size !== caseIds.size || [...unique].some((id) => !caseIds.has(id))) {
      throw new Error(`${expert.label} 的样本顺序包含重复项或未知样本。`);
    }
  });
  return { manifest, translations, caseIds, sectionIds };
}

function storeKey() {
  return `${STORE_PREFIX}:${state.manifest.study_id}:${state.manifest.manifest_hash}`;
}

function expertLabel(expertId = state.activeExpert) {
  return EXPERTS.find((item) => item.id === expertId)?.label || expertId;
}

function annotationBucket(expertId = state.activeExpert) {
  if (!state.annotations[expertId]) state.annotations[expertId] = {};
  return state.annotations[expertId];
}

function annotationFor(presentationId, expertId = state.activeExpert) {
  return state.annotations[expertId]?.[presentationId] || {};
}

function casesForExpert(expertId = state.activeExpert) {
  const byId = new Map(state.cases.map((item) => [item.presentation_id, item]));
  return (state.orders[expertId] || []).map((id) => byId.get(id)).filter(Boolean);
}

function currentCase() {
  return casesForExpert()[state.activeIndex] || null;
}

function translatedSection(item, section) {
  return state.translations.cases[item.presentation_id].sections[section.section_id];
}

function roleLabel(value) {
  return {
    conflict_evidence: '核心冲突证据',
    supporting_context: '相关证据或解释',
    ordinary_context: '一般上下文',
    uncertain: '无法判断',
  }[value] || '';
}

function targetLabel(value) {
  return {
    present: '存在目标冲突',
    absent: '不存在目标冲突',
    insufficient: '信息不足，无法判断',
  }[value] || '';
}

function sufficiencyLabel(value) {
  return {
    yes: '充分', partial: '部分充分', no: '不充分', not_applicable: '不适用',
  }[value] || '';
}

function contextLabel(value) {
  return { yes: '需要', no: '不需要', uncertain: '不确定' }[value] || '';
}

function isComplete(presentationId, expertId = state.activeExpert) {
  const annotation = annotationFor(presentationId, expertId);
  const item = state.cases.find((candidate) => candidate.presentation_id === presentationId);
  const reviewerId = (annotation.reviewer_id || state.reviewerIds[expertId] || '').trim();
  const fieldsComplete = Boolean(
    reviewerId
    && annotation.target_conflict
    && annotation.evidence_sufficient
    && annotation.need_more_context
    && annotation.confidence
    && item?.sections.every((section) => annotation.sections?.[section.section_id]?.role)
  );
  if (!fieldsComplete) return false;
  if (annotation.target_conflict === 'absent' && annotation.evidence_sufficient !== 'not_applicable') return false;
  if (annotation.target_conflict === 'present' && annotation.evidence_sufficient === 'not_applicable') return false;
  if (annotation.target_conflict === 'present' && ['yes', 'partial'].includes(annotation.evidence_sufficient)) {
    return Object.values(annotation.sections || {}).some((section) => section.minimal_evidence);
  }
  return true;
}

function setSaveStatus(message, type = 'saved') {
  $('saveStatus').textContent = message;
  const indicator = $('saveIndicator');
  indicator.classList.remove('saved', 'error');
  if (type) indicator.classList.add(type);
}

function saveState(message = '已自动保存') {
  if (!state.manifest) return false;
  const payload = {
    schema_version: STATE_SCHEMA,
    study_id: state.manifest.study_id,
    manifest_hash: state.manifest.manifest_hash,
    translation_pack_hash: state.translations.translation_pack_hash || '',
    annotation_mode: 'blind_human_audit',
    active_expert: state.activeExpert,
    active_indices: state.activeIndices,
    annotations: state.annotations,
    reviewer_ids: state.reviewerIds,
    orders: state.orders,
    created_at: state.createdAt,
    updated_at: new Date().toISOString(),
  };
  try {
    localStorage.setItem(storeKey(), JSON.stringify(payload));
    localStorage.setItem(`${STORE_PREFIX}:last_expert`, state.activeExpert);
    state.storageAvailable = true;
    setSaveStatus(`${message} · ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`);
    return true;
  } catch (error) {
    state.storageAvailable = false;
    setSaveStatus('自动保存失败，请立即导出进度备份', 'error');
    showToast('浏览器无法保存数据，请立即下载进度备份。', true);
    console.error(error);
    return false;
  }
}

function loadStoredState() {
  state.orders = Object.fromEntries(EXPERTS.map((expert) => [
    expert.id,
    [...state.manifest.expert_orders[expert.id]],
  ]));
  try {
    const stored = JSON.parse(localStorage.getItem(storeKey()) || 'null');
    if (stored) {
      const compatible = stored.schema_version === STATE_SCHEMA
        && stored.study_id === state.manifest.study_id
        && stored.manifest_hash === state.manifest.manifest_hash
        && (!stored.translation_pack_hash
          || stored.translation_pack_hash === state.translations.translation_pack_hash);
      if (!compatible) throw new Error('本地进度来自不同版本，已忽略。');
      validateOrderMap(stored.orders);
      validateAnnotationMap(stored.annotations || {});
      state.annotations = stored.annotations || {};
      state.reviewerIds = stored.reviewer_ids || {};
      state.orders = stored.orders;
      state.activeIndices = stored.active_indices || {};
      state.createdAt = stored.created_at || state.createdAt;
      state.activeExpert = EXPERTS.some((expert) => expert.id === stored.active_expert)
        ? stored.active_expert
        : state.activeExpert;
    }
  } catch (error) {
    console.warn(error);
    showToast('未载入旧进度：旧数据版本不兼容或已损坏。', true);
  }
  state.activeIndex = boundedIndex(state.activeIndices[state.activeExpert] || 0);
}

function boundedIndex(value, expertId = state.activeExpert) {
  const count = casesForExpert(expertId).length;
  const number = Number.isInteger(Number(value)) ? Number(value) : 0;
  return Math.max(0, Math.min(number, Math.max(0, count - 1)));
}

function validateOrderMap(orders) {
  const validIds = new Set(state.cases.map((item) => item.presentation_id));
  EXPERTS.forEach((expert) => {
    const order = orders?.[expert.id];
    if (!Array.isArray(order) || order.length !== validIds.size || new Set(order).size !== validIds.size) {
      throw new Error(`${expert.label} 的备份顺序无效。`);
    }
    if (order.some((id) => !validIds.has(id))) throw new Error(`${expert.label} 的备份包含未知样本。`);
  });
}

function validateAnnotationMap(annotations) {
  const cases = new Map(state.cases.map((item) => [item.presentation_id, item]));
  Object.entries(annotations || {}).forEach(([expertId, bucket]) => {
    if (!EXPERTS.some((expert) => expert.id === expertId) || !bucket || typeof bucket !== 'object') {
      throw new Error('备份中的专家编号无效。');
    }
    Object.entries(bucket).forEach(([presentationId, annotation]) => {
      const item = cases.get(presentationId);
      if (!item || !annotation || typeof annotation !== 'object') throw new Error('备份包含未知样本。');
      const allowedSections = new Set(item.sections.map((section) => section.section_id));
      if (Object.keys(annotation.sections || {}).some((id) => !allowedSections.has(id))) {
        throw new Error(`备份中的样本 ${presentationId} 包含未知段落。`);
      }
    });
  });
}

function renderCaseList() {
  const cases = casesForExpert();
  const done = cases.filter((item) => isComplete(item.presentation_id)).length;
  $('progressText').textContent = `${done} / ${cases.length}`;
  $('progressBar').style.width = cases.length ? `${(done / cases.length) * 100}%` : '0%';
  const visible = cases.map((item, index) => ({ item, index })).filter(({ item }) => {
    if (state.filter === 'done') return isComplete(item.presentation_id);
    if (state.filter === 'open') return !isComplete(item.presentation_id);
    return true;
  });
  $('caseList').innerHTML = visible.length ? visible.map(({ item, index }) => {
    const complete = isComplete(item.presentation_id);
    return `<button class="case-button ${index === state.activeIndex ? 'active' : ''} ${complete ? 'done' : ''}" data-case-index="${index}" type="button">
      <span class="case-button-head"><strong>样本 ${index + 1}</strong><span class="case-status" aria-label="${complete ? '已完成' : '未完成'}">${complete ? '●' : '○'}</span></span>
      <small>${esc(item.domain_label || '文本材料')} · ${item.sections.length} 个段落</small>
    </button>`;
  }).join('') : '<p class="local-note">当前筛选下没有样本。</p>';
  document.querySelectorAll('[data-case-index]').forEach((button) => {
    button.addEventListener('click', () => navigateTo(Number(button.dataset.caseIndex)));
  });
}

function selected(value, expected) {
  return value === expected ? 'checked' : '';
}

function renderParagraph(item, section, index) {
  const annotation = annotationFor(item.presentation_id);
  const sectionAnnotation = annotation.sections?.[section.section_id] || {};
  const translated = translatedSection(item, section);
  const group = `section_role_${section.section_id}`;
  return `<article class="paragraph-card" data-section-id="${esc(section.section_id)}">
    <div class="paragraph-text">
      <p class="paragraph-number">段落 ${index + 1}</p>
      ${translated.title_zh ? `<h4 class="paragraph-title">${esc(translated.title_zh)}</h4>` : ''}
      <div class="paragraph-body">${esc(translated.text_zh || '')}</div>
      <details class="source-original">
        <summary>展开核对原文</summary>
        ${section.title ? `<h5>${esc(section.title)}</h5>` : ''}
        <div>${esc(section.text || '')}</div>
      </details>
    </div>
    <div class="paragraph-form">
      <h4>该段在整组材料中的作用 <span class="required">*</span></h4>
      <div class="radio-list">
        <label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="conflict_evidence" ${selected(sectionAnnotation.role, 'conflict_evidence')}> <span><b>核心冲突证据</b><br>该段本身构成冲突的一端。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="supporting_context" ${selected(sectionAnnotation.role, 'supporting_context')}> <span><b>相关证据或解释</b><br>有助于理解、定位或修复冲突。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="ordinary_context" ${selected(sectionAnnotation.role, 'ordinary_context')}> <span><b>一般上下文</b><br>与目标冲突没有直接关系。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="uncertain" ${selected(sectionAnnotation.role, 'uncertain')}> <span><b>无法判断</b><br>现有材料不足以判断该段作用。</span></label>
      </div>
      <div class="check-grid">
        <label class="check-option"><input type="checkbox" data-minimal-evidence ${sectionAnnotation.minimal_evidence ? 'checked' : ''}> <span><b>纳入最小证据集</b><br>没有该段就难以证明冲突。</span></label>
        <label class="check-option"><input type="checkbox" data-repair-packet ${sectionAnnotation.repair_packet ? 'checked' : ''}> <span><b>纳入修复材料</b><br>提出修复建议时应保留该段。</span></label>
      </div>
      <textarea data-section-note placeholder="可选：简要说明判断理由">${esc(sectionAnnotation.note || '')}</textarea>
    </div>
  </article>`;
}

function renderWorkspace() {
  const item = currentCase();
  if (!item) {
    $('workspace').innerHTML = '<div class="empty-state"><h2>没有可标注样本</h2></div>';
    return;
  }
  const cases = casesForExpert();
  const annotation = annotationFor(item.presentation_id);
  const radio = (name, value) => selected(annotation[name] || '', value);
  $('workspace').innerHTML = `
    <header class="case-header">
      <p class="eyebrow">标注材料 ${state.activeIndex + 1} / ${cases.length}</p>
      <h2>样本 ${state.activeIndex + 1}</h2>
      <p class="blind-notice">下列段落来自同一个文档图中的循环关联区域。请判断它们是否包含无法同时成立的要求或记录，并选出足以证明及修复问题的材料。</p>
      <div class="case-meta">
        <span class="pill">${esc(item.domain_label || '文本材料')}</span>
        <span class="pill">${item.sections.length} 个段落</span>
        <span class="pill">${esc(expertLabel())}</span>
      </div>
    </header>
    <div class="instructions"><strong>阅读说明：</strong>中文译文是主要阅读版本；对术语或细节有疑问时，可展开原文核对。请勿根据措辞风格猜测材料来源。</div>
    <div id="validationBox" class="validation-box" hidden></div>
    <section class="section-wrap">
      <div class="section-heading"><h3>完整材料与逐段判断</h3><span>每个段落均需选择一项</span></div>
      <div class="paragraphs">${item.sections.map((section, index) => renderParagraph(item, section, index)).join('')}</div>
    </section>
    <section class="overall-panel">
      <h3>整组材料判断</h3>
      <div class="question-grid">
        <div class="question">
          <h4>这组材料是否存在目标冲突？ <span class="required">*</span></h4>
          <div class="choice-row">
            <label><input type="radio" name="target_conflict" value="present" ${radio('target_conflict', 'present')}>存在</label>
            <label><input type="radio" name="target_conflict" value="absent" ${radio('target_conflict', 'absent')}>不存在</label>
            <label><input type="radio" name="target_conflict" value="insufficient" ${radio('target_conflict', 'insufficient')}>信息不足</label>
          </div>
        </div>
        <div class="question">
          <h4>当前材料是否足以定位该问题？ <span class="required">*</span></h4>
          <div class="choice-row">
            <label><input type="radio" name="evidence_sufficient" value="yes" ${radio('evidence_sufficient', 'yes')}>充分</label>
            <label><input type="radio" name="evidence_sufficient" value="partial" ${radio('evidence_sufficient', 'partial')}>部分充分</label>
            <label><input type="radio" name="evidence_sufficient" value="no" ${radio('evidence_sufficient', 'no')}>不充分</label>
            <label><input type="radio" name="evidence_sufficient" value="not_applicable" ${radio('evidence_sufficient', 'not_applicable')}>不适用</label>
          </div>
        </div>
        <div class="question">
          <h4>是否需要未展示的上下文才能判断？ <span class="required">*</span></h4>
          <div class="choice-row">
            <label><input type="radio" name="need_more_context" value="yes" ${radio('need_more_context', 'yes')}>需要</label>
            <label><input type="radio" name="need_more_context" value="no" ${radio('need_more_context', 'no')}>不需要</label>
            <label><input type="radio" name="need_more_context" value="uncertain" ${radio('need_more_context', 'uncertain')}>不确定</label>
          </div>
        </div>
        <div class="question">
          <h4>对本次判断的信心 <span class="required">*</span></h4>
          <select name="confidence">
            <option value="">请选择</option>
            ${[1, 2, 3, 4, 5].map((value) => `<option value="${value}" ${String(annotation.confidence || '') === String(value) ? 'selected' : ''}>${value} / 5</option>`).join('')}
          </select>
        </div>
        <div class="question wide">
          <h4>整体判断理由（可选）</h4>
          <textarea name="comments" placeholder="可记录冲突关系、材料缺口或专业判断依据">${esc(annotation.comments || '')}</textarea>
        </div>
      </div>
    </section>
    <div class="savebar">
      <button id="previousCaseBtn" class="button ghost" type="button" ${state.activeIndex === 0 ? 'disabled' : ''}>上一项</button>
      <button id="saveCurrentBtn" class="button secondary" type="button">保存当前项</button>
      <button id="nextCaseBtn" class="button primary" type="button">${state.activeIndex === cases.length - 1 ? '保存并检查完成情况' : '保存并进入下一项'}</button>
      <span class="hint">侧栏跳转可保留未完成草稿</span>
    </div>`;
  $('previousCaseBtn').addEventListener('click', () => navigateTo(state.activeIndex - 1));
  $('saveCurrentBtn').addEventListener('click', () => {
    captureCurrentForm('当前样本已保存');
    const result = validateCurrentCase();
    if (!result.valid) showValidation(result.errors);
    else showToast('当前样本填写完整并已保存。');
  });
  $('nextCaseBtn').addEventListener('click', saveAndNext);
}

function captureCurrentForm(message = '已自动保存') {
  const item = currentCase();
  const root = $('workspace');
  if (!item || !root?.querySelector('.overall-panel')) return;
  const previous = annotationFor(item.presentation_id);
  const sections = {};
  root.querySelectorAll('.paragraph-card').forEach((card) => {
    const sectionId = card.dataset.sectionId;
    const role = card.querySelector('[data-section-role]:checked')?.value || '';
    sections[sectionId] = {
      role,
      role_label: roleLabel(role),
      minimal_evidence: Boolean(card.querySelector('[data-minimal-evidence]')?.checked),
      repair_packet: Boolean(card.querySelector('[data-repair-packet]')?.checked),
      note: card.querySelector('[data-section-note]')?.value || '',
    };
  });
  const radio = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value || '';
  annotationBucket()[item.presentation_id] = {
    ...previous,
    reviewer_id: $('reviewerId').value.trim(),
    expert_slot: state.activeExpert,
    target_conflict: radio('target_conflict'),
    evidence_sufficient: radio('evidence_sufficient'),
    need_more_context: radio('need_more_context'),
    confidence: root.querySelector('select[name="confidence"]')?.value || '',
    comments: root.querySelector('textarea[name="comments"]')?.value || '',
    sections,
    saved_at: new Date().toISOString(),
  };
  state.reviewerIds[state.activeExpert] = $('reviewerId').value.trim();
  state.activeIndices[state.activeExpert] = state.activeIndex;
  saveState(message);
  renderCaseList();
}

function validateCurrentCase() {
  const item = currentCase();
  const annotation = annotationFor(item.presentation_id);
  const errors = [];
  if (!(annotation.reviewer_id || state.reviewerIds[state.activeExpert] || '').trim()) errors.push('请填写匿名标注者编号。');
  const missingSections = item.sections.filter((section) => !annotation.sections?.[section.section_id]?.role);
  if (missingSections.length) errors.push(`还有 ${missingSections.length} 个段落未判断。`);
  if (!annotation.target_conflict) errors.push('请选择整组材料是否存在目标冲突。');
  if (!annotation.evidence_sufficient) errors.push('请选择当前材料是否足以定位问题。');
  if (!annotation.need_more_context) errors.push('请选择是否需要更多上下文。');
  if (!annotation.confidence) errors.push('请选择判断信心。');
  if (annotation.target_conflict === 'absent' && annotation.evidence_sufficient && annotation.evidence_sufficient !== 'not_applicable') {
    errors.push('选择“不存在冲突”时，材料充分性应选择“不适用”。');
  }
  if (annotation.target_conflict === 'present' && annotation.evidence_sufficient === 'not_applicable') {
    errors.push('选择“存在冲突”时，材料充分性不能选择“不适用”。');
  }
  const minimalCount = Object.values(annotation.sections || {}).filter((section) => section.minimal_evidence).length;
  if (annotation.target_conflict === 'present'
      && ['yes', 'partial'].includes(annotation.evidence_sufficient)
      && minimalCount === 0) {
    errors.push('认为存在冲突且材料至少部分充分时，请至少勾选一个“最小证据集”段落。');
  }
  return { valid: errors.length === 0, errors };
}

function showValidation(errors) {
  const box = $('validationBox');
  if (!box) return;
  box.hidden = false;
  box.innerHTML = `<strong>当前样本尚未填写完整：</strong><ul>${errors.map((error) => `<li>${esc(error)}</li>`).join('')}</ul>`;
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function saveAndNext() {
  captureCurrentForm('当前样本已保存');
  const result = validateCurrentCase();
  if (!result.valid) {
    showValidation(result.errors);
    return;
  }
  const cases = casesForExpert();
  if (state.activeIndex < cases.length - 1) {
    navigateTo(state.activeIndex + 1, false);
  } else {
    const incomplete = cases.filter((item) => !isComplete(item.presentation_id)).length;
    showToast(incomplete ? `仍有 ${incomplete} 个样本未完成。` : '全部样本均已完成，可以导出结果。', Boolean(incomplete));
    renderCaseList();
  }
}

function navigateTo(index, capture = true) {
  if (capture) captureCurrentForm();
  state.activeIndex = boundedIndex(index);
  state.activeIndices[state.activeExpert] = state.activeIndex;
  saveState('进度已保存');
  renderAll();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function firstIncomplete() {
  captureCurrentForm();
  const index = casesForExpert().findIndex((item) => !isComplete(item.presentation_id));
  if (index < 0) showToast('当前专家的全部样本均已完成。');
  else navigateTo(index, false);
}

function buildExportRows(expertId = state.activeExpert) {
  const caseRows = [];
  const sectionRows = [];
  const order = casesForExpert(expertId);
  order.forEach((item, orderIndex) => {
    const annotation = annotationFor(item.presentation_id, expertId);
    const sections = annotation.sections || {};
    const minimal = Object.entries(sections).filter(([, value]) => value.minimal_evidence).map(([id]) => id);
    const repair = Object.entries(sections).filter(([, value]) => value.repair_packet).map(([id]) => id);
    caseRows.push({
      专家编号: expertLabel(expertId),
      匿名标注者编号: annotation.reviewer_id || state.reviewerIds[expertId] || '',
      展示顺序: orderIndex + 1,
      样本编号: item.presentation_id,
      文本类型: item.domain_label || '',
      段落数: item.sections.length,
      目标冲突判断: targetLabel(annotation.target_conflict),
      目标冲突代码: annotation.target_conflict || '',
      材料充分性: sufficiencyLabel(annotation.evidence_sufficient),
      材料充分性代码: annotation.evidence_sufficient || '',
      是否需要更多上下文: contextLabel(annotation.need_more_context),
      更多上下文代码: annotation.need_more_context || '',
      判断信心_1到5: annotation.confidence || '',
      最小证据段落: minimal.join(';'),
      修复材料段落: repair.join(';'),
      整体备注: annotation.comments || '',
      完成状态: isComplete(item.presentation_id, expertId) ? '已完成' : '未完成',
      保存时间: annotation.saved_at || '',
      manifest_hash: state.manifest.manifest_hash,
      translation_pack_hash: state.translations.translation_pack_hash || '',
    });
    item.sections.forEach((section, sectionIndex) => {
      const sectionAnnotation = sections[section.section_id] || {};
      const translated = translatedSection(item, section);
      sectionRows.push({
        专家编号: expertLabel(expertId),
        匿名标注者编号: annotation.reviewer_id || state.reviewerIds[expertId] || '',
        样本编号: item.presentation_id,
        文本类型: item.domain_label || '',
        段落序号: sectionIndex + 1,
        段落编号: section.section_id,
        中文标题: translated.title_zh || '',
        中文正文: translated.text_zh || '',
        原文标题: section.title || '',
        原文正文: section.text || '',
        段落作用: roleLabel(sectionAnnotation.role),
        段落作用代码: sectionAnnotation.role || '',
        是否最小证据: sectionAnnotation.minimal_evidence ? '是' : '否',
        是否修复材料: sectionAnnotation.repair_packet ? '是' : '否',
        段落备注: sectionAnnotation.note || '',
      });
    });
  });
  return { caseRows, sectionRows };
}

function exportReadiness() {
  captureCurrentForm();
  const cases = casesForExpert();
  const incomplete = cases.filter((item) => !isComplete(item.presentation_id)).length;
  if (!state.reviewerIds[state.activeExpert]?.trim()) {
    showToast('请先填写匿名标注者编号。', true);
    return { proceed: false, incomplete };
  }
  if (incomplete && !window.confirm(`当前还有 ${incomplete} 个样本未完成。是否仍导出未完成草稿？`)) {
    return { proceed: false, incomplete };
  }
  return { proceed: true, incomplete };
}

function exportXlsx() {
  const readiness = exportReadiness();
  if (!readiness.proceed) return;
  if (!window.XLSX) {
    showToast('电子表格组件不可用，请先导出进度备份。', true);
    return;
  }
  const { caseRows, sectionRows } = buildExportRows();
  const metadata = [{
    研究编号: state.manifest.study_id,
    标注模式: '独立盲法专家标注',
    专家编号: expertLabel(),
    匿名标注者编号: state.reviewerIds[state.activeExpert] || '',
    导出时间: new Date().toISOString(),
    manifest_hash: state.manifest.manifest_hash,
    translation_pack_hash: state.translations.translation_pack_hash || '',
  }];
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(xlsxSafeRows(caseRows)), '样本整体标注');
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(xlsxSafeRows(sectionRows)), '逐段标注');
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(xlsxSafeRows(metadata)), '版本信息');
  XLSX.writeFile(workbook, exportFilename('标注结果', readiness.incomplete, 'xlsx'));
  showToast('电子表格已导出。');
}

function exportJson() {
  captureCurrentForm();
  const expertId = state.activeExpert;
  const payload = {
    schema_version: EXPORT_SCHEMA,
    study_id: state.manifest.study_id,
    manifest_hash: state.manifest.manifest_hash,
    translation_pack_hash: state.translations.translation_pack_hash || '',
    annotation_mode: 'blind_human_audit',
    expert_slot: expertId,
    anonymous_reviewer_id: state.reviewerIds[expertId] || '',
    order: [...state.orders[expertId]],
    active_index: state.activeIndex,
    annotations: JSON.parse(JSON.stringify(state.annotations[expertId] || {})),
    exported_at: new Date().toISOString(),
  };
  downloadBlob(exportFilename('进度备份', false, 'json'), JSON.stringify(payload, null, 2), 'application/json');
  showToast('进度备份已下载。');
}

function exportCsv() {
  const readiness = exportReadiness();
  if (!readiness.proceed) return;
  const { caseRows } = buildExportRows();
  const headers = Object.keys(caseRows[0] || {});
  const rows = [headers, ...caseRows.map((row) => headers.map((key) => spreadsheetSafe(row[key])))];
  const csv = rows.map((row) => row.map(csvEscape).join(',')).join('\r\n');
  downloadBlob(exportFilename('样本汇总', readiness.incomplete, 'csv'), `\ufeff${csv}`, 'text/csv;charset=utf-8');
  showToast('汇总表已导出。');
}

function spreadsheetSafe(value) {
  const text = String(value ?? '');
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function xlsxSafeRows(rows) {
  return rows.map((row) => Object.fromEntries(
    Object.entries(row).map(([key, value]) => [key, typeof value === 'string' ? spreadsheetSafe(value) : value]),
  ));
}

function csvEscape(value) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function exportFilename(kind, incomplete, extension) {
  const reviewer = safeName(state.reviewerIds[state.activeExpert] || state.activeExpert);
  const suffix = incomplete ? '_未完成' : '';
  return `${safeName(state.manifest.study_id)}_${safeName(expertLabel())}_${reviewer}_${dateStamp()}_${kind}${suffix}.${extension}`;
}

function safeName(value) {
  return String(value || 'annotation').replace(/[^a-zA-Z0-9_\-\u4e00-\u9fff]+/g, '_');
}

function dateStamp() {
  return new Date().toISOString().slice(0, 10);
}

function downloadBlob(filename, content, mimeType) {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function restoreBackup(raw) {
  if (!raw || raw.schema_version !== EXPORT_SCHEMA) throw new Error('备份文件版本不兼容。');
  if (raw.study_id !== state.manifest.study_id || raw.manifest_hash !== state.manifest.manifest_hash) {
    throw new Error('备份文件与当前样本版本不一致。');
  }
  if (raw.translation_pack_hash !== (state.translations.translation_pack_hash || '')) {
    throw new Error('备份文件与当前中文材料版本不一致。');
  }
  if (!EXPERTS.some((expert) => expert.id === raw.expert_slot)) throw new Error('备份中的专家编号无效。');
  validateOrderMap({ ...state.orders, [raw.expert_slot]: raw.order });
  validateAnnotationMap({ [raw.expert_slot]: raw.annotations || {} });
  if (!window.confirm(`将用备份覆盖${expertLabel(raw.expert_slot)}当前浏览器中的进度，是否继续？`)) return;
  try {
    const existing = localStorage.getItem(storeKey());
    if (existing) localStorage.setItem(`${storeKey()}:before_restore:${Date.now()}`, existing);
  } catch (error) {
    console.warn('覆盖前归档失败。', error);
  }
  state.annotations[raw.expert_slot] = JSON.parse(JSON.stringify(raw.annotations || {}));
  state.reviewerIds[raw.expert_slot] = String(raw.anonymous_reviewer_id || '');
  state.orders[raw.expert_slot] = [...raw.order];
  state.activeIndices[raw.expert_slot] = boundedIndex(raw.active_index || 0, raw.expert_slot);
  state.activeExpert = raw.expert_slot;
  state.activeIndex = state.activeIndices[raw.expert_slot];
  $('expertSlot').value = state.activeExpert;
  $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
  saveState('进度备份已恢复');
  renderAll();
  showToast('进度备份已恢复。');
}

function readJsonFile(file) {
  return file.text().then((text) => JSON.parse(text));
}

function showToast(message, isError = false) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3200);
}

function renderAll() {
  renderCaseList();
  renderWorkspace();
}

function debounce(callback, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}

// BOOTSTRAP_BINDINGS
function bindEvents() {
  $('expertSlot').addEventListener('change', () => {
    captureCurrentForm();
    state.activeIndices[state.activeExpert] = state.activeIndex;
    state.activeExpert = $('expertSlot').value;
    state.activeIndex = boundedIndex(state.activeIndices[state.activeExpert] || 0);
    $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
    saveState('专家编号已切换');
    renderAll();
  });
  $('reviewerId').addEventListener('input', debounce(() => {
    state.reviewerIds[state.activeExpert] = $('reviewerId').value.trim();
    captureCurrentForm();
  }, 250));
  document.querySelectorAll('[data-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      state.filter = button.dataset.filter;
      document.querySelectorAll('[data-filter]').forEach((item) => item.classList.toggle('active', item === button));
      renderCaseList();
    });
  });
  $('firstIncompleteBtn').addEventListener('click', firstIncomplete);
  $('exportXlsxBtn').addEventListener('click', exportXlsx);
  $('exportJsonBtn').addEventListener('click', exportJson);
  $('exportCsvBtn').addEventListener('click', exportCsv);
  $('restoreBtn').addEventListener('click', () => $('restoreInput').click());
  $('restoreInput').addEventListener('change', async (event) => {
    const [file] = event.target.files || [];
    if (!file) return;
    try { await restoreBackup(await readJsonFile(file)); }
    catch (error) { showToast(error.message, true); }
    event.target.value = '';
  });
  $('workspace').addEventListener('change', () => captureCurrentForm());
  $('workspace').addEventListener('input', debounce(() => captureCurrentForm(), 250));
  window.addEventListener('keydown', (event) => {
    if (!event.altKey || event.metaKey || event.ctrlKey) return;
    if (event.key === 'ArrowLeft' && state.activeIndex > 0) navigateTo(state.activeIndex - 1);
    if (event.key === 'ArrowRight' && state.activeIndex < casesForExpert().length - 1) navigateTo(state.activeIndex + 1);
  });
  window.addEventListener('beforeunload', () => captureCurrentForm());
}

function initialize() {
  try {
    state.manifest = readEmbeddedJson('manifestData');
    state.translations = readEmbeddedJson('translationData');
    validateData(state.manifest, state.translations);
    state.cases = state.manifest.cases;
    let rememberedExpert = '';
    try {
      rememberedExpert = localStorage.getItem(`${STORE_PREFIX}:last_expert`) || '';
    } catch (error) {
      state.storageAvailable = false;
      console.warn('浏览器本地存储不可用。', error);
    }
    if (EXPERTS.some((expert) => expert.id === rememberedExpert)) state.activeExpert = rememberedExpert;
    loadStoredState();
    $('expertSlot').value = state.activeExpert;
    $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
    bindEvents();
    renderAll();
    saveState('材料已载入');
  } catch (error) {
    console.error(error);
    $('workspace').innerHTML = `<div class="empty-state"><h2>页面数据无法载入</h2><p>${esc(error.message)}</p></div>`;
    setSaveStatus('载入失败', 'error');
  }
}

initialize();
