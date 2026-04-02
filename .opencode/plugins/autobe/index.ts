/**
 * opencode-autobe — OpenCode plugin for AutoBE
 *
 * Adds one tool to OpenCode:
 *   - autobe_generate  Run the full AutoBE pipeline from a description
 *
 * Configuration (environment variables):
 *   ANTHROPIC_API_KEY   API key for Anthropic (required, also supports OPENAI_API_KEY)
 *   AUTOBE_MODEL        Default AI model (default: claude-sonnet-4-20250514)
 *   AUTOBE_BASE_URL     Custom base URL for the AI vendor endpoint (optional)
 */

import { tool, type Plugin } from "@opencode-ai/plugin";
import OpenAI from "openai";
import { join } from "path";
import { writeFile, mkdir } from "fs/promises";

// ---------------------------------------------------------------------------
// Write helper
// ---------------------------------------------------------------------------

async function writeFiles(
  directory: string,
  files: Record<string, string>,
): Promise<void> {
  for (const [filePath, content] of Object.entries(files)) {
    const full = join(directory, filePath);
    const dir = full.substring(0, full.lastIndexOf("/"));
    if (dir) await mkdir(dir, { recursive: true });
    await writeFile(full, content, "utf-8");
  }
}

// ---------------------------------------------------------------------------
// Vendor factory
// ---------------------------------------------------------------------------

function createVendor(OpenAIClass: typeof OpenAI): import("@autobe/agent").IAutoBeVendor {
  const apiKey =
    process.env.ANTHROPIC_API_KEY ??
    process.env.OPENAI_API_KEY ??
    process.env.AUTOBE_API_KEY;

  if (!apiKey) {
    throw new Error(
      "No API key found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or AUTOBE_API_KEY.",
    );
  }

  const baseURL = process.env.AUTOBE_BASE_URL;
  const isAnthropic =
    baseURL?.includes("anthropic") || apiKey.startsWith("sk-ant-");

  if (isAnthropic && !baseURL) {
    return {
      api: new OpenAIClass({
        apiKey,
        baseURL: "https://api.anthropic.com/compat/v1",
      }),
      model: (process.env.AUTOBE_MODEL ?? "claude-sonnet-4-20250514") as OpenAI.ChatModel,
      semaphore: 16,
    };
  }

  return {
    api: new OpenAIClass({ apiKey, baseURL }),
    model: (process.env.AUTOBE_MODEL ?? "gpt-4.1") as OpenAI.ChatModel,
    semaphore: 16,
  };
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

const plugin: Plugin = async (_ctx) => {
  return {
    tool: {
      autobe_generate: tool({
        description: `Generate a complete NestJS + Prisma backend using AutoBE AI.

Runs the full AutoBE vibe-coding pipeline in-process:
  1. Requirements analysis   → structured specification
  2. Database design         → Prisma schema (ERD)
  3. API design              → OpenAPI specification
  4. Test generation         → E2E test suites
  5. Code generation         → NestJS implementation (100 % TypeScript-compilable)

All generated files are written to the current project directory by default.

Prerequisites:
  • AI API key in ANTHROPIC_API_KEY, OPENAI_API_KEY, or AUTOBE_API_KEY`,

        args: {
          description: tool.schema
            .string()
            .describe(
              "Natural-language description of the backend to generate. " +
                "Include domain, main entities, key operations, and any constraints.",
            ),
          model: tool.schema
            .string()
            .optional()
            .describe(
              "AI model, e.g. 'claude-sonnet-4-20250514', 'gpt-4.1'. " +
                "Defaults to AUTOBE_MODEL env var or auto-detected based on API key.",
            ),
          write_files: tool.schema
            .boolean()
            .optional()
            .describe("Write generated files to the project directory. Default: true."),
        },

        async execute(args, ctx) {
          const shouldWrite = args.write_files !== false;

          ctx.metadata({ title: "AutoBE: setting up…" });

          // Lazy-load CJS packages via dynamic import to satisfy bun's async-module requirements
          const [{ AutoBeAgent }, { AutoBeCompiler }, { default: OpenAIClass }] =
            await Promise.all([
              import("@autobe/agent"),
              import("@autobe/compiler"),
              import("openai"),
            ]);

          // 1. Create vendor configuration
          let vendor: import("@autobe/agent").IAutoBeVendor;
          try {
            vendor = createVendor(OpenAIClass);
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            return [
              "❌ AutoBE vendor setup failed: " + msg,
              "",
              "Checklist:",
              "  1. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment",
            ].join("\n");
          }

          if (args.model) {
            vendor = { ...vendor, model: args.model as OpenAI.ChatModel };
          }

          // 2. Create AutoBeAgent
          ctx.metadata({ title: "AutoBE: initializing agent…" });

          const agent = new AutoBeAgent({
            vendor,
            compiler: (listener) => new AutoBeCompiler(listener),
            config: {
              locale: "en-US",
              timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            },
          });

          const phaseLabels: Record<string, string> = {
            analyzeStart: "AutoBE: analysing requirements…",
            databaseStart: "AutoBE: designing database schema…",
            interfaceStart: "AutoBE: designing API interface…",
            testStart: "AutoBE: writing E2E tests…",
            realizeStart: "AutoBE: generating implementation…",
            analyzeComplete: "AutoBE: ✓ requirements analysed",
            databaseComplete: "AutoBE: ✓ database schema done",
            interfaceComplete: "AutoBE: ✓ API interface done",
            testComplete: "AutoBE: ✓ E2E tests done",
            realizeComplete: "AutoBE: ✓ implementation done!",
          };

          let lastLabel = "";
          for (const [event, label] of Object.entries(phaseLabels)) {
            agent.on(event as never, () => {
              if (label !== lastLabel) {
                lastLabel = label;
                ctx.metadata({ title: label });
              }
            });
          }

          // 3. Run generation
          ctx.metadata({ title: "AutoBE: generating…" });

          try {
            await agent.conversate(args.description);
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            return ["❌ AutoBE generation failed: " + msg, "", "Model: " + vendor.model].join("\n");
          }

          // 4. Get generated files
          let files: Record<string, string>;
          try {
            files = await agent.getFiles({ dbms: "postgres" });
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            return [
              "❌ Failed to retrieve generated files: " + msg,
              "",
              "The generation completed but file retrieval failed.",
            ].join("\n");
          }

          const fileList = Object.keys(files);

          if (shouldWrite && fileList.length > 0) {
            await writeFiles(ctx.directory, files);
          }

          return [
            "✅ AutoBE generation complete!",
            "",
            `Model:    ${vendor.model}`,
            `Files:    ${fileList.length}`,
            "",
            "Generated files:",
            ...fileList.slice(0, 30).map((f) => `  ${f}`),
            ...(fileList.length > 30 ? [`  … and ${fileList.length - 30} more`] : []),
            "",
            shouldWrite && fileList.length > 0
              ? `✓ Written to: ${ctx.directory}`
              : "(write_files=false — files not written to disk)",
          ].join("\n");
        },
      }),
    },
  };
};

export default plugin;
