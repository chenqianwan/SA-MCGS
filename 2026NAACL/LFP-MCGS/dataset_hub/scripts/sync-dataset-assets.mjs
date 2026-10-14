import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const researchRoot = path.resolve(siteRoot, "..");
const publicRoot = path.join(siteRoot, "public");

const groups = {
  docs: [],
  artifacts: [],
  figures: [],
  experiments: [],
  "experiment-v2": [],
  "experiment-v3": [],
  "experiment-v4": [
    "experiments/v4_bgb_smoke/results/phase4_xhub_productive/summary.json",
    "experiments/v4_bgb_smoke/results/phase4_xhub_productive/manifest.json",
    "experiments/v4_bgb_smoke/results/phase4_xhub_clean/summary.json",
    "experiments/v4_bgb_smoke/results/phase4_xhub_clean/manifest.json",
    "experiments/v4_bgb_smoke/results/phase5_graphpuct_xhub_smoke/summary.json",
    "experiments/v4_bgb_smoke/results/phase5_graphpuct_xhub_smoke/manifest.json",
  ],
};

const targetName = (source) => {
  if (source.includes("/phase4_xhub_productive/")) {
    return `phase4_xhub_productive_${path.basename(source)}`;
  }
  if (source.includes("/phase4_xhub_clean/")) {
    return `phase4_xhub_clean_${path.basename(source)}`;
  }
  if (source.includes("/phase5_graphpuct_xhub_smoke/")) {
    return `phase5_graphpuct_${path.basename(source)}`;
  }
  return path.basename(source);
};
const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");
const manifest = {
  generatedAt: "2026-08-20T00:00:00+08:00",
  auditAsOf: "2026-08-20",
  sourceRoot: "2026NAACL",
  policy: "Whitelisted summaries only. Raw datasets are never copied into the site.",
  files: [],
};

for (const [group, sources] of Object.entries(groups)) {
  const outputDir = path.join(publicRoot, group);
  await rm(outputDir, { recursive: true, force: true });
  await mkdir(outputDir, { recursive: true });

  for (const relativeSource of sources) {
    const source = path.join(researchRoot, relativeSource);
    const output = path.join(outputDir, targetName(relativeSource));
    const bytes = await readFile(source);
    await copyFile(source, output);
    manifest.files.push({
      group,
      source: relativeSource,
      publicPath: `/${group}/${targetName(relativeSource)}`,
      bytes: bytes.length,
      sha256: sha256(bytes),
    });
  }
}

await writeFile(
  path.join(publicRoot, "content-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

console.log(`Synced ${manifest.files.length} audited assets.`);
