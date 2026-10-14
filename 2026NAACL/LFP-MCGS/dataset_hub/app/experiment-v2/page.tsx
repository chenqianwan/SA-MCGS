import { redirect } from "next/navigation";

export default function ExperimentV2Redirect() {
  redirect("/experiment-v3");
}
