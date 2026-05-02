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

function logErrorDetails(error: unknown): void {
  const maybeError = error as { name?: unknown; message?: unknown; stack?: unknown; cause?: unknown };

  console.error(`error.name: ${String(maybeError.name ?? "(unknown)")}`);
  console.error(`error.message: ${String(maybeError.message ?? "(no message)")}`);
  if (maybeError.stack) {
    console.error(`error.stack: ${String(maybeError.stack)}`);
  }
  console.error(`String(error): ${String(error)}`);
  if (maybeError.cause) {
    console.error("error.cause:", maybeError.cause);
  }
}

async function streamAssistantText(run: Awaited<ReturnType<Awaited<ReturnType<typeof Agent.create>>["send"]>>): Promise<void> {
  for await (const event of run.stream()) {
    if (event.type !== "assistant") {
      continue;
    }

    for (const block of event.message.content) {
      if (block.type === "text") {
        process.stdout.write(block.text);
      }
    }
  }
}

async function runCursorAgent(name: string, prompt: string, apiKey: string): Promise<void> {
  const agent = await Agent.create({
    apiKey,
    name,
    model: { id: process.env.CURSOR_MODEL ?? "composer-2" },
    local: { cwd: process.cwd() },
  });

  try {
    const run = await agent.send(prompt);
    await streamAssistantText(run);
    const result = await run.wait();

    console.log(`\nCursor review finished with status: ${result.status}`);
    if (result.status === "error") {
      process.exitCode = 2;
    }
  } finally {
    await agent[Symbol.asyncDispose]();
  }
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
    await runCursorAgent(`MaterialScope PR #${pullRequest.number} review`, prompt, apiKey);
  } catch (error) {
    if (error instanceof CursorAgentError) {
      console.error("Cursor agent startup failed.");
      logErrorDetails(error);
      console.error(`Retryable: ${error.isRetryable}`);
      process.exitCode = 1;
      return;
    }

    logErrorDetails(error);
    throw error;
  }
}

main().catch((error) => {
  logErrorDetails(error);
  process.exitCode = 1;
});
