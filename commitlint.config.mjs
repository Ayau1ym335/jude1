// Commit message rules (XC-FND-04, IDR-34): Conventional Commits + a `Task: <TASK-ID>` trailer
// naming a task that exists in the WBS (CLAUDE.md working rule 2).
import { readFileSync } from "node:fs";

const WBS_PATH = new URL("./docs/plan/WORK_BREAKDOWN_STRUCTURE_v1.1.csv", import.meta.url);
const TRAILER_RE = /^Task:[ \t]*(\S+)[ \t]*$/gm;

function loadTaskIds() {
  const ids = new Set();
  for (const line of readFileSync(WBS_PATH, "utf8").split(/\r?\n/).slice(1)) {
    const id = line.split(",")[2];
    if (id && /^(TSK|XC)-/.test(id)) ids.add(id);
  }
  return ids;
}

let taskIds;

/** @type {import("@commitlint/types").UserConfig} */
export default {
  extends: ["@commitlint/config-conventional"],
  plugins: [
    {
      rules: {
        "task-trailer": ({ raw }) => {
          const found = [...(raw ?? "").matchAll(TRAILER_RE)].map((m) => m[1]);
          if (found.length === 0) {
            return [false, "message must end with a trailer line `Task: <TASK-ID>` (e.g. Task: XC-FND-04)"];
          }
          if (found.length > 1) {
            return [false, `exactly one Task trailer allowed (one task per commit), found: ${found.join(", ")}`];
          }
          taskIds ??= loadTaskIds();
          if (!taskIds.has(found[0])) {
            return [false, `Task ${found[0]} is not an ID in docs/plan/WORK_BREAKDOWN_STRUCTURE_v1.1.csv`];
          }
          return [true];
        },
      },
    },
  ],
  rules: {
    "task-trailer": [2, "always"],
  },
};
