import Image from "next/image";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <div className="flex items-center font-extrabold text-2xl md:text-3xl">
      {/* First part */}
      <span className="text-black dark:text-white">
        Agentic
      </span>

      {/* Highlighted badge */}
      <span className="ml-1 px-2 py-0.5 rounded bg-orange-500 text-black">
        Planner
      </span>
    </div>
    </div>
  );
}
