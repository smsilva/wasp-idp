// Prerequisite tables (`<div class="checks" markdown>` around a Markdown table): each command in the Check
// column becomes a chip that copies it, and a footer row copies them all, one per line.
(() => {
  const ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12V1z"/></svg>';

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = Object.assign(document.createElement("textarea"), { value: text });
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
  }

  // The button shows it worked for a moment: green, and "Copied" when it has a label.
  function confirm(button) {
    const label = button.querySelector(".label");
    const before = label?.textContent;
    button.classList.add("copied");
    if (label) label.textContent = "Copied";
    setTimeout(() => {
      button.classList.remove("copied");
      if (label) label.textContent = before;
    }, 1400);
  }

  function chip(code) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "check-chip";
    button.title = "Copy";
    button.textContent = code.textContent;
    button.insertAdjacentHTML("beforeend", ICON);
    button.addEventListener("click", () => copy(code.textContent).then(() => confirm(button)));
    code.replaceWith(button);
    return code.textContent;
  }

  function paint() {
    document.querySelectorAll(".checks table:not([data-checks])").forEach((table) => {
      table.dataset.checks = "";
      const column = [...table.tHead.rows[0].cells].findIndex((cell) => cell.textContent.trim() === "Check");
      if (column < 0) return;
      const commands = [...table.tBodies[0].rows].map((row) => row.cells[column]?.querySelector("code")).filter(Boolean).map(chip);
      const footer = table.createTFoot().insertRow().insertCell();
      footer.colSpan = table.tHead.rows[0].cells.length;
      footer.innerHTML = `<div class="checks-footer"><span>Click a check to copy it.</span><button type="button" class="check-all">${ICON}<span class="label">Copy all checks</span></button></div>`;
      const all = footer.querySelector("button");
      all.addEventListener("click", () => copy(commands.join("\n")).then(() => confirm(all)));
    });
  }

  if (typeof document$ !== "undefined") document$.subscribe(paint);
  else document.addEventListener("DOMContentLoaded", paint);
})();
