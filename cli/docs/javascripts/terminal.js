// Terminal look for command blocks, in the colors of the deck (docs/presentation): a `$` prompt on each
// command, options and their values in their own colors, and ✓/✗ lines of the output in green/red.
// The prompt is a CSS pseudo-element, so the copy button still copies the commands only.
(() => {
  // Options that take no value: the word after them is an argument, not their value.
  const FLAGS = new Set(["--wait", "--default", "--dry-run", "--yes", "--all", "--no-browser", "--use-device-code",
    "--skip-init", "--force", "--editable", "--quiet", "--admin", "--compact-output"]);
  const OPERATORS = new Set(["|", "||", "&&", ";", ">", ">>", "<", "\\", "--"]);
  // Verbs of the platform and kubectl commands: the word before one is the concept, the first argument
  // after it is the object; both are shown in bold.
  const VERBS = new Set(["create", "delete", "get", "list", "add", "remove", "share", "unshare", "verify", "default",
    "import", "render", "logs", "exec", "describe", "apply", "auth"]);

  const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const span = (kind, text) => `<span class="t-${kind}">${escape(text)}</span>`;

  // Words and the spaces between them, keeping quoted strings whole.
  function words(line) {
    return line.match(/\s+|'[^']*'|"[^"]*"|[^\s'"]+(?:'[^']*'|"[^"]*")?[^\s'"]*/g) || [];
  }

  function shell(text) {
    let continued = false;
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
      const start = !continued;
      continued = /\\\s*$/.test(line);
      let first = start;
      let expectValue = false;
      const parts = words(line);
      // Concept and object of the command: the word before the verb and the first argument after it.
      const bold = new Set();
      if (start) {
        const plain = parts.map((word, index) => [word, index]).filter(([word]) => !/^\s+$/.test(word));
        const verb = plain.findIndex(([word], position) => position > 0 && VERBS.has(word));
        if (verb > 0) {
          if (verb > 1) bold.add(plain[verb - 1][1]);
          const object = plain.slice(verb + 1).find(([word]) => !word.startsWith("-") && !OPERATORS.has(word));
          if (object) bold.add(object[1]);
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
          first = false;
          return span("cmd", word);
        }
        if (word.startsWith("--")) {
          expectValue = !FLAGS.has(word) && !word.includes("=");
          return span("opt", word);
        }
        if (expectValue) {
          expectValue = false;
          return span("val", word);
        }
        if (bold.has(index)) return span("key", word);
        if (/^['"$]/.test(word)) return span("val", word);
        return span("arg", word);
      }).join("");
      return (start ? '<span class="t-prompt"></span>' : '<span class="t-indent"></span>') + html;
    }).join("\n") + "\n";
  }

  function output(text) {
    return text.replace(/\n$/, "").split("\n").map((line) => {
      const head = line.trimStart();
      if (head.startsWith("✓")) return span("ok", line);
      if (head.startsWith("✗")) return span("err", line);
      if (head.startsWith("→")) return span("info", line);
      return escape(line);
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
