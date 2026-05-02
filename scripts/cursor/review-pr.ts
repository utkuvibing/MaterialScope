import "dotenv/config";

import { Agent, CursorAgentError } from "@cursor/sdk";
import { Octokit } from "@octokit/rest";
import { readFile } from "node:fs/promises";

type PullRequestEvent = {
  pull_request?: {
    number: number;
    title: string;
    body?: string | null;
    html_url?: string;
    base?: { ref?: string };
    head?: { ref?: string };
  };
  repository?: {
    full_name?: string;
  };
};

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

async function loadEvent(): Promise<PullRequestEvent> {
  const eventPath = requireEnv("GITHUB_EVENT_PATH");
  return JSON.parse(await readFile(eventPath, "utf8")) as PullRequestEvent;
}

async function getChangedFiles(owner: string, repo: string, pullNumber: number): Promise<string[]> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return [];
  }

  const octokit = new Octokit({ auth: token });
  const files = await octokit.paginate(octokit.pulls.listFiles, {
    owner,
    repo,
    pull_number: pullNumber,
    per_page: 100,
  });

  return files.map((file) => file.filename);
}

async function main(): Promise<void> {
  const apiKey = requireEnv("CURSOR_API_KEY");
  const event = await loadEvent();
  const pullRequest = event.pull_request;

  if (!pullRequest) {
    console.log("No pull_request payload found; nothing to review.");
    return;
  }

  const fullName = event.repository?.full_name ?? process.env.GITHUB_REPOSITORY;
  if (!fullName?.includes("/")) {
    throw new Error("Unable to determine GitHub repository full name.");
  }

  const [owner, repo] = fullName.split("/");
  const changedFiles = await getChangedFiles(owner, repo, pullRequest.number);

  const prompt = `Review this MaterialScope pull request in the checked-out repository.

PR: #${pullRequest.number} ${pullRequest.title}
URL: ${pullRequest.html_url ?? "(not provided)"}
Base branch: ${pullRequest.base?.ref ?? "(unknown)"}
Head branch: ${pullRequest.head?.ref ?? "(unknown)"}

PR body:
${pullRequest.body ?? "(empty)"}

Changed files:
${changedFiles.length > 0 ? changedFiles.map((file) => `- ${file}`).join("\n") : "(not available)"}

Review priorities:
- Bugs, regressions, safety issues, and missing tests first.
- Respect MaterialScope as a Python/Dash/FastAPI scientific app.
- Do not suggest broad restructuring for a small PR.
- Check scientific claims carefully; screening/prototype workflows must not be framed as definitive expert confirmation.
- Check Dash/Plotly UI changes for callback correctness, state handling, and performance.

Do not modify files unless the workflow explicitly asks for an autofix. Provide concise review findings with file references where possible.`;

  try {
    // TODO(Cursor SDK): Keep this as a local one-shot review until the exact
    // cloud review/comment API shape is confirmed for the installed SDK version.
    const result = await Agent.prompt(prompt, {
      apiKey,
      model: { id: "composer-2" },
      local: { cwd: process.cwd() },
    });

    console.log(`Cursor review finished with status: ${result.status}`);
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
