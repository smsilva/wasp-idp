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
  const label = pt ? ["Conta de emergência?", "Entrar com usuário e senha"] : ["Emergency account?", "Sign in with username and password"];
  toggle.append(label[0] + " ");
  const link = document.createElement("a");
  link.textContent = label[1];
  link.addEventListener("click", () => { form.classList.remove("platform-collapsed"); toggle.remove(); });
  toggle.append(link);
  form.before(toggle);
});
