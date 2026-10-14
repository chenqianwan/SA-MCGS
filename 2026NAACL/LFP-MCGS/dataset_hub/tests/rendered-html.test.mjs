import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render(pathname = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${pathname}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the compact current research conclusion", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>LFP-MCGS · Structured Test-Time Reasoning over Cyclic Documents<\/title>/i);
  assert.match(html, /让通用 LLM 在循环文档上/);
  assert.match(html, /闭环成立，优势未定/);
  assert.match(html, /局部窗口是模型读取原文的接口/);
  assert.match(html, /committed KB/);
  assert.match(html, /incremental LFP/);
  assert.match(html, /看实验结果/);
  assert.match(html, /看文献与数据/);
  assert.doesNotMatch(html, /历史诊断|Phase 0|2,160 cells|XHUB BASELINE/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/i);
});

for (const path of ["/experiment-v1", "/experiment-v2"]) {
  test(`${path} redirects to the current experiment`, async () => {
    const response = await render(path);
    assert.ok([301, 302, 303, 307, 308].includes(response.status));
    assert.equal(response.headers.get("location"), "/experiment-v3");
  });
}

test("renders only the current experiment evidence", async () => {
  const response = await render("/experiment-v3");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /真实闭环已经跑通/);
  assert.match(html, /算法优势还没有成立/);
  assert.match(html, /Pure Baseline · 3\/5\/7\/9\/11\/25/);
  assert.match(html, /LEA-LFP full-cover/);
  assert.match(html, /GraphPUCT \+ LLM \+ online LFP/);
  assert.match(html, /13 次 XHub 调用、48,885 tokens/);
  assert.match(html, /真实 LLM 在搜索内部/);
  assert.match(html, /branch/);
  assert.match(html, /seed · bridge · witness/);
  assert.match(html, /接下来只过四道 Gate/);
  assert.doesNotMatch(html, /三步证据链|搜索控制器冒烟|探索性规模网格|历史 oracle-controller|2,160 cells|Phase 03|Phase 03\.5|Phase 04|Phase 05|TreeMCTS 的唯一职责/);
});

test("renders only the decision-relevant literature and dataset shortlist", async () => {
  const response = await render("/review");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /完整闭环仍有新意/);
  assert.match(html, /Self-Correcting RAG/);
  assert.match(html, /SymBa/);
  assert.match(html, /PRISM-MCTS/);
  assert.match(html, /RL4RLA/);
  assert.match(html, /BGB controlled SCC intervention/);
  assert.match(html, /SARA-Cycle/);
  assert.match(html, /AOP-Wiki/);
  assert.match(html, /OpenExempt/);
  assert.match(html, /MoNaCo \+ FSDBench/);
  assert.doesNotMatch(html, /Downgrade ledger|执行决定|LLM-WikiRace|PaperScope|历史诊断/);
});

test("legacy wave4 route redirects to the current review", async () => {
  const response = await render("/wave4");
  assert.ok([301, 302, 303, 307, 308].includes(response.status));
  assert.equal(response.headers.get("location"), "/review");
});

test("publishes only current compact experiment summaries", async () => {
  const manifest = JSON.parse(await readFile(new URL("../public/content-manifest.json", import.meta.url), "utf8"));
  assert.equal(manifest.auditAsOf, "2026-08-20");
  assert.equal(manifest.files.length, 6);
  assert.ok(manifest.files.every((entry) => entry.group === "experiment-v4"));
  assert.ok(manifest.files.every((entry) => !entry.source.includes("/raw/")));
  assert.ok(manifest.files.every((entry) => /^[a-f0-9]{64}$/.test(entry.sha256)));
  await assert.rejects(access(new URL("../app/_sites-preview/", import.meta.url)));
});
