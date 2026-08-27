import { greeting } from "@/greeting";

export default function Page() {
  return (
    <main>
      <h1>{greeting("Rendered Monorepo")}</h1>
    </main>
  );
}
