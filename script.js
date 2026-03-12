document.addEventListener("DOMContentLoaded", () => {
    const year = new Date().getFullYear();
    document.querySelectorAll("[data-current-year]").forEach((node) => {
        node.textContent = String(year);
    });

    const currentPage = window.location.pathname.split("/").pop() || "index.html";
    const pageKey = currentPage === "services.html"
        ? "services"
        : currentPage === "contact.html"
            ? "contact"
            : currentPage === "about.html"
                ? "about"
                : "home";

    document.querySelectorAll("[data-nav]").forEach((link) => {
        if (link.dataset.nav === pageKey) {
            link.classList.add("is-active");
            link.setAttribute("aria-current", "page");
        }
    });
});
