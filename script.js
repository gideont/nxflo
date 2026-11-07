document.addEventListener("DOMContentLoaded", () => {
    const year = new Date().getFullYear();
    document.querySelectorAll("[data-current-year]").forEach((node) => {
        node.textContent = String(year);
    });

    document.querySelectorAll("[data-nav-dropdown]").forEach((tools) => {
    const toggle = tools?.querySelector("button");
    const menu = tools?.querySelector("[data-dropdown-menu]");
    if (tools && toggle && menu) {
        let closeTimer;
        let pinned = false;
        const setOpen = (open) => {
            clearTimeout(closeTimer);
            toggle.setAttribute("aria-expanded", String(open));
            menu.hidden = !open;
            if (!open) pinned = false;
        };
        toggle.addEventListener("click", () => {
            const open = menu.hidden || !pinned;
            setOpen(open);
            pinned = open;
        });
        tools.addEventListener("pointerenter", (event) => {
            if (event.pointerType === "mouse") setOpen(true);
        });
        tools.addEventListener("pointerleave", (event) => {
            if (event.pointerType === "mouse" && !pinned) closeTimer = setTimeout(() => setOpen(false), 180);
        });
        tools.addEventListener("focusout", (event) => {
            if (!tools.contains(event.relatedTarget)) setOpen(false);
        });
        tools.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown" && !menu.contains(event.target)) {
                event.preventDefault(); setOpen(true); menu.querySelector("a").focus();
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !menu.hidden) {
                const restoreFocus = tools.contains(document.activeElement);
                setOpen(false);
                if (restoreFocus) toggle.focus();
            }
        });
        document.addEventListener("click", (event) => {
            if (!tools.contains(event.target)) setOpen(false);
        });
    }

    });

    // The shared renderer marks the current navigation section, including
    // service detail pages. Keep that single source of truth with or without JS.

});

// Count public page loads only; never send query strings, file contents, or form data.
(() => {
  const path = location.pathname === '/index.html' ? '/' : location.pathname;
  if (path === '/admin.html' || path === '/admin' || !/^\/(?:[a-z0-9-]+\.html)?$/.test(path)) return;
  if (navigator.globalPrivacyControl || navigator.doNotTrack === '1') return;
  const send = () => fetch('/bms_integration_hub/api/analytics/collect', {
    method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})
  }).catch(() => {});
  if (document.visibilityState === 'visible') send();
  else document.addEventListener('visibilitychange', function visible() {
    if (document.visibilityState === 'visible') { document.removeEventListener('visibilitychange', visible); send(); }
  });
})();
