import type { Metadata } from "next";
import LiteratureDataReview from "../LiteratureDataReview";

export const metadata: Metadata = {
  title: "文献与数据 · LFP-MCGS",
  description: "The nearest prior work, exact claim boundary, and six-role dataset shortlist for LFP-MCGS.",
  openGraph: {
    title: "文献与数据 · LFP-MCGS",
    description: "Nearest prior work, exact novelty boundary, and the current six-role dataset shortlist.",
    images: [{ url: "/og-review.png", width: 1731, height: 909, alt: "Evidence review map connecting cyclic documents, source validation, symbolic closure, and graph search." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "文献与数据 · LFP-MCGS",
    description: "Nearest prior work and the current dataset shortlist.",
    images: ["/og-review.png"],
  },
};

export default function ReviewPage() {
  return <LiteratureDataReview />;
}
