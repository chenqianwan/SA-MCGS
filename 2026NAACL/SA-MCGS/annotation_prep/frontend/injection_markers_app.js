/* Provenance badges for the explicitly assisted page; no labels are inferred. */
state.injectionMarkers = null;

const validateDataBeforeInjectionMarkers = validateData;
validateData = function validateDataWithInjectionMarkers(manifest, translations) {
  const result = validateDataBeforeInjectionMarkers(manifest, translations);
  const markers = readEmbeddedJson('injectionMarkersData');
  if (markers?.schema_version !== 'assisted_injection_markers.v1'
    || markers.source_manifest_hash !== manifest.manifest_hash
    || !/^sha256:[a-f0-9]{64}$/.test(markers.marker_pack_hash || '')
    || Object.keys(markers.cases || {}).length !== manifest.cases.length) {
    throw new Error('注入段落标记与当前材料不一致。');
  }
  for (const item of manifest.cases) {
    const entry = markers.cases[item.presentation_id];
    const ids = new Set(item.sections.map((section) => section.section_id));
    if (!entry || entry.condition !== state.hints.cases[item.presentation_id].condition
      || !Array.isArray(entry.modified_section_ids)
      || new Set(entry.modified_section_ids).size !== entry.modified_section_ids.length
      || entry.modified_section_ids.some((id) => !ids.has(id))
      || (entry.condition === 'pre' && entry.modified_section_ids.length)
      || (entry.condition === 'post' && !entry.modified_section_ids.length)) {
      throw new Error(`样本 ${item.presentation_id} 的注入段落标记无法核对。`);
    }
  }
  state.injectionMarkers = markers;
  return result;
};

const renderParagraphBeforeInjectionMarkers = renderParagraph;
renderParagraph = function renderParagraphWithInjectionMarkers(item, section, index) {
  const html = renderParagraphBeforeInjectionMarkers(item, section, index);
  if (!state.injectionMarkers.cases[item.presentation_id].modified_section_ids.includes(section.section_id)) return html;
  const marker = `<p class="paragraph-number">段落 ${index + 1}</p>`;
  if (!html.includes(marker)) throw new Error('注入段落标记位置发生变化。');
  return html.replace(marker, `<p class="paragraph-number">段落 ${index + 1} <span class="injection-marker" title="该段文字相较同源未注入材料被修改；不代表专家已判定存在冲突。">注入段落</span></p>`);
};

const captureBeforeInjectionMarkers = captureCurrentForm;
captureCurrentForm = function captureWithInjectionMarkerProvenance(...args) {
  const pid = currentCase()?.presentation_id;
  const captured = captureBeforeInjectionMarkers(...args);
  if (captured && pid) {
    // Merely opening/exporting the page never rewrites a previous annotation.
    annotationBucket()[pid].injection_marker_pack_hash = state.injectionMarkers.marker_pack_hash;
    saveState();
  }
  return captured;
};

const buildRowsBeforeInjectionMarkers = buildExportRows;
buildExportRows = function buildRowsWithInjectionMarkers(expertId = state.activeExpert) {
  const rows = buildRowsBeforeInjectionMarkers(expertId);
  for (const row of [...rows.caseRows, ...rows.sectionRows]) {
    row.injection_marker_pack_hash = annotationFor(row.样本编号, expertId).injection_marker_pack_hash || '';
  }
  return rows;
};
