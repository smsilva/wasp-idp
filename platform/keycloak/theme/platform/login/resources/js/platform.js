// platform theme (#173): on the login page, Google is the main action and the local account
// form stays behind a link. Without JavaScript the form is simply visible.
document.addEventListener("DOMContentLoaded", () => {
  const pt = document.documentElement.lang.startsWith("pt");
  const googleName = document.querySelector("#social-google span");
  if (googleName) googleName.textContent = pt ? "Continuar com Google" : "Continue with Google";
  if (document.body.dataset.pageId !== "login-login") return;
  const form = document.getElementById("kc-form");
  const google = document.getElementById("social-google");
  if (!form || !google) return;
  const hasError = document.querySelector(".pf-v5-c-alert, .kc-feedback-text, [aria-invalid='true']");
  if (hasError) return;
  form.classList.add("platform-collapsed");
  const toggle = document.createElement("div");
  toggle.className = "platform-local-toggle";
  const link = document.createElement("a");
  link.textContent = pt ? "Entrar com usuário e senha" : "Sign in with username and password";
  link.addEventListener("click", () => { form.classList.remove("platform-collapsed"); toggle.remove(); });
  toggle.append(link);
  form.before(toggle);
});

// platform theme (#537): the device code as eight boxes, XXXX-XXXX like Keycloak generates it. Pasting the whole
// code in any box fills them all. The stock field stays in the form, hidden, and receives the joined value, so the
// POST is unchanged; without JavaScript the stock field is shown.
document.addEventListener("DOMContentLoaded", () => {
  const field = document.getElementById("device-user-code");
  if (!field) return;
  const size = 4;
  const clean = (text) => text.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const boxes = [];
  const row = document.createElement("div");
  row.className = "platform-code";
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", field.labels?.[0]?.textContent.trim() || "Code");
  for (let index = 0; index < size * 2; index++) {
    if (index === size) {
      const dash = document.createElement("span");
      dash.className = "dash";
      dash.textContent = "-";
      dash.setAttribute("aria-hidden", "true");
      row.append(dash);
    }
    const box = document.createElement("input");
    box.type = "text";
    box.inputMode = "text";
    box.autocomplete = index === 0 ? "one-time-code" : "off";
    box.maxLength = 1;
    box.setAttribute("autocapitalize", "characters");
    box.setAttribute("spellcheck", "false");
    box.setAttribute("aria-label", `${index + 1}`);
    boxes.push(box);
    row.append(box);
  }
  const sync = () => {
    const value = boxes.map((box) => box.value).join("");
    field.value = value.length > size ? `${value.slice(0, size)}-${value.slice(size)}` : value;
    row.classList.toggle("complete", value.length === boxes.length);
  };
  // Writes the characters from box `start` on, and focuses the box after the last one written.
  const fill = (start, text) => {
    const chars = clean(text).slice(0, boxes.length - start).split("");
    chars.forEach((char, offset) => { boxes[start + offset].value = char; });
    sync();
    // A complete code moves on to Continue: Enter or Space submits it.
    const submit = row.closest("form")?.querySelector("[type=submit]");
    if (row.classList.contains("complete") && submit) submit.focus();
    else if (chars.length) boxes[Math.min(start + chars.length, boxes.length - 1)].focus();
    return chars.length;
  };
  boxes.forEach((box, index) => {
    box.addEventListener("input", () => {
      const typed = box.value;
      box.value = "";
      if (!fill(index, typed)) sync();
    });
    box.addEventListener("paste", (event) => {
      event.preventDefault();
      // A pasted code starts over from the first box, wherever the cursor was.
      const text = clean(event.clipboardData.getData("text"));
      if (text.length >= boxes.length) {
        boxes.forEach((other) => { other.value = ""; });
        fill(0, text);
      } else {
        fill(index, text);
      }
    });
    box.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !box.value && index > 0) {
        boxes[index - 1].value = "";
        boxes[index - 1].focus();
        sync();
        event.preventDefault();
      } else if (event.key === "ArrowLeft" && index > 0) {
        boxes[index - 1].focus();
        event.preventDefault();
      } else if (event.key === "ArrowRight" && index < boxes.length - 1) {
        boxes[index + 1].focus();
        event.preventDefault();
      }
    });
    box.addEventListener("focus", () => box.select());
  });
  field.type = "hidden";
  field.removeAttribute("autofocus");
  field.after(row);
  // A code already in the stock field (an error page keeps it) shows up in the boxes.
  if (field.value) fill(0, field.value);
  if (!field.value) boxes[0].focus();
});
