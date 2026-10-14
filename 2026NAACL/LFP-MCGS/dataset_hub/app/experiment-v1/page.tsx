import { redirect } from "next/navigation";

export default function ExperimentV1Redirect() {
  redirect("/experiment-v3");
}
