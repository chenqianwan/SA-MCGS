/* Two binary case judgments; preserve independent evidence/repair selections. */
let binaryDirtyContext = null;

function binaryContextKey() {
  return `${state.activeExpert}:${currentCase()?.presentation_id || ''}`;
}

function binaryLegacyRecord(annotation) {
  if (annotation.legacy_annotation) return annotation.legacy_annotation;
  return Object.keys(annotation).length && annotation.annotation_protocol !== ANNOTATION_PROTOCOL
    ? annotation : null;
}

function binaryLegacyNotice(annotation) {
  const legacy = binaryLegacyRecord(annotation);
  if (!legacy) return '';
  return `<details class="legacy-judgment-record"><summary>旧版判断记录（只读保留）</summary>
    <p>目标冲突：${esc(targetLabel(legacy.target_conflict) || '未填写')}；旧“定位问题”充分性：${esc(sufficiencyLabel(legacy.evidence_sufficient) || '未填写')}；旧“更多上下文”：${esc(contextLabel(legacy.need_more_context) || '未填写')}。</p>
    <p>旧“存在／不存在”选择原样展示；新的“是否足够支持上述判断”请重新明确选择，不从旧充分性自动推断。</p></details>`;
}

const renderAssistedParagraphBeforeBinary = renderParagraph;
renderParagraph = function renderBinaryParagraph(item, section, index) {
  const oldHtml = renderAssistedParagraphBeforeBinary(item, section, index);
  const marker = '    <div class="paragraph-form">';
  const insertion = oldHtml.indexOf(marker);
  if (insertion < 0) throw new Error('段落标注区域结构发生变化。');
  const record = annotationFor(item.presentation_id).sections?.[section.section_id] || {};
  const group = `section_role_${section.section_id}`;
  const roles = ['conflict_evidence', 'supporting_context', 'ordinary_context', 'uncertain'];
  return oldHtml.slice(0, insertion) + `<div class="paragraph-form">
      <h4>该段应纳入哪些材料？</h4>
      <div class="check-grid">
        <label class="check-option"><input type="checkbox" data-minimal-evidence ${record.minimal_evidence ? 'checked' : ''}> <span><b>纳入最小证据集</b><br>证明目标冲突不可缺少的证据。</span></label>
        <label class="check-option"><input type="checkbox" data-repair-packet ${record.repair_packet ? 'checked' : ''}> <span><b>纳入修复材料</b><br>审阅、解释或提出修复建议时应保留的材料。</span></label>
      </div>
      <p class="local-note">最小证据属于修复材料；两项都不选表示不纳入以上集合，整例确认后才视为已检查。</p>
      <details class="section-extras"><summary>补充判断与备注（选填）</summary>
        <p class="local-note">段落角色仅供补充解释，不替代上面的两个集合选择。</p>
        <div class="radio-list">
          ${roles.map((role) => `<label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="${role}" ${selected(record.role, role)}> <span>${esc(roleLabel(role))}</span></label>`).join('')}
          <label class="radio-option"><input type="radio" name="${esc(group)}" data-section-role value="" ${record.role ? '' : 'checked'}> <span>不填写角色</span></label>
        </div>
        <textarea data-section-note placeholder="可选：记录本段判断理由或需要复核之处">${esc(record.note || '')}</textarea>
      </details>
    </div>
  </article>`;
};

function updateBinaryReviewNotice() {
  const root = $('workspace');
  if (!root) return;
  const notice = $('binaryReviewNotice');
  const value = root.querySelector('input[name="judgment_sufficient"]:checked')?.value;
  if (notice) notice.hidden = value !== 'no';
  const status = $('setsReviewStatus');
  if (status) {
    const annotation = annotationFor(currentCase()?.presentation_id);
    const reviewed = binaryDirtyContext?.key === binaryContextKey()
      ? binaryDirtyContext.reviewed : annotation.sets_reviewed === true;
    status.textContent = reviewed
      ? '本例段落选择已确认；修改答案后需再次确认。'
      : '检查完段落选择后，请点击“确认并保存”或“确认并进入下一项”。';
  }
}

function bindBinaryFormChanges() {
  const workspace = $('workspace');
  if (!workspace || workspace.dataset.binaryEventsBound === 'true') return;
  workspace.dataset.binaryEventsBound = 'true';
  const controls = '[data-minimal-evidence], [data-repair-packet], [data-section-role], [data-section-note], input[name="target_conflict"], input[name="judgment_sufficient"], select[name="confidence"], textarea[name="comments"]';
  const markChanged = (event) => {
    const control = event.target;
    if (!control?.matches?.(controls)) return;
    // Checkboxes/radios fire input followed by change; handle the logical change once.
    if (event.type === 'input' && ['checkbox', 'radio'].includes(control.type)) return;
    const card = control.closest('.paragraph-card');
    if (control.matches('[data-repair-packet]') && !control.checked
      && card?.querySelector('[data-minimal-evidence]')?.checked) {
      control.checked = true;
      showToast('最小证据必须纳入修复材料。如需取消，请先取消“最小证据集”。', true);
      return;
    }
    if (control.matches('[data-minimal-evidence]') && control.checked) {
      const repair = card?.querySelector('[data-repair-packet]');
      if (repair) repair.checked = true;
    }
    binaryDirtyContext = { key: binaryContextKey(), reviewed: false };
    updateBinaryReviewNotice();
  };
  workspace.addEventListener('input', markChanged, true);
  workspace.addEventListener('change', markChanged, true);
  workspace.addEventListener('click', (event) => {
    const button = event.target?.closest?.('#saveCurrentBtn, #nextCaseBtn');
    if (!button || button.disabled) return;
    // Confirmation is explicit. Merely navigating, exporting or auto-saving is not confirmation.
    binaryDirtyContext = { key: binaryContextKey(), reviewed: true };
  }, true);
}

const renderAssistedWorkspaceBeforeBinary = renderWorkspace;
renderWorkspace = function renderBinaryWorkspace() {
  binaryDirtyContext = null;
  renderAssistedWorkspaceBeforeBinary();
  const item = currentCase();
  if (!item) return;
  const root = $('workspace');
  const annotation = annotationFor(item.presentation_id);
  const isBinary = annotation.annotation_protocol === ANNOTATION_PROTOCOL;
  const target = ['present', 'absent'].includes(annotation.target_conflict) ? annotation.target_conflict : '';
  const sufficiency = isBinary && ['yes', 'no'].includes(annotation.judgment_sufficient)
    ? annotation.judgment_sufficient : '';
  const panel = root.querySelector('.overall-panel');
  if (!panel) throw new Error('整组判断区域缺失。');
  panel.innerHTML = `<h3>整组材料判断</h3>
    ${binaryLegacyNotice(annotation)}
    <div class="question-grid">
      <div class="question">
        <h4>这组材料是否存在目标冲突？ <span class="required">*</span></h4>
        <div class="choice-row">
          <label><input type="radio" name="target_conflict" value="present" ${selected(target, 'present')}>存在</label>
          <label><input type="radio" name="target_conflict" value="absent" ${selected(target, 'absent')}>不存在</label>
        </div>
      </div>
      <div class="question">
        <h4>当前材料是否足够支持上述判断？ <span class="required">*</span></h4>
        <div class="choice-row">
          <label><input type="radio" name="judgment_sufficient" value="yes" ${selected(sufficiency, 'yes')}>充分</label>
          <label><input type="radio" name="judgment_sufficient" value="no" ${selected(sufficiency, 'no')}>不充分</label>
        </div>
      </div>
      <div class="question">
        <h4>对本次判断的信心 <span class="required">*</span></h4>
        <select name="confidence"><option value="">请选择</option>
          ${[1, 2, 3, 4, 5].map((value) => `<option value="${value}" ${String(annotation.confidence || '') === String(value) ? 'selected' : ''}>${value} / 5</option>`).join('')}
        </select>
      </div>
      <div class="question wide"><h4>整体判断理由（可选）</h4>
        <textarea name="comments" placeholder="可记录判断依据或材料缺口">${esc(annotation.comments || '')}</textarea>
      </div>
    </div>
    <p id="binaryReviewNotice" class="local-note" ${sufficiency === 'no' ? '' : 'hidden'}>材料不充分：该判断将进入待复核，不直接作为已确认的正例或负例。</p>`;
  const paragraphHeading = root.querySelector('.section-heading span');
  if (paragraphHeading) paragraphHeading.textContent = '检查两个集合；角色和备注选填';
  $('saveCurrentBtn').textContent = '确认并保存';
  $('nextCaseBtn').textContent = state.activeIndex === casesForExpert().length - 1
    ? '确认并检查完成情况' : '确认并进入下一项';
  const savebarHint = root.querySelector('.savebar .hint');
  if (savebarHint) {
    savebarHint.id = 'setsReviewStatus';
    savebarHint.setAttribute('aria-live', 'polite');
  }
  bindBinaryFormChanges();
  updateBinaryReviewNotice();
};

captureCurrentForm = function captureBinaryForm(message = '已自动保存') {
  const item = currentCase();
  const root = $('workspace');
  if (!item || !root?.querySelector('.overall-panel')
    || binaryDirtyContext?.key !== binaryContextKey()) return false;
  const previous = annotationFor(item.presentation_id);
  const sections = {};
  root.querySelectorAll('.paragraph-card').forEach((card) => {
    const sectionId = card.dataset.sectionId;
    const oldSection = previous.sections?.[sectionId] || {};
    const selectedRole = card.querySelector('[data-section-role]:checked');
    const role = selectedRole ? selectedRole.value : (oldSection.role || '');
    sections[sectionId] = {
      ...oldSection, role, role_label: roleLabel(role),
      minimal_evidence: Boolean(card.querySelector('[data-minimal-evidence]')?.checked),
      repair_packet: Boolean(card.querySelector('[data-repair-packet]')?.checked),
      note: card.querySelector('[data-section-note]')?.value || '',
    };
  });
  const radio = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value || '';
  const record = {
    ...previous,
    annotation_protocol: ANNOTATION_PROTOCOL,
    reviewer_id: $('reviewerId').value.trim(),
    expert_slot: state.activeExpert,
    target_conflict: radio('target_conflict'),
    judgment_sufficient: radio('judgment_sufficient'),
    judgment_requires_review: radio('judgment_sufficient') === 'no',
    confidence: root.querySelector('select[name="confidence"]')?.value || '',
    comments: root.querySelector('textarea[name="comments"]')?.value || '',
    sections, sets_reviewed: binaryDirtyContext.reviewed === true,
    saved_at: new Date().toISOString(),
  };
  if (Object.keys(previous).length && previous.annotation_protocol !== ANNOTATION_PROTOCOL
    && !previous.legacy_annotation) {
    record.legacy_annotation = JSON.parse(JSON.stringify(previous));
  }
  annotationBucket()[item.presentation_id] = record;
  binaryDirtyContext = null;
  state.reviewerIds[state.activeExpert] = $('reviewerId').value.trim();
  state.activeIndices[state.activeExpert] = state.activeIndex;
  saveState(message);
  renderCaseList();
  updateBinaryReviewNotice();
  return true;
};

function binaryCaseErrors(presentationId, expertId = state.activeExpert) {
  const item = state.cases.find((entry) => entry.presentation_id === presentationId);
  const annotation = annotationFor(presentationId, expertId);
  const errors = [];
  if (!item) return ['样本不存在。'];
  if (!(annotation.reviewer_id || state.reviewerIds[expertId] || '').trim()) errors.push('请填写匿名标注者编号。');
  if (!['present', 'absent'].includes(annotation.target_conflict)) errors.push('请选择是否存在目标冲突。');
  if (annotation.annotation_protocol !== ANNOTATION_PROTOCOL
    || !['yes', 'no'].includes(annotation.judgment_sufficient)) {
    errors.push('请明确选择当前材料是否足够支持上述判断。');
  }
  if (!['1', '2', '3', '4', '5'].includes(String(annotation.confidence || ''))) errors.push('请选择判断信心。');
  if (annotation.sets_reviewed !== true) errors.push('请检查段落选择后点击“确认并保存”或“确认并进入下一项”。');
  const selections = item.sections.map((section) => annotation.sections?.[section.section_id]);
  if (selections.some((entry) => !entry || typeof entry.minimal_evidence !== 'boolean' || typeof entry.repair_packet !== 'boolean')) {
    errors.push('段落集合选择尚未确认完整。');
  }
  if (selections.some((entry) => entry?.minimal_evidence && !entry.repair_packet)) errors.push('最小证据必须同时纳入修复材料。');
  const minimalCount = selections.filter((entry) => entry?.minimal_evidence).length;
  const repairCount = selections.filter((entry) => entry?.repair_packet).length;
  if (annotation.target_conflict === 'present' && annotation.judgment_sufficient === 'yes'
    && (!minimalCount || !repairCount)) errors.push('认为存在冲突且判断充分时，请选择非空最小证据集和修复材料集。');
  if (annotation.target_conflict === 'absent' && minimalCount) errors.push('选择“不存在冲突”时，不能同时选入证明冲突的最小证据。');
  return errors;
}

isComplete = function isBinaryComplete(presentationId, expertId = state.activeExpert) {
  return binaryCaseErrors(presentationId, expertId).length === 0;
};

validateCurrentCase = function validateBinaryCurrentCase() {
  const errors = binaryCaseErrors(currentCase()?.presentation_id);
  return { valid: errors.length === 0, errors };
};
