import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();
const execPlanRoot = path.join(repoRoot, "docs", "exec-plans");
const activeRoot = path.join(execPlanRoot, "active");
const completedRoot = path.join(execPlanRoot, "completed");
const requiredPlanSections = [
  "## Purpose / Big Picture",
  "## Surprises & Discoveries",
  "## Decision Log",
  "## Outcomes & Retrospective",
  "## Context and Orientation",
  "## Plan of Work",
  "## Concrete Steps",
  "## Machine State",
  "## Progress",
  "## Testing Approach",
  "## Constraints & Considerations",
];

const fail = (message) => {
  console.error(message);
  process.exit(1);
};

const readJson = (filePath) => {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    fail(
      `Invalid JSON in ${path.relative(repoRoot, filePath)}: ${error.message}`
    );
  }
};

const ensureStringArray = (value, label) => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    fail(`${label} must be an array of strings`);
  }
};

const isIsoDate = (value) =>
  typeof value === "string" &&
  value.length > 0 &&
  !Number.isNaN(Date.parse(value));

const collectTaskDirs = (root) => {
  if (!fs.existsSync(root)) {
    return [];
  }
  const found = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "tasks") {
          found.push(fullPath);
        }
        stack.push(fullPath);
      }
    }
  }
  return found;
};

for (const requiredRoot of [execPlanRoot, activeRoot, completedRoot]) {
  if (!fs.existsSync(requiredRoot)) {
    fail(`Missing required exec-plan directory: ${path.relative(repoRoot, requiredRoot)}`);
  }
}

const taskDirs = collectTaskDirs(execPlanRoot);
if (taskDirs.length > 0) {
  fail(
    `Deprecated tasks directories detected:\n${taskDirs
      .map((dir) => path.relative(repoRoot, dir))
      .join("\n")}`
  );
}

const initiativeDirs = fs
  .readdirSync(activeRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);

for (const initiative of initiativeDirs) {
  const initiativeRoot = path.join(activeRoot, initiative);
  const stateRoot = path.join(initiativeRoot, "state");
  const featureListPath = path.join(stateRoot, "feature-list.json");
  const sessionStatePath = path.join(stateRoot, "session-state.json");
  const progressPath = path.join(stateRoot, "progress.jsonl");
  const planFiles = fs
    .readdirSync(initiativeRoot, { withFileTypes: true })
    .filter(
      (entry) =>
        entry.isFile() &&
        entry.name.startsWith("PLAN_") &&
        entry.name.endsWith(".md")
    )
    .map((entry) => entry.name);

  if (planFiles.length !== 1) {
    fail(
      `Expected exactly one PLAN_*.md file in ${path.relative(repoRoot, initiativeRoot)}`
    );
  }

  const planPath = path.join(initiativeRoot, planFiles[0]);

  for (const requiredPath of [
    planPath,
    featureListPath,
    sessionStatePath,
    progressPath,
  ]) {
    if (!fs.existsSync(requiredPath)) {
      fail(`Missing required execplan artifact: ${path.relative(repoRoot, requiredPath)}`);
    }
  }

  const planText = fs.readFileSync(planPath, "utf8");
  for (const section of requiredPlanSections) {
    if (!planText.includes(section)) {
      fail(`${path.relative(repoRoot, planPath)} is missing required section ${section}`);
    }
  }

  const featureList = readJson(featureListPath);
  const sessionState = readJson(sessionStatePath);

  if (featureList.initiative !== initiative) {
    fail(`feature-list.json initiative must match directory name for ${initiative}`);
  }

  if (featureList.plan_file !== planFiles[0]) {
    fail(`feature-list.json plan_file must match ${planFiles[0]} for ${initiative}`);
  }

  if (!isIsoDate(featureList.created_at) || !isIsoDate(featureList.last_updated)) {
    fail(`feature-list.json timestamps must be valid ISO-like datetimes for ${initiative}`);
  }

  ensureStringArray(
    featureList.editing_rules,
    `${path.relative(repoRoot, featureListPath)}:editing_rules`
  );

  if (!Array.isArray(featureList.features) || featureList.features.length === 0) {
    fail(`feature-list.json must contain a non-empty features array for ${initiative}`);
  }

  const featureIds = new Set();
  for (const feature of featureList.features) {
    for (const key of ["id", "category", "description"]) {
      if (typeof feature[key] !== "string" || feature[key].length === 0) {
        fail(`Each feature in ${path.relative(repoRoot, featureListPath)} must have a non-empty ${key}`);
      }
    }
    ensureStringArray(
      feature.steps,
      `${path.relative(repoRoot, featureListPath)}:${feature.id}:steps`
    );
    if (typeof feature.passes !== "boolean") {
      fail(
        `Feature ${feature.id} in ${path.relative(repoRoot, featureListPath)} must have a boolean passes field`
      );
    }
    if (featureIds.has(feature.id)) {
      fail(`Duplicate feature id ${feature.id} in ${path.relative(repoRoot, featureListPath)}`);
    }
    featureIds.add(feature.id);
  }

  if (sessionState.initiative !== initiative) {
    fail(`session-state.json initiative must match directory name for ${initiative}`);
  }

  if (sessionState.plan_file !== planFiles[0]) {
    fail(`session-state.json plan_file must match ${planFiles[0]} for ${initiative}`);
  }

  for (const key of ["status", "last_updated", "next_action"]) {
    if (typeof sessionState[key] !== "string" || sessionState[key].length === 0) {
      fail(`session-state.json field ${key} must be a non-empty string for ${initiative}`);
    }
  }

  if (!isIsoDate(sessionState.last_updated)) {
    fail(`session-state.json last_updated must be a valid ISO-like datetime for ${initiative}`);
  }

  if (
    sessionState.active_feature_id !== null &&
    sessionState.active_feature_id !== undefined &&
    !featureIds.has(sessionState.active_feature_id)
  ) {
    fail(`session-state.json active_feature_id must reference a known feature for ${initiative}`);
  }

  ensureStringArray(
    sessionState.completed_feature_ids,
    `${path.relative(repoRoot, sessionStatePath)}:completed_feature_ids`
  );
  ensureStringArray(
    sessionState.blocked_by,
    `${path.relative(repoRoot, sessionStatePath)}:blocked_by`
  );
  ensureStringArray(
    sessionState.handoff_rules,
    `${path.relative(repoRoot, sessionStatePath)}:handoff_rules`
  );

  const progressRaw = fs.readFileSync(progressPath, "utf8").trim();
  if (progressRaw.length === 0) {
    fail(`progress.jsonl must contain at least one entry for ${initiative}`);
  }

  let previousTimestamp = null;
  const progressLines = progressRaw.split("\n");
  for (const [index, line] of progressLines.entries()) {
    let entry;
    try {
      entry = JSON.parse(line);
    } catch (error) {
      fail(
        `Invalid JSON on line ${index + 1} of ${path.relative(repoRoot, progressPath)}: ${error.message}`
      );
    }

    for (const key of ["timestamp", "actor", "type", "summary"]) {
      if (typeof entry[key] !== "string" || entry[key].length === 0) {
        fail(`progress.jsonl line ${index + 1} in ${initiative} must have a non-empty ${key}`);
      }
    }

    if (!isIsoDate(entry.timestamp)) {
      fail(`progress.jsonl line ${index + 1} in ${initiative} must have a valid timestamp`);
    }

    if (previousTimestamp !== null && Date.parse(entry.timestamp) < Date.parse(previousTimestamp)) {
      fail(`progress.jsonl timestamps must be non-decreasing for ${initiative}`);
    }
    previousTimestamp = entry.timestamp;

    if (
      entry.feature_id !== null &&
      entry.feature_id !== undefined &&
      !featureIds.has(entry.feature_id)
    ) {
      fail(`progress.jsonl line ${index + 1} references unknown feature_id ${entry.feature_id}`);
    }

    ensureStringArray(
      entry.files_touched ?? [],
      `${path.relative(repoRoot, progressPath)}:${index + 1}:files_touched`
    );
    ensureStringArray(
      entry.verification ?? [],
      `${path.relative(repoRoot, progressPath)}:${index + 1}:verification`
    );
  }
}

console.log(`EXECPLAN_STATE_OK ${initiativeDirs.length}`);
