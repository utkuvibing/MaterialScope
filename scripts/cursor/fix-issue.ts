import "dotenv/config";

import { Agent, CursorAgentError } from "@cursor/sdk";
import { Octokit } from "@octokit/rest";
import { readFile } from "node:fs/promises";

type IssueEvent = {
  action?: string;
  issue?: {
    number: number;
    title: string;
    body?: string | null;
    html_url?: string;
    labels?: Array<string | { name?: string | null }>;
  };
  repository?: {
    full_name?: string;
    html_url?: string;
    default_branch?: string;
  };
};

type IssuePayload = NonNullable<IssueEvent["issue"]>;

const CURSOR_LABEL = "cursor-agent";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function hasCursorLabel(issue: IssueEvent["issue"]): boolean {
  return Boolean(
    issue?.labels?.some((label) =>
      typeof label === "string" ? label === CURSOR_LABEL : label.name === CURSOR_LABEL,
    ),
  );
}

async function loadEvent(): Promise<IssueEvent> {
  const eventPath = requireEnv("GITHUB_EVENT_PATH");
  return JSON.parse(await readFile(eventPath, "utf8")) as IssueEvent;
}

async function loadIssueFromGitHub(owner: string, repo: string, issueNumber: number): Promise<IssuePayload> {
  const token = requireEnv("GITHUB_TOKEN");
  const octokit = new Octokit({ auth: token });
  const response = await octokit.issues.get({
    owner,
    repo,
    issue_number: issueNumber,
  });

  return {
    number: response.data.number,
    title: response.data.title,
    body: response.data.body,
    html_url: response.data.html_url,
    labels: response.data.labels.map((label) =>
      typeof label === "string" ? label : { name: label.name },
    ),
  };
}

async function enrichIssueBody(owner: string, repo: string, issueNumber: number): Promise<string> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return "";
  }

  const octokit = new Octokit({ auth: token });
  const comments = await octokit.paginate(octokit.issues.listComments, {
    owner,
    repo,
    issue_number: issueNumber,
    per_page: 25,
  });

  if (comments.length === 0) {
    return "";
  }

  return comments
    .slice(-10)
    .map((comment) => `Comment by ${comment.user?.login ?? "unknown"}:\n${comment.body ?? ""}`)
    .join("\n\n---\n\n");
}

async function main(): Promise<void> {
  const apiKey = requireEnv("CURSOR_API_KEY");
  const event = await loadEvent();
  const fullName = event.repository?.full_name ?? process.env.GITHUB_REPOSITORY;
  if (!fullName?.includes("/")) {
    throw new Error("Unable to determine GitHub repository full name.");
  }

  const [owner, repo] = fullName.split("/");
  const issueNumber = Number(process.env.ISSUE_NUMBER);
  const issue =
    event.issue ??
    (Number.isFinite(issueNumber) ? await loadIssueFromGitHub(owner, repo, issueNumber) : undefined);

  if (!issue) {
    console.log("No issue payload or ISSUE_NUMBER found; nothing to do.");
    return;
  }

  if (!hasCursorLabel(issue)) {
    console.log(`Issue #${issue.number} does not have label "${CURSOR_LABEL}"; skipping.`);
    return;
  }

  const comments = await enrichIssueBody(owner, repo, issue.number);
  const cwd = process.cwd();

  const prompt = `You are working in the MaterialScope repository.

GitHub issue: #${issue.number} ${issue.title}
Issue URL: ${issue.html_url ?? "(not provided)"}
Repository: ${fullName}

Issue body:
${issue.body ?? "(empty)"}

Recent issue comments:
${comments || "(none)"}

MaterialScope constraints:
- Keep this repository primarily Python/Dash/FastAPI.
- Do not restructure the app.
- Make only a small, focused fix for this issue.
- Do not commit secrets, .env files, credentials, generated libraries, build outputs, or local artifacts.
- Preserve scientific caution: screening/prototype features must not be described as definitive scientific identification.
- Prefer existing project patterns in dash_app, backend, core, tests, tools, and ui.
- Add or update focused tests only when they are directly useful for the issue.

Validation:
- If the fix touches Python behavior and pytest can run in this environment, run: pytest
- If pytest cannot run because optional scientific dependencies are missing, report that clearly and keep the code changes small.

Output expectation:
- Modify the checked-out branch only.
- Do not merge anything.
- Do not push to main.
- Leave a concise summary of changes and validation in your final response.`;

  try {
    // TODO(Cursor SDK): This first scaffold intentionally uses the documented local
    // Agent.prompt shape. If MaterialScope later moves this to a Cursor cloud-agent
    // auto-PR flow, confirm the current @cursor/sdk cloud repos/PR option names
    // against the SDK docs before replacing the workflow-created draft PR below.
    const result = await Agent.prompt(prompt, {
      apiKey,
      model: { id: "composer-2" },
      local: { cwd },
    });

    console.log(`Cursor agent finished with status: ${result.status}`);
    if (result.status === "error") {
      process.exitCode = 2;
    }
  } catch (error) {
    if (error instanceof CursorAgentError) {
      console.error(`Cursor agent startup failed: ${error.message}`);
      console.error(`Retryable: ${error.isRetryable}`);
      process.exitCode = 1;
      return;
    }

    throw error;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
