/* eslint-disable @next/next/no-html-link-for-pages */
import { FileSearch, FlaskConical, Network } from "lucide-react";

export default function ResearchTabs({ active }: { active: "framework" | "confirmatory" | "review" }) {
  return (
    <nav className="research-tabs" aria-label="研究工作区">
      <a href="/" className={active === "framework" ? "active" : ""} aria-current={active === "framework" ? "page" : undefined}>
        <Network aria-hidden="true" />
        <span><strong>研究结论</strong><small>question · method · status</small></span>
      </a>
      <a href="/experiment-v3" className={active === "confirmatory" ? "active" : ""} aria-current={active === "confirmatory" ? "page" : undefined}>
        <FlaskConical aria-hidden="true" />
        <span><strong>实验结果</strong><small>baseline · real loop · next</small></span>
      </a>
      <a href="/review" className={active === "review" ? "active" : ""} aria-current={active === "review" ? "page" : undefined}>
        <FileSearch aria-hidden="true" />
        <span><strong>文献与数据</strong><small>closest work · shortlist</small></span>
      </a>
    </nav>
  );
}
