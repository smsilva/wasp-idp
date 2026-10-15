// Terminal look for command blocks, in the colors of the deck (docs/presentation): a `$` prompt on each
// command, options and their values in their own colors, and ✓/✗ lines of the output in green/red.
// The prompt is a CSS pseudo-element, so the copy button still copies the commands only.
(() => {
  // Options that take no value: the word after them is an argument, not their value.
  const FLAGS = new Set(["--wait", "--default", "--dry-run", "--yes", "--all", "--no-browser", "--use-device-code",
    "--skip-init", "--force", "--editable", "--quiet", "--admin", "--compact-output", "--include", "--silent",
    "--edit", "--generate-file", "--https"]);
  const OPERATORS = new Set(["|", "||", "&&", ";", ">", ">>", "<", "\\", "--"]);
  // Reserved words of the shell, where a command would stand (`for`, `do`, `done`, `if`, `then` ...),
  // in a color no platform concept uses.
  const KEYWORDS = new Set(["for", "while", "until", "do", "done", "if", "then", "elif", "else", "fi", "case", "esac"]);
  // Verbs of the platform and kubectl commands: the word before one is the concept, the first argument
  // after it is the object; both are shown in bold.
  const VERBS = new Set(["create", "delete", "get", "list", "add", "remove", "share", "unshare", "verify", "default",
    "import", "render", "logs", "exec", "describe", "apply", "auth", "clone"]);

  // Values of these options get a color of their own, the same one their part of an instance URL gets.
  const ROLES = { "--component": "component", "--environment": "environment" };
  // ... and so does the object of a command on that concept (`platform environment create demo`).
  const CONCEPTS = { component: "component", environment: "environment" };
  // `http://<component>.<environment>.localhost`: the host of a workload instance (Reach an instance from outside).
  const INSTANCE_URL = /^(https?:\/\/)([a-z0-9-]+)\.([a-z0-9-]+)(\.localhost.*)$/;

  // Names of components and environments the page's commands use (`--component hello-api`,
  // `environment create demo`): a path or URL segment equal to one of them takes its color too
  // (`/tmp/hello-api`, `wasp-foundry/hello-api.git`).
  let names = new Map();

  function collectNames(texts) {
    names = new Map();
    const patterns = [
      [/--component[ =]([a-z0-9-]+)/g, "component"],
      [/--environment[ =]([a-z0-9-]+)/g, "environment"],
      [/\bcomponent\s+[a-z]+\s+([a-z0-9-]+)/g, "component"],
      [/\benvironment\s+[a-z]+\s+([a-z0-9-]+)/g, "environment"],
    ];
    for (const text of texts) {
      for (const [pattern, role] of patterns) {
        for (const match of text.matchAll(pattern)) names.set(match[1], role);
      }
    }
  }

  // A word with the known names inside it colored, the rest in `kind`.
  function withNames(kind, word) {
    if (!names.size) return span(kind, word);
    return word.split(/([\/.:@])/).map((part) => {
      if (!part) return "";
      const role = names.get(part);
      return role ? span(role, part) : span(kind, part);
    }).join("");
  }

  const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const span = (kind, text) => `<span class="t-${kind}">${escape(text)}</span>`;

  // Words and the spaces between them, keeping quoted strings whole.
  function words(line) {
    return line.match(/\s+|'[^']*'|"[^"]*"|[^\s'"]+(?:'[^']*'|"[^"]*")?[^\s'"]*/g) || [];
  }

  function shell(text) {
    let continued = false;
    // Open `do`/`then` blocks of a loop or an if: their lines and the closing `done`/`fi` belong to the
    // command that opened them, so they get no prompt of their own.
    let depth = 0;
    // Delimiter of an open here-document: its lines are input to the command, not commands.
    let heredoc = null;
    return text.replace(/\n$/, "").split("\n").map((line) => {
      if (heredoc !== null) {
        if (line === heredoc) heredoc = null;
        return '<span class="t-heredoc"></span>' + escape(line);
      }
      const opened = line.match(/<<-?\s*['"]?(\w+)['"]?/);
      if (opened) heredoc = opened[1];
      if (!line.trim()) {
        continued = false;
        return "";
      }
      if (/^\s*#/.test(line)) return span("comment", line);
      const closes = /^\s*(done|fi)\b/.test(line);
      if (closes && depth > 0) depth -= 1;
      // A line inside a block still opens with a command (colored), only without the prompt.
      const fresh = !continued;
      const start = fresh && depth === 0 && !closes;
      continued = /\\\s*$/.test(line);
      if (/\b(do|then)\s*$/.test(line)) depth += 1;
      let first = fresh;
      let expectValue = false;
      let role = null;
      const parts = words(line);
      // The `in` of `for <name> in`: the word after the loop variable.
      let loopVariable = false;
      // Concept and object of the command: the word before the verb and the first argument after it.
      const bold = new Set();
      // The object of `component <verb>` / `environment <verb>` takes the color of that concept.
      const objectRole = new Map();
      if (start) {
        const plain = parts.map((word, index) => [word, index]).filter(([word]) => !/^\s+$/.test(word));
        const verb = plain.findIndex(([word], position) => position > 0 && VERBS.has(word));
        if (verb > 0) {
          if (verb > 1) bold.add(plain[verb - 1][1]);
          const object = plain.slice(verb + 1).find(([word]) => !word.startsWith("-") && !OPERATORS.has(word));
          if (object) {
            bold.add(object[1]);
            const concept = CONCEPTS[plain[verb - 1][0]];
            if (concept) objectRole.set(object[1], concept);
          }
        }
      }
      const html = parts.map((word, index) => {
        if (/^\s+$/.test(word)) return word;
        if (OPERATORS.has(word)) {
          expectValue = false;
          if (word === "|" || word === "&&" || word === "||" || word === ";") first = true;
          return span("op", word);
        }
        if (first) {
          // After `do`/`then` a command can follow on the same line (`do echo`), so it stays first.
          if (KEYWORDS.has(word)) {
            first = word !== "for" && word !== "case";
            loopVariable = word === "for";
            return span("kw", word);
          }
          first = false;
          return span("cmd", word);
        }
        if (loopVariable) {
          loopVariable = false;
          return span("arg", word);
        }
        if (word === "in" && parts.slice(0, index).some((w) => w === "for" || w === "case")) return span("kw", word);
        if (word === "do" || word === "then") return span("kw", word);
        if (word.startsWith("--")) {
          expectValue = !FLAGS.has(word) && !word.includes("=");
          role = ROLES[word] || null;
          return span("opt", word);
        }
        // Before the value check: `curl --include <url>` reads the URL as the value of --include.
        const url = word.match(INSTANCE_URL);
        if (url) {
          expectValue = false;
          return span("arg", url[1]) + span("component", url[2]) + span("arg", ".") + span("environment", url[3]) + span("arg", url[4]);
        }
        if (expectValue) {
          expectValue = false;
          return role ? span(role, word) : withNames("val", word);
        }
        if (objectRole.has(index)) return span(objectRole.get(index), word);
        if (bold.has(index)) return span("key", word);
        if (/^['"$]/.test(word)) return span("val", word);
        return withNames("arg", word);
      }).join("");
      return (start ? '<span class="t-prompt"></span>' : '<span class="t-indent"></span>') + html;
    }).join("\n") + "\n";
  }

  // A line of output in `kind` (or plain), with the names the page's commands use in their own colors:
  // `✓ demo ready` shows `demo` as it shows in `environment create demo`.
  function outputLine(kind, line) {
    const paint = (text) => (kind ? span(kind, text) : escape(text));
    if (!names.size) return paint(line);
    return line.split(/([a-z0-9-]+)/).map((part) => {
      if (!part) return "";
      const role = names.get(part);
      return role ? span(role, part) : paint(part);
    }).join("");
  }

  function output(text) {
    return text.replace(/\n$/, "").split("\n").map((line) => {
      const head = line.trimStart();
      if (head.startsWith("✓")) return outputLine("ok", line);
      if (head.startsWith("✗")) return outputLine("err", line);
      if (head.startsWith("→")) return outputLine("info", line);
      return outputLine(null, line);
    }).join("\n") + "\n";
  }

  // "What will be created": tree lines muted, names in bold, the kind of each entity muted.
  function plan(text) {
    return text.replace(/\n$/, "").split("\n").map((line) => {
      const match = line.match(/^([\s│├└─]*)(\S+)(\s+)(.*)$/);
      if (!match) return escape(line);
      const [, tree, name, gap, kind] = match;
      return span("op", tree) + span("key", name) + gap + span("comment", kind);
    }).join("\n") + "\n";
  }

  function paint() {
    collectNames([...document.querySelectorAll(".highlight.language-bash pre > code")].map((code) => code.textContent));
    document.querySelectorAll(".highlight.plan pre > code:not([data-terminal])").forEach((code) => {
      code.innerHTML = plan(code.textContent);
      code.dataset.terminal = "";
    });
    document.querySelectorAll(".highlight.language-bash pre > code:not([data-terminal])").forEach((code) => {
      code.innerHTML = shell(code.textContent);
      code.dataset.terminal = "";
    });
    document.querySelectorAll(".highlight.output pre > code:not([data-terminal])").forEach((code) => {
      code.innerHTML = output(code.textContent);
      code.dataset.terminal = "";
    });
  }

  if (typeof document$ !== "undefined") document$.subscribe(paint);
  else document.addEventListener("DOMContentLoaded", paint);
})();
