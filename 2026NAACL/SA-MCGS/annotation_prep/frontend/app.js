'use strict';

const DEFAULT_MANIFEST_URL = 'data/manifest.json';
const DEFAULT_TRANSLATION_URL = 'data/translations_zh.json';
const DEFAULT_HINT_URL = 'data/method_hints.json';
const STORE_PREFIX = 'assisted_expert_audit_v1';
const EXPERTS = [
  { id: 'expert_1', label: '专家 1' },
  { id: 'expert_2', label: '专家 2' },
  { id: 'expert_3', label: '专家 3' },
];

const state = {
  manifest: null,
  translations: null,
  hints: null,
  cases: [],
  activeExpert: localStorage.getItem(`${STORE_PREFIX}:active_expert`) || 'expert_1',
  activeIndex: 0,
  annotations: {},
  reviewerIds: {},
  orders: {},
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function manifestKey(studyId = state.manifest?.study_id || 'unknown') {
  return `${STORE_PREFIX}:${studyId}`;
}

function activeExpertLabel() {
  return EXPERTS.find((expert) => expert.id === state.activeExpert)?.label || state.activeExpert;
}

function annotationBucket(expertId = state.activeExpert) {
  if (!state.annotations[expertId]) state.annotations[expertId] = {};
  return state.annotations[expertId];
}

function annotationFor(presentationId, expertId = state.activeExpert) {
  return state.annotations[expertId]?.[presentationId] || {};
}

function hash32(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function mulberry32(seed) {
  return function random() {
    let value = seed += 0x6D2B79F5;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function deterministicOrder(cases, expertId) {
  const ids = cases.map((item) => item.presentation_id);
  const random = mulberry32(hash32(`${state.manifest.study_id}|${state.manifest.randomization_seed}|${expertId}`));
  for (let index = ids.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [ids[index], ids[swapIndex]] = [ids[swapIndex], ids[index]];
  }
  return ids;
}

function validateManifest(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('样本清单必须是有效的数据对象。');
  if (raw.schema_version !== 'blind_annotation.v1') {
    throw new Error(`不支持的数据版本：${raw.schema_version || '缺失'}。`);
  }
  if (!raw.study_id || !Array.isArray(raw.cases) || raw.cases.length === 0) {
    throw new Error('样本清单缺少研究编号或样本列表。');
  }
  const seen = new Set();
  raw.cases.forEach((item, index) => {
    if (!item.presentation_id || seen.has(item.presentation_id)) {
      throw new Error(`第 ${index + 1} 个样本缺少展示编号，或展示编号重复。`);
    }
    seen.add(item.presentation_id);
    if (!Array.isArray(item.sections) || item.sections.length === 0) {
      throw new Error(`样本 ${item.presentation_id} 没有段落。`);
    }
    item.sections.forEach((section, sectionIndex) => {
      if (!section.section_id || (!section.text && !section.title)) {
        throw new Error(`样本 ${item.presentation_id} 的第 ${sectionIndex + 1} 段格式不完整。`);
      }
    });
  });
  return raw;
}

function validateAuxiliaryPacks(manifest, translations, hints) {
  if (translations?.schema_version !== 'annotation_translation.zh-CN.v1') {
    throw new Error('中文翻译数据格式不兼容。');
  }
  if (hints?.schema_version !== 'assisted_method_hints.v1') {
    throw new Error('算法提示数据格式不兼容。');
  }
  if (translations.source_manifest_hash !== manifest.manifest_hash) {
    throw new Error('中文翻译与当前样本版本不一致。');
  }
  if (hints.source_manifest_hash !== manifest.manifest_hash) {
    throw new Error('算法提示与当前样本版本不一致。');
  }
  manifest.cases.forEach((item) => {
    const translatedCase = translations.cases?.[item.presentation_id];
    const hintedCase = hints.cases?.[item.presentation_id];
    if (!translatedCase || !hintedCase) {
      throw new Error(`样本 ${item.presentation_id} 缺少中文翻译或算法提示。`);
    }
    item.sections.forEach((section) => {
      const translated = translatedCase.sections?.[section.section_id];
      const hinted = hintedCase.sections?.[section.section_id];
      if (!translated || !hinted) {
        throw new Error(`样本 ${item.presentation_id} 的 ${section.section_id} 数据不完整。`);
      }
      if (typeof translated.title_zh !== 'string' || typeof translated.text_zh !== 'string') {
        throw new Error(`样本 ${item.presentation_id} 的 ${section.section_id} 缺少中文文字。`);
      }
    });
  });
}

function loadStoredState() {
  const key = manifestKey();
  try {
    const stored = JSON.parse(localStorage.getItem(key) || '{}');
    const hashMismatch = Boolean(
      stored.manifest_hash
      && state.manifest.manifest_hash
      && stored.manifest_hash !== state.manifest.manifest_hash
    );
    const stimulusMismatch = Boolean(
      (stored.translation_pack_hash && stored.translation_pack_hash !== state.translations?.translation_pack_hash)
      || (stored.hint_pack_hash && stored.hint_pack_hash !== state.hints?.hint_pack_hash)
    );
    if (hashMismatch || stimulusMismatch) {
      localStorage.setItem(`${key}:archived:${Date.now()}`, JSON.stringify(stored));
      state.annotations = {};
      state.reviewerIds = {};
      state.orders = {};
    } else {
      state.annotations = stored.annotations || {};
      state.reviewerIds = stored.reviewer_ids || {};
      state.orders = stored.orders || {};
    }
  } catch (error) {
    console.warn('本地保存状态无法读取，已重置。', error);
    state.annotations = {};
    state.reviewerIds = {};
    state.orders = {};
  }
  EXPERTS.forEach((expert) => {
    const prescribed = state.manifest.expert_orders?.[expert.id];
    const current = state.orders[expert.id] || prescribed || [];
    const validIds = new Set(state.cases.map((item) => item.presentation_id));
    const isValid = current.length === state.cases.length && current.every((id) => validIds.has(id));
    state.orders[expert.id] = isValid
      ? [...current]
      : (Array.isArray(prescribed) ? [...prescribed] : deterministicOrder(state.cases, expert.id));
  });
  saveState('样本已载入');
}

function saveState(message = '已自动保存') {
  if (!state.manifest) return;
  const payload = {
    schema_version: 'assisted_annotation.state.v1',
    study_id: state.manifest.study_id,
    manifest_hash: state.manifest.manifest_hash || '',
    annotation_mode: 'method_assisted_review',
    translation_pack_hash: state.translations?.translation_pack_hash || '',
    hint_pack_hash: state.hints?.hint_pack_hash || '',
    annotations: state.annotations,
    reviewer_ids: state.reviewerIds,
    orders: state.orders,
    updated_at: new Date().toISOString(),
  };
  localStorage.setItem(manifestKey(), JSON.stringify(payload));
  localStorage.setItem(`${STORE_PREFIX}:active_expert`, state.activeExpert);
  const status = $('saveStatus');
  if (status) status.textContent = message;
  document.querySelector('.autosave')?.classList.add('saved');
}

function casesForActiveExpert() {
  const byId = new Map(state.cases.map((item) => [item.presentation_id, item]));
  return (state.orders[state.activeExpert] || []).map((id) => byId.get(id)).filter(Boolean);
}

function isComplete(presentationId, expertId = state.activeExpert) {
  const annotation = annotationFor(presentationId, expertId);
  const item = state.cases.find((candidate) => candidate.presentation_id === presentationId);
  const allSectionsJudged = Boolean(item?.sections.every((section) => annotation.sections?.[section.section_id]?.judgement));
  return Boolean(
    annotation.overall_conflict
    && annotation.material_sufficient
    && annotation.need_more_context
    && annotation.confidence
    && allSectionsJudged
  );
}

function currentCase() {
  return casesForActiveExpert()[state.activeIndex] || null;
}

function renderCaseList() {
  const cases = casesForActiveExpert();
  const done = cases.filter((item) => isComplete(item.presentation_id)).length;
  $('progressText').textContent = `${done} / ${cases.length}`;
  $('progressBar').style.width = cases.length ? `${(done / cases.length) * 100}%` : '0%';
  $('caseList').innerHTML = cases.map((item, index) => {
    const complete = isComplete(item.presentation_id);
    const condition = state.hints?.cases?.[item.presentation_id]?.condition;
    const conditionLabel = condition === 'pre' ? '未注入' : '注入后';
    return `<button class="case-button ${index === state.activeIndex ? 'active' : ''} ${complete ? 'done' : ''}" data-case-index="${index}" type="button">
      <span class="case-button-head"><strong>样本 ${index + 1}</strong><span class="case-status" aria-label="${complete ? '已完成' : '未完成'}">${complete ? '●' : '○'}</span></span>
      <small>${esc(item.domain_label || '文本材料')} · ${item.sections.length} 段 · ${conditionLabel}</small>
    </button>`;
  }).join('');
  document.querySelectorAll('[data-case-index]').forEach((button) => {
    button.addEventListener('click', () => {
      captureCurrentForm();
      state.activeIndex = Number(button.dataset.caseIndex);
      renderAll();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

function selected(value, expected) {
  return value === expected ? 'checked' : '';
}

const MODEL_LABELS = {
  'gpt-4o': 'GPT-4o',
  'gemini-2.5-pro': 'Gemini 2.5 Pro',
};

const METHOD_LABELS = {
  lea: 'LEA',
  'sa-mcgs': 'SA-MCGS',
};

function translatedSection(item, section) {
  return state.translations?.cases?.[item.presentation_id]?.sections?.[section.section_id] || {
    title_zh: '',
    text_zh: '',
  };
}

function hintStatusText(hint) {
  return hint?.reason_zh || ({
    not_run: '尚未运行',
    strict_invalid: '输出未通过严格校验',
    missing: '没有可核验结果',
    identity_mismatch: '结果身份不匹配',
  }[hint?.status] || '暂无结果');
}

function renderModelHint(model, hint) {
  const modelLabel = MODEL_LABELS[model] || model;
  if (!hint || hint.status !== 'available') {
    return `<div class="model-hint unavailable">
      <strong>${esc(modelLabel)}</strong>
      <span>${esc(hintStatusText(hint))}</span>
    </div>`;
  }
  const score = hint.score == null ? '—' : Number(hint.score).toFixed(3);
  const rank = hint.rank == null ? '—' : `第 ${hint.rank} / ${hint.total_nodes}`;
  return `<div class="model-hint ${hint.selected ? 'selected' : 'not-selected'}">
    <strong>${esc(modelLabel)}</strong>
    <span class="selection-chip">${hint.selected ? '已纳入结果子图' : '未纳入结果子图'}</span>
    <span>风险相关分 ${score}</span>
    <span>排名 ${rank}</span>
  </div>`;
}

function renderMethodHint(item, section, method) {
  const methodData = state.hints?.cases?.[item.presentation_id]
    ?.sections?.[section.section_id]?.methods?.[method];
  const models = methodData?.models || {};
  const available = Object.values(models).filter((hint) => hint?.status === 'available');
  const selectedCount = available.filter((hint) => hint.selected).length;
  const summary = available.length
    ? `${selectedCount} / ${available.length} 个可用模型纳入该段`
    : '当前没有可用运行结果';
  return `<section class="method-hint-card method-${esc(method)}">
    <div class="method-hint-head">
      <h5>${esc(METHOD_LABELS[method] || method)}</h5>
      <span>${summary}</span>
    </div>
    <div class="model-hint-list">
      ${Object.entries(models).map(([model, hint]) => renderModelHint(model, hint)).join('')}
    </div>
  </section>`;
}

function renderParagraph(item, section, index) {
  const annotation = annotationFor(item.presentation_id);
  const sectionAnnotation = annotation.sections?.[section.section_id] || {};
  const judgement = sectionAnnotation.judgement || '';
  const translated = translatedSection(item, section);
  const judgementGroup = `section_judgement_${section.section_id}`;
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
      <div class="method-hints" aria-label="算法结果提示">
        ${renderMethodHint(item, section, 'lea')}
        ${renderMethodHint(item, section, 'sa-mcgs')}
      </div>
    </div>
    <div class="paragraph-form">
      <h4>这段文字与整组材料的关系</h4>
      <div class="radio-list">
        <label class="radio-option"><input type="radio" name="${esc(judgementGroup)}" data-section-judgement value="problem" ${selected(judgement, 'problem')}> <span><b>有明显问题</b><br>自身有问题，或与其他段落明显冲突。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(judgementGroup)}" data-section-judgement value="related" ${selected(judgement, 'related')}> <span><b>可能有关</b><br>自身未必有错，但定位问题时可能相关。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(judgementGroup)}" data-section-judgement value="clear" ${selected(judgement, 'clear')}> <span><b>没有明显问题</b><br>看起来只是普通上下文。</span></label>
        <label class="radio-option"><input type="radio" name="${esc(judgementGroup)}" data-section-judgement value="unsure" ${selected(judgement, 'unsure')}> <span><b>不确定</b><br>现有文字不足以判断。</span></label>
      </div>
      <label class="keep-option"><input type="checkbox" data-section-keep ${sectionAnnotation.keep_for_repair ? 'checked' : ''}> <span><b>保留为关键材料</b><br>若只给复核者少量段落，我会保留这一段。</span></label>
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
  const cases = casesForActiveExpert();
  const annotation = annotationFor(item.presentation_id);
  const condition = state.hints?.cases?.[item.presentation_id]?.condition;
  const conditionLabel = condition === 'pre' ? '未注入原始样本' : '注入后样本';
  const radio = (name, value) => selected(annotation[name] || '', value);
  $('workspace').innerHTML = `
    <header class="case-header">
      <p class="eyebrow">辅助复核材料 ${state.activeIndex + 1} / ${cases.length}</p>
      <h2>样本 ${state.activeIndex + 1}</h2>
      <p class="blind-notice">这些段落来自同一个文档图中的循环关联区域。请结合中文译文和算法提示，判断文字之间是否存在无法同时成立的要求，以及哪些段落足以定位问题。</p>
      <div class="case-meta">
        <span class="pill">${esc(item.domain_label || '文本材料')}</span>
        <span class="pill">${item.sections.length} 个段落</span>
        <span class="pill condition-${esc(condition || 'unknown')}">${esc(conditionLabel)}</span>
        <span class="pill">${esc(activeExpertLabel())}</span>
      </div>
    </header>
    <div class="instructions"><strong>复核说明：</strong>中文译文是主要阅读版本；LEA 与 SA-MCGS 提示只反映算法运行结果，不能替代专家判断。</div>
    <section class="section-wrap">
      <div class="section-heading"><h3>完整材料与逐段标注</h3><span>每段均可独立判断</span></div>
      <div class="paragraphs">${item.sections.map((section, index) => renderParagraph(item, section, index)).join('')}</div>
    </section>
    <section class="overall-panel">
      <h3>整组材料判断</h3>
      <div class="question-grid">
        <div class="question">
          <h4>这组文字整体是否存在真实冲突？</h4>
          <div class="choice-row">
            <label><input type="radio" name="overall_conflict" value="yes" ${radio('overall_conflict', 'yes')}>是</label>
            <label><input type="radio" name="overall_conflict" value="maybe" ${radio('overall_conflict', 'maybe')}>可能</label>
            <label><input type="radio" name="overall_conflict" value="no" ${radio('overall_conflict', 'no')}>否</label>
            <label><input type="radio" name="overall_conflict" value="unsure" ${radio('overall_conflict', 'unsure')}>不确定</label>
          </div>
        </div>
        <div class="question">
          <h4>你保留的段落是否足够定位和修复问题？</h4>
          <div class="choice-row">
            <label><input type="radio" name="material_sufficient" value="yes" ${radio('material_sufficient', 'yes')}>足够</label>
            <label><input type="radio" name="material_sufficient" value="partial" ${radio('material_sufficient', 'partial')}>部分足够</label>
            <label><input type="radio" name="material_sufficient" value="no" ${radio('material_sufficient', 'no')}>不够</label>
            <label><input type="radio" name="material_sufficient" value="unsure" ${radio('material_sufficient', 'unsure')}>不确定</label>
            <label><input type="radio" name="material_sufficient" value="not_applicable" ${radio('material_sufficient', 'not_applicable')}>不适用（未发现冲突）</label>
          </div>
        </div>
        <div class="question">
          <h4>是否还需要未展示的上下文才能判断？</h4>
          <div class="choice-row">
            <label><input type="radio" name="need_more_context" value="yes" ${radio('need_more_context', 'yes')}>需要</label>
            <label><input type="radio" name="need_more_context" value="no" ${radio('need_more_context', 'no')}>不需要</label>
            <label><input type="radio" name="need_more_context" value="unsure" ${radio('need_more_context', 'unsure')}>不确定</label>
          </div>
        </div>
        <div class="question">
          <h4>对本次判断的信心</h4>
          <select name="confidence">
            <option value="">请选择</option>
            ${[1, 2, 3, 4, 5].map((value) => `<option value="${value}" ${String(annotation.confidence || '') === String(value) ? 'selected' : ''}>${value} / 5</option>`).join('')}
          </select>
        </div>
        <div class="question wide">
          <h4>整体备注（可选）</h4>
          <textarea name="comments" placeholder="可记录冲突理由、仍缺少的材料或专业判断依据">${esc(annotation.comments || '')}</textarea>
        </div>
      </div>
    </section>
    <div class="savebar">
      <button id="saveCurrentBtn" class="button primary" type="button">保存当前样本</button>
      <button id="nextCaseBtn" class="button secondary" type="button">保存并进入下一项</button>
      <span class="hint">填写时自动保存在本浏览器；结束后请导出电子表格。</span>
    </div>`;

  $('saveCurrentBtn').addEventListener('click', () => captureCurrentForm('当前样本已保存'));
  $('nextCaseBtn').addEventListener('click', () => {
    captureCurrentForm('当前样本已保存');
    if (state.activeIndex < cases.length - 1) {
      state.activeIndex += 1;
      renderAll();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
}

function debounce(callback, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}

function captureCurrentForm(message = '已自动保存') {
  const item = currentCase();
  const root = $('workspace');
  if (!item || !root?.querySelector('.overall-panel')) return;
  const previous = annotationFor(item.presentation_id);
  const sections = {};
  root.querySelectorAll('.paragraph-card').forEach((card) => {
    const sectionId = card.dataset.sectionId;
    const judgement = card.querySelector('[data-section-judgement]:checked')?.value || '';
    sections[sectionId] = {
      judgement,
      judgement_label: judgementLabel(judgement),
      keep_for_repair: Boolean(card.querySelector('[data-section-keep]')?.checked),
      note: card.querySelector('[data-section-note]')?.value || '',
    };
  });
  const radio = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value || '';
  annotationBucket()[item.presentation_id] = {
    ...previous,
    reviewer_id: $('reviewerId').value.trim(),
    expert_slot: state.activeExpert,
    expert_label: activeExpertLabel(),
    overall_conflict: radio('overall_conflict'),
    material_sufficient: radio('material_sufficient'),
    need_more_context: radio('need_more_context'),
    confidence: root.querySelector('select[name="confidence"]')?.value || '',
    comments: root.querySelector('textarea[name="comments"]')?.value || '',
    sections,
    saved_at: new Date().toISOString(),
  };
  state.reviewerIds[state.activeExpert] = $('reviewerId').value.trim();
  saveState(message);
  renderCaseList();
}

function judgementLabel(value) {
  return {
    problem: '有明显问题',
    related: '可能有关',
    clear: '没有明显问题',
    unsure: '不确定',
  }[value] || '';
}

function buildExport() {
  captureCurrentForm();
  const caseRows = [];
  const sectionRows = [];
  EXPERTS.forEach((expert) => {
    state.cases.forEach((item) => {
      const annotation = annotationFor(item.presentation_id, expert.id);
      const selectedSections = Object.entries(annotation.sections || {})
        .filter(([, section]) => section.keep_for_repair)
        .map(([sectionId]) => sectionId);
      caseRows.push({
        专家编号: expert.label,
        标注者: annotation.reviewer_id || state.reviewerIds[expert.id] || '',
        样本编号: item.presentation_id,
        文本类型: item.domain_label || '',
        样本条件: state.hints?.cases?.[item.presentation_id]?.condition === 'pre' ? '未注入原始样本' : '注入后样本',
        标注模式: '算法辅助复核',
        已展示算法提示: '是',
        段落数: item.sections.length,
        整体是否冲突: annotation.overall_conflict || '',
        勾选材料是否足够修复: annotation.material_sufficient || '',
        是否需要更多上下文: annotation.need_more_context || '',
        标注信心_1到5: annotation.confidence || '',
        专家勾选段落: selectedSections.join(';'),
        备注: annotation.comments || '',
        保存时间: annotation.saved_at || '',
        manifest_hash: state.manifest.manifest_hash || '',
        translation_pack_hash: state.translations?.translation_pack_hash || '',
        hint_pack_hash: state.hints?.hint_pack_hash || '',
      });
      item.sections.forEach((section, index) => {
        const sectionAnnotation = annotation.sections?.[section.section_id] || {};
        const translated = translatedSection(item, section);
        const methodHints = state.hints?.cases?.[item.presentation_id]
          ?.sections?.[section.section_id]?.methods || {};
        sectionRows.push({
          专家编号: expert.label,
          标注者: annotation.reviewer_id || state.reviewerIds[expert.id] || '',
          样本编号: item.presentation_id,
          文本类型: item.domain_label || '',
          段落序号: index + 1,
          原始编号: section.section_id,
          中文标题: translated.title_zh || '',
          中文正文: translated.text_zh || '',
          原文标题: section.title || '',
          原文正文: section.text || '',
          LEA提示: JSON.stringify(methodHints.lea || {}),
          SA_MCGS提示: JSON.stringify(methodHints['sa-mcgs'] || {}),
          专家判断: sectionAnnotation.judgement_label || judgementLabel(sectionAnnotation.judgement),
          专家判断代码: sectionAnnotation.judgement || '',
          是否放入最终修复材料: sectionAnnotation.keep_for_repair ? '是' : '否',
          段落备注: sectionAnnotation.note || '',
        });
      });
    });
  });
  return { caseRows, sectionRows };
}

function exportXlsx() {
  if (!window.XLSX) {
    alert('电子表格导出组件未载入；请改用完整备份或汇总表。');
    return;
  }
  const { caseRows, sectionRows } = buildExport();
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(caseRows), '样本整体标注');
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(sectionRows), '逐段标注');
  XLSX.writeFile(workbook, `${safeName(state.manifest.study_id)}_${dateStamp()}_标注结果.xlsx`);
}

function exportJson() {
  const payload = {
    schema_version: 'assisted_annotation.export.v1',
    study_id: state.manifest.study_id,
    manifest_hash: state.manifest.manifest_hash || '',
    annotation_mode: 'method_assisted_review',
    translation_pack_hash: state.translations?.translation_pack_hash || '',
    hint_pack_hash: state.hints?.hint_pack_hash || '',
    exported_at: new Date().toISOString(),
    reviewer_ids: state.reviewerIds,
    orders: state.orders,
    annotations: state.annotations,
  };
  downloadBlob(`${safeName(state.manifest.study_id)}_${dateStamp()}_完整备份.json`, JSON.stringify(payload, null, 2), 'application/json');
}

function csvEscape(value) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function exportCsv() {
  const { caseRows } = buildExport();
  const headers = Object.keys(caseRows[0] || {});
  const csv = [headers, ...caseRows.map((row) => headers.map((key) => row[key]))]
    .map((row) => row.map(csvEscape).join(','))
    .join('\r\n');
  downloadBlob(`${safeName(state.manifest.study_id)}_${dateStamp()}_样本汇总.csv`, `\ufeff${csv}`, 'text/csv;charset=utf-8');
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

function safeName(value) {
  return String(value || 'annotation').replace(/[^a-zA-Z0-9_-]+/g, '_');
}

function dateStamp() {
  return new Date().toISOString().slice(0, 10);
}

async function applyManifest(raw) {
  state.manifest = validateManifest(raw);
  validateAuxiliaryPacks(state.manifest, state.translations, state.hints);
  state.cases = state.manifest.cases;
  state.activeIndex = 0;
  if (!EXPERTS.some((expert) => expert.id === state.activeExpert)) state.activeExpert = 'expert_1';
  loadStoredState();
  $('expertSlot').value = state.activeExpert;
  $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
  renderAll();
}

async function loadDefaultManifest() {
  try {
    const [manifestResponse, translationResponse, hintResponse] = await Promise.all([
      fetch(DEFAULT_MANIFEST_URL, { cache: 'no-store' }),
      fetch(DEFAULT_TRANSLATION_URL, { cache: 'no-store' }),
      fetch(DEFAULT_HINT_URL, { cache: 'no-store' }),
    ]);
    if (!manifestResponse.ok || !translationResponse.ok || !hintResponse.ok) {
      throw new Error('样本、中文翻译或算法提示文件未能完整读取');
    }
    state.translations = await translationResponse.json();
    state.hints = await hintResponse.json();
    await applyManifest(await manifestResponse.json());
  } catch (error) {
    showLoadError(`无法自动读取页面数据（${error.message}）。请通过本地服务器打开页面，并确认三个数据文件均已生成。`);
  }
}

function showLoadError(message) {
  const fragment = $('errorTemplate').content.cloneNode(true);
  fragment.querySelector('[data-error-message]').textContent = message;
  fragment.querySelector('[data-retry-manifest]').addEventListener('click', () => $('manifestInput').click());
  $('workspace').replaceChildren(fragment);
  $('saveStatus').textContent = '样本尚未载入';
}

async function readJsonFile(file) {
  return JSON.parse(await file.text());
}

async function applySelectedDataFiles(files) {
  const payloads = await Promise.all([...files].map(readJsonFile));
  const manifest = payloads.find((value) => value?.schema_version === 'blind_annotation.v1');
  const translations = payloads.find((value) => value?.schema_version === 'annotation_translation.zh-CN.v1');
  const hints = payloads.find((value) => value?.schema_version === 'assisted_method_hints.v1');
  if (!manifest || !translations || !hints) {
    throw new Error('请同时选择样本清单、中文译文和算法提示三个数据文件。');
  }
  state.translations = translations;
  state.hints = hints;
  await applyManifest(manifest);
}

async function restoreBackup(raw) {
  if (!state.manifest) throw new Error('请先载入本次标注的样本清单。');
  if (raw.schema_version !== 'assisted_annotation.export.v1') throw new Error('标注备份的数据版本不兼容。');
  if (raw.study_id !== state.manifest.study_id) throw new Error('备份与当前研究编号不一致。');
  if (raw.manifest_hash && state.manifest.manifest_hash && raw.manifest_hash !== state.manifest.manifest_hash) {
    throw new Error('备份与当前样本版本不一致，已拒绝覆盖。');
  }
  if (raw.translation_pack_hash && raw.translation_pack_hash !== state.translations?.translation_pack_hash) {
    throw new Error('备份与当前中文翻译版本不一致，已拒绝覆盖。');
  }
  if (raw.hint_pack_hash && raw.hint_pack_hash !== state.hints?.hint_pack_hash) {
    throw new Error('备份与当前算法提示版本不一致，已拒绝覆盖。');
  }
  state.annotations = raw.annotations || {};
  state.reviewerIds = raw.reviewer_ids || {};
  state.orders = raw.orders || state.orders;
  state.activeIndex = 0;
  $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
  saveState('备份已恢复');
  renderAll();
}

function renderAll() {
  renderCaseList();
  renderWorkspace();
}

$('loadManifestBtn').addEventListener('click', () => $('manifestInput').click());
$('manifestInput').addEventListener('change', async (event) => {
  if (!event.target.files?.length) return;
  try { await applySelectedDataFiles(event.target.files); }
  catch (error) { showLoadError(error.message); }
  event.target.value = '';
});
$('restoreBtn').addEventListener('click', () => $('restoreInput').click());
$('restoreInput').addEventListener('change', async (event) => {
  const [file] = event.target.files;
  if (!file) return;
  try { await restoreBackup(await readJsonFile(file)); }
  catch (error) { alert(error.message); }
  event.target.value = '';
});
$('expertSlot').addEventListener('change', () => {
  captureCurrentForm();
  state.activeExpert = $('expertSlot').value;
  state.activeIndex = 0;
  $('reviewerId').value = state.reviewerIds[state.activeExpert] || '';
  saveState('专家编号已切换');
  renderAll();
});
$('reviewerId').addEventListener('input', debounce(() => {
  state.reviewerIds[state.activeExpert] = $('reviewerId').value.trim();
  saveState();
}, 250));
$('exportXlsxBtn').addEventListener('click', exportXlsx);
$('exportJsonBtn').addEventListener('click', exportJson);
$('exportCsvBtn').addEventListener('click', exportCsv);
$('workspace').addEventListener('change', () => captureCurrentForm('已自动保存'));
$('workspace').addEventListener('input', debounce(() => captureCurrentForm('已自动保存'), 250));
window.addEventListener('beforeunload', () => captureCurrentForm());

loadDefaultManifest();
