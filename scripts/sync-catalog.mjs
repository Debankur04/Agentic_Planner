import { readFile } from "node:fs/promises";

const baseUrl = process.env.ELIXPO_PAY_BASE_URL || "https://payouts.elixpo.com";
const apiKey = process.env.ELIXPO_PAY_API_KEY;
console.log(apiKey);


if (!apiKey) {
  console.error("ELIXPO_PAY_API_KEY is required");
  process.exit(1);
}

const catalog = JSON.parse(await readFile("payouts.catalog.json", "utf8"));
const res = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/sync`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(catalog),
});

const out = await res.json();
if (!res.ok || out.ok === false || (out.errors?.length ?? 0) > 0) {
  console.error("catalog sync failed:", JSON.stringify(out.errors ?? out));
  process.exit(1);
}

console.log(`synced ${out.synced?.length ?? 0} products`);
