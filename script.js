document.addEventListener("DOMContentLoaded", () => {
    const year = new Date().getFullYear();
    document.querySelectorAll("[data-current-year]").forEach((node) => {
        node.textContent = String(year);
    });

    // The shared renderer marks the current navigation section, including
    // service detail pages. Keep that single source of truth with or without JS.

    const disclosures = [...document.querySelectorAll(".home-card-disclosure")];
    const setExpanded = (disclosure, expanded) => {
        disclosure.open = expanded;
        disclosure.querySelector("summary").setAttribute("aria-expanded", String(expanded));
    };
    disclosures.forEach((disclosure) => {
        const arrow = disclosure.querySelector("summary");
        arrow.setAttribute("aria-expanded", String(disclosure.open));
        arrow.addEventListener("click", (event) => {
            event.preventDefault();
            const expanded = !disclosure.open;
            // Close the previous answer before opening this one.
            disclosures.forEach((other) => {
                if (other !== disclosure) setExpanded(other, false);
            });
            setExpanded(disclosure, expanded);
        });
        disclosure.addEventListener("toggle", () => {
            arrow.setAttribute("aria-expanded", String(disclosure.open));
        });
        arrow.addEventListener("keydown", (event) => {
            if (event.key === "Escape") setExpanded(disclosure, false);
        });
    });
});
