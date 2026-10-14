/* Offline main-experiment pre18 batch; exact, non-destructive predecessor migration. */
(() => {
  'use strict';
  const SCHEMA = 'pre30_reannotation.export.v1';
  const PROTOCOL = 'pre30_binary_judgment.v1';
  const MODE = 'method_assisted_reannotation';
  const EXPERTS = ['expert_1', 'expert_2', 'expert_3'];
  const HINT_METHODS = ['sa-mcgs', 'lea'];
  const METHOD_LABELS = { 'sa-mcgs': 'SA-MCGS', lea: 'LEA' };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const safeId = (value) => typeof value === 'string' && value.length > 0 && !['__proto__', 'constructor', 'prototype'].includes(value);
  const now = () => new Date().toISOString();
  const canonical = (value) => JSON.stringify(sortValue(value));
  function sortValue(value) {
    if (Array.isArray(value)) return value.map(sortValue);
    if (object(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortValue(value[key])]));
    return value;
  }
  function require(condition, message) { if (!condition) throw new Error(message); }
  let data, byId, catalog, baseKey, predecessorContext = null, historyPack = null;
  let expert = 'expert_1', activeCase = '', language = 'zh', filter = 'all', validation = '';
  let storageAvailable = true;
  const sessions = new Map(), corrupt = new Map();

  function validatePayload(payload) {
    require(object(payload) && payload.study_id === 'pre18_main_reannotation_20261010', '不是本次主实验法律案例标注批次。');
    require(typeof payload.schema_version === 'string' && payload.schema_version.length > 0, '样本包缺少版本。');
    for (const field of ['manifest_hash', 'prediction_pack_hash']) {
      require(/^(sha256:)?[a-f0-9]{64}$/.test(payload[field] || ''), '样本包身份校验字段不完整。');
    }
    require(Array.isArray(payload.models) && payload.models.length > 0, '缺少模型列表。');
    const models = new Set();
    payload.models.forEach((model) => {
      require(object(model) && safeId(model.id) && typeof model.label === 'string' && !models.has(model.id), '模型列表无效。');
      models.add(model.id);
    });
    require(Array.isArray(payload.cases) && payload.cases.length === 18, '本批次必须包含主实验中的 18 个法律案例。');
    const ids = new Set();
    for (const item of payload.cases) {
      require(object(item) && safeId(item.id) && !ids.has(item.id), '案例编号无效或重复。');
      ids.add(item.id);
      require(/^(sha256:)?[a-f0-9]{64}$/.test(item.content_hash || ''), `案例 ${item.id} 缺少材料身份。`);
      require(Array.isArray(item.sections) && item.sections.length > 0, `案例 ${item.id} 缺少原文。`);
      const sections = new Set();
      for (const section of item.sections) {
        require(object(section) && safeId(section.id) && !sections.has(section.id)
          && typeof section.original_text === 'string' && section.original_text.trim().length > 0,
        `案例 ${item.id} 的段落无效。`);
        require(section.zh_text == null || typeof section.zh_text === 'string', '译文必须是文字或空值。');
        sections.add(section.id);
      }
      require(Array.isArray(item.sa_predictions), `案例 ${item.id} 缺少预测列表。`);
      const predicted = new Set();
      item.sa_predictions.forEach((prediction) => {
        require(object(prediction) && models.has(prediction.model) && !predicted.has(prediction.model), '模型预测重复或身份不符。');
        predicted.add(prediction.model);
        require(['available', 'pending', 'invalid'].includes(prediction.status), '预测状态未知。');
        require([true, false, null].includes(prediction.risk_found), '预测判定必须是 true、false 或 null。');
        require(prediction.status === 'available' || prediction.risk_found === null, '未完成或无效预测不能给出风险判定。');
        require(Array.isArray(prediction.evidence_sections) && prediction.evidence_sections.every((id) => sections.has(id)), '预测证据引用了不存在的段落。');
      });
    }
    require(Array.from({ length: 18 }, (_, index) => `PRE-${String(index + 1).padStart(2, '0')}`).every((id) => ids.has(id)), '主实验案例范围必须为 PRE-01 至 PRE-18。');
    return payload;
  }

  function key(slot = expert) { return `${baseKey}:${slot}`; }
  function emptySession(slot) {
    return { schema_version: SCHEMA, annotation_protocol: PROTOCOL, annotation_mode: MODE, sa_visible: true,
      study_id: data.study_id, manifest_hash: data.manifest_hash, prediction_pack_hash: data.prediction_pack_hash,
      expert_id: slot, case_catalog: clone(catalog), active_case_id: data.cases[0].id,
      display_language: 'zh', annotations: {}, exported_at: now() };
  }
  function blankRecord(item) {
    return { case_id: item.id, content_hash: item.content_hash, target_conflict: null,
      judgment_sufficient: null, confidence: null,
      sections: Object.fromEntries(item.sections.map((section) => [section.id, { minimal_evidence: false, repair_material: false }])),
      notes: '', confirmed: false, sets_reviewed: false, confirmed_at: null, updated_at: null, sa_visible: true };
  }
  function session() { return sessions.get(expert); }
  function currentItem() { return byId.get(activeCase); }
  function recordFor(item) { return own(session().annotations, item.id) ? session().annotations[item.id] : blankRecord(item); }
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
  function validateBackup(raw, context = { identity: data, catalog, byId }) {
    require(object(raw) && raw.schema_version === SCHEMA && raw.annotation_protocol === PROTOCOL
      && raw.annotation_mode === MODE && raw.sa_visible === true, '文件不是本页面的模型辅助重新标注备份。');
    for (const field of ['study_id', 'manifest_hash', 'prediction_pack_hash']) {
      require(raw[field] === context.identity[field], `备份的 ${field} 与指定批次不一致，未导入。`);
    }
    require(EXPERTS.includes(raw.expert_id), '备份专家编号无效。');
    require(canonical(raw.case_catalog) === canonical(context.catalog), '备份的案例材料或段落身份与指定批次不一致。');
    require(context.byId.has(raw.active_case_id) && ['zh', 'original'].includes(raw.display_language), '备份导航状态无效。');
    require(object(raw.annotations), '备份答案结构无效。');
    for (const [id, record] of Object.entries(raw.annotations)) {
      require(context.byId.has(id) && object(record), '备份含未知案例或无效答案。');
      const item = context.byId.get(id);
      const permitted = Object.keys(blankRecord(item));
      require(Object.keys(record).every((name) => permitted.includes(name)) && permitted.every((name) => own(record, name)), '备份答案字段不完整或包含未知字段。');
      require(record.case_id === id && record.content_hash === item.content_hash && record.sa_visible === true, '备份答案的材料身份或模式不符。');
      require([null, 'present', 'absent'].includes(record.target_conflict)
        && [null, 'sufficient', 'insufficient'].includes(record.judgment_sufficient)
        && (record.confidence === null || (Number.isInteger(record.confidence) && record.confidence >= 1 && record.confidence <= 5)), '备份含无效判断值。');
      require(typeof record.notes === 'string' && typeof record.confirmed === 'boolean' && typeof record.sets_reviewed === 'boolean', '备份含无效备注或确认状态。');
      require(object(record.sections) && canonical(Object.keys(record.sections).sort()) === canonical(item.sections.map((section) => section.id).sort()), '备份段落集合不匹配。');
      for (const answer of Object.values(record.sections)) {
        require(object(answer) && Object.keys(answer).length === 2 && typeof answer.minimal_evidence === 'boolean'
          && typeof answer.repair_material === 'boolean' && (!answer.minimal_evidence || answer.repair_material), '备份的材料勾选不合法。');
      }
      for (const field of ['updated_at', 'confirmed_at']) {
        require(record[field] === null || (typeof record[field] === 'string' && Number.isFinite(Date.parse(record[field]))), '备份时间记录无效。');
      }
      if (record.confirmed) {
        require(record.sets_reviewed === true && record.confirmed_at !== null && problems(record).length === 0, '备份中“已确认”的答案未满足完整性要求。');
      } else require(record.confirmed_at === null && record.sets_reviewed === false, '未确认答案不应带有确认状态。');
    }
    if (own(raw, 'historical_import')) validateHistoryImport(raw);
    return raw;
  }

  function prepareHistory() {
    if (data.historical_annotations == null) return null;
    const pack = data.historical_annotations;
    require(object(pack) && pack.schema_version === 'pre18_historical_annotations.v1'
      && /^sha256:[a-f0-9]{64}$/.test(pack.pack_hash || ''), '历史标注包的版本或身份无效。');
    require(object(pack.experts) && canonical(Object.keys(pack.experts).sort()) === canonical(['expert_1', 'expert_2']), '历史标注仅应包含前两位专家。');
    const caseIds = data.cases.map((item) => item.id).sort();
    for (const slot of ['expert_1', 'expert_2']) {
      const source = pack.experts[slot];
      require(object(source) && object(source.annotations) && canonical(Object.keys(source.annotations).sort()) === canonical(caseIds), '每位专家的历史标注必须完整对应本页案例。');
      validateBackup({ ...emptySession(slot), annotations: source.annotations });
      require(Object.values(source.annotations).every((record) => record.confirmed), '历史标注中存在未完成答案。');
      require(object(source.provenance) && typeof source.provenance.source_file === 'string'
        && /^(sha256:)?[a-f0-9]{64}$/.test(source.provenance.source_sha256 || '')
        && /^(sha256:)?[a-f0-9]{64}$/.test(source.provenance.source_manifest_hash || ''), '历史标注缺少可核验来源。');
      require(object(source.case_provenance) && canonical(Object.keys(source.case_provenance).sort()) === canonical(caseIds), '历史案例来源不完整。');
      for (const item of data.cases) {
        const origin = source.case_provenance[item.id];
        require(object(origin) && typeof origin.source_presentation_id === 'string'
          && typeof origin.source_saved_at === 'string' && Number.isFinite(Date.parse(origin.source_saved_at))
          && origin.source_saved_at === source.annotations[item.id].confirmed_at
          && typeof origin.source_annotation_mode === 'string' && typeof origin.source_annotation_protocol === 'string'
          && object(origin.original_record) && Array.isArray(origin.section_mapping), '历史案例的原票、时间或模式记录无效。');
        require(origin.section_mapping.length === item.sections.length
          && new Set(origin.section_mapping.map((entry) => entry?.section_id)).size === item.sections.length
          && origin.section_mapping.every((entry) => object(entry) && safeId(entry.source_section_id)
            && item.sections.some((section) => section.id === entry.section_id && String(section.source_node_id) === String(entry.source_node_id))), '历史案例的段落映射不匹配。');
      }
    }
    return pack;
  }
  function validateHistoryImport(raw) {
    const imported = raw.historical_import, source = historyPack?.experts?.[raw.expert_id];
    require(object(imported) && source && imported.pack_hash === historyPack.pack_hash, '备份中的历史标注来源与本页不符。');
    require(Array.isArray(imported.seeded_case_ids) && new Set(imported.seeded_case_ids).size === imported.seeded_case_ids.length
      && imported.seeded_case_ids.every((id) => byId.has(id)), '备份中的历史补入案例列表无效。');
    for (const field of ['provenance', 'case_provenance']) {
      require(canonical(imported[field]) === canonical(source[field]), '备份中的历史来源记录已改变或不完整。');
    }
    require(canonical(imported.original_annotations) === canonical(source.annotations), '备份中的历史原票已改变或不完整。');
  }
  function withHistoricalDefaults(raw) {
    const source = historyPack?.experts?.[raw.expert_id];
    if (!source) return { value: raw, changed: false };
    const value = clone(raw), missing = data.cases.map((item) => item.id).filter((id) => !own(value.annotations, id));
    const changed = missing.length > 0 || !own(value, 'historical_import');
    if (!changed) return { value: raw, changed: false };
    // Keep a whole existing case, including a draft. Never merge individual answers.
    missing.forEach((id) => { value.annotations[id] = clone(source.annotations[id]); });
    if (!own(value, 'historical_import')) {
      value.historical_import = { pack_hash: historyPack.pack_hash, seeded_case_ids: [],
        provenance: clone(source.provenance), case_provenance: clone(source.case_provenance),
        original_annotations: clone(source.annotations) };
    }
    value.historical_import.seeded_case_ids = [...new Set([...value.historical_import.seeded_case_ids, ...missing])];
    return { value: validateBackup(value), changed: true };
  }
  function backupBeforeHistory(slot, raw) {
    if (raw === null) return;
    const backupKey = `${key(slot)}:before_history_seed:${historyPack.pack_hash}`;
    try {
      if (localStorage.getItem(backupKey) === null) localStorage.setItem(backupKey, raw);
    } catch (_) { throw new Error('无法安全备份历史补入前的已有进度，未覆盖。请先导出原始 JSON 并腾出浏览器存储空间。'); }
  }
  function installLoadedSession(raw, priorRaw, persist = false) {
    const seeded = withHistoricalDefaults(raw);
    if (seeded.changed) backupBeforeHistory(raw.expert_id, priorRaw);
    sessions.set(raw.expert_id, seeded.value);
    if (seeded.changed || persist) {
      try { localStorage.setItem(key(raw.expert_id), JSON.stringify(seeded.value)); storageAvailable = true; }
      catch (_) { storageAvailable = false; }
    }
  }
  function historicalReused(record, slot = expert) {
    const original = historyPack?.experts?.[slot]?.annotations?.[record.case_id];
    return Boolean(original && canonical(record) === canonical(original));
  }
  function annotationOrigin(record, slot = expert) {
    if (historicalReused(record, slot)) return 'historical_reused';
    if (record.confirmed) return 'current_round_confirmed';
    return own(sessions.get(slot).annotations, record.case_id) ? 'current_round_draft' : 'unfilled';
  }

  function preparePredecessor() {
    if (data.predecessor == null) return null;
    const previous = data.predecessor;
    require(object(previous) && previous.study_id === 'pre30_reannotation_20261010', '前任批次描述无效。');
    for (const field of ['manifest_hash', 'prediction_pack_hash']) {
      require(/^(sha256:)?[a-f0-9]{64}$/.test(previous[field] || ''), '前任批次身份校验字段不完整。');
    }
    require(object(previous.case_catalog) && Object.keys(previous.case_catalog).length === 30, '前任批次必须提供完整的原案例目录。');
    const oldIndex = new Map();
    for (let index = 1; index <= 30; index += 1) {
      const id = `PRE-${String(index).padStart(2, '0')}`;
      const item = previous.case_catalog[id];
      require(object(item) && /^(sha256:)?[a-f0-9]{64}$/.test(item.content_hash || ''), '前任批次案例目录不完整。');
      require(Array.isArray(item.sections) && item.sections.length > 0, '前任批次段落目录无效。');
      const sectionIds = new Set();
      for (const section of item.sections) {
        require(object(section) && safeId(section.id) && !sectionIds.has(section.id)
          && typeof section.source_node_id === 'string' && section.source_node_id.length > 0, '前任批次段落身份无效。');
        sectionIds.add(section.id);
      }
      oldIndex.set(id, { id, content_hash: item.content_hash, sections: item.sections });
    }
    for (const item of data.cases) {
      require(canonical(previous.case_catalog[item.id]) === canonical(catalog[item.id]), `案例 ${item.id} 与前任批次的材料或段落身份不一致，不能迁移。`);
    }
    return { identity: previous, catalog: previous.case_catalog, byId: oldIndex };
  }
  function predecessorKey(slot) {
    const previous = predecessorContext.identity;
    return `sa_mcgs_pre30_reannotation_v1:${previous.study_id}:${previous.manifest_hash}:${previous.prediction_pack_hash}:${slot}`;
  }
  function migratePredecessor(raw) {
    require(predecessorContext !== null, '本页未指定可迁移的前任批次。');
    const previous = validateBackup(raw, predecessorContext);
    const migrated = emptySession(previous.expert_id);
    migrated.annotations = Object.fromEntries(Object.entries(previous.annotations)
      .filter(([id]) => byId.has(id)).map(([id, record]) => [id, clone(record)]));
    migrated.active_case_id = byId.has(previous.active_case_id) ? previous.active_case_id : data.cases[0].id;
    migrated.display_language = previous.display_language;
    migrated.scope_migration = {
      version: 'pre30_to_main_pre18_v1', migrated_at: now(),
      source_study_id: previous.study_id, source_manifest_hash: previous.manifest_hash,
      source_prediction_pack_hash: previous.prediction_pack_hash,
      source_exported_at: typeof previous.exported_at === 'string' ? previous.exported_at : null,
      retained_case_ids: data.cases.map((item) => item.id),
      copied_annotation_ids: Object.keys(migrated.annotations),
      excluded_case_ids: Object.keys(previous.case_catalog).filter((id) => !byId.has(id)),
      excluded_annotation_ids: Object.keys(previous.annotations).filter((id) => !byId.has(id)),
    };
    return validateBackup(migrated);
  }
  function normalizeImportedBackup(raw) {
    if (object(raw) && predecessorContext && raw.study_id === predecessorContext.identity.study_id) {
      return migratePredecessor(raw);
    }
    return validateBackup(raw);
  }

  function loadExpert(slot) {
    if (sessions.has(slot)) return;
    let raw = null;
    try { raw = localStorage.getItem(key(slot)); } catch (_) { storageAvailable = false; }
    if (raw !== null) {
      try {
        const saved = validateBackup(JSON.parse(raw));
        require(saved.expert_id === slot, '存储中的专家编号不符。');
        installLoadedSession(saved, raw);
        return;
      } catch (error) { corrupt.set(slot, { raw, reason: error.message }); }
      sessions.set(slot, emptySession(slot));
      return;
    }
    if (predecessorContext) {
      let previousRaw = null;
      try { previousRaw = localStorage.getItem(predecessorKey(slot)); } catch (_) { storageAvailable = false; }
      if (previousRaw !== null) {
        try {
          const migrated = migratePredecessor(JSON.parse(previousRaw));
          require(migrated.expert_id === slot, '前任存储中的专家编号不符。');
          // Only the new key is written. The exact predecessor key/raw is untouched.
          installLoadedSession(migrated, null, true);
          return;
        } catch (error) { corrupt.set(slot, { raw: previousRaw, reason: `前任进度未迁移：${error.message}` }); }
      }
    }
    if (corrupt.has(slot)) sessions.set(slot, emptySession(slot));
    else installLoadedSession(emptySession(slot), null);
  }
  function showStorageNotice() {
    const issue = corrupt.get(expert);
    const migrated = session().scope_migration?.version === 'pre30_to_main_pre18_v1';
    $('scopeMigrationNotice').hidden = !migrated;
    $('scopeMigrationNotice').textContent = migrated ? '已恢复旧批次中属于这 18 例的进度；旧存储和原始备份未改动。' : '';
    $('storageNotice').hidden = !issue && storageAvailable;
    $('storageNotice').textContent = issue
      ? `当前专家的已有进度未通过校验，页面已停止改写。请先导出原始 JSON 备份，再导入正确的本批次文件。原因：${issue.reason}`
      : '浏览器无法写入本地存储，当前答案仅在此页面内存中。请及时导出 JSON；关闭页面会丢失尚未备份的进度。';
    $('exportJsonBtn').textContent = issue ? '导出现有原始 JSON' : '导出 JSON 备份';
    $('exportCsvBtn').disabled = Boolean(issue);
  }
  function save(message = '已自动保存') {
    if (corrupt.has(expert)) return false;
    const current = session();
    current.active_case_id = activeCase;
    current.display_language = language;
    current.exported_at = now();
    try { localStorage.setItem(key(), JSON.stringify(current)); storageAvailable = true; }
    catch (_) { storageAvailable = false; }
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
    const historical = data.cases.filter((item) => historicalReused(recordFor(item))).length;
    const drafts = Object.values(session().annotations).filter((record) => !record.confirmed).length;
    const hasHistoricalSource = Boolean(historyPack?.experts?.[expert]);
    $('progressText').textContent = hasHistoricalSource
      ? `${Object.keys(session().annotations).length} / ${data.cases.length} 已有标注` : `${completed} / ${data.cases.length} 已完成`;
    $('draftText').textContent = hasHistoricalSource
      ? `沿用 ${historical} · 本轮确认 ${completed - historical} · 待确认 ${drafts}` : drafts ? `${drafts} 例草稿` : '';
    $('progressBar').max = data.cases.length;
    $('progressBar').value = completed;
    $('caseList').innerHTML = filteredCases().map((item) => {
      const record = recordFor(item), started = own(session().annotations, item.id);
      const status = historicalReused(record) ? '历史已完成' : record.confirmed ? '本轮已确认' : started ? '待确认' : '未填写';
      return `<button type="button" class="case-item ${item.id === activeCase ? 'active' : ''}" data-case="${esc(item.id)}" ${item.id === activeCase ? 'aria-current="true"' : ''}>
        <span class="case-number">${esc(String(item.order).padStart(2, '0'))}</span><span class="case-item-main"><span class="case-item-title">${esc(item.source_label || `案例 ${item.order}`)}</span>
        <span class="case-item-meta"><span>${esc(item.domain)}</span><span class="${record.confirmed ? 'status-confirmed' : started ? 'status-draft' : ''}">${status}</span></span></span></button>`;
    }).join('') || '<p class="empty-list">此筛选下暂无案例。</p>';
    updateNavigation();
  }
  function updateNavigation() {
    const cases = filteredCases(), index = cases.findIndex((item) => item.id === activeCase);
    $('previousBtn').disabled = index <= 0;
    $('nextBtn').disabled = !cases.length || index === cases.length - 1;
    $('confirmBtn').disabled = corrupt.has(expert);
    $('casePosition').textContent = `专家 ${expert.slice(-1)}${expert === 'expert_3' ? ' · 争议复核' : ''} · 案例 ${currentItem().order} / ${data.cases.length}`;
  }
  function predictionCard(item, model) {
    const prediction = item.sa_predictions.find((entry) => entry.model === model.id);
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
    return `<article class="prediction-card ${style}"><div class="prediction-model">SA-MCGS · ${esc(model.label)}</div><div class="prediction-status">${title}</div>
      ${count}<p>${esc(prediction?.reason || (title === '待运行' ? '本例尚未提供该模型的有效预测。' : '请结合全文核对这一模型判定。'))}</p>${evidence}</article>`;
  }
  function radios(name, choices, value) {
    return `<div class="choice-row">${choices.map(([id, label]) => `<label class="choice"><input type="radio" name="${name}" value="${id}" ${String(value) === String(id) ? 'checked' : ''}><span>${label}</span></label>`).join('')}</div>`;
  }
  function availableNodeHint(hint) {
    return object(hint) && hint.status === 'available' && typeof hint.selected === 'boolean';
  }
  function renderModelHint(model, hint) {
    if (!availableNodeHint(hint)) {
      const status = {
        not_run: '尚未运行', strict_invalid: '无有效结果（校验失败）',
        missing: '缺少可核验结果', available: '结果信息不完整',
      }[hint?.status] || '暂无可核验结果';
      const reason = typeof hint?.reason_zh === 'string' && hint.reason_zh.trim() && hint.reason_zh !== status
        ? `<p class="node-hint-reason">${esc(hint.reason_zh)}</p>` : '';
      return `<div class="model-hint unavailable" data-model="${esc(model.id)}"><div class="model-hint-heading"><strong>${esc(model.label)}</strong><span class="selection-chip unavailable">${status}</span></div>${reason}</div>`;
    }
    const score = typeof hint.score === 'number' && Number.isFinite(hint.score) ? hint.score.toFixed(3) : '—';
    const hasRank = Number.isInteger(hint.rank) && hint.rank > 0;
    const hasTotal = Number.isInteger(hint.total_nodes) && hint.total_nodes > 0;
    const rank = hasRank ? `第 ${hint.rank}${hasTotal ? ` / ${hint.total_nodes}` : ' 名'}` : '—';
    const top3 = hasRank ? hint.rank <= 3 : hint.top3 === true;
    const mentions = Number.isInteger(hint.conflict_endpoint_mentions) && hint.conflict_endpoint_mentions >= 0
      ? `<span>冲突端点提及 ${hint.conflict_endpoint_mentions} 次</span>` : '';
    return `<div class="model-hint ${hint.selected ? 'selected' : 'not-selected'}" data-model="${esc(model.id)}">
      <div class="model-hint-heading"><strong>${esc(model.label)}</strong><span class="selection-chip">${hint.selected ? '已纳入结果子图' : '未纳入结果子图'}</span></div>
      <div class="node-hint-metrics"><span>风险相关分 ${esc(score)}</span><span>排名 ${esc(rank)}</span>${top3 ? '<span class="top-three-chip">排名前三</span>' : ''}${mentions}</div></div>`;
  }
  function renderMethodHint(item, section, method) {
    const methodData = data.node_results?.[item.id]?.[section.id]?.methods?.[method];
    const models = object(methodData?.models) ? methodData.models : {};
    const available = data.models.map((model) => models[model.id]).filter(availableNodeHint);
    const included = available.filter((hint) => hint.selected === true).length;
    const summary = available.length ? `${included} / ${available.length} 个可用模型纳入该段` : '暂无可用结果';
    return `<section class="method-hint-card" data-method="${esc(method)}"><div class="method-hint-head"><h4>${METHOD_LABELS[method]}</h4><span>${summary}</span></div>
      <div class="model-hint-list">${data.models.map((model) => renderModelHint(model, models[model.id])).join('')}</div></section>`;
  }
  function sectionCard(section, record) {
    const answer = record.sections[section.id];
    const translated = typeof section.zh_text === 'string' && Boolean(section.zh_text.trim());
    const useTranslation = language === 'zh' && translated;
    const heading = language === 'zh' && typeof section.zh_heading === 'string' && section.zh_heading.trim()
      ? section.zh_heading : section.heading;
    const note = language === 'zh' && !translated ? '<p class="translation-note">未提供中文译文，以下显示原文。</p>' : '';
    return `<article class="material-section" data-section="${esc(section.id)}"><h3><span class="section-id">${esc(section.id)}</span><span class="section-heading-text">${esc(heading || '原文段落')}</span></h3>
      ${note}<div class="section-text">${esc(useTranslation ? section.zh_text : section.original_text)}</div>
      <details class="original-panel"><summary>展开原文核对</summary><p class="original-heading">${esc(section.heading || '原文段落')}</p><div class="section-text">${esc(section.original_text)}</div></details>
      <div class="method-hints" aria-label="SA-MCGS 与 LEA 逐段结果提示">${HINT_METHODS.map((method) => renderMethodHint(currentItem(), section, method)).join('')}</div>
      <div class="section-choices"><label class="choice"><input type="checkbox" data-section-id="${esc(section.id)}" data-field="minimal_evidence" ${answer.minimal_evidence ? 'checked' : ''}>最小证据</label>
      <label class="choice"><input type="checkbox" data-section-id="${esc(section.id)}" data-field="repair_material" ${answer.repair_material ? 'checked' : ''}>修复材料</label></div></article>`;
  }
  function renderCurrent() {
    const item = currentItem(), record = recordFor(item);
    $('caseContent').innerHTML = `<header class="case-header"><p class="case-kicker">${esc(item.domain)} · 未注入原文</p><h2>案例 ${esc(item.order)}</h2><p class="source-label">${esc(item.source_label)}</p></header>
      <section class="prediction-area" aria-label="SA 风险预测"><div class="section-heading"><h3>SA 风险预测</h3><span class="muted small">模型判断 · 非人工答案</span></div>
      <div class="prediction-grid">${data.models.map((model) => predictionCard(item, model)).join('')}</div>
      <p class="prediction-note">“未判风险”是该模型的输出，不等于材料已经证明无风险。“无有效结果”和“待运行”均不作负例判断；模型提示不会自动勾选人工答案。</p></section>
      <div id="validationMessage" class="validation-message" role="alert" hidden></div>
      <div id="confirmationBanner"></div>
      <fieldset class="answers-fieldset" ${corrupt.has(expert) ? 'disabled' : ''}><section class="judgment-panel"><h3>你的判断</h3><div class="judgment-grid">
      <fieldset class="form-group"><legend>材料中是否存在目标风险或冲突？</legend>${radios('target_conflict', [['present', '存在'], ['absent', '不存在']], record.target_conflict)}</fieldset>
      <fieldset class="form-group"><legend>材料是否足以支持上述判断？</legend>${radios('judgment_sufficient', [['sufficient', '充分'], ['insufficient', '不充分']], record.judgment_sufficient)}</fieldset>
      <fieldset class="form-group confidence-group"><legend>对自己的判断有多大信心？</legend>${radios('confidence', [1, 2, 3, 4, 5].map((value) => [value, `${value} 分`]), record.confidence)}<p class="form-hint">1 分为很低，5 分为很高。“不充分”的判断会保留为待复核，不自动归为正例或负例。</p></fieldset></div></section>
      <div class="material-heading"><h3>完整材料 · ${item.sections.length} 段</h3><span id="selectionSummary" class="selection-summary"></span></div>
      <p class="form-hint">请核对两类材料集合。选入最小证据时会同时选入修复材料；移出修复材料时也会移出最小证据。</p>
      <p class="form-hint">每段展示 SA-MCGS 和 LEA 的模型结果；“未纳入结果子图”不等于无风险，缺失或失败的结果也不作无风险判断。</p>
      ${item.sections.map((section) => sectionCard(section, record)).join('')}
      <section class="judgment-panel"><label class="notes-label" for="notesInput">备注 <span class="muted small">选填</span></label><textarea id="notesInput" placeholder="可记录判断理由、材料不足之处或需要核对的问题。">${esc(record.notes)}</textarea><p class="form-hint">完成判断并核对逐段选择后，请点击“确认并保存”。自动保存不会代替确认；再次修改答案后需要重新确认。</p></section></fieldset>`;
    renderMessage(); renderConfirmation(); updateSelectionSummary(); updateNavigation();
    $('saveStatus').classList.remove('error');
    $('saveStatus').textContent = historicalReused(record) ? '沿用原标注 · 历史已完成' : record.confirmed ? '本例已在本轮确认' : own(session().annotations, item.id) ? '草稿已保存，尚未确认' : '本例答案为空';
    showStorageNotice();
  }
  function renderMessage() {
    $('validationMessage').hidden = !validation;
    $('validationMessage').textContent = validation;
  }
  function renderConfirmation() {
    const record = recordFor(currentItem());
    $('confirmationBanner').innerHTML = historicalReused(record)
      ? `<p class="completion-banner">沿用原标注 · 历史已完成<br><span class="small">原保存时间：${esc(new Date(record.confirmed_at).toLocaleString('zh-CN'))}。只需修改需要重标的项目。</span></p>`
      : record.confirmed ? `<p class="completion-banner">本轮已确认 · ${esc(new Date(record.confirmed_at).toLocaleString('zh-CN'))}</p>`
      : own(session().annotations, activeCase) ? '<p class="completion-banner draft">当前为草稿，请核对全文与材料选择后确认。</p>' : '';
  }
  function updateSelectionSummary() {
    const record = recordFor(currentItem());
    $('selectionSummary').textContent = `最小证据 ${selected(record, 'minimal_evidence').length} 段 · 修复材料 ${selected(record, 'repair_material').length} 段`;
  }
  function edit(update) {
    if (corrupt.has(expert)) return;
    const item = currentItem(), before = recordFor(item), after = clone(before);
    update(after);
    if (canonical(before) === canonical(after)) return;
    after.confirmed = false; after.sets_reviewed = false; after.confirmed_at = null; after.updated_at = now();
    session().annotations[item.id] = after;
    validation = ''; renderMessage(); renderConfirmation(); updateSelectionSummary(); renderList(); save();
  }
  function confirmCurrent() {
    if (corrupt.has(expert)) return;
    const item = currentItem(), record = clone(recordFor(item)), errors = problems(record);
    if (errors.length) {
      validation = errors.join(' '); renderMessage();
      $('validationMessage').scrollIntoView({ block: 'center', behavior: 'smooth' });
      return;
    }
    if (!record.confirmed) {
      record.confirmed = true; record.sets_reviewed = true; record.confirmed_at = now(); record.updated_at = record.confirmed_at;
      session().annotations[item.id] = record;
    }
    validation = ''; renderMessage(); renderConfirmation(); renderList();
    save(historicalReused(record) ? '沿用原标注 · 历史已完成' : '本例已在本轮确认并保存');
  }
  function navigate(id) {
    if (!byId.has(id)) return;
    activeCase = id; validation = ''; save('进度已保存'); renderList(); renderCurrent();
    $('caseContent').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
  function move(delta) {
    const cases = filteredCases(), index = cases.findIndex((item) => item.id === activeCase);
    const target = index < 0 ? (delta > 0 ? cases[0] : null) : cases[index + delta];
    if (target) navigate(target.id);
  }
  function filename(extension, slot = expert) {
    return `${data.study_id}_${slot}_${new Date().toISOString().replace(/[:.]/g, '-')}.${extension}`;
  }
  function download(content, extension, mime) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const link = document.createElement('a'); link.href = url; link.download = filename(extension);
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportJson() {
    if (corrupt.has(expert)) { download(corrupt.get(expert).raw, 'json', 'application/json'); return; }
    const result = clone(session()); result.exported_at = now();
    // Export-only metadata leaves stored answer schemas and legacy imports intact.
    // This snapshot describes the hints provided by this page at export time.
    result.method_hints_visible = [...HINT_METHODS];
    result.node_results_pack_hash = typeof data.node_results_pack_hash === 'string' ? data.node_results_pack_hash : null;
    result.node_results = Object.fromEntries(data.cases.filter((item) => object(data.node_results?.[item.id]))
      .map((item) => [item.id, clone(data.node_results[item.id])]));
    result.annotation_mode_scope = 'current_page_context';
    result.annotation_provenance = Object.fromEntries(data.cases.map((item) => [item.id, {
      annotation_origin: annotationOrigin(recordFor(item)), historical_reused: historicalReused(recordFor(item)),
      historical_pack_hash: session().historical_import?.pack_hash || null,
    }]));
    download(JSON.stringify(result, null, 2), 'json', 'application/json');
    $('saveStatus').textContent = 'JSON 备份已导出，包含草稿与已确认答案';
  }
  function csvCell(value) {
    let text = value == null ? '' : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function exportCsv() {
    if (corrupt.has(expert)) return;
    const columns = ['study_id', 'manifest_hash', 'prediction_pack_hash', 'annotation_mode', 'annotation_protocol', 'sa_visible',
      'expert_id', 'case_id', 'order', 'domain', 'source_label', 'content_hash', 'target_conflict', 'judgment_sufficient', 'confidence',
      'minimal_evidence_sections', 'repair_material_sections', 'minimal_evidence_source_nodes', 'repair_material_source_nodes',
      'notes', 'confirmed', 'sets_reviewed', 'confirmed_at', 'updated_at', 'sa_predictions',
      'method_hints_visible', 'node_results_pack_hash', 'node_results', 'annotation_mode_scope',
      'annotation_origin', 'historical_reused', 'historical_pack_hash',
      'historical_source_provenance', 'historical_case_provenance', 'historical_original_annotation'];
    const rows = data.cases.map((item) => {
      const record = recordFor(item);
      const sourceNodes = (field) => item.sections.filter((section) => record.sections[section.id][field]).map((section) => section.source_node_id);
      return { ...record, study_id: data.study_id, manifest_hash: data.manifest_hash, prediction_pack_hash: data.prediction_pack_hash,
        annotation_mode: MODE, annotation_protocol: PROTOCOL, sa_visible: true, expert_id: expert, order: item.order, domain: item.domain, source_label: item.source_label,
        minimal_evidence_sections: JSON.stringify(selected(record, 'minimal_evidence')), repair_material_sections: JSON.stringify(selected(record, 'repair_material')),
        minimal_evidence_source_nodes: JSON.stringify(sourceNodes('minimal_evidence')), repair_material_source_nodes: JSON.stringify(sourceNodes('repair_material')),
        sa_predictions: JSON.stringify(item.sa_predictions), method_hints_visible: JSON.stringify(HINT_METHODS),
        node_results_pack_hash: typeof data.node_results_pack_hash === 'string' ? data.node_results_pack_hash : null,
        node_results: JSON.stringify(object(data.node_results?.[item.id]) ? data.node_results[item.id] : {}),
        annotation_mode_scope: 'current_page_context', annotation_origin: annotationOrigin(record),
        historical_reused: historicalReused(record), historical_pack_hash: session().historical_import?.pack_hash || '',
        historical_source_provenance: JSON.stringify(session().historical_import?.provenance || null),
        historical_case_provenance: JSON.stringify(session().historical_import?.case_provenance?.[item.id] || null),
        historical_original_annotation: JSON.stringify(session().historical_import?.original_annotations?.[item.id] || null) };
    });
    const text = [columns.map(csvCell).join(','), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(','))].join('\r\n');
    download('\uFEFF' + text, 'csv', 'text/csv;charset=utf-8');
    $('saveStatus').textContent = 'CSV 已导出；请同时保留可恢复进度的 JSON 备份';
  }
  async function importJson(file) {
    if (!file) return;
    try {
      require(file.size <= 25 * 1024 * 1024, '备份文件过大，请核对是否选择了本页面导出的 JSON。');
      const parsed = JSON.parse(await file.text());
      const raw = withHistoricalDefaults(normalizeImportedBackup(parsed)).value;
      const count = Object.values(raw.annotations).filter((record) => record.confirmed).length;
      const migrationNote = parsed.study_id !== data.study_id
        ? `\n只保留本页 ${data.cases.length} 例的答案，其余案例不进入本批次；原始文件不会改动。` : '';
      const historyNote = raw.historical_import ? '\n缺失案例沿用该专家的历史原标注；文件中已有答案或草稿保持不变。' : '';
      if (!window.confirm(`导入专家 ${raw.expert_id.slice(-1)} 的进度（${count}/${data.cases.length} 已完成）？${migrationNote}${historyNote}\n只更新该专家；如已有进度，将先保留一份本地备份。`)) return;
      let prior = null;
      try { prior = localStorage.getItem(key(raw.expert_id)); }
      catch (_) { throw new Error('无法读取该专家的已有进度，未覆盖。请先导出现有 JSON。'); }
      if (prior !== null) {
        try { localStorage.setItem(`${key(raw.expert_id)}:before_import:${Date.now()}`, prior); }
        catch (_) { throw new Error('无法安全备份该专家的现有进度，未覆盖。请先导出现有 JSON，并腾出浏览器存储空间。'); }
      }
      if (raw.historical_import) backupBeforeHistory(raw.expert_id, prior);
      sessions.set(raw.expert_id, clone(raw)); corrupt.delete(raw.expert_id);
      expert = raw.expert_id; activeCase = raw.active_case_id; language = raw.display_language; filter = 'all'; validation = '';
      $('expertSelect').value = expert; $('languageSelect').value = language; $('completionFilter').value = filter;
      renderList(); renderCurrent(); save('本批次备份已恢复');
    } catch (error) { window.alert(`导入失败：${error.message}`); }
    finally { $('importFile').value = ''; }
  }
  function bind() {
    $('expertSelect').addEventListener('change', (event) => {
      save(); expert = event.target.value; loadExpert(expert); activeCase = session().active_case_id; language = session().display_language;
      filter = 'all'; validation = ''; $('completionFilter').value = filter; $('languageSelect').value = language;
      renderList(); renderCurrent();
    });
    $('completionFilter').addEventListener('change', (event) => { filter = event.target.value; renderList(); });
    $('languageSelect').addEventListener('change', (event) => { language = event.target.value; save('材料显示方式已保存'); renderCurrent(); });
    $('caseList').addEventListener('click', (event) => { const button = event.target.closest('[data-case]'); if (button) navigate(button.dataset.case); });
    $('caseContent').addEventListener('change', (event) => {
      const input = event.target;
      if (input.matches('input[type=radio]')) {
        edit((record) => { record[input.name] = input.name === 'confidence' ? Number(input.value) : input.value; });
      } else if (input.matches('input[type=checkbox][data-section-id]')) {
        const id = input.dataset.sectionId, field = input.dataset.field;
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
    data.cases.sort((a, b) => a.order - b.order);
    byId = new Map(data.cases.map((item) => [item.id, item]));
    catalog = Object.fromEntries(data.cases.map((item) => [item.id, { content_hash: item.content_hash,
      sections: item.sections.map((section) => ({ id: section.id, source_node_id: section.source_node_id })) }]));
    baseKey = `sa_mcgs_pre30_reannotation_v1:${data.study_id}:${data.manifest_hash}:${data.prediction_pack_hash}`;
    predecessorContext = preparePredecessor();
    historyPack = prepareHistory();
    loadExpert(expert); activeCase = session().active_case_id; language = session().display_language;
    $('languageSelect').value = language; $('app').hidden = false; bind(); renderList(); renderCurrent();
  } catch (error) {
    $('fatalError').hidden = false;
    $('fatalError').textContent = `页面未启动，原始标注备份未改写：${error.message}`;
  }
})();
