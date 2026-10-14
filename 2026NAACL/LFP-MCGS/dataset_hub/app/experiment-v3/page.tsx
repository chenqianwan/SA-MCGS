import type { Metadata } from "next";
import ExperimentV3 from "../ExperimentV3";

export const metadata: Metadata = {
  title: "实验结果 · LFP-MCGS Research Hub",
  description: "Current Pure Baseline results, the real GraphPUCT + LLM + online-LFP smoke, controlled SCC carriers, and the next decisive gates.",
};

export default function ExperimentV3Page() {
  return <ExperimentV3 />;
}
