/* Self-contained independent annotation page. Only this batch's storage is read. */
(() => {
  'use strict';
  const SCHEMA = 'third_expert_blind.export.v2';
  const LEGACY_SCHEMA = 'third_expert_blind.export.v1';
  const PROTOCOL = 'binary_judgment_v1';
  const EXPERT = 'expert_3';
  const METHODS = ['sa-mcgs', 'lea'];
  const METHOD_LABELS = { 'sa-mcgs': 'SA-MCGS', lea: 'LEA' };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const now = () => new Date().toISOString();
  const hash = (value) => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value);
  const timestamp = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value));
  function require(condition, message) { if (!condition) throw new Error(message); }
  function fields(value, allowed, required = allowed) {
    return object(value) && Object.keys(value).every((name) => allowed.includes(name)) && required.every((name) => own(value, name));
  }
  function canonical(value) {
    if (Array.isArray(value)) return JSON.stringify(value.map((entry) => JSON.parse(canonical(entry))));
    if (object(value)) return JSON.stringify(Object.fromEntries(Object.keys(value).sort().map((name) => [name, JSON.parse(canonical(value[name]))])));
    return JSON.stringify(value);
  }
  let data, byId, catalog, storageKey, session, methodHints;
  let hintsVisible = false;
  let activeCase = '', language = 'zh', filter = 'all', validation = '';
  let storageAvailable = true, storageReadBlocked = false, corrupt = null;

  function validatePayload(raw) {
    require(fields(raw, ['schema_version', 'study_id', 'manifest_hash', 'annotation_protocol', 'annotation_mode', 'expert_id', 'hints_visible', 'case_count', 'cases']), '样本包字段不完整或含未知字段。');
    require(raw.schema_version === 'third_expert_blind_payload.v1' && raw.study_id === 'expert3_blind_20261010'
      && raw.annotation_protocol === PROTOCOL && raw.annotation_mode === 'blind'
      && raw.expert_id === EXPERT && raw.hints_visible === false && hash(raw.manifest_hash), '样本包身份或标注模式不符。');
    require(Number.isInteger(raw.case_count) && raw.case_count > 0 && Array.isArray(raw.cases)
      && raw.cases.length === raw.case_count, '样本包案例数不一致。');
    const ids = new Set(), orders = new Set();
    for (const item of raw.cases) {
      require(fields(item, ['id', 'order', 'content_hash', 'sections']) && /^B-\d{2,}$/.test(item.id)
        && !ids.has(item.id) && hash(item.content_hash) && Number.isInteger(item.order) && item.order > 0
        && !orders.has(item.order), '案例身份或顺序无效。');
      ids.add(item.id); orders.add(item.order);
      require(Array.isArray(item.sections) && item.sections.length > 0, '案例缺少完整材料。');
      const sections = new Set();
      for (const section of item.sections) {
        require(fields(section, ['id', 'heading', 'original_text', 'zh_heading', 'zh_text'], ['id', 'original_text'])
          && /^S\d{3,}$/.test(section.id) && !sections.has(section.id)
          && typeof section.original_text === 'string' && section.original_text.trim().length > 0, '案例段落无效。');
        for (const name of ['heading', 'zh_heading', 'zh_text']) require(section[name] == null || typeof section[name] === 'string', '段落标题或译文无效。');
        sections.add(section.id);
      }
    }
    return raw;
  }
  function emptySession() {
    return { schema_version: SCHEMA, study_id: data.study_id, manifest_hash: data.manifest_hash,
      annotation_protocol: PROTOCOL, annotation_mode: 'blind', expert_id: EXPERT, hints_visible: false,
      case_catalog: clone(catalog), active_case_id: data.cases[0].id, display_language: 'zh', annotations: {}, exported_at: now(),
      hint_visibility: emptyVisibility() };
  }
  function prepareMethodHints(raw) {
    const withPredictions = raw?.schema_version === 'third_expert_method_hints.v2';
    const allowed = ['schema_version', 'source_manifest_hash', 'models', 'methods', 'cases', 'pack_hash',
      ...(withPredictions ? ['case_predictions', 'risk_rule_description'] : [])];
    require(fields(raw, allowed)
      && (withPredictions || raw.schema_version === 'third_expert_method_hints.v1') && raw.source_manifest_hash === data.manifest_hash
      && hash(raw.pack_hash) && canonical(raw.methods) === canonical(METHODS), '段落提示包的身份或版本不符。');
    require(Array.isArray(raw.models) && raw.models.length > 0, '段落提示包缺少模型列表。');
    const models = new Set();
    for (const model of raw.models) {
      require(fields(model, ['id', 'label']) && typeof model.id === 'string' && /^[a-zA-Z0-9_.-]+$/.test(model.id)
        && !['__proto__', 'constructor', 'prototype'].includes(model.id) && !models.has(model.id)
        && typeof model.label === 'string', '段落提示包的模型列表无效。');
      models.add(model.id);
    }
    if (withPredictions) {
      require(object(raw.case_predictions) && Object.keys(raw.case_predictions).every((id) => byId.has(id))
        && typeof raw.risk_rule_description === 'string', '案例风险预测包结构无效。');
      for (const [caseId, predictions] of Object.entries(raw.case_predictions)) {
        require(Array.isArray(predictions), '案例风险预测列表无效。');
        const seen = new Set();
        for (const prediction of predictions) {
          require(fields(prediction, ['model', 'label', 'status', 'risk_found', 'risk_pair_count', 'reason', 'evidence_sections', 'decision_rule'],
            ['model', 'label', 'status', 'risk_found', 'risk_pair_count', 'reason', 'evidence_sections'])
            && models.has(prediction.model) && !seen.has(prediction.model) && typeof prediction.label === 'string'
            && ['available', 'pending', 'invalid'].includes(prediction.status), '案例风险预测的模型或状态无效。');
          seen.add(prediction.model);
          require([true, false, null].includes(prediction.risk_found)
            && (prediction.status === 'available' || prediction.risk_found === null), '未完成或无效预测不能给出风险判定。');
          require(prediction.risk_pair_count === null || (Number.isInteger(prediction.risk_pair_count) && prediction.risk_pair_count >= 0), '案例风险对数量无效。');
          require(typeof prediction.reason === 'string' && (prediction.decision_rule == null || typeof prediction.decision_rule === 'string')
            && Array.isArray(prediction.evidence_sections) && prediction.evidence_sections.every((id) => catalog[caseId].sections.includes(id)), '案例风险预测的说明或证据段落无效。');
        }
      }
    }
    require(object(raw.cases) && Object.keys(raw.cases).every((id) => byId.has(id)), '段落提示含未知案例。');
    for (const [caseId, sections] of Object.entries(raw.cases)) {
      require(object(sections) && Object.keys(sections).every((id) => catalog[caseId].sections.includes(id)), '段落提示引用了未知段落。');
      for (const section of Object.values(sections)) {
        require(fields(section, ['methods']) && object(section.methods) && Object.keys(section.methods).every((method) => METHODS.includes(method)), '段落提示的方法结构无效。');
        for (const method of Object.values(section.methods)) {
          require(fields(method, ['models']) && object(method.models) && Object.keys(method.models).every((id) => models.has(id)), '段落提示的模型身份不符。');
          for (const hint of Object.values(method.models)) {
            require(fields(hint, ['status', 'selected', 'score', 'rank', 'total_nodes', 'top3', 'conflict_endpoint_mentions', 'local_evidence_mentions', 'repair_entry_mentions', 'reason_zh', 'source_attempt', 'original_status'], ['status'])
              && ['available', 'not_run', 'strict_invalid', 'missing'].includes(hint.status), '段落提示状态无效。');
            require(hint.status !== 'available' || typeof hint.selected === 'boolean', '可用段落提示缺少纳入状态。');
            require(hint.selected == null || typeof hint.selected === 'boolean', '段落提示纳入状态无效。');
            require(hint.score == null || (typeof hint.score === 'number' && Number.isFinite(hint.score)), '段落提示分数无效。');
            for (const field of ['rank', 'total_nodes', 'conflict_endpoint_mentions', 'local_evidence_mentions', 'repair_entry_mentions']) {
              require(hint[field] == null || (Number.isInteger(hint[field]) && hint[field] >= 0), '段落提示统计值无效。');
            }
            require(hint.top3 == null || typeof hint.top3 === 'boolean', '段落提示排名状态无效。');
            require(hint.reason_zh == null || typeof hint.reason_zh === 'string', '段落提示说明无效。');
          }
        }
      }
    }
    return raw;
  }
  function emptyVisibility() { return { pack_hash: methodHints.pack_hash, ever_shown: false, shown_case_ids: [], events: [] }; }
  function validateVisibility(value) {
    require(fields(value, ['pack_hash', 'ever_shown', 'shown_case_ids', 'events']) && hash(value.pack_hash)
      && typeof value.ever_shown === 'boolean' && Array.isArray(value.shown_case_ids)
      && new Set(value.shown_case_ids).size === value.shown_case_ids.length && value.shown_case_ids.every((id) => byId.has(id))
      && Array.isArray(value.events), '提示显示历史无效。');
    for (const event of value.events) {
      require(fields(event, ['case_id', 'visible', 'at', 'reason', 'pack_hash']) && byId.has(event.case_id)
        && typeof event.visible === 'boolean' && timestamp(event.at) && hash(event.pack_hash)
        && ['toggle', 'case_navigation', 'restore_hidden', 'import_hidden'].includes(event.reason), '提示显示事件无效。');
    }
    const shown = [...new Set(value.events.filter((event) => event.visible).map((event) => event.case_id))].sort();
    require(canonical(shown) === canonical([...value.shown_case_ids].sort()) && value.ever_shown === (shown.length > 0), '提示显示历史前后不一致。');
    return value;
  }
  function mergeVisibility(...values) {
    const merged = emptyVisibility(), events = new Map();
    values.filter(Boolean).forEach((value) => {
      validateVisibility(value);
      value.events.forEach((event) => events.set(canonical(event), clone(event)));
    });
    merged.events = [...events.values()].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
    merged.shown_case_ids = data.cases.map((item) => item.id).filter((id) => merged.events.some((event) => event.case_id === id && event.visible));
    merged.ever_shown = merged.shown_case_ids.length > 0;
    return merged;
  }
  function syncVisibility(value = session) {
    value.schema_version = SCHEMA;
    value.hints_visible = hintsVisible;
    value.annotation_mode = value.hint_visibility.ever_shown ? 'method_assisted_review' : 'blind';
  }
  function normalizeSession(raw) {
    const value = clone(raw);
    value.hint_visibility = mergeVisibility(raw.schema_version === SCHEMA ? raw.hint_visibility : null);
    syncVisibility(value);
    return value;
  }
  function recordVisibility(caseId, visible, reason, value = session) {
    value.hint_visibility.events.push({ case_id: caseId, visible, at: now(), reason, pack_hash: methodHints.pack_hash });
    if (visible && !value.hint_visibility.shown_case_ids.includes(caseId)) value.hint_visibility.shown_case_ids.push(caseId);
    value.hint_visibility.ever_shown = value.hint_visibility.shown_case_ids.length > 0;
    value.hint_visibility = mergeVisibility(value.hint_visibility);
    syncVisibility(value);
  }
  function blankRecord(item) {
    return { case_id: item.id, content_hash: item.content_hash, target_conflict: null,
      judgment_sufficient: null, confidence: null,
      sections: Object.fromEntries(item.sections.map((section) => [section.id, { minimal_evidence: false, repair_material: false }])),
      notes: '', confirmed: false, sets_reviewed: false, confirmed_at: null, updated_at: null };
  }
  function currentItem() { return byId.get(activeCase); }
  function recordFor(item) { return own(session.annotations, item.id) ? session.annotations[item.id] : blankRecord(item); }
  function selected(record, field) { return Object.keys(record.sections).filter((id) => record.sections[id][field]); }
  function problems(record) {
    const errors = [];
    if (!['present', 'absent'].includes(record.target_conflict)) errors.push('请选择“存在”或“不存在”。');
    if (!['sufficient', 'insufficient'].includes(record.judgment_sufficient)) errors.push('请选择材料“充分”或“不充分”。');
    if (!Number.isInteger(record.confidence) || record.confidence < 1 || record.confidence > 5) errors.push('请选择 1–5 分的信心。');
    if (record.target_conflict === 'present' && record.judgment_sufficient === 'sufficient'
      && !selected(record, 'minimal_evidence').length) errors.push('判断“存在且充分”时，请至少选择一个最小证据段落。');
    if (Object.values(record.sections).some((section) => section.minimal_evidence && !section.repair_material)) errors.push('最小证据必须同时纳入修复材料。');
    return errors;
  }
  function validateBackup(raw) {
    const legacy = raw?.schema_version === LEGACY_SCHEMA;
    const allowed = Object.keys(emptySession()).filter((name) => !legacy || name !== 'hint_visibility');
    require(fields(raw, allowed) && (legacy || raw.schema_version === SCHEMA), '文件不是本页面的标注备份。');
    for (const name of ['study_id', 'manifest_hash', 'annotation_protocol', 'expert_id']) {
      require(raw[name] === data[name], `备份的 ${name} 与本批次不一致，未导入。`);
    }
    if (legacy) require(raw.annotation_mode === 'blind' && raw.hints_visible === false, '旧版备份的标注模式不符。');
    else {
      validateVisibility(raw.hint_visibility);
      require(typeof raw.hints_visible === 'boolean'
        && raw.annotation_mode === (raw.hint_visibility.ever_shown ? 'method_assisted_review' : 'blind')
        && (!raw.hints_visible || raw.hint_visibility.shown_case_ids.includes(raw.active_case_id)), '备份的显示状态与历史不一致。');
    }
    require(canonical(raw.case_catalog) === canonical(catalog), '备份的案例材料或段落身份与本批次不一致。');
    require(byId.has(raw.active_case_id) && ['zh', 'original'].includes(raw.display_language)
      && timestamp(raw.exported_at), '备份的导航状态或时间无效。');
    require(object(raw.annotations), '备份答案结构无效。');
    for (const [id, record] of Object.entries(raw.annotations)) {
      require(byId.has(id), '备份含未知案例。');
      const item = byId.get(id);
      require(fields(record, Object.keys(blankRecord(item))) && record.case_id === id
        && record.content_hash === item.content_hash, '备份答案字段或材料身份不符。');
      require([null, 'present', 'absent'].includes(record.target_conflict)
        && [null, 'sufficient', 'insufficient'].includes(record.judgment_sufficient)
        && (record.confidence === null || (Number.isInteger(record.confidence) && record.confidence >= 1 && record.confidence <= 5)), '备份含无效判断值。');
      require(typeof record.notes === 'string' && typeof record.confirmed === 'boolean'
        && typeof record.sets_reviewed === 'boolean', '备份含无效备注或确认状态。');
      require(object(record.sections) && canonical(Object.keys(record.sections).sort()) === canonical(item.sections.map((section) => section.id).sort()), '备份段落集合不匹配。');
      for (const answer of Object.values(record.sections)) {
        require(fields(answer, ['minimal_evidence', 'repair_material']) && typeof answer.minimal_evidence === 'boolean'
          && typeof answer.repair_material === 'boolean' && (!answer.minimal_evidence || answer.repair_material), '备份的材料勾选不合法。');
      }
      for (const name of ['updated_at', 'confirmed_at']) require(record[name] === null || timestamp(record[name]), '备份时间记录无效。');
      if (record.confirmed) require(record.sets_reviewed === true && record.confirmed_at !== null && !problems(record).length, '备份中已确认答案未满足完整性要求。');
      else require(record.confirmed_at === null && record.sets_reviewed === false, '未确认答案不能带有确认状态。');
    }
    return raw;
  }
  function loadSession() {
    let raw = null;
    try { raw = localStorage.getItem(storageKey); }
    catch (_) { storageAvailable = false; storageReadBlocked = true; }
    if (raw !== null) {
      try {
        const saved = validateBackup(JSON.parse(raw));
        session = normalizeSession(saved);
        if (saved.hints_visible) recordVisibility(saved.active_case_id, false, 'restore_hidden');
        persistSession();
        return;
      }
      catch (error) { corrupt = { raw, reason: error.message }; }
    }
    session = emptySession();
  }
  function persistSession() {
    if (storageReadBlocked) return;
    try { localStorage.setItem(storageKey, JSON.stringify(session)); storageAvailable = true; }
    catch (_) { storageAvailable = false; }
  }
  function showStorageNotice() {
    $('storageNotice').hidden = !corrupt && storageAvailable;
    $('storageNotice').textContent = corrupt
      ? `已有进度未通过校验，页面已停止改写。请先导出原始 JSON 备份，再导入正确的本批次文件。原因：${corrupt.reason}`
      : '浏览器无法安全读写本地存储，当前答案仅保留于页面内存。请及时导出 JSON，关闭页面前务必备份。';
    $('exportJsonBtn').textContent = corrupt ? '导出现有原始 JSON' : '导出 JSON 备份';
    $('exportCsvBtn').disabled = Boolean(corrupt);
  }
  function save(message = '已自动保存') {
    if (corrupt) return false;
    session.active_case_id = activeCase; session.display_language = language; session.exported_at = now();
    syncVisibility();
    persistSession();
    showStorageNotice();
    $('saveStatus').textContent = storageAvailable ? `${message} · ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}` : '仅保留于页面内存，请导出 JSON 备份';
    $('saveStatus').classList.toggle('error', !storageAvailable);
    return storageAvailable;
  }
  function filteredCases() {
    return data.cases.filter((item) => filter === 'all' || (filter === 'confirmed') === Boolean(recordFor(item).confirmed));
  }
  function renderList() {
    const completed = data.cases.filter((item) => recordFor(item).confirmed).length;
    const drafts = Object.values(session.annotations).filter((record) => !record.confirmed).length;
    $('progressText').textContent = `${completed} / ${data.cases.length} 已确认`;
    $('draftText').textContent = drafts ? `${drafts} 例草稿` : '';
    $('progressBar').max = data.cases.length; $('progressBar').value = completed;
    $('caseList').innerHTML = filteredCases().map((item) => {
      const record = recordFor(item), started = own(session.annotations, item.id);
      const status = record.confirmed ? '已确认' : started ? '待确认' : '未填写';
      return `<button type="button" class="case-item ${item.id === activeCase ? 'active' : ''}" data-case="${esc(item.id)}" ${item.id === activeCase ? 'aria-current="true"' : ''}>
        <span class="case-item-title">${esc(item.id)}</span><span class="${record.confirmed ? 'status-confirmed' : started ? 'status-draft' : 'muted'}">${status}</span></button>`;
    }).join('') || '<p class="empty-list">此筛选下暂无案例。</p>';
    updateNavigation();
  }
  function updateNavigation() {
    const cases = filteredCases(), index = cases.findIndex((item) => item.id === activeCase);
    $('previousBtn').disabled = index <= 0;
    $('nextBtn').disabled = !cases.length || index === cases.length - 1;
    $('confirmBtn').disabled = Boolean(corrupt);
    $('casePosition').textContent = `专家 3 · ${data.cases.indexOf(currentItem()) + 1} / ${data.cases.length}`;
  }
  function radios(name, choices, value) {
    return `<div class="choice-row">${choices.map(([id, label]) => `<label class="choice"><input type="radio" name="${name}" value="${id}" ${String(value) === String(id) ? 'checked' : ''}><span>${label}</span></label>`).join('')}</div>`;
  }
  function renderHintsControls() {
    $('toggleHintsBtn').textContent = hintsVisible ? '隐藏 SA/LEA 提示' : '显示 SA/LEA 提示';
    $('toggleHintsBtn').setAttribute('aria-pressed', String(hintsVisible));
    $('toggleHintsBtn').disabled = Boolean(corrupt);
    $('hintVisibilityStatus').textContent = hintsVisible
      ? '提示已显示，显示记录已保存。'
      : session.hint_visibility.ever_shown
        ? `提示当前隐藏；曾展示提示的 ${session.hint_visibility.shown_case_ids.length} 个案例已记录。`
        : 'SA/LEA 提示默认隐藏，可按需打开；你的答案保持不变。';
  }
  function toggleHints() {
    if (corrupt) return;
    hintsVisible = !hintsVisible;
    recordVisibility(activeCase, hintsVisible, 'toggle');
    renderCurrent(); save(hintsVisible ? '提示已显示，显示记录已保存' : '提示已隐藏，显示历史已保留');
  }
  function availableNodeHint(hint) { return object(hint) && hint.status === 'available' && typeof hint.selected === 'boolean'; }
  function renderModelHint(model, hint) {
    if (!availableNodeHint(hint)) {
      const status = { not_run: '尚未运行', strict_invalid: '无有效结果（校验失败）', missing: '缺少可核验结果', available: '结果信息不完整' }[hint?.status] || '暂无可核验结果';
      const reason = typeof hint?.reason_zh === 'string' && hint.reason_zh.trim() && hint.reason_zh !== status
        ? `<p class="node-hint-reason">${esc(hint.reason_zh)}</p>` : '';
      return `<div class="model-hint unavailable" data-model="${esc(model.id)}"><div class="model-hint-heading"><strong>${esc(model.label)}</strong><span class="selection-chip unavailable">${status}</span></div>${reason}</div>`;
    }
    const score = typeof hint.score === 'number' && Number.isFinite(hint.score) ? hint.score.toFixed(3) : '—';
    const hasRank = Number.isInteger(hint.rank) && hint.rank > 0, hasTotal = Number.isInteger(hint.total_nodes) && hint.total_nodes > 0;
    const rank = hasRank ? `第 ${hint.rank}${hasTotal ? ` / ${hint.total_nodes}` : ' 名'}` : '—';
    const top3 = hasRank ? hint.rank <= 3 : hint.top3 === true;
    const mentions = Number.isInteger(hint.conflict_endpoint_mentions) && hint.conflict_endpoint_mentions >= 0
      ? `<span>冲突端点提及 ${hint.conflict_endpoint_mentions} 次</span>` : '';
    return `<div class="model-hint ${hint.selected ? 'selected' : 'not-selected'}" data-model="${esc(model.id)}"><div class="model-hint-heading"><strong>${esc(model.label)}</strong><span class="selection-chip">${hint.selected ? '已纳入结果子图' : '未纳入结果子图'}</span></div>
      <div class="node-hint-metrics"><span>风险相关分 ${esc(score)}</span><span>排名 ${esc(rank)}</span>${top3 ? '<span class="top-three-chip">排名前三</span>' : ''}${mentions}</div></div>`;
  }
  function renderMethodHint(section, method) {
    const models = methodHints.cases[currentItem().id]?.[section.id]?.methods?.[method]?.models || {};
    const available = methodHints.models.map((model) => models[model.id]).filter(availableNodeHint);
    const included = available.filter((hint) => hint.selected).length;
    const summary = available.length ? `${included} / ${available.length} 个可用模型纳入该段` : '暂无可用结果';
    return `<section class="method-hint-card" data-method="${esc(method)}"><div class="method-hint-head"><h4>${METHOD_LABELS[method]}</h4><span>${summary}</span></div>
      <div class="model-hint-list">${methodHints.models.map((model) => renderModelHint(model, models[model.id])).join('')}</div></section>`;
  }
  function predictionCard(item, model) {
    const prediction = methodHints.case_predictions?.[item.id]?.find((entry) => entry.model === model.id);
    let title = '待运行', style = 'pending';
    if (prediction?.status === 'invalid') { title = '无有效结果'; style = 'unavailable'; }
    else if (prediction?.status === 'available') {
      if (prediction.risk_found === true) { title = '有风险'; style = 'risk'; }
      else if (prediction.risk_found === false) { title = '未判风险'; style = 'no-risk'; }
      else { title = '无有效结果'; style = 'unavailable'; }
    }
    const count = prediction?.status === 'available' && typeof prediction.risk_found === 'boolean'
      && Number.isInteger(prediction.risk_pair_count) && prediction.risk_pair_count >= 0
      ? `<p>报告的风险对：${prediction.risk_pair_count}</p>` : '';
    let evidence = '';
    if (prediction?.status === 'available' && prediction.evidence_sections.length) {
      const references = prediction.evidence_sections.map(esc).join('、');
      evidence = prediction.evidence_sections.length > 6
        ? `<details class="prediction-evidence"><summary>模型引用了 ${prediction.evidence_sections.length} 段 · 展开查看</summary><p>${references}</p></details>`
        : `<p>模型引用段落：${references}</p>`;
    }
    return `<article class="prediction-card ${style}" data-model="${esc(model.id)}"><div class="prediction-model">SA-MCGS · ${esc(model.label)}</div><div class="prediction-status">${title}</div>
      ${count}<p>${esc(prediction?.reason || (title === '待运行' ? '本例尚未提供该模型的有效预测。' : '请结合全文核对这一模型判定。'))}</p>${evidence}</article>`;
  }
  function renderPredictions(item) {
    if (!hintsVisible || methodHints.schema_version !== 'third_expert_method_hints.v2') return '';
    return `<section class="prediction-area" aria-label="SA 风险预测"><h3>SA 风险预测</h3>
      <div class="prediction-grid">${methodHints.models.map((model) => predictionCard(item, model)).join('')}</div>
      <p class="prediction-note">模型结果仅供参考，请独立核对原文。</p></section>`;
  }
  function sectionCard(section, record) {
    const answer = record.sections[section.id], translated = typeof section.zh_text === 'string' && Boolean(section.zh_text.trim());
    const useTranslation = language === 'zh' && translated;
    const heading = language === 'zh' && typeof section.zh_heading === 'string' && section.zh_heading.trim() ? section.zh_heading : section.heading;
    return `<article class="material-section" data-section="${esc(section.id)}"><h3><span class="section-id">${esc(section.id)}</span><span class="section-heading-text">${esc(heading || '原文段落')}</span></h3>
      ${language === 'zh' && !translated ? '<p class="translation-note">未提供中文译文，以下显示原文。</p>' : ''}<div class="section-text">${esc(useTranslation ? section.zh_text : section.original_text)}</div>
      <details class="original-panel"><summary>展开原文核对</summary><p class="original-heading">${esc(section.heading || '原文段落')}</p><div class="section-text">${esc(section.original_text)}</div></details>
      ${hintsVisible ? `<div class="method-hints" aria-label="SA-MCGS 与 LEA 逐段结果提示">${METHODS.map((method) => renderMethodHint(section, method)).join('')}</div>` : ''}
      <div class="section-choices"><label class="choice"><input type="checkbox" data-section-id="${esc(section.id)}" data-field="minimal_evidence" ${answer.minimal_evidence ? 'checked' : ''}>最小证据</label>
      <label class="choice"><input type="checkbox" data-section-id="${esc(section.id)}" data-field="repair_material" ${answer.repair_material ? 'checked' : ''}>修复材料</label></div></article>`;
  }
  function renderCurrent() {
    const item = currentItem(), record = recordFor(item);
    $('caseContent').innerHTML = `<header class="case-header"><h2>案例 ${esc(item.id)}</h2></header>
      ${renderPredictions(item)}
      <div id="validationMessage" class="validation-message" role="alert" hidden></div><div id="confirmationBanner"></div>
      <fieldset class="answers-fieldset" ${corrupt ? 'disabled' : ''}><section class="judgment-panel"><h3>你的判断</h3><div class="judgment-grid">
      <fieldset class="form-group"><legend>材料中是否存在目标风险或冲突？</legend>${radios('target_conflict', [['present', '存在'], ['absent', '不存在']], record.target_conflict)}</fieldset>
      <fieldset class="form-group"><legend>材料是否足以支持上述判断？</legend>${radios('judgment_sufficient', [['sufficient', '充分'], ['insufficient', '不充分']], record.judgment_sufficient)}</fieldset>
      <fieldset class="form-group confidence-group"><legend>对自己的判断有多大信心？</legend>${radios('confidence', [1, 2, 3, 4, 5].map((value) => [value, `${value} 分`]), record.confidence)}<p class="form-hint">1 分为很低，5 分为很高。“不充分”的判断不自动归为正例或负例。</p></fieldset></div></section>
      <div class="material-heading"><h3>完整材料 · ${item.sections.length} 段</h3><span id="selectionSummary" class="selection-summary"></span></div>
      <p class="form-hint material-intro">请核对两类材料集合。选入最小证据时会同时选入修复材料；移出修复材料时也会移出最小证据。</p>
      ${hintsVisible ? '<p class="form-hint material-intro">“未纳入结果子图”不等于无风险；缺失或失败的模型结果也不作无风险判断。</p>' : ''}
      ${item.sections.map((section) => sectionCard(section, record)).join('')}
      <section class="judgment-panel"><label class="notes-label" for="notesInput">备注 <span class="muted small">选填</span></label><textarea id="notesInput" placeholder="可记录判断理由、材料不足之处或需要核对的问题。">${esc(record.notes)}</textarea><p class="form-hint">完成判断并核对逐段选择后，请点击“确认并保存”。自动保存不会代替确认；再次修改答案后需要重新确认。</p></section></fieldset>`;
    renderMessage(); renderConfirmation(); updateSelectionSummary(); updateNavigation(); renderHintsControls();
    $('saveStatus').classList.remove('error');
    $('saveStatus').textContent = record.confirmed ? '本例已确认' : own(session.annotations, item.id) ? '草稿已保存，尚未确认' : '本例答案为空';
    showStorageNotice();
  }
  function renderMessage() { $('validationMessage').hidden = !validation; $('validationMessage').textContent = validation; }
  function renderConfirmation() {
    const record = recordFor(currentItem());
    $('confirmationBanner').innerHTML = record.confirmed
      ? `<p class="completion-banner">已确认 · ${esc(new Date(record.confirmed_at).toLocaleString('zh-CN'))}</p>`
      : own(session.annotations, activeCase) ? '<p class="completion-banner draft">当前为草稿，请核对全文与材料选择后确认。</p>' : '';
  }
  function updateSelectionSummary() {
    const record = recordFor(currentItem());
    $('selectionSummary').textContent = `最小证据 ${selected(record, 'minimal_evidence').length} 段 · 修复材料 ${selected(record, 'repair_material').length} 段`;
  }
  function edit(update) {
    if (corrupt) return;
    const item = currentItem(), before = recordFor(item), after = clone(before);
    update(after);
    if (canonical(before) === canonical(after)) return;
    after.confirmed = false; after.sets_reviewed = false; after.confirmed_at = null; after.updated_at = now();
    session.annotations[item.id] = after;
    validation = ''; renderMessage(); renderConfirmation(); updateSelectionSummary(); renderList(); save();
  }
  function confirmCurrent() {
    if (corrupt) return;
    const item = currentItem(), record = clone(recordFor(item)), errors = problems(record);
    if (errors.length) {
      validation = errors.join(' '); renderMessage(); $('validationMessage').scrollIntoView({ block: 'center', behavior: 'smooth' }); return;
    }
    if (!record.confirmed) {
      record.confirmed = true; record.sets_reviewed = true; record.confirmed_at = now(); record.updated_at = record.confirmed_at;
      session.annotations[item.id] = record;
    }
    validation = ''; renderMessage(); renderConfirmation(); renderList(); save('本例已确认并保存');
  }
  function navigate(id) {
    if (!byId.has(id)) return;
    if (!corrupt && hintsVisible && id !== activeCase) {
      recordVisibility(activeCase, false, 'case_navigation');
      recordVisibility(id, true, 'case_navigation');
    }
    activeCase = id; validation = ''; save('进度已保存'); renderList(); renderCurrent();
    $('caseContent').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
  function move(delta) {
    const cases = filteredCases(), index = cases.findIndex((item) => item.id === activeCase);
    const target = index < 0 ? (delta > 0 ? cases[0] : null) : cases[index + delta];
    if (target) navigate(target.id);
  }
  function download(content, extension, mime) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const link = document.createElement('a'); link.href = url;
    link.download = `expert3_annotations_${new Date().toISOString().replace(/[:.]/g, '-')}.${extension}`;
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportJson() {
    if (corrupt) { download(corrupt.raw, 'json', 'application/json'); return; }
    syncVisibility();
    const result = clone(session); result.exported_at = now();
    result.active_case_id = activeCase; result.display_language = language;
    download(JSON.stringify(result, null, 2), 'json', 'application/json');
    $('saveStatus').textContent = 'JSON 备份已导出，包含草稿与已确认答案';
  }
  function csvCell(value) {
    let text = value == null ? '' : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function exportCsv() {
    if (corrupt) return;
    syncVisibility();
    const columns = ['study_id', 'manifest_hash', 'annotation_mode', 'annotation_protocol', 'expert_id', 'hints_visible',
      'case_id', 'order', 'content_hash', 'target_conflict', 'judgment_sufficient', 'confidence',
      'minimal_evidence_sections', 'repair_material_sections', 'notes', 'confirmed', 'sets_reviewed', 'confirmed_at', 'updated_at',
      'hint_pack_hash', 'hints_ever_shown', 'hints_shown_case_ids', 'case_hints_ever_shown', 'case_hints_currently_visible',
      'hint_visibility_events', 'case_hint_visibility_events'];
    const rows = data.cases.map((item) => {
      const record = recordFor(item);
      return { ...record, study_id: data.study_id, manifest_hash: data.manifest_hash, annotation_mode: session.annotation_mode, annotation_protocol: PROTOCOL,
        expert_id: EXPERT, hints_visible: hintsVisible, order: item.order, minimal_evidence_sections: JSON.stringify(selected(record, 'minimal_evidence')),
        repair_material_sections: JSON.stringify(selected(record, 'repair_material')), hint_pack_hash: methodHints.pack_hash,
        hints_ever_shown: session.hint_visibility.ever_shown, hints_shown_case_ids: JSON.stringify(session.hint_visibility.shown_case_ids),
        case_hints_ever_shown: session.hint_visibility.shown_case_ids.includes(item.id), case_hints_currently_visible: hintsVisible && item.id === activeCase,
        hint_visibility_events: JSON.stringify(session.hint_visibility.events),
        case_hint_visibility_events: JSON.stringify(session.hint_visibility.events.filter((event) => event.case_id === item.id)) };
    });
    const text = [columns.map(csvCell).join(','), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(','))].join('\r\n');
    download('\uFEFF' + text, 'csv', 'text/csv;charset=utf-8');
    $('saveStatus').textContent = 'CSV 已导出；请同时保留可恢复进度的 JSON 备份';
  }
  async function importJson(file) {
    if (!file) return;
    try {
      require(file.size <= 25 * 1024 * 1024, '备份文件过大，请核对所选文件。');
      const raw = validateBackup(JSON.parse(await file.text()));
      const count = Object.values(raw.annotations).filter((record) => record.confirmed).length;
      if (!window.confirm(`导入本批次专家 3 的进度（${count}/${data.cases.length} 已确认）？\n如已有进度，将先保留一份本地备份。`)) return;
      let prior;
      try { prior = localStorage.getItem(storageKey); }
      catch (_) { throw new Error('无法读取已有进度，未覆盖。请先导出现有 JSON。'); }
      if (prior !== null) {
        try { localStorage.setItem(`${storageKey}:before_import:${Date.now()}`, prior); }
        catch (_) { throw new Error('无法安全备份现有进度，未覆盖。请先导出现有 JSON，并腾出浏览器存储空间。'); }
      }
      let persisted = null;
      if (prior !== null) {
        try { persisted = validateBackup(JSON.parse(prior)); } catch (_) { /* A confirmed import may restore a corrupt backup; its raw bytes are saved above. */ }
      }
      const restored = normalizeSession(raw);
      restored.hint_visibility = mergeVisibility(restored.hint_visibility, session.hint_visibility, persisted?.hint_visibility);
      const closingCases = new Set([
        ...(hintsVisible ? [activeCase] : []), ...(raw.hints_visible ? [raw.active_case_id] : []),
        ...(persisted?.hints_visible ? [persisted.active_case_id] : []),
      ]);
      hintsVisible = false;
      syncVisibility(restored);
      closingCases.forEach((id) => recordVisibility(id, false, 'import_hidden', restored));
      session = restored; corrupt = null; storageReadBlocked = false;
      activeCase = session.active_case_id; language = session.display_language; filter = 'all'; validation = '';
      $('languageSelect').value = language; $('completionFilter').value = filter;
      renderList(); renderCurrent(); save('本批次备份已恢复');
    } catch (error) { window.alert(`导入失败：${error.message}`); }
    finally { $('importFile').value = ''; }
  }
  function bind() {
    $('toggleHintsBtn').addEventListener('click', toggleHints);
    $('completionFilter').addEventListener('change', (event) => { filter = event.target.value; renderList(); });
    $('languageSelect').addEventListener('change', (event) => { language = event.target.value; save('材料显示方式已保存'); renderCurrent(); });
    $('caseList').addEventListener('click', (event) => { const button = event.target.closest('[data-case]'); if (button) navigate(button.dataset.case); });
    $('caseContent').addEventListener('change', (event) => {
      const input = event.target;
      if (input.matches('input[type=radio]') && ['target_conflict', 'judgment_sufficient', 'confidence'].includes(input.name)) {
        edit((record) => { record[input.name] = input.name === 'confidence' ? Number(input.value) : input.value; });
      } else if (input.matches('input[type=checkbox][data-section-id]')) {
        const id = input.dataset.sectionId, field = input.dataset.field;
        if (!own(recordFor(currentItem()).sections, id) || !['minimal_evidence', 'repair_material'].includes(field)) return;
        edit((record) => {
          record.sections[id][field] = input.checked;
          if (field === 'minimal_evidence' && input.checked) record.sections[id].repair_material = true;
          if (field === 'repair_material' && !input.checked) record.sections[id].minimal_evidence = false;
        });
        const answer = recordFor(currentItem()).sections[id];
        for (const checkbox of $('caseContent').querySelectorAll('input[data-section-id]')) {
          if (checkbox.dataset.sectionId === id) checkbox.checked = answer[checkbox.dataset.field];
        }
      }
    });
    $('caseContent').addEventListener('input', (event) => { if (event.target.id === 'notesInput') edit((record) => { record.notes = event.target.value; }); });
    $('confirmBtn').addEventListener('click', confirmCurrent);
    $('previousBtn').addEventListener('click', () => move(-1)); $('nextBtn').addEventListener('click', () => move(1));
    $('exportJsonBtn').addEventListener('click', exportJson); $('exportCsvBtn').addEventListener('click', exportCsv);
    $('importJsonBtn').addEventListener('click', () => $('importFile').click());
    $('importFile').addEventListener('change', (event) => importJson(event.target.files[0]));
    document.addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); confirmCurrent(); } });
  }
  try {
    data = validatePayload(JSON.parse($('payloadData').textContent));
    byId = new Map(data.cases.map((item) => [item.id, item]));
    catalog = Object.fromEntries(data.cases.map((item) => [item.id, { content_hash: item.content_hash, sections: item.sections.map((section) => section.id) }]));
    methodHints = prepareMethodHints(JSON.parse($('methodHintsData').textContent));
    storageKey = `third_expert_blind_v1:${data.study_id}:${data.manifest_hash}:${EXPERT}`;
    loadSession(); activeCase = session.active_case_id; language = session.display_language;
    $('languageSelect').value = language; $('app').hidden = false; bind(); renderList(); renderCurrent();
  } catch (error) {
    $('fatalError').hidden = false; $('app').hidden = true;
    $('fatalError').textContent = `页面未启动，原始标注备份未改写：${error.message}`;
  }
})();
