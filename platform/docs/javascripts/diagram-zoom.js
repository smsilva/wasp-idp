// Click a Mermaid diagram to see it scaled to the window; click again, click outside or Esc to close.
// Material renders each diagram inside a closed shadow root, so the host element itself is scaled.
(() => {
  let open = null;

  function close() {
    if (!open) return;
    open.host.removeAttribute("style");
    open.host.classList.remove("diagram-zoomed");
    open.placeholder.remove();
    open.backdrop.remove();
    open = null;
  }

  function zoom(host) {
    const rect = host.getBoundingClientRect();
    const scale = Math.min((window.innerWidth * 0.94) / rect.width, (window.innerHeight * 0.88) / rect.height);
    const placeholder = document.createElement("div");
    placeholder.style.height = `${rect.height}px`;
    host.before(placeholder);
    const backdrop = document.createElement("div");
    backdrop.className = "diagram-backdrop";
    document.body.append(backdrop);
    host.classList.add("diagram-zoomed");
    host.style.width = `${rect.width}px`;
    host.style.transform = `translate(-50%, -50%) scale(${scale})`;
    open = { host, placeholder, backdrop };
  }

  document.addEventListener("click", (event) => {
    if (open) {
      close();
      return;
    }
    const host = event.target.closest && event.target.closest(".mermaid");
    if (host) zoom(host);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
})();
